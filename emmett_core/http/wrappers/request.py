import datetime
from abc import abstractmethod
from io import BytesIO
from typing import Any, Optional
from urllib.parse import parse_qs

from ..._emmett_core import (
    MultiPartEncodingError,
    MultiPartExceedingSizeError,
    MultiPartParsingError,
    MultiPartReader,
    MultiPartStateError,
    get_content_type,
)
from ...datastructures import sdict
from ...http.response import HTTPBytesResponse
from ...parsers import Parsers
from ...utils import cachedprop
from . import IngressWrapper
from .helpers import FileStorage


class Request(IngressWrapper):
    __slots__ = ["_now", "method"]

    method: str

    @property
    @abstractmethod
    async def body(self) -> bytes: ...

    #: allow eventual overrides
    @cachedprop
    def now(self) -> datetime.datetime:
        return self._now

    @cachedprop
    def content_type(self) -> Optional[str]:
        return get_content_type(self.headers.get("content-type", "")) or "text/plain"

    @cachedprop
    def content_length(self) -> int:
        return self.headers.get("content_length", 0, cast=int)

    _empty_body_methods = {v: v for v in ["GET", "HEAD", "OPTIONS"]}

    @cachedprop
    async def _input_params(self):
        if self._empty_body_methods.get(self.method) or not self.content_type:
            return sdict(), sdict()
        return await self._load_params()

    @cachedprop
    async def body_params(self) -> sdict[str, Any]:
        rv, _ = await self._input_params
        return rv

    @cachedprop
    async def files(self) -> sdict[str, FileStorage]:
        _, rv = await self._input_params
        return rv

    @staticmethod
    async def _load_params_missing(*args, **kwargs):
        return sdict(), sdict()

    async def _load_params_json(self, body):
        try:
            params = Parsers.get_for("json")(await body)
        except Exception:
            params = {}
        return sdict(params), sdict()

    async def _load_params_form_urlencoded(self, body):
        rv = sdict()
        data = await body
        for key, values in parse_qs(data.decode("latin-1"), keep_blank_values=True).items():
            if len(values) == 1:
                rv[key] = values[0]
                continue
            rv[key] = values
        return rv, sdict()

    @property
    def _multipart_headers(self):
        return self.headers

    @staticmethod
    def _file_param_from_field(field):
        return FileStorage(BytesIO(field.file.read()), field.filename, field.name, field.type, field.headers)

    async def _load_params_form_multipart(self, body):
        params, files = sdict(), sdict()
        try:
            parser = MultiPartReader(self.headers.get("content-type"), self.max_multipart_size)
            async for chunk in body:
                parser.parse(chunk)
            for key, is_file, field in parser.contents():
                if is_file:
                    files[key] = data = files[key] or []
                    data.append(FileStorage(field))
                else:
                    params[key] = data = params[key] or []
                    data.append(field.decode("utf8"))
        except MultiPartEncodingError:
            raise HTTPBytesResponse(400, b"Invalid encoding")
        except (MultiPartParsingError, MultiPartStateError):
            raise HTTPBytesResponse(400, b"Invalid multipart data")
        except MultiPartExceedingSizeError:
            raise HTTPBytesResponse(413, b"Request entity too large")
        for target in (params, files):
            for key, val in target.items():
                if len(val) == 1:
                    target[key] = val[0]
        return params, files

    _params_loaders = {
        "application/json": _load_params_json,
        "application/x-www-form-urlencoded": _load_params_form_urlencoded,
        "multipart/form-data": _load_params_form_multipart,
    }

    def _load_params(self):
        loader = self._params_loaders.get(self.content_type, self._load_params_missing)
        return loader(self, self.body)

    @abstractmethod
    async def push_promise(self, path: str): ...
