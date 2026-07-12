# Humalike Community Python SDK

[![CI](https://github.com/j-lojek/humalike-python/actions/workflows/ci.yml/badge.svg)](https://github.com/j-lojek/humalike-python/actions/workflows/ci.yml)

An unofficial, typed Python client for the public
[Humalike APIs](https://docs.humalike.com/). It provides matching synchronous
and asynchronous clients, stable errors, safe retry defaults, Persona polling,
and Turn-Taking WebSocket support.

> This is a community project, not an official Humalike SDK. It currently
> targets the public contract verified on 2026-07-12 and remains beta software.

## Features

- sync and async methods for every documented HTTP API family;
- public `TypedDict` response models and capability-level `Protocol` types;
- dependency injection for deterministic, network-free tests;
- bounded polling helpers for Persona operations;
- caller-controlled Social Memory idempotency;
- conservative retries that do not replay billable mutations by default;
- optional async Turn-Taking WebSocket client with signed-URL redaction.

Python 3.10–3.14 is supported.

## Installation

Install from a clone or source checkout:

```bash
git clone https://github.com/j-lojek/humalike-python.git
cd humalike-python
python -m pip install .
```

Add the optional WebSocket dependency when using realtime Turn-Taking events:

```bash
python -m pip install ".[websocket]"
```

For vendored or submodule-based product setups, see
[Product integration](docs/PRODUCT_INTEGRATION.md).

## Authentication

Set the token in the process environment. The SDK does not load `.env` files.

```bash
export HUMALIKE_TOKEN="your-token"
```

```powershell
$env:HUMALIKE_TOKEN = "your-token"
```

Then create a client at your application boundary:

```python
from humalike import HumalikeClient

with HumalikeClient.from_env() as huma:
    identity = huma.whoami()
    print(f"authenticated: {bool(identity.get('user_id'))}")
```

`from_env()` reads `HUMALIKE_TOKEN` by default. Pass a variable name explicitly
if your application uses a different one.

## Using an API family

Endpoint helpers return dictionaries with public `TypedDict` annotations, with
documented nullable cases. For example, `get_report(...)` returns
`StoredReportResponse | None`. Social Learning accepts a conversation and
returns the service's profile data unchanged. The call below is real and may
consume credits; use the gated executable in `examples/social_learning.py`
before adapting it:

```python
from humalike import HumalikeClient

messages = [
    {"id": "m1", "speaker": "ada", "text": "yo still on for tonight"},
    {"id": "m2", "speaker": "max", "text": "ye 8 same spot"},
]

with HumalikeClient.from_env() as huma:
    result = huma.extract_profile(messages, source="discord")
    print(result.get("prompt_block"))
```

Some API methods may consume credits. Check Humalike's official
[credits and billing documentation](https://docs.humalike.com/credits-and-billing)
before running live examples or adding a call to an application.

The async client exposes the same endpoint method names:

```python
import asyncio

from humalike import AsyncHumalikeClient


async def main() -> None:
    async with AsyncHumalikeClient.from_env() as huma:
        identity = await huma.whoami()
        print(f"authenticated: {bool(identity.get('user_id'))}")


asyncio.run(main())
```

## API coverage

| Family | Client methods | Cost and state |
|---|---|---|
| Account | `whoami`, `usage_summary` | Non-billable, read-only account calls |
| Social Learning | `extract_profile` | Billable analysis |
| Social Observability | `analyze_transcript`, `get_report` | Billable analysis; read-only report lookup |
| Theory of Mind | `foresee_reply` | Billable analysis |
| Social Memory | `ingest_memory`, `recall_memory`, `ask_memory` | Persistent, non-billable ingest; billable reads |
| Personas | generate, enhance, and validate start/get/wait methods | Billable starts; read-only polling |
| Turn-Taking | `open_thread`, `submit_messages`, `record_event`, `respond` | Stateful; conditional billing described below |
| Realtime | async `connect_turn_taking` and `TurnTakingStream` | Streams messages already scheduled by Turn-Taking |

`open_thread` and `record_event` are not billable. `submit_messages` is billable
unless short-circuited by `skip_decide` or media; `respond` is billable unless
the reply is superseded. Billing behavior can change, so the official billing
documentation remains authoritative.

See the [API reference](docs/API_REFERENCE.md) for signatures, return types,
polling behavior, low-level requests, and capability protocols.

## Retry and idempotency policy

Automatic retries are limited to safe reads, documented read-like account
preflights, and Social Memory ingest carrying an `Idempotency-Key`. Other
mutating or potentially billable POST requests are not replayed automatically.

For durable Social Memory ingest retries, persist the key in your application:

```python
result = huma.ingest_memory(
    "discord:guild-17:channel-4",
    [{"speaker": "alice", "text": "I cannot eat peanuts"}],
    idempotency_key="conversation-import:batch-0042",
)
```

If a mutating request times out, the SDK surfaces the ambiguity to the caller.
Do not retry blindly unless the endpoint has a confirmed server-side replay
identity. Humalike documents replaying the same `submit_messages` batch as
idempotent, but the public request has no stable replay key. In a controlled
2026-07-12 live check with SDK retries disabled, the original synthetic batch
and its exact replay each settled as one `turn-taking` call and one credit, and
the replay advanced `turn_epoch`. This does not prove duplicate message storage,
but it does prove repeated decision cost and turn-state advancement. The
high-level method therefore defaults to `retry=False`; callers that accept the
documented contract can opt in explicitly with `retry=True`. `respond` remains
non-retryable by default.

Humalike also documents `respond` as idempotent. In an earlier controlled exact
replay, the same thread, epoch, content, and agent produced different scheduled
message IDs and another settled charge. This is one synthetic observation, not
a pricing claim, but it means the SDK cannot safely automate `respond` replay.
After an ambiguous timeout, reconcile application state instead of resubmitting
the draft blindly.

## Errors

SDK transport, API, protocol, and operation exceptions derive from
`HumalikeError`. Local configuration or argument checks raise `ValueError`, and
using realtime support without the optional WebSocket dependency raises
`RuntimeError`. SDK exception categories are:

- `AuthenticationError`, `PaymentRequiredError`, `PermissionDeniedError`, and
  `ValidationError` for actionable API responses;
- `HumalikeAPIError` for other API failures and `UpstreamError` for HTTP 5xx;
- `APITimeoutError` and `APIConnectionError` for transport failures;
- `ProtocolError` for response contracts the SDK validates explicitly, including
  JSON framing, stable Persona operation and Turn-Taking decision envelopes,
  and realtime event envelopes;
- `OperationFailedError` and `OperationTimeoutError` for Persona polling.

The original `httpx` exception is retained as `__cause__` where applicable.

A product can degrade on exhausted availability failures while keeping
configuration, payment, input, and contract failures visible:

```python
from collections.abc import Mapping, Sequence
from typing import Any

from humalike import (
    APIConnectionError,
    AuthenticationError,
    PaymentRequiredError,
    PermissionDeniedError,
    ProtocolError,
    SocialLearningClient,
    SocialLearningResponse,
    UpstreamError,
    ValidationError,
)


def optional_profile(
    client: SocialLearningClient,
    messages: Sequence[Mapping[str, Any]],
) -> SocialLearningResponse | None:
    try:
        return client.extract_profile(messages)
    except (APIConnectionError, UpstreamError):
        return None  # application-defined availability fallback
    except (
        AuthenticationError,
        PermissionDeniedError,
        PaymentRequiredError,
        ValidationError,
        ProtocolError,
    ):
        raise  # configuration, account, input, or contract action is required
```

Treat the visible branches differently:

- authentication or permission: stop and fix the token or entitlement;
- payment: do not retry; disable the feature or replenish the account;
- validation: correct the request before trying again;
- protocol: preserve the response metadata and investigate a contract change.

`APITimeoutError` is an `APIConnectionError`. API response errors expose
`status_code`, `code`, `message`, `details`, and `trace_id`. A Persona
`OperationTimeoutError` stops local polling but does not cancel the remote job;
save its operation ID and resume polling. `OperationFailedError` is terminal for
that operation. A timeout after a mutation is ambiguous and must not be treated
as proof that the server did nothing.

Public SDK exceptions support pickle round-trips for multiprocessing and job
queues. Serialized exceptions retain their diagnostic fields and must be
handled as sensitive data; only `repr()` is redacted.

## Building products

Product logic can depend on the smallest capability protocol it needs instead
of constructing the full client internally:

```python
from collections.abc import Mapping, Sequence
from typing import Any

from humalike import SocialObservabilityClient, SocialObservabilityResponse


def build_report(
    client: SocialObservabilityClient,
    messages: Sequence[Mapping[str, Any]],
) -> SocialObservabilityResponse:
    return client.analyze_transcript(messages, agent_name="support-agent")
```

This makes an application-specific test double or graceful-degradation adapter
easy to inject.
Authentication, payment, validation, and protocol failures should remain
visible; availability failures may use a product-defined fallback.

## Examples

Every script in the [examples guide](examples/README.md) calls the real Humalike
API with short fictional inputs. Start with the documented read-only account
methods:

```bash
python examples/quickstart.py
python examples/async_quickstart.py
python examples/response_metadata.py
```

Starting a stateful or billable example requires an explicit
`--allow-billable` acknowledgement. Resuming an existing Persona operation is
the documented exception because it does not start a new job. The suite covers
Social Learning, Social Observability, Theory of Mind, Social Memory, Personas,
and Turn-Taking with real WebSocket delivery. All nine entry points were
live-validated on 2026-07-12; the guide records the narrowly scoped usage
observation and its limitations.

## Development

```bash
python -m pip install -e ".[dev]"
pytest --cov=humalike --cov-fail-under=88
ruff check .
ruff format --check .
mypy src examples
python -m build
```

Tests must not read credentials or contact the live API. See
[Contributing](CONTRIBUTING.md) and [Security](SECURITY.md) before submitting a
change. The project is licensed under the [MIT License](LICENSE).
