from __future__ import annotations

import os
import pkgutil
import sys
import traceback
import warnings
from types import ModuleType
from typing import Any, Generic, Optional

from .typing import T


class ProxyMixin:
    def _get_robj(self):
        raise NotImplementedError

    def __getitem__(self, key):
        return self._get_robj()[key]

    def __setitem__(self, key, value):
        self._get_robj()[key] = value

    def __delitem__(self, key):
        del self._get_robj()[key]

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_robj(), name)

    def __setattr__(self, name, value):
        setattr(self._get_robj(), name, value)

    def __delattr__(self, name):
        delattr(self._get_robj(), name)

    def __bool__(self):
        try:
            return bool(self._get_robj())
        except RuntimeError:
            return False

    def __eq__(self, obj) -> bool:
        return self._get_robj() == obj

    def __ne__(self, obj) -> bool:
        return self._get_robj() != obj

    def __call__(self, *args, **kwargs):
        return self._get_robj()(*args, **kwargs)

    def __iter__(self):
        return iter(self._get_robj())

    def __contains__(self, element):
        return element in self._get_robj()

    def __dir__(self):
        try:
            return dir(self._get_robj())
        except RuntimeError:
            return []

    @property
    def __dict__(self):
        try:
            return self._get_robj().__dict__
        except RuntimeError:
            raise AttributeError("__dict__")

    def __str__(self):
        return str(self._get_robj())

    def __repr__(self):
        try:
            obj = self._get_robj()
        except RuntimeError:
            return "<%s unbound>" % self.__class__.__name__
        return repr(obj)


class ObjectProxy(ProxyMixin, Generic[T]):
    __slots__ = ("__obj", "__name__")

    def __init__(self, obj: Any, name: str):
        object.__setattr__(self, "_ObjectProxy__obj", obj)
        object.__setattr__(self, "__name__", name)

    def _get_robj(self) -> T:
        return getattr(self.__obj, self.__name__)


class ContextVarProxy(ProxyMixin, Generic[T]):
    __slots__ = ("__obj", "__name__")

    def __init__(self, obj: Any, name: str):
        object.__setattr__(self, "_ContextVarProxy__obj", obj)
        object.__setattr__(self, "__name__", name)

    def _get_robj(self) -> T:
        return getattr(self.__obj.get(), self.__name__)


#: application loaders
def get_app_module(module_name: str, raise_on_failure: bool = True) -> Optional[ModuleType]:
    try:
        __import__(module_name)
    except ImportError:
        if sys.exc_info()[-1].tb_next:
            raise RuntimeError(
                f"While importing '{module_name}', an ImportError was raised:\n\n{traceback.format_exc()}"
            )
        elif raise_on_failure:
            raise RuntimeError(f"Could not import '{module_name}'.")
        else:
            return
    return sys.modules[module_name]


#: Given a module instance this tries to find the best possible application in the module
def find_best_app(module: ModuleType, app_cls) -> Any:
    # Search for the most common names first.
    for attr_name in ("app", "application"):
        app = getattr(module, attr_name, None)
        if isinstance(app, app_cls):
            return app

    # Otherwise find the only object that is an App instance.
    matches = [v for v in module.__dict__.values() if isinstance(v, app_cls)]

    if len(matches) == 1:
        return matches[0]
    raise RuntimeError(f"Failed to find Emmett application in module '{module.__name__}'.")


def locate_app(app_cls, module_name: str, app_name: str, raise_on_failure: bool = True) -> Any:
    module = get_app_module(module_name, raise_on_failure=raise_on_failure)
    if app_name:
        return getattr(module, app_name, None)
    return find_best_app(module, app_cls)


#: deprecation helpers
class RemovedInNextVersionWarning(DeprecationWarning):
    pass


class deprecated(object):
    def __init__(self, old_method_name, new_method_name, class_name=None, s=0):
        self.class_name = class_name
        self.old_method_name = old_method_name
        self.new_method_name = new_method_name
        self.additional_stack = s

    def __call__(self, f):
        def wrapped(*args, **kwargs):
            warn_of_deprecation(self.old_method_name, self.new_method_name, self.class_name, 3 + self.additional_stack)
            return f(*args, **kwargs)

        return wrapped


warnings.simplefilter("always", RemovedInNextVersionWarning)


def warn_of_deprecation(old_name, new_name, prefix=None, stack=2):
    msg = "%(old)s is deprecated, use %(new)s instead."
    if prefix:
        msg = "%(prefix)s." + msg
    warnings.warn(msg % {"old": old_name, "new": new_name, "prefix": prefix}, RemovedInNextVersionWarning, stack)


#: app init helpers
def get_root_path(import_name):
    """Returns the path of the package or cwd if that cannot be found."""
    # Module already imported and has a file attribute.  Use that first.
    mod = sys.modules.get(import_name)
    if mod is not None and hasattr(mod, "__file__"):
        return os.path.dirname(os.path.abspath(mod.__file__))

    # Next attempt: check the loader.
    loader = pkgutil.get_loader(import_name)

    # Loader does not exist or we're referring to an unloaded main module
    # or a main module without path (interactive sessions), go with the
    # current working directory.
    if loader is None or import_name == "__main__":
        return os.getcwd()

    # For .egg, zipimporter does not have get_filename until Python 2.7.
    # Some other loaders might exhibit the same behavior.
    if hasattr(loader, "get_filename"):
        filepath = loader.get_filename(import_name)
    else:
        # Fall back to imports.
        __import__(import_name)
        mod = sys.modules[import_name]
        filepath = getattr(mod, "__file__", None)

        # If we don't have a filepath it might be because we are a
        # namespace package.  In this case we pick the root path from the
        # first module that is contained in our package.
        if filepath is None:
            raise RuntimeError(
                "No root path can be found for the provided "
                'module "%s".  This can happen because the '
                "module came from an import hook that does "
                "not provide file name information or because "
                "it's a namespace package.  In this case "
                "the root path needs to be explicitly "
                "provided." % import_name
            )

    # filepath is import_name.py for a module, or __init__.py for a package.
    return os.path.dirname(os.path.abspath(filepath))


def create_missing_app_folders(app, folders=["static"]):
    try:
        for subfolder in folders:
            path = os.path.join(app.root_path, subfolder)
            if not os.path.exists(path):
                os.mkdir(path)
    except Exception:
        pass
