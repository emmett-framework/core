from enum import Enum


class Signals(str, Enum):
    __str__ = lambda v: v.value

    after_loop = "after_loop"
    after_route = "after_route"
    before_route = "before_route"
    before_routes = "before_routes"
