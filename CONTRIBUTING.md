# Contributing

This is an unofficial community SDK. Contributions should describe behavior as
documented, observed, or inferred and must not imply Humalike endorsement.

## Development

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
mypy src examples
python -m build
```

Tests must be deterministic, credential-free, and offline. Use
`httpx.MockTransport` or an injected `WebSocketConnector`; never add a live API
call to CI.

## Contract changes

For every endpoint change:

1. cite the public documentation snapshot or a redacted observed response;
2. update sync and async methods together;
3. update the relevant public TypedDict and capability protocol;
4. add payload, error, and retry tests;
5. preserve forward-compatible unknown response fields;
6. state whether the call may be billable or mutate state.

Do not weaken retry safety to make a flaky integration appear reliable. A
timeout after a billable mutation is ambiguous and must reach the application
unless the endpoint has a tested server-side replay identity.
Documented-idempotent endpoints still need a regression test proving the exact
replay boundary before joining the default retry policy.

## Security and privacy

Never include tokens, signed WebSocket URLs, account/resource identifiers, real
transcripts, or raw customer/persona output in commits, issues, test recordings,
or logs. See [SECURITY.md](SECURITY.md).
