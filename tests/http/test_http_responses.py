from io import BytesIO

import pytest

from emmett_core.ctx import Current
from emmett_core.http.helpers import redirect
from emmett_core.http.response import (
    HTTPAsyncIterResponse,
    HTTPBytesResponse,
    HTTPIterResponse,
    HTTPResponse,
    HTTPStringResponse,
)
from emmett_core.http.wrappers.response import Response


@pytest.fixture(scope="function")
def current():
    rv = Current()
    rv.response = Response()
    return rv


@pytest.fixture(scope="function")
def rsgi_proto():
    class Transport:
        def __init__(self, proto):
            self.proto = proto

        async def send_bytes(self, data):
            self.proto.data.write(data)

    class Proto:
        def __init__(self):
            self.code = 0
            self.headers = []
            self.data = BytesIO()

        def response_stream(self, code, headers):
            self.code = code
            self.headers = headers
            return Transport(self)

    return Proto()


def test_http_string_empty():
    http = HTTPStringResponse(200)

    assert http.encoded_body == b""
    assert http.status_code == 200
    assert list(http.headers) == [(b"content-type", b"text/plain")]


def test_http_bytes_empty():
    http = HTTPBytesResponse(200)

    assert http.body == b""
    assert http.status_code == 200
    assert list(http.headers) == [(b"content-type", b"text/plain")]


def test_http_string():
    http = HTTPStringResponse(
        200, "Hello World", headers={"x-test": "Hello Header"}, cookies={"cookie_test": "Set-Cookie: hello cookie"}
    )

    assert http.encoded_body == b"Hello World"
    assert http.status_code == 200
    assert list(http.headers) == [(b"x-test", b"Hello Header"), (b"set-cookie", b"hello cookie")]


@pytest.mark.asyncio
async def test_http_iter(rsgi_proto):
    def iterator():
        yield b"test"

    http = HTTPIterResponse(iterator())
    await http.rsgi(rsgi_proto)
    rsgi_proto.data.seek(0)

    assert rsgi_proto.code == 200
    assert not list(http.headers)
    assert rsgi_proto.data.read() == b"test"


@pytest.mark.asyncio
async def test_http_aiter(rsgi_proto):
    async def iterator():
        yield b"test"

    http = HTTPAsyncIterResponse(iterator())
    await http.rsgi(rsgi_proto)
    rsgi_proto.data.seek(0)

    assert rsgi_proto.code == 200
    assert not list(http.headers)
    assert rsgi_proto.data.read() == b"test"


def test_redirect(current):
    try:
        redirect(current, "/redirect", 302)
    except HTTPResponse as http_redirect:
        assert current.response.status == 302
        assert http_redirect.status_code == 302
        assert list(http_redirect.headers) == [(b"location", b"/redirect")]
