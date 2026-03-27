from __future__ import annotations

import threading

import pytest

from src import pipeline_runner, pipeline_scheduler


def test_load_scheduler_config_defaults_to_disabled() -> None:
    """Scheduler should stay opt-in unless the env explicitly enables it."""
    config = pipeline_scheduler.load_scheduler_config({})

    assert config.enabled is False
    assert config.interval_minutes == 180
    assert config.run_on_start is False


def test_load_scheduler_config_rejects_invalid_interval() -> None:
    """Broken interval env should fail fast instead of silently disabling automation."""
    with pytest.raises(ValueError):
        pipeline_scheduler.load_scheduler_config(
            {
                "PIPELINE_SCHEDULER_ENABLED": "1",
                "PIPELINE_INTERVAL_MINUTES": "abc",
            }
        )


def test_start_scheduler_from_env_returns_none_when_disabled() -> None:
    """No background thread should start when automation is disabled."""
    scheduler = pipeline_scheduler.start_scheduler_from_env(
        runner=lambda: 0,
        environ={},
    )

    assert scheduler is None


def test_scheduler_runs_immediately_on_start() -> None:
    """Run-on-start should trigger one immediate pipeline pass."""
    calls: list[str] = []
    started = threading.Event()
    release = threading.Event()

    def fake_runner() -> int:
        calls.append("run")
        started.set()
        release.wait(timeout=1)
        return 0

    scheduler = pipeline_scheduler.PipelineScheduler(
        runner=fake_runner,
        interval_minutes=60,
        run_on_start=True,
    )
    scheduler.start()

    assert started.wait(timeout=1) is True

    release.set()
    scheduler.stop()
    assert calls == ["run"]


def test_scheduler_skips_overlapping_runs() -> None:
    """A second trigger should be skipped while the previous run is still active."""
    entered = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    def fake_runner() -> int:
        calls.append("run")
        entered.set()
        release.wait(timeout=1)
        return 0

    scheduler = pipeline_scheduler.PipelineScheduler(
        runner=fake_runner,
        interval_minutes=60,
        run_on_start=False,
    )

    background = threading.Thread(
        target=lambda: scheduler.run_now(trigger="first"),
        daemon=True,
    )
    background.start()
    assert entered.wait(timeout=1) is True

    assert scheduler.run_now(trigger="second") is False

    release.set()
    background.join(timeout=1)
    scheduler.stop()
    assert calls == ["run"]


def test_run_pipeline_can_skip_logging_setup(monkeypatch) -> None:
    """Embedded scheduler runs should reuse the bot process logging configuration."""
    calls: list[str] = []

    monkeypatch.setattr(
        pipeline_runner,
        "collect_main",
        lambda _argv: calls.append("collect") or 0,
    )
    monkeypatch.setattr(
        pipeline_runner,
        "generate_main",
        lambda _argv: calls.append("generate") or 0,
    )
    monkeypatch.setattr(
        pipeline_runner,
        "setup_logging",
        lambda _project_root: calls.append("logging"),
    )

    result = pipeline_runner.run_pipeline(configure_logging=False)

    assert result == 0
    assert calls == ["collect", "generate"]
