import datetime
from contextlib import contextmanager

import pytest

from emmett_core.ctx import Current, RequestContext
from emmett_core.datastructures import sdict
from emmett_core.routing.router import HTTPRouter


def route(router, path, **kwargs):
    def wrap(f):
        return router(paths=[path], **kwargs)(f)

    return wrap


@pytest.fixture(scope="module")
def current(app):
    rv = Current()
    rv.app = app
    return rv


@pytest.fixture(scope="function")
def http_router(app, current):
    return HTTPRouter(app, current)


@pytest.fixture(scope="function")
def http_ctx_builder(current):
    @contextmanager
    def ctx_builder(path, method="GET", scheme="http", host="localhost"):
        req = sdict(path=path, method=method, scheme=scheme, host=host)
        token = current._init_(RequestContext(current.app, req, sdict()))
        yield current
        current._close_(token)

    return ctx_builder


@pytest.fixture(scope="function")
def cfg_http_router(current, http_router):
    @route(http_router, "/test_route")
    def test_route():
        return "Test Router"

    @route(http_router, "/test_404")
    def test_404():
        current.response.status = 404
        return "Not found, dude"

    @route(http_router, "/test2/<int:a>/<str:b>")
    def test_route2(a, b):
        return "Test Router"

    @route(http_router, "/test3/<int:a>/foo(/<str:b>)?(.<str:c>)?")
    def test_route3(a, b, c):
        return "Test Router"

    @route(http_router, "/test4/<str:a>/foo(/<int:b>)?(.<str:c>)?")
    def test_route4(a, b, c):
        return "Test Router"

    @route(http_router, "/test_int/<int:a>")
    def test_route_int(a):
        return "Test Router"

    @route(http_router, "/test_float/<float:a>")
    def test_route_float(a):
        return "Test Router"

    @route(http_router, "/test_date/<date:a>")
    def test_route_date(a):
        return "Test Router"

    @route(http_router, "/test_alpha/<alpha:a>")
    def test_route_alpha(a):
        return "Test Router"

    @route(http_router, "/test_str/<str:a>")
    def test_route_str(a):
        return "Test Router"

    @route(http_router, "/test_any/<any:a>")
    def test_route_any(a):
        return "Test Router"

    @route(http_router, "/test_complex/<int:a>/<float:b>/<date:c>/<alpha:d>/<str:e>/<any:f>")
    def test_route_complex(a, b, c, d, e, f):
        return "Test Router"

    return http_router


@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("/test_route", "test_route"),
        ("/test2/1/test", "test_route2"),
        ("/test3/1/foo", "test_route3"),
        ("/test3/1/foo/bar", "test_route3"),
        ("/test3/1/foo.baz", "test_route3"),
        ("/test3/1/foo/bar.baz", "test_route3"),
        ("/test_int/1", "test_route_int"),
        ("/test_float/1.1", "test_route_float"),
        ("/test_date/2000-01-01", "test_route_date"),
        ("/test_alpha/a", "test_route_alpha"),
        ("/test_str/a1-", "test_route_str"),
        ("/test_any/a/b", "test_route_any"),
    ],
)
def test_http_routing_hit(cfg_http_router, http_ctx_builder, path, name):
    with http_ctx_builder(path) as ctx:
        route, _ = cfg_http_router.match(ctx.request)
        assert route.name == f"test_router.{name}"


@pytest.mark.parametrize(
    "path",
    [
        "/missing",
        "/test_int",
        "/test_int/a",
        "/test_int/1.1",
        "/test_int/2000-01-01",
        "/test_float",
        "/test_float/a.a",
        "/test_float/1",
        "/test_date",
        "/test_alpha",
        "/test_alpha/a1",
        "/test_alpha/a-a",
        "/test_str",
        "/test_str/a/b",
        "/test_any",
    ],
)
def test_http_routing_miss(cfg_http_router, http_ctx_builder, path):
    with http_ctx_builder(path) as ctx:
        route, args = cfg_http_router.match(ctx.request)
        assert not route
        assert not args


def test_http_routing_args(cfg_http_router, http_ctx_builder):
    with http_ctx_builder("/test_complex/1/1.2/2000-12-01/foo/foo1/bar/baz") as ctx:
        route, args = cfg_http_router.match(ctx.request)
        assert route.name == "test_router.test_route_complex"
        assert args["a"] == 1
        assert round(args["b"], 1) == 1.2
        assert args["c"] == datetime.date(2000, 12, 1)
        assert args["d"] == "foo"
        assert args["e"] == "foo1"
        assert args["f"] == "bar/baz"


def test_http_routing_with_scheme(): ...


def test_http_routing_with_host(): ...


def test_http_routing_with_scheme_and_host(): ...
