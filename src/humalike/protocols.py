"""Capability protocols for products that depend on only part of the SDK.

Applications should type against the smallest protocol they need.  This keeps
Humalike an optional behavioral enhancement: tests and graceful-degradation
paths can provide a tiny structural fake without importing an HTTP transport.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from .models import (
    EnhancementResult,
    ForeseeResponse,
    GroundingLevel,
    IdentityResponse,
    MemoryAskResponse,
    MemoryIngestResponse,
    MemoryRecallResponse,
    OpenThreadResponse,
    OperationEnvelope,
    OperationStartResponse,
    PopulationResult,
    RecordEventResponse,
    RecordEventType,
    RespondResponse,
    SocialLearningResponse,
    SocialObservabilityResponse,
    StoredReportResponse,
    SubmitMessagesResponse,
    UsageSummaryResponse,
    ValidationResult,
)
from .websocket import TurnTakingStream, WebSocketConnector


@runtime_checkable
class AccountClient(Protocol):
    def whoami(self) -> IdentityResponse: ...

    def usage_summary(self) -> UsageSummaryResponse: ...


@runtime_checkable
class SocialLearningClient(Protocol):
    def extract_profile(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        source: str | None = None,
    ) -> SocialLearningResponse: ...


@runtime_checkable
class SocialObservabilityClient(Protocol):
    def analyze_transcript(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        agent_name: str,
        source: str | None = None,
        focus: str | None = None,
    ) -> SocialObservabilityResponse: ...

    def get_report(self, report_id: str) -> StoredReportResponse | None: ...


@runtime_checkable
class TheoryOfMindClient(Protocol):
    def foresee_reply(
        self,
        transcript: Sequence[Mapping[str, Any]],
        *,
        candidate_reply: str,
        agent_name: str = "agent",
        system_prompt: str | None = None,
        subject_name: str | None = None,
    ) -> ForeseeResponse: ...


@runtime_checkable
class SocialMemoryClient(Protocol):
    def ingest_memory(
        self,
        scope_id: str,
        transcript: Sequence[Mapping[str, Any]],
        *,
        idempotency_key: str | None = None,
    ) -> MemoryIngestResponse: ...

    def recall_memory(self, scope_id: str, message: Mapping[str, Any]) -> MemoryRecallResponse: ...

    def ask_memory(self, scope_id: str, question: str) -> MemoryAskResponse: ...


@runtime_checkable
class PersonasClient(Protocol):
    def start_population(
        self, prompt: str, *, count: int = 1, grounding: GroundingLevel = "off"
    ) -> OperationStartResponse: ...

    def get_population(self, operation_id: str) -> OperationEnvelope: ...

    def wait_population(
        self,
        operation_id: str,
        *,
        timeout: float = 900.0,
        poll_interval: float = 3.0,
    ) -> PopulationResult: ...

    def start_enhancement(
        self, persona: str, *, grounding: GroundingLevel = "off"
    ) -> OperationStartResponse: ...

    def get_enhancement(self, operation_id: str) -> OperationEnvelope: ...

    def wait_enhancement(
        self,
        operation_id: str,
        *,
        timeout: float = 900.0,
        poll_interval: float = 3.0,
    ) -> EnhancementResult: ...

    def start_validation(
        self,
        personas: Sequence[Mapping[str, Any]],
        *,
        blueprint: Mapping[str, Any] | None = None,
    ) -> OperationStartResponse: ...

    def get_validation(self, operation_id: str) -> OperationEnvelope: ...

    def wait_validation(
        self,
        operation_id: str,
        *,
        timeout: float = 300.0,
        poll_interval: float = 1.0,
    ) -> ValidationResult: ...


@runtime_checkable
class TurnTakingClient(Protocol):
    def open_thread(
        self,
        *,
        thread_id: str | None = None,
        enable_social_signals: bool | None = None,
        signals_channel_id: str | None = None,
    ) -> OpenThreadResponse: ...

    def submit_messages(
        self,
        thread_id: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        system_prompt: str | None = None,
        skip_decide: bool = False,
        retry: bool = False,
    ) -> SubmitMessagesResponse: ...

    def record_event(
        self,
        thread_id: str,
        event_type: RecordEventType,
        sender: str,
        *,
        client_ts: str | None = None,
    ) -> RecordEventResponse: ...

    def respond(
        self,
        thread_id: str,
        content: str,
        turn_epoch: int,
        *,
        system_prompt: str | None = None,
        agent_name: str | None = None,
        pacing: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> RespondResponse: ...


class HumalikeClientProtocol(
    AccountClient,
    SocialLearningClient,
    SocialObservabilityClient,
    TheoryOfMindClient,
    SocialMemoryClient,
    PersonasClient,
    TurnTakingClient,
    Protocol,
):
    """Complete synchronous HTTP capability surface."""


@runtime_checkable
class AsyncAccountClient(Protocol):
    async def whoami(self) -> IdentityResponse: ...

    async def usage_summary(self) -> UsageSummaryResponse: ...


@runtime_checkable
class AsyncSocialLearningClient(Protocol):
    async def extract_profile(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        source: str | None = None,
    ) -> SocialLearningResponse: ...


@runtime_checkable
class AsyncSocialObservabilityClient(Protocol):
    async def analyze_transcript(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        agent_name: str,
        source: str | None = None,
        focus: str | None = None,
    ) -> SocialObservabilityResponse: ...

    async def get_report(self, report_id: str) -> StoredReportResponse | None: ...


@runtime_checkable
class AsyncTheoryOfMindClient(Protocol):
    async def foresee_reply(
        self,
        transcript: Sequence[Mapping[str, Any]],
        *,
        candidate_reply: str,
        agent_name: str = "agent",
        system_prompt: str | None = None,
        subject_name: str | None = None,
    ) -> ForeseeResponse: ...


@runtime_checkable
class AsyncSocialMemoryClient(Protocol):
    async def ingest_memory(
        self,
        scope_id: str,
        transcript: Sequence[Mapping[str, Any]],
        *,
        idempotency_key: str | None = None,
    ) -> MemoryIngestResponse: ...

    async def recall_memory(
        self, scope_id: str, message: Mapping[str, Any]
    ) -> MemoryRecallResponse: ...

    async def ask_memory(self, scope_id: str, question: str) -> MemoryAskResponse: ...


@runtime_checkable
class AsyncPersonasClient(Protocol):
    async def start_population(
        self, prompt: str, *, count: int = 1, grounding: GroundingLevel = "off"
    ) -> OperationStartResponse: ...

    async def get_population(self, operation_id: str) -> OperationEnvelope: ...

    async def wait_population(
        self,
        operation_id: str,
        *,
        timeout: float = 900.0,
        poll_interval: float = 3.0,
    ) -> PopulationResult: ...

    async def start_enhancement(
        self, persona: str, *, grounding: GroundingLevel = "off"
    ) -> OperationStartResponse: ...

    async def get_enhancement(self, operation_id: str) -> OperationEnvelope: ...

    async def wait_enhancement(
        self,
        operation_id: str,
        *,
        timeout: float = 900.0,
        poll_interval: float = 3.0,
    ) -> EnhancementResult: ...

    async def start_validation(
        self,
        personas: Sequence[Mapping[str, Any]],
        *,
        blueprint: Mapping[str, Any] | None = None,
    ) -> OperationStartResponse: ...

    async def get_validation(self, operation_id: str) -> OperationEnvelope: ...

    async def wait_validation(
        self,
        operation_id: str,
        *,
        timeout: float = 300.0,
        poll_interval: float = 1.0,
    ) -> ValidationResult: ...


@runtime_checkable
class AsyncTurnTakingClient(Protocol):
    async def open_thread(
        self,
        *,
        thread_id: str | None = None,
        enable_social_signals: bool | None = None,
        signals_channel_id: str | None = None,
    ) -> OpenThreadResponse: ...

    async def submit_messages(
        self,
        thread_id: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        system_prompt: str | None = None,
        skip_decide: bool = False,
        retry: bool = False,
    ) -> SubmitMessagesResponse: ...

    async def record_event(
        self,
        thread_id: str,
        event_type: RecordEventType,
        sender: str,
        *,
        client_ts: str | None = None,
    ) -> RecordEventResponse: ...

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
    ) -> RespondResponse: ...

    async def connect_turn_taking(
        self,
        grant_or_url: str | Mapping[str, Any],
        *,
        connector: WebSocketConnector | None = None,
        open_timeout: float = 10.0,
        max_size: int = 1_048_576,
    ) -> TurnTakingStream: ...


class AsyncHumalikeClientProtocol(
    AsyncAccountClient,
    AsyncSocialLearningClient,
    AsyncSocialObservabilityClient,
    AsyncTheoryOfMindClient,
    AsyncSocialMemoryClient,
    AsyncPersonasClient,
    AsyncTurnTakingClient,
    Protocol,
):
    """Complete asynchronous HTTP capability surface."""


if TYPE_CHECKING:
    from .async_client import AsyncHumalikeClient
    from .client import HumalikeClient

    def _accept_sync(value: HumalikeClientProtocol) -> None: ...

    def _accept_async(value: AsyncHumalikeClientProtocol) -> None: ...

    def _verify_concrete_clients(
        sync_client: HumalikeClient,
        async_client: AsyncHumalikeClient,
    ) -> None:
        """Static-only proof that both concrete clients satisfy their protocols."""

        _accept_sync(sync_client)
        _accept_async(async_client)
