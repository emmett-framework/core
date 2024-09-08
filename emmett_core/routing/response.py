from __future__ import annotations

from typing import Any

from ..http.response import HTTPBytesResponse, HTTPResponse, HTTPStringResponse
from ..wrappers.response import Response
from .rules import HTTPRoutingRule


class MetaResponseBuilder:
    def __init__(self, route: HTTPRoutingRule):
        self.route = route

    def __call__(self, output: Any, response: Response) -> HTTPResponse:
        raise NotImplementedError


class ResponseBuilder(MetaResponseBuilder):
    http_cls = HTTPStringResponse

    def __call__(self, output: Any, response: Response) -> HTTPStringResponse:
        return self.http_cls(response.status, output, headers=response.headers, cookies=response.cookies)


class EmptyResponseBuilder(ResponseBuilder):
    http_cls = HTTPResponse

    def __call__(self, output: Any, response: Response) -> HTTPResponse:
        return self.http_cls(response.status, headers=response.headers, cookies=response.cookies)


class ResponseProcessor(ResponseBuilder):
    def process(self, output: Any, response: Response):
        raise NotImplementedError

    def __call__(self, output: Any, response: Response) -> HTTPStringResponse:
        return self.http_cls(
            response.status, self.process(output, response), headers=response.headers, cookies=response.cookies
        )


class BytesResponseBuilder(MetaResponseBuilder):
    http_cls = HTTPBytesResponse

    def __call__(self, output: Any, response: Response) -> HTTPBytesResponse:
        return self.http_cls(response.status, output, headers=response.headers, cookies=response.cookies)


class AutoResponseBuilder(ResponseProcessor):
    def process(self, output: Any, response: Response) -> str:
        if output is None:
            return ""
        elif isinstance(output, str):
            return output
        return str(output)
