#!/usr/bin/env python3
"""Retry helpers for transient external API failures."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def retry_call(
    func: Callable[[], T],
    *,
    operation: str,
    attempts: int = 3,
    base_delay: float = 1.0,
    retry_exceptions: tuple[type[BaseException], ...] = (Exception,),
    should_retry: Callable[[BaseException], bool] | None = None,
    logger: logging.Logger | None = None,
) -> T:
    """Run a callable with exponential backoff for transient failures."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    for attempt in range(1, attempts + 1):
        try:
            return func()
        except retry_exceptions as exc:
            can_retry = attempt < attempts and (
                should_retry(exc) if should_retry is not None else True
            )
            if not can_retry:
                raise

            delay = base_delay * (2 ** (attempt - 1))
            if logger is not None:
                logger.warning(
                    "%s failed on attempt %d/%d: %s. Retrying in %.1f seconds.",
                    operation,
                    attempt,
                    attempts,
                    exc,
                    delay,
                )
            time.sleep(delay)

    raise RuntimeError(f"{operation} failed unexpectedly")
