from collections.abc import Awaitable, Callable
from typing import TypeVar


T = TypeVar("T")
KT = TypeVar("KT")
VT = TypeVar("VT")

ErrorHandlerType = TypeVar("ErrorHandlerType", bound=Callable[[], Awaitable[str]])
