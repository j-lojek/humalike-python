"""Authenticate and read real account usage with the asynchronous client."""

from __future__ import annotations

import asyncio

from humalike import AsyncAccountClient, AsyncHumalikeClient


async def run(client: AsyncAccountClient) -> None:
    identity = await client.whoami()
    usage = await client.usage_summary()
    print(f"authenticated: {bool(identity.get('user_id'))}")
    print(f"credits used (30 days): {usage.get('total_credits', '<unknown>')}")


async def main() -> None:
    async with AsyncHumalikeClient.from_env() as client:
        await run(client)


if __name__ == "__main__":
    asyncio.run(main())
