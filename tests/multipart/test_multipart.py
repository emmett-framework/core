from __future__ import annotations

from pathlib import Path

import pytest

from emmett_core.serializers import Serializers


@pytest.fixture(scope="function")
def multipart_client(current, client):
    app = client.application
    json_dump = Serializers.get_for("json")

    @app.route("/", output="str")
    async def multipart():
        rv = {"params": {}, "files": {}}
        params = await current.request.body_params
        files = await current.request.files
        for key, val in params.items():
            accum = []
            if not isinstance(val, list):
                val = [val]
            for item in val:
                accum.append(item)
            rv["params"][key] = accum
        for key, val in files.items():
            accum = []
            if not isinstance(val, list):
                val = [val]
            for item in val:
                accum.append(
                    {
                        "filename": item.filename,
                        "size": item.size,
                        "content": item.read().decode("utf8"),
                        "content_type": item.content_type,
                    }
                )
            rv["files"][key] = accum
        return json_dump(rv)

    return client


@pytest.fixture(scope="function")
def multipart_save_client(current, client, tmpdir: Path):
    app = client.application

    @app.route("/", output="str")
    async def multipart():
        target = tmpdir / "save.txt"
        files = await current.request.files
        await files.test.save(str(target))
        return ""

    return client


def test_multipart_request_data(multipart_client):
    response = multipart_client.post("/", data={"some": "data"}, content_type="multipart/form-data")
    assert response.json() == {"params": {"some": ["data"]}, "files": {}}


def test_multipart_request_files(tmpdir: Path, multipart_client):
    path = tmpdir / "test.txt"
    with path.open("wb") as file:
        file.write(b"<file content>")

    with path.open("rb") as f:
        response = multipart_client.post("/", data={"test": f})
        assert response.json() == {
            "params": {},
            "files": {
                "test": [
                    {
                        "filename": str(path),
                        "size": 14,
                        "content": "<file content>",
                        "content_type": "text/plain",
                    }
                ]
            },
        }


def test_multipart_request_files_with_content_type(tmpdir: Path, multipart_client):
    path = tmpdir / "test.txt"
    with path.open("wb") as file:
        file.write(b"<file content>")

    with path.open("rb") as f:
        response = multipart_client.post("/", data={"test": (f, "test.txt", "text/plain")})
        assert response.json() == {
            "params": {},
            "files": {
                "test": [
                    {
                        "filename": "test.txt",
                        "size": 14,
                        "content": "<file content>",
                        "content_type": "text/plain",
                    }
                ]
            },
        }


def test_multipart_request_multiple_files(tmpdir: Path, multipart_client):
    path1 = tmpdir / "test1.txt"
    with path1.open("wb") as file:
        file.write(b"<file1 content>")

    path2 = tmpdir / "test2.txt"
    with path2.open("wb") as file:
        file.write(b"<file2 content>")

    with path1.open("rb") as f1, path2.open("rb") as f2:
        response = multipart_client.post(
            "/", data={"test1": (f1, "test1.txt", "text/plain"), "test2": (f2, "test2.txt", "text/plain")}
        )
        assert response.json() == {
            "params": {},
            "files": {
                "test1": [
                    {
                        "filename": "test1.txt",
                        "size": 15,
                        "content": "<file1 content>",
                        "content_type": "text/plain",
                    }
                ],
                "test2": [
                    {
                        "filename": "test2.txt",
                        "size": 15,
                        "content": "<file2 content>",
                        "content_type": "text/plain",
                    }
                ],
            },
        }


def test_multipart_multi_items(tmpdir: Path, multipart_client):
    path1 = tmpdir / "test1.txt"
    with path1.open("wb") as file:
        file.write(b"<file1 content>")

    path2 = tmpdir / "test2.txt"
    with path2.open("wb") as file:
        file.write(b"<file2 content>")

    with path1.open("rb") as f1, path2.open("rb") as f2:
        response = multipart_client.post(
            "/", data={"test1": ["abc", (f1, "test1.txt", "text/plain"), (f2, "test2.txt", "text/plain")]}
        )
        assert response.json() == {
            "params": {"test1": ["abc"]},
            "files": {
                "test1": [
                    {
                        "filename": "test1.txt",
                        "size": 15,
                        "content": "<file1 content>",
                        "content_type": "text/plain",
                    },
                    {
                        "filename": "test2.txt",
                        "size": 15,
                        "content": "<file2 content>",
                        "content_type": "text/plain",
                    },
                ]
            },
        }


def test_multipart_request_mixed_files_and_data(multipart_client):
    response = multipart_client.post(
        "/",
        data=(
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
        ),
        headers=[("content-type", "multipart/form-data; boundary=a7f7ac8d4e2e437c877bb7b8d7cc549c")],
    )
    assert response.json() == {
        "files": {
            "file": [
                {
                    "filename": "file.txt",
                    "size": 14,
                    "content": "<file content>",
                    "content_type": "text/plain",
                }
            ],
        },
        "params": {
            "field0": ["value0"],
            "field1": ["value1"],
        },
    }


def test_multipart_request_with_charset_for_filename(multipart_client):
    response = multipart_client.post(
        "/",
        data=(
            # file
            b"--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\n"
            b'Content-Disposition: form-data; name="file"; filename="\xe6\x96\x87\xe6\x9b\xb8.txt"\r\n'
            b"Content-Type: text/plain\r\n\r\n"
            b"<file content>\r\n"
            b"--a7f7ac8d4e2e437c877bb7b8d7cc549c--\r\n"
        ),
        headers=[("content-type", "multipart/form-data; charset=utf-8; boundary=a7f7ac8d4e2e437c877bb7b8d7cc549c")],
    )
    assert response.json() == {
        "params": {},
        "files": {
            "file": [
                {
                    "filename": "文書.txt",
                    "size": 14,
                    "content": "<file content>",
                    "content_type": "text/plain",
                }
            ]
        },
    }


def test_multipart_request_without_charset_for_filename(multipart_client):
    response = multipart_client.post(
        "/",
        data=(
            # file
            b"--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\n"
            b'Content-Disposition: form-data; name="file"; filename="\xe7\x94\xbb\xe5\x83\x8f.jpg"\r\n'
            b"Content-Type: image/jpeg\r\n\r\n"
            b"<file content>\r\n"
            b"--a7f7ac8d4e2e437c877bb7b8d7cc549c--\r\n"
        ),
        headers=[("content-type", "multipart/form-data; boundary=a7f7ac8d4e2e437c877bb7b8d7cc549c")],
    )
    assert response.json() == {
        "params": {},
        "files": {
            "file": [
                {
                    "filename": "画像.jpg",
                    "size": 14,
                    "content": "<file content>",
                    "content_type": "image/jpeg",
                }
            ],
        },
    }


def test_multipart_request_with_encoded_value(multipart_client):
    response = multipart_client.post(
        "/",
        data=(
            b"--20b303e711c4ab8c443184ac833ab00f\r\n"
            b"Content-Disposition: form-data; "
            b'name="value"\r\n\r\n'
            b"Transf\xc3\xa9rer\r\n"
            b"--20b303e711c4ab8c443184ac833ab00f--\r\n"
        ),
        headers=[("content-type", "multipart/form-data; charset=utf-8; boundary=20b303e711c4ab8c443184ac833ab00f")],
    )
    assert response.json() == {"params": {"value": ["Transférer"]}, "files": {}}


def test_missing_boundary_parameter(multipart_client):
    res = multipart_client.post(
        "/",
        data=(
            # file
            b'Content-Disposition: form-data; name="file"; filename="\xe6\x96\x87\xe6\x9b\xb8.txt"\r\n'
            b"Content-Type: text/plain\r\n\r\n"
            b"<file content>\r\n"
        ),
        headers=[("content-type", "multipart/form-data; charset=utf-8")],
    )
    assert res.status == 400
    assert res.data == "Invalid multipart data"


def test_missing_name_parameter_on_content_disposition(multipart_client):
    res = multipart_client.post(
        "/",
        data=(
            # data
            b'--a7f7ac8d4e2e437c877bb7b8d7cc549c\r\nContent-Disposition: form-data; ="field0"\r\n\r\nvalue0\r\n'
        ),
        headers=[("content-type", "multipart/form-data; boundary=a7f7ac8d4e2e437c877bb7b8d7cc549c")],
    )
    assert res.status == 400
    assert res.data == "Invalid multipart data"


def test_multipart_max_size_exceeds_limit(multipart_client):
    boundary = "------------------------4K1ON9fZkj9uCUmqLHRbbR"
    multipart_data = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="small"\r\n\r\n'
        "small content\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="large"\r\n\r\n'
        + ("x" * 1024 * 1024 + "x")  # 1MB + 1 byte of data
        + "\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    res = multipart_client.post(
        "/",
        data=multipart_data,
        headers=[("content-type", f"multipart/form-data; boundary={boundary}"), ("transfer-encoding", "chunked")],
    )
    assert res.status == 413
    assert res.data == "Request entity too large"


def test_multipart_request_file_save(tmpdir: Path, multipart_save_client):
    path = tmpdir / "test.txt"
    target = tmpdir / "save.txt"
    with path.open("wb") as file:
        file.write(b"<")
        for i in range(8192):
            file.write(f"{i}".zfill(5).encode("utf8"))
        file.write(b">")

    with path.open("rb") as f:
        response = multipart_save_client.post("/", data={"test": (f, "test.txt", "text/plain")})
        assert response.status == 200

    with path.open("rb") as f1, target.open("rb") as f2:
        assert f1.read() == f2.read()
