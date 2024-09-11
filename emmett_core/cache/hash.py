from __future__ import annotations

import hashlib
from typing import Any, Callable, Dict, List, Tuple


hashlib_sha1 = lambda s: hashlib.sha1(bytes(s, "utf8"))  # noqa: S324


class CacheHashMixin:
    def __init__(self):
        self.strategies = {}

    def add_strategy(self, key: str, method: Callable[..., Any] = lambda data: data):
        self.strategies[key] = method

    def _hash_component(self, key: str, data: Any) -> str:
        return "".join([key, "{", repr(data), "}"])

    def _build_hash(self, data: Dict[str, Any]) -> str:
        components = []
        for key, strategy in self.strategies.items():
            components.append(self._hash_component(key, strategy(data[key])))
        return hashlib_sha1(":".join(components)).hexdigest()

    def _build_ctx_key(self, **ctx) -> str:
        return self.key + ":" + self._build_hash(ctx)  # type: ignore

    @staticmethod
    def dict_strategy(data: Dict[str, Any]) -> List[Tuple[str, Any]]:
        return [(key, data[key]) for key in sorted(data)]
