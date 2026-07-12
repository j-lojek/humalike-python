from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from humalike import AsyncHumalikeClient, HumalikeClient, ProtocolError


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"status": "pending"}, "field 'id'"),
        ({"id": "operation-1"}, "field 'status'"),
        ({"id": "operation-1", "status": "queued"}, "undocumented status"),
        ({"id": "  ", "status": "pending"}, "field 'id'"),
    ],
)
def test_sync_operation_start_validates_stable_envelope(
    make_client: Callable[..., HumalikeClient],
    body: dict[str, Any],
    message: str,
) -> None:
    client = make_client(lambda _: httpx.Response(200, json=body))

    with pytest.raises(ProtocolError, match=message):
        client.start_population("A small customer cohort")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"status": "running"}, "field 'id'"),
        ({"id": "operation-1"}, "field 'status'"),
        ({"id": "operation-1", "status": "queued"}, "undocumented status"),
    ],
)
def test_sync_operation_read_back_validates_stable_envelope(
    make_client: Callable[..., HumalikeClient],
    body: dict[str, Any],
    message: str,
) -> None:
    client = make_client(lambda _: httpx.Response(200, json=body))

    with pytest.raises(ProtocolError, match=message):
        client.get_population("operation-1")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"turn_epoch": 1, "tags": []}, "field 'decision'"),
        (
            {"decision": "maybe", "turn_epoch": 1, "tags": []},
            "field 'decision'",
        ),
        (
            {"decision": "speak", "turn_epoch": True, "tags": []},
            "field 'turn_epoch'",
        ),
        (
            {"decision": "stay_silent", "turn_epoch": 1, "tags": "quiet"},
            "field 'tags'",
        ),
        (
            {"decision": "speak", "turn_epoch": 1, "tags": ["ok", 2]},
            "field 'tags'",
        ),
    ],
)
def test_sync_submit_validates_documented_decision_envelope(
    make_client: Callable[..., HumalikeClient],
    body: dict[str, Any],
    message: str,
) -> None:
    client = make_client(lambda _: httpx.Response(200, json=body))

    with pytest.raises(ProtocolError, match=message):
        client.submit_messages(
            "thread-1",
            [{"sender": "Marta", "content": "Hello"}],
        )


def test_sync_stable_response_validation_preserves_forward_fields(
    make_client: Callable[..., HumalikeClient],
) -> None:
    body = {
        "decision": "stay_silent",
        "turn_epoch": 7,
        "tags": ["observed"],
        "future_field": {"kept": True},
    }
    client = make_client(lambda _: httpx.Response(200, json=body))

    response = client.submit_messages(
        "thread-1",
        [{"sender": "Marta", "content": "Hello"}],
    )

    assert response == body


def test_async_stable_response_envelopes_are_validated() -> None:
    responses = iter(
        [
            {"id": "operation-1", "status": "queued"},
            {"id": "operation-1"},
            {"decision": "speak", "turn_epoch": 1},
        ]
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    async def scenario() -> None:
        client = AsyncHumalikeClient(
            "fixture-token",
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(ProtocolError, match="undocumented status"):
                await client.start_population("A small customer cohort")
            with pytest.raises(ProtocolError, match="field 'status'"):
                await client.get_population("operation-1")
            with pytest.raises(ProtocolError, match="field 'tags'"):
                await client.submit_messages(
                    "thread-1",
                    [{"sender": "Marta", "content": "Hello"}],
                )
        finally:
            await client.close()

    asyncio.run(scenario())
