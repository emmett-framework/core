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
