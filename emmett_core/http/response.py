from __future__ import annotations

import errno
import mimetypes
import os
import stat
from collections.abc import AsyncIterable, Generator, Iterable
from email.utils import formatdate
from hashlib import md5
from typing import Any, BinaryIO

from .._io import loop_open_file


class _RangeNotSatisfiable(Exception):
    def __init__(self, max_size: int):
        self.max_size = max_size


class HTTPResponse(Exception):
    def __init__(
        self,
        status_code: int,
        *,
        headers: dict[str, str] = {"content-type": "text/plain"},
        cookies: dict[str, Any] = {},
    ):
        self.status_code: int = status_code
        self._headers: dict[str, str] = headers
        self._cookies: dict[str, Any] = cookies

    def asgi_headers(self) -> Generator[tuple[bytes, bytes], None, None]:
        for key, val in self._headers.items():
            yield key.encode("latin-1"), val.encode("latin-1")
        for cookie in self._cookies.values():
            yield b"set-cookie", str(cookie)[12:].encode("latin-1")

    def rsgi_headers(self) -> Generator[tuple[str, str], None, None]:
        yield from self._headers.items()
        for cookie in self._cookies.values():
            yield "set-cookie", str(cookie)[12:]

    async def _send_headers(self, send):
        await send({"type": "http.response.start", "status": self.status_code, "headers": list(self.asgi_headers())})

    async def _send_body(self, send):
        await send({"type": "http.response.body"})

    async def asgi(self, scope, send):
        await self._send_headers(send)
        await self._send_body(send)

    def rsgi(self, scope, protocol):
        protocol.response_empty(self.status_code, list(self.rsgi_headers()))


class HTTPBytesResponse(HTTPResponse):
    def __init__(
        self,
        status_code: int,
        body: bytes = b"",
        headers: dict[str, str] = {"content-type": "text/plain"},
        cookies: dict[str, Any] = {},
    ):
        super().__init__(status_code, headers=headers, cookies=cookies)
        self.body = body

    async def _send_body(self, send):
        await send({"type": "http.response.body", "body": self.body, "more_body": False})

    def rsgi(self, scope, protocol):
        protocol.response_bytes(self.status_code, list(self.rsgi_headers()), self.body)


class HTTPStringResponse(HTTPResponse):
    def __init__(
        self,
        status_code: int,
        body: str = "",
        headers: dict[str, str] = {"content-type": "text/plain"},
        cookies: dict[str, Any] = {},
    ):
        super().__init__(status_code, headers=headers, cookies=cookies)
        self.body = body

    @property
    def encoded_body(self):
        return self.body.encode("utf-8")

    async def _send_body(self, send):
        await send({"type": "http.response.body", "body": self.encoded_body, "more_body": False})

    def rsgi(self, scope, protocol):
        protocol.response_str(self.status_code, list(self.rsgi_headers()), self.body)


class HTTPRedirectResponse(HTTPResponse):
    def __init__(self, status_code: int, location: str, cookies: dict[str, Any] = {}):
        location = location.replace("\r", "%0D").replace("\n", "%0A")
        super().__init__(status_code, headers={"location": location}, cookies=cookies)


class HTTPFileResponse(HTTPResponse):
    def __init__(
        self,
        file_path: str,
        status_code: int = 200,
        headers: dict[str, str] = {},
        cookies: dict[str, Any] = {},
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

    def _if_range_feasible(self, http_if_range: str) -> bool:
        return http_if_range == self._headers["last-modified"] or http_if_range == self._headers["etag"]

    @classmethod
    def _parse_range_header(cls, http_range: str, file_size: int) -> list[tuple[int, int]]:
        units, hrange_val = http_range.split("=", 1)
        units = units.strip().lower()
        if units != "bytes":
            raise ValueError

        ranges = cls._parse_ranges(hrange_val, file_size)
        if len(ranges) == 0:
            raise ValueError("Range header: range must be requested")
        if any(not (0 <= start < file_size) for start, _ in ranges):
            raise _RangeNotSatisfiable(file_size)
        if any(start > end for start, end in ranges):
            raise ValueError("Range header: start must be less than end")

        if len(ranges) == 1:
            return ranges

        #: sort and merge overlapping ranges
        ranges.sort()
        res = [ranges[0]]
        for start, end in ranges[1:]:
            last_start, last_end = res[-1]
            if start <= last_end:
                res[-1] = (last_start, max(last_end, end))
            else:
                res.append((start, end))
        return ranges

    @classmethod
    def _parse_ranges(cls, hrange: str, file_size: int) -> list[tuple[int, int]]:
        ret = []
        for part in hrange.split(","):
            part = part.strip()
            if not part or part == "-":
                continue
            if "-" not in part:
                continue

            start_str, end_str = part.split("-", 1)
            start_str = start_str.strip()
            end_str = end_str.strip()
            try:
                start = int(start_str) if start_str else file_size - int(end_str)
                end = int(end_str) + 1 if start_str and end_str and int(end_str) < file_size else file_size
                ret.append((start, end))
            except ValueError:
                continue

        return ret

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
        except OSError as e:
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

    def rsgi(self, scope, protocol):
        try:
            stat_data = os.stat(self.file_path)
            if not stat.S_ISREG(stat_data.st_mode):
                return HTTPResponse(403).rsgi(scope, protocol)
            self._headers.update(self._get_stat_headers(stat_data))
        except OSError as e:
            if e.errno == errno.EACCES:
                return HTTPResponse(403).rsgi(scope, protocol)
            return HTTPResponse(404).rsgi(scope, protocol)

        self._headers["accept-ranges"] = "bytes"
        empty_res = scope.method.lower() == "head"
        h_range = scope.headers.get("range")
        h_if_range = scope.headers.get("if-range")
        if h_range or (h_if_range and self._if_range_feasible(h_if_range)):
            try:
                ranges = self._parse_range_header(h_range, stat_data.st_size)
            except _RangeNotSatisfiable as exc:
                return protocol.response_empty(416, [("content-range", f"bytes */{exc.max_size}")])
            except Exception:
                return protocol.response_empty(400)
            # FIXME: support multiple ranges in RSGI
            range_start, range_end = ranges[0]
            self._headers["content-range"] = f"bytes {range_start}-{range_end - 1}/{stat_data.st_size}"
            self._headers["content-length"] = str(range_end - range_start)
            if empty_res:
                return protocol.response_empty(206, list(self.rsgi_headers()))
            return protocol.response_file_range(206, list(self.rsgi_headers()), self.file_path, range_start, range_end)

        if empty_res:
            return protocol.response_empty(self.status_code, list(self.rsgi_headers()))
        protocol.response_file(self.status_code, list(self.rsgi_headers()), self.file_path)


class HTTPIOResponse(HTTPResponse):
    def __init__(
        self,
        io_stream: BinaryIO,
        status_code: int = 200,
        headers: dict[str, str] = {},
        cookies: dict[str, Any] = {},
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

    def rsgi(self, scope, protocol):
        protocol.response_bytes(self.status_code, list(self.rsgi_headers()), self.io_stream.read())


class HTTPIterResponse(HTTPResponse):
    def __init__(
        self, iter: Iterable[bytes], status_code: int = 200, headers: dict[str, str] = {}, cookies: dict[str, Any] = {}
    ):
        super().__init__(status_code, headers=headers, cookies=cookies)
        self.iter = iter

    async def _send_body(self, send):
        for chunk in self.iter:
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def rsgi(self, scope, protocol):
        trx = protocol.response_stream(self.status_code, list(self.rsgi_headers()))
        for chunk in self.iter:
            await trx.send_bytes(chunk)


class HTTPAsyncIterResponse(HTTPResponse):
    def __init__(
        self,
        iter: AsyncIterable[bytes],
        status_code: int = 200,
        headers: dict[str, str] = {},
        cookies: dict[str, Any] = {},
    ):
        super().__init__(status_code, headers=headers, cookies=cookies)
        self.iter = iter

    async def _send_body(self, send):
        async for chunk in self.iter:
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def rsgi(self, scope, protocol):
        trx = protocol.response_stream(self.status_code, list(self.rsgi_headers()))
        async for chunk in self.iter:
            await trx.send_bytes(chunk)
