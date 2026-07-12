"""Extract a real Social Learning profile from a short synthetic conversation."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from humalike import HumalikeClient, SocialLearningClient

MESSAGES = [
    {"id": "m1", "speaker": "ada", "text": "Could we ship the small fix today?"},
    {"id": "m2", "speaker": "max", "text": "Yes, post a short update first."},
    {"id": "m3", "speaker": "ada", "text": "I will share the test result and merge."},
    {"id": "m4", "speaker": "max", "text": "Perfect, keep the message concise."},
    {"id": "m5", "speaker": "ada", "text": "Done. I will watch errors for an hour."},
]


def run(client: SocialLearningClient) -> None:
    result = client.extract_profile(MESSAGES, source="humalike-python-example")
    print("prompt block:")
    print(result.get("prompt_block", "<not returned>"))
    profile = result.get("profile")
    fields = ", ".join(sorted(profile)) if isinstance(profile, dict) else "<none>"
    print(f"profile fields: {fields}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-billable",
        action="store_true",
        help="acknowledge that this real Social Learning request consumes credits",
    )
    args = parser.parse_args(argv)
    if not args.allow_billable:
        parser.error("this example makes a billable request; pass --allow-billable")
    with HumalikeClient.from_env() as client:
        run(client)


if __name__ == "__main__":
    main()
