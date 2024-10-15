from __future__ import annotations

from typing import Any

from ..http.response import HTTPAsyncIterResponse, HTTPBytesResponse, HTTPIterResponse, HTTPResponse, HTTPStringResponse
from ..http.wrappers.response import Response
from .rules import HTTPRoutingRule


class MetaResponseBuilder:
    __slots__ = ["route"]

    def __init__(self, route: HTTPRoutingRule):
        self.route = route

    def __call__(self, output: Any, response: Response) -> HTTPResponse:
        return output


class EmptyResponseBuilder(MetaResponseBuilder):
    http_cls = HTTPResponse

    def __call__(self, output: Any, response: Response) -> HTTPResponse:
        return self.http_cls(response.status, headers=response.headers, cookies=response.cookies)


class BytesResponseBuilder(MetaResponseBuilder):
    http_cls = HTTPBytesResponse

    def __call__(self, output: Any, response: Response) -> HTTPBytesResponse:
        return self.http_cls(response.status, output, headers=response.headers, cookies=response.cookies)


class StringResponseBuilder(MetaResponseBuilder):
    http_cls = HTTPStringResponse

    def __call__(self, output: Any, response: Response) -> HTTPStringResponse:
        return self.http_cls(response.status, output, headers=response.headers, cookies=response.cookies)


class IterResponseBuilder(MetaResponseBuilder):
    http_cls = HTTPIterResponse

    def __call__(self, output: Any, response: Response) -> HTTPIterResponse:
        return self.http_cls(output, status_code=response.status, headers=response.headers, cookies=response.cookies)


class AsyncIterResponseBuilder(MetaResponseBuilder):
    http_cls = HTTPAsyncIterResponse

    def __call__(self, output: Any, response: Response) -> HTTPAsyncIterResponse:
        return self.http_cls(output, status_code=response.status, headers=response.headers, cookies=response.cookies)


class ResponseProcessor(StringResponseBuilder):
    def process(self, output: Any, response: Response):
        raise NotImplementedError

    def __call__(self, output: Any, response: Response) -> HTTPResponse:
        if isinstance(output, HTTPResponse):
            return output
        return self.http_cls(
            response.status, self.process(output, response), headers=response.headers, cookies=response.cookies
        )


class AutoResponseBuilder(ResponseProcessor):
    def process(self, output: Any, response: Response) -> str:
        if output is None:
            return ""
        if isinstance(output, str):
            return output
        return str(output)
