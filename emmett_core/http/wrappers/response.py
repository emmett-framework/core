from __future__ import annotations

import re
from abc import ABCMeta, abstractmethod
from http.cookies import SimpleCookie

from ..response import HTTPAsyncIterResponse, HTTPFileResponse, HTTPIOResponse, HTTPIterResponse, HTTPResponse
from . import EgressWrapper
from .helpers import ResponseHeaders


_SSE_NEWLINES_RE = re.compile(r"\r\n|\n")


class Response(EgressWrapper):
    __slots__ = ["_flow_stream", "status", "headers", "cookies"]

    def __init__(self, proto):
        super().__init__(proto)
        self.status = 200
        self.headers = ResponseHeaders({"content-type": "text/plain"})
        self.cookies = SimpleCookie()

    def _bind_flow(self, flow_stream):
        self._flow_stream = flow_stream

    @property
    def content_type(self) -> str:
        return self.headers["content-type"]

    @content_type.setter
    def content_type(self, value: str):
        self.headers["content-type"] = value

    def wrap_iter(self, obj) -> HTTPIterResponse:
        return HTTPIterResponse(obj, status_code=self.status, headers=self.headers, cookies=self.cookies)

    def wrap_aiter(self, obj) -> HTTPAsyncIterResponse:
        return HTTPAsyncIterResponse(obj, status_code=self.status, headers=self.headers, cookies=self.cookies)

    def wrap_file(self, path) -> HTTPFileResponse:
        return HTTPFileResponse(str(path), status_code=self.status, headers=self.headers, cookies=self.cookies)

    def wrap_io(self, obj, chunk_size: int = 4096) -> HTTPIOResponse:
        return HTTPIOResponse(
            obj, status_code=self.status, headers=self.headers, cookies=self.cookies, chunk_size=chunk_size
        )

    @abstractmethod
    async def stream(self, target, item_wrapper=None) -> HTTPResponse: ...


class ResponseStream(metaclass=ABCMeta):
    __slots__ = ["response", "_proto", "_target", "_item_wrapper"]

    def __init__(self, response: Response, target, item_wrapper=None):
        self.response = response
        self._proto = response._proto
        self._target = target
        self._item_wrapper = item_wrapper or (lambda v: v)

    @property
    def _headers(self):
        return self.response.headers

    @property
    def _cookies(self):
        return self.response.cookies

    def __await__(self):
        return self().__await__()

    @abstractmethod
    async def __call__(self): ...

    @abstractmethod
    async def send(self, data): ...


class ServerSentEvent:
    __slots__ = ["data", "event", "id", "retry", "comment"]

    def __init__(
        self,
        data,
        event=None,
        id=None,
        retry=-1,
        comment=None,
    ):
        self.data = data
        self.event = event
        self.id = id
        self.retry = retry
        self.comment = comment

    def encode(self, json_encoder) -> bytes:
        stack = bytearray()

        if self.id:
            stack.extend(b"id: " + _SSE_NEWLINES_RE.sub("", self.id).encode("utf8") + b"\r\n")
        if self.comment:
            for part in _SSE_NEWLINES_RE.split(self.comment):
                stack.extend(b": " + part.encode("utf8") + b"\r\n")
        if self.event:
            stack.extend(b"event: " + _SSE_NEWLINES_RE.sub("", self.event).encode("utf8") + b"\r\n")
        if self.data:
            data = self.data
            if not isinstance(data, (bytes, str)):
                data = json_encoder(data)
            if not isinstance(data, bytes):
                data = data.encode("utf8")
            stack.extend(b"data: " + data + b"\r\n")
        if self.retry > -1:
            stack.extend(b"retry: " + str(self.retry).encode() + b"\r\n")

        stack.extend(b"\r\n")
        return bytes(stack)
