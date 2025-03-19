import asyncio


class Dispatcher:
    __slots__ = ["f", "flow_open", "flow_close"]

    def __init__(self, route):
        self.f = route.f
        self.flow_open = route.pipeline_flow_open
        self.flow_close = route.pipeline_flow_close

    async def _parallel_flow(self, flow):
        tasks = [asyncio.create_task(method()) for method in flow]
        await asyncio.gather(*tasks, return_exceptions=True)
        for task in tasks:
            if task.exception():
                raise task.exception()

    def dispatch(self, reqargs):
        return self.f(**reqargs)


class RequestDispatcher(Dispatcher):
    __slots__ = ["response_builder"]

    def __init__(self, route, rule, response_builder):
        super().__init__(route)
        self.response_builder = response_builder

    async def dispatch(self, reqargs, response):
        return self.response_builder(await self.f(**reqargs), response)


class RequestOpenDispatcher(RequestDispatcher):
    __slots__ = []

    async def dispatch(self, reqargs, response):
        await self._parallel_flow(self.flow_open)
        return self.response_builder(await self.f(**reqargs), response)


class RequestCloseDispatcher(RequestDispatcher):
    __slots__ = []

    async def dispatch(self, reqargs, response):
        try:
            rv = self.response_builder(await self.f(**reqargs), response)
        finally:
            await asyncio.shield(self._parallel_flow(self.flow_close))
        return rv


class RequestFlowDispatcher(RequestDispatcher):
    __slots__ = []

    async def dispatch(self, reqargs, response):
        await self._parallel_flow(self.flow_open)
        try:
            rv = self.response_builder(await self.f(**reqargs), response)
        finally:
            await asyncio.shield(self._parallel_flow(self.flow_close))
        return rv


class WSOpenDispatcher(Dispatcher):
    __slots__ = []

    async def dispatch(self, reqargs):
        await self._parallel_flow(self.flow_open)
        await self.f(**reqargs)


class WSCloseDispatcher(Dispatcher):
    __slots__ = []

    async def dispatch(self, reqargs):
        try:
            await self.f(**reqargs)
        except asyncio.CancelledError:
            await asyncio.shield(self._parallel_flow(self.flow_close))
            return
        except Exception:
            await self._parallel_flow(self.flow_close)
            raise
        await asyncio.shield(self._parallel_flow(self.flow_close))


class WSFlowDispatcher(Dispatcher):
    __slots__ = []

    async def dispatch(self, reqargs):
        await self._parallel_flow(self.flow_open)
        try:
            await self.f(**reqargs)
        except asyncio.CancelledError:
            await asyncio.shield(self._parallel_flow(self.flow_close))
            return
        except Exception:
            await self._parallel_flow(self.flow_close)
            raise
        await asyncio.shield(self._parallel_flow(self.flow_close))
