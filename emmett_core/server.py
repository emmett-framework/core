from ._imports import granian


def run(
    interface,
    app,
    host="127.0.0.1",
    port=8000,
    loop="auto",
    task_impl="asyncio",
    log_level=None,
    log_access=False,
    workers=1,
    runtime_threads=1,
    runtime_blocking_threads=None,
    runtime_mode="st",
    backlog=1024,
    backpressure=None,
    http="auto",
    http_read_timeout=10_000,
    enable_websockets=True,
    ssl_certfile=None,
    ssl_keyfile=None,
    reload=False,
    **kwargs,
):
    if granian is None:
        raise RuntimeError("granian dependency not installed")

    http1_settings = granian.http.HTTP1Settings(header_read_timeout=http_read_timeout)
    http2_settings = granian.http.HTTP2Settings(keep_alive_interval=http_read_timeout)

    app_path = ":".join([app[0], app[1] or "app"])
    server = granian.Granian(
        app_path,
        address=host,
        port=port,
        interface=interface,
        workers=workers,
        runtime_threads=runtime_threads,
        runtime_blocking_threads=runtime_blocking_threads,
        runtime_mode=runtime_mode,
        loop=loop,
        task_impl=task_impl,
        http=http,
        websockets=enable_websockets,
        backlog=backlog,
        backpressure=backpressure,
        http1_settings=http1_settings,
        http2_settings=http2_settings,
        log_level=log_level,
        log_access=log_access,
        ssl_cert=ssl_certfile,
        ssl_key=ssl_keyfile,
        reload=reload,
    )
    server.serve()
