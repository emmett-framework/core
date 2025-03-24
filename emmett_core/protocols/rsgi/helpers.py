import asyncio
from typing import AsyncGenerator

from ...http.response import HTTPBytesResponse, HTTPResponse
from ...http.wrappers.response import ResponseStream as _ResponseStream


class BodyWrapper:
    __slots__ = ["proto", "timeout"]

    def __init__(self, proto, timeout):
        self.proto = proto
        self.timeout = timeout

    def __await__(self):
        if self.timeout:
            return self._await_with_timeout().__await__()
        return self.proto().__await__()

    async def _await_with_timeout(self):
        try:
            rv = await asyncio.wait_for(self.proto(), timeout=self.timeout)
        except asyncio.TimeoutError:
            raise HTTPBytesResponse(408, b"Request timeout")
        return rv

    async def __aiter__(self) -> AsyncGenerator[bytes, None]:
        async for chunk in self.proto:
            yield chunk


class ResponseStream(_ResponseStream):
    __slots__ = []

    async def __call__(self):
        for method in self.response._flow_stream:
            method()
        self._proto = self._proto.response_stream(self.response.status, list(HTTPResponse.rsgi_headers(self)))
        async for item in self._target:
            await self.send(self._item_wrapper(item))
        return noop_response

    def send(self, data):
        if isinstance(data, str):
            return self._proto.send_str(data)
        return self._proto.send_bytes(data)


class NoopResponse:
    def rsgi(self, protocol):
        return


class WSTransport:
    __slots__ = ["protocol", "transport", "accepted", "interrupted", "input", "status", "noop"]

    def __init__(self, protocol) -> None:
        self.protocol = protocol
        self.transport = None
        self.accepted = asyncio.Event()
        self.input = asyncio.Queue()
        self.interrupted = False
        self.status = 200
        self.noop = asyncio.Event()

    async def init(self):
        self.transport = await self.protocol.accept()
        self.accepted.set()

    @property
    def receive(self):
        return self.input.get


noop_response = NoopResponse()
