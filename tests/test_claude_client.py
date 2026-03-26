from __future__ import annotations

from src import claude_client


def test_parse_json_payload_handles_fenced_code_block() -> None:
    """Model JSON parsing should tolerate markdown code fences."""
    payload = claude_client._parse_json_payload(  # noqa: SLF001
        """```json
        {"selected_ids":["a1","a2"]}
        ```"""
    )

    assert payload == {"selected_ids": ["a1", "a2"]}


def test_filter_articles_falls_back_to_input_order_when_selection_is_invalid(
    monkeypatch,
) -> None:
    """Invalid model selections should not empty the generation queue."""
    articles = [
        {"id": "a1", "title": "First", "text": "one"},
        {"id": "a2", "title": "Second", "text": "two"},
        {"id": "a3", "title": "Third", "text": "three"},
    ]
    monkeypatch.setattr(
        claude_client,
        "_call_claude_json",
        lambda *args, **kwargs: {"selected_ids": ["missing-id"]},
    )

    selected = claude_client.filter_articles("key", articles, max_items=2)

    assert [article["id"] for article in selected] == ["a1", "a2"]


def test_extract_openrouter_text_reads_openai_compatible_message_shape() -> None:
    """OpenRouter responses should be read from choices[0].message.content."""
    text = claude_client._extract_openrouter_text(  # noqa: SLF001
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"selected_ids":["a1"]}',
                    }
                }
            ]
        }
    )

    assert text == '{"selected_ids":["a1"]}'


def test_validate_post_reports_link_and_markdown_errors() -> None:
    """Post validation should catch missing source links and markdown."""
    errors = claude_client.validate_post(
        "🚀 **Headline** without source",
        "https://example.com/source",
    )

    assert "post is missing the source URL" in errors
    assert "post contains markdown formatting" in errors
