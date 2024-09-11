from __future__ import annotations

import asyncio
from functools import wraps
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional, Union

from .hash import CacheHashMixin


if TYPE_CHECKING:
    from .handlers import CacheHandler


class CacheDecorator(CacheHashMixin):
    def __init__(self, handler: CacheHandler, key: Optional[str], duration: Union[int, str, None] = "default"):
        super().__init__()
        self._cache = handler
        self.key = key
        self.duration = duration
        self.add_strategy("args")
        self.add_strategy("kwargs", self.dict_strategy)

    def _key_from_wrapped(self, f: Callable[..., Any]) -> str:
        return f.__module__ + "." + f.__name__

    def _wrap_sync(self, f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def wrap(*args, **kwargs) -> Any:
            if not args and not kwargs:
                key = self.key or self._key_from_wrapped(f)
            else:
                key = self._build_ctx_key(args=args, kwargs=kwargs)
            return self._cache.get_or_set(key, lambda: f(*args, **kwargs), self.duration)

        return wrap

    def _wrap_loop(self, f: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(f)
        async def wrap(*args, **kwargs) -> Any:
            if not args and not kwargs:
                key = self.key or self._key_from_wrapped(f)
            else:
                key = self._build_ctx_key(args=args, kwargs=kwargs)
            return await self._cache.get_or_set_loop(key, lambda: f(*args, **kwargs), self.duration)

        return wrap

    def __call__(self, f: Callable[..., Any]) -> Callable[..., Any]:
        rv = self._wrap_loop(f) if asyncio.iscoroutinefunction(f) else self._wrap_sync(f)
        if not self.key:
            self.key = f.__module__ + "." + f.__name__
        return rv
