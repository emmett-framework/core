from __future__ import annotations

import inspect
from functools import wraps

from .pipe import Pipe
from .wrappers import (
    _wrap_flow_request_basic,
    _wrap_flow_request_complete,
    _wrap_flow_request_failure,
    _wrap_flow_request_success,
    _wrap_flow_ws_basic,
    _wrap_flow_ws_complete,
    _wrap_flow_ws_failure,
    _wrap_flow_ws_success,
)


class Pipeline:
    __slots__ = ["_method_open", "_method_close", "pipes"]
    _type_suffix = ""

    def __init__(self, pipes=[]):
        self._method_open = f"open_{self._type_suffix}"
        self._method_close = f"close_{self._type_suffix}"
        self.pipes = pipes

    @staticmethod
    def _awaitable_wrap(f):
        @wraps(f)
        async def awaitable(*args, **kwargs):
            return f(*args, **kwargs)

        return awaitable

    def __call__(self, f):
        raise NotImplementedError

    def _flow_open(self):
        rv = []
        for pipe in self.pipes:
            if pipe._pipeline_all_methods_.issuperset({"open", self._method_open}):
                raise RuntimeError(
                    f"{pipe.__class__.__name__} pipe has double open methods."
                    f" Use `open` or `{self._method_open}`, not both."
                )
            if "open" in pipe._pipeline_all_methods_:
                rv.append(pipe.open)
            if self._method_open in pipe._pipeline_all_methods_:
                rv.append(getattr(pipe, self._method_open))
        return rv

    def _flow_close(self):
        rv = []
        for pipe in reversed(self.pipes):
            if pipe._pipeline_all_methods_.issuperset({"close", self._method_close}):
                raise RuntimeError(
                    f"{pipe.__class__.__name__} pipe has double close methods."
                    f" Use `close` or `{self._method_close}`, not both."
                )
            if "close" in pipe._pipeline_all_methods_:
                rv.append(pipe.close)
            if self._method_close in pipe._pipeline_all_methods_:
                rv.append(getattr(pipe, self._method_close))
        return rv

    def _flow_stream(self):
        rv = []
        for pipe in self.pipes:
            if "on_stream" not in pipe._pipeline_all_methods_:
                continue
            rv.append(pipe.on_stream)
        return rv


class RequestPipeline(Pipeline):
    __slots__ = []
    _type_suffix = "request"

    def _get_proper_wrapper(self, pipe):
        if pipe._pipeline_all_methods_.issuperset({"on_pipe_success", "on_pipe_failure"}):
            rv = _wrap_flow_request_complete
        elif "on_pipe_success" in pipe._pipeline_all_methods_:
            rv = _wrap_flow_request_success
        elif "on_pipe_failure" in pipe._pipeline_all_methods_:
            rv = _wrap_flow_request_failure
        else:
            rv = _wrap_flow_request_basic
        return rv

    def __call__(self, f):
        if not any((inspect.iscoroutinefunction(f), inspect.isasyncgenfunction(f))):
            f = self._awaitable_wrap(f)
        for pipe in reversed(self.pipes):
            if not isinstance(pipe, Pipe):
                continue
            if not pipe._is_flow_request_responsible:
                continue
            wrapper = self._get_proper_wrapper(pipe)
            pipe_method = pipe.pipe_request if "pipe_request" in pipe._pipeline_all_methods_ else pipe.pipe
            f = wrapper(pipe_method, pipe.on_pipe_success, pipe.on_pipe_failure, f)
        return f

    def _output_type(self):
        rv = None
        for pipe in reversed(self.pipes):
            if not pipe._is_flow_request_responsible or pipe.output is None:
                continue
            rv = pipe.output
        return rv


class WebsocketPipeline(Pipeline):
    __slots__ = []
    _type_suffix = "ws"

    def _get_proper_wrapper(self, pipe):
        if pipe._pipeline_all_methods_.issuperset({"on_pipe_success", "on_pipe_failure"}):
            rv = _wrap_flow_ws_complete
        elif "on_pipe_success" in pipe._pipeline_all_methods_:
            rv = _wrap_flow_ws_success
        elif "on_pipe_failure" in pipe._pipeline_all_methods_:
            rv = _wrap_flow_ws_failure
        else:
            rv = _wrap_flow_ws_basic
        return rv

    def __call__(self, f):
        if not inspect.iscoroutinefunction(f):
            f = self._awaitable_wrap(f)
        for pipe in reversed(self.pipes):
            if not isinstance(pipe, Pipe):
                continue
            if not pipe._is_flow_ws_responsible:
                continue
            wrapper = self._get_proper_wrapper(pipe)
            pipe_method = pipe.pipe_ws if "pipe_ws" in pipe._pipeline_all_methods_ else pipe.pipe
            f = wrapper(pipe_method, pipe.on_pipe_success, pipe.on_pipe_failure, f)
        return f

    def _flow_receive(self):
        rv = []
        for pipe in self.pipes:
            if "on_receive" not in pipe._pipeline_all_methods_:
                continue
            rv.append(pipe.on_receive)
        return rv

    def _flow_send(self):
        rv = []
        for pipe in reversed(self.pipes):
            if "on_send" not in pipe._pipeline_all_methods_:
                continue
            rv.append(pipe.on_send)
        return rv
