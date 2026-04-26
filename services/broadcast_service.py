from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from db.base import BroadcastButtonType, BroadcastKind, BroadcastStatus, utcnow
from db.broadcast_queries import get_broadcast
from db.models import User
from services.texts import normalize_language
from utils.logger import get_logger


@dataclass(slots=True)
class BroadcastDraftPayload:
    broadcast_type: BroadcastKind
    message_text: str
    photo_file_id: str | None = None
    button_type: BroadcastButtonType = BroadcastButtonType.NONE
    button_text: str | None = None
    button_value: str | None = None


_LOGGER = get_logger("services.broadcast")
_ACTIVE_BROADCAST_TASKS: dict[int, asyncio.Task[None]] = {}
_BROADCAST_LANGUAGES: tuple[str, ...] = ("ru", "uz", "en")
_BROADCAST_LANG_PATTERN = re.compile(r"^(ru|uz|en)\s*:\s*(.*)$", re.IGNORECASE)

_INTERNAL_ACTIONS: tuple[tuple[str, str, str], ...] = (
    ("subscriptions", "Открыть подписки", "open_subscriptions"),
    ("chatgpt", "Открыть тарифы ChatGPT", "open_chatgpt"),
    ("capcut", "Открыть тарифы CapCut Pro", "open_capcut"),
    ("profile", "Открыть профиль", "menu:profile"),
    ("faq", "Открыть FAQ", "menu:faq"),
    ("main_menu", "Открыть главное меню", "menu:main"),
)


def list_internal_actions() -> list[tuple[str, str]]:
    return [(action_id, title) for action_id, title, _ in _INTERNAL_ACTIONS]


def get_internal_action_callback(action_id: str) -> str | None:
    for candidate_id, _title, callback_data in _INTERNAL_ACTIONS:
        if candidate_id == action_id:
            return callback_data
    return None


def pack_broadcast_value(raw_value: str) -> str:
    value = (raw_value or "").strip()
    translations = _parse_multilingual_input(value)
    if not translations:
        return value
    return json.dumps(translations, ensure_ascii=False, separators=(",", ":"))


def resolve_broadcast_value(raw_value: str | None, language: str) -> str:
    value = (raw_value or "").strip()
    if not value:
        return ""
    translations = _parse_packed_translations(value)
    if not translations:
        return value
    normalized_language = normalize_language(language)
    return (
        translations.get(normalized_language)
        or translations.get("ru")
        or translations.get("uz")
        or translations.get("en")
        or value
    )


def broadcast_has_translations(raw_value: str | None) -> bool:
    return _parse_packed_translations(raw_value) is not None


def _parse_multilingual_input(raw_value: str) -> dict[str, str] | None:
    if not raw_value:
        return None
    lines = raw_value.splitlines()
    translations: dict[str, str] = {}
    current_language: str | None = None
    buffer: list[str] = []

    for line in lines:
        match = _BROADCAST_LANG_PATTERN.match(line.strip())
        if match:
            if current_language is not None:
                text = "\n".join(buffer).strip()
                if text:
                    translations[current_language] = text
            current_language = match.group(1).lower()
            inline_value = match.group(2)
            buffer = [inline_value] if inline_value else []
            continue

        if current_language is None:
            if line.strip():
                return None
            continue

        buffer.append(line)

    if current_language is None:
        return None

    text = "\n".join(buffer).strip()
    if text:
        translations[current_language] = text

    if not translations:
        return None

    ordered_translations: dict[str, str] = {}
    for language in _BROADCAST_LANGUAGES:
        candidate = (translations.get(language) or "").strip()
        if candidate:
            ordered_translations[language] = candidate
    return ordered_translations or None


def _parse_packed_translations(raw_value: str | None) -> dict[str, str] | None:
    value = (raw_value or "").strip()
    if not value or not value.startswith("{"):
        return None
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    translations: dict[str, str] = {}
    for language in _BROADCAST_LANGUAGES:
        candidate = payload.get(language)
        if isinstance(candidate, str) and candidate.strip():
            translations[language] = candidate.strip()
    return translations or None


def build_broadcast_markup(
    button_type: BroadcastButtonType,
    button_text: str | None,
    button_value: str | None,
    *,
    language: str = "ru",
) -> InlineKeyboardMarkup | None:
    localized_button_text = resolve_broadcast_value(button_text, language)
    if button_type == BroadcastButtonType.NONE or not localized_button_text:
        return None
    if button_type == BroadcastButtonType.URL and button_value:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=localized_button_text, url=button_value)]]
        )
    if button_type == BroadcastButtonType.INTERNAL_ACTION and button_value:
        callback_data = get_internal_action_callback(button_value)
        if callback_data:
            return InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=localized_button_text, callback_data=callback_data)]]
            )
    return None


async def send_broadcast_preview(
    bot: Bot,
    chat_id: int,
    payload: BroadcastDraftPayload,
    *,
    language: str = "ru",
) -> None:
    message_text = resolve_broadcast_value(payload.message_text, language)
    reply_markup = build_broadcast_markup(
        payload.button_type,
        payload.button_text,
        payload.button_value,
        language=language,
    )
    if payload.broadcast_type == BroadcastKind.PHOTO and payload.photo_file_id:
        await bot.send_photo(
            chat_id,
            photo=payload.photo_file_id,
            caption=message_text or None,
            reply_markup=reply_markup,
        )
        return
    await bot.send_message(chat_id, message_text or "-", reply_markup=reply_markup)


def short_broadcast_text(text: str, *, language: str = "ru", limit: int = 48) -> str:
    normalized = " ".join(resolve_broadcast_value(text, language).split())
    if len(normalized) <= limit:
        return normalized or "Без текста"
    return normalized[: limit - 1].rstrip() + "…"


async def start_broadcast_delivery(app, bot: Bot, *, broadcast_id: int) -> bool:
    active_task = _ACTIVE_BROADCAST_TASKS.get(broadcast_id)
    if active_task is not None and not active_task.done():
        return False

    task = asyncio.create_task(_run_broadcast_delivery(app, bot, broadcast_id))
    _ACTIVE_BROADCAST_TASKS[broadcast_id] = task
    task.add_done_callback(lambda _: _ACTIVE_BROADCAST_TASKS.pop(broadcast_id, None))
    return True


async def _run_broadcast_delivery(app, bot: Bot, broadcast_id: int) -> None:
    async with app.session_factory() as session:
        broadcast = await get_broadcast(session, broadcast_id)
        if broadcast is None:
            return
        recipients = list(await session.execute(select(User.telegram_id, User.language).order_by(User.id)))
        broadcast.total_recipients = len(recipients)
        broadcast.success_count = 0
        broadcast.failed_count = 0
        await session.commit()

        payload = BroadcastDraftPayload(
            broadcast_type=broadcast.broadcast_type,
            message_text=broadcast.message_text,
            photo_file_id=broadcast.photo_file_id,
            button_type=broadcast.button_type,
            button_text=broadcast.button_text,
            button_value=broadcast.button_value,
        )

    success_count = 0
    failed_count = 0

    for index, recipient in enumerate(recipients, start=1):
        telegram_id = recipient[0]
        language_enum = recipient[1]
        language = normalize_language(language_enum.value if language_enum else None)
        message_text = resolve_broadcast_value(payload.message_text, language)
        reply_markup = build_broadcast_markup(
            payload.button_type,
            payload.button_text,
            payload.button_value,
            language=language,
        )
        try:
            if payload.broadcast_type == BroadcastKind.PHOTO and payload.photo_file_id:
                await bot.send_photo(
                    telegram_id,
                    photo=payload.photo_file_id,
                    caption=message_text or None,
                    reply_markup=reply_markup,
                )
            else:
                await bot.send_message(
                    telegram_id,
                    message_text or "-",
                    reply_markup=reply_markup,
                )
            success_count += 1
        except Exception as exc:
            failed_count += 1
            _LOGGER.warning("Broadcast delivery failed | broadcast_id=%s user_id=%s error=%s", broadcast_id, telegram_id, exc)

        if index % 20 == 0:
            await asyncio.sleep(1.0)
        else:
            await asyncio.sleep(0.05)

    async with app.session_factory() as session:
        broadcast = await get_broadcast(session, broadcast_id)
        if broadcast is None:
            return
        broadcast.success_count = success_count
        broadcast.failed_count = failed_count
        broadcast.sent_at = utcnow()
        broadcast.status = BroadcastStatus.SENT if success_count > 0 else BroadcastStatus.FAILED
        await session.commit()
        creator_id = broadcast.created_by_admin_telegram_id

    try:
        await bot.send_message(
            creator_id,
            (
                "✅ Рассылка завершена.\n\n"
                f"Получателей: <b>{success_count + failed_count}</b>\n"
                f"Успешно: <b>{success_count}</b>\n"
                f"Ошибок: <b>{failed_count}</b>"
            ),
        )
    except Exception:
        _LOGGER.exception("Failed to send broadcast summary to admin %s", creator_id)
