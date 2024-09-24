import pytest

from emmett_core.sessions import SessionManager as _SessionManager


@pytest.fixture(scope="function")
def session_manager(current):
    class SessionManager(_SessionManager):
        @classmethod
        def _build_pipe(cls, handler_cls, *args, **kwargs):
            cls._pipe = handler_cls(current, *args, **kwargs)
            return cls._pipe

    return SessionManager.cookies(key="sid", secure=True, domain="localhost", cookie_name="foo_session")


@pytest.mark.asyncio
async def test_session_cookie(http_ctx, session_manager):
    assert session_manager.key == "sid"
    assert session_manager.secure is True
    assert session_manager.domain == "localhost"

    await session_manager.open_request()
    assert http_ctx.session._expiration == 3600

    await session_manager.close_request()
    cookie = str(http_ctx.response.cookies)
    assert "foo_session" in cookie
    assert "Domain=localhost;" in cookie
    assert "secure" in cookie.lower()

    http_ctx.request.cookies = http_ctx.response.cookies
    await session_manager.open_request()
    assert http_ctx.session._expiration == 3600
