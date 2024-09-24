import pytest

from emmett_core.ctx import Current
from emmett_core.http.helpers import redirect
from emmett_core.http.response import HTTPBytesResponse, HTTPResponse, HTTPStringResponse
from emmett_core.http.wrappers.response import Response


@pytest.fixture(scope="function")
def current():
    rv = Current()
    rv.response = Response()
    return rv


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


def test_redirect(current):
    try:
        redirect(current, "/redirect", 302)
    except HTTPResponse as http_redirect:
        assert current.response.status == 302
        assert http_redirect.status_code == 302
        assert list(http_redirect.headers) == [(b"location", b"/redirect")]
