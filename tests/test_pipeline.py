from __future__ import annotations

import pipeline


def test_pipeline_stops_when_collect_fails(monkeypatch, tmp_path) -> None:
    """Generate must not start if collect exits non-zero."""
    monkeypatch.setattr(pipeline, "setup_logging", lambda _root: tmp_path / "pipeline.log")
    monkeypatch.setattr(pipeline, "collect_main", lambda _argv: pipeline.CollectExitCode.PARTIAL_FAILURE)
    monkeypatch.setattr(
        pipeline,
        "generate_main",
        lambda _argv: (_ for _ in ()).throw(AssertionError("generate must not run")),
    )

    result = pipeline.main()

    assert result == pipeline.CollectExitCode.PARTIAL_FAILURE


def test_pipeline_runs_generate_after_successful_collect(monkeypatch, tmp_path) -> None:
    """Generate should run after a successful collect step."""
    monkeypatch.setattr(pipeline, "setup_logging", lambda _root: tmp_path / "pipeline.log")
    monkeypatch.setattr(pipeline, "collect_main", lambda _argv: pipeline.CollectExitCode.SUCCESS)
    monkeypatch.setattr(pipeline, "generate_main", lambda _argv: pipeline.GenerateExitCode.PARTIAL_FAILURE)

    result = pipeline.main()

    assert result == pipeline.GenerateExitCode.PARTIAL_FAILURE
