from __future__ import annotations

import asyncio
import importlib.util
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from humalike import (
    APIResponse,
    ForeseeResponse,
    IdentityResponse,
    MemoryAskResponse,
    MemoryIngestResponse,
    MemoryRecallResponse,
    OpenThreadResponse,
    OperationStartResponse,
    PopulationResult,
    RecordEventResponse,
    RespondResponse,
    SocialLearningResponse,
    SocialObservabilityResponse,
    SubmitMessagesResponse,
    TurnTakingEvent,
    UsageSummaryResponse,
)

EXAMPLES = Path(__file__).parents[1] / "examples"
PYTHON_EXAMPLES = {
    "async_quickstart.py",
    "personas.py",
    "quickstart.py",
    "response_metadata.py",
    "social_learning.py",
    "social_memory.py",
    "social_observability.py",
    "theory_of_mind.py",
    "turn_taking.py",
}
BILLABLE_EXAMPLES = PYTHON_EXAMPLES - {
    "async_quickstart.py",
    "quickstart.py",
    "response_metadata.py",
}


def load_example(filename: str) -> ModuleType:
    path = EXAMPLES / filename
    spec = importlib.util.spec_from_file_location(f"example_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AccountStub:
    def whoami(self) -> IdentityResponse:
        return {"user_id": "test-user"}

    def usage_summary(self) -> UsageSummaryResponse:
        return {"total_calls": 4, "total_credits": 12}


class AsyncAccountStub:
    async def whoami(self) -> IdentityResponse:
        return {"user_id": "async-test-user"}

    async def usage_summary(self) -> UsageSummaryResponse:
        return {"total_calls": 5, "total_credits": 13}


class ResponseStub:
    def request_with_response(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
    ) -> APIResponse[Any]:
        assert (method, path, json) == (
            "POST",
            "/v1/turn-taking/actions/whoami",
            {},
        )
        return APIResponse(
            data={"user_id": "metadata-test-user"},
            status_code=200,
            headers={"x-request-id": "request-test"},
            request_id="request-test",
        )


class SocialLearningStub:
    def extract_profile(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        source: str | None = None,
    ) -> SocialLearningResponse:
        assert len(messages) == 5
        assert source == "humalike-python-example"
        return {"profile": {"tone": "concise"}, "prompt_block": "Keep replies concise."}


class SocialObservabilityStub:
    def analyze_transcript(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        agent_name: str,
        source: str | None = None,
        focus: str | None = None,
    ) -> SocialObservabilityResponse:
        assert len(messages) == 3
        assert agent_name == "support-agent"
        assert source and focus
        return {"health_score": 0.4, "summary": "The reply missed prior effort.", "findings": [{}]}

    def get_report(self, report_id: str) -> Any:
        raise AssertionError(f"unexpected read-back: {report_id}")


class TheoryOfMindStub:
    def foresee_reply(
        self,
        transcript: Sequence[Mapping[str, Any]],
        *,
        candidate_reply: str,
        agent_name: str = "agent",
        system_prompt: str | None = None,
        subject_name: str | None = None,
    ) -> ForeseeResponse:
        assert transcript and candidate_reply and system_prompt
        assert (agent_name, subject_name) == ("agent", "customer")
        return {
            "refined_reply": "I will own the next step.",
            "refinement_rationale": "Avoids dismissing the unresolved issue.",
            "predicted_reaction": [{"risk": "high"}],
        }


class SocialMemoryStub:
    def __init__(self) -> None:
        self.ingest_keys: list[str | None] = []

    def ingest_memory(
        self,
        scope_id: str,
        transcript: Sequence[Mapping[str, Any]],
        *,
        idempotency_key: str | None = None,
    ) -> MemoryIngestResponse:
        assert scope_id == "scope-test" and len(transcript) == 2
        self.ingest_keys.append(idempotency_key)
        return {"ingested": 2}

    def recall_memory(self, scope_id: str, message: Mapping[str, Any]) -> MemoryRecallResponse:
        assert scope_id == "scope-test" and message
        return {"context": "Ada avoids peanuts."}

    def ask_memory(self, scope_id: str, question: str) -> MemoryAskResponse:
        assert scope_id == "scope-test" and question
        return {"answer": "Ada cannot eat peanuts."}


class PersonasStub:
    def __init__(self) -> None:
        self.starts = 0

    def start_population(
        self, prompt: str, *, count: int = 1, grounding: str = "off"
    ) -> OperationStartResponse:
        assert prompt and count == 1 and grounding == "off"
        self.starts += 1
        return {"id": "operation-test", "status": "pending"}

    def get_population(self, operation_id: str) -> Any:
        raise AssertionError(f"unexpected primitive poll: {operation_id}")

    def wait_population(
        self,
        operation_id: str,
        *,
        timeout: float = 900,
        poll_interval: float = 3,
    ) -> PopulationResult:
        assert operation_id == "operation-test"
        assert (timeout, poll_interval) == (900, 2)
        return {"personas": [{"persona_id": "p1", "fields": {"name": "Ada"}}]}

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"unexpected Personas capability: {name}")


class TurnTakingStreamStub:
    def __init__(self) -> None:
        self.events = [
            TurnTakingEvent(type="attached", data={}),
            TurnTakingEvent(type="turn_taking.typing", data={"active": True}),
            TurnTakingEvent(type="turn_taking.message", data={"content": "Test reply"}),
        ]

    async def __aenter__(self) -> TurnTakingStreamStub:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def recv(self, *, timeout: float | None = None) -> TurnTakingEvent:
        assert timeout == 3
        return self.events.pop(0)


class AsyncTurnTakingStub:
    async def open_thread(
        self,
        *,
        thread_id: str | None = None,
        enable_social_signals: bool | None = None,
        signals_channel_id: str | None = None,
    ) -> OpenThreadResponse:
        assert thread_id is None and enable_social_signals is True
        assert signals_channel_id is None
        return {"thread": {"id": "thread-test"}, "realtime": {"connect_url": "wss://test.invalid"}}

    async def connect_turn_taking(self, *_: Any, **__: Any) -> TurnTakingStreamStub:
        return TurnTakingStreamStub()

    async def record_event(
        self,
        thread_id: str,
        event_type: str,
        sender: str,
        *,
        client_ts: str | None = None,
    ) -> RecordEventResponse:
        assert (thread_id, event_type, sender, client_ts) == (
            "thread-test",
            "typing_start",
            "customer",
            None,
        )
        return {"tags": []}

    async def submit_messages(
        self,
        thread_id: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        system_prompt: str | None = None,
        skip_decide: bool = False,
        retry: bool = False,
    ) -> SubmitMessagesResponse:
        assert thread_id == "thread-test" and messages and skip_decide and not retry
        return {"decision": "speak", "turn_epoch": 1, "tags": []}

    async def respond(
        self,
        thread_id: str,
        content: str,
        turn_epoch: int,
        *,
        system_prompt: str | None = None,
        agent_name: str | None = None,
        pacing: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> RespondResponse:
        assert thread_id == "thread-test" and content and turn_epoch == 1
        assert agent_name == "support-agent" and pacing and metadata
        return {"superseded": False, "scheduled": [{"id": "scheduled-test"}]}


def test_public_examples_are_real_client_entrypoints() -> None:
    assert {path.name for path in EXAMPLES.glob("*.py")} == PYTHON_EXAMPLES
    for path in EXAMPLES.glob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        assert "mocktransport" not in source
        assert "fixture" not in source
        assert "fake" not in source
        assert ".from_env(" in source


@pytest.mark.parametrize("filename", sorted(BILLABLE_EXAMPLES))
def test_stateful_or_billable_examples_require_explicit_gate(filename: str) -> None:
    module = load_example(filename)
    with pytest.raises(SystemExit, match="2"):
        module.main([])


def test_account_and_metadata_examples(capsys: pytest.CaptureFixture[str]) -> None:
    load_example("quickstart.py").run(AccountStub())
    asyncio.run(load_example("async_quickstart.py").run(AsyncAccountStub()))
    load_example("response_metadata.py").run(ResponseStub())
    output = capsys.readouterr().out
    assert output.count("authenticated: True") == 3
    assert "credits used (30 days): 12" in output
    assert "credits used (30 days): 13" in output
    assert "request id: request-test" in output


def test_behavioral_api_examples(capsys: pytest.CaptureFixture[str]) -> None:
    load_example("social_learning.py").run(SocialLearningStub())
    load_example("social_observability.py").run(SocialObservabilityStub())
    load_example("theory_of_mind.py").run(TheoryOfMindStub())
    output = capsys.readouterr().out
    assert "Keep replies concise." in output
    assert "health score: 0.4" in output
    assert "predicted risk: high" in output


def test_social_memory_example_reuses_one_idempotency_key(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = SocialMemoryStub()
    load_example("social_memory.py").run(client, scope_id="scope-test")
    assert len(client.ingest_keys) == 2
    assert client.ingest_keys[0] == client.ingest_keys[1]
    assert "idempotent replay matched: True" in capsys.readouterr().out


def test_personas_example_can_start_or_resume(capsys: pytest.CaptureFixture[str]) -> None:
    module = load_example("personas.py")
    client = PersonasStub()
    module.run(client)
    assert client.starts == 1
    module.run(client, operation_id="operation-test")
    assert client.starts == 1
    output = capsys.readouterr().out
    assert "operation id (save this to resume): operation-test" in output
    assert "generated personas: 1" in output


def test_personas_example_rejects_non_positive_timeout() -> None:
    module = load_example("personas.py")
    with pytest.raises(SystemExit, match="2"):
        module.main(["--operation-id", "operation-test", "--timeout", "0"])


def test_turn_taking_example_consumes_real_event_shapes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    asyncio.run(load_example("turn_taking.py").run(AsyncTurnTakingStub(), receive_timeout=3))
    output = capsys.readouterr().out
    assert "message 1: Test reply" in output
    assert "event tags: []" in output
    assert "scheduled messages: 1" in output
