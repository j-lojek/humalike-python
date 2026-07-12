"""Public structural types for Humalike requests and responses.

The API intentionally contains dynamic objects (most notably persona fields and
analysis reports).  These ``TypedDict`` definitions describe stable top-level
fields without discarding forward-compatible fields returned by the server.
They have no runtime validation cost and remain ordinary dictionaries.
"""

import sys
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeAlias, TypeVar

if sys.version_info >= (3, 11):
    from typing import NotRequired, TypedDict
else:  # pragma: no cover - exercised by the Python 3.10 CI job
    from typing_extensions import NotRequired, TypedDict

JSON: TypeAlias = dict[str, Any]
GroundingLevel: TypeAlias = Literal["off", "web", "research"]
OperationStatus: TypeAlias = Literal["pending", "running", "succeeded", "failed"]
RecordEventType: TypeAlias = Literal["typing_start", "typing_stop", "message_edited"]
TurnDecision: TypeAlias = Literal["speak", "stay_silent"]
T = TypeVar("T")


@dataclass(frozen=True, repr=False)
class APIResponse(Generic[T]):
    """Decoded response plus transport metadata for advanced integrations.

    Response data and headers can contain sensitive information, so ``repr``
    intentionally exposes only the status code.
    """

    data: T
    status_code: int
    headers: dict[str, str]
    request_id: str | None = None

    def __repr__(self) -> str:
        return f"APIResponse(status_code={self.status_code}, data='<redacted>')"


class TranscriptMessage(TypedDict, total=False):
    """Message shape accepted across transcript-oriented endpoints.

    Individual APIs use either ``speaker``/``text`` or ``sender``/``content``.
    The SDK preserves that documented flexibility instead of silently renaming
    identities or message content.
    """

    id: str
    user_id: str
    speaker: str
    text: str
    channel: str
    timestamp: str
    reply_to: str
    sender: str
    content: str
    client_ts: str
    has_media: bool


class IdentityResponse(TypedDict):
    user_id: str


class UsageComponent(TypedDict):
    component: str
    calls: int
    credits: int


class UsageDay(TypedDict):
    date: str
    requests: int


class UsageSummaryResponse(TypedDict):
    total_calls: int
    total_credits: int
    per_component: list[UsageComponent]
    daily_series: list[UsageDay]


class SocialLearningResponse(TypedDict):
    profile: JSON
    prompt_block: str


class SocialObservabilityResponse(TypedDict):
    health_score: float
    summary: str
    interactions: list[JSON]
    interaction_totals: list[JSON]
    per_user: list[JSON]
    findings: list[JSON]


class StoredReportResponse(TypedDict):
    """Envelope returned by the Social Observability report repository."""

    agent_name: str
    health_score: float
    report: SocialObservabilityResponse


class ForeseeResponse(TypedDict):
    refined_reply: str
    refinement_rationale: str
    mental_state: list[JSON]
    predicted_reaction: list[JSON]


class MemoryIngestResponse(TypedDict):
    ingested: int


class MemoryRecallResponse(TypedDict):
    context: str


class MemoryAskResponse(TypedDict):
    answer: str


class OperationStartResponse(TypedDict):
    id: str
    status: OperationStatus


class OperationProgress(TypedDict):
    produced: int
    total: int


class OperationEnvelope(TypedDict):
    id: str
    status: OperationStatus
    source: NotRequired[str]
    grounding: NotRequired[GroundingLevel]
    progress: NotRequired[OperationProgress]
    result: NotRequired[JSON]
    persona: NotRequired[JSON | None]
    error: NotRequired[str | None]


class PopulationResult(TypedDict):
    personas: list[JSON]
    blueprint: JSON
    diversity: NotRequired[JSON]
    marginals: NotRequired[list[JSON]]


class EnhancementResult(TypedDict):
    persona_id: str
    fields: dict[str, str]
    system_prompt: str
    markdown: str


class ValidationResult(TypedDict):
    passed: bool
    gates: list[JSON]
    scorecards: list[JSON]
    diversity: NotRequired[JSON]
    marginals: NotRequired[list[JSON]]


class RealtimeGrant(TypedDict):
    connect_url: str
    expires_at: str


class ThreadResource(TypedDict):
    id: str
    user_id: str
    created_at: str
    updated_at: str


class OpenThreadResponse(TypedDict):
    thread: ThreadResource
    channel: str
    realtime: RealtimeGrant


class SubmitMessagesResponse(TypedDict):
    decision: TurnDecision
    turn_epoch: int
    tags: list[str]


class RecordEventResponse(TypedDict):
    tags: list[str]


class ScheduledMessage(TypedDict):
    id: str
    thread_id: str
    content: str
    position: int
    deliver_at: str
    status: str


class RespondResponse(TypedDict):
    superseded: bool
    scheduled: list[ScheduledMessage]


class PacingOverrides(TypedDict, total=False):
    typing_wpm: float
    reading_delay_ms: int
    max_typing_ms: int


class TurnTakingEventDict(TypedDict):
    """Common WebSocket envelope with conditional event-specific fields.

    Documented delivery events require ``id``, ``ts`` and ``data``.  The
    observed ``attached`` event instead requires ``server_time`` and may omit
    ``id`` and ``data``.  Every accepted event requires ``type`` and ``channel``.
    """

    type: str
    channel: str
    data: NotRequired[JSON]
    id: NotRequired[str]
    ts: NotRequired[str]
    server_time: NotRequired[str]
