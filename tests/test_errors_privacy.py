from __future__ import annotations

import pickle

import pytest

from humalike import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    HumalikeAPIError,
    HumalikeError,
    OperationFailedError,
    OperationTimeoutError,
    PaymentRequiredError,
    PermissionDeniedError,
    ProtocolError,
    UpstreamError,
    ValidationError,
)


class SensitiveDetails:
    def __repr__(self) -> str:
        return "secret-details"


def test_api_error_repr_keeps_classification_but_redacts_payloads() -> None:
    error = ValidationError(
        status_code=422,
        code="VALIDATION_ERROR",
        message="secret-message",
        details=SensitiveDetails(),
        trace_id="secret-trace",
    )

    rendered = repr(error)
    assert rendered.startswith("ValidationError(status_code=422, code='VALIDATION_ERROR'")
    assert rendered.count("<redacted>") == 3
    assert "secret-message" not in rendered
    assert "secret-details" not in rendered
    assert "secret-trace" not in rendered

    diagnostic = str(error)
    assert "VALIDATION_ERROR" in diagnostic
    assert "secret-message" in diagnostic
    assert "HTTP 422" in diagnostic
    assert "secret-trace" in diagnostic


def test_api_error_repr_distinguishes_absent_optional_values() -> None:
    error = ValidationError(400, "VALIDATION_ERROR", "invalid")

    rendered = repr(error)
    assert "message='<redacted>'" in rendered
    assert "details=None" in rendered
    assert "trace_id=None" in rendered


def test_transport_and_protocol_error_repr_redacts_diagnostics() -> None:
    errors = [
        APIConnectionError("secret-operation"),
        APITimeoutError("secret-timeout-operation"),
        ProtocolError("secret-protocol-message"),
    ]

    for error in errors:
        rendered = repr(error)
        assert type(error).__name__ in rendered
        assert "<redacted>" in rendered
        assert "secret" not in rendered
        assert "secret" in str(error)


def test_operation_error_repr_redacts_resource_and_server_error() -> None:
    failed = OperationFailedError("secret-operation-id", "secret-provider-error")
    timed_out = OperationTimeoutError("secret-timeout-id", 12.5)

    assert repr(failed) == ("OperationFailedError(operation_id='<redacted>', error='<redacted>')")
    assert "secret-operation-id" not in repr(failed)
    assert "secret-provider-error" not in repr(failed)
    assert "secret-operation-id" in str(failed)
    assert "secret-provider-error" in str(failed)

    assert repr(timed_out) == (
        "OperationTimeoutError(operation_id='<redacted>', timeout_seconds=12.5)"
    )
    assert "secret-timeout-id" not in repr(timed_out)
    assert "secret-timeout-id" in str(timed_out)
    assert "12.5s" in str(timed_out)


@pytest.mark.parametrize(
    "error",
    [
        HumalikeError("diagnostic"),
        APIConnectionError("connect"),
        APITimeoutError("request"),
        HumalikeAPIError(
            status_code=418,
            code="TEAPOT",
            message="message",
            details={"field": "value"},
            trace_id="trace-1",
        ),
        AuthenticationError(status_code=401, code="UNAUTHORIZED", message="message"),
        PaymentRequiredError(
            status_code=402,
            code="PAYMENT_REQUIRED",
            message="message",
        ),
        PermissionDeniedError(status_code=403, code="FORBIDDEN", message="message"),
        ValidationError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="message",
            details={"field": "value"},
        ),
        UpstreamError(status_code=502, code="UPSTREAM_ERROR", message="message"),
        ProtocolError("unexpected response"),
        OperationFailedError("operation-1", "provider failure"),
        OperationTimeoutError("operation-2", 12.5),
    ],
)
def test_public_exceptions_round_trip_through_pickle(error: HumalikeError) -> None:
    restored = pickle.loads(pickle.dumps(error))

    assert type(restored) is type(error)
    assert restored.args == error.args
    assert vars(restored) == vars(error)
    assert str(restored) == str(error)
    assert repr(restored) == repr(error)
