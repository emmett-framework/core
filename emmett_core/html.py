import threading
from html import escape as _htmlescape


class TagStack(threading.local):
    def __init__(self):
        self.stack = []

    def __getitem__(self, key):
        return self.stack[key]

    def append(self, item):
        self.stack.append(item)

    def pop(self, idx):
        self.stack.pop(idx)

    def __bool__(self):
        return bool(self.stack)


class HtmlTag:
    __slots__ = ["name", "components", "attributes", "stack"]

    _rules = {
        "ul": ["li"],
        "ol": ["li"],
        "table": ["tr", "thead", "tbody"],
        "thead": ["tr"],
        "tbody": ["tr"],
        "tr": ["td", "th"],
        "select": ["option", "optgroup"],
        "optgroup": ["optionp"],
    }
    _self_closed = {"br", "col", "embed", "hr", "img", "input", "link", "meta"}

    def __init__(self, name, stack=None):
        self.name = name
        self.components = []
        self.attributes = {}
        self.stack = stack
        if stack:
            stack[-1].append(self)

    def __enter__(self):
        self.stack.append(self)
        return self

    def __exit__(self, type, value, traceback):
        self.stack.pop(-1)

    @staticmethod
    def wrap(component, rules):
        if rules and (not isinstance(component, HtmlTag) or component.name not in rules):
            return HtmlTag(rules[0])(component)
        return component

    def __call__(self, *components, **attributes):
        rules = self._rules.get(self.name, [])
        self.components = [self.wrap(comp, rules) for comp in components]
        self.attributes = attributes
        return self

    def append(self, component):
        self.components.append(component)

    def insert(self, i, component):
        self.components.insert(i, component)

    def remove(self, component):
        self.components.remove(component)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.components[key]
        return self.attributes.get(key)

    def __setitem__(self, key, value):
        if isinstance(key, int):
            self.components.insert(key, value)
        else:
            self.attributes[key] = value

    def __iter__(self):
        for item in self.components:
            yield item

    def __str__(self):
        return self.__html__()

    def __add__(self, other):
        return cat(self, other)

    def add_class(self, name):
        c = self["_class"]
        classes = (set(c.split()) if c else set()) | set(name.split())
        self["_class"] = " ".join(classes) if classes else None
        return self

    def remove_class(self, name):
        c = self["_class"]
        classes = (set(c.split()) if c else set()) - set(name.split())
        self["_class"] = " ".join(classes) if classes else None
        return self

    @classmethod
    def _build_html_attributes_items(cls, attrs, namespace=None):
        if namespace:
            for k, v in sorted(attrs.items()):
                nk = f"{namespace}-{k}"
                if v is True:
                    yield (nk, k)
                else:
                    yield (nk, htmlescape(v))
        else:
            for k, v in filter(lambda item: item[0].startswith("_") and item[1] is not None, sorted(attrs.items())):
                nk = k[1:]
                if isinstance(v, dict):
                    for item in cls._build_html_attributes_items(v, nk):
                        yield item
                elif v is True:
                    yield (nk, nk)
                else:
                    yield (nk, htmlescape(v))

    def _build_html_attributes(self):
        return " ".join(f'{k}="{v}"' for k, v in self._build_html_attributes_items(self.attributes))

    def __html__(self):
        name = self.name
        attrs = self._build_html_attributes()
        attrs = " " + attrs if attrs else ""
        if name in self._self_closed:
            return "<%s%s />" % (name, attrs)
        components = "".join(htmlescape(v) for v in self.components)
        return "<%s%s>%s</%s>" % (name, attrs, components, name)

    def __json__(self):
        return str(self)


class TreeHtmlTag(HtmlTag):
    __slots__ = ["parent"]

    def __init__(self, name, stack=None):
        self.parent = stack[-1] if stack else None
        super().__init__(name, stack=stack)

    def __call__(self, *components, **attributes):
        super().__call__(*components, **attributes)
        for component in filter(lambda c: isinstance(c, self.__class__), self.components):
            component.parent = self
        return self

    def append(self, component):
        super().append(component)
        if isinstance(component, self.__class__) and component.parent != self:
            component.parent = self

    def insert(self, i, component):
        super().insert(i, component)
        if isinstance(component, self.__class__) and component.parent != self:
            component.parent = self

    def remove(self, component):
        super().remove(component)
        if isinstance(component, self.__class__) and component.parent is self:
            component.parent = None


class MetaHtmlTag:
    __slots__ = ["_stack"]
    _tag_cls = HtmlTag

    def __init__(self, stack):
        self._stack = stack

    def __getattr__(self, name):
        return self._tag_cls(name, stack=self._stack)

    def __getitem__(self, name):
        return self._tag_cls(name, stack=self._stack)


class cat(HtmlTag):
    __slots__ = []

    def __init__(self, *components):
        self.components = list(components)
        self.attributes = {}

    def __html__(self):
        return "".join(htmlescape(v) for v in self.components)


def _to_str(obj):
    if not isinstance(obj, str):
        return str(obj)
    return obj


def htmlescape(obj):
    if hasattr(obj, "__html__"):
        return obj.__html__()
    return _htmlescape(_to_str(obj), True).replace("'", "&#39;")
