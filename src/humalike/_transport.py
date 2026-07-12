"""Shared HTTP transport policy for the synchronous and asynchronous clients."""

from __future__ import annotations

import math
import random
import time
from collections.abc import Mapping, Sequence
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import httpx

from .errors import (
    AuthenticationError,
    HumalikeAPIError,
    PaymentRequiredError,
    PermissionDeniedError,
    ProtocolError,
    UpstreamError,
    ValidationError,
)
from .models import JSON

DEFAULT_BASE_URL = "https://api.humalike.com"
DEFAULT_TIMEOUT_SECONDS = 120.0
RETRYABLE_STATUS = {408, 429, 502, 503, 504}
RUNNING_OPERATION_STATES = {"pending", "running"}
READ_LIKE_POST_PATHS = {
    "/v1/turn-taking/actions/whoami",
    "/v1/credits/projections/usage-summary",
}
IDEMPOTENT_WRITE_PATHS = {"/v1/social-memory/actions/ingest"}
GROUNDING_LEVELS = {"off", "web", "research"}
MAX_LOCAL_BACKOFF_SECONDS = 30.0
MAX_SERVER_RETRY_AFTER_SECONDS = 300.0
LOCAL_BACKOFF_JITTER_RATIO = 0.1
RECORD_EVENT_TYPES = {"typing_start", "typing_stop", "message_edited"}
FORBIDDEN_REQUEST_HEADERS = frozenset(
    {
        "authorization",
        "connection",
        "content-length",
        "host",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


def _contains_control_characters(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def without_none(payload: Mapping[str, Any]) -> JSON:
    return {key: value for key, value in payload.items() if value is not None}


def transcript(messages: Sequence[Mapping[str, Any]], source: str | None = None) -> JSON:
    body: JSON = {"messages": [dict(message) for message in messages]}
    if source is not None:
        body["source"] = source
    return body


def validated_token(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("token must be a non-empty string without surrounding whitespace")
    if _contains_control_characters(value):
        raise ValueError("token must not contain control characters")
    if not value.isascii():
        raise ValueError("token must contain only ASCII characters")
    return value


def validated_base_url(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(
            "base_url must be an HTTPS origin without credentials, path, query, or fragment"
        )
    normalized = value.rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError(
            "base_url must be an HTTPS origin without credentials, path, query, or fragment"
        )
    return normalized


def validated_api_path(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("path must be a relative /v1/... API path")
    if _contains_control_characters(value):
        raise ValueError("path must be a relative /v1/... API path without control characters")
    parsed = urlsplit(value)
    try:
        decoded_path = unquote(parsed.path, errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("path must contain valid UTF-8 percent escapes") from exc
    segments = decoded_path.split("/")
    if (
        not value.startswith("/v1/")
        or not parsed.path.startswith("/v1/")
        or not decoded_path.startswith("/v1/")
        or parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or "\\" in decoded_path
        or _contains_control_characters(decoded_path)
        or any(segment in {".", ".."} for segment in segments)
        or "%2f" in parsed.path.lower()
        or "%5c" in parsed.path.lower()
    ):
        raise ValueError("path must be a relative /v1/... API path")
    return value


def path_segment(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    if value in {".", ".."} or "/" in value or "\\" in value or _contains_control_characters(value):
        raise ValueError(f"{name} must be a safe single path segment")
    return quote(value, safe="")


def required_text(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def validated_header_component(value: str, *, name: str) -> str:
    required_text(value, name=name)
    if _contains_control_characters(value):
        raise ValueError(f"{name} must not contain control characters")
    if not value.isascii():
        raise ValueError(f"{name} must contain only ASCII characters")
    return value


def validated_idempotency_key(value: str, *, name: str = "idempotency_key") -> str:
    validated_header_component(value, name=name)
    if value != value.strip():
        raise ValueError(f"{name} must not contain surrounding whitespace")
    return value


def validated_optional_bool(value: bool | None, *, name: str) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{name} must be a bool or None")
    return value


def validated_max_retries(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("max_retries must be an integer >= 0")
    return value


def validated_non_negative_number(
    value: float,
    *,
    name: str,
    allow_zero: bool = True,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        or (not allow_zero and value == 0)
    ):
        comparison = ">= 0" if allow_zero else "> 0"
        raise ValueError(f"{name} must be a finite number {comparison}")
    return float(value)


def validated_http_timeout(
    value: float | httpx.Timeout,
    *,
    name: str = "timeout",
) -> float | httpx.Timeout:
    if isinstance(value, httpx.Timeout):
        components = value.as_dict()
        if any(
            component is None
            or isinstance(component, bool)
            or not isinstance(component, (int, float))
            or not math.isfinite(component)
            or component <= 0
            for component in components.values()
        ):
            raise ValueError(f"{name} components must be finite numbers > 0")
        return value
    return validated_non_negative_number(value, name=name, allow_zero=False)


def bounded_http_timeout(
    value: float | httpx.Timeout,
    remaining: float,
) -> float | httpx.Timeout:
    """Cap every configured HTTP timeout component to a remaining deadline."""

    if isinstance(value, httpx.Timeout):
        components = value.as_dict()

        def bounded(component: float | None) -> float:
            if component is None:
                raise ValueError("timeout components must be finite numbers > 0")
            return min(component, remaining)

        return httpx.Timeout(
            connect=bounded(components["connect"]),
            read=bounded(components["read"]),
            write=bounded(components["write"]),
            pool=bounded(components["pool"]),
        )
    return min(float(value), remaining)


def required_object_response(
    value: Any,
    *,
    operation: str,
    nullable: bool = False,
) -> JSON | None:
    if value is None and nullable:
        return None
    if not isinstance(value, Mapping):
        raise ProtocolError(f"{operation} returned a non-object response envelope")
    return dict(value)


def required_messages(
    value: Sequence[Mapping[str, Any]], *, name: str = "messages"
) -> Sequence[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise ValueError(f"{name} must contain at least one message")
    for index, message in enumerate(value):
        if not isinstance(message, Mapping):
            raise ValueError(f"{name}[{index}] must be an object")
    return value


def validated_submit_messages(
    value: Sequence[Mapping[str, Any]],
) -> Sequence[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("messages must be a sequence of 1 to 20 message objects")
    if not 1 <= len(value) <= 20:
        raise ValueError("messages must contain between 1 and 20 items")
    for index, message in enumerate(value):
        if not isinstance(message, Mapping):
            raise ValueError(f"messages[{index}] must be an object")
        sender = message.get("sender")
        content = message.get("content")
        if not isinstance(sender, str) or not 1 <= len(sender) <= 255:
            raise ValueError(f"messages[{index}].sender must be a string of 1 to 255 characters")
        if not isinstance(content, str) or not 1 <= len(content) <= 4000:
            raise ValueError(f"messages[{index}].content must be a string of 1 to 4000 characters")
        if "client_ts" in message and not isinstance(message["client_ts"], str):
            raise ValueError(f"messages[{index}].client_ts must be a string")
        if message.get("client_ts") == "":
            raise ValueError(f"messages[{index}].client_ts must not be empty")
        if "has_media" in message and not isinstance(message["has_media"], bool):
            raise ValueError(f"messages[{index}].has_media must be a bool")
    return value


def validated_record_event_type(value: str) -> str:
    if not isinstance(value, str) or value not in RECORD_EVENT_TYPES:
        allowed = ", ".join(sorted(RECORD_EVENT_TYPES))
        raise ValueError(f"event_type must be one of: {allowed}")
    return value


def validated_grounding(value: str) -> str:
    if not isinstance(value, str) or value not in GROUNDING_LEVELS:
        allowed = ", ".join(sorted(GROUNDING_LEVELS))
        raise ValueError(f"grounding must be one of: {allowed}")
    return value


def default_headers(token: str, *, user_agent: str) -> httpx.Headers:
    return httpx.Headers(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": user_agent,
        }
    )


def merged_headers(
    defaults: httpx.Headers,
    overrides: Mapping[str, str] | None,
) -> httpx.Headers:
    result = httpx.Headers(defaults)
    if overrides is None:
        return result
    for name, value in overrides.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise ValueError("per-request header names and values must be strings")
        normalized_name = name.strip().lower()
        if normalized_name in FORBIDDEN_REQUEST_HEADERS:
            raise ValueError(f"{name.strip() or name} cannot be set per request")
        if normalized_name == "idempotency-key":
            value = validated_idempotency_key(value, name="Idempotency-Key")
        result[name] = value
    return result


def retry_is_safe(
    method: str,
    path: str,
    headers: Mapping[str, str] | None,
) -> bool:
    normalized_method = method.upper()
    normalized_path = urlsplit(path).path
    if normalized_method in {"GET", "HEAD", "OPTIONS"}:
        return True
    if normalized_method == "POST" and normalized_path in READ_LIKE_POST_PATHS:
        return True
    if normalized_method != "POST" or normalized_path not in IDEMPOTENT_WRITE_PATHS:
        return False
    if not headers:
        return False
    key = next(
        (value for name, value in headers.items() if name.lower() == "idempotency-key"),
        None,
    )
    if key is None:
        return False
    try:
        validated_idempotency_key(key, name="Idempotency-Key")
    except ValueError:
        return False
    return True


def retry_delay(
    attempt: int,
    response: httpx.Response | None,
    *,
    backoff: float,
    backoff_maximum: float = MAX_LOCAL_BACKOFF_SECONDS,
    retry_after_maximum: float = MAX_SERVER_RETRY_AFTER_SECONDS,
    jitter_ratio: float = LOCAL_BACKOFF_JITTER_RATIO,
    random_value: float | None = None,
    now: float | None = None,
) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                seconds = float(retry_after)
                if math.isfinite(seconds):
                    return min(retry_after_maximum, max(0.0, seconds))
            except ValueError:
                pass
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                delay = retry_at.timestamp() - (time.time() if now is None else now)
                if math.isfinite(delay):
                    return min(retry_after_maximum, max(0.0, delay))
            except (OverflowError, TypeError, ValueError):
                pass
    if backoff == 0:
        delay = 0.0
    else:
        try:
            delay = min(backoff_maximum, math.ldexp(backoff, attempt))
        except OverflowError:
            delay = backoff_maximum
    if delay <= 0 or jitter_ratio <= 0:
        return delay
    sample = random.random() if random_value is None else random_value
    return min(backoff_maximum, delay + delay * jitter_ratio * sample)


def api_error(response: httpx.Response) -> HumalikeAPIError:
    try:
        body = response.json()
    except ValueError:
        body = {}
    envelope = body.get("error", {}) if isinstance(body, dict) else {}
    if not isinstance(envelope, dict):
        envelope = {}
    code = str(envelope.get("code") or f"HTTP_{response.status_code}")
    message = str(envelope.get("message") or "request failed")
    details = envelope.get("details")
    trace_id = envelope.get("trace_id") or response.headers.get("x-trace-id")
    error_type: type[HumalikeAPIError]
    if response.status_code == 401 or code.upper() == "UNAUTHORIZED":
        error_type = AuthenticationError
    elif response.status_code == 402 or code.upper() == "PAYMENT_REQUIRED":
        error_type = PaymentRequiredError
    elif response.status_code == 403 or code.lower() == "forbidden":
        error_type = PermissionDeniedError
    elif response.status_code in {400, 422} or "validation" in code.lower():
        error_type = ValidationError
    elif response.status_code >= 500 or code.upper() == "UPSTREAM_ERROR":
        error_type = UpstreamError
    else:
        error_type = HumalikeAPIError
    return error_type(
        status_code=response.status_code,
        code=code,
        message=message,
        details=details,
        trace_id=str(trace_id) if trace_id else None,
    )
