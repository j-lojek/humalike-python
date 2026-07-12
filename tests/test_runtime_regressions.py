from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from humalike import (
    APIConnectionError,
    AsyncHumalikeClient,
    HumalikeClient,
    ProtocolError,
    TurnTakingStream,
)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ([], "non-object response envelope"),
        (
            {"id": "operation-1", "status": "succeeded", "result": []},
            "did not contain object field 'result'",
        ),
    ],
)
def test_sync_polling_rejects_non_object_contract_values(
    make_client: Callable[..., HumalikeClient],
    body: Any,
    message: str,
) -> None:
    client = make_client(lambda _: httpx.Response(200, json=body))

    with pytest.raises(ProtocolError, match=message):
        client.wait_population("operation-1")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("not-an-envelope", "non-object response envelope"),
        (
            {"id": "operation-1", "status": "succeeded", "result": 42},
            "did not contain object field 'result'",
        ),
    ],
)
def test_async_polling_rejects_non_object_contract_values(body: Any, message: str) -> None:
    async def scenario() -> None:
        client = AsyncHumalikeClient(
            "fixture-token",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
        )
        try:
            with pytest.raises(ProtocolError, match=message):
                await client.wait_population("operation-1")
        finally:
            await client.close()

    asyncio.run(scenario())


def test_sync_open_thread_rejects_explicitly_disabled_signals_channel(
    make_client: Callable[..., HumalikeClient],
) -> None:
    requests = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, json={})

    client = make_client(handler)

    with pytest.raises(ValueError, match="enable_social_signals is False"):
        client.open_thread(
            enable_social_signals=False,
            signals_channel_id="community-room",
        )

    assert requests == 0


def test_async_open_thread_rejects_explicitly_disabled_signals_channel() -> None:
    requests = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, json={})

    async def scenario() -> None:
        client = AsyncHumalikeClient(
            "fixture-token",
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(ValueError, match="enable_social_signals is False"):
                await client.open_thread(
                    enable_social_signals=False,
                    signals_channel_id="community-room",
                )
        finally:
            await client.close()

    asyncio.run(scenario())
    assert requests == 0


class ClosingConnection:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.closed = False

    async def recv(self) -> str:
        self.closed = True
        raise self.error

    async def close(self) -> None:
        self.closed = True


def test_async_iteration_ends_on_websockets_normal_close() -> None:
    async def scenario() -> None:
        connection = ClosingConnection(ConnectionClosedOK(None, None))
        stream = TurnTakingStream(connection)

        events = [event async for event in stream]

        assert events == []
        assert connection.closed
        assert "closed" in repr(stream)
        with pytest.raises(StopAsyncIteration):
            await anext(stream)

    asyncio.run(scenario())


def test_async_iteration_preserves_abnormal_websocket_close_error() -> None:
    async def scenario() -> None:
        connection_error = ConnectionClosedError(None, None)
        stream = TurnTakingStream(ClosingConnection(connection_error))

        with pytest.raises(APIConnectionError) as raised:
            await anext(stream)

        assert raised.value.__cause__ is connection_error
        await stream.close()

    asyncio.run(scenario())
