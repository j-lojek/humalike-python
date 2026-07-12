"""Review a draft with the real Theory of Mind API before sending it."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from humalike import HumalikeClient, TheoryOfMindClient

TRANSCRIPT = [
    {"speaker": "customer", "text": "The export still fails in Chrome."},
    {"speaker": "agent", "text": "Did you check the popup icon?"},
    {"speaker": "customer", "text": "There is no popup icon. I will try another day."},
]


def run(client: TheoryOfMindClient) -> None:
    result = client.foresee_reply(
        TRANSCRIPT,
        candidate_reply="No problem. Contact us again if it still fails.",
        agent_name="agent",
        system_prompt="You are a concise support agent who takes ownership of unresolved issues.",
        subject_name="customer",
    )
    print(f"refined reply: {result.get('refined_reply', '<not returned>')}")
    print(f"rationale: {result.get('refinement_rationale', '<not returned>')}")
    reactions = result.get("predicted_reaction", [])
    if reactions:
        print(f"predicted risk: {reactions[0].get('risk', '<not returned>')}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-billable",
        action="store_true",
        help="acknowledge that this real Theory of Mind request consumes credits",
    )
    args = parser.parse_args(argv)
    if not args.allow_billable:
        parser.error("this example makes a billable request; pass --allow-billable")
    with HumalikeClient.from_env() as client:
        run(client)


if __name__ == "__main__":
    main()
