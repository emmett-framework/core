from http.cookies import SimpleCookie

from ..response import HTTPAsyncIterResponse, HTTPFileResponse, HTTPIOResponse, HTTPIterResponse
from . import Wrapper
from .helpers import ResponseHeaders


class Response(Wrapper):
    __slots__ = ("status", "headers", "cookies")

    def __init__(self):
        self.status = 200
        self.headers = ResponseHeaders({"content-type": "text/plain"})
        self.cookies = SimpleCookie()

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
