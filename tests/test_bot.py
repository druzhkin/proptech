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


def test_required_env_vars_make_admin_optional() -> None:
    """The bot should require only bot token and channel id at startup."""
    assert bot._required_env_vars() == ["TG_BOT_TOKEN", "TG_CHANNEL_ID"]  # noqa: SLF001


def test_ensure_authorized_accepts_channel_admin_without_pinned_admin() -> None:
    """When TG_ADMIN_ID is absent, a real channel admin should still be authorized."""

    class FakeClient:
        def get_chat_member(self, chat_id: str, user_id: str) -> dict[str, str]:
            assert chat_id == "@proptech_channel"
            assert user_id == "42"
            return {"status": "administrator"}

    authorized_users: set[str] = set()
    is_allowed = bot._ensure_authorized(  # noqa: SLF001
        {"message": {"from": {"id": 42}}},
        client=FakeClient(),  # type: ignore[arg-type]
        admin_id=None,
        channel_id="@proptech_channel",
        authorized_users=authorized_users,
    )

    assert is_allowed is True
    assert "42" in authorized_users


def test_ensure_authorized_rejects_non_admin_without_pinned_admin() -> None:
    """A non-admin should not be able to control the review bot."""

    class FakeClient:
        def get_chat_member(self, chat_id: str, user_id: str) -> dict[str, str]:
            assert chat_id == "@proptech_channel"
            assert user_id == "51"
            return {"status": "member"}

    is_allowed = bot._ensure_authorized(  # noqa: SLF001
        {"message": {"from": {"id": 51}}},
        client=FakeClient(),  # type: ignore[arg-type]
        admin_id=None,
        channel_id="@proptech_channel",
        authorized_users=set(),
    )

    assert is_allowed is False


def test_send_draft_preview_handles_missing_batches_gracefully(monkeypatch) -> None:
    """No-drafts state should be shown as a user message, not as a raw exception."""

    class FakeClient:
        def __init__(self) -> None:
            self.messages: list[tuple[str | int, str]] = []

        def send_message(self, chat_id: str | int, text: str, *, reply_markup=None) -> dict[str, int]:
            self.messages.append((chat_id, text))
            return {"message_id": len(self.messages)}

    def fake_load_drafts(requested_date: str | None = None) -> tuple[str, list[dict[str, str]]]:
        del requested_date
        raise FileNotFoundError("No draft files found in data/drafts")

    monkeypatch.setattr(bot, "load_drafts", fake_load_drafts)
    client = FakeClient()

    bot.send_draft_preview(client, "777")  # type: ignore[arg-type]

    assert client.messages == [("777", bot.EMPTY_DRAFTS_MESSAGE)]


def test_send_status_handles_missing_batches_gracefully(monkeypatch) -> None:
    """Status command should explain that no draft batch exists yet."""

    class FakeClient:
        def __init__(self) -> None:
            self.messages: list[tuple[str | int, str]] = []

        def send_message(self, chat_id: str | int, text: str, *, reply_markup=None) -> dict[str, int]:
            self.messages.append((chat_id, text))
            return {"message_id": len(self.messages)}

    def fake_load_drafts(requested_date: str | None = None) -> tuple[str, list[dict[str, str]]]:
        del requested_date
        raise FileNotFoundError("No draft files found in data/drafts")

    monkeypatch.setattr(bot, "load_drafts", fake_load_drafts)
    client = FakeClient()

    bot.send_status(client, "777")  # type: ignore[arg-type]

    assert client.messages == [("777", bot.EMPTY_STATUS_MESSAGE)]


def test_handle_message_start_uses_updated_help_text() -> None:
    """Help should mention /next because it is part of the review flow now."""

    class FakeClient:
        def __init__(self) -> None:
            self.messages: list[tuple[str | int, str]] = []

        def send_message(self, chat_id: str | int, text: str, *, reply_markup=None) -> dict[str, int]:
            self.messages.append((chat_id, text))
            return {"message_id": len(self.messages)}

    client = FakeClient()

    bot.handle_message(
        client,  # type: ignore[arg-type]
        {"chat": {"id": 777}, "text": "/start"},
        channel_id="@proptech_channel",
        pending_edits={},
    )

    assert client.messages == [("777", bot.HELP_MESSAGE)]


def test_handle_message_accepts_next_alias(monkeypatch) -> None:
    """Admins should be able to use /next as an alias for /drafts."""
    preview_requests: list[tuple[str | int, str | None, str | None, str | None]] = []

    class FakeClient:
        def send_message(self, chat_id: str | int, text: str, *, reply_markup=None) -> dict[str, int]:
            raise AssertionError(f"Unexpected send_message call for {chat_id}: {text}")

    def fake_send_draft_preview(
        client,
        chat_id: str | int,
        *,
        drafts_date: str | None = None,
        draft_id: str | None = None,
        prefix_text: str | None = None,
    ) -> None:
        del client
        preview_requests.append((chat_id, drafts_date, draft_id, prefix_text))

    monkeypatch.setattr(bot, "send_draft_preview", fake_send_draft_preview)

    bot.handle_message(
        FakeClient(),  # type: ignore[arg-type]
        {"chat": {"id": 777}, "text": "/next"},
        channel_id="@proptech_channel",
        pending_edits={},
    )

    assert preview_requests == [("777", None, None, None)]
