from __future__ import annotations

import json

from src import generate


def test_load_articles_uses_latest_available_file(tmp_path, monkeypatch) -> None:
    """When today's file is missing, generation should use the latest available date."""
    articles_dir = tmp_path / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)
    (articles_dir / "2026-03-20.json").write_text("[]", encoding="utf-8")
    (articles_dir / "2026-03-25.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(generate, "ARTICLES_DIR", articles_dir)

    articles_date, articles = generate.load_articles()

    assert articles_date == "2026-03-25"
    assert articles == []


def test_save_drafts_preserves_published_records(tmp_path, monkeypatch) -> None:
    """Reruns should not overwrite already published drafts."""
    drafts_dir = tmp_path / "drafts"
    monkeypatch.setattr(generate, "DRAFTS_DIR", drafts_dir)
    drafts_dir.mkdir(parents=True, exist_ok=True)
    existing_path = drafts_dir / "2026-03-26.json"
    existing_path.write_text(
        json.dumps(
            [
                {
                    "id": "draft-1",
                    "article_id": "article-1",
                    "status": "published",
                    "text": "published text",
                }
            ]
        ),
        encoding="utf-8",
    )

    generate.save_drafts(
        "2026-03-26",
        [
            {
                "id": "draft-2",
                "article_id": "article-1",
                "status": "draft",
                "text": "new text",
            }
        ],
    )

    saved = json.loads(existing_path.read_text(encoding="utf-8"))

    assert saved[0]["status"] == "published"
    assert saved[0]["text"] == "published text"


def test_main_saves_drafts_and_rejects_evergreen(monkeypatch, tmp_path) -> None:
    """Generation should create drafts for real articles and reject evergreen placeholders."""
    articles_dir = tmp_path / "articles"
    drafts_dir = tmp_path / "drafts"
    articles_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir.mkdir(parents=True, exist_ok=True)

    (articles_dir / "2026-03-26.json").write_text(
        json.dumps(
            [
                {
                    "id": "article-1",
                    "source_type": "perplexity",
                    "source_name": "Perplexity",
                    "title": "AI for planning",
                    "url": "https://example.com/a1",
                    "text": "Long article body",
                    "image_url": None,
                    "date": "2026-03-26",
                    "category_hint": "проектирование",
                    "collected_at": "2026-03-26T00:00:00+00:00",
                },
                {
                    "id": "ev001",
                    "source_type": "perplexity",
                    "source_name": "Evergreen Topics",
                    "title": "Evergreen placeholder",
                    "url": "evergreen://ev001",
                    "text": "Placeholder",
                    "image_url": None,
                    "date": "2026-03-26",
                    "category_hint": "аналитика",
                    "collected_at": "2026-03-26T00:00:00+00:00",
                },
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(generate, "ARTICLES_DIR", articles_dir)
    monkeypatch.setattr(generate, "DRAFTS_DIR", drafts_dir)
    monkeypatch.setattr(generate, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        generate,
        "_load_logging_setup",
        lambda: (lambda _project_root: tmp_path / "logs" / "pipeline-2026-03-26.log"),
    )
    monkeypatch.setattr(
        generate,
        "_load_claude_client",
        lambda: (
            lambda _api_key, articles, max_items=5: list(articles[:max_items]),
            lambda _api_key, article: (
                {
                    "text": f"🚀 Useful draft with link {article['url']}",
                    "category": "PropTech",
                },
                [],
            ),
        ),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "token")

    result = generate.main(["--date", "2026-03-26", "--max", "5"])
    saved = json.loads((drafts_dir / "2026-03-26.json").read_text(encoding="utf-8"))

    assert result == generate.ExitCode.PARTIAL_FAILURE
    assert len(saved) == 2
    assert {record["status"] for record in saved} == {"draft", "rejected"}
    assert any(record["rejection_reason"] == "evergreen_placeholder_requires_source_link" for record in saved)
