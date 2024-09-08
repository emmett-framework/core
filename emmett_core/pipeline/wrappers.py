from functools import wraps

from ..http.response import HTTPResponse


def _wrap_flow_request_complete(pipe_method, on_success, on_failure, f):
    @wraps(f)
    async def flow(**kwargs):
        try:
            output = await pipe_method(f, **kwargs)
            await on_success()
            return output
        except HTTPResponse:
            await on_success()
            raise
        except Exception:
            await on_failure()
            raise

    return flow


def _wrap_flow_request_success(pipe_method, on_success, on_failure, f):
    @wraps(f)
    async def flow(**kwargs):
        try:
            output = await pipe_method(f, **kwargs)
            await on_success()
            return output
        except HTTPResponse:
            await on_success()
            raise

    return flow


def _wrap_flow_request_failure(pipe_method, on_success, on_failure, f):
    @wraps(f)
    async def flow(**kwargs):
        try:
            return await pipe_method(f, **kwargs)
        except HTTPResponse:
            raise
        except Exception:
            await on_failure()
            raise

    return flow


def _wrap_flow_request_basic(pipe_method, on_success, on_failure, f):
    @wraps(f)
    async def flow(**kwargs):
        return await pipe_method(f, **kwargs)

    return flow


def _wrap_flow_ws_complete(pipe_method, on_success, on_failure, f):
    @wraps(f)
    async def flow(**kwargs):
        try:
            await pipe_method(f, **kwargs)
            await on_success()
        except Exception:
            await on_failure()
            raise

    return flow


def _wrap_flow_ws_success(pipe_method, on_success, on_failure, f):
    @wraps(f)
    async def flow(**kwargs):
        await pipe_method(f, **kwargs)
        await on_success()

    return flow


def _wrap_flow_ws_failure(pipe_method, on_success, on_failure, f):
    @wraps(f)
    async def flow(**kwargs):
        try:
            await pipe_method(f, **kwargs)
        except Exception:
            await on_failure()
            raise

    return flow


def _wrap_flow_ws_basic(pipe_method, on_success, on_failure, f):
    @wraps(f)
    async def flow(**kwargs):
        return await pipe_method(f, **kwargs)

    return flow
