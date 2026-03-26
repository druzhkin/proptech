from __future__ import annotations

import json

from src import bot


def test_build_short_id_map_expands_on_collision() -> None:
    """Short IDs must grow beyond 8 chars when prefixes collide."""
    records = [
        {"id": "12345678-aaaa-bbbb-cccc-000000000001"},
        {"id": "12345678-aaaa-bbbb-cccc-000000000002"},
    ]

    short_ids = bot.build_short_id_map(records)

    assert short_ids[records[0]["id"]] != short_ids[records[1]["id"]]
    assert len(short_ids[records[0]["id"]]) > 8


def test_find_draft_by_short_id_raises_for_ambiguous_prefix() -> None:
    """Ambiguous short IDs must not silently resolve to the wrong draft."""
    records = [
        {"id": "draft-alpha-001"},
        {"id": "draft-alpha-002"},
    ]

    try:
        bot.find_draft_by_short_id(records, "draft-alpha-0")
    except ValueError as exc:
        assert "ambiguous" in str(exc)
    else:
        raise AssertionError("Expected ambiguous short ID to raise ValueError")


def test_compute_status_counts_tracks_review_outcomes() -> None:
    """Status summary should separate pending, skipped, rejected, and published drafts."""
    counts = bot.compute_status_counts(
        [
            {"status": "draft"},
            {"status": "published"},
            {"status": "skipped"},
            {"status": "rejected"},
            {"status": "draft"},
        ]
    )

    assert counts == {
        "pending": 2,
        "published": 1,
        "skipped": 1,
        "rejected": 1,
    }


def test_record_publication_updates_drafts_and_published_files(tmp_path, monkeypatch) -> None:
    """Publishing should update the draft record and append a published record."""
    drafts_dir = tmp_path / "drafts"
    published_dir = tmp_path / "published"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    published_dir.mkdir(parents=True, exist_ok=True)
    (drafts_dir / "2026-03-26.json").write_text(
        json.dumps(
            [
                {
                    "id": "draft-1",
                    "article_id": "article-1",
                    "title": "Draft title",
                    "text": "Useful Telegram draft",
                    "status": "draft",
                }
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(bot, "DRAFTS_DIR", drafts_dir)
    monkeypatch.setattr(bot, "PUBLISHED_DIR", published_dir)

    updated_record, published_path = bot.record_publication(
        "2026-03-26",
        "draft-1",
        channel_id="@proptech_channel",
        telegram_message_id=321,
    )

    saved_drafts = json.loads((drafts_dir / "2026-03-26.json").read_text(encoding="utf-8"))
    saved_published = json.loads((published_dir / "2026-03-26.json").read_text(encoding="utf-8"))

    assert updated_record["status"] == "published"
    assert updated_record["telegram_message_id"] == 321
    assert published_path.endswith("2026-03-26.json")
    assert saved_drafts[0]["status"] == "published"
    assert saved_published[0]["telegram_message_id"] == 321


def test_publish_draft_falls_back_to_text_when_photo_send_fails() -> None:
    """If photo upload fails, bot should notify admin and publish text-only."""

    class FakeClient:
        def __init__(self) -> None:
            self.messages: list[tuple[str | int, str]] = []

        def send_photo(self, chat_id: str | int, photo: str, *, caption: str = "") -> dict[str, int]:
            raise RuntimeError(f"photo failed for {chat_id}: {photo} {caption}")

        def send_message(self, chat_id: str | int, text: str, *, reply_markup=None) -> dict[str, int]:
            self.messages.append((chat_id, text))
            return {"message_id": len(self.messages)}

    client = FakeClient()

    result = bot.publish_draft(
        client,  # type: ignore[arg-type]
        {
            "id": "draft-1",
            "text": "Final text for channel",
            "image_url": "https://example.com/image.jpg",
        },
        channel_id="@proptech_channel",
        admin_chat_id="777",
    )

    assert result["telegram_message_id"] == 2
    assert client.messages[0][0] == "777"
    assert "без изображения" in client.messages[0][1]
    assert client.messages[1] == ("@proptech_channel", "Final text for channel")
