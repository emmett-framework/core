from __future__ import annotations

import asyncio
import os
import re
from typing import Awaitable, Callable, Optional, Tuple

from ...ctx import RequestContext, WSContext
from ...http.response import HTTPFileResponse, HTTPResponse, HTTPStringResponse
from ...utils import cachedprop
from .helpers import WSTransport, noop_response
from .wrappers import Request, Response, Websocket


REGEX_STATIC = re.compile(r"^/static/(?P<m>__[\w\-\.]+__/)?(?P<v>_\d+\.\d+\.\d+/)?(?P<f>.*?)$")
REGEX_STATIC_LANG = re.compile(r"^/(?P<l>\w{2}/)?static/(?P<m>__[\w\-\.]__+/)?(?P<v>_\d+\.\d+\.\d+/)?(?P<f>.*?)$")


class Handler:
    __slots__ = ["app", "current"]

    def __init__(self, app, current):
        self.app = app
        self.current = current


class RequestHandler(Handler):
    __slots__ = ["router"]

    def __init__(self, app, current):
        super().__init__(app, current)
        self._bind_router()
        self._configure_methods()

    def _bind_router(self):
        raise NotImplementedError

    def _configure_methods(self):
        raise NotImplementedError


class HTTPHandler(RequestHandler):
    __slots__ = ["pre_handler", "static_handler", "static_matcher", "__dict__"]
    wapper_cls = Request
    response_cls = Response

    def _bind_router(self):
        self.router = self.app._router_http

    def _configure_methods(self):
        self.static_matcher = (
            self._static_lang_matcher if self.app.language_force_on_url else self._static_nolang_matcher
        )
        self.static_handler = self._static_handler if self.app.config.handle_static else self.dynamic_handler
        self.pre_handler = self._prefix_handler if self.router._prefix_main else self.static_handler

    async def __call__(self, scope, protocol):
        task_transport = asyncio.create_task(self.handle_disconnect(protocol))
        task_request = asyncio.create_task(self.handle_request(scope, protocol))
        _, pending = await asyncio.wait([task_request, task_transport], return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()

    async def handle_disconnect(self, protocol):
        await protocol.client_disconnect()

    async def handle_request(self, scope, protocol):
        http = await self.pre_handler(scope, protocol, scope.path)
        if coro := http.rsgi(protocol):
            if self.app.config.response_timeout is None:
                await coro
                return
            try:
                await asyncio.wait_for(coro, self.app.config.response_timeout)
            except asyncio.TimeoutError:
                self.app.log.warn(f"Timeout sending response: ({scope.path})")

    @cachedprop
    def error_handler(self) -> Callable[[], Awaitable[str]]:
        return self.exception_handler

    @cachedprop
    def exception_handler(self) -> Callable[[], Awaitable[str]]:
        return self.app.error_handlers.get(500, self._exception_handler)

    @staticmethod
    async def _http_response(code: int) -> HTTPResponse:
        return HTTPResponse(code)

    def _prefix_handler(self, scope, protocol, path: str) -> Awaitable[HTTPResponse]:
        if not path.startswith(self.router._prefix_main):
            return self._http_response(404)
        path = path[self.router._prefix_main_len :] or "/"
        return self.static_handler(scope, protocol, path)

    def _static_lang_matcher(self, path: str) -> Tuple[Optional[str], Optional[str]]:
        match = REGEX_STATIC_LANG.match(path)
        if match:
            lang, mname, version, file_name = match.group("l", "m", "v", "f")
            if mname:
                mod = self.app._modules.get(mname)
                spath = mod._static_path if mod else self.app.static_path
            else:
                spath = self.app.static_path
            static_file = os.path.join(spath, file_name)
            if lang:
                lang_file = os.path.join(spath, lang, file_name)
                if os.path.exists(lang_file):
                    static_file = lang_file
            return static_file, version
        return None, None

    def _static_nolang_matcher(self, path: str) -> Tuple[Optional[str], Optional[str]]:
        if path.startswith("/static/"):
            mname, version, file_name = REGEX_STATIC.match(path).group("m", "v", "f")
            if mname:
                mod = self.app._modules.get(mname[2:-3])
                static_file = os.path.join(mod._static_path, file_name) if mod else None
            elif file_name:
                static_file = os.path.join(self.app.static_path, file_name)
            else:
                static_file = None
            return static_file, version
        return None, None

    async def _static_response(self, file_path: str) -> HTTPFileResponse:
        return HTTPFileResponse(file_path)

    def _static_handler(self, scope, protocol, path: str) -> Awaitable[HTTPResponse]:
        static_file, _ = self.static_matcher(path)
        if static_file:
            return self._static_response(static_file)
        return self.dynamic_handler(scope, protocol, path)

    async def dynamic_handler(self, scope, protocol, path: str) -> HTTPResponse:
        request = self.__class__.wapper_cls(
            scope,
            path,
            protocol,
            max_content_length=self.app.config.request_max_content_length,
            max_multipart_size=self.app.config.request_multipart_max_size,
            body_timeout=self.app.config.request_body_timeout,
        )
        response = self.response_cls(protocol)
        ctx = RequestContext(self.app, request, response)
        ctx_token = self.current._init_(ctx)
        try:
            http = await self.router.dispatch(request, response)
        except HTTPResponse as http_exception:
            http = http_exception
            #: render error with handlers if in app
            error_handler = self.app.error_handlers.get(http.status_code)
            if error_handler:
                http = HTTPStringResponse(
                    http.status_code, await error_handler(), headers=response.headers, cookies=response.cookies
                )
        except asyncio.CancelledError:
            http = noop_response
        except Exception:
            self.app.log.exception("Application exception:")
            http = HTTPStringResponse(500, await self.error_handler(), headers=response.headers)
        finally:
            self.current._close_(ctx_token)
        return http

    async def _exception_handler(self) -> str:
        self.current.response.headers._data["content-type"] = "text/plain"
        return "Internal error"


class WSHandler(RequestHandler):
    __slots__ = ["pre_handler", "__dict__"]
    wrapper_cls = Websocket

    def _bind_router(self):
        self.router = self.app._router_ws

    def _configure_methods(self):
        self.pre_handler = self._prefix_handler if self.router._prefix_main else self.dynamic_handler

    async def __call__(self, scope, protocol):
        transport = WSTransport(protocol)
        task_transport = asyncio.create_task(self.handle_transport(transport))
        task_request = asyncio.create_task(self.handle_request(scope, transport))
        _, pending = await asyncio.wait([task_request, task_transport], return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        self._close_connection(transport)

    async def handle_transport(self, transport: WSTransport):
        await transport.accepted.wait()
        try:
            while True:
                msg = await transport.transport.receive()
                # if msg.kind == WebsocketMessageType.close:
                if msg.kind == 0:
                    transport.interrupted = True
                    break
                await transport.input.put(msg)
        # except ProtocolClosed:
        except RuntimeError:
            transport.interrupted = True

    def handle_request(self, scope, transport: WSTransport):
        return self.pre_handler(scope, transport, scope.path)

    async def _empty_awaitable(self):
        return

    def _prefix_handler(self, scope, transport: WSTransport, path: str) -> Awaitable[None]:
        if not path.startswith(self.router._prefix_main):
            transport.status = 404
            return self._empty_awaitable()
        path = path[self.router._prefix_main_len :] or "/"
        return self.dynamic_handler(scope, transport, path)

    async def dynamic_handler(self, scope, transport: WSTransport, path: str):
        ctx = WSContext(self.app, self.__class__.wrapper_cls(scope, path, transport))
        ctx_token = self.current._init_(ctx)
        try:
            await self.router.dispatch(ctx.websocket)
        except HTTPResponse as http:
            transport.status = http.status_code
        except asyncio.CancelledError:
            if not transport.interrupted:
                self.app.log.exception("Application exception:")
        except Exception:
            transport.status = 500
            self.app.log.exception("Application exception:")
        finally:
            self.current._close_(ctx_token)

    def _close_connection(self, transport: WSTransport):
        transport.protocol.close(transport.status)
