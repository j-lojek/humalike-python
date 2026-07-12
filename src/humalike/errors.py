"""Stable exception hierarchy for Humalike API and operation failures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _redacted_or_none(value: object | None) -> str:
    return repr("<redacted>") if value is not None else "None"


class HumalikeError(Exception):
    """Base class for SDK API, transport, protocol, and operation errors."""


@dataclass(eq=False, repr=False)
class APIConnectionError(HumalikeError):
    """The API could not be reached or the response stream was interrupted."""

    operation: str

    def __post_init__(self) -> None:
        HumalikeError.__init__(self, self.operation)

    def __reduce__(self) -> tuple[type[HumalikeError], tuple[object, ...]]:
        return type(self), (self.operation,)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(operation='<redacted>')"

    def __str__(self) -> str:
        return f"Humalike connection failed during {self.operation}"


@dataclass(eq=False, repr=False)
class APITimeoutError(APIConnectionError):
    """A request timed out before a conclusive API response was received."""

    def __str__(self) -> str:
        return f"Humalike request timed out during {self.operation}"


@dataclass(eq=False, repr=False)
class HumalikeAPIError(HumalikeError):
    """A non-2xx response using Humalike's error envelope."""

    status_code: int
    code: str
    message: str
    details: Any = None
    trace_id: str | None = None

    def __post_init__(self) -> None:
        HumalikeError.__init__(
            self,
            self.status_code,
            self.code,
            self.message,
            self.details,
            self.trace_id,
        )

    def __reduce__(self) -> tuple[type[HumalikeError], tuple[object, ...]]:
        return type(self), (
            self.status_code,
            self.code,
            self.message,
            self.details,
            self.trace_id,
        )

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(status_code={self.status_code!r}, code={self.code!r}, "
            "message='<redacted>', "
            f"details={_redacted_or_none(self.details)}, "
            f"trace_id={_redacted_or_none(self.trace_id)})"
        )

    def __str__(self) -> str:
        trace = f" (trace_id={self.trace_id})" if self.trace_id else ""
        return f"{self.code}: {self.message} [HTTP {self.status_code}]{trace}"


class AuthenticationError(HumalikeAPIError):
    """The bearer token is absent, invalid, expired, or revoked."""


class PaymentRequiredError(HumalikeAPIError):
    """The account cannot cover the request's precomputed credit cost."""


class PermissionDeniedError(HumalikeAPIError):
    """The token is valid but cannot access this endpoint."""


class ValidationError(HumalikeAPIError):
    """The request failed API validation."""


class UpstreamError(HumalikeAPIError):
    """A Humalike dependency failed after retries were exhausted."""


@dataclass(eq=False, repr=False)
class ProtocolError(HumalikeError):
    """The server returned a response outside the documented contract."""

    message: str

    def __post_init__(self) -> None:
        HumalikeError.__init__(self, self.message)

    def __reduce__(self) -> tuple[type[HumalikeError], tuple[object, ...]]:
        return type(self), (self.message,)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(message='<redacted>')"

    def __str__(self) -> str:
        return self.message


@dataclass(eq=False, repr=False)
class OperationFailedError(HumalikeError):
    """An asynchronous persona operation reached ``status=failed``."""

    operation_id: str
    error: str

    def __post_init__(self) -> None:
        HumalikeError.__init__(self, self.operation_id, self.error)

    def __reduce__(self) -> tuple[type[HumalikeError], tuple[object, ...]]:
        return type(self), (self.operation_id, self.error)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(operation_id='<redacted>', error='<redacted>')"

    def __str__(self) -> str:
        return f"operation {self.operation_id} failed: {self.error}"


@dataclass(eq=False, repr=False)
class OperationTimeoutError(HumalikeError):
    """Polling did not reach a terminal state inside the caller's deadline."""

    operation_id: str
    timeout_seconds: float

    def __post_init__(self) -> None:
        HumalikeError.__init__(self, self.operation_id, self.timeout_seconds)

    def __reduce__(self) -> tuple[type[HumalikeError], tuple[object, ...]]:
        return type(self), (self.operation_id, self.timeout_seconds)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(operation_id='<redacted>', "
            f"timeout_seconds={self.timeout_seconds!r})"
        )

    def __str__(self) -> str:
        return f"operation {self.operation_id} did not finish within {self.timeout_seconds:g}s"
