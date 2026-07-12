"""Synchronous Humalike API client.

The public API deliberately stays close to the HTTP contract while adding the
production mechanics missing from copy-paste examples: retries, typed errors,
idempotency, async-operation polling, timeouts, and dependency injection for
tests.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar, cast

import httpx

from ._response_validation import (
    validate_operation_envelope,
    validate_operation_start_response,
    validate_submit_messages_response,
)
from ._transport import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    LOCAL_BACKOFF_JITTER_RATIO,
    MAX_LOCAL_BACKOFF_SECONDS,
    MAX_SERVER_RETRY_AFTER_SECONDS,
    RETRYABLE_STATUS,
    RUNNING_OPERATION_STATES,
    api_error,
    bounded_http_timeout,
    default_headers,
    merged_headers,
    path_segment,
    required_messages,
    required_object_response,
    required_text,
    retry_delay,
    retry_is_safe,
    validated_api_path,
    validated_base_url,
    validated_grounding,
    validated_header_component,
    validated_http_timeout,
    validated_idempotency_key,
    validated_max_retries,
    validated_non_negative_number,
    validated_optional_bool,
    validated_record_event_type,
    validated_submit_messages,
    validated_token,
)
from ._transport import (
    transcript as _transcript,
)
from ._transport import (
    without_none as _without_none,
)
from ._version import __version__
from .errors import (
    APIConnectionError,
    APITimeoutError,
    OperationFailedError,
    OperationTimeoutError,
    ProtocolError,
)
from .models import (
    JSON,
    APIResponse,
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

T = TypeVar("T")


class HumalikeClient:
    """Production-oriented synchronous client for every documented API family.

    ``http_client`` and ``transport`` exist primarily for frameworks and tests.
    Most callers only need ``HumalikeClient(token=...)`` or ``from_env()``.
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        retry_backoff: float = 0.25,
        retry_backoff_max: float = MAX_LOCAL_BACKOFF_SECONDS,
        retry_after_max: float = MAX_SERVER_RETRY_AFTER_SECONDS,
        retry_jitter: float = LOCAL_BACKOFF_JITTER_RATIO,
        user_agent_suffix: str | None = None,
        http_client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        token = validated_token(token)
        max_retries = validated_max_retries(max_retries)
        retry_backoff = validated_non_negative_number(
            retry_backoff,
            name="retry_backoff",
        )
        retry_backoff_max = validated_non_negative_number(
            retry_backoff_max,
            name="retry_backoff_max",
        )
        retry_after_max = validated_non_negative_number(
            retry_after_max,
            name="retry_after_max",
        )
        retry_jitter = validated_non_negative_number(
            retry_jitter,
            name="retry_jitter",
        )
        if retry_jitter > 1:
            raise ValueError("retry_jitter must be a finite number between 0 and 1")
        timeout = validated_http_timeout(timeout)
        if http_client is not None and transport is not None:
            raise ValueError("pass either http_client or transport, not both")
        base_url = validated_base_url(base_url)

        self._base_url = base_url
        self._timeout = timeout
        user_agent = f"humalike-python/{__version__}"
        if user_agent_suffix is not None:
            user_agent += " " + validated_header_component(
                user_agent_suffix, name="user_agent_suffix"
            )
        self._default_headers = default_headers(token, user_agent=user_agent)
        self._max_retries = max_retries
        self._retry_backoff: float = retry_backoff
        self._retry_backoff_max = retry_backoff_max
        self._retry_after_max = retry_after_max
        self._retry_jitter = retry_jitter
        self._sleep = sleep
        self._monotonic = monotonic
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(timeout=timeout, transport=transport)

    @classmethod
    def from_env(cls, variable: str = "HUMALIKE_TOKEN", **kwargs: Any) -> HumalikeClient:
        """Create a client from ``HUMALIKE_TOKEN`` (or a caller-selected variable)."""

        token = os.getenv(variable)
        if not token:
            raise ValueError(f"environment variable {variable!r} is not set")
        return cls(token, **kwargs)

    def __repr__(self) -> str:
        return "HumalikeClient(token='<redacted>')"

    def __enter__(self) -> HumalikeClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        retry: bool | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> Any:
        """Issue a request and return its decoded JSON data.

        See :meth:`request_with_response` when response headers or status are
        also needed.
        """

        return self.request_with_response(
            method,
            path,
            json=json,
            headers=headers,
            retry=retry,
            timeout=timeout,
        ).data

    def request_with_response(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        retry: bool | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> APIResponse[Any]:
        """Issue an authenticated request with SDK retry and error semantics.

        Retries default to safe methods, route-allowlisted read-like POSTs, and
        Social Memory ingest when it carries an idempotency key. Pass
        ``retry=True`` only when the caller has an endpoint-specific guarantee
        that replay cannot duplicate a billable operation or mutation.
        """

        return self._request_with_response(
            method,
            path,
            json=json,
            headers=headers,
            retry=retry,
            timeout=timeout,
            deadline=None,
        )

    def _request_with_response(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None,
        headers: Mapping[str, str] | None,
        retry: bool | None,
        timeout: float | httpx.Timeout | None,
        deadline: float | None,
    ) -> APIResponse[Any]:
        path = validated_api_path(path)
        request_headers = merged_headers(self._default_headers, headers)
        retry = validated_optional_bool(retry, name="retry")
        retry_allowed = retry_is_safe(method, path, request_headers) if retry is None else retry
        request_timeout = self._timeout if timeout is None else validated_http_timeout(timeout)

        for attempt in range(self._max_retries + 1):
            attempt_timeout: float | httpx.Timeout = request_timeout
            if deadline is not None:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    raise APITimeoutError(f"{method.upper()} request deadline")
                attempt_timeout = bounded_http_timeout(request_timeout, remaining)
            try:
                response = self._http.request(
                    method,
                    self._base_url + path,
                    json=dict(json) if json is not None else None,
                    headers=request_headers,
                    timeout=attempt_timeout,
                    follow_redirects=False,
                )
            except httpx.TimeoutException as exc:
                if not retry_allowed or attempt >= self._max_retries:
                    raise APITimeoutError(f"{method.upper()} request") from exc
                self._sleep_before_retry(
                    retry_delay(
                        attempt,
                        None,
                        backoff=self._retry_backoff,
                        backoff_maximum=self._retry_backoff_max,
                        retry_after_maximum=self._retry_after_max,
                        jitter_ratio=self._retry_jitter,
                    ),
                    deadline=deadline,
                    operation=f"{method.upper()} request deadline",
                )
                continue
            except httpx.TransportError as exc:
                if not retry_allowed or attempt >= self._max_retries:
                    raise APIConnectionError(f"{method.upper()} request") from exc
                self._sleep_before_retry(
                    retry_delay(
                        attempt,
                        None,
                        backoff=self._retry_backoff,
                        backoff_maximum=self._retry_backoff_max,
                        retry_after_maximum=self._retry_after_max,
                        jitter_ratio=self._retry_jitter,
                    ),
                    deadline=deadline,
                    operation=f"{method.upper()} request deadline",
                )
                continue

            if deadline is not None and self._monotonic() >= deadline:
                raise APITimeoutError(f"{method.upper()} request deadline")

            if (
                retry_allowed
                and response.status_code in RETRYABLE_STATUS
                and attempt < self._max_retries
            ):
                self._sleep_before_retry(
                    retry_delay(
                        attempt,
                        response,
                        backoff=self._retry_backoff,
                        backoff_maximum=self._retry_backoff_max,
                        retry_after_maximum=self._retry_after_max,
                        jitter_ratio=self._retry_jitter,
                    ),
                    deadline=deadline,
                    operation=f"{method.upper()} request deadline",
                )
                continue

            if not 200 <= response.status_code < 300:
                raise api_error(response)
            if response.status_code == 204 or not response.content:
                data: Any = None
            else:
                try:
                    data = response.json()
                except ValueError as exc:
                    raise ProtocolError(
                        f"Humalike returned non-JSON success body for {method.upper()} {path}"
                    ) from exc
            request_id = response.headers.get("x-request-id") or response.headers.get("x-trace-id")
            return APIResponse(
                data=data,
                status_code=response.status_code,
                headers=dict(response.headers),
                request_id=request_id,
            )

        raise AssertionError("unreachable")

    def _sleep_before_retry(
        self,
        delay: float,
        *,
        deadline: float | None,
        operation: str,
    ) -> None:
        if deadline is None:
            self._sleep(delay)
            return
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise APITimeoutError(operation)
        if delay >= remaining:
            self._sleep(remaining)
            raise APITimeoutError(operation)
        self._sleep(delay)

    def _request_endpoint(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        retry: bool | None = None,
        nullable: bool = False,
    ) -> JSON | None:
        return required_object_response(
            self.request(method, path, json=json, headers=headers, retry=retry),
            operation=operation,
            nullable=nullable,
        )

    # Account

    def whoami(self) -> IdentityResponse:
        return cast(
            IdentityResponse,
            self._request_endpoint(
                "POST",
                "/v1/turn-taking/actions/whoami",
                operation="whoami",
                json={},
            ),
        )

    def usage_summary(self) -> UsageSummaryResponse:
        return cast(
            UsageSummaryResponse,
            self._request_endpoint(
                "POST",
                "/v1/credits/projections/usage-summary",
                operation="usage_summary",
                json={},
            ),
        )

    # Social Learning and Observability

    def extract_profile(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        source: str | None = None,
    ) -> SocialLearningResponse:
        required_messages(messages)
        payload = {"transcript": _transcript(messages, source)}
        return cast(
            SocialLearningResponse,
            self._request_endpoint(
                "POST",
                "/v1/social-learning/actions/extract",
                operation="extract_profile",
                json=payload,
            ),
        )

    def analyze_transcript(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        agent_name: str,
        source: str | None = None,
        focus: str | None = None,
    ) -> SocialObservabilityResponse:
        required_messages(messages)
        required_text(agent_name, name="agent_name")
        payload = _without_none(
            {
                "transcript": _transcript(messages, source),
                "agent_name": agent_name,
                "focus": focus,
            }
        )
        return cast(
            SocialObservabilityResponse,
            self._request_endpoint(
                "POST",
                "/v1/social-observability/actions/analyze",
                operation="analyze_transcript",
                json=payload,
            ),
        )

    def get_report(self, report_id: str) -> StoredReportResponse | None:
        report_id = path_segment(report_id, name="report_id")
        return cast(
            StoredReportResponse | None,
            self._request_endpoint(
                "GET",
                f"/v1/social-observability/repositories/Report/by-id/{report_id}",
                operation="get_report",
                nullable=True,
            ),
        )

    # Theory of Mind

    def foresee_reply(
        self,
        transcript: Sequence[Mapping[str, Any]],
        *,
        candidate_reply: str,
        agent_name: str = "agent",
        system_prompt: str | None = None,
        subject_name: str | None = None,
    ) -> ForeseeResponse:
        required_messages(transcript, name="transcript")
        required_text(candidate_reply, name="candidate_reply")
        required_text(agent_name, name="agent_name")
        payload = _without_none(
            {
                "transcript": [dict(turn) for turn in transcript],
                "candidate_reply": candidate_reply,
                "agent_name": agent_name,
                "system_prompt": system_prompt,
                "subject_name": subject_name,
            }
        )
        return cast(
            ForeseeResponse,
            self._request_endpoint(
                "POST",
                "/v1/foresee/actions/foresee",
                operation="foresee_reply",
                json=payload,
            ),
        )

    # Social Memory

    def ingest_memory(
        self,
        scope_id: str,
        transcript: Sequence[Mapping[str, Any]],
        *,
        idempotency_key: str | None = None,
    ) -> MemoryIngestResponse:
        required_text(scope_id, name="scope_id")
        required_messages(transcript, name="transcript")
        key = (
            str(uuid.uuid4())
            if idempotency_key is None
            else validated_idempotency_key(idempotency_key)
        )
        headers = {"Idempotency-Key": key}
        payload = {"scope_id": scope_id, "transcript": [dict(turn) for turn in transcript]}
        return cast(
            MemoryIngestResponse,
            self._request_endpoint(
                "POST",
                "/v1/social-memory/actions/ingest",
                operation="ingest_memory",
                json=payload,
                headers=headers,
            ),
        )

    def recall_memory(self, scope_id: str, message: Mapping[str, Any]) -> MemoryRecallResponse:
        required_text(scope_id, name="scope_id")
        if not message:
            raise ValueError("message must not be empty")
        return cast(
            MemoryRecallResponse,
            self._request_endpoint(
                "POST",
                "/v1/social-memory/actions/recall",
                operation="recall_memory",
                json={"scope_id": scope_id, "message": dict(message)},
            ),
        )

    def ask_memory(self, scope_id: str, question: str) -> MemoryAskResponse:
        required_text(scope_id, name="scope_id")
        required_text(question, name="question")
        return cast(
            MemoryAskResponse,
            self._request_endpoint(
                "POST",
                "/v1/social-memory/actions/ask",
                operation="ask_memory",
                json={"scope_id": scope_id, "question": question},
            ),
        )

    # Personas

    def start_population(
        self, prompt: str, *, count: int = 1, grounding: GroundingLevel = "off"
    ) -> OperationStartResponse:
        required_text(prompt, name="prompt")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("count must be an integer >= 1")
        validated_grounding(grounding)
        response = self._request_endpoint(
            "POST",
            "/v1/personas/actions/generate",
            operation="start_population",
            json={"prompt": prompt, "count": count, "grounding": grounding},
        )
        validate_operation_start_response(response, operation="start_population")
        return cast(OperationStartResponse, response)

    def get_population(self, operation_id: str) -> OperationEnvelope:
        return self._get_persona_operation(operation_id, "Population", None)

    def wait_population(
        self,
        operation_id: str,
        *,
        timeout: float = 900.0,
        poll_interval: float = 3.0,
    ) -> PopulationResult:
        envelope = self._wait_operation(
            operation_id,
            lambda current_id, deadline: self._get_persona_operation(
                current_id,
                "Population",
                deadline,
            ),
            timeout=timeout,
            poll_interval=poll_interval,
        )
        return cast(PopulationResult, self._required_result(envelope, "result"))

    def start_enhancement(
        self,
        persona: str,
        *,
        grounding: GroundingLevel = "off",
    ) -> OperationStartResponse:
        required_text(persona, name="persona")
        validated_grounding(grounding)
        response = self._request_endpoint(
            "POST",
            "/v1/personas/actions/enhance",
            operation="start_enhancement",
            json={"persona": persona, "grounding": grounding},
        )
        validate_operation_start_response(response, operation="start_enhancement")
        return cast(OperationStartResponse, response)

    def get_enhancement(self, operation_id: str) -> OperationEnvelope:
        return self._get_persona_operation(operation_id, "Enhancement", None)

    def wait_enhancement(
        self,
        operation_id: str,
        *,
        timeout: float = 900.0,
        poll_interval: float = 3.0,
    ) -> EnhancementResult:
        envelope = self._wait_operation(
            operation_id,
            lambda current_id, deadline: self._get_persona_operation(
                current_id,
                "Enhancement",
                deadline,
            ),
            timeout=timeout,
            poll_interval=poll_interval,
        )
        return cast(
            EnhancementResult,
            self._required_result(envelope, "persona"),
        )

    def start_validation(
        self,
        personas: Sequence[Mapping[str, Any]],
        *,
        blueprint: Mapping[str, Any] | None = None,
    ) -> OperationStartResponse:
        required_messages(personas, name="personas")
        payload = _without_none(
            {
                "personas": [dict(persona) for persona in personas],
                "blueprint": dict(blueprint) if blueprint is not None else None,
            }
        )
        response = self._request_endpoint(
            "POST",
            "/v1/personas/actions/validate",
            operation="start_validation",
            json=payload,
        )
        validate_operation_start_response(response, operation="start_validation")
        return cast(OperationStartResponse, response)

    def get_validation(self, operation_id: str) -> OperationEnvelope:
        return self._get_persona_operation(operation_id, "Evaluation", None)

    def wait_validation(
        self,
        operation_id: str,
        *,
        timeout: float = 300.0,
        poll_interval: float = 1.0,
    ) -> ValidationResult:
        envelope = self._wait_operation(
            operation_id,
            lambda current_id, deadline: self._get_persona_operation(
                current_id,
                "Evaluation",
                deadline,
            ),
            timeout=timeout,
            poll_interval=poll_interval,
        )
        return cast(
            ValidationResult,
            self._required_result(envelope, "result"),
        )

    # Turn-taking and Social Signals

    def open_thread(
        self,
        *,
        thread_id: str | None = None,
        enable_social_signals: bool | None = None,
        signals_channel_id: str | None = None,
    ) -> OpenThreadResponse:
        """Open or reconnect a thread.

        ``enable_social_signals=True`` sends the documented integration object.
        A channel id also opts in when the flag is ``None``.  ``False`` omits
        the integration and cannot be combined with a channel id because the
        public contract does not document a disable/reset payload.
        """

        enable_social_signals = validated_optional_bool(
            enable_social_signals,
            name="enable_social_signals",
        )
        if thread_id is not None:
            required_text(thread_id, name="thread_id")
        if signals_channel_id is not None:
            required_text(signals_channel_id, name="signals_channel_id")
            if enable_social_signals is False:
                raise ValueError(
                    "signals_channel_id cannot be used when enable_social_signals is False"
                )
        integrations: JSON | None = None
        if enable_social_signals is True or signals_channel_id is not None:
            integrations = {"social_signals": _without_none({"channel_id": signals_channel_id})}
        payload = _without_none({"thread_id": thread_id, "integrations": integrations})
        return cast(
            OpenThreadResponse,
            self._request_endpoint(
                "POST",
                "/v1/turn-taking/actions/open_thread",
                operation="open_thread",
                json=payload,
            ),
        )

    def submit_messages(
        self,
        thread_id: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        system_prompt: str | None = None,
        skip_decide: bool = False,
        retry: bool = False,
    ) -> SubmitMessagesResponse:
        required_text(thread_id, name="thread_id")
        validated_submit_messages(messages)
        if not isinstance(skip_decide, bool):
            raise ValueError("skip_decide must be a bool")
        payload = _without_none(
            {
                "thread_id": thread_id,
                "messages": [dict(message) for message in messages],
                "system_prompt": system_prompt,
                "skip_decide": skip_decide,
            }
        )
        response = self._request_endpoint(
            "POST",
            "/v1/turn-taking/actions/submit_messages",
            operation="submit_messages",
            json=payload,
            retry=retry,
        )
        validate_submit_messages_response(response)
        return cast(SubmitMessagesResponse, response)

    def record_event(
        self,
        thread_id: str,
        event_type: RecordEventType,
        sender: str,
        *,
        client_ts: str | None = None,
    ) -> RecordEventResponse:
        required_text(thread_id, name="thread_id")
        validated_record_event_type(event_type)
        required_text(sender, name="sender")
        if len(sender) > 255:
            raise ValueError("sender must contain at most 255 characters")
        if client_ts is not None:
            required_text(client_ts, name="client_ts")
        payload = _without_none(
            {
                "thread_id": thread_id,
                "type": event_type,
                "sender": sender,
                "client_ts": client_ts,
            }
        )
        return cast(
            RecordEventResponse,
            self._request_endpoint(
                "POST",
                "/v1/turn-taking/actions/record_event",
                operation="record_event",
                json=payload,
            ),
        )

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
    ) -> RespondResponse:
        required_text(thread_id, name="thread_id")
        required_text(content, name="content")
        if isinstance(turn_epoch, bool) or not isinstance(turn_epoch, int) or turn_epoch < 0:
            raise ValueError("turn_epoch must be an integer >= 0")
        payload = _without_none(
            {
                "thread_id": thread_id,
                "content": content,
                "turn_epoch": turn_epoch,
                "system_prompt": system_prompt,
                "agent_name": agent_name,
                "pacing": dict(pacing) if pacing is not None else None,
                "metadata": dict(metadata) if metadata is not None else None,
            }
        )
        return cast(
            RespondResponse,
            self._request_endpoint(
                "POST",
                "/v1/turn-taking/actions/respond",
                operation="respond",
                json=payload,
            ),
        )

    def _wait_operation(
        self,
        operation_id: str,
        fetch: Callable[[str, float | None], OperationEnvelope],
        *,
        timeout: float,
        poll_interval: float,
    ) -> OperationEnvelope:
        """Wait within one caller budget, except for a zero-timeout initial probe.

        A positive timeout bounds SDK-controlled HTTP phase limits, safe retries,
        retry backoff, and polling sleeps, and rejects a late result.  A sync
        transport remains responsible for returning control from an in-flight
        request. ``timeout=0`` deliberately performs one normal GET (with its
        standard HTTP timeout/retry policy) so callers can inspect an already
        terminal operation without authorizing any subsequent wait or request.
        """

        timeout = validated_non_negative_number(timeout, name="timeout")
        poll_interval = validated_non_negative_number(
            poll_interval,
            name="poll_interval",
            allow_zero=False,
        )
        zero_timeout_probe = timeout == 0
        deadline = None if zero_timeout_probe else self._monotonic() + timeout
        while True:
            if deadline is not None and self._monotonic() >= deadline:
                raise OperationTimeoutError(operation_id, timeout)
            try:
                envelope = fetch(operation_id, deadline)
            except APITimeoutError as exc:
                if deadline is not None and self._monotonic() >= deadline:
                    raise OperationTimeoutError(operation_id, timeout) from exc
                raise
            if deadline is not None and self._monotonic() >= deadline:
                raise OperationTimeoutError(operation_id, timeout)
            if not isinstance(envelope, Mapping):
                raise ProtocolError(
                    f"operation {operation_id} returned a non-object response envelope"
                )
            status = envelope.get("status")
            if status == "succeeded":
                return envelope
            if status == "failed":
                raise OperationFailedError(operation_id, str(envelope.get("error") or "unknown"))
            if status not in RUNNING_OPERATION_STATES:
                raise ProtocolError(
                    f"operation {operation_id} returned undocumented status {status!r}"
                )
            if zero_timeout_probe:
                raise OperationTimeoutError(operation_id, timeout)
            assert deadline is not None
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise OperationTimeoutError(operation_id, timeout)
            self._sleep(min(poll_interval, remaining))

    def _get_persona_operation(
        self,
        operation_id: str,
        repository: str,
        deadline: float | None,
    ) -> OperationEnvelope:
        encoded_id = path_segment(operation_id, name="operation_id")
        path = f"/v1/personas/repositories/{repository}/by-id/{encoded_id}"
        if deadline is None:
            data = self.request("GET", path)
        else:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise APITimeoutError("GET request deadline")
            data = self._request_with_response(
                "GET",
                path,
                json=None,
                headers=None,
                retry=None,
                timeout=None,
                deadline=deadline,
            ).data
        operation = f"get_{repository.lower()}"
        response = required_object_response(
            data,
            operation=operation,
        )
        validate_operation_envelope(response, operation=operation)
        return cast(OperationEnvelope, response)

    @staticmethod
    def _required_result(envelope: Mapping[str, Any], field: str) -> JSON:
        value = envelope.get(field)
        if not isinstance(value, Mapping):
            operation_id = envelope.get("id", "<unknown>")
            raise ProtocolError(
                f"succeeded operation {operation_id} did not contain object field {field!r}"
            )
        return dict(value)
