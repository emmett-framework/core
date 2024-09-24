import pytest

from emmett_core.utils import _cached_prop_loop, _cached_prop_sync, cachedprop


class Class:
    def __init__(self):
        self.calls = 0

    @cachedprop
    def prop(self):
        self.calls += 1
        return "test_cachedprop_sync"

    @cachedprop
    async def prop_loop(self):
        self.calls += 1
        return "test_cachedprop_loop"


def test_cachedprop_sync():
    assert isinstance(Class.prop, _cached_prop_sync)
    obj = Class()
    assert obj.calls == 0
    assert obj.prop == "test_cachedprop_sync"
    assert obj.calls == 1
    assert obj.prop == "test_cachedprop_sync"
    assert obj.calls == 1


@pytest.mark.asyncio
async def test_cachedprop_loop():
    assert isinstance(Class.prop_loop, _cached_prop_loop)
    obj = Class()
    assert obj.calls == 0
    assert (await obj.prop_loop) == "test_cachedprop_loop"
    assert obj.calls == 1
    assert (await obj.prop_loop) == "test_cachedprop_loop"
    assert obj.calls == 1
