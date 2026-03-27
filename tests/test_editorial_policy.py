from __future__ import annotations

from src import editorial_policy


def test_describe_editorial_fit_scores_open_source_ai_stack() -> None:
    """Self-hosted AI tooling with GitHub cues should rank as a strong CIO-fit."""
    article = {
        "title": "GitHub release packages Docling, Qdrant, and Ollama into a self-hosted document AI stack",
        "text": (
            "The repo combines OCR, semantic search, and local models for contract review "
            "and policy lookup. Platform teams can deploy it with Docker and expose it to "
            "finance, sales, and construction staff as an internal copilot."
        ),
        "category_hint": "automation",
        "source_name": "GitHub",
        "url": "https://github.com/example/self-hosted-doc-ai",
    }

    fit = editorial_policy.describe_editorial_fit(article)

    assert fit["score"] >= 8
    assert "ai_knowledge_ops" in fit["track_ids"]
    assert "open_source_tooling" in fit["track_ids"]
    assert "it_platform" in fit["business_function_ids"]
    assert "knowledge_ops" in fit["business_function_ids"]


def test_describe_editorial_fit_stays_low_for_generic_corporate_update() -> None:
    """Generic company updates without a practical tool angle should stay off-radar."""
    article = {
        "title": "Vendor expands strategic partnership with regional developer",
        "text": (
            "The companies plan to collaborate on future digital transformation initiatives "
            "across several markets. Public technical detail and deployment specifics were not shared."
        ),
        "category_hint": "partnership",
        "source_name": "Corporate newsroom",
        "url": "https://example.com/partnership",
    }

    fit = editorial_policy.describe_editorial_fit(article)

    assert fit["score"] <= 2
    assert fit["track_ids"] == []
