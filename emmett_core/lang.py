import re

from .datastructures import Accept


class LanguageAccept(Accept):
    regex_locale_delim = re.compile(r"[_-]")

    def _value_matches(self, value, item):
        def _normalize(language):
            return self.regex_locale_delim.split(language.lower())[0]

        return item == "*" or _normalize(value) == _normalize(item)
