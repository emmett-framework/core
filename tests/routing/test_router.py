import datetime

import pytest

from emmett_core.datastructures import sdict


def route(router, path, **kwargs):
    def wrap(f):
        return router(paths=path, **kwargs)(f)

    return wrap


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


@pytest.fixture(scope="function")
def cfg_http_router_scheme(http_router):
    @route(http_router, "/test")
    def test_route():
        return "Test Router"

    @route(http_router, "/test2/<int:a>/<str:b>", schemes="https")
    def test_route2(a, b):
        return "Test Router"

    @route(http_router, "/test3/<int:a>/foo(/<str:b>)?(.<str:c>)?", schemes="http")
    def test_route3(a, b, c):
        return "Test Router"

    return http_router


@pytest.fixture(scope="function")
def cfg_http_router_host(http_router):
    @route(http_router, "/test")
    def test_route():
        return "Test Router"

    @route(http_router, "/test2/<int:a>/<str:b>", hostname="test1.tld")
    def test_route2(a, b):
        return "Test Router"

    return http_router


@pytest.fixture(scope="function")
def cfg_http_router_scheme_host(http_router):
    @route(http_router, "/test")
    def test_route():
        return "Test Router"

    @route(http_router, "/test2/<int:a>/<str:b>", schemes="https")
    def test_route2(a, b):
        return "Test Router"

    @route(http_router, "/test3/<int:a>/foo(/<str:b>)?(.<str:c>)?", hostname="test1.tld")
    def test_route3(a, b, c):
        return "Test Router"

    return http_router


@pytest.fixture(scope="function")
def cfg_ws_router(current, ws_router):
    @route(ws_router, "/test_route")
    def test_route():
        return

    @route(ws_router, "/test2/<int:a>/<str:b>")
    def test_route2(a, b):
        return

    @route(ws_router, "/test3/<int:a>/foo(/<str:b>)?(.<str:c>)?")
    def test_route3(a, b, c):
        return

    @route(ws_router, "/test4/<str:a>/foo(/<int:b>)?(.<str:c>)?")
    def test_route4(a, b, c):
        return

    @route(ws_router, "/test_int/<int:a>")
    def test_route_int(a):
        return

    @route(ws_router, "/test_float/<float:a>")
    def test_route_float(a):
        return

    @route(ws_router, "/test_date/<date:a>")
    def test_route_date(a):
        return

    @route(ws_router, "/test_alpha/<alpha:a>")
    def test_route_alpha(a):
        return

    @route(ws_router, "/test_str/<str:a>")
    def test_route_str(a):
        return

    @route(ws_router, "/test_any/<any:a>")
    def test_route_any(a):
        return

    @route(ws_router, "/test_complex/<int:a>/<float:b>/<date:c>/<alpha:d>/<str:e>/<any:f>")
    def test_route_complex(a, b, c, d, e, f):
        return

    return ws_router


@pytest.fixture(scope="function")
def cfg_ws_router_scheme(ws_router):
    @route(ws_router, "/test")
    def test_route():
        return

    @route(ws_router, "/test2/<int:a>/<str:b>", schemes="https")
    def test_route2(a, b):
        return

    @route(ws_router, "/test3/<int:a>/foo(/<str:b>)?(.<str:c>)?", schemes="http")
    def test_route3(a, b, c):
        return

    return ws_router


@pytest.fixture(scope="function")
def cfg_ws_router_host(ws_router):
    @route(ws_router, "/test")
    def test_route():
        return

    @route(ws_router, "/test2/<int:a>/<str:b>", hostname="test1.tld")
    def test_route2(a, b):
        return

    return ws_router


@pytest.fixture(scope="function")
def cfg_ws_router_scheme_host(ws_router):
    @route(ws_router, "/test")
    def test_route():
        return

    @route(ws_router, "/test2/<int:a>/<str:b>", schemes="https")
    def test_route2(a, b):
        return

    @route(ws_router, "/test3/<int:a>/foo(/<str:b>)?(.<str:c>)?", hostname="test1.tld")
    def test_route3(a, b, c):
        return

    return ws_router


@pytest.fixture(scope="function")
def routing_ctx(
    request,
    http_ctx_builder,
    ws_ctx_builder,
    cfg_http_router,
    cfg_ws_router,
):
    return {
        "http": sdict(router=cfg_http_router, ctx=http_ctx_builder),
        "ws": sdict(router=cfg_ws_router, ctx=ws_ctx_builder),
    }[request.param]


@pytest.fixture(scope="function")
def routing_ctx_host(
    request,
    http_ctx_builder,
    ws_ctx_builder,
    cfg_http_router_host,
    cfg_ws_router_host,
):
    return {
        "http": sdict(router=cfg_http_router_host, ctx=http_ctx_builder),
        "ws": sdict(router=cfg_ws_router_host, ctx=ws_ctx_builder),
    }[request.param]


@pytest.fixture(scope="function")
def routing_ctx_scheme(
    request,
    http_ctx_builder,
    ws_ctx_builder,
    cfg_http_router_scheme,
    cfg_ws_router_scheme,
):
    return {
        "http": sdict(router=cfg_http_router_scheme, ctx=http_ctx_builder),
        "ws": sdict(router=cfg_ws_router_scheme, ctx=ws_ctx_builder),
    }[request.param]


@pytest.fixture(scope="function")
def routing_ctx_scheme_host(
    request,
    http_ctx_builder,
    ws_ctx_builder,
    cfg_http_router_scheme_host,
    cfg_ws_router_scheme_host,
):
    return {
        "http": sdict(router=cfg_http_router_scheme_host, ctx=http_ctx_builder),
        "ws": sdict(router=cfg_ws_router_scheme_host, ctx=ws_ctx_builder),
    }[request.param]


@pytest.mark.parametrize(("routing_ctx"), ["http", "ws"], indirect=True)
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
def test_routing_hit(routing_ctx, path, name):
    with routing_ctx.ctx(path) as ctx:
        route, _ = routing_ctx.router.match(ctx.wrapper)
        assert route.name == f"test_router.{name}"


@pytest.mark.parametrize(("routing_ctx"), ["http", "ws"], indirect=True)
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
def test_routing_miss(routing_ctx, path):
    with routing_ctx.ctx(path) as ctx:
        route, args = routing_ctx.router.match(ctx.wrapper)
        assert not route
        assert not args


@pytest.mark.parametrize(("routing_ctx"), ["http", "ws"], indirect=True)
def test_routing_args(routing_ctx):
    with routing_ctx.ctx("/test_complex/1/1.2/2000-12-01/foo/foo1/bar/baz") as ctx:
        route, args = routing_ctx.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route_complex"
        assert args["a"] == 1
        assert round(args["b"], 1) == 1.2
        assert args["c"] == datetime.date(2000, 12, 1)
        assert args["d"] == "foo"
        assert args["e"] == "foo1"
        assert args["f"] == "bar/baz"


@pytest.mark.parametrize(("routing_ctx_scheme"), ["http", "ws"], indirect=True)
def test_routing_with_scheme(routing_ctx_scheme):
    with routing_ctx_scheme.ctx("/test") as ctx:
        route, _ = routing_ctx_scheme.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route"

    with routing_ctx_scheme.ctx("/test", scheme="https") as ctx:
        route, _ = routing_ctx_scheme.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route"

    with routing_ctx_scheme.ctx("/test2/1/test") as ctx:
        route, _ = routing_ctx_scheme.router.match(ctx.wrapper)
        assert not route

    with routing_ctx_scheme.ctx("/test2/1/test", scheme="https") as ctx:
        route, _ = routing_ctx_scheme.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route2"

    with routing_ctx_scheme.ctx("/test3/1/foo/bar.baz") as ctx:
        route, _ = routing_ctx_scheme.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route3"

    with routing_ctx_scheme.ctx("/test3/1/foo/bar.baz", scheme="https") as ctx:
        route, _ = routing_ctx_scheme.router.match(ctx.wrapper)
        assert not route


@pytest.mark.parametrize(("routing_ctx_host"), ["http", "ws"], indirect=True)
def test_routing_with_host(routing_ctx_host):
    with routing_ctx_host.ctx("/test") as ctx:
        route, _ = routing_ctx_host.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route"

    with routing_ctx_host.ctx("/test", host="test1.tld") as ctx:
        route, _ = routing_ctx_host.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route"

    with routing_ctx_host.ctx("/test", host="test2.tld") as ctx:
        route, _ = routing_ctx_host.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route"

    with routing_ctx_host.ctx("/test2/1/test") as ctx:
        route, _ = routing_ctx_host.router.match(ctx.wrapper)
        assert not route

    with routing_ctx_host.ctx("/test2/1/test", host="test1.tld") as ctx:
        route, _ = routing_ctx_host.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route2"

    with routing_ctx_host.ctx("/test2/1/test", host="test2.tld") as ctx:
        route, _ = routing_ctx_host.router.match(ctx.wrapper)
        assert not route


@pytest.mark.parametrize(("routing_ctx_scheme_host"), ["http", "ws"], indirect=True)
def test_routing_with_scheme_and_host(routing_ctx_scheme_host):
    with routing_ctx_scheme_host.ctx("/test") as ctx:
        route, _ = routing_ctx_scheme_host.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route"

    with routing_ctx_scheme_host.ctx("/test", scheme="https") as ctx:
        route, _ = routing_ctx_scheme_host.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route"

    with routing_ctx_scheme_host.ctx("/test", host="test1.tld") as ctx:
        route, _ = routing_ctx_scheme_host.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route"

    with routing_ctx_scheme_host.ctx("/test", scheme="https", host="test2.tld") as ctx:
        route, _ = routing_ctx_scheme_host.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route"

    with routing_ctx_scheme_host.ctx("/test2/1/test") as ctx:
        route, _ = routing_ctx_scheme_host.router.match(ctx.wrapper)
        assert not route

    with routing_ctx_scheme_host.ctx("/test2/1/test", scheme="https") as ctx:
        route, _ = routing_ctx_scheme_host.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route2"

    with routing_ctx_scheme_host.ctx("/test2/1/test", scheme="https", host="test1.tld") as ctx:
        route, _ = routing_ctx_scheme_host.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route2"

    with routing_ctx_scheme_host.ctx("/test2/1/test", scheme="https", host="test2.tld") as ctx:
        route, _ = routing_ctx_scheme_host.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route2"

    with routing_ctx_scheme_host.ctx("/test3/1/foo/bar.baz") as ctx:
        route, _ = routing_ctx_scheme_host.router.match(ctx.wrapper)
        assert not route

    with routing_ctx_scheme_host.ctx("/test3/1/foo/bar.baz", host="test1.tld") as ctx:
        route, _ = routing_ctx_scheme_host.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route3"

    with routing_ctx_scheme_host.ctx("/test3/1/foo/bar.baz", scheme="https", host="test1.tld") as ctx:
        route, _ = routing_ctx_scheme_host.router.match(ctx.wrapper)
        assert route.name == "test_router.test_route3"

    with routing_ctx_scheme_host.ctx("/test3/1/foo/bar.baz", host="test2.tld") as ctx:
        route, _ = routing_ctx_scheme_host.router.match(ctx.wrapper)
        assert not route
