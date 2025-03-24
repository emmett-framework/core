import asyncio
from typing import AsyncGenerator

from ...http.response import HTTPBytesResponse, HTTPResponse
from ...http.wrappers.response import ResponseStream as _ResponseStream


class RequestCancelled(Exception): ...


class BodyWrapper:
    __slots__ = ["proto", "timeout", "_data"]

    def __init__(self, proto, timeout):
        self.proto = proto
        self.timeout = timeout
        self._data = bytearray()

    def _append_data(self, data: bytes):
        if data == b"":
            return
        self._data.extend(data)

    def __await__(self):
        if self.timeout:
            return self._await_with_timeout().__await__()
        return self._load_all().__await__()

    async def _await_with_timeout(self):
        try:
            rv = await asyncio.wait_for(self.proto(), timeout=self.timeout)
        except asyncio.TimeoutError:
            raise HTTPBytesResponse(408, b"Request timeout")
        return rv

    async def __aiter__(self) -> AsyncGenerator[bytes, None]:
        while True:
            event = await self.proto()
            if event["type"] == "http.request":
                yield event["body"]
                if not event.get("more_body", False):
                    break
            elif event["type"] == "http.disconnect":
                raise RequestCancelled

    async def _load_all(self):
        async for chunk in self:
            self._append_data(chunk)
        return bytes(self._data)


class ResponseStream(_ResponseStream):
    __slots__ = []

    async def __call__(self):
        for method in self.response._flow_stream:
            method()
        await self._proto(
            {
                "type": "http.response.start",
                "status": self.response.status,
                "headers": list(HTTPResponse.asgi_headers(self)),
            }
        )
        async for item in self._target:
            await self.send(self._item_wrapper(item))
        await self._proto({"type": "http.response.body", "body": b"", "more_body": False})
        return noop_response

    def send(self, data):
        if isinstance(data, str):
            data = data.encode("utf8")
        return self._proto({"type": "http.response.body", "body": data, "more_body": True})


class NoopResponse:
    async def asgi(self, scope, send):
        return


noop_response = NoopResponse()
