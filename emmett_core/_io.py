import asyncio
from functools import partial
from shutil import copyfileobj


class LoopFileWrapper:
    __slots__ = ("_file", "_loop")

    def __init__(self, f, loop=None):
        self._file = f
        self._loop = loop or asyncio.get_running_loop()

    async def read(self, *args, **kwargs):
        return await self._loop.run_in_executor(None, partial(self._file.read, *args, **kwargs))

    async def write(self, *args, **kwargs):
        return await self._loop.run_in_executor(None, partial(self._file.write, *args, **kwargs))

    async def close(self, *args, **kwargs):
        return await self._loop.run_in_executor(None, partial(self._file.close, *args, **kwargs))

    def __getattr__(self, name):
        return getattr(self._file, name)


class LoopFileCtxWrapper:
    __slots__ = ("_coro", "_obj")

    def __init__(self, coro):
        self._coro = coro
        self._obj = None

    def __await__(self):
        return self._coro.__await__()

    async def __aenter__(self):
        self._obj = await self._coro
        return self._obj

    async def __aexit__(self, exc_type, exc, tb):
        await self._obj.close()
        self._obj = None


async def _loop_open_file(loop, *args, **kwargs):
    f = await loop.run_in_executor(None, partial(open, *args, **kwargs))
    return LoopFileWrapper(f, loop)


def loop_open_file(*args, **kwargs):
    return LoopFileCtxWrapper(_loop_open_file(asyncio.get_running_loop(), *args, **kwargs))


async def loop_copyfileobj(fsrc, fdst, length=None):
    return await asyncio.get_running_loop().run_in_executor(None, partial(copyfileobj, fsrc, fdst, length))
