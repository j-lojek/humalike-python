from __future__ import annotations

import socket
from collections.abc import Callable, Generator
from typing import Any

import httpx
import pytest

from humalike import HumalikeClient


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Fail every external socket attempt while allowing asyncio loopback plumbing."""

    original_create_connection = socket.create_connection
    original_connect = socket.socket.connect

    def is_loopback(address: Any) -> bool:
        return (
            isinstance(address, tuple)
            and bool(address)
            and address[0] in {"127.0.0.1", "::1", "localhost"}
        )

    def guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
        if not is_loopback(address):
            raise AssertionError("tests must not open an external network connection")
        return original_create_connection(address, *args, **kwargs)

    def guarded_connect(instance: socket.socket, address: Any) -> None:
        if not is_loopback(address):
            raise AssertionError("tests must not open an external network connection")
        original_connect(instance, address)

    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    yield


@pytest.fixture
def make_client() -> Generator[
    Callable[[Callable[[httpx.Request], httpx.Response]], HumalikeClient],
    None,
    None,
]:
    clients: list[HumalikeClient] = []

    def factory(
        handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any
    ) -> HumalikeClient:
        client = HumalikeClient(
            "test-token-sync",
            transport=httpx.MockTransport(handler),
            retry_backoff=0,
            **kwargs,
        )
        clients.append(client)
        return client

    yield factory

    for client in clients:
        client.close()
