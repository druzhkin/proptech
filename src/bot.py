#!/usr/bin/env python3
"""Telegram review bot for draft moderation and publishing."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from collections.abc import Callable, MutableMapping, Sequence
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / "config" / ".env"
DRAFTS_DIR = PROJECT_ROOT / "data" / "drafts"
PUBLISHED_DIR = PROJECT_ROOT / "data" / "published"

PendingEdits = MutableMapping[str, dict[str, str]]
AuthorizedUsers = set[str]
AUTHORIZED_CHANNEL_STATUSES = {"administrator", "creator"}
EMPTY_DRAFTS_MESSAGE = (
    "\u0427\u0435\u0440\u043d\u043e\u0432\u0438\u043a\u043e\u0432 \u043f\u043e\u043a\u0430 "
    "\u043d\u0435\u0442. \u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u043d\u0443\u0436\u043d\u043e "
    "\u0441\u043e\u0431\u0440\u0430\u0442\u044c \u0441\u0442\u0430\u0442\u044c\u0438 \u0438 "
    "\u0441\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c draft batch."
)
EMPTY_STATUS_MESSAGE = (
    "\u0421\u0442\u0430\u0442\u0443\u0441 \u043f\u043e\u043a\u0430 \u043d\u0435\u0434\u043e\u0441\u0442"
    "\u0443\u043f\u0435\u043d: \u0432 data/drafts \u0435\u0449\u0451 \u043d\u0435\u0442 \u043d\u0438 "
    "\u043e\u0434\u043d\u043e\u0433\u043e batch-\u0444\u0430\u0439\u043b\u0430."
)
HELP_MESSAGE = (
    "\u041a\u043e\u043c\u0430\u043d\u0434\u044b: /drafts, /next, /status, /cancel. "
    "\u041a\u043d\u043e\u043f\u043a\u0438 Publish/Edit/Skip \u0440\u0430\u0431\u043e\u0442\u0430"
    "\u044e\u0442 \u043f\u043e\u0434 \u043a\u0430\u0436\u0434\u044b\u043c draft preview."
)
UNKNOWN_COMMAND_MESSAGE = (
    "\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u0430\u044f \u043a\u043e\u043c\u0430\u043d"
    "\u0434\u0430. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 /drafts, /next, "
    "/status \u0438\u043b\u0438 /cancel."
)


class ExitCode(IntEnum):
    """CLI exit codes for the Telegram bot."""

    SUCCESS = 0
    PARTIAL_FAILURE = 1
    FAILURE = 2


class TelegramAPIError(RuntimeError):
    """Raised when Telegram returns an API-level error."""


def _load_logging_setup() -> Callable[[Path], Path]:
    """Import the shared logging bootstrap for package and script execution."""
    if __package__ in (None, ""):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.logging_utils import setup_logging
    else:
        from .logging_utils import setup_logging

    return setup_logging


def _load_scheduler_starter() -> Callable[[], Any]:
    """Import the optional pipeline scheduler bootstrap safely."""
    if __package__ in (None, ""):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.pipeline_scheduler import start_scheduler_from_env
    else:
        from .pipeline_scheduler import start_scheduler_from_env

    return start_scheduler_from_env


def _resolve_drafts_file(requested_date: str | None = None) -> Path:
    """Resolve the draft JSON file to use for review."""
    if requested_date:
        file_path = DRAFTS_DIR / f"{requested_date}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"Drafts file not found for date {requested_date}")
        return file_path

    today_path = DRAFTS_DIR / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    if today_path.exists():
        return today_path

    available_files = sorted(DRAFTS_DIR.glob("*.json"))
    if not available_files:
        raise FileNotFoundError("No draft files found in data/drafts")
    return available_files[-1]


def load_drafts(requested_date: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    """Load draft records and return the source date plus normalized records."""
    file_path = _resolve_drafts_file(requested_date)
    with file_path.open("r", encoding="utf-8") as file_obj:
        loaded = json.load(file_obj)

    if not isinstance(loaded, list):
        raise ValueError("Drafts file must contain a list")

    normalized_records = [record for record in loaded if isinstance(record, dict)]
    return file_path.stem, normalized_records


def save_drafts(drafts_date: str, records: list[dict[str, Any]]) -> str:
    """Persist draft records for a specific date."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = DRAFTS_DIR / f"{drafts_date}.json"
    with file_path.open("w", encoding="utf-8") as file_obj:
        json.dump(records, file_obj, indent=2, ensure_ascii=False)
    return str(file_path)


def load_published_records(drafts_date: str) -> list[dict[str, Any]]:
    """Load published records for a specific date if the file exists."""
    file_path = PUBLISHED_DIR / f"{drafts_date}.json"
    if not file_path.exists():
        return []

    with file_path.open("r", encoding="utf-8") as file_obj:
        loaded = json.load(file_obj)
    if not isinstance(loaded, list):
        raise ValueError("Published file must contain a list")

    return [record for record in loaded if isinstance(record, dict)]


def append_published_record(drafts_date: str, record: dict[str, Any]) -> str:
    """Append a published record to the date-partitioned JSON file."""
    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    file_path = PUBLISHED_DIR / f"{drafts_date}.json"
    records = load_published_records(drafts_date)
    records.append(record)

    with file_path.open("w", encoding="utf-8") as file_obj:
        json.dump(records, file_obj, indent=2, ensure_ascii=False)

    return str(file_path)


def list_pending_drafts(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return drafts that still require admin review."""
    return [
        record
        for record in records
        if str(record.get("status", "")).strip() == "draft"
    ]


def build_short_id_map(
    records: Sequence[dict[str, Any]],
    *,
    min_length: int = 8,
) -> dict[str, str]:
    """Build unique short IDs without assuming that 8 characters never collide."""
    record_ids = [
        str(record.get("id", "")).strip()
        for record in records
        if str(record.get("id", "")).strip()
    ]
    if not record_ids:
        return {}

    lengths = {
        record_id: min(min_length, len(record_id))
        for record_id in record_ids
    }

    while True:
        groups: dict[str, list[str]] = {}
        for record_id in record_ids:
            prefix = record_id[: lengths[record_id]]
            groups.setdefault(prefix, []).append(record_id)

        collisions = [group for group in groups.values() if len(group) > 1]
        if not collisions:
            return {
                record_id: record_id[: lengths[record_id]]
                for record_id in record_ids
            }

        progressed = False
        for group in collisions:
            for record_id in group:
                if lengths[record_id] < len(record_id):
                    lengths[record_id] += 1
                    progressed = True

        if not progressed:
            return {record_id: record_id for record_id in record_ids}


def find_draft_by_short_id(
    records: Sequence[dict[str, Any]],
    short_id: str,
) -> dict[str, Any]:
    """Find a draft by full ID or by a unique short-ID prefix."""
    normalized_id = short_id.strip()
    if not normalized_id:
        raise LookupError("Draft ID cannot be empty")

    matches = [
        record
        for record in records
        if str(record.get("id", "")).strip().startswith(normalized_id)
    ]
    if not matches:
        raise LookupError(f"Draft not found: {normalized_id}")
    if len(matches) > 1:
        raise ValueError(f"Draft ID is ambiguous: {normalized_id}")
    return matches[0]


def _word_count(text: str) -> int:
    """Count words in a draft text."""
    return len(text.split())


def _has_photo(draft: dict[str, Any]) -> bool:
    """Check whether a draft has an image URL."""
    return bool(str(draft.get("image_url") or "").strip())


def compute_status_counts(records: Sequence[dict[str, Any]]) -> dict[str, int]:
    """Compute review counters for the latest draft batch."""
    counts = {
        "pending": 0,
        "published": 0,
        "skipped": 0,
        "rejected": 0,
    }
    for record in records:
        status = str(record.get("status", "")).strip()
        if status == "draft":
            counts["pending"] += 1
        elif status == "published":
            counts["published"] += 1
        elif status == "skipped":
            counts["skipped"] += 1
        elif status == "rejected":
            counts["rejected"] += 1
    return counts


def format_status_message(drafts_date: str, records: Sequence[dict[str, Any]]) -> str:
    """Build the `/status` response for the admin."""
    counts = compute_status_counts(records)
    return (
        f"Статус draft batch за {drafts_date}\n"
        f"Ожидают ревью: {counts['pending']}\n"
        f"Опубликовано: {counts['published']}\n"
        f"Пропущено: {counts['skipped']}\n"
        f"Отклонено до ревью: {counts['rejected']}"
    )


def format_draft_message(
    draft: dict[str, Any],
    *,
    short_id: str,
) -> str:
    """Render a review-friendly draft preview for Telegram."""
    text = str(draft.get("text", "")).strip()
    photo_label = "да" if _has_photo(draft) else "нет"
    return (
        f"Draft {short_id}\n"
        f"Источник: {draft.get('source_name', 'unknown')}\n"
        f"Категория: {draft.get('category', 'unknown')}\n"
        f"Слов: {_word_count(text)}\n"
        f"Фото: {photo_label}\n"
        f"Заголовок: {draft.get('title', '')}\n"
        f"URL: {draft.get('url', '')}\n\n"
        f"{text}"
    )


def build_review_keyboard(drafts_date: str, draft_id: str) -> dict[str, list[list[dict[str, str]]]]:
    """Build inline review controls for a specific draft."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Publish",
                    "callback_data": f"publish|{drafts_date}|{draft_id}",
                },
                {
                    "text": "✏️ Edit",
                    "callback_data": f"edit|{drafts_date}|{draft_id}",
                },
                {
                    "text": "❌ Skip",
                    "callback_data": f"skip|{drafts_date}|{draft_id}",
                },
            ]
        ]
    }


def update_draft_record(
    drafts_date: str,
    draft_id: str,
    updater: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """Apply an in-place mutation to a single draft record and persist the file."""
    actual_date, records = load_drafts(drafts_date)
    updated_record: dict[str, Any] | None = None

    for record in records:
        if str(record.get("id", "")).strip() != draft_id:
            continue
        updater(record)
        updated_record = record
        break

    if updated_record is None:
        raise LookupError(f"Draft not found: {draft_id}")

    save_drafts(actual_date, records)
    return updated_record


def apply_admin_edit(drafts_date: str, draft_id: str, new_text: str) -> dict[str, Any]:
    """Persist an admin-edited draft text."""
    cleaned_text = new_text.strip()
    if not cleaned_text:
        raise ValueError("Edited draft text cannot be empty")

    def _update(record: dict[str, Any]) -> None:
        record["text"] = cleaned_text
        record["edited_at"] = datetime.now(timezone.utc).isoformat()
        record["edited_by_admin"] = True
        record["validation_errors"] = []

    return update_draft_record(drafts_date, draft_id, _update)


def mark_draft_skipped(drafts_date: str, draft_id: str) -> dict[str, Any]:
    """Persist a skip action from the admin."""

    def _update(record: dict[str, Any]) -> None:
        record["status"] = "skipped"
        record["rejection_reason"] = "skipped_by_admin"
        record["skipped_at"] = datetime.now(timezone.utc).isoformat()

    return update_draft_record(drafts_date, draft_id, _update)


def build_published_record(
    draft: dict[str, Any],
    *,
    channel_id: str,
    telegram_message_id: int,
    telegram_photo_message_id: int | None = None,
) -> dict[str, Any]:
    """Build the serialized published record stored on disk."""
    published_record = dict(draft)
    published_record["status"] = "published"
    published_record["channel_id"] = channel_id
    published_record["telegram_message_id"] = telegram_message_id
    published_record["published_at"] = datetime.now(timezone.utc).isoformat()
    if telegram_photo_message_id is not None:
        published_record["telegram_photo_message_id"] = telegram_photo_message_id
    return published_record


def record_publication(
    drafts_date: str,
    draft_id: str,
    *,
    channel_id: str,
    telegram_message_id: int,
    telegram_photo_message_id: int | None = None,
) -> tuple[dict[str, Any], str]:
    """Persist both the updated draft record and the published output file."""
    updated_record = update_draft_record(
        drafts_date,
        draft_id,
        lambda record: record.update(
            {
                "status": "published",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "telegram_message_id": telegram_message_id,
                **(
                    {"telegram_photo_message_id": telegram_photo_message_id}
                    if telegram_photo_message_id is not None
                    else {}
                ),
            }
        ),
    )
    published_path = append_published_record(
        drafts_date,
        build_published_record(
            updated_record,
            channel_id=channel_id,
            telegram_message_id=telegram_message_id,
            telegram_photo_message_id=telegram_photo_message_id,
        ),
    )
    return updated_record, published_path


class TelegramClient:
    """Minimal Telegram Bot API wrapper using the existing requests dependency."""

    def __init__(
        self,
        token: str,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self._session = session or requests.Session()
        self._base_url = f"https://api.telegram.org/bot{token}"

    def _request(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        response = self._session.post(
            f"{self._base_url}/{method}",
            data=payload,
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise TelegramAPIError("Telegram returned a non-object response")
        if not body.get("ok"):
            raise TelegramAPIError(str(body.get("description", "Unknown Telegram API error")))
        return body.get("result")

    def get_updates(self, *, offset: int | None = None, timeout: int = 20) -> list[dict[str, Any]]:
        """Long-poll Telegram for new updates."""
        payload: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        result = self._request("getUpdates", payload)
        return result if isinstance(result, list) else []

    def get_chat_member(self, chat_id: str | int, user_id: str | int) -> dict[str, Any]:
        """Fetch a member record for a Telegram chat."""
        payload = {
            "chat_id": str(chat_id),
            "user_id": str(user_id),
        }
        result = self._request("getChatMember", payload)
        return result if isinstance(result, dict) else {}

    def send_message(
        self,
        chat_id: str | int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a text message."""
        payload: dict[str, Any] = {
            "chat_id": str(chat_id),
            "text": text,
        }
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        result = self._request("sendMessage", payload)
        return result if isinstance(result, dict) else {}

    def send_photo(
        self,
        chat_id: str | int,
        photo: str,
        *,
        caption: str = "",
    ) -> dict[str, Any]:
        """Send a photo by URL with an optional caption."""
        payload: dict[str, Any] = {
            "chat_id": str(chat_id),
            "photo": photo,
        }
        if caption:
            payload["caption"] = caption
        result = self._request("sendPhoto", payload)
        return result if isinstance(result, dict) else {}

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        """Stop the Telegram client-side loading spinner for a callback."""
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        self._request("answerCallbackQuery", payload)

    def edit_message_reply_markup(self, chat_id: str | int, message_id: int) -> None:
        """Remove inline review buttons from an already processed message."""
        payload = {
            "chat_id": str(chat_id),
            "message_id": message_id,
            "reply_markup": json.dumps({"inline_keyboard": []}),
        }
        self._request("editMessageReplyMarkup", payload)


def publish_draft(
    client: TelegramClient,
    draft: dict[str, Any],
    *,
    channel_id: str,
    admin_chat_id: str | int,
) -> dict[str, int]:
    """Publish a reviewed draft to the target Telegram channel."""
    text = str(draft.get("text", "")).strip()
    if not text:
        raise ValueError("Draft text is empty and cannot be published")

    image_url = str(draft.get("image_url") or "").strip()
    if image_url:
        try:
            if len(text) <= 1024:
                response = client.send_photo(channel_id, image_url, caption=text)
                return {"telegram_message_id": int(response["message_id"])}

            photo_response = client.send_photo(channel_id, image_url)
            text_response = client.send_message(channel_id, text)
            return {
                "telegram_message_id": int(text_response["message_id"]),
                "telegram_photo_message_id": int(photo_response["message_id"]),
            }
        except Exception:
            logger.exception(
                "Photo publish failed for draft %s. Falling back to text-only publish.",
                draft.get("id", "unknown"),
            )
            _safe_notify_admin(
                client,
                admin_chat_id,
                "Не удалось отправить фото в канал, публикую текстом без изображения.",
            )

    response = client.send_message(channel_id, text)
    return {"telegram_message_id": int(response["message_id"])}


def _parse_callback_data(data: str) -> tuple[str, str, str]:
    """Parse callback payloads of the form `action|date|draft_id`."""
    action, drafts_date, draft_id = data.split("|", 2)
    return action, drafts_date, draft_id


def _message_chat_id(message: dict[str, Any]) -> str | None:
    """Extract a chat ID from a Telegram message object."""
    chat = message.get("chat")
    if not isinstance(chat, dict):
        return None
    chat_id = chat.get("id")
    return str(chat_id) if chat_id is not None else None


def _update_user_id(update: dict[str, Any]) -> str | None:
    """Extract a Telegram user ID from either a message or callback update."""
    if isinstance(update.get("message"), dict):
        user = update["message"].get("from")
        if isinstance(user, dict) and user.get("id") is not None:
            return str(user["id"])

    if isinstance(update.get("callback_query"), dict):
        user = update["callback_query"].get("from")
        if isinstance(user, dict) and user.get("id") is not None:
            return str(user["id"])

    return None


def _update_chat_id(update: dict[str, Any]) -> str | None:
    """Extract a Telegram chat ID from either a message or callback update."""
    if isinstance(update.get("message"), dict):
        return _message_chat_id(update["message"])

    callback_query = update.get("callback_query")
    if isinstance(callback_query, dict):
        message = callback_query.get("message")
        if isinstance(message, dict):
            return _message_chat_id(message)

    return None


def _safe_notify_admin(client: TelegramClient, admin_chat_id: str | int, text: str) -> None:
    """Attempt to send an error/info message to the admin without crashing."""
    try:
        client.send_message(admin_chat_id, text)
    except Exception:
        logger.exception("Failed to notify admin chat %s", admin_chat_id)


def _is_channel_admin(
    client: TelegramClient,
    *,
    channel_id: str,
    user_id: str,
) -> bool:
    """Return whether a Telegram user is an admin of the configured channel."""
    try:
        member = client.get_chat_member(channel_id, user_id)
    except Exception:
        logger.exception("Failed to resolve Telegram channel membership for user %s", user_id)
        return False

    status = str(member.get("status", "")).strip().lower()
    return status in AUTHORIZED_CHANNEL_STATUSES


def _ensure_authorized(
    update: dict[str, Any],
    *,
    client: TelegramClient,
    admin_id: str | None,
    channel_id: str,
    authorized_users: AuthorizedUsers,
) -> bool:
    """Return whether the update belongs to the configured or inferred admin."""
    user_id = _update_user_id(update)
    if not user_id:
        logger.warning("Ignoring update without a resolvable user id")
        return False

    if admin_id:
        if user_id == admin_id:
            authorized_users.add(user_id)
            return True

        logger.warning("Ignoring update from unauthorized user %s", user_id)
        return False

    if user_id in authorized_users:
        return True

    if _is_channel_admin(client, channel_id=channel_id, user_id=user_id):
        authorized_users.add(user_id)
        logger.info("Authorized Telegram user %s via channel admin lookup", user_id)
        return True

    logger.warning("Ignoring update from unauthorized user %s", user_id or "unknown")
    return False


def send_draft_preview(
    client: TelegramClient,
    chat_id: str | int,
    *,
    drafts_date: str | None = None,
    draft_id: str | None = None,
    prefix_text: str | None = None,
) -> None:
    """Send the next pending draft or a specific draft preview to the admin."""
    try:
        actual_date, records = load_drafts(drafts_date)
    except FileNotFoundError:
        empty_message = EMPTY_DRAFTS_MESSAGE
        if prefix_text:
            empty_message = f"{prefix_text}\n\n{empty_message}"
        client.send_message(chat_id, empty_message)
        return

    short_ids = build_short_id_map(records)

    if draft_id:
        draft = find_draft_by_short_id(records, draft_id)
    else:
        pending = list_pending_drafts(records)
        if not pending:
            empty_message = f"Черновиков для ревью не осталось за {actual_date}."
            if prefix_text:
                empty_message = f"{prefix_text}\n\n{empty_message}"
            client.send_message(chat_id, empty_message)
            return
        draft = pending[0]

    full_id = str(draft.get("id", "")).strip()
    body = format_draft_message(
        draft,
        short_id=short_ids.get(full_id, full_id),
    )
    if prefix_text:
        body = f"{prefix_text}\n\n{body}"

    client.send_message(
        chat_id,
        body,
        reply_markup=build_review_keyboard(actual_date, full_id),
    )


def send_status(client: TelegramClient, chat_id: str | int, *, drafts_date: str | None = None) -> None:
    """Send batch status counters to the admin."""
    try:
        actual_date, records = load_drafts(drafts_date)
    except FileNotFoundError:
        client.send_message(chat_id, EMPTY_STATUS_MESSAGE)
        return

    client.send_message(chat_id, format_status_message(actual_date, records))


def handle_callback_query(
    client: TelegramClient,
    callback_query: dict[str, Any],
    *,
    channel_id: str,
    pending_edits: PendingEdits,
) -> None:
    """Handle inline Publish/Edit/Skip actions from the admin."""
    callback_query_id = str(callback_query.get("id", ""))
    data = str(callback_query.get("data", ""))
    message = callback_query.get("message")
    if not callback_query_id or not data or not isinstance(message, dict):
        raise ValueError("Malformed callback query payload")

    chat_id = _message_chat_id(message)
    message_id = message.get("message_id")
    if chat_id is None or not isinstance(message_id, int):
        raise ValueError("Callback query is missing message context")

    action, drafts_date, draft_id = _parse_callback_data(data)
    _, records = load_drafts(drafts_date)
    try:
        draft = find_draft_by_short_id(records, draft_id)
    except LookupError as exc:
        logger.warning("Draft lookup failed: %s", exc)
        client.answer_callback_query(callback_query_id, "Черновик не найден или устарёл.")
        try:
            client.edit_message_reply_markup(chat_id, message_id)
        except Exception:
            logger.exception("Failed to clear stale callback keyboard")
        return

    short_ids = build_short_id_map(records)
    full_id = str(draft.get("id", "")).strip()
    short_id = short_ids.get(full_id, full_id)

    if str(draft.get("status", "")).strip() != "draft":
        client.answer_callback_query(callback_query_id, "Черновик уже обработан.")
        try:
            client.edit_message_reply_markup(chat_id, message_id)
        except Exception:
            logger.exception("Failed to clear stale callback keyboard for draft %s", full_id)
        return

    if action == "publish":
        publish_result = publish_draft(
            client,
            draft,
            channel_id=channel_id,
            admin_chat_id=chat_id,
        )
        _, published_path = record_publication(
            drafts_date,
            full_id,
            channel_id=channel_id,
            telegram_message_id=publish_result["telegram_message_id"],
            telegram_photo_message_id=publish_result.get("telegram_photo_message_id"),
        )
        client.answer_callback_query(callback_query_id, "Опубликовано")
        try:
            client.edit_message_reply_markup(chat_id, message_id)
        except Exception:
            logger.exception("Failed to clear callback keyboard after publish for %s", full_id)
        send_draft_preview(
            client,
            chat_id,
            drafts_date=drafts_date,
            prefix_text=f"Опубликовано: {short_id}\nPublished log: {published_path}",
        )
        return

    if action == "skip":
        mark_draft_skipped(drafts_date, full_id)
        client.answer_callback_query(callback_query_id, "Пропущено")
        try:
            client.edit_message_reply_markup(chat_id, message_id)
        except Exception:
            logger.exception("Failed to clear callback keyboard after skip for %s", full_id)
        send_draft_preview(
            client,
            chat_id,
            drafts_date=drafts_date,
            prefix_text=f"Пропущено: {short_id}",
        )
        return

    if action == "edit":
        pending_edits[str(chat_id)] = {
            "drafts_date": drafts_date,
            "draft_id": full_id,
        }
        client.answer_callback_query(callback_query_id, "Жду новый текст")
        client.send_message(
            chat_id,
            f"Пришлите новую версию текста для draft {short_id}. Команда /cancel отменяет edit mode.",
        )
        return

    raise ValueError(f"Unsupported callback action: {action}")


def handle_message(
    client: TelegramClient,
    message: dict[str, Any],
    *,
    channel_id: str,
    pending_edits: PendingEdits,
) -> None:
    """Handle text commands and admin edit submissions."""
    chat_id = _message_chat_id(message)
    if chat_id is None:
        raise ValueError("Message is missing chat context")

    text = str(message.get("text", "")).strip()
    if not text:
        client.send_message(chat_id, "Поддерживаются только текстовые команды и текст правок.")
        return

    pending_edit = pending_edits.get(chat_id)
    if pending_edit and not text.startswith("/"):
        updated = apply_admin_edit(
            pending_edit["drafts_date"],
            pending_edit["draft_id"],
            text,
        )
        pending_edits.pop(chat_id, None)
        send_draft_preview(
            client,
            chat_id,
            drafts_date=pending_edit["drafts_date"],
            draft_id=str(updated.get("id", "")),
            prefix_text="Текст обновлён. Проверьте финальную версию перед публикацией.",
        )
        return

    if text == "/start":
        client.send_message(chat_id, HELP_MESSAGE)
        return

    if text in {"/drafts", "/next"}:
        send_draft_preview(client, chat_id)
        return

    if text == "/status":
        send_status(client, chat_id)
        return

    if text == "/cancel":
        if pending_edit:
            pending_edits.pop(chat_id, None)
            client.send_message(chat_id, "Edit mode отменён.")
        else:
            client.send_message(chat_id, "Активного edit mode нет.")
        return

    client.send_message(
        chat_id,
        "Неизвестная команда. Используйте /drafts, /status или /cancel.",
    )


def handle_update(
    client: TelegramClient,
    update: dict[str, Any],
    *,
    admin_id: str | None,
    channel_id: str,
    pending_edits: PendingEdits,
    authorized_users: AuthorizedUsers,
) -> None:
    """Dispatch a Telegram update to the correct handler."""
    if not _ensure_authorized(
        update,
        client=client,
        admin_id=admin_id,
        channel_id=channel_id,
        authorized_users=authorized_users,
    ):
        callback_query = update.get("callback_query")
        if isinstance(callback_query, dict) and callback_query.get("id"):
            try:
                client.answer_callback_query(str(callback_query["id"]), "Unauthorized")
            except Exception:
                logger.exception("Failed to answer unauthorized callback query")
        return

    callback_query = update.get("callback_query")
    if isinstance(callback_query, dict):
        try:
            handle_callback_query(
                client,
                callback_query,
                channel_id=channel_id,
                pending_edits=pending_edits,
            )
        except Exception:
            logger.exception("Unhandled error in callback query handler")
            if callback_query.get("id"):
                try:
                    client.answer_callback_query(
                        str(callback_query["id"]),
                        "Ошибка обработки действия. Попробуйте /drafts.",
                    )
                except Exception:
                    logger.exception("Failed to notify admin about callback error")
        return

    message = update.get("message")
    if isinstance(message, dict):
        handle_message(
            client,
            message,
            channel_id=channel_id,
            pending_edits=pending_edits,
        )
        return

    logger.info("Ignoring unsupported Telegram update shape")


def _required_env_vars() -> list[str]:
    """Return env vars required to run the Telegram bot safely."""
    return ["TG_BOT_TOKEN", "TG_CHANNEL_ID"]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the admin-only Telegram review bot."""
    parser = argparse.ArgumentParser(description="PropTech Telegram review bot")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one polling cycle and exit",
    )
    args = parser.parse_args(argv)

    setup_logging = _load_logging_setup()
    log_path = setup_logging(PROJECT_ROOT)
    load_dotenv(ENV_PATH)
    logger.info("Logging to %s", log_path)

    missing_env_vars = [name for name in _required_env_vars() if not os.getenv(name)]
    if missing_env_vars:
        logger.error(
            "Missing required environment variables: %s",
            ", ".join(missing_env_vars),
        )
        return ExitCode.FAILURE

    bot_token = os.getenv("TG_BOT_TOKEN", "")
    channel_id = str(os.getenv("TG_CHANNEL_ID", "")).strip()
    admin_id = str(os.getenv("TG_ADMIN_ID", "")).strip() or None

    client = TelegramClient(bot_token)
    pending_edits: PendingEdits = {}
    authorized_users: AuthorizedUsers = {admin_id} if admin_id else set()
    offset: int | None = None

    if admin_id:
        logger.info("Bot started for pinned admin %s", admin_id)
    else:
        logger.info(
            "Bot started without TG_ADMIN_ID; channel administrator lookup auth is enabled"
        )

    scheduler = None
    if not args.once:
        try:
            start_scheduler_from_env = _load_scheduler_starter()
            scheduler = start_scheduler_from_env()
        except ValueError as exc:
            logger.error("Invalid pipeline scheduler configuration: %s", exc)
            return ExitCode.FAILURE

    stopped = False

    def _signal_handler(signum: int, _frame: Any) -> None:
        nonlocal stopped
        logger.info("Received signal %d, shutting down gracefully...", signum)
        stopped = True
        if scheduler is not None:
            scheduler.stop()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    while not stopped:
        try:
            updates = client.get_updates(offset=offset, timeout=20)
        except Exception:
            logger.exception("Telegram polling failed")
            if args.once:
                return ExitCode.FAILURE
            time.sleep(3)
            continue

        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                offset = update_id + 1

            try:
                handle_update(
                    client,
                    update,
                    admin_id=admin_id,
                    channel_id=channel_id,
                    pending_edits=pending_edits,
                    authorized_users=authorized_users,
                )
            except Exception as exc:
                logger.exception("Failed to handle update %s", update_id)
                chat_id = _update_chat_id(update)
                if chat_id is not None:
                    _safe_notify_admin(
                        client,
                        chat_id,
                        f"Ошибка обработки update: {exc}",
                    )

        if args.once:
            return ExitCode.SUCCESS

    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
