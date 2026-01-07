from abc import abstractmethod
from typing import Any

from . import IngressWrapper


class Websocket(IngressWrapper):
    __slots__ = ["_flow_receive", "_flow_send", "receive", "send"]

    def _bind_flow(self, flow_receive, flow_send):
        self._flow_receive = flow_receive
        self._flow_send = flow_send

    @abstractmethod
    async def accept(self, headers: dict[str, str] | None = None, subprotocol: str | None = None): ...

    async def _accept_and_receive(self) -> Any:
        await self.accept()
        return await self.receive()

    async def _accept_and_send(self, data: Any):
        await self.accept()
        await self.send(data)

    @abstractmethod
    async def _wrapped_receive(self) -> Any: ...

    @abstractmethod
    async def _wrapped_send(self, data: Any): ...
