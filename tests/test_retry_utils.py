from __future__ import annotations

import pytest

from src import retry_utils


def test_retry_call_retries_until_success(monkeypatch) -> None:
    """Transient failures should be retried with the configured budget."""
    attempts = {"count": 0}
    monkeypatch.setattr(retry_utils.time, "sleep", lambda *_args, **_kwargs: None)

    def flaky_operation() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ValueError("temporary failure")
        return "ok"

    result = retry_utils.retry_call(
        flaky_operation,
        operation="flaky operation",
        attempts=3,
        retry_exceptions=(ValueError,),
    )

    assert result == "ok"
    assert attempts["count"] == 3


def test_retry_call_stops_when_predicate_rejects_retry(monkeypatch) -> None:
    """Permanent failures should surface immediately without exhausting retries."""
    attempts = {"count": 0}
    monkeypatch.setattr(retry_utils.time, "sleep", lambda *_args, **_kwargs: None)

    def permanent_failure() -> str:
        attempts["count"] += 1
        raise ValueError("do not retry")

    with pytest.raises(ValueError):
        retry_utils.retry_call(
            permanent_failure,
            operation="permanent failure",
            attempts=3,
            retry_exceptions=(ValueError,),
            should_retry=lambda _exc: False,
        )

    assert attempts["count"] == 1
