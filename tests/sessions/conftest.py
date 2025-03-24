import pytest

from emmett_core.app import App as _App
from emmett_core.ctx import Current, RequestContext
from emmett_core.http.wrappers.response import Response as _Response
from emmett_core.protocols.rsgi.test_client.scope import ScopeBuilder
from emmett_core.protocols.rsgi.wrappers import Request
from emmett_core.routing.router import HTTPRouter, WebsocketRouter


class Response(_Response):
    async def stream(self, target, item_wrapper=None):
        raise NotImplementedError


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


@pytest.fixture(scope="function")
def current():
    return Current()


@pytest.fixture(scope="function")
def app(current):
    rv = App(__name__)
    rv._init_with_test_env(current)
    return rv


@pytest.fixture(scope="function")
def http_ctx(current, app):
    scope = ScopeBuilder(path="/").get_data()[0]
    token = current._init_(RequestContext(app, Request(scope, scope.path, None), Response(None)))
    yield current
    current._close_(token)
