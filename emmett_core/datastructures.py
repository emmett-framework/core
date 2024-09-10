import copy
from typing import Dict, Optional

from .typing import KT, VT


class sdict(Dict[KT, VT]):
    #: like a dictionary except `obj.foo` can be used in addition to
    #  `obj['foo']`, and setting obj.foo = None deletes item foo.
    __slots__ = ()

    __setattr__ = dict.__setitem__  # type: ignore
    __delattr__ = dict.__delitem__  # type: ignore
    __getitem__ = dict.get  # type: ignore

    # see http://stackoverflow.com/questions/10364332/how-to-pickle-python-object-derived-from-dict
    def __getattr__(self, key: str) -> Optional[VT]:
        if key.startswith("__"):
            raise AttributeError
        return self.get(key, None)  # type: ignore

    __repr__ = lambda self: "<sdict %s>" % dict.__repr__(self)
    __getstate__ = lambda self: None
    __copy__ = lambda self: sdict(self)
    __deepcopy__ = lambda self, memo: sdict(copy.deepcopy(dict(self)))


class gsdict(sdict[KT, VT]):
    #: like sdict, except it autogrows creating sub-sdict attributes
    __slots__ = ()

    def __getitem__(self, key):
        if key not in self.keys():
            self[key] = sdict()
        return super().__getitem__(key)

    __getattr__ = __getitem__


class ImmutableListMixin:
    _hash_cache = None

    def __hash__(self) -> Optional[int]:  # type: ignore
        if self._hash_cache is not None:
            return self._hash_cache
        rv = self._hash_cache = hash(tuple(self))  # type: ignore
        return rv

    def __reduce_ex__(self, protocol):
        return type(self), (list(self),)

    def __delitem__(self, key):
        _is_immutable(self)

    def __iadd__(self, other):
        _is_immutable(self)

    def __imul__(self, other):
        _is_immutable(self)

    def __setitem__(self, key, value):
        _is_immutable(self)

    def append(self, item):
        _is_immutable(self)

    def remove(self, itme):
        _is_immutable(self)

    def extend(self, iterable):
        _is_immutable(self)

    def insert(self, pos, value):
        _is_immutable(self)

    def pop(self, index=-1):
        _is_immutable(self)

    def reverse(self):
        _is_immutable(self)

    def sort(self, cmp=None, key=None, reverse=None):
        _is_immutable(self)


class ImmutableList(ImmutableListMixin, list):  # type: ignore
    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, list.__repr__(self))


def _is_immutable(self):
    raise TypeError("%r objects are immutable" % self.__class__.__name__)
