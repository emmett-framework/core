import re
from collections.abc import Iterator, MutableMapping
from typing import BinaryIO

from ..._io import loop_copyfileobj


regex_client = re.compile(r"[\w\-:]+(\.[\w\-]+)*\.?")


class ResponseHeaders(MutableMapping[str, str]):
    __slots__ = ["_data"]

    def __init__(self, data: dict[str, str] | None = None):
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
        yield from self._data.keys()

    def __len__(self) -> int:
        return len(self._data)

    def items(self) -> Iterator[tuple[str, str]]:  # type: ignore
        yield from self._data.items()

    def keys(self) -> Iterator[str]:  # type: ignore
        yield from self._data.keys()

    def values(self) -> Iterator[str]:  # type: ignore
        yield from self._data.values()

    def update(self, data: dict[str, str]):  # type: ignore
        self._data.update(data)


class FileStorage:
    __slots__ = ["file"]

    def __init__(self, file):
        self.file = file

    def __iter__(self):
        return self.file.__iter__()

    def __getattr__(self, name):
        return getattr(self.file, name)

    @property
    def size(self):
        return self.file.content_length

    async def save(self, destination: BinaryIO | str, buffer_size: int = 16384):
        close_destination = False
        if isinstance(destination, str):
            destination = open(destination, "wb")
            close_destination = True
        try:
            await loop_copyfileobj(self.file, destination, buffer_size)
        finally:
            if close_destination:
                destination.close()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.filename} ({self.content_type})>"
