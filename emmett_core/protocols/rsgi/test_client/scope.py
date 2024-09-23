import sys
from io import BytesIO
from urllib.parse import parse_qs

from ....datastructures import sdict
from .helpers import Headers, filesdict, stream_encode_multipart
from .urls import iri_to_uri, url_encode, url_fix, url_parse, url_unparse


class ScopeHeaders:
    def __init__(self, data):
        self.inner = {}
        self._inject(data)

    def _inject(self, data):
        for key, val in data:
            if key in self.inner:
                self.inner[key].append(val)
            else:
                self.inner[key] = [val]

    def __contains__(self, key: str):
        return key in self.inner

    def keys(self):
        return self.inner.keys()

    def values(self):
        for key in self.inner.keys():
            yield self.inner[key][0]

    def items(self):
        for key in self.inner.keys():
            yield key, self.inner[key][0]

    def get(self, key, default=None):
        if rv := self.inner.get(key):
            return rv[0]
        return default

    def get_all(self, key, default=None):
        return self.inner.get(key, default)

    def _denorm(self):
        for key in self.inner.keys():
            for val in self.inner[key]:
                yield key, val


class Scope:
    def __init__(
        self,
        headers,
        path,
        method,
        query_string,
        scheme="http",
        proto="http",
        http_version="1.1",
        rsgi_version="2.4",
        server="127.0.0.1",
        client="127.0.0.1",
        authority=None,
    ):
        self.headers = ScopeHeaders(headers)
        self.path = path
        self.method = method
        self.query_string = query_string
        # self.body = body
        self.scheme = scheme
        self.proto = proto
        self.http_version = http_version
        self.rsgi_version = rsgi_version
        self.server = server
        self.client = client
        self.authority = authority


class ScopeBuilder(object):
    server_protocol = "1.1"

    def __init__(
        self,
        path="/",
        base_url=None,
        query_string=None,
        method="GET",
        input_stream=None,
        content_type=None,
        content_length=None,
        errors_stream=None,
        headers=None,
        data=None,
        charset="utf-8",
        boundary=None,
    ):
        if query_string is None and "?" in path:
            path, query_string = path.split("?", 1)
        self.charset = charset
        self.path = iri_to_uri(path)
        if base_url is not None:
            base_url = url_fix(iri_to_uri(base_url, charset), charset)
        self.base_url = base_url
        if isinstance(query_string, (bytes, str)):
            self.query_string = query_string
        else:
            if query_string is None:
                query_string = sdict()
            elif not isinstance(query_string, dict):
                query_string = self._parse_querystring(query_string)
            self.args = query_string
        self.method = method
        if headers is None:
            headers = Headers()
        elif not isinstance(headers, Headers):
            headers = Headers(headers)
        self.headers = headers
        if content_type is not None:
            self.content_type = content_type
        if errors_stream is None:
            errors_stream = sys.stderr
        self.errors_stream = errors_stream
        self.input_stream = input_stream
        self.content_length = content_length
        self.boundary = boundary
        self.closed = False

        if data:
            if input_stream is not None:
                raise TypeError("can't provide input stream and data")
            if isinstance(data, str):
                data = data.encode(self.charset)
            if isinstance(data, bytes):
                self.input_stream = BytesIO(data)
                if self.content_length is None:
                    self.content_length = len(data)
            else:
                for key, values in data.items():
                    if not isinstance(values, list):
                        values = [values]
                    for v in values:
                        if isinstance(v, (tuple)) or hasattr(v, "read"):
                            self._add_file_from_data(key, v)
                        else:
                            if self.form[key] is None:
                                self.form[key] = []
                            self.form[key].append(v)

    @staticmethod
    def _parse_querystring(query_string):
        dget = parse_qs(query_string, keep_blank_values=1)
        params = sdict(dget)
        for key, value in params.items():
            if isinstance(value, list) and len(value) == 1:
                params[key] = value[0]
        return params

    def _add_file_from_data(self, key, value):
        if isinstance(value, tuple):
            self.files.add_file(key, *value)
        else:
            self.files.add_file(key, value)

    def _get_base_url(self):
        return url_unparse((self.url_scheme, self.host, self.script_root, "", "")).rstrip("/") + "/"

    def _set_base_url(self, value):
        if value is None:
            scheme = "http"
            netloc = "localhost"
            script_root = ""
        else:
            scheme, netloc, script_root, qs, anchor = url_parse(value)
            if qs or anchor:
                raise ValueError("base url must not contain a query string or fragment")
        self.script_root = script_root.rstrip("/")
        self.host = netloc
        self.url_scheme = scheme

    base_url = property(_get_base_url, _set_base_url)
    del _get_base_url, _set_base_url

    def _get_content_type(self):
        ct = self.headers.get("Content-Type")
        if ct is None and not self._input_stream:
            if self._files:
                return "multipart/form-data"
            elif self._form:
                return "application/x-www-form-urlencoded"
            return None
        return ct

    def _set_content_type(self, value):
        if value is None:
            self.headers.pop("Content-Type", None)
        else:
            self.headers["Content-Type"] = value

    content_type = property(_get_content_type, _set_content_type)
    del _get_content_type, _set_content_type

    def _get_content_length(self):
        return self.headers.get("Content-Length", type=int)

    def _set_content_length(self, value):
        if value is None:
            self.headers.pop("Content-Length", None)
        else:
            self.headers["Content-Length"] = str(value)

    content_length = property(_get_content_length, _set_content_length)
    del _get_content_length, _set_content_length

    def form_property(name, storage):  # noqa: N805
        key = "_" + name

        def getter(self):
            if self._input_stream is not None:
                raise AttributeError("an input stream is defined")
            rv = getattr(self, key)
            if rv is None:
                rv = storage()
                setattr(self, key, rv)

            return rv

        def setter(self, value):
            self._input_stream = None
            setattr(self, key, value)

        return property(getter, setter)

    form = form_property("form", sdict)
    files = form_property("files", filesdict)
    del form_property

    def _get_input_stream(self):
        return self._input_stream

    def _set_input_stream(self, value):
        self._input_stream = value
        self._form = self._files = None

    input_stream = property(
        _get_input_stream,
        _set_input_stream,
    )
    del _get_input_stream, _set_input_stream

    def _get_query_string(self):
        if self._query_string is None:
            if self._args is not None:
                return url_encode(self._args, charset=self.charset)
            return ""
        return self._query_string

    def _set_query_string(self, value):
        self._query_string = value
        self._args = None

    query_string = property(_get_query_string, _set_query_string)
    del _get_query_string, _set_query_string

    def _get_args(self):
        if self._query_string is not None:
            raise AttributeError("a query string is defined")
        if self._args is None:
            self._args = sdict()
        return self._args

    def _set_args(self, value):
        self._query_string = None
        self._args = value

    args = property(_get_args, _set_args)
    del _get_args, _set_args

    @property
    def server_name(self):
        return self.host.split(":", 1)[0]

    @property
    def server_port(self):
        pieces = self.host.split(":", 1)
        if len(pieces) == 2 and pieces[1].isdigit():
            return int(pieces[1])
        elif self.url_scheme == "https":
            return 443
        return 80

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def close(self):
        if self.closed:
            return
        try:
            files = self.files.values()
        except AttributeError:
            files = ()
        for f in files:
            try:
                f.close()
            except Exception:
                pass
        self.closed = True

    def get_data(self):
        input_stream = self.input_stream
        content_length = self.content_length
        content_type = self.content_type

        if input_stream is not None:
            start_pos = input_stream.tell()
            input_stream.seek(0, 2)
            end_pos = input_stream.tell()
            input_stream.seek(start_pos)
            content_length = end_pos - start_pos
        elif content_type == "multipart/form-data":
            values = sdict()
            for d in [self.files, self.form]:
                for key, val in d.items():
                    if key not in values:
                        values[key] = []
                    values[key].extend(val)
            input_stream, content_length, boundary = stream_encode_multipart(
                values, charset=self.charset, boundary=self.boundary
            )
            content_type += '; boundary="%s"' % boundary
        elif content_type == "application/x-www-form-urlencoded":
            values = url_encode(self.form, charset=self.charset)
            values = values.encode("ascii")
            content_length = len(values)
            input_stream = BytesIO(values)
        else:
            input_stream = BytesIO()

        headers = [("host", self.host)]
        if self.content_type:
            headers.extend([("content-type", content_type), ("content-length", str(content_length or 0))])
        for key, value in self.headers:
            headers.append((key, value))

        scope = Scope(
            headers=headers,
            path=self.path,
            method=self.method,
            query_string=self.query_string,
            scheme=self.url_scheme,
            http_version=self.server_protocol,
            server=f"{self.server_name}:{self.server_port}",
            client=f"{self.server_name}:{self.server_port}",
        )

        return scope, input_stream.getvalue()
