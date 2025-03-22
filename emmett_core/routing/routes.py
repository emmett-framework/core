import re

from .cache import (
    CacheCloseDispatcher,
    CacheDispatcher,
    CacheFlowDispatcher,
    CacheOpenDispatcher,
)
from .dispatchers import (
    Dispatcher,
    RequestCloseDispatcher,
    RequestDispatcher,
    RequestFlowDispatcher,
    RequestOpenDispatcher,
    WSCloseDispatcher,
    WSFlowDispatcher,
    WSOpenDispatcher,
)


REGEX_INT = re.compile(r"<int\:(\w+)>")
REGEX_STR = re.compile(r"<str\:(\w+)>")
REGEX_ANY = re.compile(r"<any\:(\w+)>")
REGEX_ALPHA = re.compile(r"<alpha\:(\w+)>")
REGEX_DATE = re.compile(r"<date\:(\w+)>")
REGEX_FLOAT = re.compile(r"<float\:(\w+)>")


class Route:
    __slots__ = [
        "f",
        "hostname",
        "is_static",
        "name",
        "path",
        "pipeline_flow_close",
        "pipeline_flow_open",
        "schemes",
        "_argtypes",
    ]
    _re_condl = re.compile(r"\(.*\)\?")
    _re_param = re.compile(r"<(\w+)\:(\w+)>")

    def __init__(self, rule, path, idx):
        self.name = rule.name if idx == 0 else f"{rule.name}.{idx}"
        self.f = rule.f
        if not path.startswith("/"):
            path = "/" + path
        if rule.prefix:
            path = (path != "/" and rule.prefix + path) or rule.prefix
        self.path = path
        self.schemes = tuple(rule.schemes)
        self.hostname = rule.hostname
        self.pipeline_flow_open = rule.pipeline_flow_open
        self.pipeline_flow_close = rule.pipeline_flow_close
        self._init_match_type()
        self._build_argtmap()

    def _init_match_type(self):
        if self._re_condl.findall(self.path) or self._re_param.findall(self.path):
            self.is_static = False
        else:
            self.is_static = True

    def _build_argtmap(self):
        types = {"int", "float", "date"}
        tmap = {}
        for argtype in types:
            for arg in set(re.compile(r"<{}\:(\w+)>".format(argtype)).findall(self.path)):
                tmap[arg] = argtype
        self._argtypes = tmap

    @staticmethod
    def build_regex(path):
        path = REGEX_INT.sub(r"(?P<\g<1>>\\d+)", path)
        path = REGEX_STR.sub(r"(?P<\g<1>>[^/]+)", path)
        path = REGEX_ANY.sub(r"(?P<\g<1>>.*)", path)
        path = REGEX_ALPHA.sub(r"(?P<\g<1>>[^/\\W\\d_]+)", path)
        path = REGEX_DATE.sub(r"(?P<\g<1>>\\d{4}-\\d{2}-\\d{2})", path)
        path = REGEX_FLOAT.sub(r"(?P<\g<1>>\\d+\.\\d+)", path)
        return f"^{path}$"


class HTTPRoute(Route):
    __slots__ = ["methods", "pipeline_flow_stream", "dispatchers"]

    def __init__(self, rule, path, idx):
        super().__init__(rule, path, idx)
        self.methods = tuple(method.upper() for method in rule.methods)
        self.pipeline_flow_stream = rule.pipeline_flow_stream
        dispatchers = {
            "base": (RequestDispatcher, CacheDispatcher),
            "open": (RequestOpenDispatcher, CacheOpenDispatcher),
            "close": (RequestCloseDispatcher, CacheCloseDispatcher),
            "flow": (RequestFlowDispatcher, CacheFlowDispatcher),
        }
        if self.pipeline_flow_open and self.pipeline_flow_close:
            dispatcher, cdispatcher = dispatchers["flow"]
        elif self.pipeline_flow_open and not self.pipeline_flow_close:
            dispatcher, cdispatcher = dispatchers["open"]
        elif not self.pipeline_flow_open and self.pipeline_flow_close:
            dispatcher, cdispatcher = dispatchers["close"]
        else:
            dispatcher, cdispatcher = dispatchers["base"]
        self.dispatchers = {}
        for method in self.methods:
            dispatcher_cls = cdispatcher if rule.cache_rule and method in ["HEAD", "GET"] else dispatcher
            self.dispatchers[method] = dispatcher_cls(
                self, rule, rule.head_builder if method == "HEAD" else rule.response_builder
            )


class WebsocketRoute(Route):
    __slots__ = ["pipeline_flow_receive", "pipeline_flow_send", "dispatcher"]

    def __init__(self, rule, path, idx):
        super().__init__(rule, path, idx)
        self.pipeline_flow_receive = rule.pipeline_flow_receive
        self.pipeline_flow_send = rule.pipeline_flow_send
        dispatchers = {
            "base": Dispatcher,
            "open": WSOpenDispatcher,
            "close": WSCloseDispatcher,
            "flow": WSFlowDispatcher,
        }
        if self.pipeline_flow_open and self.pipeline_flow_close:
            dispatcher = dispatchers["flow"]
        elif self.pipeline_flow_open and not self.pipeline_flow_close:
            dispatcher = dispatchers["open"]
        elif not self.pipeline_flow_open and self.pipeline_flow_close:
            dispatcher = dispatchers["close"]
        else:
            dispatcher = dispatchers["base"]
        self.dispatcher = dispatcher(self)
