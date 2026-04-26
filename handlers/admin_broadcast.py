from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from db.base import BroadcastButtonType, BroadcastKind, BroadcastStatus
from db.broadcast_queries import get_broadcast, list_broadcasts, save_broadcast_draft
from services.broadcast_service import (
    BroadcastDraftPayload,
    broadcast_has_translations,
    list_internal_actions,
    pack_broadcast_value,
    resolve_broadcast_value,
    send_broadcast_preview,
    short_broadcast_text,
    start_broadcast_delivery,
)
from services.context import AppContext
from services.users import get_user_language
from states import AdminBroadcastState
from utils.messages import answer_or_edit


def build_admin_broadcast_router(app: AppContext, bot: Bot) -> Router:
    router = Router(name="admin_broadcast")

    def _guard(user_id: int) -> bool:
        return app.is_admin(user_id)

    def _internal_actions_map() -> dict[str, str]:
        return {action_id: label for action_id, label in list_internal_actions()}

    async def _admin_language(admin_telegram_id: int) -> str:
        async with app.session_factory() as session:
            return await get_user_language(session, admin_telegram_id, app.settings.default_language)

    def _multilingual_prompt(subject: str) -> str:
        return (
            f"{subject}\n\n"
            "Можно отправить один общий текст для всех пользователей.\n\n"
            "Если нужна рассылка по языку пользователя, отправьте текст в формате:\n"
            "ru: Русский текст\n\n"
            "uz: O'zbekcha matn\n\n"
            "en: English text"
        )

    def _menu_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Создать текстовую рассылку", callback_data="admin:broadcasts:create:text")],
                [InlineKeyboardButton(text="Создать фото-рассылку", callback_data="admin:broadcasts:create:photo")],
                [InlineKeyboardButton(text="История рассылок", callback_data="admin:broadcasts:history")],
                [InlineKeyboardButton(text="Назад", callback_data="admin:main")],
            ]
        )

    def _cancel_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Отмена", callback_data="admin:broadcasts:cancel")],
                [InlineKeyboardButton(text="Меню", callback_data="admin:main")],
            ]
        )

    def _button_choice_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Да", callback_data="admin:broadcasts:button:yes")],
                [InlineKeyboardButton(text="Нет", callback_data="admin:broadcasts:button:no")],
                [InlineKeyboardButton(text="Отмена", callback_data="admin:broadcasts:cancel")],
            ]
        )

    def _button_type_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Ссылка", callback_data="admin:broadcasts:button_type:url")],
                [InlineKeyboardButton(text="Сценарий бота", callback_data="admin:broadcasts:button_type:internal")],
                [InlineKeyboardButton(text="Отмена", callback_data="admin:broadcasts:cancel")],
            ]
        )

    def _internal_actions_markup() -> InlineKeyboardMarkup:
        rows = [
            [InlineKeyboardButton(text=label, callback_data=f"admin:broadcasts:internal_action:{action_id}")]
            for action_id, label in list_internal_actions()
        ]
        rows.append([InlineKeyboardButton(text="Отмена", callback_data="admin:broadcasts:cancel")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _preview_controls_markup(broadcast_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Отправить всем", callback_data=f"admin:broadcasts:preview:send:{broadcast_id}")],
                [InlineKeyboardButton(text="Отправить тест", callback_data=f"admin:broadcasts:preview:test:{broadcast_id}")],
                [InlineKeyboardButton(text="Редактировать", callback_data=f"admin:broadcasts:preview:edit:{broadcast_id}")],
                [InlineKeyboardButton(text="Отмена", callback_data=f"admin:broadcasts:preview:cancel:{broadcast_id}")],
            ]
        )

    def _edit_markup(broadcast) -> InlineKeyboardMarkup:
        rows = [
            [InlineKeyboardButton(text="Изменить текст / подпись", callback_data=f"admin:broadcasts:edit:text:{broadcast.id}")],
        ]
        if broadcast.broadcast_type == BroadcastKind.PHOTO:
            rows.append([InlineKeyboardButton(text="Изменить фото", callback_data=f"admin:broadcasts:edit:photo:{broadcast.id}")])
        rows.append([InlineKeyboardButton(text="Настроить кнопку", callback_data=f"admin:broadcasts:edit:button:{broadcast.id}")])
        if broadcast.button_type != BroadcastButtonType.NONE:
            rows.append(
                [InlineKeyboardButton(text="Убрать кнопку", callback_data=f"admin:broadcasts:edit:button_clear:{broadcast.id}")]
            )
        rows.append([InlineKeyboardButton(text="Показать preview", callback_data=f"admin:broadcasts:preview:show:{broadcast.id}")])
        rows.append([InlineKeyboardButton(text="Назад", callback_data=f"admin:broadcasts:preview:show:{broadcast.id}")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _history_markup(items) -> InlineKeyboardMarkup:
        rows = [
            [
                InlineKeyboardButton(
                    text=(
                        f"{item.created_at.strftime('%m-%d %H:%M')} | "
                        f"{_broadcast_kind_label(item.broadcast_type)} | "
                        f"{_broadcast_status_label(item.status)}"
                    ),
                    callback_data=f"admin:broadcasts:history:view:{item.id}",
                )
            ]
            for item in items
        ]
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:broadcasts")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _broadcast_kind_label(kind: BroadcastKind) -> str:
        return {
            BroadcastKind.TEXT: "text",
            BroadcastKind.PHOTO: "photo",
        }[kind]

    def _broadcast_status_label(status: BroadcastStatus) -> str:
        return {
            BroadcastStatus.DRAFT: "draft",
            BroadcastStatus.SENT: "sent",
            BroadcastStatus.FAILED: "failed",
            BroadcastStatus.CANCELLED: "cancelled",
        }[status]

    def _button_label(button_type: BroadcastButtonType, button_text: str | None, button_value: str | None) -> str:
        label_text = resolve_broadcast_value(button_text, "ru") or "-"
        if broadcast_has_translations(button_text):
            label_text = f"multi | {label_text}"
        if button_type == BroadcastButtonType.NONE:
            return "без кнопки"
        if button_type == BroadcastButtonType.URL:
            return f"url | {label_text} -> {button_value or '-'}"
        if button_type == BroadcastButtonType.INTERNAL_ACTION:
            action_label = _internal_actions_map().get(button_value or "", button_value or "-")
            return f"internal | {label_text} -> {action_label}"
        return "-"

    def _payload_from_broadcast(broadcast) -> BroadcastDraftPayload:
        return BroadcastDraftPayload(
            broadcast_type=broadcast.broadcast_type,
            message_text=broadcast.message_text,
            photo_file_id=broadcast.photo_file_id,
            button_type=broadcast.button_type,
            button_text=broadcast.button_text,
            button_value=broadcast.button_value,
        )

    async def _load_broadcast_into_state(state: FSMContext, broadcast) -> None:
        await state.clear()
        await state.update_data(
            draft_id=broadcast.id,
            broadcast_type=broadcast.broadcast_type.value,
            message_text=broadcast.message_text,
            photo_file_id=broadcast.photo_file_id,
            button_type=broadcast.button_type.value,
            button_text=broadcast.button_text,
            button_value=broadcast.button_value,
        )

    async def _payload_from_state(state: FSMContext) -> BroadcastDraftPayload | None:
        data = await state.get_data()
        broadcast_type_raw = data.get("broadcast_type")
        if not broadcast_type_raw:
            return None
        return BroadcastDraftPayload(
            broadcast_type=BroadcastKind(broadcast_type_raw),
            message_text=(data.get("message_text") or "").strip(),
            photo_file_id=data.get("photo_file_id"),
            button_type=BroadcastButtonType(data.get("button_type") or BroadcastButtonType.NONE.value),
            button_text=(data.get("button_text") or "").strip() or None,
            button_value=(data.get("button_value") or "").strip() or None,
        )

    async def _show_missing_draft(target: CallbackQuery) -> None:
        await target.answer("Черновик не найден.", show_alert=True)
        await answer_or_edit(
            target,
            "Черновик рассылки не найден. Создайте новую рассылку через админ-меню.",
            reply_markup=_menu_markup(),
        )

    async def _show_preview_notice(target: Message | CallbackQuery, text: str) -> None:
        if isinstance(target, CallbackQuery):
            await answer_or_edit(
                target,
                text,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="Меню рассылок", callback_data="admin:broadcasts")]]
                ),
            )
            return
        await target.answer(text)

    async def _show_preview_message(chat_id: int, broadcast_id: int, payload: BroadcastDraftPayload) -> None:
        await send_broadcast_preview(bot, chat_id, payload, language=await _admin_language(chat_id))
        await bot.send_message(
            chat_id,
            "Выберите действие с этой рассылкой.",
            reply_markup=_preview_controls_markup(broadcast_id),
        )

    async def _save_preview(target: Message | CallbackQuery, state: FSMContext, admin_id: int) -> None:
        payload = await _payload_from_state(state)
        data = await state.get_data()
        if payload is None:
            if isinstance(target, CallbackQuery):
                await _show_missing_draft(target)
            else:
                await target.answer("Черновик рассылки не найден. Начните создание заново через админ-меню.")
            return

        async with app.session_factory() as session:
            draft = await save_broadcast_draft(
                session,
                broadcast_id=data.get("draft_id"),
                broadcast_type=payload.broadcast_type,
                message_text=payload.message_text,
                photo_file_id=payload.photo_file_id,
                button_type=payload.button_type,
                button_text=payload.button_text,
                button_value=payload.button_value,
                created_by_admin_telegram_id=admin_id,
            )
            draft.status = BroadcastStatus.DRAFT
            await session.commit()
            draft_id = draft.id

        await state.clear()
        await _show_preview_notice(target, "Черновик сохранён. Актуальный preview отправлен ниже.")
        chat_id = target.from_user.id if isinstance(target, CallbackQuery) else target.chat.id
        await _show_preview_message(chat_id, draft_id, payload)

    async def _show_preview_from_draft(callback: CallbackQuery, broadcast_id: int, *, notice: str) -> None:
        async with app.session_factory() as session:
            broadcast = await get_broadcast(session, broadcast_id)
        if broadcast is None:
            await _show_missing_draft(callback)
            return
        await callback.answer()
        await _show_preview_notice(callback, notice)
        await _show_preview_message(callback.from_user.id, broadcast.id, _payload_from_broadcast(broadcast))

    async def _require_active_state(callback: CallbackQuery, state: FSMContext) -> bool:
        data = await state.get_data()
        if data.get("broadcast_type"):
            return True
        await _show_missing_draft(callback)
        return False

    async def _load_draft_record(
        callback: CallbackQuery,
        broadcast_id: int,
        *,
        require_draft: bool = False,
    ):
        async with app.session_factory() as session:
            broadcast = await get_broadcast(session, broadcast_id)
        if broadcast is None:
            await _show_missing_draft(callback)
            return None
        if require_draft and broadcast.status != BroadcastStatus.DRAFT:
            await callback.answer("Доступно только для черновика.", show_alert=True)
            await answer_or_edit(
                callback,
                "Этот черновик уже отправлен или закрыт. Для новой отправки создайте новую рассылку.",
                reply_markup=_menu_markup(),
            )
            return None
        return broadcast

    @router.callback_query(F.data == "admin:broadcasts")
    async def broadcast_menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            (
                "<b>Рассылка</b>\n\n"
                "Здесь можно собрать текстовую или фото-рассылку, добавить одну кнопку, "
                "посмотреть preview, отправить тест и затем безопасно запустить массовую отправку."
            ),
            reply_markup=_menu_markup(),
        )

    @router.callback_query(F.data == "admin:broadcasts:create:text")
    async def broadcast_create_text_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.clear()
        await state.set_state(AdminBroadcastState.waiting_text)
        await state.update_data(broadcast_type=BroadcastKind.TEXT.value)
        await callback.answer()
        await answer_or_edit(
            callback,
            _multilingual_prompt("Отправьте текст сообщения для рассылки."),
            reply_markup=_cancel_markup(),
        )

    @router.callback_query(F.data == "admin:broadcasts:create:photo")
    async def broadcast_create_photo_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.clear()
        await state.set_state(AdminBroadcastState.waiting_photo)
        await state.update_data(broadcast_type=BroadcastKind.PHOTO.value)
        await callback.answer()
        await answer_or_edit(
            callback,
            "Отправьте фото для рассылки.",
            reply_markup=_cancel_markup(),
        )

    @router.message(AdminBroadcastState.waiting_text)
    async def broadcast_text_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            await state.clear()
            return
        text = (message.text or "").strip()
        if not text:
            await message.answer("Текст сообщения не должен быть пустым.")
            return
        await state.update_data(message_text=pack_broadcast_value(text))
        data = await state.get_data()
        if data.get("edit_field") == "text":
            await _save_preview(message, state, message.from_user.id)
            return
        await message.answer("Добавить кнопку?", reply_markup=_button_choice_markup())

    @router.message(AdminBroadcastState.waiting_photo, F.photo)
    async def broadcast_photo_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            await state.clear()
            return
        await state.update_data(photo_file_id=message.photo[-1].file_id)
        data = await state.get_data()
        if data.get("edit_field") == "photo":
            await _save_preview(message, state, message.from_user.id)
            return
        await state.set_state(AdminBroadcastState.waiting_caption)
        await message.answer(_multilingual_prompt("Отправьте подпись / текст для фото-рассылки."), reply_markup=_cancel_markup())

    @router.message(AdminBroadcastState.waiting_photo)
    async def broadcast_photo_invalid_handler(message: Message) -> None:
        await message.answer("Нужно отправить именно фото для фото-рассылки.")

    @router.message(AdminBroadcastState.waiting_caption)
    async def broadcast_caption_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            await state.clear()
            return
        text = (message.text or "").strip()
        if not text:
            await message.answer("Подпись не должна быть пустой.")
            return
        await state.update_data(message_text=pack_broadcast_value(text))
        data = await state.get_data()
        if data.get("edit_field") == "text":
            await _save_preview(message, state, message.from_user.id)
            return
        await message.answer("Добавить кнопку?", reply_markup=_button_choice_markup())

    @router.callback_query(F.data == "admin:broadcasts:button:yes")
    async def broadcast_button_yes_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        if not await _require_active_state(callback, state):
            return
        await callback.answer()
        await answer_or_edit(callback, "Выберите тип кнопки.", reply_markup=_button_type_markup())

    @router.callback_query(F.data == "admin:broadcasts:button:no")
    async def broadcast_button_no_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        if not await _require_active_state(callback, state):
            return
        await state.update_data(button_type=BroadcastButtonType.NONE.value, button_text=None, button_value=None)
        await callback.answer()
        await _save_preview(callback, state, callback.from_user.id)

    @router.callback_query(F.data == "admin:broadcasts:button_type:url")
    async def broadcast_button_type_url_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        if not await _require_active_state(callback, state):
            return
        await state.set_state(AdminBroadcastState.waiting_button_text)
        await state.update_data(button_type=BroadcastButtonType.URL.value, button_text=None, button_value=None)
        await callback.answer()
        await answer_or_edit(callback, _multilingual_prompt("Введите текст кнопки для ссылки."), reply_markup=_cancel_markup())

    @router.callback_query(F.data == "admin:broadcasts:button_type:internal")
    async def broadcast_button_type_internal_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        if not await _require_active_state(callback, state):
            return
        await state.set_state(AdminBroadcastState.waiting_button_text)
        await state.update_data(button_type=BroadcastButtonType.INTERNAL_ACTION.value, button_text=None, button_value=None)
        await callback.answer()
        await answer_or_edit(
            callback,
            _multilingual_prompt("Введите текст кнопки для внутреннего сценария бота."),
            reply_markup=_cancel_markup(),
        )

    @router.message(AdminBroadcastState.waiting_button_text)
    async def broadcast_button_text_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            await state.clear()
            return
        button_text = (message.text or "").strip()
        if not button_text:
            await message.answer("Текст кнопки не должен быть пустым.")
            return
        await state.update_data(button_text=pack_broadcast_value(button_text))
        data = await state.get_data()
        if data.get("button_type") == BroadcastButtonType.URL.value:
            await state.set_state(AdminBroadcastState.waiting_button_url)
            await message.answer("Введите URL для кнопки. Пример: https://example.com", reply_markup=_cancel_markup())
            return
        await message.answer(
            "Выберите внутренний сценарий бота для кнопки.",
            reply_markup=_internal_actions_markup(),
        )

    @router.message(AdminBroadcastState.waiting_button_url)
    async def broadcast_button_url_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            await state.clear()
            return
        url = (message.text or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            await message.answer("Укажите корректный URL, который начинается с http:// или https://")
            return
        await state.update_data(button_value=url)
        await _save_preview(message, state, message.from_user.id)

    @router.callback_query(F.data.startswith("admin:broadcasts:internal_action:"))
    async def broadcast_internal_action_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        if not await _require_active_state(callback, state):
            return
        action_id = callback.data.split(":")[-1]
        if action_id not in _internal_actions_map():
            await callback.answer("Сценарий не найден.", show_alert=True)
            return
        await state.update_data(button_value=action_id)
        await callback.answer()
        await _save_preview(callback, state, callback.from_user.id)

    @router.callback_query(F.data == "admin:broadcasts:cancel")
    async def broadcast_cancel_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.clear()
        await callback.answer("Сценарий отменён.")
        await answer_or_edit(callback, "Создание или редактирование рассылки отменено.", reply_markup=_menu_markup())

    @router.callback_query(F.data.startswith("admin:broadcasts:preview:test:"))
    async def broadcast_preview_test_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        broadcast_id = int(callback.data.split(":")[-1])
        broadcast = await _load_draft_record(callback, broadcast_id, require_draft=True)
        if broadcast is None:
            return
        await callback.answer("Отправляю тест.")
        await send_broadcast_preview(
            bot,
            callback.from_user.id,
            _payload_from_broadcast(broadcast),
            language=await _admin_language(callback.from_user.id),
        )

    @router.callback_query(F.data.startswith("admin:broadcasts:preview:send:"))
    async def broadcast_preview_send_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        broadcast_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            broadcast = await get_broadcast(session, broadcast_id)
            if broadcast is None:
                await callback.answer()
                await _show_missing_draft(callback)
                return
            if broadcast.status != BroadcastStatus.DRAFT:
                await callback.answer("Эта рассылка уже отправлена или закрыта.", show_alert=True)
                await answer_or_edit(
                    callback,
                    "Массовая отправка доступна только для черновика со статусом draft.",
                    reply_markup=_menu_markup(),
                )
                return

        started = await start_broadcast_delivery(app, bot, broadcast_id=broadcast_id)
        await callback.answer("Рассылка запущена." if started else "Рассылка уже выполняется.")
        if started:
            await answer_or_edit(
                callback,
                "Рассылка запущена в фоне. Когда отправка завершится, бот пришлёт отдельный итоговый отчёт.",
                reply_markup=_menu_markup(),
            )

    @router.callback_query(F.data.startswith("admin:broadcasts:preview:edit:"))
    async def broadcast_preview_edit_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        broadcast_id = int(callback.data.split(":")[-1])
        broadcast = await _load_draft_record(callback, broadcast_id, require_draft=True)
        if broadcast is None:
            return
        await callback.answer()
        await answer_or_edit(
            callback,
            (
                f"<b>Редактирование рассылки #{broadcast.id}</b>\n\n"
                f"Тип: <b>{_broadcast_kind_label(broadcast.broadcast_type)}</b>\n"
                f"Кнопка: <b>{_button_label(broadcast.button_type, broadcast.button_text, broadcast.button_value)}</b>"
            ),
            reply_markup=_edit_markup(broadcast),
        )

    @router.callback_query(F.data.startswith("admin:broadcasts:preview:show:"))
    async def broadcast_preview_show_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        broadcast_id = int(callback.data.split(":")[-1])
        await _show_preview_from_draft(callback, broadcast_id, notice="Актуальный preview отправлен ниже.")

    @router.callback_query(F.data.startswith("admin:broadcasts:edit:text:"))
    async def broadcast_edit_text_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        broadcast_id = int(callback.data.split(":")[-1])
        broadcast = await _load_draft_record(callback, broadcast_id, require_draft=True)
        if broadcast is None:
            return
        await _load_broadcast_into_state(state, broadcast)
        await state.update_data(edit_field="text")
        target_state = AdminBroadcastState.waiting_caption if broadcast.broadcast_type == BroadcastKind.PHOTO else AdminBroadcastState.waiting_text
        await state.set_state(target_state)
        await callback.answer()
        prompt = (
            _multilingual_prompt("Отправьте новую подпись для фото-рассылки.")
            if broadcast.broadcast_type == BroadcastKind.PHOTO
            else _multilingual_prompt("Отправьте новый текст сообщения.")
        )
        await answer_or_edit(callback, prompt, reply_markup=_cancel_markup())

    @router.callback_query(F.data.startswith("admin:broadcasts:edit:photo:"))
    async def broadcast_edit_photo_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        broadcast_id = int(callback.data.split(":")[-1])
        broadcast = await _load_draft_record(callback, broadcast_id, require_draft=True)
        if broadcast is None:
            return
        if broadcast.broadcast_type != BroadcastKind.PHOTO:
            await callback.answer("Фото доступно только для photo-рассылки.", show_alert=True)
            return
        await _load_broadcast_into_state(state, broadcast)
        await state.update_data(edit_field="photo")
        await state.set_state(AdminBroadcastState.waiting_photo)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте новое фото для этой рассылки.", reply_markup=_cancel_markup())

    @router.callback_query(F.data.startswith("admin:broadcasts:edit:button:"))
    async def broadcast_edit_button_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        broadcast_id = int(callback.data.split(":")[-1])
        broadcast = await _load_draft_record(callback, broadcast_id)
        if broadcast is None:
            return
        await _load_broadcast_into_state(state, broadcast)
        await state.update_data(edit_field="button")
        await callback.answer()
        await answer_or_edit(callback, "Выберите новый тип кнопки.", reply_markup=_button_type_markup())

    @router.callback_query(F.data.startswith("admin:broadcasts:edit:button_clear:"))
    async def broadcast_edit_button_clear_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        broadcast_id = int(callback.data.split(":")[-1])
        broadcast = await _load_draft_record(callback, broadcast_id, require_draft=True)
        if broadcast is None:
            return
        async with app.session_factory() as session:
            broadcast = await get_broadcast(session, broadcast_id)
            broadcast.button_type = BroadcastButtonType.NONE
            broadcast.button_text = None
            broadcast.button_value = None
            broadcast.status = BroadcastStatus.DRAFT
            await session.commit()
        await _show_preview_from_draft(callback, broadcast_id, notice="Кнопка удалена. Актуальный preview отправлен ниже.")

    @router.callback_query(F.data.startswith("admin:broadcasts:preview:cancel:"))
    async def broadcast_preview_cancel_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        broadcast_id = int(callback.data.split(":")[-1])
        await state.clear()
        async with app.session_factory() as session:
            broadcast = await get_broadcast(session, broadcast_id)
            if broadcast is not None and broadcast.status == BroadcastStatus.DRAFT:
                broadcast.status = BroadcastStatus.CANCELLED
                await session.commit()
        await callback.answer("Черновик отменён.")
        await answer_or_edit(callback, "Черновик рассылки отменён.", reply_markup=_menu_markup())

    @router.callback_query(F.data == "admin:broadcasts:history")
    async def broadcast_history_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        async with app.session_factory() as session:
            items = await list_broadcasts(session, limit=12)
        await callback.answer()
        if not items:
            await answer_or_edit(callback, "История рассылок пока пуста.", reply_markup=_menu_markup())
            return
        await answer_or_edit(
            callback,
            "<b>История рассылок</b>\n\nВыберите рассылку, чтобы посмотреть детали.",
            reply_markup=_history_markup(items),
        )

    @router.callback_query(F.data.startswith("admin:broadcasts:history:view:"))
    async def broadcast_history_detail_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        broadcast_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            broadcast = await get_broadcast(session, broadcast_id)
        await callback.answer()
        if broadcast is None:
            await answer_or_edit(callback, "Рассылка не найдена.", reply_markup=_menu_markup())
            return
        sent_at = broadcast.sent_at.strftime("%Y-%m-%d %H:%M") if broadcast.sent_at else "-"
        message_text = resolve_broadcast_value(broadcast.message_text, "ru") or "-"
        short_text = short_broadcast_text(broadcast.message_text, language="ru")
        text = (
            f"<b>Рассылка #{broadcast.id}</b>\n\n"
            f"Тип: <b>{_broadcast_kind_label(broadcast.broadcast_type)}</b>\n"
            f"Статус: <b>{_broadcast_status_label(broadcast.status)}</b>\n"
            f"Текст: {message_text}\n"
            f"Фото: <code>{broadcast.photo_file_id or '-'}</code>\n"
            f"Кнопка: {_button_label(broadcast.button_type, broadcast.button_text, broadcast.button_value)}\n"
            f"Создана: <b>{broadcast.created_at.strftime('%Y-%m-%d %H:%M')}</b>\n"
            f"Отправлена: <b>{sent_at}</b>\n"
            f"Получателей: <b>{broadcast.total_recipients}</b>\n"
            f"Успешно: <b>{broadcast.success_count}</b>\n"
            f"Ошибок: <b>{broadcast.failed_count}</b>\n"
            f"Кратко: {short_text}"
        )
        await answer_or_edit(
            callback,
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="admin:broadcasts:history")]]
            ),
        )

    return router
