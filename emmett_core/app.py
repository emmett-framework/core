from __future__ import annotations

import os
import sys
from collections.abc import Awaitable, Callable
from logging import Logger
from typing import Any

from ._internal import create_missing_app_folders, get_root_path
from .datastructures import gsdict, sdict
from .extensions import Extension, ExtensionType, Signals
from .pipeline import Pipe
from .protocols.rsgi.test_client.client import EmmettTestClient
from .routing.cache import RouteCacheRule
from .routing.router import RoutingCtx, RoutingCtxGroup
from .typing import ErrorHandlerType
from .utils import cachedprop


class Config(gsdict):
    __slots__ = ()

    def __init__(self, app: App):
        self._app = app
        super().__init__(
            hostname_default=None,
            static_version=None,
            static_version_urls=False,
            url_default_namespace=None,
            request_max_content_length=None,
            request_multipart_max_size=1024 * 1024,
            request_body_timeout=None,
            response_timeout=None,
        )
        self._handle_static = True

    def __setattr__(self, key, value):
        obj = getattr(self.__class__, key, None)
        if isinstance(obj, property):
            return obj.fset(self, value)
        return super().__setattr__(key, value)

    @property
    def handle_static(self) -> bool:
        return self._handle_static

    @handle_static.setter
    def handle_static(self, value: bool):
        self._handle_static = value
        self._app._configure_handlers()


class AppModule:
    @classmethod
    def from_app(
        cls,
        app: App,
        import_name: str,
        name: str,
        static_folder: str | None,
        static_path: str | None,
        url_prefix: str | None,
        hostname: str | None,
        cache: RouteCacheRule | None,
        root_path: str | None,
        pipeline: list[Pipe],
        opts: dict[str, Any] = {},
    ):
        return cls(
            app,
            name,
            import_name,
            static_folder=static_folder,
            static_path=static_path,
            url_prefix=url_prefix,
            hostname=hostname,
            cache=cache,
            root_path=root_path,
            pipeline=pipeline,
            **opts,
        )

    @classmethod
    def from_module(
        cls,
        appmod: AppModule,
        import_name: str,
        name: str,
        static_folder: str | None,
        static_path: str | None,
        url_prefix: str | None,
        hostname: str | None,
        cache: RouteCacheRule | None,
        root_path: str | None,
        opts: dict[str, Any] = {},
    ):
        if "." in name:
            raise RuntimeError("Nested app modules' names should not contains dots")
        name = appmod.name + "." + name
        if url_prefix and not url_prefix.startswith("/"):
            url_prefix = "/" + url_prefix
        module_url_prefix = (appmod.url_prefix + (url_prefix or "")) if appmod.url_prefix else url_prefix
        hostname = hostname or appmod.hostname
        cache = cache or appmod.cache
        return cls(
            appmod.app,
            name,
            import_name,
            static_folder=static_folder,
            static_path=static_path,
            url_prefix=module_url_prefix,
            hostname=hostname,
            cache=cache,
            root_path=root_path,
            pipeline=appmod.pipeline,
            **opts,
        )

    @classmethod
    def from_module_group(
        cls,
        appmodgroup: AppModuleGroup,
        import_name: str,
        name: str,
        static_folder: str | None,
        static_path: str | None,
        url_prefix: str | None,
        hostname: str | None,
        cache: RouteCacheRule | None,
        root_path: str | None,
        opts: dict[str, Any] = {},
    ) -> AppModulesGrouped:
        mods = []
        for module in appmodgroup.modules:
            mod = cls.from_module(
                module,
                import_name,
                name,
                static_folder=static_folder,
                static_path=static_path,
                url_prefix=url_prefix,
                hostname=hostname,
                cache=cache,
                root_path=root_path,
                opts=opts,
            )
            mods.append(mod)
        return AppModulesGrouped(*mods)

    def module(
        self,
        import_name: str,
        name: str,
        static_folder: str | None = None,
        static_path: str | None = None,
        url_prefix: str | None = None,
        hostname: str | None = None,
        cache: RouteCacheRule | None = None,
        root_path: str | None = None,
        module_class: type[AppModule] | None = None,
        **kwargs: Any,
    ) -> AppModule:
        module_class = module_class or self.__class__
        return module_class.from_module(
            self,
            import_name,
            name,
            static_folder=static_folder,
            static_path=static_path,
            url_prefix=url_prefix,
            hostname=hostname,
            cache=cache,
            root_path=root_path,
            opts=kwargs,
        )

    def __init__(
        self,
        app: App,
        name: str,
        import_name: str,
        static_folder: str | None = None,
        static_path: str | None = None,
        url_prefix: str | None = None,
        hostname: str | None = None,
        cache: RouteCacheRule | None = None,
        root_path: str | None = None,
        pipeline: list[Pipe] | None = None,
        **kwargs: Any,
    ):
        self.app = app
        self.name = name
        self.import_name = import_name
        if root_path is None:
            root_path = get_root_path(self.import_name)
        self.root_path = root_path
        if static_path and not static_path.startswith("/"):
            static_path = os.path.join(self.root_path, static_path)
        self._static_path = (
            os.path.join(self.app.static_path, static_folder)
            if static_folder
            else (static_path or self.app.static_path)
        )
        self.url_prefix = url_prefix
        self.hostname = hostname
        self.cache = cache
        self._super_pipeline = pipeline or []
        self.pipeline = []
        self.app._register_module(self)

    @property
    def pipeline(self) -> list[Pipe]:
        return self._pipeline

    @pipeline.setter
    def pipeline(self, pipeline: list[Pipe]):
        self._pipeline = self._super_pipeline + pipeline

    def route(self, paths: str | list[str] | None = None, name: str | None = None, **kwargs) -> RoutingCtx:
        if name is not None and "." in name:
            raise RuntimeError("App modules' route names should not contains dots")
        name = self.name + "." + (name or "")
        pipeline = kwargs.get("pipeline", [])
        if self.pipeline:
            pipeline = self.pipeline + pipeline
        kwargs["pipeline"] = pipeline
        kwargs["cache"] = kwargs.get("cache", self.cache)
        return self.app.route(paths=paths, name=name, prefix=self.url_prefix, hostname=self.hostname, **kwargs)

    def websocket(self, paths: str | list[str] | None = None, name: str | None = None, **kwargs) -> RoutingCtx:
        if name is not None and "." in name:
            raise RuntimeError("App modules' websocket names should not contains dots")
        name = self.name + "." + (name or "")
        pipeline = kwargs.get("pipeline", [])
        if self.pipeline:
            pipeline = self.pipeline + pipeline
        kwargs["pipeline"] = pipeline
        return self.app.websocket(paths=paths, name=name, prefix=self.url_prefix, hostname=self.hostname, **kwargs)


class App:
    __slots__ = [
        "__dict__",
        "_asgi_handlers",
        "_extensions_env",
        "_extensions_listeners",
        "_language_default",
        "_language_force_on_url",
        "_languages_set",
        "_languages",
        "_logger",
        "_modules",
        "_pipeline",
        "_router_http",
        "_router_ws",
        "config",
        "error_handlers",
        "ext",
        "import_name",
        "logger_name",
        "root_path",
        "static_path",
    ]

    debug = None
    config_class = Config
    modules_class = AppModule
    signals_class = Signals
    test_client_class = EmmettTestClient

    def __init__(self, import_name: str, root_path: str | None = None, url_prefix: str | None = None, **opts):
        self.import_name = import_name
        #: init debug var
        self.debug = os.environ.get("EMMETT_RUN_ENV") == "true"
        #: set paths for the application
        self._configure_paths(root_path, opts)
        #: init the configuration
        self.config = self.config_class(self)
        #: init languages
        self._languages: list[str] = []
        self._languages_set: set[str] = set()
        self._language_default: str | None = None
        self._language_force_on_url = False
        #: init routing
        self._pipeline: list[Pipe] = []
        self._init_routers(url_prefix)
        self._asgi_handlers = {}
        self._rsgi_handlers = {}
        self.error_handlers: dict[int, Callable[[], Awaitable[str]]] = {}
        self._init_handlers()
        #: init logger
        self._logger = None
        self.logger_name = self.import_name
        #: init extensions
        self.ext: sdict[str, Extension] = sdict()
        self._extensions_env: sdict[str, Any] = sdict()
        self._extensions_listeners: dict[str, list[Callable[..., Any]]] = {
            str(element): [] for element in self.signals_class
        }
        #: finalise
        self._modules: dict[str, AppModule] = {}
        self._register_with_ctx()

    def _configure_paths(self, root_path, opts):
        if root_path is None:
            root_path = get_root_path(self.import_name)
        self.root_path = root_path
        self.static_path = os.path.join(self.root_path, "static")
        create_missing_app_folders(self)

    def _init_routers(self, url_prefix):
        raise NotImplementedError

    def _init_handlers(self):
        raise NotImplementedError

    def _configure_handlers(self):
        self._asgi_handlers["http"]._configure_methods()
        self._rsgi_handlers["http"]._configure_methods()

    def _register_with_ctx(self):
        raise NotImplementedError

    @cachedprop
    def name(self):
        if self.import_name == "__main__":
            fn = getattr(sys.modules["__main__"], "__file__", None)
            if fn is None:
                rv = "__main__"
            else:
                rv = os.path.splitext(os.path.basename(fn))[0]
        else:
            rv = self.import_name
        return rv

    @property
    def languages(self) -> list[str]:
        return self._languages

    @languages.setter
    def languages(self, value: list[str]):
        self._languages = value
        self._languages_set = set(self._languages)

    @property
    def language_default(self) -> str | None:
        return self._language_default

    @language_default.setter
    def language_default(self, value: str):
        self._language_default = value

    @property
    def language_force_on_url(self) -> bool:
        return self._language_force_on_url

    @language_force_on_url.setter
    def language_force_on_url(self, value: bool):
        self._language_force_on_url = value
        self._router_http._mixin_cls._set_language_impl(self._router_http)
        self._router_ws._mixin_cls._set_language_impl(self._router_ws)
        self._configure_handlers()

    @property
    def pipeline(self) -> list[Pipe]:
        return self._pipeline

    @pipeline.setter
    def pipeline(self, pipes: list[Pipe]):
        self._pipeline = pipes
        self._router_http.pipeline = self._pipeline
        self._router_ws.pipeline = self._pipeline

    def route(
        self,
        paths: str | list[str] | None = None,
        name: str | None = None,
        pipeline: list[Pipe] | None = None,
        schemes: str | list[str] | None = None,
        hostname: str | None = None,
        methods: str | list[str] | None = None,
        prefix: str | None = None,
        cache: RouteCacheRule | None = None,
        output: str = "auto",
    ) -> RoutingCtx:
        if callable(paths):
            raise SyntaxError("Use @route(), not @route.")
        return self._router_http(
            paths=paths,
            name=name,
            pipeline=pipeline,
            schemes=schemes,
            hostname=hostname,
            methods=methods,
            prefix=prefix,
            cache=cache,
            output=output,
        )

    def websocket(
        self,
        paths: str | list[str] | None = None,
        name: str | None = None,
        pipeline: list[Pipe] | None = None,
        schemes: str | list[str] | None = None,
        hostname: str | None = None,
        prefix: str | None = None,
    ) -> RoutingCtx:
        if callable(paths):
            raise SyntaxError("Use @websocket(), not @websocket.")
        return self._router_ws(
            paths=paths, name=name, pipeline=pipeline, schemes=schemes, hostname=hostname, prefix=prefix
        )

    def on_error(self, code: int) -> Callable[[ErrorHandlerType], ErrorHandlerType]:
        def decorator(f: ErrorHandlerType) -> ErrorHandlerType:
            self.error_handlers[code] = f
            return f

        return decorator

    @property
    def log(self) -> Logger:
        if self._logger and self._logger.name == self.logger_name:
            return self._logger
        from .log import _logger_lock, create_logger

        with _logger_lock:
            if self._logger and self._logger.name == self.logger_name:
                return self._logger
            self._logger = rv = create_logger(self)
            return rv

    #: Register modules
    def _register_module(self, mod: AppModule):
        self._modules[mod.name] = mod

    #: Creates the extensions' environments and configs
    def __init_extension(self, ext):
        if ext.namespace is None:
            ext.namespace = ext.__name__
        if self._extensions_env[ext.namespace] is None:
            self._extensions_env[ext.namespace] = sdict()
        return self._extensions_env[ext.namespace], self.config[ext.namespace]

    #: Register extension listeners
    def __register_extension_listeners(self, ext):
        for signal, listener in ext._listeners_:
            self._extensions_listeners[signal].append(listener)

    #: Add an extension to application
    def use_extension(self, ext_cls: type[ExtensionType]) -> ExtensionType:
        if not issubclass(ext_cls, Extension):
            raise RuntimeError(f"{ext_cls.__name__} is an invalid extension")
        ext_env, ext_config = self.__init_extension(ext_cls)
        ext = self.ext[ext_cls.__name__] = ext_cls(self, ext_env, ext_config)
        self.__register_extension_listeners(ext)
        ext.on_load()
        return ext

    def send_signal(self, signal: Signals, *args, **kwargs):
        for listener in self._extensions_listeners[signal]:
            listener(*args, **kwargs)

    def test_client(self, use_cookies: bool = True, **kwargs):
        return self.__class__.test_client_class(self, use_cookies=use_cookies, **kwargs)

    def __call__(self, scope, receive, send):
        return self._asgi_handlers[scope["type"]](scope, receive, send)

    def __rsgi__(self, scope, protocol):
        return self._rsgi_handlers[scope.proto](scope, protocol)

    def __rsgi_init__(self, loop):
        self.send_signal(Signals.after_loop, loop=loop)

    def module(
        self,
        import_name: str,
        name: str,
        static_folder: str | None = None,
        static_path: str | None = None,
        url_prefix: str | None = None,
        hostname: str | None = None,
        cache: RouteCacheRule | None = None,
        root_path: str | None = None,
        pipeline: list[Pipe] | None = None,
        module_class: type[AppModule] | None = None,
        **kwargs: Any,
    ) -> AppModule:
        module_class = module_class or self.modules_class
        return module_class.from_app(
            self,
            import_name,
            name,
            static_folder=static_folder,
            static_path=static_path,
            url_prefix=url_prefix,
            hostname=hostname,
            cache=cache,
            root_path=root_path,
            pipeline=pipeline or [],
            opts=kwargs,
        )

    def module_group(self, *modules: AppModule) -> AppModuleGroup:
        return AppModuleGroup(*modules)


class AppModuleGroup:
    def __init__(self, *modules: AppModule):
        self.modules = modules

    def module(
        self,
        import_name: str,
        name: str,
        static_folder: str | None = None,
        static_path: str | None = None,
        url_prefix: str | None = None,
        hostname: str | None = None,
        cache: RouteCacheRule | None = None,
        root_path: str | None = None,
        module_class: type[AppModule] | None = None,
        **kwargs: Any,
    ) -> AppModulesGrouped:
        module_class = module_class or AppModule
        return module_class.from_module_group(
            self,
            import_name,
            name,
            static_folder=static_folder,
            static_path=static_path,
            url_prefix=url_prefix,
            hostname=hostname,
            cache=cache,
            root_path=root_path,
            opts=kwargs,
        )

    def route(self, paths: str | list[str] | None = None, name: str | None = None, **kwargs) -> RoutingCtxGroup:
        return RoutingCtxGroup([mod.route(paths=paths, name=name, **kwargs) for mod in self.modules])

    def websocket(self, paths: str | list[str] | None = None, name: str | None = None, **kwargs):
        return RoutingCtxGroup([mod.websocket(paths=paths, name=name, **kwargs) for mod in self.modules])


class AppModulesGrouped(AppModuleGroup):
    @property
    def pipeline(self) -> list[list[Pipe]]:
        return [module.pipeline for module in self.modules]

    @pipeline.setter
    def pipeline(self, pipeline: list[Pipe]):
        for module in self.modules:
            module.pipeline = pipeline
