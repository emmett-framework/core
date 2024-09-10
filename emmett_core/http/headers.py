import re

from ..datastructures import ImmutableList


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


class LanguageAccept(Accept):
    regex_locale_delim = re.compile(r"[_-]")

    def _value_matches(self, value, item):
        def _normalize(language):
            return self.regex_locale_delim.split(language.lower())[0]

        return item == "*" or _normalize(value) == _normalize(item)
