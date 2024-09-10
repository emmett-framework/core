from http.cookies import SimpleCookie
from typing import Any

from ...datastructures import sdict
from ...utils import cachedprop
from . import Wrapper
from .helpers import ResponseHeaders


class Response(Wrapper):
    __slots__ = ("status", "headers", "cookies")

    def __init__(self):
        self.status = 200
        self.headers = ResponseHeaders({"content-type": "text/plain"})
        self.cookies = SimpleCookie()

    @cachedprop
    def meta(self) -> sdict[str, Any]:
        return sdict()

    @cachedprop
    def meta_prop(self) -> sdict[str, Any]:
        return sdict()

    @property
    def content_type(self) -> str:
        return self.headers["content-type"]

    @content_type.setter
    def content_type(self, value: str):
        self.headers["content-type"] = value
