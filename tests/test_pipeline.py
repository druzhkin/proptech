from __future__ import annotations

from src import pipeline_runner


def test_pipeline_stops_when_collect_fails(monkeypatch, tmp_path) -> None:
    """Generate must not start if collect exits non-zero."""
    monkeypatch.setattr(
        pipeline_runner,
        "setup_logging",
        lambda _root: tmp_path / "pipeline.log",
    )
    monkeypatch.setattr(
        pipeline_runner,
        "collect_main",
        lambda _argv: pipeline_runner.CollectExitCode.PARTIAL_FAILURE,
    )
    monkeypatch.setattr(
        pipeline_runner,
        "generate_main",
        lambda _argv: (_ for _ in ()).throw(AssertionError("generate must not run")),
    )

    result = pipeline_runner.run_pipeline()

    assert result == pipeline_runner.CollectExitCode.PARTIAL_FAILURE


def test_pipeline_runs_generate_after_successful_collect(monkeypatch, tmp_path) -> None:
    """Generate should run after a successful collect step."""
    monkeypatch.setattr(
        pipeline_runner,
        "setup_logging",
        lambda _root: tmp_path / "pipeline.log",
    )
    monkeypatch.setattr(
        pipeline_runner,
        "collect_main",
        lambda _argv: pipeline_runner.CollectExitCode.SUCCESS,
    )
    monkeypatch.setattr(
        pipeline_runner,
        "generate_main",
        lambda _argv: pipeline_runner.GenerateExitCode.PARTIAL_FAILURE,
    )

    result = pipeline_runner.run_pipeline()

    assert result == pipeline_runner.GenerateExitCode.PARTIAL_FAILURE
