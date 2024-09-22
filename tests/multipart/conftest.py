import pytest

from emmett_core.app import App as _App
from emmett_core.ctx import Current
from emmett_core.protocols.rsgi.test_client.client import EmmettTestClient
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


@pytest.fixture(scope="function")
def current():
    return Current()


@pytest.fixture(scope="function")
def app(current):
    class TestClient(EmmettTestClient):
        _current = current

    App.test_client_class = TestClient
    rv = App(__name__)
    rv._init_with_test_env(current)
    return rv


@pytest.fixture(scope="function")
def client(app):
    return app.test_client()
