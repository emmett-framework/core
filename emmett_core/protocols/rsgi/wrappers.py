from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from urllib.parse import parse_qs

from ...datastructures import sdict
from ...http.response import HTTPBytesResponse, HTTPResponse
from ...http.wrappers.helpers import regex_client
from ...http.wrappers.request import Request as _Request
from ...http.wrappers.response import Response as _Response
from ...http.wrappers.websocket import Websocket as _Websocket
from ...utils import cachedprop
from .helpers import BodyWrapper, ResponseStream


class RSGIIngressMixin:
    def __init__(self, scope, path, protocol):
        self._scope = scope
        self._proto = protocol
        self.scheme = scope.scheme
        self.path: str = path

    @property
    def headers(self):
        return self._scope.headers

    @cachedprop
    def host(self) -> str:
        if self._scope.http_version[0] == "1":
            return self.headers.get("host")
        return self._scope.authority

    @cachedprop
    def query_params(self) -> sdict[str, Union[str, List[str]]]:
        rv: sdict[str, Any] = sdict()
        for key, values in parse_qs(self._scope.query_string, keep_blank_values=True).items():
            if len(values) == 1:
                rv[key] = values[0]
                continue
            rv[key] = values
        return rv

    @cachedprop
    def client(self) -> str:
        g = regex_client.search(self.headers.get("x-forwarded-for", ""))
        client = (
            (g.group() or "").split(",")[0] if g else (self._scope.client.split(":")[0] if self._scope.client else None)
        )
        if client in (None, "", "unknown", "localhost"):
            client = "::1" if self.host.startswith("[") else "127.0.0.1"
        return client  # type: ignore


class Request(RSGIIngressMixin, _Request):
    __slots__ = ["_scope", "_proto"]

    def __init__(
        self,
        scope,
        path,
        protocol,
        max_content_length: Optional[int] = None,
        max_multipart_size: Optional[int] = None,
        body_timeout: Optional[int] = None,
    ):
        super().__init__(scope, path, protocol)
        self.max_content_length = max_content_length
        self.max_multipart_size = max_multipart_size
        self.body_timeout = body_timeout
        self._now = datetime.utcnow()
        self.method = scope.method

    @property
    def _multipart_headers(self):
        return dict(self.headers.items())

    @cachedprop
    def body(self) -> BodyWrapper:
        if self.max_content_length and self.content_length > self.max_content_length:
            raise HTTPBytesResponse(413, b"Request entity too large")
        return BodyWrapper(self._proto, self.body_timeout)

    async def push_promise(self, path: str):
        raise NotImplementedError("RSGI protocol doesn't support HTTP2 push.")


class Response(_Response):
    async def stream(self, target, item_wrapper=None) -> HTTPResponse:
        return await ResponseStream(self, target, item_wrapper=item_wrapper)


class Websocket(RSGIIngressMixin, _Websocket):
    __slots__ = ["_scope", "_proto"]

    def __init__(self, scope, path, protocol):
        super().__init__(scope, path, protocol)
        self._flow_receive = None
        self._flow_send = None
        self.receive = self._accept_and_receive
        self.send = self._accept_and_send

    async def accept(self, headers: Optional[Dict[str, str]] = None, subprotocol: Optional[str] = None):
        if self._proto.transport:
            return
        await self._proto.init()
        self.receive = self._wrapped_receive
        self.send = self._wrapped_send

    async def _wrapped_receive(self) -> Any:
        data = (await self._proto.receive()).data
        for method in self._flow_receive:
            data = method(data)
        return data

    async def _wrapped_send(self, data: Any):
        for method in self._flow_send:
            data = method(data)
        trx = self._proto.transport.send_str if isinstance(data, str) else self._proto.transport.send_bytes
        try:
            await trx(data)
        # except ProtocolClosed:
        except RuntimeError:
            if not self._proto.interrupted:
                raise
            await self._proto.noop.wait()
