from contextlib import contextmanager

import pytest

from emmett_core.app import App as _App
from emmett_core.ctx import Current, RequestContext, WSContext
from emmett_core.datastructures import sdict
from emmett_core.protocols.rsgi.test_client.scope import ScopeBuilder
from emmett_core.protocols.rsgi.wrappers import Request, Websocket
from emmett_core.routing.router import HTTPRouter, WebsocketRouter


class App(_App):
    def _init_routers(self, url_prefix):
        pass

    def _init_handlers(self):
        pass

    def _register_with_ctx(self):
        pass

    def _init_with_test_env(self, current):
        self._router_http = HTTPRouter(self, current)
        self._router_ws = WebsocketRouter(self, current)
        current.app = self


class FakeWSTransport(sdict):
    async def send_str(self, data):
        self.current._send_storage.append(data)

    async def send_bytes(self, data):
        self.current._send_storage.append(data.decode("utf8"))


class FakeWSProtocol(sdict):
    async def accept(self):
        pass

    async def init(self):
        self.transport = FakeWSTransport(current=self.current)
        return self.transport

    async def receive(self):
        return sdict(data="{}")


@pytest.fixture(scope="function")
def current():
    return Current()


@pytest.fixture(scope="function")
def app(current):
    rv = App(__name__)
    rv._init_with_test_env(current)
    return rv


@pytest.fixture(scope="function")
def http_ctx_builder(current):
    @contextmanager
    def ctx_builder(path):
        scope = ScopeBuilder(path=path).get_data()[0]
        token = current._init_(
            RequestContext(current.app, Request(scope, scope.path, None), sdict(_bind_flow=lambda v: None))
        )
        yield sdict(ctx=current, wrapper=current.request)
        current._close_(token)

    return ctx_builder


@pytest.fixture(scope="function")
def ws_ctx_builder(current):
    @contextmanager
    def ctx_builder(path):
        scope = ScopeBuilder(path=path).get_data()[0]
        scope.proto = "ws"
        token = current._init_(WSContext(current.app, Websocket(scope, scope.path, FakeWSProtocol(current=current))))
        yield sdict(ctx=current, wrapper=current.websocket)
        current._close_(token)

    return ctx_builder
