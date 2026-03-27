#!/usr/bin/env python3
"""Background scheduler for running the content pipeline inside the bot service."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .pipeline_runner import run_pipeline

logger = logging.getLogger(__name__)
TRUE_ENV_VALUES = {"1", "true", "yes", "on"}


def _env_flag(value: str | None) -> bool:
    """Interpret common truthy env values."""
    return str(value or "").strip().lower() in TRUE_ENV_VALUES


@dataclass(frozen=True)
class PipelineSchedulerConfig:
    """Validated runtime configuration for the background scheduler."""

    enabled: bool
    interval_minutes: int
    run_on_start: bool


def load_scheduler_config(
    environ: Mapping[str, str] | None = None,
) -> PipelineSchedulerConfig:
    """Load and validate scheduler config from environment variables."""
    env = environ or os.environ
    enabled = _env_flag(env.get("PIPELINE_SCHEDULER_ENABLED"))
    run_on_start = _env_flag(env.get("PIPELINE_RUN_ON_START"))

    raw_interval = str(env.get("PIPELINE_INTERVAL_MINUTES", "180")).strip() or "180"
    try:
        interval_minutes = int(raw_interval)
    except ValueError as exc:
        raise ValueError(
            "PIPELINE_INTERVAL_MINUTES must be an integer number of minutes"
        ) from exc

    if interval_minutes <= 0:
        raise ValueError("PIPELINE_INTERVAL_MINUTES must be greater than zero")

    return PipelineSchedulerConfig(
        enabled=enabled,
        interval_minutes=interval_minutes,
        run_on_start=run_on_start,
    )


class PipelineScheduler:
    """Daemon thread that periodically runs `collect -> generate`."""

    def __init__(
        self,
        *,
        runner: Callable[[], int],
        interval_minutes: int,
        run_on_start: bool,
    ) -> None:
        self._runner = runner
        self._interval_seconds = interval_minutes * 60
        self._interval_minutes = interval_minutes
        self._run_on_start = run_on_start
        self._stop_event = threading.Event()
        self._run_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the daemon scheduler thread once."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._thread = threading.Thread(
            target=self._run_loop,
            name="pipeline-scheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Pipeline scheduler enabled: every %d minutes%s",
            self._interval_minutes,
            " with run-on-start" if self._run_on_start else "",
        )

    def stop(self, *, timeout: float = 5.0) -> None:
        """Stop the scheduler thread. Used by tests and clean shutdowns."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def run_now(self, *, trigger: str) -> bool:
        """Run the pipeline immediately unless a previous run is still active."""
        if not self._run_lock.acquire(blocking=False):
            logger.warning(
                "Skipping %s pipeline run because a previous run is still active",
                trigger,
            )
            return False

        try:
            logger.info("Starting %s pipeline run", trigger)
            exit_code = int(self._runner())
        except Exception:
            logger.exception("Scheduled pipeline run crashed during %s trigger", trigger)
        else:
            if exit_code == 0:
                logger.info("Finished %s pipeline run successfully", trigger)
            else:
                logger.warning(
                    "Finished %s pipeline run with exit code %d",
                    trigger,
                    exit_code,
                )
        finally:
            self._run_lock.release()

        return True

    def _run_loop(self) -> None:
        """Loop forever until stop is requested."""
        if self._run_on_start:
            self.run_now(trigger="startup")

        while not self._stop_event.wait(self._interval_seconds):
            self.run_now(trigger="scheduled")


def start_scheduler_from_env(
    runner: Callable[[], int] | None = None,
    environ: Mapping[str, str] | None = None,
) -> PipelineScheduler | None:
    """Start the scheduler when explicitly enabled via env vars."""
    config = load_scheduler_config(environ)
    if not config.enabled:
        return None

    scheduler = PipelineScheduler(
        runner=runner or (lambda: run_pipeline(configure_logging=False)),
        interval_minutes=config.interval_minutes,
        run_on_start=config.run_on_start,
    )
    scheduler.start()
    return scheduler
