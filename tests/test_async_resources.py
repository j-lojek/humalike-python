from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from humalike import (
    AsyncHumalikeClient,
    OperationFailedError,
    ProtocolError,
)


def test_async_client_covers_every_documented_http_route() -> None:
    seen: list[tuple[str, dict[str, Any] | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.url.path, body))
        if request.url.path in {
            "/v1/personas/actions/generate",
            "/v1/personas/actions/enhance",
            "/v1/personas/actions/validate",
        }:
            return httpx.Response(200, json={"id": "operation-1", "status": "pending"})
        if request.url.path.startswith("/v1/personas/repositories/"):
            return httpx.Response(200, json={"id": "operation-1", "status": "running"})
        if request.url.path == "/v1/turn-taking/actions/submit_messages":
            return httpx.Response(
                200,
                json={"decision": "stay_silent", "turn_epoch": 1, "tags": []},
            )
        return httpx.Response(200, json={"ok": True})

    async def scenario() -> None:
        client = AsyncHumalikeClient(
            "ak_fixture",
            transport=httpx.MockTransport(handler),
            retry_backoff=0,
        )
        messages = [{"id": "m1", "speaker": "ada", "text": "yo"}]
        turns = [{"speaker": "ada", "text": "yo"}]
        inbound = [{"sender": "ada", "content": "yo"}]
        try:
            await client.whoami()
            await client.usage_summary()
            await client.extract_profile(messages, source="fixture")
            await client.analyze_transcript(messages, agent_name="agent", focus="tone")
            await client.get_report("report id")
            await client.foresee_reply(turns, candidate_reply="okay")
            await client.ingest_memory("scope", turns, idempotency_key="stable")
            await client.recall_memory("scope", turns[0])
            await client.ask_memory("scope", "what happened?")
            await client.start_population("one fictional tester")
            await client.get_population("population id")
            await client.start_enhancement("Sam is concise")
            await client.get_enhancement("enhancement id")
            await client.start_validation([{"persona_id": "p1"}])
            await client.get_validation("evaluation id")
            await client.open_thread(
                thread_id="thread-1",
                enable_social_signals=True,
                signals_channel_id="channel-1",
            )
            await client.submit_messages("thread-1", inbound, system_prompt="be useful")
            await client.record_event(
                "thread-1", "typing_start", "ada", client_ts="2026-07-11T12:00:00Z"
            )
            await client.respond(
                "thread-1",
                "okay",
                2,
                agent_name="agent",
                pacing={"typing_wpm": 90},
                metadata={"fixture": True},
            )
        finally:
            await client.close()

    asyncio.run(scenario())

    assert [path for path, _ in seen] == [
        "/v1/turn-taking/actions/whoami",
        "/v1/credits/projections/usage-summary",
        "/v1/social-learning/actions/extract",
        "/v1/social-observability/actions/analyze",
        "/v1/social-observability/repositories/Report/by-id/report id",
        "/v1/foresee/actions/foresee",
        "/v1/social-memory/actions/ingest",
        "/v1/social-memory/actions/recall",
        "/v1/social-memory/actions/ask",
        "/v1/personas/actions/generate",
        "/v1/personas/repositories/Population/by-id/population id",
        "/v1/personas/actions/enhance",
        "/v1/personas/repositories/Enhancement/by-id/enhancement id",
        "/v1/personas/actions/validate",
        "/v1/personas/repositories/Evaluation/by-id/evaluation id",
        "/v1/turn-taking/actions/open_thread",
        "/v1/turn-taking/actions/submit_messages",
        "/v1/turn-taking/actions/record_event",
        "/v1/turn-taking/actions/respond",
    ]
    assert seen[4][1] is None
    assert seen[6][1] == {
        "scope_id": "scope",
        "transcript": [{"speaker": "ada", "text": "yo"}],
    }
    assert seen[15][1] == {
        "thread_id": "thread-1",
        "integrations": {"social_signals": {"channel_id": "channel-1"}},
    }


def test_async_operation_failures_and_unknown_status_are_stable() -> None:
    statuses = iter(
        [
            {"id": "enhance-1", "status": "failed", "error": "provider_error"},
            {"id": "validate-1", "status": "unexpected"},
        ]
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(statuses))

    async def scenario() -> None:
        client = AsyncHumalikeClient(
            "ak_fixture", transport=httpx.MockTransport(handler), retry_backoff=0
        )
        try:
            with pytest.raises(OperationFailedError, match="provider_error"):
                await client.wait_enhancement("enhance-1")
            with pytest.raises(ProtocolError, match="undocumented status"):
                await client.wait_validation("validate-1")
        finally:
            await client.close()

    asyncio.run(scenario())
