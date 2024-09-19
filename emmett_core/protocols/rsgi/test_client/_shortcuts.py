def to_bytes(obj, charset="utf8", errors="strict"):
    if obj is None:
        return None
    if isinstance(obj, (bytes, bytearray, memoryview)):
        return bytes(obj)
    if isinstance(obj, str):
        return obj.encode(charset, errors)
    raise TypeError("Expected bytes")


def to_unicode(obj, charset="utf8", errors="strict"):
    if obj is None:
        return None
    if not isinstance(obj, bytes):
        return str(obj)
    return obj.decode(charset, errors)
