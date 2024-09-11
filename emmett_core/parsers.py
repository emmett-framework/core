from functools import partial
from typing import Any, Callable, Dict

from ._imports import orjson, rapidjson


if orjson is not None:
    _json_impl = orjson.loads
    _json_opts = {}
elif rapidjson is not None:
    _json_impl = rapidjson.loads
    _json_opts = {"datetime_mode": rapidjson.DM_ISO8601 | rapidjson.DM_NAIVE_IS_UTC, "number_mode": rapidjson.NM_NATIVE}
else:
    import json as _stdjson

    _json_impl = _stdjson.loads
    _json_opts = {}


class Parsers(object):
    _registry_: Dict[str, Callable[[str], Dict[str, Any]]] = {}

    @classmethod
    def register_for(cls, target):
        def wrap(f):
            cls._registry_[target] = f
            return f

        return wrap

    @classmethod
    def get_for(cls, target):
        return cls._registry_[target]


json = partial(_json_impl, **_json_opts)

Parsers.register_for("json")(json)
