from typing import Any, Awaitable, Callable, Dict, Tuple


Scope = Dict[str, Any]
Receive = Callable[[], Awaitable[Dict[str, Any]]]
Send = Callable[[Dict[str, Any]], Awaitable[None]]
Event = Dict[str, Any]
EventHandler = Callable[[Any, Scope, Receive, Send, Event], Awaitable[Any]]
EventLooper = Callable[..., Awaitable[Tuple[EventHandler, Event]]]
