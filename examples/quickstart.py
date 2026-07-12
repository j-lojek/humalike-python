"""Authenticate and read real account usage with the synchronous client."""

from __future__ import annotations

from humalike import AccountClient, HumalikeClient


def run(client: AccountClient) -> None:
    identity = client.whoami()
    usage = client.usage_summary()
    print(f"authenticated: {bool(identity.get('user_id'))}")
    print(f"billed calls (30 days): {usage.get('total_calls', '<unknown>')}")
    print(f"credits used (30 days): {usage.get('total_credits', '<unknown>')}")


def main() -> None:
    with HumalikeClient.from_env() as client:
        run(client)


if __name__ == "__main__":
    main()
