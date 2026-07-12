from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from humalike import (
    APITimeoutError,
    AuthenticationError,
    HumalikeAPIError,
    HumalikeClient,
    PaymentRequiredError,
    PermissionDeniedError,
    ProtocolError,
    UpstreamError,
    ValidationError,
)


def test_whoami_sets_auth_and_safe_repr(
    make_client: Callable[..., HumalikeClient],
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"user_id": "user_1"})

    client = make_client(handler)

    assert client.whoami() == {"user_id": "user_1"}
    assert seen[0].headers["authorization"] == "Bearer test-token-sync"
    assert seen[0].headers["user-agent"] == "humalike-python/0.1.0b1"
    assert seen[0].url.path == "/v1/turn-taking/actions/whoami"
    assert repr(client) == "HumalikeClient(token='<redacted>')"
    assert "ak_" not in repr(client)
    assert "1234" not in repr(client)


@pytest.mark.parametrize(
    ("status", "code", "expected"),
    [
        (401, "UNAUTHORIZED", AuthenticationError),
        (402, "PAYMENT_REQUIRED", PaymentRequiredError),
        (403, "forbidden", PermissionDeniedError),
        (422, "validation_failed", ValidationError),
        (502, "UPSTREAM_ERROR", UpstreamError),
    ],
)
def test_error_mapping(
    make_client: Callable[..., HumalikeClient],
    status: int,
    code: str,
    expected: type[Exception],
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={
                "error": {
                    "code": code,
                    "message": "boom",
                    "details": [{"field": "x", "message": "bad"}],
                    "trace_id": "trace_1",
                }
            },
        )

    client = make_client(handler, max_retries=0)
    with pytest.raises(expected) as exc_info:
        client.whoami()

    error = exc_info.value
    assert isinstance(error, HumalikeAPIError)
    assert error.code == code
    assert error.trace_id == "trace_1"
    assert "Bearer" not in str(error)


def test_retries_retryable_status_and_honors_retry_after(
    make_client: Callable[..., HumalikeClient],
) -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                502,
                headers={"Retry-After": "0.75"},
                json={"error": {"code": "UPSTREAM_ERROR", "message": "retry"}},
            )
        return httpx.Response(200, json={"user_id": "ok"})

    client = make_client(handler, sleep=sleeps.append)

    assert client.whoami() == {"user_id": "ok"}
    assert calls == 2
    assert sleeps == [0.75]


def test_billable_non_idempotent_post_is_not_retried_after_lost_response(
    make_client: Callable[..., HumalikeClient],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("response lost", request=request)

    client = make_client(handler)

    with pytest.raises(APITimeoutError) as exc_info:
        client.start_population("five indie game players", count=5)

    assert calls == 1
    assert isinstance(exc_info.value.__cause__, httpx.ReadTimeout)


def test_raw_request_can_explicitly_opt_into_retry(
    make_client: Callable[..., HumalikeClient],
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": {"message": "retry"}})
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)

    assert client.request("POST", "/v1/known-idempotent", json={}, retry=True) == {"ok": True}
    assert calls == 2


def test_idempotency_key_makes_memory_write_retry_safe(
    make_client: Callable[..., HumalikeClient],
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(502, json={"error": {"message": "retry"}})
        return httpx.Response(200, json={"ingested": 1})

    client = make_client(handler)

    result = client.ingest_memory(
        "room:42",
        [{"speaker": "alice", "text": "hello"}],
        idempotency_key="stable-key",
    )

    assert result == {"ingested": 1}
    assert len(requests) == 2
    assert {request.headers["idempotency-key"] for request in requests} == {"stable-key"}


def test_idempotency_header_does_not_make_an_unlisted_post_retry_safe(
    make_client: Callable[..., HumalikeClient],
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": {"message": "retry"}})

    client = make_client(handler)

    with pytest.raises(UpstreamError):
        client.request(
            "POST",
            "/v1/social-observability/actions/analyze",
            json={},
            headers={"Idempotency-Key": "unsupported-here"},
        )

    assert calls == 1


def test_turn_submit_allows_explicit_retry_without_inventing_a_key(
    make_client: Callable[..., HumalikeClient],
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503, json={"error": {"message": "retry"}})
        return httpx.Response(
            200,
            json={"decision": "stay_silent", "turn_epoch": 1, "tags": []},
        )

    client = make_client(handler)

    result = client.submit_messages(
        "thread-fixture",
        [{"sender": "person", "content": "hello"}],
        skip_decide=True,
        retry=True,
    )

    assert result == {"decision": "stay_silent", "turn_epoch": 1, "tags": []}
    assert len(requests) == 2
    assert all("idempotency-key" not in request.headers for request in requests)


def test_non_json_success_is_protocol_error(
    make_client: Callable[..., HumalikeClient],
) -> None:
    client = make_client(lambda _: httpx.Response(200, text="ok"))

    with pytest.raises(ProtocolError, match="non-JSON"):
        client.whoami()


def test_request_with_response_preserves_metadata_but_redacts_repr(
    make_client: Callable[..., HumalikeClient],
) -> None:
    client = make_client(
        lambda _: httpx.Response(
            200,
            headers={"Location": "/v1/report/private-id", "X-Request-ID": "request-1"},
            json={"private": "content"},
        )
    )

    response = client.request_with_response("GET", "/v1/example")

    assert response.data == {"private": "content"}
    assert response.status_code == 200
    assert response.headers["location"] == "/v1/report/private-id"
    assert response.request_id == "request-1"
    assert "content" not in repr(response)
    assert "private-id" not in repr(response)


def test_from_env_requires_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUMALIKE_TOKEN", raising=False)
    with pytest.raises(ValueError, match="HUMALIKE_TOKEN"):
        HumalikeClient.from_env()


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.humalike.com",
        "https://user:password@api.humalike.com",
        "https://api.humalike.com/v1",
        "https://api.humalike.com?token=oops",
        None,
    ],
)
def test_rejects_base_urls_that_can_leak_or_misroute_tokens(base_url: Any) -> None:
    with pytest.raises(ValueError, match="HTTPS origin"):
        HumalikeClient("ak_test", base_url=base_url)  # type: ignore[arg-type]


def test_raw_request_rejects_absolute_and_non_api_paths(
    make_client: Callable[..., HumalikeClient],
) -> None:
    client = make_client(lambda _: httpx.Response(200, json={}))

    for path in (
        "https://attacker.example/v1/data",
        "//attacker.example/v1/data",
        "/health",
        None,
    ):
        with pytest.raises(ValueError, match="/v1/"):
            client.request("GET", path)  # type: ignore[arg-type]


def test_custom_http_client_still_receives_sdk_auth_and_origin() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"user_id": "custom"})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = HumalikeClient("test-token-custom", http_client=http_client)
    try:
        assert client.whoami()["user_id"] == "custom"
    finally:
        client.close()
        http_client.close()

    assert seen[0].url == "https://api.humalike.com/v1/turn-taking/actions/whoami"
    assert seen[0].headers["authorization"] == "Bearer test-token-custom"


def test_product_user_agent_suffix_is_validated_and_appended() -> None:
    seen: list[httpx.Request] = []
    client = HumalikeClient(
        "ak_fixture",
        user_agent_suffix="roompulse/0.1.0",
        transport=httpx.MockTransport(
            lambda request: seen.append(request) or httpx.Response(200, json={})
        ),
    )
    try:
        client.whoami()
    finally:
        client.close()

    assert seen[0].headers["user-agent"] == "humalike-python/0.1.0b1 roompulse/0.1.0"
    with pytest.raises(ValueError, match="control"):
        HumalikeClient("ak_fixture", user_agent_suffix="bad\nheader")


def test_resource_ids_are_encoded_as_one_path_segment(
    make_client: Callable[..., HumalikeClient],
) -> None:
    seen: list[httpx.Request] = []
    client = make_client(lambda request: seen.append(request) or httpx.Response(200, json=None))

    client.get_report("réport id.v1%2F")

    assert seen[0].url.raw_path == (
        b"/v1/social-observability/repositories/Report/by-id/r%C3%A9port%20id.v1%252F"
    )


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda client: client.extract_profile([]), "at least one"),
        (lambda client: client.start_population(""), "prompt"),
        (lambda client: client.start_population("fixture", count=0), "count"),
        (
            lambda client: client.start_population("fixture", grounding="invalid"),
            "grounding",
        ),
        (lambda client: client.ask_memory("scope", ""), "question"),
        (lambda client: client.respond("thread", "content", -1), "turn_epoch"),
    ],
)
def test_local_validation_prevents_invalid_api_calls(
    make_client: Callable[..., HumalikeClient],
    call: Callable[[HumalikeClient], object],
    message: str,
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client = make_client(handler)
    with pytest.raises(ValueError, match=message):
        call(client)
    assert calls == 0
