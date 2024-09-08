from __future__ import annotations

import asyncio
from typing import Any, Callable, Generic, Optional, Union, overload

from .typing import T


class _cached_prop(Generic[T]):
    def __init__(self, fget: Callable[..., T], name: str, doc: Optional[str] = None):
        self.fget = fget
        self.__doc__ = doc
        self.__name__ = name

    def __get__(self, obj: Optional[object], cls: Any) -> T:
        raise NotImplementedError


def cachedprop(fget: Callable[..., T], doc: Optional[str] = None, name: Optional[str] = None) -> _cached_prop[T]:
    doc = doc or fget.__doc__
    name = name or fget.__name__
    if asyncio.iscoroutinefunction(fget):
        return _cached_prop_loop[T](fget, name, doc)
    return _cached_prop_sync[T](fget, name, doc)


class _cached_prop_sync(_cached_prop[T]):
    @overload
    def __get__(self, obj: None, cls: Any) -> _cached_prop_sync: ...

    @overload
    def __get__(self, obj: object, cls: Any) -> T: ...

    def __get__(self, obj: Optional[object], cls: Any) -> Union[_cached_prop_sync, T]:
        if obj is None:
            return self
        obj.__dict__[self.__name__] = rv = self.fget(obj)
        return rv


class _cached_awaitable_coro(Generic[T]):
    slots = ["coro_f", "obj", "_result", "_awaitable"]

    def __init__(self, coro_f: Callable[..., T], obj: object):
        self.coro_f = coro_f
        self.obj = obj
        self._awaitable = self.__fetcher

    async def __fetcher(self) -> T:
        self._result = rv = await self.coro_f(self.obj)  # type: ignore
        self._awaitable = self.__cached
        return rv

    async def __cached(self) -> T:
        return self._result

    def __await__(self):
        return self._awaitable().__await__()


class _cached_prop_loop(_cached_prop[T]):
    @overload
    def __get__(self, obj: None, cls: Any) -> _cached_prop_loop: ...

    @overload
    def __get__(self, obj: object, cls: Any) -> T: ...

    def __get__(self, obj: Optional[object], cls: Any) -> Union[_cached_prop_loop, T]:
        if obj is None:
            return self
        obj.__dict__[self.__name__] = rv = _cached_awaitable_coro[T](self.fget, obj)
        return rv  # type: ignore
