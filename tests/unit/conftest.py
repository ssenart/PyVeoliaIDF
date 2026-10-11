import socket
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest

from tests.unit.fake_site import FakeSite

LOOPBACK = ("127.0.0.1", "::1", "localhost")


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fails any unit test that tries to reach beyond the loopback: the unit tests run offline."""

    real_connect = socket.socket.connect

    def guarded_connect(self: socket.socket, address: Any) -> None:
        host = address[0] if isinstance(address, tuple) else address
        if host not in LOOPBACK:
            raise AssertionError(f"A unit test tried to reach {host}: the unit tests run offline.")
        real_connect(self, address)

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("A unit test tried to resolve a name or open an outside connection.")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", refuse)

    yield


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """The unit tests never see the credentials of the live tests, whatever the environment holds."""

    monkeypatch.delenv("VEOLIAIDF_USERNAME", raising=False)
    monkeypatch.delenv("VEOLIAIDF_PASSWORD", raising=False)


@pytest.fixture
async def site() -> AsyncIterator[FakeSite]:
    fake = FakeSite()
    await fake.start()
    try:
        yield fake
    finally:
        await fake.stop()
