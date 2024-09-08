from typing import Dict, Iterator, MutableMapping, Optional, Tuple


class ResponseHeaders(MutableMapping[str, str]):
    __slots__ = ["_data"]

    def __init__(self, data: Optional[Dict[str, str]] = None):
        self._data = data or {}

    __hash__ = None  # type: ignore

    def __getitem__(self, key: str) -> str:
        return self._data[key.lower()]

    def __setitem__(self, key: str, value: str):
        self._data[key.lower()] = value

    def __delitem__(self, key: str):
        del self._data[key.lower()]

    def __contains__(self, key: str) -> bool:  # type: ignore
        return key.lower() in self._data

    def __iter__(self) -> Iterator[str]:
        for key in self._data.keys():
            yield key

    def __len__(self) -> int:
        return len(self._data)

    def items(self) -> Iterator[Tuple[str, str]]:  # type: ignore
        for key, value in self._data.items():
            yield key, value

    def keys(self) -> Iterator[str]:  # type: ignore
        for key in self._data.keys():
            yield key

    def values(self) -> Iterator[str]:  # type: ignore
        for value in self._data.values():
            yield value

    def update(self, data: Dict[str, str]):  # type: ignore
        self._data.update(data)
