"""Async Turn-Taking WebSocket support with secret-safe representations."""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.parse import SplitResult, urlsplit

from .errors import APIConnectionError, APITimeoutError, ProtocolError
from .models import JSON, TurnTakingEventDict


class WebSocketConnection(Protocol):
    """Small transport protocol used for tests and alternative WS libraries."""

    async def recv(self) -> str | bytes: ...

    async def close(self) -> None: ...


WebSocketConnector = Callable[[str], Awaitable[WebSocketConnection]]


class _MissingWebSocketDependencyError(RuntimeError):
    """The optional default WebSocket transport is not installed."""


_REDACTED_WEBSOCKET_URL = "<redacted WebSocket URL>"


def _is_normal_websocket_close(error: BaseException | None) -> bool:
    """Recognize websockets 12--16 normal-close errors without importing it."""

    if error is None:
        return False
    return any(
        base.__name__ == "ConnectionClosedOK"
        and (base.__module__ == "websockets" or base.__module__.startswith("websockets."))
        for base in type(error).__mro__
    )


@dataclass(frozen=True, repr=False)
class TurnTakingEvent:
    """A parsed event received from a Turn-Taking thread channel.

    ``data`` and ``raw`` can contain conversation content.  They are therefore
    intentionally excluded from ``repr``.
    """

    type: str
    data: JSON
    id: str | None = None
    channel: str | None = None
    timestamp: str | None = None
    raw: TurnTakingEventDict | None = None

    def __repr__(self) -> str:
        return f"TurnTakingEvent(type={self.type!r}, channel={self.channel!r}, data='<redacted>')"


def _connect_url(value: str | Mapping[str, Any]) -> str:
    # All potentially secret-bearing locals are initialized explicitly so the
    # ``finally`` block can scrub them even when validation exits early.
    realtime: object = None
    candidate: object = None
    parsed: SplitResult | None = None
    url = _REDACTED_WEBSOCKET_URL
    try:
        if isinstance(value, str):
            url = value
        else:
            realtime = value.get("realtime")
            if isinstance(realtime, Mapping):
                candidate = realtime.get("connect_url")
            else:
                candidate = value.get("connect_url")
            if not isinstance(candidate, str):
                raise ProtocolError("Turn-Taking grant does not contain realtime.connect_url")
            url = candidate

        parsed = urlsplit(url)
        if (
            parsed.scheme != "wss"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ProtocolError(
                "Turn-Taking connect_url must be a WSS URL without userinfo or fragment"
            )
        return url
    finally:
        # Traceback collectors can serialize frame locals. Overwrite every
        # local that may reference the signed grant before this frame unwinds.
        value = _REDACTED_WEBSOCKET_URL
        realtime = None
        candidate = None
        parsed = None
        url = _REDACTED_WEBSOCKET_URL


async def _default_connector(
    url: str,
    *,
    open_timeout: float,
    max_size: int,
) -> WebSocketConnection:
    try:
        try:
            from websockets import connect
        except ImportError as exc:  # pragma: no cover - depends on installation extras
            raise _MissingWebSocketDependencyError(
                "WebSocket support requires `pip install 'humalike-python[websocket]'`"
            ) from exc
        return cast(
            WebSocketConnection,
            await connect(url, open_timeout=open_timeout, max_size=max_size),
        )
    finally:
        # The missing-dependency exception intentionally retains its safe
        # ImportError cause, whose traceback also contains this frame.
        url = _REDACTED_WEBSOCKET_URL


class TurnTakingStream:
    """An async iterator over one short-lived Turn-Taking WebSocket grant."""

    def __init__(self, connection: WebSocketConnection) -> None:
        self._connection = connection
        self._closed = False

    @classmethod
    async def connect(
        cls,
        grant_or_url: str | Mapping[str, Any],
        *,
        connector: WebSocketConnector | None = None,
        open_timeout: float = 10.0,
        max_size: int = 1_048_576,
    ) -> TurnTakingStream:
        """Connect using a grant returned by ``open_thread`` or its URL.

        The signed URL is forwarded only to the connector and is never retained
        on the stream object or included in exceptions raised by this module.
        """

        url = _REDACTED_WEBSOCKET_URL
        try:
            if (
                isinstance(open_timeout, bool)
                or not isinstance(open_timeout, (int, float))
                or not math.isfinite(open_timeout)
                or open_timeout <= 0
            ):
                raise ValueError("open_timeout must be a finite number > 0")
            if isinstance(max_size, bool) or not isinstance(max_size, int) or max_size <= 0:
                raise ValueError("max_size must be an integer > 0")
            url = _connect_url(grant_or_url)
            connection: WebSocketConnection | None = None
            connect_error: APIConnectionError | None = None
            if connector is None:
                try:
                    connection = await _default_connector(
                        url, open_timeout=open_timeout, max_size=max_size
                    )
                except _MissingWebSocketDependencyError:
                    raise
                except Exception:
                    # Connector exceptions can embed the complete signed grant URL.
                    # Raise a replacement after leaving this handler so the raw
                    # exception is not retained as context.
                    connect_error = APIConnectionError("turn-taking WebSocket connect")
            else:
                try:
                    connection = await connector(url)
                except Exception:
                    # A custom connector receives the signed URL and may repeat it in
                    # its exception message. Do not retain that exception as context.
                    connect_error = APIConnectionError("turn-taking WebSocket connect")
            if connect_error is not None:
                raise connect_error
            if connection is None:
                raise APIConnectionError("turn-taking WebSocket connector returned no connection")
            return cls(connection)
        finally:
            # Do not leave the grant in traceback locals consumed by Sentry,
            # rich tracebacks, debuggers, or other crash reporters.
            grant_or_url = _REDACTED_WEBSOCKET_URL
            url = _REDACTED_WEBSOCKET_URL

    def __repr__(self) -> str:
        state = "closed" if self._closed else "open"
        return f"TurnTakingStream(state={state!r}, connect_url='<redacted>')"

    async def __aenter__(self) -> TurnTakingStream:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    def __aiter__(self) -> TurnTakingStream:
        return self

    async def __anext__(self) -> TurnTakingEvent:
        if self._closed:
            raise StopAsyncIteration
        try:
            return await self.recv()
        except APIConnectionError as exc:
            if _is_normal_websocket_close(exc.__cause__):
                self._closed = True
                raise StopAsyncIteration from None
            raise

    async def recv(self, *, timeout: float | None = None) -> TurnTakingEvent:
        """Receive and validate one JSON event envelope."""

        if self._closed:
            raise RuntimeError("TurnTakingStream is closed")
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("timeout must be a finite number > 0")
        try:
            receive = self._connection.recv()
            frame = await receive if timeout is None else await asyncio.wait_for(receive, timeout)
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise APITimeoutError("turn-taking WebSocket receive") from exc
        except Exception as exc:
            raise APIConnectionError("turn-taking WebSocket receive") from exc

        if isinstance(frame, bytes):
            try:
                text = frame.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ProtocolError("Turn-Taking WebSocket returned non-UTF-8 bytes") from exc
        elif isinstance(frame, str):
            text = frame
        else:
            raise ProtocolError("Turn-Taking WebSocket returned a non-text frame")

        try:
            raw = json.loads(text)
        except ValueError as exc:
            raise ProtocolError("Turn-Taking WebSocket returned invalid JSON") from exc
        if not isinstance(raw, dict):
            raise ProtocolError("Turn-Taking WebSocket event must be a JSON object")
        event_type = raw.get("type")
        channel = raw.get("channel")
        data = raw.get("data")
        if not isinstance(event_type, str):
            raise ProtocolError("Turn-Taking WebSocket event requires string type")
        if not isinstance(channel, str) or not channel:
            raise ProtocolError("Turn-Taking WebSocket event requires string channel")
        event_id = raw.get("id")
        if event_type == "attached":
            if data is None:
                data = {}
            elif not isinstance(data, dict):
                raise ProtocolError("Turn-Taking attached event requires object data when present")
            timestamp = raw.get("server_time")
            if not isinstance(timestamp, str):
                raise ProtocolError("Turn-Taking attached event requires string server_time")
        else:
            if not isinstance(event_id, str):
                raise ProtocolError("Turn-Taking delivery event requires string id")
            if not isinstance(data, dict):
                raise ProtocolError("Turn-Taking delivery event requires object data")
            timestamp = raw.get("ts")
            if not isinstance(timestamp, str):
                raise ProtocolError("Turn-Taking delivery event requires string ts")

        return TurnTakingEvent(
            type=event_type,
            data=data,
            id=event_id if isinstance(event_id, str) else None,
            channel=channel,
            timestamp=timestamp,
            raw=cast(TurnTakingEventDict, raw),
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._connection.close()
        except Exception as exc:
            raise APIConnectionError("turn-taking WebSocket close") from exc


async def connect_turn_taking(
    grant_or_url: str | Mapping[str, Any],
    *,
    connector: WebSocketConnector | None = None,
    open_timeout: float = 10.0,
    max_size: int = 1_048_576,
) -> TurnTakingStream:
    """Convenience wrapper around :meth:`TurnTakingStream.connect`."""

    try:
        return await TurnTakingStream.connect(
            grant_or_url,
            connector=connector,
            open_timeout=open_timeout,
            max_size=max_size,
        )
    finally:
        grant_or_url = _REDACTED_WEBSOCKET_URL
