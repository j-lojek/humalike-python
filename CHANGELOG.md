# Changelog

All notable changes will be documented here. The project follows Semantic
Versioning after its first public release.

## 0.1.0b1 — 2026-07-12

- Add synchronous and asynchronous clients for every documented HTTP family.
- Add Persona operation polling with bounded deadlines.
- Add safe retry and Social Memory idempotency; keep Turn-Taking message replay
  explicit because live observations cannot prove the documented deduplication.
- Add stable API, transport, protocol, and operation exceptions.
- Add async Turn-Taking WebSocket parsing with signed-URL redaction.
- Add public TypedDict response models and capability protocols.
- Add real API examples with explicit billable-call gates.
- Add product integration guidance and a fully offline test and CI suite.
- Align stored-report, validation, pacing, transcript, and operation models with
  the current public API contract.
- Treat malformed polling payloads as protocol errors and normal WebSocket
  closure as the end of event iteration.
- Document complete method signatures, response models, billing and mutation
  semantics, retry policy, polling recovery, and the WebSocket lifecycle.
- Add offline documentation drift checks for public methods, exports, links,
  safety guidance, and Markdown structure.
- Reject every non-2xx response, including redirects, through the typed API
  error hierarchy, even when an injected HTTPX client enables redirects.
- Bound positive Persona polling budgets across HTTP attempts, retries,
  backoff, response processing, and polling sleeps; cancel overdue async
  attempts and document the synchronous transport boundary.
- Parse both forms of `Retry-After`, separate server/local delay caps, and add
  local backoff jitter.
- Require stable success fields in public response types and validate
  top-level endpoint response objects.
- Validate documented Turn-Taking message and event shapes before network I/O.
- Reject invalid low-level idempotency headers before they can authorize replay.
- Reject decoded path traversal, encoded separators, unsafe resource IDs, and
  caller-controlled transport routing or framing headers before network I/O.
- Return clear validation errors for non-ASCII authentication/header components
  and cap exponential retry math without overflow at extreme retry counts.
- Redact exception representations and isolate optional WebSocket dependency
  errors from connector failures.
- Make all public SDK exceptions pickleable while preserving their concrete
  class, diagnostic fields, and `.args`.
- Validate required Persona operation identity/status fields and the stable
  `submit_messages` decision envelope while preserving unknown response keys.
- Suppress raw WebSocket connect traceback chains that can contain signed grants.
- Scrub signed WebSocket grants from SDK traceback frame locals across URL
  validation, the default connector, both public wrappers, and retained safe
  missing-dependency causes.
- Add minimum-dependency CI, dependency auditing, Dependabot, compile checks,
  package metadata/content checks, and immutable GitHub Action revisions.
