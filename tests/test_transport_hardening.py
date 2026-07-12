from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from humalike import (
    AsyncHumalikeClient,
    HumalikeAPIError,
    HumalikeClient,
    OperationTimeoutError,
    ProtocolError,
)
from humalike._transport import retry_delay


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    async def async_sleep(self, seconds: float) -> None:
        self.sleep(seconds)


@pytest.mark.parametrize("status", [199, 300, 301, 307, 308, 399, 400, 599])
def test_sync_rejects_every_non_2xx_status(status: int) -> None:
    client = HumalikeClient(
        "test-token",
        max_retries=0,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status, json={"redirect_or_error": True})
        ),
    )
    try:
        with pytest.raises(HumalikeAPIError) as raised:
            client.request("GET", "/v1/example")
        assert raised.value.status_code == status
    finally:
        client.close()


@pytest.mark.parametrize("status", [199, 300, 301, 307, 308, 399, 400, 599])
def test_async_rejects_every_non_2xx_status(status: int) -> None:
    async def scenario() -> None:
        client = AsyncHumalikeClient(
            "test-token",
            max_retries=0,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(status, json={"redirect_or_error": True})
            ),
        )
        try:
            with pytest.raises(HumalikeAPIError) as raised:
                await client.request("GET", "/v1/example")
            assert raised.value.status_code == status
        finally:
            await client.close()

    asyncio.run(scenario())


def test_sync_disables_redirects_on_an_injected_client() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/example":
            return httpx.Response(307, headers={"Location": "/admin"})
        return httpx.Response(200, json={"unexpected": True})

    with httpx.Client(
        follow_redirects=True,
        transport=httpx.MockTransport(handler),
    ) as http_client:
        client = HumalikeClient(
            "test-token",
            max_retries=0,
            http_client=http_client,
        )

        with pytest.raises(HumalikeAPIError) as raised:
            client.request("GET", "/v1/example")

    assert raised.value.status_code == 307
    assert [request.url.path for request in requests] == ["/v1/example"]


def test_async_disables_redirects_on_an_injected_client() -> None:
    async def scenario() -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/v1/example":
                return httpx.Response(307, headers={"Location": "/admin"})
            return httpx.Response(200, json={"unexpected": True})

        async with httpx.AsyncClient(
            follow_redirects=True,
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = AsyncHumalikeClient(
                "test-token",
                max_retries=0,
                http_client=http_client,
            )

            with pytest.raises(HumalikeAPIError) as raised:
                await client.request("GET", "/v1/example")

        assert raised.value.status_code == 307
        assert [request.url.path for request in requests] == ["/v1/example"]

    asyncio.run(scenario())


def test_retry_after_supports_delta_seconds_and_http_date_with_fixed_time() -> None:
    now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc).timestamp()
    delta = httpx.Response(503, headers={"Retry-After": "4.5"})
    future_date = httpx.Response(
        503,
        headers={"Retry-After": "Sun, 12 Jul 2026 12:00:09 GMT"},
    )
    past_date = httpx.Response(
        503,
        headers={"Retry-After": "Sun, 12 Jul 2026 11:59:00 GMT"},
    )

    assert retry_delay(0, delta, backoff=0.25, now=now) == 4.5
    assert retry_delay(0, future_date, backoff=0.25, now=now) == 9.0
    assert retry_delay(0, past_date, backoff=0.25, now=now) == 0.0


def test_retry_delay_separates_server_cap_and_jitters_local_backoff() -> None:
    server = httpx.Response(503, headers={"Retry-After": "120"})
    assert retry_delay(0, server, backoff=1, retry_after_maximum=60) == 60
    assert retry_delay(1, None, backoff=2, random_value=0.5) == pytest.approx(4.2)
    assert retry_delay(9, None, backoff=2, random_value=1) == 30


def test_retry_delay_caps_before_an_exponential_overflow() -> None:
    assert retry_delay(10**100, None, backoff=0.25, random_value=0) == 30


def test_extreme_max_retries_value_does_not_break_a_successful_request() -> None:
    client = HumalikeClient(
        "test-token",
        max_retries=10**100,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})),
    )
    try:
        assert client.request("GET", "/v1/example") == {}
    finally:
        client.close()


@pytest.mark.parametrize(
    ("response_headers", "options", "expected_delay"),
    [
        ({"Retry-After": "120"}, {"retry_after_max": 3}, 3),
        ({}, {"retry_backoff": 10, "retry_backoff_max": 2, "retry_jitter": 0}, 2),
    ],
)
def test_sync_client_uses_separate_configurable_retry_delay_caps(
    response_headers: dict[str, str],
    options: dict[str, Any],
    expected_delay: float,
) -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, headers=response_headers)
        return httpx.Response(200, json={"user_id": "ok"})

    client = HumalikeClient(
        "test-token",
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        **options,
    )
    try:
        assert client.whoami()["user_id"] == "ok"
    finally:
        client.close()
    assert sleeps == [expected_delay]


WAIT_CASES = [
    ("wait_population", "result"),
    ("wait_enhancement", "persona"),
    ("wait_validation", "result"),
]


@pytest.mark.parametrize(("method_name", "result_field"), WAIT_CASES)
def test_sync_positive_polling_deadline_rejects_a_late_terminal_response(
    method_name: str,
    result_field: str,
) -> None:
    clock = Clock()

    def handler(_: httpx.Request) -> httpx.Response:
        clock.now = 1.01
        return httpx.Response(
            200,
            json={"id": "operation-1", "status": "succeeded", result_field: {}},
        )

    client = HumalikeClient(
        "test-token",
        timeout=0.75,
        transport=httpx.MockTransport(handler),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    try:
        with pytest.raises(OperationTimeoutError):
            getattr(client, method_name)("operation-1", timeout=1, poll_interval=0.1)
    finally:
        client.close()


@pytest.mark.parametrize(("method_name", "result_field"), WAIT_CASES)
def test_async_positive_polling_deadline_rejects_a_late_terminal_response(
    method_name: str,
    result_field: str,
) -> None:
    async def scenario() -> None:
        clock = Clock()

        def handler(_: httpx.Request) -> httpx.Response:
            clock.now = 1.01
            return httpx.Response(
                200,
                json={"id": "operation-1", "status": "succeeded", result_field: {}},
            )

        client = AsyncHumalikeClient(
            "test-token",
            transport=httpx.MockTransport(handler),
            monotonic=clock.monotonic,
            sleep=clock.async_sleep,
        )
        try:
            with pytest.raises(OperationTimeoutError):
                await getattr(client, method_name)(
                    "operation-1",
                    timeout=1,
                    poll_interval=0.1,
                )
        finally:
            await client.close()

    asyncio.run(scenario())


def test_async_positive_polling_deadline_cancels_an_inflight_attempt() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(60)
        return httpx.Response(
            200,
            json={"id": "operation-1", "status": "succeeded", "result": {}},
        )

    async def scenario() -> None:
        client = AsyncHumalikeClient(
            "test-token",
            max_retries=0,
            transport=httpx.MockTransport(handler),
        )
        started = time.monotonic()
        try:
            with pytest.raises(OperationTimeoutError):
                await client.wait_population(
                    "operation-1",
                    timeout=0.01,
                    poll_interval=0.1,
                )
        finally:
            await client.close()
        assert time.monotonic() - started < 0.5

    asyncio.run(scenario())


@pytest.mark.parametrize(("method_name", "result_field"), WAIT_CASES)
def test_sync_zero_timeout_allows_exactly_one_initial_probe(
    method_name: str,
    result_field: str,
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={"id": "operation-1", "status": "succeeded", result_field: {}},
        )

    client = HumalikeClient("test-token", transport=httpx.MockTransport(handler))
    try:
        assert getattr(client, method_name)("operation-1", timeout=0) == {}
    finally:
        client.close()
    assert calls == 1


def test_zero_timeout_running_probe_does_not_sleep_or_fetch_again() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"id": "operation-1", "status": "running"})

    client = HumalikeClient(
        "test-token",
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    )
    try:
        with pytest.raises(OperationTimeoutError):
            client.wait_population("operation-1", timeout=0)
    finally:
        client.close()
    assert calls == 1
    assert sleeps == []


def test_sync_polling_passes_declining_remaining_budget_as_http_timeout() -> None:
    clock = Clock()
    request_timeouts: list[float] = []
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        timeout = request.extensions["timeout"]
        request_timeouts.append(float(timeout["read"]))
        if calls == 1:
            return httpx.Response(200, json={"id": "operation-1", "status": "running"})
        return httpx.Response(
            200,
            json={"id": "operation-1", "status": "succeeded", "result": {}},
        )

    client = HumalikeClient(
        "test-token",
        timeout=0.75,
        transport=httpx.MockTransport(handler),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    try:
        assert dict(client.wait_population("operation-1", timeout=1, poll_interval=0.4)) == {}
    finally:
        client.close()

    assert request_timeouts == pytest.approx([0.75, 0.6])


def test_sync_retry_backoff_is_capped_by_polling_deadline() -> None:
    clock = Clock()
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": {"message": "retry"}})

    client = HumalikeClient(
        "test-token",
        max_retries=2,
        retry_backoff=2,
        transport=httpx.MockTransport(handler),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    try:
        with pytest.raises(OperationTimeoutError):
            client.wait_population("operation-1", timeout=1)
    finally:
        client.close()

    assert calls == 1
    assert clock.sleeps == [1.0]
    assert clock.now == 1.0


def test_async_polling_budget_and_retry_backoff_are_deadline_bounded() -> None:
    async def scenario() -> None:
        clock = Clock()
        calls = 0
        request_timeouts: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            timeout = request.extensions["timeout"]
            request_timeouts.append(float(timeout["read"]))
            return httpx.Response(503, json={"error": {"message": "retry"}})

        client = AsyncHumalikeClient(
            "test-token",
            max_retries=2,
            retry_backoff=2,
            transport=httpx.MockTransport(handler),
            monotonic=clock.monotonic,
            sleep=clock.async_sleep,
        )
        try:
            with pytest.raises(OperationTimeoutError):
                await client.wait_population("operation-1", timeout=1)
        finally:
            await client.close()

        assert calls == 1
        assert request_timeouts == [1.0]
        assert clock.sleeps == [1.0]

    asyncio.run(scenario())


INVALID_FINITE_VALUES: list[Any] = [True, float("nan"), float("inf"), float("-inf")]


@pytest.mark.parametrize("value", [True, -1, 1.5])
def test_max_retries_requires_a_non_negative_non_bool_integer(value: Any) -> None:
    with pytest.raises(ValueError, match="max_retries"):
        HumalikeClient("test-token", max_retries=value)
    with pytest.raises(ValueError, match="max_retries"):
        AsyncHumalikeClient("test-token", max_retries=value)


@pytest.mark.parametrize("value", [*INVALID_FINITE_VALUES, -0.1])
def test_retry_backoff_must_be_finite_and_non_negative(value: Any) -> None:
    with pytest.raises(ValueError, match="retry_backoff"):
        HumalikeClient("test-token", retry_backoff=value)
    with pytest.raises(ValueError, match="retry_backoff"):
        AsyncHumalikeClient("test-token", retry_backoff=value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("retry_backoff_max", True),
        ("retry_backoff_max", -1),
        ("retry_backoff_max", float("nan")),
        ("retry_after_max", True),
        ("retry_after_max", -1),
        ("retry_after_max", float("inf")),
        ("retry_jitter", True),
        ("retry_jitter", -0.1),
        ("retry_jitter", 1.1),
        ("retry_jitter", float("nan")),
    ],
)
def test_retry_delay_configuration_is_validated(name: str, value: Any) -> None:
    options = {name: value}
    with pytest.raises(ValueError, match=name):
        HumalikeClient("test-token", **options)
    with pytest.raises(ValueError, match=name):
        AsyncHumalikeClient("test-token", **options)


@pytest.mark.parametrize(
    "value",
    [*INVALID_FINITE_VALUES, 0, -1, httpx.Timeout(None)],
)
def test_http_timeout_must_be_finite_and_positive(value: Any) -> None:
    with pytest.raises(ValueError, match="timeout"):
        HumalikeClient("test-token", timeout=value)
    with pytest.raises(ValueError, match="timeout"):
        AsyncHumalikeClient("test-token", timeout=value)


@pytest.mark.parametrize("value", INVALID_FINITE_VALUES)
def test_polling_timeout_and_interval_reject_non_finite_or_bool_values(value: Any) -> None:
    client = HumalikeClient(
        "test-token",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"id": "operation-1", "status": "running"})
        ),
    )
    try:
        with pytest.raises(ValueError, match="timeout"):
            client.wait_population("operation-1", timeout=value)
        with pytest.raises(ValueError, match="poll_interval"):
            client.wait_population("operation-1", poll_interval=value)
    finally:
        client.close()


def test_basic_message_shapes_are_validated_before_network() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client = HumalikeClient("test-token", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match="messages"):
            client.extract_profile("not-a-message-list")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match=r"messages\[0\]"):
            client.extract_profile(["not-an-object"])  # type: ignore[list-item]
        with pytest.raises(ValueError, match="sender"):
            client.record_event("thread", "typing_start", "x" * 256)
        with pytest.raises(ValueError, match="client_ts"):
            client.record_event("thread", "typing_start", "sender", client_ts="")
        with pytest.raises(ValueError, match="event_type"):
            client.record_event("thread", ["typing_start"], "sender")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="grounding"):
            client.start_population("source", grounding=["off"])  # type: ignore[arg-type]
    finally:
        client.close()
    assert calls == 0


def test_poll_interval_must_be_strictly_positive() -> None:
    client = HumalikeClient(
        "test-token",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"id": "operation-1", "status": "running"})
        ),
    )
    try:
        with pytest.raises(ValueError, match="poll_interval"):
            client.wait_population("operation-1", poll_interval=0)
    finally:
        client.close()


def test_basic_retry_bool_and_idempotency_fields_are_validated_before_network() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client = HumalikeClient("test-token", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match="retry"):
            client.request("GET", "/v1/example", retry=1)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="timeout"):
            client.request("GET", "/v1/example", timeout=float("nan"))
        with pytest.raises(ValueError, match="idempotency_key"):
            client.ingest_memory("scope", [{"speaker": "a"}], idempotency_key=" ")
        with pytest.raises(ValueError, match="Idempotency-Key"):
            client.request(
                "POST",
                "/v1/social-memory/actions/ingest",
                json={},
                headers={"Idempotency-Key": ""},
            )
        with pytest.raises(ValueError, match="skip_decide"):
            client.submit_messages(
                "thread",
                [{"sender": "a", "content": "hello"}],
                skip_decide=1,  # type: ignore[arg-type]
            )
        with pytest.raises(ValueError, match="enable_social_signals"):
            client.open_thread(enable_social_signals=1)  # type: ignore[arg-type]
    finally:
        client.close()
    assert calls == 0


def test_async_basic_bool_and_idempotency_fields_are_validated_before_network() -> None:
    async def scenario() -> None:
        calls = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        client = AsyncHumalikeClient(
            "test-token",
            transport=httpx.MockTransport(handler),
        )
        try:
            invalid_calls: list[Callable[[], Awaitable[Any]]] = [
                lambda: client.request("GET", "/v1/example", retry=1),  # type: ignore[arg-type]
                lambda: client.request("GET", "/v1/example", timeout=float("inf")),
                lambda: client.ingest_memory(
                    "scope",
                    [{"speaker": "a"}],
                    idempotency_key=" ",
                ),
                lambda: client.request(
                    "POST",
                    "/v1/social-memory/actions/ingest",
                    json={},
                    headers={"Idempotency-Key": "\n"},
                ),
                lambda: client.submit_messages(
                    "thread",
                    [{"sender": "a", "content": "hello"}],
                    skip_decide=1,  # type: ignore[arg-type]
                ),
                lambda: client.open_thread(enable_social_signals=1),  # type: ignore[arg-type]
            ]
            for call in invalid_calls:
                with pytest.raises(ValueError):
                    await call()
        finally:
            await client.close()
        assert calls == 0

    asyncio.run(scenario())


INVALID_SUBMIT_MESSAGES: list[Any] = [
    [],
    [{"sender": "a", "content": "ok"}] * 21,
    ["not-an-object"],
    [{"sender": "", "content": "ok"}],
    [{"sender": "a" * 256, "content": "ok"}],
    [{"sender": "a", "content": ""}],
    [{"sender": "a", "content": "x" * 4001}],
    [{"sender": "a", "content": "ok", "client_ts": 1}],
    [{"sender": "a", "content": "ok", "has_media": 1}],
]


@pytest.mark.parametrize("messages", INVALID_SUBMIT_MESSAGES)
def test_sync_submit_messages_validates_documented_bounds_before_network(messages: Any) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client = HumalikeClient("test-token", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match="messages"):
            client.submit_messages("thread", messages)
    finally:
        client.close()
    assert calls == 0


def test_sync_submit_messages_does_not_retry_by_default() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": {"message": "ambiguous"}})

    client = HumalikeClient(
        "test-token",
        retry_backoff=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(HumalikeAPIError):
            client.submit_messages(
                "thread",
                [{"sender": "a", "content": "hello"}],
            )
    finally:
        client.close()
    assert calls == 1


def test_async_submit_messages_allows_explicit_retry_opt_in() -> None:
    async def scenario() -> None:
        calls = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503, json={"error": {"message": "retry"}})
            return httpx.Response(
                200,
                json={"decision": "speak", "turn_epoch": 1, "tags": []},
            )

        client = AsyncHumalikeClient(
            "test-token",
            retry_backoff=0,
            transport=httpx.MockTransport(handler),
        )
        try:
            result = await client.submit_messages(
                "thread",
                [{"sender": "a", "content": "hello"}],
                retry=True,
            )
            assert result["turn_epoch"] == 1
        finally:
            await client.close()
        assert calls == 2

    asyncio.run(scenario())


def test_record_event_rejects_undocumented_type_before_network() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client = HumalikeClient("test-token", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match="event_type"):
            client.record_event("thread", "typing", "sender")  # type: ignore[arg-type]
    finally:
        client.close()
    assert calls == 0


@pytest.mark.parametrize("body", [None, [], "text"])
def test_sync_high_level_helpers_require_object_responses(body: Any) -> None:
    client = HumalikeClient(
        "test-token",
        max_retries=0,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
    )
    try:
        with pytest.raises(ProtocolError, match="non-object"):
            client.whoami()
    finally:
        client.close()


@pytest.mark.parametrize("body", [None, [], "text"])
def test_async_high_level_helpers_require_object_responses(body: Any) -> None:
    async def scenario() -> None:
        client = AsyncHumalikeClient(
            "test-token",
            max_retries=0,
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
        )
        try:
            with pytest.raises(ProtocolError, match="non-object"):
                await client.whoami()
        finally:
            await client.close()

    asyncio.run(scenario())


def test_nullable_report_and_low_level_none_remain_supported() -> None:
    client = HumalikeClient(
        "test-token",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=None)),
    )
    try:
        assert client.get_report("missing") is None
        assert client.request("GET", "/v1/example") is None
    finally:
        client.close()


UNSAFE_API_PATHS = [
    "/v1/../admin",
    "/v1/./admin",
    "/v1/foo/../../admin",
    "/v1/%2e%2e/admin",
    "/v1/%2e/admin",
    "/v1/%2E%2E/admin",
    "/v1/foo\\..\\admin",
    "/v1/foo%5c..%5cadmin",
    "/v1/foo%5C..%5Cadmin",
    "/v1/foo%2fbar",
    "/v1/foo%2Fbar",
    "/v1/%00/admin",
    "/v1/%7f/admin",
    "/v1/foo\nbar",
]


@pytest.mark.parametrize("path", UNSAFE_API_PATHS)
def test_sync_rejects_ambiguous_or_traversing_api_paths_before_network(path: str) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client = HumalikeClient("test-token", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match="path"):
            client.request("GET", path)
    finally:
        client.close()
    assert calls == 0


@pytest.mark.parametrize("path", UNSAFE_API_PATHS)
def test_async_rejects_ambiguous_or_traversing_api_paths_before_network(path: str) -> None:
    async def scenario() -> None:
        calls = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        client = AsyncHumalikeClient(
            "test-token",
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(ValueError, match="path"):
                await client.request_with_response("GET", path)
        finally:
            await client.close()
        assert calls == 0

    asyncio.run(scenario())


def test_safe_api_path_keeps_query_and_percent_encoded_data() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = HumalikeClient(
        "test-token",
        transport=httpx.MockTransport(handler),
    )
    try:
        client.request("GET", "/v1/items/r%C3%A9port%20id.v1?include=summary")
    finally:
        client.close()

    assert seen[0].url.raw_path == b"/v1/items/r%C3%A9port%20id.v1?include=summary"


UNSAFE_RESOURCE_IDS = [".", "..", "folder/report", "folder\\report", "report\x00id"]


@pytest.mark.parametrize("resource_id", UNSAFE_RESOURCE_IDS)
def test_sync_resource_ids_cannot_change_endpoint_routing(resource_id: str) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client = HumalikeClient("test-token", transport=httpx.MockTransport(handler))
    try:
        calls_to_check: list[Callable[[], Any]] = [
            lambda: client.get_report(resource_id),
            lambda: client.get_population(resource_id),
            lambda: client.get_enhancement(resource_id),
            lambda: client.get_validation(resource_id),
        ]
        for call in calls_to_check:
            with pytest.raises(ValueError, match="safe single path segment"):
                call()
    finally:
        client.close()
    assert calls == 0


@pytest.mark.parametrize("resource_id", UNSAFE_RESOURCE_IDS)
def test_async_resource_ids_cannot_change_endpoint_routing(resource_id: str) -> None:
    async def scenario() -> None:
        calls = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        client = AsyncHumalikeClient(
            "test-token",
            transport=httpx.MockTransport(handler),
        )
        try:
            calls_to_check: list[Callable[[], Awaitable[Any]]] = [
                lambda: client.get_report(resource_id),
                lambda: client.get_population(resource_id),
                lambda: client.get_enhancement(resource_id),
                lambda: client.get_validation(resource_id),
            ]
            for call in calls_to_check:
                with pytest.raises(ValueError, match="safe single path segment"):
                    await call()
        finally:
            await client.close()
        assert calls == 0

    asyncio.run(scenario())


FORBIDDEN_HEADERS = [
    "Authorization",
    "Proxy-Authorization",
    "Proxy-Authenticate",
    "Host",
    "Content-Length",
    "Transfer-Encoding",
    "Connection",
    "Upgrade",
    "TE",
    "Trailer",
    "Keep-Alive",
]


@pytest.mark.parametrize("header", FORBIDDEN_HEADERS)
def test_sync_rejects_transport_managed_request_headers(header: str) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client = HumalikeClient("test-token", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match="cannot be set per request"):
            client.request("GET", "/v1/example", headers={header.swapcase(): "unsafe"})
    finally:
        client.close()
    assert calls == 0


@pytest.mark.parametrize("header", FORBIDDEN_HEADERS)
def test_async_rejects_transport_managed_request_headers(header: str) -> None:
    async def scenario() -> None:
        calls = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        client = AsyncHumalikeClient(
            "test-token",
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(ValueError, match="cannot be set per request"):
                await client.request(
                    "GET",
                    "/v1/example",
                    headers={f" {header.swapcase()} ": "unsafe"},
                )
        finally:
            await client.close()
        assert calls == 0

    asyncio.run(scenario())


def test_ascii_header_components_fail_locally_with_clear_errors() -> None:
    for client_type in (HumalikeClient, AsyncHumalikeClient):
        with pytest.raises(ValueError, match="token must contain only ASCII"):
            client_type("tóken")
        with pytest.raises(ValueError, match="user_agent_suffix must contain only ASCII"):
            client_type("test-token", user_agent_suffix="zażółć/1")

    client = HumalikeClient(
        "test-token",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})),
    )
    try:
        with pytest.raises(ValueError, match="Idempotency-Key must contain only ASCII"):
            client.request(
                "POST",
                "/v1/social-memory/actions/ingest",
                headers={"Idempotency-Key": "powtórka"},
            )
    finally:
        client.close()


def test_async_non_ascii_idempotency_key_fails_before_network() -> None:
    async def scenario() -> None:
        calls = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        client = AsyncHumalikeClient(
            "test-token",
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(ValueError, match="Idempotency-Key must contain only ASCII"):
                await client.request(
                    "POST",
                    "/v1/social-memory/actions/ingest",
                    headers={"Idempotency-Key": "powtórka"},
                )
        finally:
            await client.close()
        assert calls == 0

    asyncio.run(scenario())
