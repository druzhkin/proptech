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


def test_validate_post_rejects_first_person_voice() -> None:
    """Posts should not be written from the author's first-person perspective."""
    errors = claude_client.validate_post(
        "\u041c\u044b \u0432\u0438\u0434\u0438\u043c, \u043a\u0430\u043a BIM-\u0438\u043d\u0441\u0442\u0440\u0443\u043c\u0435\u043d\u0442 \u0443\u0441\u043a\u043e\u0440\u044f\u0435\u0442 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443. https://example.com/source",
        "https://example.com/source",
    )

    assert "post contains first-person voice" in errors
