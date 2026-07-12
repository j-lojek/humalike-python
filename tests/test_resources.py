from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from humalike import HumalikeClient


class Recorder:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path in {
            "/v1/personas/actions/generate",
            "/v1/personas/actions/enhance",
            "/v1/personas/actions/validate",
        }:
            return httpx.Response(200, json={"id": "operation-1", "status": "pending"})
        if request.url.path == "/v1/turn-taking/actions/submit_messages":
            return httpx.Response(
                200,
                json={"decision": "stay_silent", "turn_epoch": 1, "tags": []},
            )
        return httpx.Response(200, json={"ok": True})

    def last(self) -> tuple[str, dict[str, Any], httpx.Headers]:
        request = self.requests[-1]
        return request.url.path, json.loads(request.content), request.headers


def test_learning_observability_and_theory_of_mind_payloads(
    make_client: Callable[..., HumalikeClient],
) -> None:
    recorder = Recorder()
    client = make_client(recorder)
    messages = [{"id": "m1", "speaker": "ada", "text": "yo"}]

    client.extract_profile(messages, source="discord")
    assert recorder.last()[0:2] == (
        "/v1/social-learning/actions/extract",
        {"transcript": {"messages": messages, "source": "discord"}},
    )

    client.analyze_transcript(messages, agent_name="huma", focus="retention")
    assert recorder.last()[0:2] == (
        "/v1/social-observability/actions/analyze",
        {
            "transcript": {"messages": messages},
            "agent_name": "huma",
            "focus": "retention",
        },
    )

    turns = [{"speaker": "customer", "text": "never mind"}]
    client.foresee_reply(
        turns,
        candidate_reply="ok",
        system_prompt="be warm",
        subject_name="customer",
    )
    assert recorder.last()[0:2] == (
        "/v1/foresee/actions/foresee",
        {
            "transcript": turns,
            "candidate_reply": "ok",
            "agent_name": "agent",
            "system_prompt": "be warm",
            "subject_name": "customer",
        },
    )


def test_social_memory_payloads_and_idempotency(
    make_client: Callable[..., HumalikeClient],
) -> None:
    recorder = Recorder()
    client = make_client(recorder)
    turns = [{"speaker": "alice", "text": "no peanuts"}]

    client.ingest_memory("room:42", turns, idempotency_key="idem-1")
    path, body, headers = recorder.last()
    assert path == "/v1/social-memory/actions/ingest"
    assert body == {"scope_id": "room:42", "transcript": turns}
    assert headers["idempotency-key"] == "idem-1"

    client.recall_memory("room:42", {"speaker": "bob", "text": "lunch?"})
    assert recorder.last()[0:2] == (
        "/v1/social-memory/actions/recall",
        {"scope_id": "room:42", "message": {"speaker": "bob", "text": "lunch?"}},
    )

    client.ask_memory("room:42", "what is Alice allergic to?")
    assert recorder.last()[0:2] == (
        "/v1/social-memory/actions/ask",
        {"scope_id": "room:42", "question": "what is Alice allergic to?"},
    )


def test_persona_operation_payloads(
    make_client: Callable[..., HumalikeClient],
) -> None:
    recorder = Recorder()
    client = make_client(recorder)

    client.start_population("five indie game players", count=5, grounding="web")
    assert recorder.last()[0:2] == (
        "/v1/personas/actions/generate",
        {"prompt": "five indie game players", "count": 5, "grounding": "web"},
    )

    client.start_enhancement("Sam, 30, support main")
    assert recorder.last()[0:2] == (
        "/v1/personas/actions/enhance",
        {"persona": "Sam, 30, support main", "grounding": "off"},
    )

    personas = [{"persona_id": "p1", "fields": {"name": "Sam"}}]
    client.start_validation(personas)
    assert recorder.last()[0:2] == (
        "/v1/personas/actions/validate",
        {"personas": personas},
    )


def test_turn_taking_payloads(
    make_client: Callable[..., HumalikeClient],
) -> None:
    recorder = Recorder()
    client = make_client(recorder)

    client.open_thread(enable_social_signals=True, signals_channel_id="discord:1")
    assert recorder.last()[0:2] == (
        "/v1/turn-taking/actions/open_thread",
        {"integrations": {"social_signals": {"channel_id": "discord:1"}}},
    )

    client.open_thread(enable_social_signals=False)
    assert recorder.last()[0:2] == (
        "/v1/turn-taking/actions/open_thread",
        {},
    )

    inbound = [{"sender": "casey", "content": "anyone?"}]
    client.submit_messages("thread-1", inbound, system_prompt="join only if useful")
    assert recorder.last()[0:2] == (
        "/v1/turn-taking/actions/submit_messages",
        {
            "thread_id": "thread-1",
            "messages": inbound,
            "system_prompt": "join only if useful",
            "skip_decide": False,
        },
    )

    client.record_event("thread-1", "typing_start", "casey", client_ts="2026-01-01Z")
    assert recorder.last()[0:2] == (
        "/v1/turn-taking/actions/record_event",
        {
            "thread_id": "thread-1",
            "type": "typing_start",
            "sender": "casey",
            "client_ts": "2026-01-01Z",
        },
    )

    client.respond(
        "thread-1",
        "I can help",
        7,
        pacing={"typing_wpm": 320},
        metadata={"reply_to": "m1"},
    )
    assert recorder.last()[0:2] == (
        "/v1/turn-taking/actions/respond",
        {
            "thread_id": "thread-1",
            "content": "I can help",
            "turn_epoch": 7,
            "pacing": {"typing_wpm": 320},
            "metadata": {"reply_to": "m1"},
        },
    )
