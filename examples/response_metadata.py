"""Inspect status and request metadata from a real whoami response."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from humalike import APIResponse, HumalikeClient


class ResponseClient(Protocol):
    def request_with_response(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
    ) -> APIResponse[Any]: ...


def run(client: ResponseClient) -> None:
    response = client.request_with_response(
        "POST",
        "/v1/turn-taking/actions/whoami",
        json={},
    )
    print(f"status: {response.status_code}")
    print(f"request id: {response.request_id or '<not returned>'}")
    if isinstance(response.data, Mapping):
        print(f"authenticated: {bool(response.data.get('user_id'))}")


def main() -> None:
    with HumalikeClient.from_env() as client:
        run(client)


if __name__ == "__main__":
    main()
