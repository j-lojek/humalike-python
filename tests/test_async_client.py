from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

import httpx
import pytest

from humalike import APITimeoutError, AsyncHumalikeClient, HumalikeClient

T = TypeVar("T")


def run(awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


def make_async_client(
    handler: Callable[[httpx.Request], httpx.Response],
    **kwargs: Any,
) -> AsyncHumalikeClient:
    return AsyncHumalikeClient(
        "test-token-async",
        transport=httpx.MockTransport(handler),
        retry_backoff=0,
        **kwargs,
    )


def test_async_auth_payload_repr_and_close() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"profile": {}, "prompt_block": "short"})

    async def scenario() -> None:
        async with make_async_client(handler) as client:
            result = await client.extract_profile(
                [{"id": "m1", "speaker": "ada", "text": "yo"}],
                source="fixture",
            )
            assert result["prompt_block"] == "short"
            assert repr(client) == "AsyncHumalikeClient(token='<redacted>')"

    run(scenario())
    request = seen[0]
    assert request.headers["authorization"] == "Bearer test-token-async"
    assert request.url.path == "/v1/social-learning/actions/extract"
    assert json.loads(request.content) == {
        "transcript": {
            "messages": [{"id": "m1", "speaker": "ada", "text": "yo"}],
            "source": "fixture",
        }
    }


def test_async_safe_retry_and_sleep() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(502, headers={"Retry-After": "0.4"})
        return httpx.Response(200, json={"user_id": "ok"})

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async def scenario() -> None:
        client = make_async_client(handler, sleep=sleep)
        try:
            assert await client.whoami() == {"user_id": "ok"}
        finally:
            await client.close()

    run(scenario())
    assert calls == 2
    assert sleeps == [0.4]


def test_async_billable_timeout_is_wrapped_and_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("lost", request=request)

    async def scenario() -> None:
        client = make_async_client(handler)
        try:
            with pytest.raises(APITimeoutError) as exc_info:
                await client.start_population("one fictional person")
            assert isinstance(exc_info.value.__cause__, httpx.ReadTimeout)
        finally:
            await client.close()

    run(scenario())
    assert calls == 1


def test_async_polling_returns_terminal_result() -> None:
    responses = iter(
        [
            {"id": "op-1", "status": "running"},
            {"id": "op-1", "status": "succeeded", "result": {"personas": []}},
        ]
    )
    now = [0.0]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    async def sleep(seconds: float) -> None:
        now[0] += seconds

    async def scenario() -> None:
        client = make_async_client(handler, sleep=sleep, monotonic=lambda: now[0])
        try:
            result = await client.wait_population("op-1", poll_interval=0.25)
            assert result == {"personas": []}
        finally:
            await client.close()

    run(scenario())
    assert now == [0.25]


def test_async_rejects_per_request_authorization_override() -> None:
    client = make_async_client(lambda _: httpx.Response(200, json={}))

    async def scenario() -> None:
        try:
            with pytest.raises(ValueError, match="Authorization"):
                await client.request(
                    "GET",
                    "/v1/example",
                    headers={"Authorization": "Bearer attacker"},
                )
        finally:
            await client.close()

    run(scenario())


def test_sync_and_async_endpoint_signatures_stay_in_parity() -> None:
    endpoint_methods = {
        "analyze_transcript",
        "ask_memory",
        "extract_profile",
        "foresee_reply",
        "get_enhancement",
        "get_population",
        "get_report",
        "get_validation",
        "ingest_memory",
        "open_thread",
        "recall_memory",
        "record_event",
        "request",
        "request_with_response",
        "respond",
        "start_enhancement",
        "start_population",
        "start_validation",
        "submit_messages",
        "usage_summary",
        "wait_enhancement",
        "wait_population",
        "wait_validation",
        "whoami",
    }

    for name in endpoint_methods:
        sync_method = getattr(HumalikeClient, name)
        async_method = getattr(AsyncHumalikeClient, name)
        assert not inspect.iscoroutinefunction(sync_method)
        assert inspect.iscoroutinefunction(async_method)
        assert list(inspect.signature(sync_method).parameters) == list(
            inspect.signature(async_method).parameters
        )


def test_async_request_with_response_preserves_metadata() -> None:
    client = make_async_client(
        lambda _: httpx.Response(
            200,
            headers={"Location": "/private", "X-Trace-ID": "trace-1"},
            json={"private": True},
        )
    )

    async def scenario() -> None:
        try:
            response = await client.request_with_response("GET", "/v1/example")
            assert response.data == {"private": True}
            assert response.headers["location"] == "/private"
            assert response.request_id == "trace-1"
            assert "private" not in repr(response)
        finally:
            await client.close()

    run(scenario())


def test_async_client_exposes_turn_taking_stream() -> None:
    class Connection:
        closed = False

        async def recv(self) -> str:
            return (
                '{"type":"attached","channel":"turn-taking-thread/test",'
                '"server_time":"2026-07-12T12:00:00Z","data":{}}'
            )

        async def close(self) -> None:
            self.closed = True

    connection = Connection()

    async def connector(_: str) -> Connection:
        return connection

    client = make_async_client(lambda _: httpx.Response(200, json={}))

    async def scenario() -> None:
        try:
            stream = await client.connect_turn_taking(
                {"realtime": {"connect_url": "wss://example.test/ws?c=fake"}},
                connector=connector,
            )
            assert (await stream.recv()).type == "attached"
            await stream.close()
        finally:
            await client.close()

    run(scenario())
    assert connection.closed
