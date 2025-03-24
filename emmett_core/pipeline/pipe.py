from typing import Optional


class MetaPipe(type):
    _pipeline_methods_ = {
        "open",
        "open_request",
        "open_ws",
        "close",
        "close_request",
        "close_ws",
        "pipe",
        "pipe_request",
        "pipe_ws",
        "on_pipe_success",
        "on_pipe_failure",
        "on_receive",
        "on_send",
        "on_stream",
    }

    def __new__(cls, name, bases, attrs):
        new_class = type.__new__(cls, name, bases, attrs)
        if not bases:
            return new_class
        declared_methods = cls._pipeline_methods_ & set(attrs.keys())
        new_class._pipeline_declared_methods_ = declared_methods
        all_methods = set()
        for base in reversed(new_class.__mro__[:-2]):
            if hasattr(base, "_pipeline_declared_methods_"):
                all_methods = all_methods | base._pipeline_declared_methods_
        all_methods = all_methods | declared_methods
        new_class._pipeline_all_methods_ = all_methods
        new_class._is_flow_request_responsible = bool(
            all_methods & {"pipe", "pipe_request", "on_pipe_success", "on_pipe_failure"}
        )
        new_class._is_flow_ws_responsible = bool(
            all_methods & {"pipe", "pipe_ws", "on_pipe_success", "on_pipe_failure"}
        )
        if all_methods.issuperset({"pipe", "pipe_request"}):
            raise RuntimeError(f"{name} has double pipe methods. Use `pipe` or `pipe_request`, not both.")
        if all_methods.issuperset({"pipe", "pipe_ws"}):
            raise RuntimeError(f"{name} has double pipe methods. Use `pipe` or `pipe_ws`, not both.")
        return new_class


class Pipe(metaclass=MetaPipe):
    output: Optional[str] = None

    async def open(self):
        pass

    async def open_request(self):
        pass

    async def open_ws(self):
        pass

    async def close(self):
        pass

    async def close_request(self):
        pass

    async def close_ws(self):
        pass

    async def pipe(self, next_pipe, **kwargs):
        return await next_pipe(**kwargs)

    async def pipe_request(self, next_pipe, **kwargs):
        return await next_pipe(**kwargs)

    async def pipe_ws(self, next_pipe, **kwargs):
        return await next_pipe(**kwargs)

    async def on_pipe_success(self):
        pass

    async def on_pipe_failure(self):
        pass

    def on_receive(self, data):
        return data

    def on_send(self, data):
        return data

    def on_stream(self):
        pass
