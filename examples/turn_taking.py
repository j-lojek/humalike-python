"""Schedule a real paced reply and receive it over the Turn-Taking WebSocket."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from humalike import AsyncHumalikeClient, AsyncTurnTakingClient


async def run(client: AsyncTurnTakingClient, *, receive_timeout: float = 30) -> None:
    opened = await client.open_thread(enable_social_signals=True)
    thread_id = opened.get("thread", {}).get("id")
    if not isinstance(thread_id, str) or not thread_id:
        raise RuntimeError("Humalike did not return a thread id")

    async with await client.connect_turn_taking(opened) as stream:
        attached = await stream.recv(timeout=receive_timeout)
        event_result = await client.record_event(thread_id, "typing_start", "customer")
        decision = await client.submit_messages(
            thread_id,
            [{"sender": "customer", "content": "Can you help with an export error?"}],
            skip_decide=True,
        )
        turn_epoch = decision.get("turn_epoch")
        if not isinstance(turn_epoch, int):
            raise RuntimeError("Humalike did not return a turn epoch")
        response = await client.respond(
            thread_id,
            "Yes. Tell me the file type and what happens when you click export.",
            turn_epoch,
            agent_name="support-agent",
            pacing={"typing_wpm": 500, "max_typing_ms": 2500},
            metadata={"example": "humalike-python"},
        )

        scheduled_count = len(response.get("scheduled", []))
        if scheduled_count == 0:
            raise RuntimeError("Humalike did not schedule any messages")
        received_messages = 0
        event_types = [attached.type]
        while received_messages < scheduled_count:
            event = await stream.recv(timeout=receive_timeout)
            event_types.append(event.type)
            if event.type == "turn_taking.message":
                received_messages += 1
                print(f"message {received_messages}: {event.data.get('content', '<not returned>')}")

    print(f"event tags: {event_result.get('tags', [])}")
    print(f"decision: {decision.get('decision', '<not returned>')}")
    print(f"scheduled messages: {scheduled_count}")
    print(f"event types: {', '.join(event_types)}")


async def async_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-billable",
        action="store_true",
        help="acknowledge remote writes, billable respond, and a real WebSocket connection",
    )
    args = parser.parse_args(argv)
    if not args.allow_billable:
        parser.error(
            "this example writes remote state and calls billable respond; pass --allow-billable"
        )
    async with AsyncHumalikeClient.from_env() as client:
        await run(client)


def main(argv: Sequence[str] | None = None) -> None:
    asyncio.run(async_main(argv))


if __name__ == "__main__":
    main()
