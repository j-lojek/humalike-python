"""Analyze how a real synthetic support exchange is landing socially."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from humalike import HumalikeClient, SocialObservabilityClient

MESSAGES = [
    {
        "id": "m1",
        "speaker": "customer",
        "user_id": "synthetic-customer",
        "text": "The export still fails after the first suggestion.",
    },
    {
        "id": "m2",
        "speaker": "support-agent",
        "text": "Please repeat the same steps once more.",
    },
    {
        "id": "m3",
        "speaker": "customer",
        "user_id": "synthetic-customer",
        "text": "I already did that twice, so I will leave it for now.",
    },
]


def run(client: SocialObservabilityClient) -> None:
    report = client.analyze_transcript(
        MESSAGES,
        agent_name="support-agent",
        source="humalike-python-example",
        focus="whether the support reply acknowledged the customer's effort",
    )
    print(f"health score: {report.get('health_score', '<not returned>')}")
    print(f"summary: {report.get('summary', '<not returned>')}")
    print(f"findings: {len(report.get('findings', []))}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-billable",
        action="store_true",
        help="acknowledge that this real Social Observability request consumes credits",
    )
    args = parser.parse_args(argv)
    if not args.allow_billable:
        parser.error("this example makes a billable request; pass --allow-billable")
    with HumalikeClient.from_env() as client:
        run(client)


if __name__ == "__main__":
    main()
