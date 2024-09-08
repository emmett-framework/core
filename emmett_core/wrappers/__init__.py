from typing import Any


class Wrapper:
    def __getitem__(self, name: str) -> Any:
        return getattr(self, name, None)

    def __setitem__(self, name: str, value: Any):
        setattr(self, name, value)
