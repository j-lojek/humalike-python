"""Narrow runtime checks for stable, typed success envelopes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import ProtocolError

_OPERATION_STATUSES = frozenset({"pending", "running", "succeeded", "failed"})
_TURN_DECISIONS = frozenset({"speak", "stay_silent"})


def _required_mapping(response: object, *, operation: str) -> Mapping[str, Any]:
    if not isinstance(response, Mapping):
        raise ProtocolError(f"{operation} returned a non-object response envelope")
    return response


def _required_non_empty_string(
    response: Mapping[str, Any],
    field: str,
    *,
    operation: str,
) -> str:
    value = response.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(f"{operation} response field {field!r} must be a non-empty string")
    return value


def validate_operation_start_response(response: object, *, operation: str) -> None:
    """Validate the required fields shared by Persona operation starts."""

    envelope = _required_mapping(response, operation=operation)
    _required_non_empty_string(envelope, "id", operation=operation)
    status = _required_non_empty_string(envelope, "status", operation=operation)
    if status not in _OPERATION_STATUSES:
        raise ProtocolError(f"{operation} response contains undocumented status")


def validate_operation_envelope(response: object, *, operation: str) -> None:
    """Validate stable identity and state fields on Persona read-back envelopes."""

    envelope = _required_mapping(response, operation=operation)
    _required_non_empty_string(envelope, "id", operation=operation)
    status = _required_non_empty_string(envelope, "status", operation=operation)
    if status not in _OPERATION_STATUSES:
        raise ProtocolError(f"{operation} response contains undocumented status")


def validate_submit_messages_response(response: object) -> None:
    """Validate the small documented decision envelope returned by submit."""

    operation = "submit_messages"
    envelope = _required_mapping(response, operation=operation)

    decision = envelope.get("decision")
    if not isinstance(decision, str) or decision not in _TURN_DECISIONS:
        raise ProtocolError(
            "submit_messages response field 'decision' must be 'speak' or 'stay_silent'"
        )

    turn_epoch = envelope.get("turn_epoch")
    if isinstance(turn_epoch, bool) or not isinstance(turn_epoch, int) or turn_epoch < 0:
        raise ProtocolError("submit_messages response field 'turn_epoch' must be an integer >= 0")

    tags = envelope.get("tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ProtocolError("submit_messages response field 'tags' must be an array of strings")
