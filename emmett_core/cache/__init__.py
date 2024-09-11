from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, List, Optional, Union, overload

from ..typing import T
from .handlers import RamCache
from .helpers import CacheDecorator


if TYPE_CHECKING:
    from ..routing.cache import RouteCacheRule


class Cache:
    def __init__(self, **kwargs):
        #: load handlers
        handlers = []
        for key, val in kwargs.items():
            if key == "default":
                continue
            handlers.append((key, val))
        if not handlers:
            handlers.append(("ram", RamCache()))
        #: set handlers
        for name, handler in handlers:
            setattr(self, name, handler)
        _default_handler_name = kwargs.get("default", handlers[0][0])
        self._default_handler = getattr(self, _default_handler_name)

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
        return self._default_handler(key, function, duration)

    def get(self, key: str) -> Any:
        return self._default_handler.get(key)

    def set(self, key: str, value: Any, duration: Union[int, str, None] = "default"):
        self._default_handler.set(key, value, duration)

    def get_or_set(self, key: str, function: Callable[..., T], duration: Union[int, str, None] = "default") -> T:
        return self._default_handler.get_or_set(key, function, duration)

    def clear(self, key: Optional[str] = None):
        self._default_handler.clear(key)

    def response(
        self,
        duration: Union[int, str, None] = "default",
        query_params: bool = True,
        language: bool = True,
        hostname: bool = False,
        headers: List[str] = [],
    ) -> RouteCacheRule:
        return self._default_handler.response(duration, query_params, language, hostname, headers)
