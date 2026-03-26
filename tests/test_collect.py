from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pytest
from src import collect


def test_deduplicate_removes_duplicate_urls() -> None:
    """Keep the first article per URL and preserve unique/empty URLs."""
    articles = [
        {"title": "first", "url": "https://example.com/a"},
        {"title": "duplicate", "url": "https://example.com/a"},
        {"title": "empty", "url": ""},
        {"title": "second", "url": "https://example.com/b"},
    ]

    result = collect.deduplicate(articles)

    assert result == [
        {"title": "first", "url": "https://example.com/a"},
        {"title": "empty", "url": ""},
        {"title": "second", "url": "https://example.com/b"},
    ]


def test_main_fails_fast_when_required_env_is_missing(
    monkeypatch,
    caplog,
    tmp_path,
) -> None:
    """Missing required env vars should stop collection before any API call."""
    monkeypatch.setattr(collect, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        collect,
        "_load_logging_setup",
        lambda: (lambda _project_root: tmp_path / "logs" / "pipeline-2026-03-26.log"),
    )
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

    caplog.set_level(logging.ERROR)
    result = collect.main(["--engine", "perplexity"])

    assert result == collect.ExitCode.FAILURE
    assert "Missing required environment variables: PERPLEXITY_API_KEY" in caplog.text


def test_main_uses_evergreen_fallback_when_perplexity_returns_no_articles(
    monkeypatch,
    tmp_path,
) -> None:
    """An empty Perplexity result should fall back to evergreen topics."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    evergreen_path = tmp_path / "evergreen_topics.json"
    evergreen_path.write_text(
        json.dumps(
            [
                {
                    "id": "ev001",
                    "title": "AI feasibility in housing",
                    "category": "проектирование",
                    "used": False,
                }
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(collect, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        collect,
        "_load_logging_setup",
        lambda: (lambda _project_root: tmp_path / "logs" / "pipeline-2026-03-26.log"),
    )
    monkeypatch.setattr(
        collect,
        "_load_collectors",
        lambda: (lambda _api_key: [], lambda _channels, _api_key: []),
    )
    monkeypatch.setenv("PERPLEXITY_API_KEY", "token")
    monkeypatch.setattr(collect, "EVERGREEN_TOPICS_PATH", evergreen_path)
    monkeypatch.setattr(collect, "ARTICLES_DIR", tmp_path / "articles")

    result = collect.main(["--engine", "perplexity"])

    saved_path = tmp_path / "articles" / f"{today}.json"
    saved_articles = json.loads(saved_path.read_text(encoding="utf-8"))

    assert result == collect.ExitCode.SUCCESS
    assert saved_articles[0]["source_name"] == "Evergreen Topics"
    assert saved_articles[0]["url"] == "evergreen://ev001"


def test_main_does_not_mask_perplexity_failure_with_evergreen(
    monkeypatch,
    tmp_path,
) -> None:
    """Evergreen fallback should not convert real source failures into success."""
    monkeypatch.setattr(collect, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        collect,
        "_load_logging_setup",
        lambda: (lambda _project_root: tmp_path / "logs" / "pipeline-2026-03-26.log"),
    )

    def failing_search(_api_key: str) -> list[dict[str, str]]:
        raise RuntimeError("Perplexity down")

    monkeypatch.setattr(
        collect,
        "_load_collectors",
        lambda: (failing_search, lambda _channels, _api_key: []),
    )
    monkeypatch.setattr(
        collect,
        "build_evergreen_articles",
        lambda: pytest.fail("evergreen fallback must not mask source failures"),
    )
    monkeypatch.setenv("PERPLEXITY_API_KEY", "token")
    monkeypatch.setattr(collect, "ARTICLES_DIR", tmp_path / "articles")

    result = collect.main(["--engine", "perplexity"])

    assert result == collect.ExitCode.FAILURE
    assert not (tmp_path / "articles").exists()
