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
