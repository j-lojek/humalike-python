from __future__ import annotations

import sys
from typing import Any, get_args, get_origin, get_type_hints

if sys.version_info >= (3, 11):
    from typing import NotRequired
else:  # pragma: no cover - exercised by the Python 3.10 CI job
    from typing_extensions import NotRequired

from humalike import (
    JSON,
    EnhancementResult,
    ForeseeResponse,
    GroundingLevel,
    IdentityResponse,
    MemoryAskResponse,
    MemoryIngestResponse,
    MemoryRecallResponse,
    OpenThreadResponse,
    OperationEnvelope,
    OperationProgress,
    OperationStartResponse,
    OperationStatus,
    PacingOverrides,
    PopulationResult,
    RealtimeGrant,
    RecordEventResponse,
    RecordEventType,
    RespondResponse,
    ScheduledMessage,
    SocialLearningResponse,
    SocialObservabilityResponse,
    StoredReportResponse,
    SubmitMessagesResponse,
    ThreadResource,
    TranscriptMessage,
    TurnDecision,
    TurnTakingEventDict,
    UsageComponent,
    UsageDay,
    UsageSummaryResponse,
    ValidationResult,
)


def _assert_typed_dict_keys(
    model: Any,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    assert set(model.__required_keys__) == required, model.__name__
    assert set(model.__optional_keys__) == optional, model.__name__
    assert set(model.__annotations__) == required | optional, model.__name__


def _unwrap_not_required(annotation: Any) -> Any:
    """Normalize a Python 3.10 typing_extensions introspection difference."""

    if get_origin(annotation) is NotRequired:
        return get_args(annotation)[0]
    return annotation


def test_success_response_fields_are_required() -> None:
    required_only = [
        (IdentityResponse, {"user_id"}),
        (UsageComponent, {"component", "calls", "credits"}),
        (UsageDay, {"date", "requests"}),
        (
            UsageSummaryResponse,
            {"total_calls", "total_credits", "per_component", "daily_series"},
        ),
        (SocialLearningResponse, {"profile", "prompt_block"}),
        (
            SocialObservabilityResponse,
            {
                "health_score",
                "summary",
                "interactions",
                "interaction_totals",
                "per_user",
                "findings",
            },
        ),
        (StoredReportResponse, {"agent_name", "health_score", "report"}),
        (
            ForeseeResponse,
            {
                "refined_reply",
                "refinement_rationale",
                "mental_state",
                "predicted_reaction",
            },
        ),
        (MemoryIngestResponse, {"ingested"}),
        (MemoryRecallResponse, {"context"}),
        (MemoryAskResponse, {"answer"}),
        (OperationStartResponse, {"id", "status"}),
        (OperationProgress, {"produced", "total"}),
        (
            EnhancementResult,
            {"persona_id", "fields", "system_prompt", "markdown"},
        ),
        (RealtimeGrant, {"connect_url", "expires_at"}),
        (ThreadResource, {"id", "user_id", "created_at", "updated_at"}),
        (OpenThreadResponse, {"thread", "channel", "realtime"}),
        (SubmitMessagesResponse, {"decision", "turn_epoch", "tags"}),
        (RecordEventResponse, {"tags"}),
        (
            ScheduledMessage,
            {"id", "thread_id", "content", "position", "deliver_at", "status"},
        ),
        (RespondResponse, {"superseded", "scheduled"}),
    ]

    for model, required in required_only:
        _assert_typed_dict_keys(model, required=required)


def test_only_contractually_conditional_fields_are_optional() -> None:
    _assert_typed_dict_keys(
        OperationEnvelope,
        required={"id", "status"},
        optional={"source", "grounding", "progress", "result", "persona", "error"},
    )
    _assert_typed_dict_keys(
        PopulationResult,
        required={"personas", "blueprint"},
        optional={"diversity", "marginals"},
    )
    _assert_typed_dict_keys(
        ValidationResult,
        required={"passed", "gates", "scorecards"},
        optional={"diversity", "marginals"},
    )
    _assert_typed_dict_keys(
        TranscriptMessage,
        required=set(),
        optional={
            "id",
            "user_id",
            "speaker",
            "text",
            "channel",
            "timestamp",
            "reply_to",
            "sender",
            "content",
            "client_ts",
            "has_media",
        },
    )
    _assert_typed_dict_keys(
        PacingOverrides,
        required=set(),
        optional={"typing_wpm", "reading_delay_ms", "max_typing_ms"},
    )
    _assert_typed_dict_keys(
        TurnTakingEventDict,
        required={"type", "channel"},
        optional={"data", "id", "ts", "server_time"},
    )


def test_nested_and_conditional_contract_types() -> None:
    assert get_type_hints(StoredReportResponse)["report"] == SocialObservabilityResponse

    operation = get_type_hints(OperationEnvelope)
    assert operation["status"] == OperationStatus
    assert _unwrap_not_required(operation["grounding"]) == GroundingLevel
    assert _unwrap_not_required(operation["persona"]) == JSON | None
    assert _unwrap_not_required(operation["error"]) == str | None

    assert _unwrap_not_required(get_type_hints(PopulationResult)["marginals"]) == list[JSON]
    validation = get_type_hints(ValidationResult)
    assert validation["gates"] == list[JSON]
    assert validation["scorecards"] == list[JSON]
    assert _unwrap_not_required(validation["marginals"]) == list[JSON]

    assert get_type_hints(OperationStartResponse)["status"] == OperationStatus
    assert get_type_hints(SubmitMessagesResponse)["decision"] == TurnDecision


def test_public_literal_aliases_match_the_documented_values() -> None:
    assert set(get_args(GroundingLevel)) == {"off", "web", "research"}
    assert set(get_args(OperationStatus)) == {"pending", "running", "succeeded", "failed"}
    assert set(get_args(RecordEventType)) == {
        "typing_start",
        "typing_stop",
        "message_edited",
    }
    assert set(get_args(TurnDecision)) == {"speak", "stay_silent"}
