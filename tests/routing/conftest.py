from contextlib import contextmanager

import pytest

from emmett_core.ctx import Current, RequestContext, WSContext
from emmett_core.datastructures import sdict
from emmett_core.routing.router import HTTPRouter, WebsocketRouter


@pytest.fixture(scope="function")
def app():
    return sdict(
        root_path="",
        languages=["en", "it"],
        language_default="en",
        language_force_on_url=True,
        send_signal=lambda *a, **k: None,
        config=sdict(
            hostname_default=None,
            static_version=None,
            static_version_urls=False,
        ),
    )


@pytest.fixture(scope="function")
def current(app):
    rv = Current()
    rv.app = app
    return rv


@pytest.fixture(scope="function")
def http_router(app, current):
    rv = HTTPRouter(app, current)
    app._router_http = rv
    return rv


@pytest.fixture(scope="function")
def ws_router(app, current):
    rv = WebsocketRouter(app, current)
    app._router_ws = rv
    return rv


@pytest.fixture(scope="function")
def http_ctx_builder(current):
    @contextmanager
    def ctx_builder(path, method="GET", scheme="http", host="localhost"):
        req = sdict(path=path, method=method, scheme=scheme, host=host)
        token = current._init_(RequestContext(current.app, req, sdict()))
        yield sdict(wrapper=current.request)
        current._close_(token)

    return ctx_builder


@pytest.fixture(scope="function")
def ws_ctx_builder(current):
    @contextmanager
    def ctx_builder(path, scheme="http", host="localhost"):
        ws = sdict(path=path, scheme=scheme, host=host)
        token = current._init_(WSContext(current.app, ws))
        yield sdict(wrapper=current.websocket)
        current._close_(token)

    return ctx_builder
