"""Generate or resume polling one real fictional Persona population."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from humalike import HumalikeClient, PersonasClient


def run(
    client: PersonasClient,
    *,
    operation_id: str | None = None,
    timeout: float = 900,
) -> None:
    if operation_id is None:
        operation = client.start_population(
            "One fictional member of a small Polish indie-game community",
            count=1,
            grounding="off",
        )
        operation_id = operation.get("id")
    if not isinstance(operation_id, str) or not operation_id:
        raise RuntimeError("Humalike did not return a Persona operation id")
    print(f"operation id (save this to resume): {operation_id}", flush=True)
    population = client.wait_population(operation_id, timeout=timeout, poll_interval=2)
    personas = population.get("personas", [])
    print(f"generated personas: {len(personas)}")
    if personas:
        fields = personas[0].get("fields")
        rendered = ", ".join(sorted(fields)) if isinstance(fields, dict) else "<none>"
        print(f"first persona fields: {rendered}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-billable",
        action="store_true",
        help="acknowledge that starting real Persona generation consumes substantial credits",
    )
    parser.add_argument(
        "--operation-id",
        help="resume polling an existing operation without starting another generation",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=900,
        help="local polling deadline in seconds; timing out does not cancel the remote job",
    )
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.operation_id is None and not args.allow_billable:
        parser.error("starting a Persona job is billable; pass --allow-billable")
    with HumalikeClient.from_env() as client:
        run(client, operation_id=args.operation_id, timeout=args.timeout)


if __name__ == "__main__":
    main()
