from typing import Any, Dict

from ..http.wrappers.response import ServerSentEvent
from ..routing.router import RouterMixin
from .extras import JSONPipe, RequirePipe, SSEPipe, StreamPipe


class PipeBuilder(object):
    def build_pipe(self):
        raise NotImplementedError

    def __call__(self, func):
        obj = RouterMixin.exposing()
        obj.pipeline.append(self.build_pipe())
        return func


class ServicePipeBuilder:
    _pipe_cls = {"json": JSONPipe}

    def __call__(self, procedure):
        pipe_cls = self.__class__._pipe_cls.get(procedure)
        if not pipe_cls:
            raise RuntimeError(f"Unknwon service: {procedure}")
        return pipe_cls()


class requires(PipeBuilder):
    _pipe_cls = RequirePipe

    def __init__(self, condition=None, otherwise=None):
        if condition is None or otherwise is None:
            raise SyntaxError("requires usage: @requires(condition, otherwise)")
        if not callable(otherwise) and not isinstance(otherwise, str):
            raise SyntaxError("requires 'otherwise' param must be string or callable")
        self.condition = condition
        self.otherwise = otherwise

    def build_pipe(self):
        return self.__class__._pipe_cls(self.condition, self.otherwise)


class service(PipeBuilder):
    _inner_builder = ServicePipeBuilder()

    def __init__(self, procedure):
        self.procedure = procedure

    @classmethod
    def json(cls, f):
        return cls("json")(f)

    def build_pipe(self):
        return self._inner_builder(self.procedure)


class stream(PipeBuilder):
    _pipe_cls = StreamPipe

    def __init__(
        self,
        status: int = 200,
        headers: Dict[str, str] = {},
        cookies: Dict[str, Any] = {},
    ):
        self.response_status = status
        self.response_headers = headers
        self.response_cookies = cookies

    def build_pipe(self):
        return self.__class__._pipe_cls(
            status=self.response_status,
            headers=self.response_headers,
            cookies=self.response_cookies,
        )


class sse(stream):
    _pipe_cls = SSEPipe
    Event = ServerSentEvent
