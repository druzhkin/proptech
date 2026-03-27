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


def test_save_drafts_preserves_skipped_and_admin_edited_records(tmp_path, monkeypatch) -> None:
    """Reruns should not resurrect skipped drafts or overwrite admin edits."""
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
                    "status": "skipped",
                    "text": "skip me",
                },
                {
                    "id": "draft-2",
                    "article_id": "article-2",
                    "status": "draft",
                    "text": "admin text",
                    "edited_by_admin": True,
                },
            ]
        ),
        encoding="utf-8",
    )

    generate.save_drafts(
        "2026-03-26",
        [
            {
                "id": "new-draft-1",
                "article_id": "article-1",
                "status": "draft",
                "text": "should not replace skipped",
            },
            {
                "id": "new-draft-2",
                "article_id": "article-2",
                "status": "draft",
                "text": "should not replace admin edit",
            },
        ],
    )

    saved = json.loads(existing_path.read_text(encoding="utf-8"))
    by_article_id = {record["article_id"]: record for record in saved}

    assert by_article_id["article-1"]["status"] == "skipped"
    assert by_article_id["article-1"]["text"] == "skip me"
    assert by_article_id["article-2"]["edited_by_admin"] is True
    assert by_article_id["article-2"]["text"] == "admin text"


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
    monkeypatch.setenv("OPENROUTER_API_KEY", "token")

    result = generate.main(["--date", "2026-03-26", "--max", "5"])
    saved = json.loads((drafts_dir / "2026-03-26.json").read_text(encoding="utf-8"))

    assert result == generate.ExitCode.PARTIAL_FAILURE
    assert len(saved) == 2
    assert {record["status"] for record in saved} == {"draft", "rejected"}
    assert any(record["rejection_reason"] == "evergreen_placeholder_requires_source_link" for record in saved)


def test_is_business_noise_rejects_business_first_headlines_even_with_tech_claims() -> None:
    """Funding and acquisition angles should be rejected even if they mention technology."""
    business_only = {
        "title": "Startup raises Series A for real estate marketplace",
        "text": "The company raised funding from investors and shared valuation details.",
        "category_hint": "funding",
        "source_name": "Example",
        "url": "https://example.com/funding",
    }
    business_with_tech_spin = {
        "title": "Startup raises Series A after shipping BIM automation",
        "text": "The release includes BIM clash detection, workflow automation, and field deployment data.",
        "category_hint": "automation",
        "source_name": "Example",
        "url": "https://example.com/tech",
    }

    assert generate._is_business_noise(business_only) is True  # noqa: SLF001
    assert generate._is_business_noise(business_with_tech_spin) is True  # noqa: SLF001


def test_is_business_noise_ignores_late_investor_mentions_when_headline_is_technical() -> None:
    """Incidental investor mentions should not kill an otherwise technical story."""
    article = {
        "title": "Drone surveying workflow cuts site capture to one flight",
        "text": "Builders are using RTK drones on active sites. Investors were mentioned in a background paragraph.",
        "category_hint": "automation",
        "source_name": "Example",
        "url": "https://example.com/drone",
    }

    assert generate._is_business_noise(article) is False  # noqa: SLF001


def test_main_rejects_business_only_articles_before_generation(monkeypatch, tmp_path) -> None:
    """Funding-first stories should be rejected before model generation starts."""
    articles_dir = tmp_path / "articles"
    drafts_dir = tmp_path / "drafts"
    articles_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir.mkdir(parents=True, exist_ok=True)

    (articles_dir / "2026-03-27.json").write_text(
        json.dumps(
            [
                {
                    "id": "article-tech",
                    "source_type": "perplexity",
                    "source_name": "Perplexity",
                    "title": "AI scheduling tool cuts coordination time",
                    "url": "https://example.com/tech",
                    "text": "The product automates field scheduling and integrates with BIM models.",
                    "image_url": None,
                    "date": "2026-03-27",
                    "category_hint": "automation",
                    "collected_at": "2026-03-27T00:00:00+00:00",
                },
                {
                    "id": "article-funding",
                    "source_type": "perplexity",
                    "source_name": "Perplexity",
                    "title": "PropTech startup raises Series B",
                    "url": "https://example.com/funding",
                    "text": "The company raised funding from investors and discussed valuation.",
                    "image_url": None,
                    "date": "2026-03-27",
                    "category_hint": "funding",
                    "collected_at": "2026-03-27T00:00:00+00:00",
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
        lambda: (lambda _project_root: tmp_path / "logs" / "pipeline-2026-03-27.log"),
    )
    monkeypatch.setattr(
        generate,
        "_load_claude_client",
        lambda: (
            lambda _api_key, articles, max_items=5: list(articles[:max_items]),
            lambda _api_key, article: (
                {
                    "text": f"Useful draft with link {article['url']}",
                    "category": "PropTech",
                },
                [],
            ),
        ),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "token")

    result = generate.main(["--date", "2026-03-27", "--max", "5"])
    saved = json.loads((drafts_dir / "2026-03-27.json").read_text(encoding="utf-8"))
    by_article_id = {record["article_id"]: record for record in saved}

    assert result == generate.ExitCode.PARTIAL_FAILURE
    assert by_article_id["article-tech"]["status"] == "draft"
    assert (
        by_article_id["article-funding"]["rejection_reason"]
        == "editorial_policy_non_technical_or_investment"
    )


def test_main_rejects_articles_that_do_not_fit_cio_radar(monkeypatch, tmp_path) -> None:
    """Stories without a clear CIO-facing tool angle should be rejected before generation."""
    articles_dir = tmp_path / "articles"
    drafts_dir = tmp_path / "drafts"
    articles_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir.mkdir(parents=True, exist_ok=True)

    (articles_dir / "2026-03-27.json").write_text(
        json.dumps(
            [
                {
                    "id": "article-github",
                    "source_type": "perplexity",
                    "source_name": "GitHub",
                    "title": "Self-hosted document AI stack ships Docker setup",
                    "url": "https://github.com/example/doc-stack",
                    "text": "The repo combines OCR, semantic search, and local models for internal knowledge workflows.",
                    "image_url": None,
                    "date": "2026-03-27",
                    "category_hint": "automation",
                    "collected_at": "2026-03-27T00:00:00+00:00",
                },
                {
                    "id": "article-corp",
                    "source_type": "perplexity",
                    "source_name": "Corporate newsroom",
                    "title": "Vendor expands strategic partnership with developer",
                    "url": "https://example.com/partnership",
                    "text": "The companies plan to collaborate in several markets. Public technical detail was not shared.",
                    "image_url": None,
                    "date": "2026-03-27",
                    "category_hint": "partnership",
                    "collected_at": "2026-03-27T00:00:00+00:00",
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
        lambda: (lambda _project_root: tmp_path / "logs" / "pipeline-2026-03-27.log"),
    )
    monkeypatch.setattr(
        generate,
        "_load_claude_client",
        lambda: (
            lambda _api_key, articles, max_items=5: list(articles[:max_items]),
            lambda _api_key, article: (
                {
                    "text": f"Useful draft with link {article['url']}",
                    "category": "Automation",
                },
                [],
            ),
        ),
    )
    monkeypatch.setattr(
        generate,
        "_load_editorial_policy",
        lambda: (
            lambda article: {
                "score": 9 if article["id"] == "article-github" else 1,
                "track_ids": ["open_source_tooling"] if article["id"] == "article-github" else [],
                "track_labels": ["Installable open-source or self-hosted tools"] if article["id"] == "article-github" else [],
                "business_function_ids": ["it_platform"] if article["id"] == "article-github" else [],
                "business_functions": ["it platform"] if article["id"] == "article-github" else [],
                "angle": "Treat it like a tool radar item.",
            }
        ),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "token")

    result = generate.main(["--date", "2026-03-27", "--max", "5"])
    saved = json.loads((drafts_dir / "2026-03-27.json").read_text(encoding="utf-8"))
    by_article_id = {record["article_id"]: record for record in saved}

    assert result == generate.ExitCode.PARTIAL_FAILURE
    assert by_article_id["article-github"]["status"] == "draft"
    assert (
        by_article_id["article-corp"]["rejection_reason"]
        == "editorial_policy_off_target_for_cio"
    )


def test_main_generates_all_eligible_articles_when_max_is_unset(monkeypatch, tmp_path) -> None:
    """Without --max, generation should create drafts for every eligible article."""
    articles_dir = tmp_path / "articles"
    drafts_dir = tmp_path / "drafts"
    articles_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir.mkdir(parents=True, exist_ok=True)

    articles = []
    for index in range(1, 8):
        articles.append(
            {
                "id": f"article-{index}",
                "source_type": "perplexity",
                "source_name": "Perplexity",
                "title": f"AI planning workflow {index}",
                "url": f"https://example.com/{index}",
                "text": "AI planning workflow integrates with BIM and scheduling.",
                "image_url": None,
                "date": "2026-03-27",
                "category_hint": "automation",
                "collected_at": "2026-03-27T00:00:00+00:00",
            }
        )

    (articles_dir / "2026-03-27.json").write_text(
        json.dumps(articles),
        encoding="utf-8",
    )

    monkeypatch.setattr(generate, "ARTICLES_DIR", articles_dir)
    monkeypatch.setattr(generate, "DRAFTS_DIR", drafts_dir)
    monkeypatch.setattr(generate, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        generate,
        "_load_logging_setup",
        lambda: (lambda _project_root: tmp_path / "logs" / "pipeline-2026-03-27.log"),
    )
    monkeypatch.setattr(
        generate,
        "_load_claude_client",
        lambda: (
            lambda _api_key, selected_articles, max_items=None: list(selected_articles),
            lambda _api_key, article: (
                {
                    "text": f"Useful draft with link {article['url']}",
                    "category": "Automation",
                },
                [],
            ),
        ),
    )
    monkeypatch.setattr(
        generate,
        "_load_editorial_policy",
        lambda: (
            lambda _article: {
                "score": 8,
                "track_ids": ["bim_and_digital_twin"],
                "track_labels": ["BIM, design tools, digital twins, and data layers"],
                "business_function_ids": ["construction"],
                "business_functions": ["construction"],
                "angle": "Focus on the workflow shift.",
            }
        ),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "token")

    result = generate.main(["--date", "2026-03-27"])
    saved = json.loads((drafts_dir / "2026-03-27.json").read_text(encoding="utf-8"))
    draft_records = [record for record in saved if record["status"] == "draft"]

    assert result == generate.ExitCode.SUCCESS
    assert len(draft_records) == 7


def test_main_excludes_terminal_records_from_new_selection_slots(monkeypatch, tmp_path) -> None:
    """Published and skipped records should not reduce the number of fresh drafts."""
    articles_dir = tmp_path / "articles"
    drafts_dir = tmp_path / "drafts"
    articles_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir.mkdir(parents=True, exist_ok=True)

    articles = []
    for index in range(1, 8):
        articles.append(
            {
                "id": f"article-{index}",
                "source_type": "perplexity",
                "source_name": "Perplexity",
                "title": f"Interesting tech story {index}",
                "url": f"https://example.com/{index}",
                "text": "AI planning workflow integrates with BIM and scheduling.",
                "image_url": None,
                "date": "2026-03-27",
                "category_hint": "automation",
                "collected_at": "2026-03-27T00:00:00+00:00",
            }
        )

    (articles_dir / "2026-03-27.json").write_text(
        json.dumps(articles),
        encoding="utf-8",
    )
    (drafts_dir / "2026-03-27.json").write_text(
        json.dumps(
            [
                {"id": "draft-1", "article_id": "article-1", "status": "published"},
                {"id": "draft-2", "article_id": "article-2", "status": "skipped"},
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
        lambda: (lambda _project_root: tmp_path / "logs" / "pipeline-2026-03-27.log"),
    )
    monkeypatch.setattr(
        generate,
        "_load_claude_client",
        lambda: (
            lambda _api_key, selected_articles, max_items=None: list(selected_articles[:max_items]),
            lambda _api_key, article: (
                {
                    "text": f"Useful draft with link {article['url']}",
                    "category": "Automation",
                },
                [],
            ),
        ),
    )
    monkeypatch.setattr(
        generate,
        "_load_editorial_policy",
        lambda: (
            lambda _article: {
                "score": 8,
                "track_ids": ["bim_and_digital_twin"],
                "track_labels": ["BIM, design tools, digital twins, and data layers"],
                "business_function_ids": ["construction"],
                "business_functions": ["construction"],
                "angle": "Focus on the workflow shift.",
            }
        ),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "token")

    result = generate.main(["--date", "2026-03-27", "--max", "5"])
    saved = json.loads((drafts_dir / "2026-03-27.json").read_text(encoding="utf-8"))
    draft_records = [record for record in saved if record["status"] == "draft"]

    assert result == generate.ExitCode.SUCCESS
    assert len(draft_records) == 5
    assert {record["article_id"] for record in draft_records} == {
        "article-3",
        "article-4",
        "article-5",
        "article-6",
        "article-7",
    }


def test_main_sanitizes_existing_invalid_draft_records(monkeypatch, tmp_path) -> None:
    """Previously queued digest-like drafts should be demoted on the next generation run."""
    articles_dir = tmp_path / "articles"
    drafts_dir = tmp_path / "drafts"
    articles_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir.mkdir(parents=True, exist_ok=True)

    (articles_dir / "2026-03-27.json").write_text(
        json.dumps(
            [
                {
                    "id": "article-valid",
                    "source_type": "perplexity",
                    "source_name": "Perplexity",
                    "title": "AI planning workflow",
                    "url": "https://example.com/valid",
                    "text": "AI planning workflow integrates with BIM and scheduling.",
                    "image_url": None,
                    "date": "2026-03-27",
                    "category_hint": "automation",
                    "collected_at": "2026-03-27T00:00:00+00:00",
                }
            ]
        ),
        encoding="utf-8",
    )
    (drafts_dir / "2026-03-27.json").write_text(
        json.dumps(
            [
                {
                    "id": "draft-old",
                    "article_id": "article-bad",
                    "source_type": "perplexity",
                    "source_name": "Perplexity Deep Research",
                    "title": "PropTech Weekly Digest",
                    "url": "",
                    "category": "Data & BIM",
                    "text": "Поиск технических новостей в PropTech сталкивается с фундаментальной проблемой сигнала и шума.",
                    "status": "draft",
                }
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
        lambda: (lambda _project_root: tmp_path / "logs" / "pipeline-2026-03-27.log"),
    )
    monkeypatch.setattr(
        generate,
        "_load_claude_client",
        lambda: (
            lambda _api_key, selected_articles, max_items=None: list(selected_articles),
            lambda _api_key, article: (
                {
                    "text": f"Useful draft with link {article['url']}",
                    "category": "Automation",
                },
                [],
            ),
        ),
    )
    monkeypatch.setattr(
        generate,
        "_load_editorial_policy",
        lambda: (
            lambda article: {
                "score": 8 if article["id"] == "article-valid" else 0,
                "track_ids": ["bim_and_digital_twin"] if article["id"] == "article-valid" else [],
                "track_labels": ["BIM, design tools, digital twins, and data layers"] if article["id"] == "article-valid" else [],
                "business_function_ids": ["construction"] if article["id"] == "article-valid" else [],
                "business_functions": ["construction"] if article["id"] == "article-valid" else [],
                "angle": "Focus on the workflow shift.",
            }
        ),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "token")

    result = generate.main(["--date", "2026-03-27"])
    saved = json.loads((drafts_dir / "2026-03-27.json").read_text(encoding="utf-8"))
    by_article_id = {record["article_id"]: record for record in saved}

    assert result == generate.ExitCode.SUCCESS
    assert by_article_id["article-bad"]["status"] == "rejected"
    assert by_article_id["article-bad"]["rejection_reason"] == "missing_source_url"
    assert by_article_id["article-valid"]["status"] == "draft"


def test_editorial_rejection_reason_rejects_limitation_meta_articles() -> None:
    """Meta answers from upstream collection should never reach generation as drafts."""
    article = {
        "title": "\u041e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f \u0438 \u0447\u0435\u0441\u0442\u043d\u044b\u0439 \u043e\u0442\u0432\u0435\u0442",
        "text": "My knowledge cutoff is April 2024. What I can offer instead...",
        "url": "",
        "category_hint": "unknown",
        "source_name": "Perplexity",
    }

    assert generate._editorial_rejection_reason(article) == "invalid_source_content"  # noqa: SLF001


def test_editorial_rejection_reason_rejects_articles_without_source_url() -> None:
    """Unsourced articles should never become Telegram drafts."""
    article = {
        "title": "Interesting AI workflow for BIM reviews",
        "text": "The workflow automates BIM coordination across teams.",
        "url": "",
        "category_hint": "automation",
        "source_name": "Perplexity",
    }

    assert generate._editorial_rejection_reason(article) == "missing_source_url"  # noqa: SLF001


def test_editorial_rejection_reason_rejects_digest_articles() -> None:
    """Digest or roundup blobs should be filtered before generation."""
    article = {
        "title": "PropTech Weekly Digest",
        "text": "A broad roundup of signal and noise across the market.",
        "url": "https://example.com/digest",
        "category_hint": "digest",
        "source_name": "Perplexity Deep Research",
    }

    assert (
        generate._editorial_rejection_reason(article)  # noqa: SLF001
        == "editorial_policy_digest_or_analysis"
    )


def test_editorial_rejection_reason_rejects_dry_permitting_story() -> None:
    """Digitized paperwork and permitting stories should not become Telegram drafts."""
    article = {
        "title": "Machine-readable planning framework speeds permit approvals",
        "text": (
            "The system helps with permit approvals, compliance checks, standards mapping, "
            "document workflows, and policy thresholds for planning teams."
        ),
        "url": "https://example.com/blog/permit-framework",
        "category_hint": "planning",
        "source_name": "Vendor blog",
    }

    assert (
        generate._editorial_rejection_reason(article)  # noqa: SLF001
        == "editorial_policy_boring_or_promotional"
    )


def test_editorial_rejection_reason_rejects_marketing_guide_story() -> None:
    """Vendor guide pages should be filtered out before generation."""
    article = {
        "title": "AI estimating software for contractors",
        "text": "The article explains benefits and best practices for estimating workflows.",
        "url": "https://example.com/blog/ai-estimating-software-the-ultimate-guide",
        "category_hint": "software",
        "source_name": "Vendor blog",
    }

    assert (
        generate._editorial_rejection_reason(article)  # noqa: SLF001
        == "editorial_policy_boring_or_promotional"
    )


def test_editorial_rejection_reason_keeps_high_interest_deployment_story() -> None:
    """Deployed hard-tech stories should survive the stricter editorial gate."""
    article = {
        "title": "Autonomous drywall robot deployed on active construction sites",
        "text": (
            "The robot is operating on production sites, automating repetitive interior finishing "
            "tasks with computer vision and field deployment feedback loops."
        ),
        "url": "https://example.com/robotics/deployment",
        "category_hint": "robotics",
        "source_name": "Industry publication",
    }

    assert generate._editorial_rejection_reason(article) is None  # noqa: SLF001
