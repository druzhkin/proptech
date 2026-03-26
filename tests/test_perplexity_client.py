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
