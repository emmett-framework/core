from __future__ import annotations

import re
from collections import namedtuple
from functools import partial
from typing import Any, Callable, List, Type

from .._emmett_core import HTTPRouter as _HTTPRouter, WSRouter as _WSRouter
from ..extensions import Signals
from ..http.response import HTTPBytesResponse
from .response import (
    AsyncIterResponseBuilder,
    AutoResponseBuilder,
    BytesResponseBuilder,
    EmptyResponseBuilder,
    IterResponseBuilder,
    MetaResponseBuilder,
    StringResponseBuilder,
)
from .rules import HTTPRoutingRule, RoutingRule, WebsocketRoutingRule


RouteRecReq = namedtuple("RouteRecReq", ["name", "dispatch", "flow_stream"])
RouteRecWS = namedtuple("RouteRecWS", ["name", "dispatch", "flow_recv", "flow_send"])


class RouterMixin:
    _routing_signal = Signals.before_routes
    _routing_started = False
    _routing_stack: List[RoutingRule] = []
    _re_components = re.compile(r"(\()?([^<\w]+)?<(\w+)\:(\w+)>(\)\?)?")

    @classmethod
    def _init_router_(cls, router, app, current, url_prefix=None):
        router.app = app
        router.current = current
        router.static_versioning = partial(cls.static_versioning, router)
        router.routes = []
        router.routes_out = {}
        router._routes_str = {}
        router._impl_host_match = False
        router._impl_scheme_match = False
        main_prefix = url_prefix or ""
        if main_prefix:
            main_prefix = main_prefix.rstrip("/")
            if not main_prefix.startswith("/"):
                main_prefix = "/" + main_prefix
            if main_prefix == "/":
                main_prefix = ""
        router._prefix_main = main_prefix
        router._prefix_main_len = len(router._prefix_main)
        router.__call__ = cls.__rcall__(router)
        cls._update_match_impl(router)
        cls._set_language_impl(router)

    @staticmethod
    def _update_match_impl(router):
        if router._impl_host_match and router._impl_scheme_match:
            router.match = router._match_w_host_and_scheme
        elif router._impl_host_match:
            router.match = router._match_w_host
        elif router._impl_scheme_match:
            router.match = router._match_w_scheme
        else:
            router.match = router._match

    @classmethod
    def _set_language_impl(cls, router):
        router.match_lang = partial(
            cls._match_w_lang if router.app.language_force_on_url else cls._match_n_lang, router
        )

    @staticmethod
    def static_versioning(router):
        return (router.app.config.static_version_urls and router.app.config.static_version) or ""

    @classmethod
    def build_route_components(cls, path):
        components = []
        params = []
        for match in cls._re_components.findall(path):
            params.append(match[1] + "{}")
        statics = cls._re_components.sub("{}", path).split("{}")
        if not params:
            components = statics
        else:
            components.append(statics[0])
            for idx, _ in enumerate(params):
                components.append(params[idx] + statics[idx + 1])
        return components

    @staticmethod
    def _match_w_lang(router, wrapper, path):
        path, lang = RouterMixin._split_lang(router, path)
        router.current.language = wrapper.language = lang
        return path

    @staticmethod
    def _match_n_lang(router, wrapper, path):
        wrapper.language = None
        return path

    @staticmethod
    def _split_lang(router, path):
        default = router.app.language_default
        if len(path) <= 1:
            return path, default
        clean_path = path.lstrip("/")
        if clean_path[2:3] == "/":
            lang, new_path = clean_path[:2], clean_path[2:]
            if lang != default and lang in router.app._languages_set:
                return new_path, lang
        return path, default

    @classmethod
    def __rcall__(cls, router):
        def inner(*args, **kwargs):
            if not cls._routing_started:
                cls._routing_started = True
                router.app.send_signal(cls._routing_signal)
            return RoutingCtx(router, router._routing_rule_cls, *args, **kwargs)

        return inner

    @classmethod
    def exposing(cls):
        return cls._routing_stack[-1]


class HTTPRouter(_HTTPRouter):
    __slots__ = [
        "__call__",
        "match",
        "match_lang",
        "_impl_host_match",
        "_impl_scheme_match",
        "_prefix_main_len",
        "_prefix_main",
        "_routes_str",
        "app",
        "current",
        "static_versioning",
        "routes_out",
        "routes",
        "pipeline",
    ]

    _mixin_cls = RouterMixin
    _routing_rule_cls = HTTPRoutingRule
    _routing_rec_builder = RouteRecReq

    _outputs = {
        "empty": EmptyResponseBuilder,
        "auto": AutoResponseBuilder,
        "bytes": BytesResponseBuilder,
        "str": StringResponseBuilder,
        "iter": IterResponseBuilder,
        "aiter": AsyncIterResponseBuilder,
        "http": MetaResponseBuilder,
    }

    def __init__(self, *args, **kwargs):
        self._mixin_cls._init_router_(self, *args, **kwargs)
        self.pipeline = []

    def add_route_str(self, route):
        self._routes_str[route.name] = "%s %s://%s%s%s -> %s" % (
            "|".join(route.methods),
            "|".join(route.schemes),
            route.hostname or "<any>",
            self._prefix_main,
            route.path,
            route.name,
        )

    def add_route(self, route):
        if route.hostname:
            self._impl_host_match = True
        if len(route.schemes) % 2:
            self._impl_scheme_match = True
            _scheme = "secure" if route.schemes[0] == "https" else "plain"
        else:
            _scheme = None
        self._mixin_cls._update_match_impl(self)
        for method in route.methods:
            if route.is_static:
                self.add_static_route(
                    self._routing_rec_builder(
                        name=route.name,
                        dispatch=route.dispatchers[method].dispatch,
                        flow_stream=route.pipeline_flow_stream,
                    ),
                    route.path,
                    method,
                    route.hostname,
                    _scheme,
                )
            else:
                self.add_re_route(
                    self._routing_rec_builder(
                        name=route.name,
                        dispatch=route.dispatchers[method].dispatch,
                        flow_stream=route.pipeline_flow_stream,
                    ),
                    route.build_regex(route.path),
                    route._argtypes,
                    method,
                    route.hostname,
                    _scheme,
                )
        self.routes_out[route.name] = {
            "host": route.hostname,
            "path": self._mixin_cls.build_route_components(route.path),
        }
        self.add_route_str(route)

    def _match(self, request):
        path = self.match_lang(request, request.path.rstrip("/") or request.path)
        return self.match_route_direct(request.method, path)

    def _match_w_scheme(self, request):
        path = self.match_lang(request, request.path.rstrip("/") or request.path)
        return self.match_route_scheme(request.scheme, request.method, path)

    def _match_w_host(self, request):
        path = self.match_lang(request, request.path.rstrip("/") or request.path)
        return self.match_route_host(request.host, request.method, path)

    def _match_w_host_and_scheme(self, request):
        path = self.match_lang(request, request.path.rstrip("/") or request.path)
        return self.match_route_all(request.host, request.scheme, request.method, path)

    async def dispatch(self, request, response):
        match, reqargs = self.match(request)
        if not match:
            raise HTTPBytesResponse(404, body=b"Resource not found")
        request.name = match.name
        response._bind_flow(match.flow_stream)
        return await match.dispatch(reqargs, response)


class WebsocketRouter(_WSRouter):
    __slots__ = [
        "__call__",
        "match",
        "match_lang",
        "_impl_host_match",
        "_impl_scheme_match",
        "_prefix_main_len",
        "_prefix_main",
        "_routes_str",
        "app",
        "current",
        "static_versioning",
        "routes_out",
        "routes",
        "pipeline",
    ]

    _mixin_cls = RouterMixin
    _routing_rule_cls = WebsocketRoutingRule
    _routing_rec_builder = RouteRecWS

    def __init__(self, *args, **kwargs):
        self._mixin_cls._init_router_(self, *args, **kwargs)
        self.pipeline = []

    def add_route_str(self, route):
        self._routes_str[route.name] = "%s://%s%s%s -> %s" % (
            "|".join([{"http": "ws", "https": "ws"}[scheme] for scheme in route.schemes]),
            route.hostname or "<any>",
            self._prefix_main,
            route.path,
            route.name,
        )

    def add_route(self, route):
        if route.hostname:
            self._impl_host_match = True
        if len(route.schemes) % 2:
            self._impl_scheme_match = True
            _scheme = "secure" if route.schemes[0] == "https" else "plain"
        else:
            _scheme = None
        self._mixin_cls._update_match_impl(self)
        if route.is_static:
            self.add_static_route(
                self._routing_rec_builder(
                    name=route.name,
                    dispatch=route.dispatcher.dispatch,
                    flow_recv=route.pipeline_flow_receive,
                    flow_send=route.pipeline_flow_send,
                ),
                route.path,
                route.hostname,
                _scheme,
            )
        else:
            self.add_re_route(
                self._routing_rec_builder(
                    name=route.name,
                    dispatch=route.dispatcher.dispatch,
                    flow_recv=route.pipeline_flow_receive,
                    flow_send=route.pipeline_flow_send,
                ),
                route.build_regex(route.path),
                route._argtypes,
                route.hostname,
                _scheme,
            )
        self.routes_out[route.name] = {
            "host": route.hostname,
            "path": self._mixin_cls.build_route_components(route.path),
        }
        self.add_route_str(route)

    def _match(self, websocket):
        path = self.match_lang(websocket, websocket.path.rstrip("/") or websocket.path)
        return self.match_route_direct(path)

    def _match_w_scheme(self, websocket):
        path = self.match_lang(websocket, websocket.path.rstrip("/") or websocket.path)
        return self.match_route_scheme(websocket.scheme, path)

    def _match_w_host(self, websocket):
        path = self.match_lang(websocket, websocket.path.rstrip("/") or websocket.path)
        return self.match_route_host(websocket.host, path)

    def _match_w_host_and_scheme(self, websocket):
        path = self.match_lang(websocket, websocket.path.rstrip("/") or websocket.path)
        return self.match_route_all(websocket.host, websocket.scheme, path)

    async def dispatch(self, websocket):
        match, reqargs = self.match(websocket)
        if not match:
            raise HTTPBytesResponse(404, body=b"Resource not found")
        websocket.name = match.name
        websocket._bind_flow(match.flow_recv, match.flow_send)
        await match.dispatch(reqargs)


class RoutingCtx:
    __slots__ = ["router", "rule"]

    def __init__(self, router, rule_cls: Type[RoutingRule], *args, **kwargs):
        self.router = router
        self.rule = rule_cls(self.router, *args, **kwargs)
        self.router._mixin_cls._routing_stack.append(self.rule)

    def __call__(self, f: Callable[..., Any]) -> Callable[..., Any]:
        self.router.app.send_signal(Signals.before_route, route=self.rule, f=f)
        rv = self.rule(f)
        self.router.app.send_signal(Signals.after_route, route=self.rule)
        self.router._mixin_cls._routing_stack.pop()
        return rv


class RoutingCtxGroup:
    __slots__ = ["ctxs"]

    def __init__(self, ctxs: List[RoutingCtx]):
        self.ctxs = ctxs

    def __call__(self, f: Callable[..., Any]) -> Callable[..., Any]:
        rv = f
        for ctx in self.ctxs:
            rv = ctx(f)
        return rv
