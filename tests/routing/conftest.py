import pytest

from emmett_core.datastructures import sdict


@pytest.fixture(scope="module")
def app():
    return sdict(
        root_path="",
        languages=["en", "it"],
        language_default="en",
        language_force_on_url=True,
        send_signal=lambda *a, **k: None,
        config=sdict(
            hostname_default=None,
            static_version=None,
            static_version_urls=False,
        ),
    )
