from __future__ import annotations

import asyncio
import builtins
import json
import math
import traceback

import pytest
from websockets.exceptions import ConnectionClosedOK

import humalike.websocket as websocket_module
from humalike import (
    APIConnectionError,
    APITimeoutError,
    AsyncHumalikeClient,
    ProtocolError,
    TurnTakingStream,
    connect_turn_taking,
)

_SIGNED_GRANT = "wss://example.test/v1/ws?grant=traceback-local-secret"


def _assert_secret_absent_from_sdk_exception_frames(
    error: BaseException,
    secret: str,
) -> None:
    """Inspect traceback locals across the complete retained exception chain."""

    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        traceback_cursor = current.__traceback__
        while traceback_cursor is not None:
            frame = traceback_cursor.tb_frame
            module_name = str(frame.f_globals.get("__name__", ""))
            if module_name.startswith("humalike"):
                for name, value in frame.f_locals.items():
                    assert secret not in repr(value), (
                        f"secret retained in {module_name}.{frame.f_code.co_name} local {name}"
                    )
            traceback_cursor = traceback_cursor.tb_next
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)


class FakeConnection:
    def __init__(self, frames: list[str | bytes]) -> None:
        self.frames = iter(frames)
        self.closed = False

    async def recv(self) -> str | bytes:
        return next(self.frames)

    async def close(self) -> None:
        self.closed = True


def test_stream_connect_recv_iter_and_redaction() -> None:
    signed = "wss://realtime.example.test/v1/ws?c=secret-grant"
    connection = FakeConnection(
        [
            json.dumps(
                {
                    "id": "delivery-1",
                    "type": "turn_taking.message",
                    "channel": "turn-taking-thread/thread-1",
                    "ts": "2026-07-11T12:00:00Z",
                    "data": {"content": "private content", "position": 0},
                }
            )
        ]
    )
    connected_to: list[str] = []

    async def connector(url: str) -> FakeConnection:
        connected_to.append(url)
        return connection

    async def scenario() -> None:
        stream = await TurnTakingStream.connect(
            {"realtime": {"connect_url": signed}}, connector=connector
        )
        assert signed not in repr(stream)
        assert "secret-grant" not in repr(stream)
        async with stream:
            event = await anext(stream)
            assert event.type == "turn_taking.message"
            assert event.data["content"] == "private content"
            assert event.id == "delivery-1"
            assert "private content" not in repr(event)
        assert connection.closed

    asyncio.run(scenario())
    assert connected_to == [signed]


def test_stream_accepts_observed_attached_frame_without_data() -> None:
    async def connector(_: str) -> FakeConnection:
        return FakeConnection(
            [
                json.dumps(
                    {
                        "type": "attached",
                        "channel": "turn-taking-thread/thread-1",
                        "server_time": "2026-07-11T12:00:00Z",
                    }
                )
            ]
        )

    async def scenario() -> None:
        stream = await TurnTakingStream.connect(
            "wss://example.test/v1/ws?c=fake", connector=connector
        )
        event = await stream.recv()
        assert event.type == "attached"
        assert event.data == {}
        assert event.timestamp == "2026-07-11T12:00:00Z"
        await stream.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_custom_connector_errors_are_stable_sdk_errors(
    error_type: type[Exception],
) -> None:
    signed = "wss://example.test/v1/ws?c=secret"

    async def connector(url: str) -> FakeConnection:
        raise error_type(f"custom connector failed: {url}")

    async def scenario() -> None:
        with pytest.raises(APIConnectionError) as raised:
            await TurnTakingStream.connect(signed, connector=connector)
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None
        rendered = "".join(traceback.format_exception(raised.value))
        assert "secret" not in rendered
        assert "custom connector failed" not in rendered
        _assert_secret_absent_from_sdk_exception_frames(raised.value, signed)

    asyncio.run(scenario())


def test_missing_optional_dependency_is_an_actionable_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def blocked_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "websockets":
            raise ImportError("optional dependency intentionally unavailable")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="pip install") as raised:
            await TurnTakingStream.connect("wss://example.test/v1/ws?c=secret")
        assert not isinstance(raised.value, APIConnectionError)
        assert isinstance(raised.value.__cause__, ImportError)
        assert "secret" not in str(raised.value)
        _assert_secret_absent_from_sdk_exception_frames(
            raised.value, "wss://example.test/v1/ws?c=secret"
        )

    asyncio.run(scenario())


def test_other_default_connector_runtime_errors_are_stable_sdk_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signed = "wss://example.test/v1/ws?c=secret"

    async def broken_default_connector(
        url: str,
        *,
        open_timeout: float,
        max_size: int,
    ) -> FakeConnection:
        assert open_timeout == 10
        assert max_size == 1_048_576
        raise RuntimeError(f"default connector failed: {url}")

    monkeypatch.setattr(websocket_module, "_default_connector", broken_default_connector)

    async def scenario() -> None:
        with pytest.raises(APIConnectionError) as raised:
            await TurnTakingStream.connect(signed)
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None
        rendered = "".join(traceback.format_exception(raised.value))
        assert "secret" not in rendered
        assert "default connector failed" not in rendered
        _assert_secret_absent_from_sdk_exception_frames(raised.value, signed)

    asyncio.run(scenario())


@pytest.mark.parametrize("entry_point", ["stream", "function", "client"])
def test_all_websocket_connect_entry_points_scrub_signed_url_from_traceback_locals(
    entry_point: str,
) -> None:
    async def connector(url: str) -> FakeConnection:
        raise RuntimeError(f"connector leaked {url}")

    async def scenario() -> None:
        client: AsyncHumalikeClient | None = None
        try:
            with pytest.raises(APIConnectionError) as raised:
                if entry_point == "stream":
                    await TurnTakingStream.connect(_SIGNED_GRANT, connector=connector)
                elif entry_point == "function":
                    await connect_turn_taking(_SIGNED_GRANT, connector=connector)
                else:
                    client = AsyncHumalikeClient("test-token")
                    await client.connect_turn_taking(_SIGNED_GRANT, connector=connector)
            _assert_secret_absent_from_sdk_exception_frames(raised.value, _SIGNED_GRANT)
            assert raised.value.__cause__ is None
            assert raised.value.__context__ is None
        finally:
            if client is not None:
                await client.close()

    asyncio.run(scenario())


def test_invalid_websocket_grant_is_scrubbed_from_validation_traceback_locals() -> None:
    invalid_signed_grant = "ws://example.test/v1/ws?grant=validation-local-secret"

    async def scenario() -> None:
        with pytest.raises(ProtocolError) as raised:
            await TurnTakingStream.connect(invalid_signed_grant)
        _assert_secret_absent_from_sdk_exception_frames(raised.value, invalid_signed_grant)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "value",
    [True, False, 0, -1, math.nan, math.inf, -math.inf, "1", None],
)
def test_stream_rejects_invalid_open_timeout_before_connect(value: object) -> None:
    connector_called = False

    async def connector(_: str) -> FakeConnection:
        nonlocal connector_called
        connector_called = True
        return FakeConnection([])

    async def scenario() -> None:
        with pytest.raises(ValueError, match="open_timeout must be a finite number > 0"):
            await TurnTakingStream.connect(
                "wss://example.test/v1/ws?c=secret",
                connector=connector,
                open_timeout=value,  # type: ignore[arg-type]
            )

    asyncio.run(scenario())
    assert not connector_called


@pytest.mark.parametrize(
    "value",
    [True, False, 0, -1, 1.0, math.nan, math.inf, -math.inf, "1", None],
)
def test_stream_rejects_invalid_max_size_before_connect(value: object) -> None:
    connector_called = False

    async def connector(_: str) -> FakeConnection:
        nonlocal connector_called
        connector_called = True
        return FakeConnection([])

    async def scenario() -> None:
        with pytest.raises(ValueError, match="max_size must be an integer > 0"):
            await TurnTakingStream.connect(
                "wss://example.test/v1/ws?c=secret",
                connector=connector,
                max_size=value,  # type: ignore[arg-type]
            )

    asyncio.run(scenario())
    assert not connector_called


def test_stream_accepts_positive_integer_connection_limits() -> None:
    connection = FakeConnection([])

    async def connector(_: str) -> FakeConnection:
        return connection

    async def scenario() -> None:
        stream = await TurnTakingStream.connect(
            "wss://example.test/v1/ws?c=secret",
            connector=connector,
            open_timeout=1,
            max_size=1,
        )
        await stream.close()

    asyncio.run(scenario())
    assert connection.closed


def test_async_iteration_ends_on_normal_websocket_close() -> None:
    class NormallyClosedConnection(FakeConnection):
        async def recv(self) -> str:
            self.closed = True
            raise ConnectionClosedOK(None, None)

    async def scenario() -> None:
        connection = NormallyClosedConnection([])
        stream = TurnTakingStream(connection)

        events = [event async for event in stream]

        assert events == []
        assert connection.closed
        assert "closed" in repr(stream)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "value",
    [
        "ws://example.test/v1/ws?c=secret",
        "wss://user:password@example.test/v1/ws",
        "wss://example.test/v1/ws#secret",
        {"realtime": {}},
    ],
)
def test_stream_rejects_unsafe_or_missing_grant(value: object) -> None:
    async def connector(_: str) -> FakeConnection:
        raise AssertionError("connector must not run")

    async def scenario() -> None:
        with pytest.raises(ProtocolError):
            await TurnTakingStream.connect(value, connector=connector)  # type: ignore[arg-type]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "frame",
    [
        "not-json",
        "[]",
        '{"data": {}}',
        '{"id": "e1", "type": "turn_taking.message", "ts": "now", "data": {}}',
        '{"type": "turn_taking.message", "channel": "c", "ts": "now", "data": {}}',
        '{"id": "e1", "type": "turn_taking.message", "channel": "c", "data": {}}',
        '{"id": "e1", "type": "turn_taking.message", "channel": "c", "ts": "now", "data": "wrong"}',
        '{"type": "attached", "channel": "c"}',
        b"\xff",
    ],
)
def test_stream_rejects_malformed_frames(frame: str | bytes) -> None:
    async def connector(_: str) -> FakeConnection:
        return FakeConnection([frame])

    async def scenario() -> None:
        stream = await TurnTakingStream.connect(
            "wss://example.test/v1/ws?c=fake", connector=connector
        )
        with pytest.raises(ProtocolError):
            await stream.recv()
        await stream.close()

    asyncio.run(scenario())


def test_stream_receive_timeout_is_stable_sdk_error() -> None:
    class SlowConnection(FakeConnection):
        async def recv(self) -> str:
            await asyncio.sleep(60)
            return "{}"

    async def connector(_: str) -> FakeConnection:
        return SlowConnection([])

    async def scenario() -> None:
        stream = await TurnTakingStream.connect(
            "wss://example.test/v1/ws?c=fake", connector=connector
        )
        with pytest.raises(APITimeoutError):
            await stream.recv(timeout=0.001)
        await stream.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "value",
    [True, False, 0, -1, math.nan, math.inf, -math.inf, "1"],
)
def test_stream_rejects_invalid_receive_timeout(value: object) -> None:
    connection = FakeConnection([])

    async def scenario() -> None:
        stream = TurnTakingStream(connection)
        with pytest.raises(ValueError, match="timeout must be a finite number > 0"):
            await stream.recv(timeout=value)  # type: ignore[arg-type]
        await stream.close()

    asyncio.run(scenario())
    assert connection.closed
