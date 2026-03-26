from __future__ import annotations

import logging

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
) -> None:
    """Missing required env vars should stop collection before any API call."""
    monkeypatch.setattr(collect, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

    caplog.set_level(logging.ERROR)
    result = collect.main(["--engine", "perplexity"])

    assert result == collect.ExitCode.FAILURE
    assert "Missing required environment variables: PERPLEXITY_API_KEY" in caplog.text
