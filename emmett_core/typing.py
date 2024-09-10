from typing import Awaitable, Callable, TypeVar


T = TypeVar("T")
KT = TypeVar("KT")
VT = TypeVar("VT")

ErrorHandlerType = TypeVar("ErrorHandlerType", bound=Callable[[], Awaitable[str]])
