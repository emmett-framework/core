from __future__ import annotations

import asyncio
import copy
from io import BytesIO

from ....ctx import Current, RequestContext
from ....http.response import HTTPResponse, HTTPStringResponse
from ....parsers import Parsers
from ....utils import cachedprop
from ..handlers import HTTPHandler
from ..wrappers import Request, Response
from .helpers import Headers, TestCookieJar
from .scope import ScopeBuilder
from .urls import get_host, url_parse, url_unparse


class ClientContextResponse(Response):
    def __init__(self, original_response: Response):
        super().__init__(original_response._proto)
        self.status = original_response.status
        self.headers._data.update(original_response.headers._data)
        self.cookies.update(original_response.cookies.copy())
        self.__dict__.update(original_response.__dict__)


class ClientContext:
    _response_wrap_cls = ClientContextResponse

    def __init__(self, ctx):
        self.request = Request(ctx.request._scope, ctx.request.path, None)
        self.response = self.__class__._response_wrap_cls(ctx.response)
        self.session = copy.deepcopy(ctx.session)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        pass


class ClientHTTPHandlerMixin:
    _client_ctx_cls = ClientContext

    def __call__(self, scope, protocol):
        return self.handle_request(scope, protocol)

    async def dynamic_handler(self, scope, protocol, path):
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
        except Exception:
            self.app.log.exception("Application exception:")
            http = HTTPStringResponse(500, await self.error_handler(), headers=response.headers)
        finally:
            scope._ctx = self.__class__._client_ctx_cls(ctx)
            self.current._close_(ctx_token)
        return http


class ClientHTTPHandler(ClientHTTPHandlerMixin, HTTPHandler): ...


class ClientResponse:
    def __init__(self, ctx, raw, status, headers):
        self.context = ctx
        self.raw = raw
        self.status = status
        self.headers = headers
        self._close = lambda: None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        pass

    @cachedprop
    def data(self):
        if isinstance(self.raw, bytes):
            return self.raw.decode("utf8")
        return self.raw

    def json(self):
        return Parsers.get_for("json")(self.data)


class EmmettTestClient:
    _current: Current
    _handler_cls = ClientHTTPHandler

    def __init__(self, application, response_wrapper=ClientResponse, use_cookies=True, allow_subdomain_redirects=False):
        self.application = application
        self.response_wrapper = response_wrapper
        if use_cookies:
            self.cookie_jar = TestCookieJar()
        else:
            self.cookie_jar = None
        self.allow_subdomain_redirects = allow_subdomain_redirects

    def run_rsgi_app(self, scope, body):
        if self.cookie_jar is not None:
            self.cookie_jar.inject_rsgi(scope)
        rv = run_rsgi_app(
            self.__class__._current, self.application, scope, body, _handler_cls=self.__class__._handler_cls
        )
        if self.cookie_jar is not None:
            self.cookie_jar.extract_rsgi(scope, Headers(rv["headers"]))
        return rv

    def resolve_redirect(self, response, new_loc, scope, headers):
        scheme, netloc, script_root, qs, _anchor = url_parse(new_loc)
        base_url = url_unparse((scheme, netloc, "", "", "")).rstrip("/") + "/"

        cur_name = netloc.split(":", 1)[0].split(".")
        real_name = get_host(scope, headers).rsplit(":", 1)[0].split(".")

        if len(cur_name) == 1 and not cur_name[0]:
            allowed = True
        else:
            if self.allow_subdomain_redirects:
                allowed = cur_name[-len(real_name) :] == real_name
            else:
                allowed = cur_name == real_name

        if not allowed:
            raise RuntimeError("%r does not support redirect to external targets" % self.__class__)

        status_code = response["status"]
        if status_code == 307:
            method = scope.method
        else:
            method = "GET"

        # For redirect handling we temporarily disable the response
        # wrapper.  This is not threadsafe but not a real concern
        # since the test client must not be shared anyways.
        old_response_wrapper = self.response_wrapper
        self.response_wrapper = None
        try:
            return self.open(path=script_root, base_url=base_url, query_string=qs, method=method, as_tuple=True)
        finally:
            self.response_wrapper = old_response_wrapper

    def open(self, *args, **kwargs):
        as_tuple = kwargs.pop("as_tuple", False)
        follow_redirects = kwargs.pop("follow_redirects", False)
        scope, body = None, b""
        if not kwargs and len(args) == 1:
            if isinstance(args[0], ScopeBuilder):
                scope, body = args[0].get_data()
        if scope is None:
            builder = ScopeBuilder(*args, **kwargs)
            try:
                scope, body = builder.get_data()
            finally:
                builder.close()

        response = self.run_rsgi_app(scope, body)

        # handle redirects
        redirect_chain = []
        while 1:
            status_code = response["status"]
            if status_code not in (301, 302, 303, 305, 307) or not follow_redirects:
                break
            headers = Headers(response["headers"])
            new_location = headers["location"]
            if new_location.startswith("/"):
                new_location = scope.scheme + "://" + scope.server + new_location
            new_redirect_entry = (new_location, status_code)
            if new_redirect_entry in redirect_chain:
                raise Exception("loop detected")
            redirect_chain.append(new_redirect_entry)
            scope, response = self.resolve_redirect(response, new_location, scope, headers)

        if self.response_wrapper is not None:
            response = self.response_wrapper(
                scope._ctx, response["body"], response["status"], Headers(response["headers"])
            )
        if as_tuple:
            return scope, response
        return response

    def get(self, *args, **kw):
        kw["method"] = "GET"
        return self.open(*args, **kw)

    def patch(self, *args, **kw):
        kw["method"] = "PATCH"
        return self.open(*args, **kw)

    def post(self, *args, **kw):
        kw["method"] = "POST"
        return self.open(*args, **kw)

    def head(self, *args, **kw):
        kw["method"] = "HEAD"
        return self.open(*args, **kw)

    def put(self, *args, **kw):
        kw["method"] = "PUT"
        return self.open(*args, **kw)

    def delete(self, *args, **kw):
        kw["method"] = "DELETE"
        return self.open(*args, **kw)

    def options(self, *args, **kw):
        kw["method"] = "OPTIONS"
        return self.open(*args, **kw)

    def trace(self, *args, **kw):
        kw["method"] = "TRACE"
        return self.open(*args, **kw)

    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.application)


class ClientHTTPStreamTransport:
    def __init__(self):
        self._data = BytesIO()

    async def send_bytes(self, data: bytes):
        self._data.write(data)

    async def send_str(self, data: str):
        self._data.write(data.encode("utf8"))


class ClientHTTPProtocol:
    def __init__(self, body):
        self.input = body
        self.response_status = 500
        self.response_headers = []
        self.response_body = b""
        self.response_body_stream = None
        self.consumed_input = False
        self.input_step = 0

    async def __call__(self):
        self.consumed_input = True
        return self.input

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.consumed_input:
            raise StopAsyncIteration
        input_range = (4096 * self.input_step, 4096 * (self.input_step + 1))
        ret = self.input[input_range[0] : input_range[1]]
        if not ret:
            self.consumed_input = True
            raise StopAsyncIteration
        self.input_step += 1
        return ret

    def response_empty(self, status, headers):
        self.response_status = status
        self.response_headers = headers

    def response_str(self, status, headers, body):
        self.response_status = status
        self.response_headers = headers
        self.response_body = body.encode("utf8")

    def response_bytes(self, status, headers, body):
        self.response_status = status
        self.response_headers = headers
        self.response_body = body

    def response_file(self, status, headers, file):
        self.response_status = status
        self.response_headers = headers
        with open(file, "rb") as f:
            self.response_body = f.read()

    def response_stream(self, status, headers):
        self.response_status = status
        self.response_headers = headers
        self.response_body_stream = ClientHTTPStreamTransport()
        return self.response_body_stream


def run_rsgi_app(current, app, scope, body=b"", _handler_cls=ClientHTTPHandler):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    raw = {}
    proto = ClientHTTPProtocol(body)
    handler = _handler_cls(app, current)
    loop.run_until_complete(handler(scope, proto))
    raw["version"] = 11
    raw["status"] = proto.response_status
    raw["headers"] = proto.response_headers
    if proto.response_body_stream:
        proto.response_body_stream._data.seek(0)
        raw["body"] = proto.response_body_stream._data.read()
    else:
        raw["body"] = proto.response_body

    return raw
