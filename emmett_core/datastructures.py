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


class Accept(ImmutableList):
    def __init__(self, values=()):
        if values is None:
            list.__init__(self)
            self.provided = False
        elif isinstance(values, Accept):
            self.provided = values.provided
            list.__init__(self, values)
        else:
            self.provided = True
            values = sorted(values, key=lambda x: (x[1], x[0]), reverse=True)
            list.__init__(self, values)

    def _value_matches(self, value, item):
        return item == "*" or item.lower() == value.lower()

    def __getitem__(self, key):
        if isinstance(key, str):
            return self.quality(key)
        return list.__getitem__(self, key)

    def quality(self, key):
        for item, quality in self:
            if self._value_matches(key, item):
                return quality
        return 0

    def __contains__(self, value):
        for item, _quality in self:
            if self._value_matches(value, item):
                return True
        return False

    def __repr__(self):
        return "%s([%s])" % (self.__class__.__name__, ", ".join("(%r, %s)" % (x, y) for x, y in self))

    def index(self, key):
        if isinstance(key, str):
            for idx, (item, _quality) in enumerate(self):
                if self._value_matches(key, item):
                    return idx
            raise ValueError(key)
        return list.index(self, key)

    def find(self, key):
        try:
            return self.index(key)
        except ValueError:
            return -1

    def values(self):
        for item in self:
            yield item[0]

    def to_header(self):
        result = []
        for value, quality in self:
            if quality != 1:
                value = "%s;q=%s" % (value, quality)
            result.append(value)
        return ",".join(result)

    def __str__(self):
        return self.to_header()

    def best_match(self, matches, default=None):
        best_quality = -1
        result = default
        for server_item in matches:
            for client_item, quality in self:
                if quality <= best_quality:
                    break
                if self._value_matches(server_item, client_item) and quality > 0:
                    best_quality = quality
                    result = server_item
        return result

    @property
    def best(self):
        if self:
            return self[0][0]
