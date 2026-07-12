# Security policy

This is a community project, not an official Humalike SDK or security channel.

- Never put a Humalike token in source, fixtures, CLI arguments, URLs or issue
  bodies. Use `HUMALIKE_TOKEN` in the local process environment.
- The client accepts only HTTPS API origins without embedded credentials, paths
  or query strings. Raw authenticated requests accept only canonical relative
  `/v1/...` paths: decoded traversal, encoded separators, backslashes, and
  controls are rejected. Per-request callers cannot replace authentication,
  authority, framing, proxy-authentication, or hop-by-hop transport headers.
  Redirect following is disabled per request, even on an injected HTTPX client,
  so authenticated calls cannot escape the validated API path through a `3xx`.
- Automatic retries are limited to safe reads, free account preflights, and
  Social Memory ingest requests carrying `Idempotency-Key`. `submit_messages`
  requires explicit retry opt-in because the public request has no stable replay
  identity. Do not opt another billable mutation into retry unless its replay
  semantics are independently confirmed.
- Turn-Taking accepts only `wss://` grants. Signed connection URLs and event
  payloads are redacted from object representations and must never be logged.
  Connect failures suppress the raw connector traceback because it may repeat
  the complete signed grant URL. SDK-owned connect and validation frames also
  overwrite grant-bearing locals before they unwind, including the retained
  safe missing-dependency cause. Custom connectors remain responsible for
  redacting their own logs and retained state.
- Injected HTTP and WebSocket transports are trusted application boundaries;
  inject only transports created by the caller, never values selected by an
  untrusted user.
- Treat API errors, trace IDs and response objects as potentially sensitive.

If a key is exposed, revoke or rotate it before debugging further.

## Reporting a vulnerability

Use **Report a vulnerability** in the repository's Security tab after GitHub
Private Vulnerability Reporting is enabled. If that private form is unavailable,
contact the repository owner and Humalike through a verified private channel;
do not open a public issue containing a working token, real transcript, resource
identifier, or exploit payload.
