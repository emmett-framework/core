from __future__ import annotations

import errno
import mimetypes
import os
import stat
from email.utils import formatdate
from hashlib import md5
from typing import Any, AsyncIterable, BinaryIO, Dict, Generator, Iterable, Tuple

from .._io import loop_open_file


class HTTPResponse(Exception):
    def __init__(
        self,
        status_code: int,
        *,
        headers: Dict[str, str] = {"content-type": "text/plain"},
        cookies: Dict[str, Any] = {},
    ):
        self.status_code: int = status_code
        self._headers: Dict[str, str] = headers
        self._cookies: Dict[str, Any] = cookies

    def asgi_headers(self) -> Generator[Tuple[bytes, bytes], None, None]:
        for key, val in self._headers.items():
            yield key.encode("latin-1"), val.encode("latin-1")
        for cookie in self._cookies.values():
            yield b"set-cookie", str(cookie)[12:].encode("latin-1")

    def rsgi_headers(self) -> Generator[Tuple[str, str], None, None]:
        for key, val in self._headers.items():
            yield key, val
        for cookie in self._cookies.values():
            yield "set-cookie", str(cookie)[12:]

    async def _send_headers(self, send):
        await send({"type": "http.response.start", "status": self.status_code, "headers": list(self.asgi_headers())})

    async def _send_body(self, send):
        await send({"type": "http.response.body"})

    async def asgi(self, scope, send):
        await self._send_headers(send)
        await self._send_body(send)

    def rsgi(self, protocol):
        protocol.response_empty(self.status_code, list(self.rsgi_headers()))


class HTTPBytesResponse(HTTPResponse):
    def __init__(
        self,
        status_code: int,
        body: bytes = b"",
        headers: Dict[str, str] = {"content-type": "text/plain"},
        cookies: Dict[str, Any] = {},
    ):
        super().__init__(status_code, headers=headers, cookies=cookies)
        self.body = body

    async def _send_body(self, send):
        await send({"type": "http.response.body", "body": self.body, "more_body": False})

    def rsgi(self, protocol):
        protocol.response_bytes(self.status_code, list(self.rsgi_headers()), self.body)


class HTTPStringResponse(HTTPResponse):
    def __init__(
        self,
        status_code: int,
        body: str = "",
        headers: Dict[str, str] = {"content-type": "text/plain"},
        cookies: Dict[str, Any] = {},
    ):
        super().__init__(status_code, headers=headers, cookies=cookies)
        self.body = body

    @property
    def encoded_body(self):
        return self.body.encode("utf-8")

    async def _send_body(self, send):
        await send({"type": "http.response.body", "body": self.encoded_body, "more_body": False})

    def rsgi(self, protocol):
        protocol.response_str(self.status_code, list(self.rsgi_headers()), self.body)


class HTTPRedirectResponse(HTTPResponse):
    def __init__(self, status_code: int, location: str, cookies: Dict[str, Any] = {}):
        location = location.replace("\r", "%0D").replace("\n", "%0A")
        super().__init__(status_code, headers={"location": location}, cookies=cookies)


class HTTPFileResponse(HTTPResponse):
    def __init__(
        self,
        file_path: str,
        status_code: int = 200,
        headers: Dict[str, str] = {},
        cookies: Dict[str, Any] = {},
        chunk_size: int = 4096,
    ):
        super().__init__(status_code, headers=headers, cookies=cookies)
        self.file_path = file_path
        self.chunk_size = chunk_size

    def _get_stat_headers(self, stat_data):
        content_type = mimetypes.guess_type(self.file_path)[0] or "text/plain"
        content_length = str(stat_data.st_size)
        last_modified = formatdate(stat_data.st_mtime, usegmt=True)
        etag_base = str(stat_data.st_mtime) + "_" + str(stat_data.st_size)
        etag = md5(etag_base.encode("utf-8")).hexdigest()  # noqa: S324
        return {
            "content-type": content_type,
            "content-length": content_length,
            "last-modified": last_modified,
            "etag": etag,
        }

    async def asgi(self, scope, send):
        try:
            stat_data = os.stat(self.file_path)
            if not stat.S_ISREG(stat_data.st_mode):
                await HTTPResponse(403).send(scope, send)
                return
            self._headers.update(self._get_stat_headers(stat_data))
            await self._send_headers(send)
            if "http.response.pathsend" in scope.get("extensions", {}):
                await send({"type": "http.response.pathsend", "path": str(self.file_path)})
            else:
                await self._send_body(send)
        except IOError as e:
            if e.errno == errno.EACCES:
                await HTTPResponse(403).send(scope, send)
            else:
                await HTTPResponse(404).send(scope, send)

    async def _send_body(self, send):
        async with loop_open_file(self.file_path, mode="rb") as f:
            more_body = True
            while more_body:
                chunk = await f.read(self.chunk_size)
                more_body = len(chunk) == self.chunk_size
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": more_body,
                    }
                )

    def rsgi(self, protocol):
        try:
            stat_data = os.stat(self.file_path)
            if not stat.S_ISREG(stat_data.st_mode):
                return HTTPResponse(403).rsgi(protocol)
            self._headers.update(self._get_stat_headers(stat_data))
        except IOError as e:
            if e.errno == errno.EACCES:
                return HTTPResponse(403).rsgi(protocol)
            return HTTPResponse(404).rsgi(protocol)

        protocol.response_file(self.status_code, list(self.rsgi_headers()), self.file_path)


class HTTPIOResponse(HTTPResponse):
    def __init__(
        self,
        io_stream: BinaryIO,
        status_code: int = 200,
        headers: Dict[str, str] = {},
        cookies: Dict[str, Any] = {},
        chunk_size: int = 4096,
    ):
        super().__init__(status_code, headers=headers, cookies=cookies)
        self.io_stream = io_stream
        self.chunk_size = chunk_size

    def _get_io_headers(self):
        content_length = str(self.io_stream.getbuffer().nbytes)
        return {"content-length": content_length}

    async def asgi(self, scope, send):
        self._headers.update(self._get_io_headers())
        await self._send_headers(send)
        await self._send_body(send)

    async def _send_body(self, send):
        more_body = True
        while more_body:
            chunk = self.io_stream.read(self.chunk_size)
            more_body = len(chunk) == self.chunk_size
            await send(
                {
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": more_body,
                }
            )

    def rsgi(self, protocol):
        protocol.response_bytes(self.status_code, list(self.rsgi_headers()), self.io_stream.read())


class HTTPIterResponse(HTTPResponse):
    def __init__(
        self, iter: Iterable[bytes], status_code: int = 200, headers: Dict[str, str] = {}, cookies: Dict[str, Any] = {}
    ):
        super().__init__(status_code, headers=headers, cookies=cookies)
        self.iter = iter

    async def _send_body(self, send):
        for chunk in self.iter:
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def rsgi(self, protocol):
        trx = protocol.response_stream(self.status_code, list(self.rsgi_headers()))
        for chunk in self.iter:
            await trx.send_bytes(chunk)


class HTTPAsyncIterResponse(HTTPResponse):
    def __init__(
        self,
        iter: AsyncIterable[bytes],
        status_code: int = 200,
        headers: Dict[str, str] = {},
        cookies: Dict[str, Any] = {},
    ):
        super().__init__(status_code, headers=headers, cookies=cookies)
        self.iter = iter

    async def _send_body(self, send):
        async for chunk in self.iter:
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def rsgi(self, protocol):
        trx = protocol.response_stream(self.status_code, list(self.rsgi_headers()))
        async for chunk in self.iter:
            await trx.send_bytes(chunk)
