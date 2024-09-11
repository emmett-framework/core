from __future__ import annotations

from typing import Any, Callable, Dict, List, Union

from ..cache.handlers import CacheHandler
from ..cache.hash import CacheHashMixin
from .dispatchers import RequestDispatcher


class RouteCacheRule(CacheHashMixin):
    def __init__(
        self,
        handler: CacheHandler,
        query_params: bool = True,
        language: bool = True,
        hostname: bool = False,
        headers: List[str] = [],
        duration: Union[int, str, None] = "default",
    ):
        super().__init__()
        self.cache = handler
        self.check_headers = headers
        self.duration = duration
        self.add_strategy("kwargs", self.dict_strategy)
        self._ctx_builders = []
        if hostname:
            self.add_strategy("hostname")
            self._ctx_builders.append(("hostname", lambda route, current: route.hostname))
        if language:
            self.add_strategy("language")
            self._ctx_builders.append(("language", lambda route, current: current.language))
        if query_params:
            self.add_strategy("query_params", self.dict_strategy)
            self._ctx_builders.append(("query_params", lambda route, current: current.request.query_params))
        if headers:
            self.add_strategy("headers", self.headers_strategy)
            self._ctx_builders.append(("headers", lambda route, current: current.request.headers))

    def _build_ctx_key(self, route: Any, **ctx) -> str:  # type: ignore
        return route.name + ":" + self._build_hash(ctx)

    def _build_ctx(self, kwargs: Dict[str, Any], route: Any, current: Any) -> Dict[str, Any]:
        rv = {"kwargs": kwargs}
        for key, builder in self._ctx_builders:
            rv[key] = builder(route, current)
        return rv

    def headers_strategy(self, data: Dict[str, str]) -> List[str]:
        return [data[key] for key in self.check_headers]

    def __call__(self, f: Callable[..., Any]) -> Callable[..., Any]:
        from .router import RouterMixin

        obj = RouterMixin.exposing()
        obj.cache_rule = self
        return f


class CacheDispatcher(RequestDispatcher):
    __slots__ = ["current", "route", "cache_rule"]

    def __init__(self, route, rule, response_builder):
        super().__init__(route, rule, response_builder)
        self.current = rule.current
        self.route = route
        self.cache_rule = rule.cache_rule

    async def get_data(self, reqargs, response):
        key = self.cache_rule._build_ctx_key(
            self.route, **self.cache_rule._build_ctx(reqargs, self.route, self.current)
        )
        data = self.cache_rule.cache.get(key)
        if data is not None:
            response.headers.update(data["headers"])
            return data["content"]
        content = await self.f(**reqargs)
        if response.status == 200:
            self.cache_rule.cache.set(key, {"content": content, "headers": response.headers}, self.cache_rule.duration)
        return content

    async def dispatch(self, reqargs, response):
        content = await self.get_data(reqargs, response)
        return self.response_builder(content, response)


class CacheOpenDispatcher(CacheDispatcher):
    __slots__ = []

    async def dispatch(self, reqargs, response):
        await self._parallel_flow(self.flow_open)
        return await super().dispatch(reqargs, response)


class CacheCloseDispatcher(CacheDispatcher):
    __slots__ = []

    async def dispatch(self, reqargs, response):
        try:
            content = await self.get_data(reqargs, response)
        except Exception:
            await self._parallel_flow(self.flow_close)
            raise
        await self._parallel_flow(self.flow_close)
        return self.response_builder(content, response)


class CacheFlowDispatcher(CacheDispatcher):
    __slots__ = []

    async def dispatch(self, reqargs, response):
        await self._parallel_flow(self.flow_open)
        try:
            content = await self.get_data(reqargs, response)
        except Exception:
            await self._parallel_flow(self.flow_close)
            raise
        await self._parallel_flow(self.flow_close)
        return self.response_builder(content, response)
