from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from humalike import (
    HumalikeClient,
    OperationFailedError,
    OperationTimeoutError,
    ProtocolError,
)


def test_wait_population_returns_result(
    make_client: Callable[..., HumalikeClient],
) -> None:
    responses = iter(
        [
            {"id": "op-1", "status": "running", "progress": {"produced": 1, "total": 2}},
            {"id": "op-1", "status": "succeeded", "result": {"personas": [{"id": "p1"}]}},
        ]
    )
    sleeps: list[float] = []
    client = make_client(
        lambda _: httpx.Response(200, json=next(responses)),
        sleep=sleeps.append,
    )

    result = client.wait_population("op-1", poll_interval=0.5)

    assert result == {"personas": [{"id": "p1"}]}
    assert sleeps == [0.5]


def test_wait_operation_reports_failure(
    make_client: Callable[..., HumalikeClient],
) -> None:
    client = make_client(
        lambda _: httpx.Response(
            200, json={"id": "op-2", "status": "failed", "error": "provider_error"}
        )
    )

    with pytest.raises(OperationFailedError, match="provider_error"):
        client.wait_enhancement("op-2")


def test_wait_operation_rejects_unknown_status(
    make_client: Callable[..., HumalikeClient],
) -> None:
    client = make_client(lambda _: httpx.Response(200, json={"id": "op-3", "status": "mystery"}))

    with pytest.raises(ProtocolError, match="undocumented status"):
        client.wait_validation("op-3")


def test_wait_operation_honors_deadline(
    make_client: Callable[..., HumalikeClient],
) -> None:
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    client = make_client(
        lambda _: httpx.Response(200, json={"id": "op-4", "status": "running"}),
        sleep=sleep,
        monotonic=lambda: now[0],
    )

    with pytest.raises(OperationTimeoutError, match="within 1s"):
        client.wait_validation("op-4", timeout=1, poll_interval=0.6)

    assert now[0] == pytest.approx(1.0)
