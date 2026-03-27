from __future__ import annotations

from src import perplexity_client


def test_parse_perplexity_response_splits_numbered_sections() -> None:
    """Structured Perplexity responses should become one article per section."""
    response_json = {
        "choices": [
            {
                "message": {
                    "content": (
                        "\n## 1. Alpha — expands [1]\n"
                        "Alpha details for the market.\n"
                        "## 2. Beta: launches [2]\n"
                        "Beta details for operators."
                    )
                }
            }
        ],
        "citations": [
            "https://example.com/alpha",
            "https://example.com/beta",
        ],
    }

    articles = perplexity_client.parse_perplexity_response(response_json)

    assert len(articles) == 2
    assert articles[0]["source_type"] == "perplexity"
    assert articles[0]["url"] == "https://example.com/alpha"
    assert articles[0]["source_name"] == "Alpha"
    assert articles[1]["url"] == "https://example.com/beta"


def test_parse_perplexity_response_rejects_limitation_meta_answer() -> None:
    """Perplexity limitation text should not be treated as a real article batch."""
    response_json = {
        "choices": [
            {
                "message": {
                    "content": (
                        "My knowledge cutoff is April 2024. "
                        "I cannot complete this request with current news."
                    )
                }
            }
        ],
        "citations": [],
    }

    assert perplexity_client.parse_perplexity_response(response_json) == []


def test_parse_perplexity_response_drops_unsplittable_digest_blob() -> None:
    """Malformed digest blobs should be dropped instead of becoming fake articles."""
    response_json = {
        "choices": [
            {
                "message": {
                    "content": (
                        "PropTech Weekly Digest\n\n"
                        "Most recent stories this week are partnerships, fundraising, and broad commentary."
                    )
                }
            }
        ],
        "citations": [],
    }

    assert perplexity_client.parse_perplexity_response(response_json) == []
