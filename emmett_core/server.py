from ._imports import granian


def run(
    interface,
    app,
    host="127.0.0.1",
    port=8000,
    loop="auto",
    loop_opt=False,
    log_level=None,
    log_access=False,
    workers=1,
    threads=1,
    threading_mode="workers",
    backlog=1024,
    backpressure=None,
    http="auto",
    enable_websockets=True,
    ssl_certfile=None,
    ssl_keyfile=None,
    reload=False,
):
    if granian is None:
        raise RuntimeError("granian dependency not installed")

    app_path = ":".join([app[0], app[1] or "app"])
    server = granian.Granian(
        app_path,
        address=host,
        port=port,
        interface=interface,
        workers=workers,
        threads=threads,
        threading_mode=threading_mode,
        loop=loop,
        loop_opt=loop_opt,
        http=http,
        websockets=enable_websockets,
        backlog=backlog,
        backpressure=backpressure,
        log_level=log_level,
        log_access=log_access,
        ssl_cert=ssl_certfile,
        ssl_key=ssl_keyfile,
        reload=reload,
    )
    server.serve()
