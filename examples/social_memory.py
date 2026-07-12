"""Ingest synthetic messages, then perform real Social Memory reads."""

from __future__ import annotations

import argparse
import uuid
from collections.abc import Sequence

from humalike import HumalikeClient, SocialMemoryClient


def run(client: SocialMemoryClient, *, scope_id: str | None = None) -> None:
    scope = scope_id or f"humalike-python-example-{uuid.uuid4().hex}"
    key = f"{scope}:batch-1"
    transcript = [
        {"speaker": "ada", "text": "I cannot eat peanuts."},
        {"speaker": "max", "text": "Understood, I will avoid peanut dishes."},
    ]
    first = client.ingest_memory(scope, transcript, idempotency_key=key)
    replay = client.ingest_memory(scope, transcript, idempotency_key=key)
    recalled = client.recall_memory(
        scope,
        {"speaker": "max", "text": "What food should I bring for the group?"},
    )
    answer = client.ask_memory(scope, "What food constraint did Ada mention?")
    print(f"ingested messages: {first.get('ingested', '<not returned>')}")
    print(f"idempotent replay matched: {replay == first}")
    print(f"recalled context: {recalled.get('context', '<not returned>')}")
    print(f"memory answer: {answer.get('answer', '<not returned>')}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-billable",
        action="store_true",
        help="acknowledge remote writes plus billable recall and ask requests",
    )
    args = parser.parse_args(argv)
    if not args.allow_billable:
        parser.error(
            "this example writes remote state and makes billable reads; pass --allow-billable"
        )
    with HumalikeClient.from_env() as client:
        run(client)


if __name__ == "__main__":
    main()
