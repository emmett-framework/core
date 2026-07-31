import os

import pytest

from emmett_core._emmett_core import MultiPartReader


@pytest.mark.skipif(bool(os.getenv("PGO_RUN")), reason="PGO build")
def test_multipart_mixed_segmented():
    data = (
        # data
        b"--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\n"
        b'Content-Disposition: form-data; name="field0"\r\n\r\n'
        b"value0\r\n"
        # file
        b"--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\n"
        b'Content-Disposition: form-data; name="file"; filename="file.txt"\r\n'
        b"Content-Type: text/plain\r\n\r\n"
        b"<file content>\r\n"
        # data
        b"--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\n"
        b'Content-Disposition: form-data; name="field1"\r\n\r\n'
        b"value1\r\n"
        b"--a7f7ac8d4e2e437c877bb7b8d7cc549c--\r\n"
    )

    parser = MultiPartReader("multipart/form-data; boundary=a7f7ac8d4e2e437c877bb7b8d7cc549c")
    parser.parse(data[:37])

    idx = 37
    while True:
        segment = data[idx : idx + 1]
        if not segment:
            break
        parser.parse(segment)
        idx += 1
    parsed = list(parser.contents())
    assert (parsed[0][0], parsed[0][2]) == ("field0", b"value0")
    assert (parsed[2][0], parsed[2][2]) == ("field1", b"value1")
    assert (parsed[1][0], parsed[1][2].filename, parsed[1][2].read()) == ("file", "file.txt", b"<file content>")


def test_multipart_mixed_chunked():
    data = (
        # data
        b"--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\n"
        b'Content-Disposition: form-data; name="field0"\r\n\r\n'
        b"value0\r\n"
        # file
        b"--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\n"
        b'Content-Disposition: form-data; name="file"; filename="file.txt"\r\n'
        b"Content-Type: text/plain\r\n\r\n"
        b"<file content>\r\n"
        # data
        b"--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\n"
        b'Content-Disposition: form-data; name="field1"\r\n\r\n'
        b"value1\r\n"
        b"--a7f7ac8d4e2e437c877bb7b8d7cc549c--\r\n"
    )

    step = 97

    parser = MultiPartReader("multipart/form-data; boundary=a7f7ac8d4e2e437c877bb7b8d7cc549c")
    parser.parse(data[:step])

    idx = 1
    while True:
        segment = data[idx * step : (idx + 1) * step]
        if not segment:
            break
        parser.parse(segment)
        idx += 1
    parsed = list(parser.contents())
    assert (parsed[0][0], parsed[0][2]) == ("field0", b"value0")
    assert (parsed[2][0], parsed[2][2]) == ("field1", b"value1")
    assert (parsed[1][0], parsed[1][2].filename, parsed[1][2].read()) == ("file", "file.txt", b"<file content>")


_BODY = (
    # data
    b"--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\n"
    b'Content-Disposition: form-data; name="field0"\r\n\r\n'
    b"value0\r\n"
    # file
    b"--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\n"
    b'Content-Disposition: form-data; name="file"; filename="file.txt"\r\n'
    b"Content-Type: text/plain\r\n\r\n"
    b"<file content>\r\n"
    b"--a7f7ac8d4e2e437c877bb7b8d7cc549c--\r\n"
)
_CONTENT_TYPE = "multipart/form-data; boundary=a7f7ac8d4e2e437c877bb7b8d7cc549c"


def _parse_chunked(data, chunksize):
    parser = MultiPartReader(_CONTENT_TYPE)
    for idx in range(0, len(data), chunksize):
        parser.parse(data[idx : idx + chunksize])
    return [(name, val.read() if is_file else val) for name, is_file, val in parser.contents()]


def _assert_body_contents(parsed):
    assert parsed == [("field0", b"value0"), ("file", b"<file content>")]


def test_multipart_preamble_epilogue_junk():
    #: junk before the first and after the last boundary is allowed and gets ignored
    junk = b"This preamble should be ignored.\r\n" * 8192
    data = junk + b"\r\n" + _BODY + junk
    for chunksize in (13, 1024, 65536):
        _assert_body_contents(_parse_chunked(data, chunksize))


def test_multipart_first_boundary_across_chunks():
    #: the first boundary might not be fully contained in the first parsed chunk
    for chunksize in (1, 7, 16):
        _assert_body_contents(_parse_chunked(_BODY, chunksize))


def test_multipart_first_chunk_ending_at_boundary():
    #: first chunk ends exactly at the boundary, before any line terminator
    parser = MultiPartReader(_CONTENT_TYPE)
    split = len(b"--a7f7ac8d4e2e437c877bb7b8d7cc549c")
    parser.parse(_BODY[:split])
    parser.parse(_BODY[split:])
    _assert_body_contents([(name, val.read() if is_file else val) for name, is_file, val in parser.contents()])


def test_multipart_empty_form():
    parser = MultiPartReader(_CONTENT_TYPE)
    parser.parse(b"--a7f7ac8d4e2e437c877bb7b8d7cc549c--\r\n")
    assert list(parser.contents()) == []


def test_multipart_missing_boundary():
    parser = MultiPartReader(_CONTENT_TYPE)
    for _ in range(4):
        parser.parse(b"no boundary anywhere in this stream " * 1024)
    with pytest.raises(RuntimeError):
        parser.contents()
