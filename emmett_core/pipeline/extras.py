from ..ctx import Current
from ..http.helpers import redirect
from ..parsers import Parsers
from ..serializers import Serializers, _json_type
from .pipe import Pipe


class RequirePipe(Pipe):
    __slots__ = ["condition", "otherwise"]
    _current: Current

    def __init__(self, condition=None, otherwise=None):
        if condition is None or otherwise is None:
            raise SyntaxError("usage: @requires(condition, otherwise)")
        if not callable(otherwise) and not isinstance(otherwise, str):
            raise SyntaxError("'otherwise' param must be string or callable")
        self.condition = condition
        self.otherwise = otherwise

    async def pipe_request(self, next_pipe, **kwargs):
        flag = self.condition()
        if not flag:
            if self.otherwise is not None:
                if callable(self.otherwise):
                    return self.otherwise()
                redirect(self.__class__._current, self.otherwise)
            else:
                redirect(self.__class__._current, "/")
        return await next_pipe(**kwargs)

    async def pipe_ws(self, next_pipe, **kwargs):
        flag = self.condition()
        if not flag:
            return
        await next_pipe(**kwargs)


class JSONPipe(Pipe):
    __slots__ = ["decoder", "encoder"]
    _current: Current
    output = _json_type

    def __init__(self):
        self.decoder = Parsers.get_for("json")
        self.encoder = Serializers.get_for("json")

    async def pipe_request(self, next_pipe, **kwargs):
        self.__class__._current.response.headers._data["content-type"] = "application/json"
        return self.encoder(await next_pipe(**kwargs))

    def on_receive(self, data):
        return self.decoder(data)

    def on_send(self, data):
        return self.encoder(data)
