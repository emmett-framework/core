from collections.abc import Awaitable, Callable
from typing import Any


Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
Event = dict[str, Any]
EventHandler = Callable[[Any, Scope, Receive, Send, Event], Awaitable[Any]]
EventLooper = Callable[..., Awaitable[tuple[EventHandler, Event]]]
