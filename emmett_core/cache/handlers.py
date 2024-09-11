from __future__ import annotations

import asyncio
import heapq
import pickle
import threading
import time
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, Union, overload

from ..typing import T
from .helpers import CacheDecorator


if TYPE_CHECKING:
    from ..routing.cache import RouteCacheRule


class CacheHandler:
    def __init__(self, prefix: str = "", default_expire: int = 300):
        self._default_expire = default_expire
        self._prefix = prefix

    @staticmethod
    def _key_prefix_(method: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(method)
        def wrap(self, key: Optional[str] = None, *args, **kwargs) -> Any:
            key = self._prefix + key if key is not None else key
            return method(self, key, *args, **kwargs)

        return wrap

    @staticmethod
    def _convert_duration_(method: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(method)
        def wrap(self, key: str, value: Any, duration: Union[int, str, None] = "default") -> Any:
            if duration is None:
                duration = 60 * 60 * 24 * 365
            if duration == "default":
                duration = self._default_expire
            now = time.time()
            return method(
                self,
                key,
                value,
                now=now,
                duration=duration,
                expiration=now + duration,  # type: ignore
            )

        return wrap

    @overload
    def __call__(
        self, key: Optional[str] = None, function: None = None, duration: Union[int, str, None] = "default"
    ) -> CacheDecorator: ...

    @overload
    def __call__(
        self, key: str, function: Optional[Callable[..., T]], duration: Union[int, str, None] = "default"
    ) -> T: ...

    def __call__(
        self,
        key: Optional[str] = None,
        function: Optional[Callable[..., T]] = None,
        duration: Union[int, str, None] = "default",
    ) -> Union[CacheDecorator, T]:
        if function:
            if asyncio.iscoroutinefunction(function):
                return self.get_or_set_loop(key, function, duration)  # type: ignore
            return self.get_or_set(key, function, duration)  # type: ignore
        return CacheDecorator(self, key, duration)

    def get_or_set(self, key: str, function: Callable[[], T], duration: Union[int, str, None] = "default") -> T:
        value = self.get(key)
        if value is None:
            value = function()
            self.set(key, value, duration)
        return value

    async def get_or_set_loop(
        self, key: str, function: Callable[[], T], duration: Union[int, str, None] = "default"
    ) -> T:
        value = self.get(key)
        if value is None:
            value = await function()  # type: ignore
            self.set(key, value, duration)
        return value

    def get(self, key: str) -> Any:
        return None

    def set(self, key: str, value: Any, duration: Union[int, str, None]):
        pass

    def clear(self, key: Optional[str] = None):
        pass

    def response(
        self,
        duration: Union[int, str, None] = "default",
        query_params: bool = True,
        language: bool = True,
        hostname: bool = False,
        headers: List[str] = [],
    ) -> RouteCacheRule:
        from ..routing.cache import RouteCacheRule

        return RouteCacheRule(self, query_params, language, hostname, headers, duration)


class RamElement:
    __slots__ = ("value", "exp", "acc")

    def __init__(self, value: Any, exp: int, acc: int):
        self.value = value
        self.exp = exp
        self.acc = acc


class RamCache(CacheHandler):
    lock = threading.RLock()

    def __init__(self, prefix: str = "", threshold: int = 500, default_expire: int = 300):
        super().__init__(prefix=prefix, default_expire=default_expire)
        self.data: Dict[str, Any] = {}
        self._heap_exp: List[Tuple[int, str]] = []
        self._heap_acc: List[Tuple[float, str]] = []
        self._threshold = threshold

    def _prune(self, now):
        # remove expired items
        while self._heap_exp:
            exp, rk = self._heap_exp[0]
            if exp >= now:
                break
            self._heap_exp.remove((exp, rk))
            element = self.data.get(rk)
            if element and element.exp == exp:
                self._heap_acc.remove((self.data[rk].acc, rk))
                del self.data[rk]
        # remove threshold exceding elements
        while len(self.data) > self._threshold:
            rk = heapq.heappop(self._heap_acc)[1]
            element = self.data.get(rk)
            if element:
                self._heap_exp.remove((element.exp, rk))
                del self.data[rk]

    @CacheHandler._key_prefix_
    def get(self, key: str) -> Any:
        try:
            with self.lock:
                element = self.data[key]
                now = time.time()
                if element.exp < now:
                    return None
                self._heap_acc.remove((element.acc, key))
                element.acc = now
                heapq.heappush(self._heap_acc, (element.acc, key))
            val = element.value
        except KeyError:
            return None
        return val

    @CacheHandler._key_prefix_
    @CacheHandler._convert_duration_
    def set(self, key: str, value: Any, **kwargs):
        with self.lock:
            self._prune(kwargs["now"])
            heapq.heappush(self._heap_exp, (kwargs["expiration"], key))
            heapq.heappush(self._heap_acc, (kwargs["now"], key))
            self.data[key] = RamElement(value, kwargs["expiration"], kwargs["now"])

    @CacheHandler._key_prefix_
    def clear(self, key: Optional[str] = None):
        with self.lock:
            if key is not None:
                try:
                    rv = self.data[key]
                    self._heap_acc.remove((rv.acc, key))
                    self._heap_exp.remove((rv.exp, key))
                    del self.data[key]
                    return
                except Exception:
                    return
            self.data.clear()
            self._heap_acc = []
            self._heap_exp = []


class RedisCache(CacheHandler):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: Optional[str] = None,
        db: int = 0,
        prefix: str = "cache:",
        default_expire: int = 300,
        **kwargs,
    ):
        super().__init__(prefix=prefix, default_expire=default_expire)
        try:
            import redis
        except ImportError:
            raise RuntimeError("no redis module found")
        self._cache = redis.Redis(host=host, port=port, password=password, db=db, **kwargs)

    def _dump_obj(self, value: Any) -> bytes:
        if isinstance(value, int):
            return str(value).encode("ascii")
        return b"!" + pickle.dumps(value)

    def _load_obj(self, value: Any) -> Any:
        if value is None:
            return None
        if value.startswith(b"!"):
            try:
                return pickle.loads(value[1:])  # noqa: S301
            except pickle.PickleError:
                return None
        try:
            return int(value)
        except ValueError:
            return None

    @CacheHandler._key_prefix_
    def get(self, key: str) -> Any:
        return self._load_obj(self._cache.get(key))

    @CacheHandler._key_prefix_
    @CacheHandler._convert_duration_
    def set(self, key: str, value: Any, **kwargs):
        dumped = self._dump_obj(value)
        return self._cache.setex(name=key, time=kwargs["duration"], value=dumped)

    @CacheHandler._key_prefix_
    def clear(self, key: Optional[str] = None):
        if key is not None:
            if key.endswith("*"):
                keys = self._cache.delete(self._cache.keys(key))
                if keys:
                    self._cache.delete(*keys)
                return
            self._cache.delete(key)
            return
        if self._prefix:
            keys = self._cache.keys(self._prefix + "*")
            if keys:
                self._cache.delete(*keys)
            return
        self._cache.flushdb()
