# Product integration

Keep the Humalike wire contract at the application boundary. Product services
should depend on the smallest SDK capability protocol they need and receive the
client through dependency injection.

```text
application entry point
  ├── creates HumalikeClient or AsyncHumalikeClient
  └── injects a capability protocol into product code
        ├── real SDK client in production
        └── test-only adapter or product fallback
```

## Graceful degradation

Humalike can be an optional behavioral enhancement rather than an application
availability dependency. The product should define its own fallback explicitly:

```python
from collections.abc import Mapping, Sequence
from typing import Any

from humalike import APIConnectionError, SocialLearningClient, UpstreamError


def voice_card(
    client: SocialLearningClient | None,
    messages: Sequence[Mapping[str, Any]],
) -> str | None:
    if client is None:
        return None
    try:
        result = client.extract_profile(messages)
    except (APIConnectionError, UpstreamError):
        return None
    return result.get("prompt_block")
```

Do not treat authentication, payment, validation, or protocol errors as normal
availability failures. They usually require a configuration, account, input, or
contract fix. `APITimeoutError` is already covered by `APIConnectionError`;
`UpstreamError` covers an HTTP upstream failure after any safe SDK retries are
exhausted.

## Local checkout or Git submodule

A product can vendor a source checkout under a stable path such as
`vendor/humalike-python`:

```bash
python -m pip install -e ./vendor/humalike-python
python -m pip install -e .
```

For CI with a Git submodule:

```bash
git submodule update --init --recursive
python -m pip install ./vendor/humalike-python
python -m pip install .
pytest
```

Do not place a relative filesystem path in published package dependencies; that
produces a non-portable wheel. Install the vendored SDK as a bootstrap step.
After a registry package is published, prefer a bounded package dependency and
update it deliberately alongside contract changes. Use only the real published
package or repository address; no address is shown here until one exists.

## Product tests

Implement only the capability protocol needed by the product and keep test-only
adapters under that product's test tree. For WebSocket tests, inject a callable
matching `WebSocketConnector`. No unit test should require credentials or
network access; the public scripts in `examples/` are reserved for real API
requests.

## Ownership boundaries

- The SDK owns authentication, transport, payloads, errors, polling, and safe
  retry/idempotency mechanics.
- The product owns prompts, persistence, privacy choices, credit policy, UI,
  fallbacks, and decisions made from Humalike output.
- A conformance harness owns guarded live probes and records observed contract
  discrepancies without changing SDK behavior speculatively.
