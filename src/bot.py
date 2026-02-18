#!/usr/bin/env python3
"""
Telegram bot for PropTech Russia channel.

Review drafts, edit, and publish to @proptech_russia.
Long-polling mode. Only responds to ADMIN_ID.

Usage:
    python src/bot.py
"""

import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / "config" / ".env")

BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
CHANNEL_ID = os.getenv("TG_CHANNEL_ID", "")
ADMIN_ID = int(os.getenv("TG_ADMIN_ID", "0"))

DRAFTS_DIR = PROJECT_ROOT / "data" / "drafts"
PUBLISHED_DIR = PROJECT_ROOT / "data" / "published"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────


def is_admin(update: Update) -> bool:
    """Check if message is from the admin."""
    user = update.effective_user
    return user is not None and user.id == ADMIN_ID


def load_json(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_drafts_file() -> Path | None:
    """Find today's drafts file, or the latest available."""
    today_file = DRAFTS_DIR / f"{date.today().isoformat()}.json"
    if today_file.exists():
        return today_file
    files = sorted(DRAFTS_DIR.glob("*.json"), reverse=True)
    return files[0] if files else None


def get_pending_drafts(drafts: list) -> list:
    """Return only drafts with status 'draft'."""
    return [d for d in drafts if d.get("status") == "draft"]


def make_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard for a draft. Truncate draft_id to fit 64-byte limit."""
    short_id = draft_id[:8]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("+ Publish", callback_data=f"pub:{short_id}"),
            InlineKeyboardButton("/ Edit", callback_data=f"edit:{short_id}"),
            InlineKeyboardButton("x Skip", callback_data=f"skip:{short_id}"),
        ]
    ])


def make_edit_preview_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    short_id = draft_id[:8]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("+ Publish edit", callback_data=f"pubedit:{short_id}"),
            InlineKeyboardButton("/ Edit more", callback_data=f"editmore:{short_id}"),
            InlineKeyboardButton("x Cancel", callback_data=f"cancel:{short_id}"),
        ]
    ])


def format_draft_message(draft: dict, index: int, total: int) -> str:
    """Format a draft for admin preview."""
    has_photo = "yes" if draft.get("image_url") else "no"
    return (
        f"{draft['post_text']}\n"
        f"\n"
        f"---------------------\n"
        f"Source: {draft.get('source_name', '?')}\n"
        f"Category: {draft.get('category', '?')}\n"
        f"Words: {draft.get('word_count', '?')}\n"
        f"Photo: {has_photo}\n"
        f"{index + 1} of {total} drafts\n"
        f"---------------------"
    )


def find_draft_by_short_id(drafts: list, short_id: str) -> dict | None:
    """Find draft whose id starts with short_id."""
    for d in drafts:
        if d["id"].startswith(short_id):
            return d
    return None


# ── Publishing ───────────────────────────────────────────────────────────────


async def publish_to_channel(
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    image_url: str | None,
) -> int | None:
    """Publish post to the channel. Return message_id or None."""
    if image_url:
        try:
            if len(text) <= 1024:
                msg = await context.bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=image_url,
                    caption=text,
                    parse_mode=None,
                )
            else:
                await context.bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=image_url,
                )
                msg = await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=text,
                    disable_web_page_preview=True,
                )
            return msg.message_id
        except Exception as e:
            logger.warning("Photo failed (%s), publishing without photo", e)

    msg = await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=text,
        disable_web_page_preview=False,
    )
    return msg.message_id


def save_published(draft: dict, final_text: str, message_id: int | None, was_edited: bool) -> None:
    """Append to data/published/YYYY-MM-DD.json."""
    today = date.today().isoformat()
    path = PUBLISHED_DIR / f"{today}.json"
    published = load_json(path)
    published.append({
        "draft_id": draft["id"],
        "post_text": final_text,
        "source_url": draft.get("source_url", ""),
        "image_url": draft.get("image_url"),
        "published_at": datetime.now(timezone.utc).isoformat(),
        "was_edited": was_edited,
        "telegram_message_id": message_id,
    })
    save_json(published, path)


def update_draft_status(drafts_file: Path, draft_id: str, new_status: str) -> None:
    """Update a draft's status in the JSON file on disk."""
    data = load_json(drafts_file)
    for d in data:
        if d["id"] == draft_id:
            d["status"] = new_status
            break
    save_json(data, drafts_file)


# ── Showing drafts ───────────────────────────────────────────────────────────


async def show_current_draft(update_or_query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the current draft to the admin. Advance index if current is already processed."""
    drafts = context.user_data.get("drafts", [])
    idx = context.user_data.get("current_index", 0)

    # Skip already processed drafts
    while idx < len(drafts) and drafts[idx].get("status") != "draft":
        idx += 1
    context.user_data["current_index"] = idx

    if idx >= len(drafts):
        text = "All drafts processed!"
        if hasattr(update_or_query, "message") and update_or_query.message:
            await update_or_query.message.reply_text(text)
        else:
            await update_or_query.edit_message_text(text)
        return

    draft = drafts[idx]
    pending = get_pending_drafts(drafts)
    total = len(drafts)
    msg_text = format_draft_message(draft, idx, total)

    # Telegram message limit is 4096 chars
    if len(msg_text) > 4096:
        msg_text = msg_text[:4090] + "\n..."

    keyboard = make_keyboard(draft["id"])

    if hasattr(update_or_query, "message") and update_or_query.message:
        await update_or_query.message.reply_text(msg_text, reply_markup=keyboard)
    else:
        # From a callback — send new message instead of editing (text may be too different)
        await update_or_query._bot.send_message(
            chat_id=ADMIN_ID,
            text=msg_text,
            reply_markup=keyboard,
        )


# ── Command Handlers ─────────────────────────────────────────────────────────


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    await update.message.reply_text(
        "PropTech Russia Bot\n\n"
        "Commands:\n"
        "/drafts - review today's drafts\n"
        "/next - next draft\n"
        "/status - stats\n"
        "/help - commands list"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    await update.message.reply_text(
        "/drafts - load and review drafts\n"
        "/next - show next draft\n"
        "/status - draft/published/rejected counts\n"
        "/cancel - cancel editing\n"
        "/help - this message"
    )


async def drafts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return

    drafts_file = find_drafts_file()
    if not drafts_file:
        await update.message.reply_text(
            "No drafts found.\n"
            "Run: python src/collect.py && python src/generate.py"
        )
        return

    all_drafts = load_json(drafts_file)
    pending = get_pending_drafts(all_drafts)

    if not pending:
        await update.message.reply_text(
            f"No pending drafts in {drafts_file.name}.\n"
            f"All {len(all_drafts)} drafts already processed."
        )
        return

    context.user_data["drafts_file"] = str(drafts_file)
    context.user_data["drafts"] = all_drafts
    context.user_data["current_index"] = 0
    context.user_data["editing_draft_id"] = None
    context.user_data["edited_text"] = None

    await update.message.reply_text(
        f"Loaded {len(pending)} pending drafts from {drafts_file.name}"
    )
    await show_current_draft(update, context)


async def next_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    if "drafts" not in context.user_data:
        await update.message.reply_text("No drafts loaded. Use /drafts first.")
        return

    idx = context.user_data.get("current_index", 0) + 1
    context.user_data["current_index"] = idx
    await show_current_draft(update, context)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return

    drafts_file = find_drafts_file()
    if not drafts_file:
        await update.message.reply_text("No drafts files found.")
        return

    all_drafts = load_json(drafts_file)
    counts = {"draft": 0, "published": 0, "rejected": 0}
    for d in all_drafts:
        s = d.get("status", "draft")
        counts[s] = counts.get(s, 0) + 1

    await update.message.reply_text(
        f"File: {drafts_file.name}\n\n"
        f"Pending:   {counts['draft']}\n"
        f"Published: {counts['published']}\n"
        f"Rejected:  {counts['rejected']}\n"
        f"Total:     {len(all_drafts)}"
    )


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    context.user_data["editing_draft_id"] = None
    context.user_data["edited_text"] = None
    await update.message.reply_text("Editing cancelled.")


# ── Callback Query Handler ───────────────────────────────────────────────────


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.from_user or query.from_user.id != ADMIN_ID:
        return
    await query.answer()

    data = query.data or ""
    if ":" not in data:
        return

    action, short_id = data.split(":", 1)
    drafts = context.user_data.get("drafts", [])
    drafts_file = Path(context.user_data.get("drafts_file", ""))
    draft = find_draft_by_short_id(drafts, short_id)

    if not draft:
        await query.edit_message_text("Draft not found. Use /drafts to reload.")
        return

    # ── Publish ──────────────────────────────────────────────────────────
    if action == "pub":
        try:
            msg_id = await publish_to_channel(
                context,
                draft["post_text"],
                draft.get("image_url"),
            )
        except Exception as e:
            await query.edit_message_text(
                f"Publish failed: {e}\n\nCheck that the bot is admin in the channel."
            )
            return

        draft["status"] = "published"
        update_draft_status(drafts_file, draft["id"], "published")
        save_published(draft, draft["post_text"], msg_id, was_edited=False)

        await query.edit_message_text("Published!")

        # Show next
        context.user_data["current_index"] = context.user_data.get("current_index", 0) + 1
        await show_current_draft(query, context)

    # ── Edit ─────────────────────────────────────────────────────────────
    elif action == "edit":
        context.user_data["editing_draft_id"] = draft["id"]
        context.user_data["edited_text"] = None
        await query.edit_message_text(
            "Send the corrected text. Or /cancel to abort."
        )

    # ── Skip ─────────────────────────────────────────────────────────────
    elif action == "skip":
        draft["status"] = "rejected"
        update_draft_status(drafts_file, draft["id"], "rejected")

        await query.edit_message_text("Skipped.")

        context.user_data["current_index"] = context.user_data.get("current_index", 0) + 1
        await show_current_draft(query, context)

    # ── Publish edited text ──────────────────────────────────────────────
    elif action == "pubedit":
        edited_text = context.user_data.get("edited_text")
        if not edited_text:
            await query.edit_message_text("No edited text found. Use /drafts to restart.")
            return

        try:
            msg_id = await publish_to_channel(
                context,
                edited_text,
                draft.get("image_url"),
            )
        except Exception as e:
            await query.edit_message_text(
                f"Publish failed: {e}\n\nCheck that the bot is admin in the channel."
            )
            return

        draft["status"] = "published"
        draft["post_text"] = edited_text
        draft["word_count"] = len(edited_text.split())
        update_draft_status(drafts_file, draft["id"], "published")
        save_published(draft, edited_text, msg_id, was_edited=True)

        context.user_data["editing_draft_id"] = None
        context.user_data["edited_text"] = None

        await query.edit_message_text("Published (edited)!")

        context.user_data["current_index"] = context.user_data.get("current_index", 0) + 1
        await show_current_draft(query, context)

    # ── Edit more ────────────────────────────────────────────────────────
    elif action == "editmore":
        context.user_data["editing_draft_id"] = draft["id"]
        await query.edit_message_text(
            "Send the corrected text. Or /cancel to abort."
        )

    # ── Cancel edit ──────────────────────────────────────────────────────
    elif action == "cancel":
        context.user_data["editing_draft_id"] = None
        context.user_data["edited_text"] = None
        await query.edit_message_text("Edit cancelled.")
        await show_current_draft(query, context)


# ── Text Message Handler (for editing) ───────────────────────────────────────


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return

    editing_id = context.user_data.get("editing_draft_id")
    if not editing_id:
        return  # Not in edit mode, ignore

    new_text = update.message.text.strip()
    if not new_text:
        return

    context.user_data["edited_text"] = new_text

    draft = find_draft_by_short_id(context.user_data.get("drafts", []), editing_id[:8])
    if not draft:
        draft = {"id": editing_id}

    preview = (
        f"Edited post preview:\n"
        f"---------------------\n"
        f"{new_text}\n"
        f"---------------------"
    )

    if len(preview) > 4096:
        preview = preview[:4090] + "\n..."

    keyboard = make_edit_preview_keyboard(draft["id"])
    await update.message.reply_text(preview, reply_markup=keyboard)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    if not BOT_TOKEN:
        logger.error("TG_BOT_TOKEN not set in config/.env")
        sys.exit(1)
    if not CHANNEL_ID:
        logger.error("TG_CHANNEL_ID not set in config/.env")
        sys.exit(1)
    if not ADMIN_ID:
        logger.error("TG_ADMIN_ID not set in config/.env")
        sys.exit(1)

    logger.info("Starting PropTech Russia bot...")
    logger.info("Channel: %s, Admin ID: %d", CHANNEL_ID, ADMIN_ID)

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("drafts", drafts_cmd))
    app.add_handler(CommandHandler("next", next_draft))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()


if __name__ == "__main__":
    main()
