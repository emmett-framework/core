from urllib.parse import quote as uquote


class UrlBuilder:
    __slots__ = ("current", "components", "_args")

    def __init__(self, current, components=[]):
        self.current = current
        if not components:
            self.components = ["/{}"]
            self._args = [""]
        else:
            self.components = ["{}"] + components[1:]
            self._args = [components[0]]

    @property
    def path(self):
        return self._args[0]

    def arg(self, value):
        if not self.components:
            self.components.append("/{}")
        return self.components.pop(0).format(value)

    def add_prefix(self, args):
        if self.current.app._router_http._prefix_main:
            self.components.insert(0, "{}")
            args.insert(0, self.current.app._router_http._prefix_main)

    def add_language(self, args, language):
        if language:
            self.components.insert(0, "/{}")
            args.insert(0, language)

    def path_prefix(self, scheme, host):
        if scheme and host:
            return "{}://{}".format(scheme, host)
        return ""

    def args(self, args):
        rv = ""
        for arg in args:
            rv += self.arg(arg)
        return rv

    def params(self, params):
        if params:
            return "?" + "&".join("%s=%s" % (uquote(str(k)), uquote(str(v))) for k, v in params.items())
        return ""

    def url(self, scheme, host, language, args, params):
        args = self._args + args
        self.add_language(args, language)
        self.add_prefix(args)
        return f"{self.path_prefix(scheme, host)}{self.args(args)}{self.params(params)}"


class HttpUrlBuilder(UrlBuilder):
    __slots__ = ("components", "_args")

    def add_static_versioning(self, args):
        versioning = self.current.app._router_http.static_versioning()
        if self.path.startswith("/static") and versioning:
            self.components.insert(1, "/_{}")
            args.insert(1, str(versioning))

    def anchor(self, anchor):
        rv = ""
        if anchor:
            if not isinstance(anchor, (list, tuple)):
                anchor = [anchor]
            for element in anchor:
                rv += "#{}".format(element)
        return rv

    def url(self, scheme, host, language, args, params, anchor):
        args = self._args + args
        self.add_static_versioning(args)
        self.add_language(args, language)
        self.add_prefix(args)
        return f"{self.path_prefix(scheme, host)}{self.args(args)}{self.params(params)}{self.anchor(anchor)}"


class Url:
    __slots__ = ["current"]
    _http_to_ws_schemes = {"http": "ws", "https": "wss"}

    def __init__(self, current) -> None:
        self.current = current

    def http(self, path, args=[], params={}, anchor=None, sign=None, scheme=None, host=None, language=None):
        if not isinstance(args, (list, tuple)):
            args = [args]
        # allow user to use url('static', 'file')
        if path == "static":
            path = "/static"
        # routes urls with 'dot' notation
        if "/" not in path:
            module = None
            # urls like 'function' refers to same module
            if "." not in path:
                namespace = self.current.app.config.url_default_namespace or self.current.app.name
                path = namespace + "." + path
            # urls like '.function' refers to main app module
            elif path.startswith("."):
                if not hasattr(self.current, "request"):
                    raise RuntimeError(f'cannot build url("{path}",...) without current request')
                module = self.current.request.name.rsplit(".", 1)[0]
                path = module + path
            # find correct route
            try:
                url_components = self.current.app._router_http.routes_out[path]["path"]
                url_host = self.current.app._router_http.routes_out[path]["host"]
                builder = HttpUrlBuilder(self.current, url_components)
                # try to use the correct hostname
                if url_host is not None:
                    try:
                        if self.current.request.host != url_host:
                            scheme = self.current.request.scheme
                            host = url_host
                    except Exception:
                        pass
            except KeyError:
                if path.endswith(".static"):
                    module = module or path.rsplit(".", 1)[0]
                    builder = HttpUrlBuilder(self.current, [f"/static/__{module}__"])
                else:
                    raise RuntimeError(f'invalid url("{path}",...)')
        # handle classic urls
        else:
            builder = HttpUrlBuilder(self.current, [path])
        # add language
        lang = None
        if self.current.app.language_force_on_url:
            if language:
                #: use the given language if is enabled in application
                if language in self.current.app.languages:
                    lang = language
            else:
                #: try to use the request language if context exists
                if hasattr(self.current, "request"):
                    lang = self.current.request.language
            if lang == self.current.app.language_default:
                lang = None
        # # add extension (useless??)
        # if extension:
        #     url = url + '.' + extension
        # scheme=True means to use current scheme
        if scheme is True:
            if not hasattr(self.current, "request"):
                raise RuntimeError(f'cannot build url("{path}",...) without current request')
            scheme = self.current.request.scheme
        # add scheme and host
        if scheme:
            if host is None:
                if not hasattr(self.current, "request"):
                    raise RuntimeError(f'cannot build url("{path}",...) without current request')
                host = self.current.request.host
        # add signature
        if sign:
            if "_signature" in params:
                del params["_signature"]
            params["_signature"] = sign(path, args, params, anchor, scheme, host, language)
        return builder.url(scheme, host, lang, args, params, anchor)

    def ws(self, path, args=[], params={}, scheme=None, host=None, language=None):
        if not isinstance(args, (list, tuple)):
            args = [args]
        # routes urls with 'dot' notation
        if "/" not in path:
            # urls like 'function' refers to same module
            if "." not in path:
                namespace = self.current.app.config.url_default_namespace or self.current.app.name
                path = namespace + "." + path
            # urls like '.function' refers to main app module
            elif path.startswith("."):
                if not hasattr(self.current, "request"):
                    raise RuntimeError(f'cannot build url("{path}",...) without current request')
                module = self.current.request.name.rsplit(".", 1)[0]
                path = module + path
            # find correct route
            try:
                url_components = self.current.app._router_ws.routes_out[path]["path"]
                url_host = self.current.app._router_ws.routes_out[path]["host"]
                builder = UrlBuilder(self.current, url_components)
                # try to use the correct hostname
                if url_host is not None:
                    # TODO: remap host
                    try:
                        if self.current.request.host != url_host:
                            scheme = self._http_to_ws_schemes[self.current.request.scheme]
                            host = url_host
                    except Exception:
                        pass
            except KeyError:
                raise RuntimeError(f'invalid url("{path}",...)')
        # handle classic urls
        else:
            builder = UrlBuilder(self.current, [path])
        # add language
        lang = None
        if self.current.app.language_force_on_url:
            if language:
                #: use the given language if is enabled in application
                if language in self.current.app.languages:
                    lang = language
            else:
                #: try to use the request language if context exists
                if hasattr(self.current, "request"):
                    lang = self.current.request.language
            if lang == self.current.app.language_default:
                lang = None
        # scheme=True means to use current scheme
        if scheme is True:
            if not hasattr(self.current, "request"):
                raise RuntimeError(f'cannot build url("{path}",...) without current request')
            scheme = self._http_to_ws_schemes[self.current.request.scheme]
        elif scheme:
            scheme = self._http_to_ws_schemes.get(scheme, scheme)
        # add scheme and host
        if scheme:
            if host is None:
                if not hasattr(self.current, "request"):
                    raise RuntimeError(f'cannot build url("{path}",...) without current request')
                host = self.current.request.host
        return builder.url(scheme, host, lang, args, params)

    def __call__(self, *args, **kwargs):
        return self.http(*args, **kwargs)
