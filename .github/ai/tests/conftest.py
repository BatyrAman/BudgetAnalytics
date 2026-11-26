"""Shared test configuration: every orchestrator test runs offline."""

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import NoReturn

import pytest


class NetworkAccessError(RuntimeError):
    pass


def _blocked(*_args: object, **_kwargs: object) -> NoReturn:
    raise NetworkAccessError("network access is not allowed in orchestrator tests")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail any test that tries to resolve a host or open a network connection."""

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    yield
