# Real API examples

Every Python script in this directory uses `HumalikeClient.from_env()` or
`AsyncHumalikeClient.from_env()` and sends requests to the real Humalike API.
The inputs are short, fictional conversations created for these examples.

Set the token in the process environment; the SDK does not load `.env` files:

```bash
export HUMALIKE_TOKEN="your-token"
```

```powershell
$env:HUMALIKE_TOKEN = "your-token"
```

## Read-only start

These documented account reads are not billable and do not mutate remote
conversation state:

```bash
python examples/quickstart.py
python examples/async_quickstart.py
python examples/response_metadata.py
```

| Example | Real API behavior |
|---|---|
| [`quickstart.py`](quickstart.py) | Sync authentication and account usage |
| [`async_quickstart.py`](async_quickstart.py) | Async authentication and account usage |
| [`response_metadata.py`](response_metadata.py) | Status, request ID, and decoded authentication state |

## Stateful or billable examples

Each command below starts a remote stateful or billable workflow and refuses to
run unless `--allow-billable` is present:

```bash
python examples/social_learning.py --allow-billable
python examples/social_observability.py --allow-billable
python examples/theory_of_mind.py --allow-billable
python examples/social_memory.py --allow-billable
python examples/personas.py --allow-billable
python examples/turn_taking.py --allow-billable
```

| Example | Real API behavior |
|---|---|
| [`social_learning.py`](social_learning.py) | Extract a norms profile and prompt block |
| [`social_observability.py`](social_observability.py) | Analyze reception of a support exchange |
| [`theory_of_mind.py`](theory_of_mind.py) | Predict reaction and refine a draft |
| [`social_memory.py`](social_memory.py) | Idempotent ingest followed by recall and ask |
| [`personas.py`](personas.py) | Start and poll a one-person fictional population |
| [`turn_taking.py`](turn_taking.py) | Open a thread, record activity, respond, and receive WebSocket events |

Turn-Taking WebSocket delivery needs the optional dependency:

```bash
python -m pip install ".[websocket]"
```

## Check usage around a paid example

The usage endpoint reports recent billed spend, not a remaining balance or a
pre-call quote. Capture the totals before and after one gated example:

```bash
python examples/quickstart.py
python examples/social_learning.py --allow-billable
python examples/quickstart.py
```

Component accounting can settle with delay. If the second snapshot has not
changed, wait briefly and read usage again; do not infer that the call was free.

Persona generation can take materially longer and consume substantially more
credits than the other examples. If a local process is interrupted after the
job starts, copy the operation ID printed before polling and resume the existing
operation instead of starting another one. Resuming does not require
`--allow-billable` because it does not start a new generation:

```bash
python examples/personas.py --operation-id "existing-operation-id"
```

The example's local polling deadline defaults to 900 seconds and can be changed
with `--timeout SECONDS`. Reaching it raises `OperationTimeoutError` but does
not cancel the remote job. Resume with the printed ID instead of paying to
start a replacement.

`social_memory.py` creates a unique remote scope and ingests synthetic messages.
The public API has no clear or delete operation, so that scope remains stored
after the script exits.

In `turn_taking.py`, a WebSocket receive timeout after `respond` returned
scheduled messages does not mean scheduling failed. Do not rerun the entire
flow blindly: a new run opens another thread and can incur another billable
`respond`.

## Live validation

All nine entry points above were run successfully against the public API on
2026-07-12. The three account examples produced no observed credit charge; the
six gated examples returned populated response fields, and Turn-Taking received
the scheduled reply over its real WebSocket connection.

That single synthetic smoke run consumed 728 credits: 495 for one Persona, 217
for Social Learning, and 16 across the other APIs. This is a bounded observation
from one account and input set, not a price quote or an estimate for future
runs. Usage can change with inputs and service behavior.

Costs are input-dependent and the public usage endpoint does not provide a
pre-call quote. Review Humalike's official
[credits and billing documentation](https://docs.humalike.com/credits-and-billing),
use a dedicated test account when possible, and inspect generated output before
logging or sharing it. A successful example run is not an SLA or pricing
guarantee.
