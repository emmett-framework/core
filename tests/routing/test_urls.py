import pytest

from emmett_core.routing.router import HTTPRouter
from emmett_core.routing.urls import Url


def route(router, path, **kwargs):
    def wrap(f):
        return router(paths=path, **kwargs)(f)

    return wrap


def cfg_router(router):
    @route(router, "/test_complex/<int:a>/<float:b>/<date:c>/<alpha:d>/<str:e>/<any:f>")
    def test_route_complex(a, b, c, d, e, f):
        return

    @route(router, "/test_optionals/<int:a>/foo(/<str:b>)?(.<str:c>)?")
    def test_route_optionals(a, b, c):
        return

    return router


@pytest.fixture(scope="function")
def url(current):
    return Url(current)


@pytest.fixture(scope="function")
def app_static_version(app):
    app.config.static_version_urls = True
    app.config.static_version = "1.0.0"
    return app


@pytest.fixture(scope="function")
def http_router_prefix(app, current):
    rv = HTTPRouter(app, current, url_prefix="/test_prefix")
    app._router_http = rv
    return rv


@pytest.fixture(scope="function")
def router(request, http_router, ws_router):
    return {"http": cfg_router(http_router), "ws": cfg_router(ws_router)}[request.param]


def test_static(url, http_router):
    link = url("static", "file")
    assert link == "/static/file"


def test_static_version(url, app_static_version, http_router):
    link = url("static", "js/foo.js", language="it")
    assert link == "/it/static/_1.0.0/js/foo.js"


def test_prefix(url, http_router_prefix):
    link = url("static", "js/foo.js", language="it")
    assert link == "/test_prefix/it/static/js/foo.js"


@pytest.mark.parametrize(("router"), ["http"], indirect=True)
@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (
            ("test_urls.test_route_complex", [1, 1.2, "2000-12-01", "foo", "foo1", "bar", "baz"], {}, {}),
            "/test_complex/1/1.2/2000-12-01/foo/foo1/bar/baz",
        ),
        (
            ("test_urls.test_route_complex", [1, 1.2, "2000-12-01", "foo", "foo1", "bar", "baz"], {"foo": "bar"}, {}),
            "/test_complex/1/1.2/2000-12-01/foo/foo1/bar/baz?foo=bar",
        ),
        (
            ("test_urls.test_route_optionals", [1], {}, {}),
            "/test_optionals/1/foo",
        ),
        (
            ("test_urls.test_route_optionals", [1, "bar"], {}, {}),
            "/test_optionals/1/foo/bar",
        ),
        (
            ("test_urls.test_route_optionals", [1, "bar", "baz"], {}, {}),
            "/test_optionals/1/foo/bar.baz",
        ),
        (
            ("test_urls.test_route_optionals", [1, "bar"], {"foo": "bar"}, {}),
            "/test_optionals/1/foo/bar?foo=bar",
        ),
        (
            ("test_urls.test_route_optionals", [1], {}, {"scheme": True}),
            "http://localhost/test_optionals/1/foo",
        ),
        (
            ("test_urls.test_route_optionals", [1], {}, {"scheme": True, "host": "test1.tld"}),
            "http://test1.tld/test_optionals/1/foo",
        ),
        (
            ("test_urls.test_route_optionals", [1], {}, {"scheme": "https"}),
            "https://localhost/test_optionals/1/foo",
        ),
    ],
)
def test_req(http_ctx_builder, url, router, parts, expected):
    route_name, args, params, extras = parts
    with http_ctx_builder("/test"):
        assert url(route_name, args, params, **extras) == expected


@pytest.mark.parametrize(("router"), ["ws"], indirect=True)
@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (
            ("test_urls.test_route_complex", [1, 1.2, "2000-12-01", "foo", "foo1", "bar", "baz"], {}, {}),
            "/test_complex/1/1.2/2000-12-01/foo/foo1/bar/baz",
        ),
        (
            ("test_urls.test_route_complex", [1, 1.2, "2000-12-01", "foo", "foo1", "bar", "baz"], {"foo": "bar"}, {}),
            "/test_complex/1/1.2/2000-12-01/foo/foo1/bar/baz?foo=bar",
        ),
        (
            ("test_urls.test_route_optionals", [1], {}, {}),
            "/test_optionals/1/foo",
        ),
        (
            ("test_urls.test_route_optionals", [1, "bar"], {}, {}),
            "/test_optionals/1/foo/bar",
        ),
        (
            ("test_urls.test_route_optionals", [1, "bar", "baz"], {}, {}),
            "/test_optionals/1/foo/bar.baz",
        ),
        (
            ("test_urls.test_route_optionals", [1, "bar"], {"foo": "bar"}, {}),
            "/test_optionals/1/foo/bar?foo=bar",
        ),
        (
            ("test_urls.test_route_optionals", [1], {}, {"scheme": True}),
            "ws://localhost/test_optionals/1/foo",
        ),
        (
            ("test_urls.test_route_optionals", [1], {}, {"scheme": True, "host": "test1.tld"}),
            "ws://test1.tld/test_optionals/1/foo",
        ),
        (
            ("test_urls.test_route_optionals", [1], {}, {"scheme": "https"}),
            "wss://localhost/test_optionals/1/foo",
        ),
        (
            ("test_urls.test_route_optionals", [1], {}, {"scheme": "wss"}),
            "wss://localhost/test_optionals/1/foo",
        ),
    ],
)
def test_ws(http_ctx_builder, url, router, parts, expected):
    route_name, args, params, extras = parts

    with http_ctx_builder("/test"):
        assert url.ws(route_name, args, params, **extras) == expected
