# SDK API reference

`HumalikeClient` and `AsyncHumalikeClient` expose matching HTTP endpoint
methods. Async methods have the same arguments and return types, but must be
awaited. Realtime Turn-Taking is async-only.

This reference uses three evidence labels:

- **Documented contract** — behavior described by the public
  [Humalike documentation](https://docs.humalike.com/) snapshot verified on
  2026-07-12.
- **Observed live** — a narrow observation from the synthetic publication pass;
  it is not an SLA, price quote, or general availability claim.
- **SDK behavior** — behavior implemented by this community client.

## Construction and lifecycle

```python
HumalikeClient(
    token: str,
    *,
    base_url: str = "https://api.humalike.com",
    timeout: float | httpx.Timeout = 120.0,
    max_retries: int = 2,
    retry_backoff: float = 0.25,
    retry_backoff_max: float = 30.0,
    retry_after_max: float = 300.0,
    retry_jitter: float = 0.1,
    user_agent_suffix: str | None = None,
    http_client: httpx.Client | None = None,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
)

AsyncHumalikeClient(
    token: str,
    *,
    base_url: str = "https://api.humalike.com",
    timeout: float | httpx.Timeout = 120.0,
    max_retries: int = 2,
    retry_backoff: float = 0.25,
    retry_backoff_max: float = 30.0,
    retry_after_max: float = 300.0,
    retry_jitter: float = 0.1,
    user_agent_suffix: str | None = None,
    http_client: httpx.AsyncClient | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    monotonic: Callable[[], float] = time.monotonic,
)
```

**SDK behavior.** `from_env(variable="HUMALIKE_TOKEN", **kwargs)` constructs
either client from one explicit environment variable. The SDK does not load a
`.env` file. A missing variable raises `ValueError`.

The default user agent is `humalike-python/<version>`. A non-sensitive suffix
such as `roompulse/0.1.0` produces
`humalike-python/<version> roompulse/0.1.0`. Tokens and user-agent suffixes must
be ASCII and cannot contain control characters; invalid values fail locally as
`ValueError` instead of leaking a lower-level header encoding exception. The
installed version is available as `humalike.__version__`.

Pass either `http_client` or `transport`, never both. An injected HTTP client is
caller-owned and is not closed by the SDK. A client constructed without one
owns its transport and should be used as a context manager or closed explicitly:

```python
with HumalikeClient.from_env() as client:
    identity = client.whoami()

async with AsyncHumalikeClient.from_env() as client:
    identity = await client.whoami()

client.close()
await async_client.close()
```

Only HTTPS origins without user information, path, query, or fragment are
accepted as `base_url`. The bearer token is sent to that origin, so a custom
origin is a trusted application boundary. See [Security](../SECURITY.md).
`sleep` and `monotonic` are dependency-injection hooks primarily intended for
deterministic tests.

## Common input and result types

`JSON` is an alias for `dict[str, Any]`. Endpoint helpers accept mappings and
return ordinary dictionaries annotated with public `TypedDict` types. Required
success fields are required in those types; that does not prevent a server from
returning additional forward-compatible keys.

`TranscriptMessage` and `PacingOverrides` use `total=False` because their keys
vary by endpoint or override. `OperationEnvelope`, `ValidationResult`, and
`TurnTakingEventDict` use `NotRequired` only for status-dependent or optional
fields. Endpoint helpers validate that a success body is an object, while
Persona operation starts/read-backs and `submit_messages` also validate their
small stable required envelopes. Polling and WebSocket helpers perform the
additional targeted checks described later. Applications should still validate
dynamic nested content at a persistence, UI, or other trust boundary.

The exported literal aliases mirror locally enforced documented values:

| Alias | Values |
|---|---|
| `GroundingLevel` | `off`, `web`, `research` |
| `OperationStatus` | `pending`, `running`, `succeeded`, `failed` |
| `RecordEventType` | `typing_start`, `typing_stop`, `message_edited` |
| `TurnDecision` | `speak`, `stay_silent` |

### Conversation messages

`TranscriptMessage` describes the union of documented message fields used by
the API families:

```python
class TranscriptMessage(TypedDict, total=False):
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
```

Social Learning, Social Observability, Theory of Mind, and Social Memory use
`speaker`/`text`. Turn-Taking inbound messages use `sender`/`content`, with
optional `client_ts` and `has_media`. The SDK preserves caller-supplied keys; it
does not silently translate between these shapes.

`respond(..., pacing=...)` accepts the documented `PacingOverrides` keys:

```python
class PacingOverrides(TypedDict, total=False):
    reading_delay_ms: int
    typing_wpm: float
    max_typing_ms: int
```

### Response model summary

| Model | Stable annotated fields |
|---|---|
| `IdentityResponse` | `user_id` |
| `UsageSummaryResponse` | `total_calls`, `total_credits`, `per_component`, `daily_series` |
| `UsageComponent` / `UsageDay` | `component`, `calls`, `credits` / `date`, `requests` |
| `SocialLearningResponse` | `profile`, `prompt_block` |
| `SocialObservabilityResponse` | `health_score`, `summary`, `interactions`, `interaction_totals`, `per_user`, `findings` |
| `StoredReportResponse` | `agent_name`, `health_score`, nested `report` |
| `ForeseeResponse` | `refined_reply`, `refinement_rationale`, `mental_state`, `predicted_reaction` |
| `MemoryIngestResponse` | `ingested` |
| `MemoryRecallResponse` / `MemoryAskResponse` | `context` / `answer` |
| `OperationStartResponse` | `id`, `status` |
| `OperationProgress` | `produced`, `total` |
| `OperationEnvelope` | `id`, `status`; conditional `source`, `grounding`, `progress`, `result`, nullable `persona`, nullable `error` |
| `PopulationResult` | `personas`, `blueprint`; optional `diversity` and `marginals` when `count > 1` |
| `EnhancementResult` | `persona_id`, `fields`, `system_prompt`, `markdown` |
| `ValidationResult` | `passed`, `gates`, `scorecards`, `diversity`, `marginals` |
| `OpenThreadResponse` | `thread`, `channel`, `realtime` |
| `ThreadResource` / `RealtimeGrant` | thread identity and timestamps / `connect_url`, `expires_at` |
| `SubmitMessagesResponse` | `decision`, `turn_epoch`, `tags` |
| `RecordEventResponse` | `tags` |
| `RespondResponse` | `superseded`, `scheduled` |
| `ScheduledMessage` | `id`, `thread_id`, `content`, `position`, `deliver_at`, `status` |

## HTTP endpoint methods

The signatures below show the synchronous methods. The async client exposes
the same HTTP signatures with `async def` and awaited results.

### Account

```python
whoami() -> IdentityResponse
usage_summary() -> UsageSummaryResponse
```

### Social Learning

```python
extract_profile(
    messages: Sequence[Mapping[str, Any]],
    *,
    source: str | None = None,
) -> SocialLearningResponse
```

`messages` must be non-empty. The SDK nests them under
`transcript.messages` and adds `transcript.source` when supplied.

### Social Observability

```python
analyze_transcript(
    messages: Sequence[Mapping[str, Any]],
    *,
    agent_name: str,
    source: str | None = None,
    focus: str | None = None,
) -> SocialObservabilityResponse

get_report(report_id: str) -> StoredReportResponse | None
```

**Documented contract.** A stored report read wraps the original analysis under
`report`, alongside `agent_name` and the denormalized `health_score`; an absent
or non-owned report returns `None`.

**Observed live.** Successful `analyze_transcript` responses in the publication
pass contained the immediate report but no `id`, `report_id`, nested report ID,
or retrieval header. The SDK therefore exposes the documented read method but
does not invent a report handle.

### Theory of Mind

```python
foresee_reply(
    transcript: Sequence[Mapping[str, Any]],
    *,
    candidate_reply: str,
    agent_name: str = "agent",
    system_prompt: str | None = None,
    subject_name: str | None = None,
) -> ForeseeResponse
```

The SDK returns the forecast and refined reply unchanged. The application owns
the policy deciding whether to send the original, the refinement, or nothing.

### Social Memory

```python
ingest_memory(
    scope_id: str,
    transcript: Sequence[Mapping[str, Any]],
    *,
    idempotency_key: str | None = None,
) -> MemoryIngestResponse

recall_memory(
    scope_id: str,
    message: Mapping[str, Any],
) -> MemoryRecallResponse

ask_memory(scope_id: str, question: str) -> MemoryAskResponse
```

`ingest_memory` always sends `Idempotency-Key`. When no key is supplied, the SDK
generates a UUID, which preserves retry identity only inside that call. Persist
and reuse a caller-owned key to preserve identity across process restarts.

### Personas

```python
start_population(
    prompt: str,
    *,
    count: int = 1,
    grounding: GroundingLevel = "off",
) -> OperationStartResponse

get_population(operation_id: str) -> OperationEnvelope

wait_population(
    operation_id: str,
    *,
    timeout: float = 900.0,
    poll_interval: float = 3.0,
) -> PopulationResult

start_enhancement(
    persona: str,
    *,
    grounding: GroundingLevel = "off",
) -> OperationStartResponse

get_enhancement(operation_id: str) -> OperationEnvelope

wait_enhancement(
    operation_id: str,
    *,
    timeout: float = 900.0,
    poll_interval: float = 3.0,
) -> EnhancementResult

start_validation(
    personas: Sequence[Mapping[str, Any]],
    *,
    blueprint: Mapping[str, Any] | None = None,
) -> OperationStartResponse

get_validation(operation_id: str) -> OperationEnvelope

wait_validation(
    operation_id: str,
    *,
    timeout: float = 300.0,
    poll_interval: float = 1.0,
) -> ValidationResult
```

`grounding` is locally restricted to `off`, `web`, or `research`. Persona
objects are dynamic mappings: their `fields` keys depend on the generated or
supplied persona blueprint.

### Turn-Taking and Social Signals

```python
open_thread(
    *,
    thread_id: str | None = None,
    enable_social_signals: bool | None = None,
    signals_channel_id: str | None = None,
) -> OpenThreadResponse

submit_messages(
    thread_id: str,
    messages: Sequence[Mapping[str, Any]],
    *,
    system_prompt: str | None = None,
    skip_decide: bool = False,
    retry: bool = False,
) -> SubmitMessagesResponse

record_event(
    thread_id: str,
    event_type: RecordEventType,
    sender: str,
    *,
    client_ts: str | None = None,
) -> RecordEventResponse

respond(
    thread_id: str,
    content: str,
    turn_epoch: int,
    *,
    system_prompt: str | None = None,
    agent_name: str | None = None,
    pacing: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> RespondResponse
```

`enable_social_signals=True` sends the documented integration object.
`False` and `None` omit it; providing `signals_channel_id` also sends the
integration. Combining an explicit `False` with `signals_channel_id` raises
`ValueError`. Preserve the `turn_epoch` from the matching decision. A
`superseded` response schedules no messages and requires a new draft against
the latest turn.

`submit_messages` validates the documented 1–20 item bound, required
`sender`/`content` lengths, and optional `client_ts`/`has_media` types before
network I/O. Its successful response must contain a documented `decision`, a
non-negative integer `turn_epoch`, and an array-of-strings `tags`; otherwise the
SDK raises `ProtocolError`. Additional response keys are preserved.
`record_event` accepts only `typing_start`, `typing_stop`, and `message_edited`.

## Documented cost and state boundaries

The classifications below summarize the **documented contract**, not observed
prices. Credits depend on inputs and service behavior, and the public usage API
does not quote a request before execution. Review the current official
[Credits and billing](https://docs.humalike.com/credits-and-billing) page before
running live traffic.

| Method or flow | Documented billing boundary | Remote effect |
|---|---|---|
| `whoami`, `usage_summary` | not billable | account reads |
| `extract_profile` | billable | analysis result only |
| `analyze_transcript` | billable | analysis is also documented as persisted |
| `get_report` | not billable | owner-scoped read |
| `foresee_reply` | billable | analysis result only |
| `ingest_memory` | not billable | appends conversation state |
| `recall_memory`, `ask_memory` | billable | reads a memory scope |
| Persona `start_*` | billable | starts a persistent async operation |
| Persona `get_*`, `wait_*` | not billable reads | polls an existing operation |
| `open_thread` | not billable | creates or reopens a thread and grant |
| `submit_messages` | billable unless documented `skip_decide`/media short-circuit applies | records messages and advances the turn |
| `record_event` | not billable | records activity |
| `respond` | billable unless the reply is superseded | refines and schedules messages |
| WebSocket connect/receive | no separate billed action is documented | receives events already scheduled for the thread |

The executable [examples](../examples/README.md) add explicit gates around
stateful or potentially billable flows. A successful synthetic smoke run is not
evidence of future price, latency, availability, or production safety.

## Persona polling behavior

**SDK behavior.** Start methods return an operation `id`; persist it before
polling. Start and get methods require a non-empty string `id` and one of the
documented operation statuses; malformed success envelopes raise
`ProtocolError`. Get methods perform one owner-scoped GET. Wait methods
repeatedly call the matching get method using a monotonic deadline:

- `pending` and `running` continue polling;
- `succeeded` returns `result` for population/validation or `persona` for
  enhancement;
- `failed` raises `OperationFailedError(operation_id, error)`;
- a missing, non-string, or otherwise undocumented status raises
  `ProtocolError`;
- a non-object envelope or a succeeded envelope without its required object
  result raises `ProtocolError`;
- reaching the deadline raises
  `OperationTimeoutError(operation_id, timeout_seconds)`.

`timeout` must be finite and non-negative; `poll_interval` must be finite and
strictly positive. A zero timeout deliberately permits exactly one normal
initial GET, then times out without sleeping or polling again if the operation
is non-terminal. That initial probe retains the normal per-request timeout.

For a positive timeout, one monotonic deadline covers every HTTP attempt, safe
retry, `Retry-After`/backoff delay, and polling sleep. Each HTTP timeout is the
smaller of its configured value and the remaining budget. A terminal response
that arrives at or after the deadline is rejected with `OperationTimeoutError`.

The async client also wraps each complete in-flight attempt in a cancellable
remaining-budget timer. HTTPX exposes sync timeouts per network phase and read
inactivity, not as a cancellable total wall-clock timer. The sync client caps
every phase and rejects a late response, but cannot preempt a custom or
slow-trickling synchronous transport while it still owns control. Use the async
wait helpers when returning control by the deadline is a strict requirement;
injected transports in either client remain a trusted, cooperative boundary.

An SDK polling timeout or local process interruption does **not** cancel the
remote job. Do not start a replacement blindly: resume with the saved operation
ID through `get_*` or `wait_*`. Poll GETs use the safe-read retry policy below.

## Retry, idempotency, and timeouts

**SDK behavior.** `max_retries` counts additional attempts. The default value
`2` therefore permits at most three total attempts. `max_retries=0` disables
automatic re-attempts.

Default retries are limited to:

- `GET`, `HEAD`, and `OPTIONS` requests;
- the read-like POST routes used by `whoami` and `usage_summary`;
- Social Memory ingest carrying `Idempotency-Key`.

For those requests, timeouts and `httpx.TransportError` failures may be retried,
as may HTTP `408`, `429`, `502`, `503`, and `504`. `Retry-After` accepts both
delta-seconds and an HTTP-date and is capped separately by `retry_after_max`
(300 seconds by default). Local delay is `retry_backoff * 2**attempt`, capped by
`retry_backoff_max` (30 seconds by default), with up to `retry_jitter` positive
jitter (10% by default) to avoid synchronized retries.

Potentially billable or mutating POSTs such as `extract_profile`,
`analyze_transcript`, Persona starts, `foresee_reply`, `recall_memory`,
`ask_memory`, `submit_messages`, and `respond` are not retried by default.

**Documented contract.** Humalike says replaying the same `submit_messages`
batch does not double-record it. **Observed live.** In a controlled 2026-07-12
check with automatic retries disabled, one normal synthetic batch and its exact
replay each settled as `+1` `turn-taking` call and `+1` credit; the replay also
advanced `turn_epoch` by one. The endpoint exposes neither a message ID nor an
idempotency key or transcript read-back, so message-storage deduplication remains
unobservable. **SDK behavior.** `submit_messages` defaults to `retry=False`
because decision cost and turn advancement demonstrably repeat. Set its explicit
`retry=True` argument only when the application deliberately accepts the
documented replay guarantee despite that observed behavior.
A timeout after one of these calls is ambiguous: the server may have completed
the work even though the response was lost.

Low-level calls accept `retry=None`, `False`, or `True`:

- `None` applies the policy above;
- `False` disables retries for that call;
- `True` forcibly opts the call into retry handling.

`retry=True` is an expert escape hatch. It bypasses the SDK's replay-safety
classification and can duplicate remote state, delivery, or cost. Use it only
with an endpoint-specific replay guarantee. The SDK never automatically retries
`respond`.

**Documented contract.** Humalike describes `respond` as idempotent.
**Observed live.** In a controlled exact replay with the same synthetic thread,
epoch, content, and agent, the second call returned different scheduled-message
IDs, remained non-superseded, and produced another settled charge across the
Turn-Taking and Theory of Mind components. This is a narrow observation, not a
price or reliability claim. **SDK behavior.** `respond` has no high-level retry
opt-in and is never replayed automatically; callers should treat a lost response
as ambiguous.

The constructor timeout is the default for each HTTP attempt. Numeric timeout
values and every `httpx.Timeout` component must be finite and positive. A
per-call `timeout=` overrides the constructor value. `max_retries` must be a
non-negative non-boolean integer. The backoff and cap values must be finite and
non-negative; `retry_jitter` must be between 0 and 1. `APITimeoutError` and
`APIConnectionError` retain the original `httpx` exception as `__cause__`.

## Errors

Operational SDK exceptions derive from `HumalikeError`; local Python argument
and optional-dependency failures are deliberately separate.

### HTTP error mapping

Non-success JSON error envelopes are decoded into `HumalikeAPIError` or a
subclass. Every `HumalikeAPIError` exposes `status_code`, `code`, `message`,
`details`, and optional `trace_id`.

| Response condition | SDK exception |
|---|---|
| HTTP 401 or code `UNAUTHORIZED` | `AuthenticationError` |
| HTTP 402 or code `PAYMENT_REQUIRED` | `PaymentRequiredError` |
| HTTP 403 or code `forbidden` | `PermissionDeniedError` |
| HTTP 400/422 or a validation code | `ValidationError` |
| HTTP 5xx or code `UPSTREAM_ERROR` | `UpstreamError` |
| another non-success response | `HumalikeAPIError` |

An error-envelope `trace_id` is preferred; otherwise `X-Trace-ID` is retained.
After retry exhaustion, `408` and `429` normally remain generic
`HumalikeAPIError` instances, while 5xx responses map to `UpstreamError`.

### Transport, protocol, and operation errors

- `APIConnectionError` — HTTP transport or WebSocket connection/receive/close
  failed.
- `APITimeoutError` — an HTTP request or bounded WebSocket receive timed out;
  it subclasses `APIConnectionError`.
- `ProtocolError` — a successful HTTP response was non-JSON, polling returned
  an invalid top-level object or targeted stable contract shape/status, a
  WebSocket grant was invalid, or an event envelope could not be decoded.
- `OperationFailedError` — a Persona operation reached `failed`.
- `OperationTimeoutError` — local Persona polling reached its deadline.

Local configuration or input validation raises `ValueError`, including a
missing `from_env` variable, invalid token/origin/user-agent suffix, empty
required values, unsupported grounding, invalid counts/epochs, and invalid
poll/WebSocket limits or documented Turn-Taking message/event shapes. Missing
optional WebSocket dependencies and receiving from an already closed stream
raise `RuntimeError`.

Exception `repr()` values redact API details, messages, trace IDs, operation
IDs, and operation error payloads. Human-readable `str()` remains diagnostic
and must still be treated as potentially sensitive.

All public SDK exceptions support pickle round-trips and preserve their public
fields, concrete subclass, and `.args`. This helps multiprocessing and job
queue integrations, but serialized exceptions contain the original diagnostic
data. Treat pickle payloads as sensitive and never deserialize untrusted data.

An availability fallback commonly needs to consider both
`APIConnectionError` (including timeouts) and `UpstreamError`. Authentication,
payment, permission, validation, and protocol failures normally require a
configuration, account, input, or contract fix rather than silent degradation.

## Low-level HTTP requests

Both clients expose matching low-level methods; await the async versions.

```python
request(
    method: str,
    path: str,
    *,
    json: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    retry: bool | None = None,
    timeout: float | httpx.Timeout | None = None,
) -> Any

request_with_response(
    method: str,
    path: str,
    *,
    json: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    retry: bool | None = None,
    timeout: float | httpx.Timeout | None = None,
) -> APIResponse[Any]
```

`path` must be a relative `/v1/...` API path. Validation examines its decoded
path before HTTPX constructs the URL: dot segments, encoded path separators,
backslashes, control characters, and any decoded path outside `/v1/` are
rejected. Report and operation identifiers remain arbitrary single-segment
strings (including spaces, Unicode, internal dots, and literal percent text),
but cannot be `.`, `..`, contain a slash or backslash, or contain controls.

Per-request headers cannot set transport-managed or hop-by-hop fields:
`Authorization`, proxy authentication, `Host`, `Content-Length`,
`Transfer-Encoding`, `Connection`, `Upgrade`, `TE`, `Trailer`, or `Keep-Alive`.
An `Idempotency-Key` must be ASCII, non-empty, trimmed, and free of control
characters before it can authorize ingest retry. Other application headers are
merged normally. Only `2xx` is accepted as success; redirects and all other
non-`2xx` responses use the API error mapping above. Redirect following is
disabled per request, including when an injected HTTPX client enables it. A
`204` or empty success returns `None`; a non-JSON success raises
`ProtocolError`.

`APIResponse[T]` is a frozen dataclass with `data`, `status_code`, `headers`,
and optional `request_id`; contained dictionaries remain ordinary mutable
objects. `request_id` uses `X-Request-ID` and falls back to `X-Trace-ID`. Its
`repr` redacts data and headers, but direct access can still reveal sensitive
response content. Endpoint helpers return only decoded data; use this low-level
envelope when status or headers are part of an extension contract.

## Turn-Taking WebSocket

Install the optional dependency before using the default connector:

```bash
python -m pip install "humalike-python[websocket]"
```

Realtime support is async-only. `AsyncHumalikeClient.connect_turn_taking`, the
standalone `connect_turn_taking` function, and `TurnTakingStream.connect` accept
the same connection arguments:

```python
async def connect_turn_taking(
    grant_or_url: str | Mapping[str, Any],
    *,
    connector: WebSocketConnector | None = None,
    open_timeout: float = 10.0,
    max_size: int = 1_048_576,
) -> TurnTakingStream

class TurnTakingStream:
    @classmethod
    async def connect(
        cls,
        grant_or_url: str | Mapping[str, Any],
        *,
        connector: WebSocketConnector | None = None,
        open_timeout: float = 10.0,
        max_size: int = 1_048_576,
    ) -> TurnTakingStream: ...

    async def recv(
        self,
        *,
        timeout: float | None = None,
    ) -> TurnTakingEvent: ...

    async def close(self) -> None: ...
```

`grant_or_url` may be the whole result of `open_thread`, a mapping containing a
`connect_url`, or the URL itself. Only a `wss://` URL with a hostname and no
userinfo or fragment is accepted. The signed URL is passed to the connector,
not retained on the stream, and redacted from representations and SDK-generated
errors. Before a connect frame exits, the SDK also overwrites signed grants in
its frame locals so traceback collectors that capture local variables do not
recover them. This applies to the class method, convenience function, async
client wrapper, URL validation helper, and default connector. A custom connector
is a trusted boundary and remains responsible for its own logs and retained
state.

Typical lifecycle:

```python
opened = await client.open_thread()

async with await client.connect_turn_taking(opened) as stream:
    attached = await stream.recv(timeout=10)
    async for event in stream:
        if event.type == "turn_taking.message":
            handle(event.data)
```

`TurnTakingEvent` exposes:

- `type: str`;
- `data: dict[str, Any]`;
- required `channel` and event-specific optional `id`;
- `timestamp`, read from a delivery event's required `ts` or an attachment's
  required `server_time`;
- `raw`, the original `TurnTakingEventDict`.

Event data and `raw` may contain conversation content and are redacted from
`repr`. `TurnTakingEventDict` requires `type` and `channel`; its remaining fields
are conditional on the event kind.

**Documented contract.** Normal delivery events require string `id`, `type`,
`channel`, and `ts` fields plus object `data`.

**Observed live.** The initial `attached` frame required `type`, `channel`, and
`server_time` but omitted `data`; the parser accepts that specific shape and
exposes an empty data object.

`recv(timeout=...)` raises `APITimeoutError` when no frame arrives in time.
Malformed text, JSON, or envelopes raise `ProtocolError`; abnormal connection
or close failures raise `APIConnectionError`. A normal `websockets`
`ConnectionClosedOK` ends `async for` iteration. Calling `recv` directly after
closure is not converted to iteration completion.

Only the SDK's private missing-dependency error escapes as the documented
installation `RuntimeError`. Any other exception, including `RuntimeError` from
a custom connector, is wrapped as `APIConnectionError`. Raw connect exceptions
are deliberately not chained because they may contain the complete signed URL;
the missing-dependency `ImportError` remains available as a safe cause. The
SDK-owned frames in that cause are scrubbed before unwinding as well.
`open_timeout` and an explicit receive `timeout` must be finite positive
numbers; `max_size` must be a positive non-boolean integer.

Grants are short-lived. On expiry or disconnect, call
`open_thread(thread_id=<existing id>)` to obtain a fresh grant and reconnect.
The SDK does not automatically reconnect, replay missed events, or refresh a
grant. Close the old stream before replacing it.

Custom connectors use this exported transport boundary:

```python
class WebSocketConnection(Protocol):
    async def recv(self) -> str | bytes: ...
    async def close(self) -> None: ...

WebSocketConnector = Callable[[str], Awaitable[WebSocketConnection]]
```

## Capability protocols

Applications can depend on the smallest structural protocol they need:

| Sync protocol | Async protocol | Methods |
|---|---|---|
| `AccountClient` | `AsyncAccountClient` | `whoami`, `usage_summary` |
| `SocialLearningClient` | `AsyncSocialLearningClient` | `extract_profile` |
| `SocialObservabilityClient` | `AsyncSocialObservabilityClient` | `analyze_transcript`, `get_report` |
| `TheoryOfMindClient` | `AsyncTheoryOfMindClient` | `foresee_reply` |
| `SocialMemoryClient` | `AsyncSocialMemoryClient` | `ingest_memory`, `recall_memory`, `ask_memory` |
| `PersonasClient` | `AsyncPersonasClient` | all Persona `start_*`, `get_*`, and `wait_*` methods |
| `TurnTakingClient` | `AsyncTurnTakingClient` | `open_thread`, `submit_messages`, `record_event`, `respond`; async also has `connect_turn_taking` |
| `HumalikeClientProtocol` | `AsyncHumalikeClientProtocol` | the complete client surface for that execution model |

The individual family capability protocols are `runtime_checkable`, but
runtime checks establish only structural attribute presence. Use a static type
checker such as Mypy to verify complete signatures and return types.
