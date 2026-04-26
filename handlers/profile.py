from __future__ import annotations

from decimal import Decimal
from html import escape
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from handlers.common import (
    order_detail_markup,
    profile_markup,
    topup_amounts_markup,
    topup_methods_markup,
    topup_receipt_markup,
)
from services.balance import list_balance_transactions
from services.context import AppContext
from services.orders import get_order_by_id, list_orders_for_user
from services.payments import get_payment_method_by_code, payment_instruction, payment_title
from services.texts import format_text
from services.topups import create_topup
from services.users import count_orders_for_user, get_user_by_telegram_id, get_user_language
from states import UserFlowState
from utils.formatting import (
    format_datetime_local,
    format_money,
    order_display_number,
    order_status_label,
)
from utils.messages import answer_or_edit


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


MIN_TOPUP_AMOUNT = Decimal("80000.00")
CLICK_QR_IMAGE_PATH = Path(__file__).resolve().parents[1] / "media" / "click.png.jpg"


def _money_unit(language: str) -> str:
    if language == "uz":
        return "so'm"
    if language == "en":
        return "UZS"
    return "сум"


def _sum_text(value: Decimal | int | float | str, language: str) -> str:
    amount_text = format_money(value, "сум").replace(" сум", "")
    return f"{amount_text} {_money_unit(language)}"


def _back_text(language: str) -> str:
    if language == "uz":
        return "◀ Orqaga"
    if language == "en":
        return "◀ Back"
    return "◀ Назад"


def _menu_text(language: str) -> str:
    if language == "uz":
        return "🏠 Menyu"
    if language == "en":
        return "🏠 Menu"
    return "🏠 Меню"


def _balance_tx_label(tx_type: str) -> str:
    mapping = {
        "topup": "✅ Пополнение",
        "purchase": "🛒 Покупка",
        "refund": "↩️ Возврат",
        "admin_adjustment": "🛠 Корректировка",
    }
    return mapping.get(tx_type, tx_type)


def _profile_text(user, orders_count: int) -> str:
    username = f"@{user.username.lstrip('@')}" if (user.username or "").strip() else "—"
    return (
        "<b>👤 Ваш профиль</b>\n\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"👤 Username: {escape(username)}\n"
        f"💰 Баланс: {format_money(user.balance, 'сум').replace(' сум', '')} сум\n"
        f"🛒 Покупок: {orders_count}\n"
        f"📅 Регистрация: {format_datetime_local(user.created_at)}"
    )


def _orders_markup(orders: list, language: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{order_display_number(order)} • {order.product_name_snapshot}", callback_data=f"order:detail:{order.id}")]
        for order in orders
    ]
    rows.append([InlineKeyboardButton(text="◀ Назад", callback_data="menu:profile", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _topup_other_amount_text(language: str) -> str:
    if language == "uz":
        return "✍️ Boshqa summa"
    if language == "en":
        return "✍️ Other amount"
    return "✍️ Другая сумма"


def _topup_crypto_text(language: str) -> str:
    if language == "uz":
        return "Kriptovalyuta"
    if language == "en":
        return "Cryptocurrency"
    return "Криптовалюта"


def _topup_amounts_markup_local(language: str) -> InlineKeyboardMarkup:
    def amount_label(amount: int) -> str:
        return f"{amount:,} {_money_unit(language)}".replace(",", " ")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=amount_label(80000), callback_data="topup:amount:80000")],
            [InlineKeyboardButton(text=amount_label(150000), callback_data="topup:amount:150000")],
            [InlineKeyboardButton(text=amount_label(200000), callback_data="topup:amount:200000")],
            [InlineKeyboardButton(text=_topup_other_amount_text(language), callback_data="topup:amount:custom")],
            [InlineKeyboardButton(text=_back_text(language), callback_data="menu:profile", style="danger")],
            [InlineKeyboardButton(text=_menu_text(language), callback_data="menu:main")],
        ]
    )


def _topup_methods_markup_local(language: str, amount: Decimal | int | str) -> InlineKeyboardMarkup:
    amount_value = str(int(Decimal(str(amount))))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Click", callback_data=f"topup:method:{amount_value}:click")],
            [InlineKeyboardButton(text="Humo / Uzcard", callback_data=f"topup:method:{amount_value}:card")],
            [InlineKeyboardButton(text=_topup_crypto_text(language), callback_data=f"topup:method:{amount_value}:usdt_trc20")],
            [InlineKeyboardButton(text=_back_text(language), callback_data="profile:topup", style="danger")],
            [InlineKeyboardButton(text=_menu_text(language), callback_data="menu:main")],
        ]
    )


def _topup_receipt_markup_local(language: str, amount: Decimal | int | str) -> InlineKeyboardMarkup:
    amount_value = str(int(Decimal(str(amount))))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_back_text(language), callback_data=f"topup:back:{amount_value}", style="danger")],
            [InlineKeyboardButton(text=_menu_text(language), callback_data="menu:main")],
        ]
    )


def _balance_tx_label(tx_type: str, language: str) -> str:
    if language == "uz":
        mapping = {
            "topup": "✅ To'ldirish",
            "purchase": "🛒 Xarid",
            "refund": "↩️ Qaytarish",
            "admin_adjustment": "🛠 Tuzatish",
        }
    elif language == "en":
        mapping = {
            "topup": "✅ Top up",
            "purchase": "🛒 Purchase",
            "refund": "↩️ Refund",
            "admin_adjustment": "🛠 Adjustment",
        }
    else:
        mapping = {
            "topup": "✅ Пополнение",
            "purchase": "🛒 Покупка",
            "refund": "↩️ Возврат",
            "admin_adjustment": "🛠 Корректировка",
        }
    return mapping.get(tx_type, tx_type)


def _profile_text(user, orders_count: int, language: str) -> str:
    username = f"@{user.username.lstrip('@')}" if (user.username or "").strip() else "—"
    if language == "uz":
        return (
            "<b>👤 Profilingiz</b>\n\n"
            f"🆔 ID: <code>{user.telegram_id}</code>\n"
            f"👤 Username: {escape(username)}\n"
            f"💰 Balans: {_sum_text(user.balance, language)}\n"
            f"🛒 Xaridlar: {orders_count}\n"
            f"📅 Ro'yxatdan o'tgan sana: {format_datetime_local(user.created_at)}"
        )
    if language == "en":
        return (
            "<b>👤 Your profile</b>\n\n"
            f"🆔 ID: <code>{user.telegram_id}</code>\n"
            f"👤 Username: {escape(username)}\n"
            f"💰 Balance: {_sum_text(user.balance, language)}\n"
            f"🛒 Purchases: {orders_count}\n"
            f"📅 Registered: {format_datetime_local(user.created_at)}"
        )
    return (
        "<b>👤 Ваш профиль</b>\n\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"👤 Username: {escape(username)}\n"
        f"💰 Баланс: {_sum_text(user.balance, language)}\n"
        f"🛒 Покупок: {orders_count}\n"
        f"📅 Регистрация: {format_datetime_local(user.created_at)}"
    )


def _orders_markup(orders: list, language: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{order_display_number(order)} • {order.product_name_snapshot}", callback_data=f"order:detail:{order.id}")]
        for order in orders
    ]
    rows.append([InlineKeyboardButton(text=_back_text(language), callback_data="menu:profile", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _notify_admins_about_topup(
    bot: Bot,
    app: AppContext,
    *,
    topup,
    user,
    payment_title_text: str,
    receipt_file_id: str,
    receipt_file_type: str,
) -> None:
    caption = (
        "🆕 Новая заявка на пополнение\n\n"
        f"👤 Пользователь: @{user.username or 'нет'}\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"💰 Сумма: {format_money(topup.amount, 'сум').replace(' сум', '')} сум\n"
        f"💳 Способ: {escape(payment_title_text)}\n"
        "⏳ Статус: Ожидает проверки\n\n"
        "Проверьте оплату и выберите действие."
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin:topup:approve:{topup.id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:topup:reject:{topup.id}", style="danger")],
            [InlineKeyboardButton(text="👤 Профиль клиента", callback_data=f"admin:user:view:{user.id}")],
        ]
    )
    for admin_id in app.settings.admin_ids:
        try:
            if receipt_file_type == "photo":
                await bot.send_photo(admin_id, photo=receipt_file_id, caption=caption, reply_markup=markup)
            else:
                await bot.send_document(admin_id, document=receipt_file_id, caption=caption, reply_markup=markup)
        except Exception:
            continue


def _topup_start_text(language: str) -> str:
    if language == "uz":
        return "<b>💳 Balansni to'ldirish</b>\n\nTo'ldirish summasini tanlang:"
    if language == "en":
        return "<b>💳 Top up balance</b>\n\nChoose a top-up amount:"
    return "<b>💳 Пополнение баланса</b>\n\nВыберите сумму пополнения:"


def _topup_custom_prompt_text(language: str) -> str:
    if language == "uz":
        return f"To'ldirish summasini kiriting. Minimal summa: {_sum_text(MIN_TOPUP_AMOUNT, language)}."
    if language == "en":
        return f"Enter the top-up amount. Minimum amount: {_sum_text(MIN_TOPUP_AMOUNT, language)}."
    return f"Введите сумму пополнения. Минимальная сумма: {_sum_text(MIN_TOPUP_AMOUNT, language)}."


def _topup_method_select_text(language: str, amount: Decimal | int | str) -> str:
    amount_text = _sum_text(amount, language)
    if language == "uz":
        return f"<b>💳 To'lov usulini tanlang</b>\n\nTo'ldirish summasi:\n{amount_text}"
    if language == "en":
        return f"<b>💳 Choose a payment method</b>\n\nTop-up amount:\n{amount_text}"
    return f"<b>💳 Выберите способ оплаты</b>\n\nСумма пополнения:\n{amount_text}"


def _topup_amount_invalid_text(language: str) -> str:
    if language == "uz":
        return "Summani butun son bilan kiriting."
    if language == "en":
        return "Enter the amount as a whole number."
    return "Введите сумму целым числом."


def _topup_amount_min_text(language: str) -> str:
    if language == "uz":
        return f"❌ Minimal to'ldirish summasi: {_sum_text(MIN_TOPUP_AMOUNT, language)}."
    if language == "en":
        return f"❌ The minimum top-up amount is {_sum_text(MIN_TOPUP_AMOUNT, language)}."
    return f"❌ Минимальная сумма пополнения: {_sum_text(MIN_TOPUP_AMOUNT, language)}."


def _topup_payment_text(language: str, payment_name: str, amount: Decimal | int | str, instruction: str) -> str:
    amount_text = _sum_text(amount, language)
    if language == "uz":
        return (
            f"<b>💳 {escape(payment_name)} orqali to'lov</b>\n\n"
            f"Summa: {amount_text}\n\n"
            f"{instruction}\n\n"
            "To'lovdan keyin chek yoki skrinshotni shu yerga yuboring."
        )
    if language == "en":
        return (
            f"<b>💳 Payment via {escape(payment_name)}</b>\n\n"
            f"Amount: {amount_text}\n\n"
            f"{instruction}\n\n"
            "After payment, send the receipt or screenshot here."
        )
    return (
        f"<b>💳 Оплата через {escape(payment_name)}</b>\n\n"
        f"Сумма: {amount_text}\n\n"
        f"{instruction}\n\n"
        "После оплаты отправьте чек или скриншот сюда."
    )


def _topup_payment_method_name(method_code: str, fallback: str, language: str) -> str:
    normalized = (method_code or "").strip().lower()
    if normalized == "click":
        return "Click"
    if normalized == "card":
        return "Humo / Uzcard"
    if normalized == "usdt_trc20":
        if language == "uz":
            return "Kriptovalyuta"
        if language == "en":
            return "Cryptocurrency"
        return "Криптовалюта"
    return fallback


def _topup_click_text(language: str, amount: Decimal | int | str) -> str:
    amount_text = _sum_text(amount, language)
    if language == "uz":
        return (
            "<b>💳 Click orqali to'lov</b>\n\n"
            f"Summa: {amount_text}\n\n"
            "To'lov uchun:\n"
            "1. Click ilovasini oching\n"
            "2. QR kodni skaner qiling\n"
            f"3. {amount_text} summani kiriting\n"
            "4. To'lovni tasdiqlang\n\n"
            "To'lovdan keyin chekni ushbu botga yuboring."
        )
    if language == "en":
        return (
            "<b>💳 Payment via Click</b>\n\n"
            f"Amount: {amount_text}\n\n"
            "To pay:\n"
            "1. Open Click\n"
            "2. Scan the QR code\n"
            f"3. Enter the amount {amount_text}\n"
            "4. Confirm the payment\n\n"
            "After payment, send the receipt to this bot."
        )
    return (
        "<b>💳 Оплата через Click</b>\n\n"
        f"Сумма: {amount_text}\n\n"
        "Для оплаты:\n"
        "1. Откройте Click\n"
        "2. Отсканируйте Qrcod\n"
        f"3. Ведите сумму {amount_text}\n"
        "4. Подтвердите оплату\n\n"
        "После оплаты отправьте чек в этот бот."
    )


def _topup_receipt_invalid_text(language: str) -> str:
    if language == "uz":
        return "Chekni rasm yoki hujjat sifatida yuboring."
    if language == "en":
        return "Send the receipt as a photo or document."
    return "Отправьте чек фотографией или документом."


def _history_title_text(language: str) -> str:
    if language == "uz":
        return "<b>📜 Balans tarixi</b>"
    if language == "en":
        return "<b>📜 Balance history</b>"
    return "<b>📜 История баланса</b>"


def _history_empty_text(language: str) -> str:
    if language == "uz":
        return "Hozircha operatsiyalar yo'q."
    if language == "en":
        return "No transactions yet."
    return "Операций пока нет."


def _history_current_balance_text(language: str, balance: Decimal | int | float | str) -> str:
    if language == "uz":
        return f"Joriy balans: {_sum_text(balance, language)}"
    if language == "en":
        return f"Current balance: {_sum_text(balance, language)}"
    return f"Текущий баланс: {_sum_text(balance, language)}"


def _orders_title_text(language: str) -> str:
    if language == "uz":
        return "<b>📦 Buyurtmalaringiz</b>"
    if language == "en":
        return "<b>📦 Your orders</b>"
    return "<b>📦 Ваши заказы</b>"


def _orders_empty_text(language: str) -> str:
    if language == "uz":
        return "<b>📦 Buyurtmalaringiz</b>\n\nBuyurtmalar hozircha yo'q."
    if language == "en":
        return "<b>📦 Your orders</b>\n\nNo orders yet."
    return "<b>📦 Ваши заказы</b>\n\nЗаказов пока нет."


def _order_not_found_text(language: str) -> str:
    if language == "uz":
        return "Buyurtma topilmadi."
    if language == "en":
        return "Order not found."
    return "Заказ не найден."


def _order_details_caption(language: str) -> str:
    if language == "uz":
        return "Buyurtma ma'lumotlari:"
    if language == "en":
        return "Order details:"
    return "Данные по заказу:"


def _topup_state_missing_text(language: str) -> str:
    if language == "uz":
        return "To'ldirish ma'lumotlari topilmadi. Profil orqali qaytadan boshlang."
    if language == "en":
        return "Top-up data was not found. Please start again from your profile."
    return "Данные пополнения не найдены. Начните заново из профиля."


def _topup_create_failed_text(language: str) -> str:
    if language == "uz":
        return "To'ldirish so'rovini yaratib bo'lmadi."
    if language == "en":
        return "Failed to create the top-up request."
    return "Не удалось создать заявку на пополнение."


def _topup_created_text(language: str, amount: Decimal | int | float | str, payment_name: str) -> str:
    amount_text = _sum_text(amount, language)
    if language == "uz":
        return (
            "✅ To'ldirish so'rovi yaratildi\n\n"
            f"💰 Summa: {amount_text}\n"
            f"💳 Usul: {payment_name}\n"
            "⏳ Holat: Tekshirilmoqda\n\n"
            "Administrator to'lovni tekshiradi va balansni to'ldiradi."
        )
    if language == "en":
        return (
            "✅ Top-up request created\n\n"
            f"💰 Amount: {amount_text}\n"
            f"💳 Method: {payment_name}\n"
            "⏳ Status: Pending review\n\n"
            "An administrator will review the payment and credit your balance."
        )
    return (
        "✅ Заявка на пополнение создана\n\n"
        f"💰 Сумма: {amount_text}\n"
        f"💳 Способ: {payment_name}\n"
        "⏳ Статус: Ожидает проверки\n\n"
        "Администратор проверит оплату и зачислит баланс."
    )


def build_profile_router(app: AppContext, bot: Bot) -> Router:
    router = Router(name="profile")

    @router.callback_query(F.data == "menu:profile")
    async def profile_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user is None:
                await callback.answer()
                return
            orders_count = await count_orders_for_user(session, user.id)
        await callback.answer()
        await answer_or_edit(
            callback,
            _profile_text(user, orders_count, language),
            reply_markup=profile_markup(language, app.settings.support_url),
        )

    @router.callback_query(F.data == "profile:promo")
    async def profile_promo_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            prompt = await format_text(session, "user.promo_enter", language, fallback="Введите промокод.")
        await state.set_state(UserFlowState.waiting_promo_code)
        await state.update_data(promo_return="profile")
        await callback.answer()
        await answer_or_edit(
            callback,
            prompt,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="menu:profile", style="danger")]]
            ),
        )

    @router.callback_query(F.data == "profile:topup")
    async def profile_topup_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            "<b>💳 Пополнение баланса</b>\n\nВыберите сумму пополнения:",
            reply_markup=topup_amounts_markup(language),
        )

    @router.callback_query(F.data.startswith("topup:amount:"))
    async def topup_amount_handler(callback: CallbackQuery, state: FSMContext) -> None:
        amount_token = callback.data.split(":")[-1]
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        if amount_token == "custom":
            await state.set_state(UserFlowState.waiting_topup_custom_amount)
            await callback.answer()
            await answer_or_edit(
                callback,
                "Введите сумму пополнения в сумах:",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="profile:topup", style="danger")]]
                ),
            )
            return
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            f"<b>💳 Выберите способ оплаты</b>\n\nСумма пополнения:\n{int(amount_token):,} сум".replace(",", " "),
            reply_markup=topup_methods_markup(language, amount_token),
        )

    @router.message(UserFlowState.waiting_topup_custom_amount)
    async def topup_custom_amount_handler(message: Message, state: FSMContext) -> None:
        raw_value = (message.text or "").replace(" ", "").strip()
        if not raw_value.isdigit() or int(raw_value) <= 0:
            await message.answer("Введите сумму целым числом в сумах.")
            return
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
        await state.clear()
        await message.answer(
            f"<b>💳 Выберите способ оплаты</b>\n\nСумма пополнения:\n{int(raw_value):,} сум".replace(",", " "),
            reply_markup=topup_methods_markup(language, raw_value),
        )

    @router.callback_query(F.data.startswith("topup:method:"))
    async def topup_method_handler(callback: CallbackQuery, state: FSMContext) -> None:
        _, _, amount_value, method_code = callback.data.split(":")
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            payment_method = await get_payment_method_by_code(session, method_code)
            if payment_method is None:
                await callback.answer("Способ оплаты не найден.", show_alert=True)
                return
            instruction = payment_instruction(payment_method, language)
            payment_name = payment_title(payment_method, language)
        await state.set_state(UserFlowState.waiting_topup_receipt)
        await state.update_data(topup_amount=amount_value, topup_method=method_code)
        await callback.answer()
        await answer_or_edit(
            callback,
            f"<b>💳 Оплата через {escape(payment_name)}</b>\n\n"
            f"Сумма: {int(amount_value):,} сум\n\n".replace(",", " ")
            + instruction
            + "\n\nПосле оплаты отправьте чек или скриншот сюда.",
            reply_markup=topup_receipt_markup(language, amount_value),
        )

    @router.callback_query(F.data.startswith("topup:back:"))
    async def topup_back_handler(callback: CallbackQuery, state: FSMContext) -> None:
        amount_value = callback.data.split(":")[-1]
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            f"<b>💳 Выберите способ оплаты</b>\n\nСумма пополнения:\n{int(amount_value):,} сум".replace(",", " "),
            reply_markup=topup_methods_markup(language, amount_value),
        )

    @router.message(UserFlowState.waiting_topup_receipt, F.photo)
    async def topup_receipt_photo_handler(message: Message, state: FSMContext) -> None:
        await _handle_topup_receipt(message, state, app, bot, file_id=message.photo[-1].file_id, file_type="photo")

    @router.message(UserFlowState.waiting_topup_receipt, F.document)
    async def topup_receipt_document_handler(message: Message, state: FSMContext) -> None:
        await _handle_topup_receipt(message, state, app, bot, file_id=message.document.file_id, file_type="document")

    @router.message(UserFlowState.waiting_topup_receipt)
    async def topup_receipt_invalid_handler(message: Message) -> None:
        await message.answer("Отправьте чек фотографией или документом.")

    @router.callback_query(F.data == "profile:history")
    async def profile_history_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user is None:
                await callback.answer()
                return
            history = await list_balance_transactions(session, user.id, limit=10)
        lines = ["<b>📜 История баланса</b>", ""]
        if not history:
            lines.append("Операций пока нет.")
        else:
            for index, item in enumerate(history, start=1):
                amount_text = format_money(abs(item.amount), "сум").replace(" сум", "")
                sign = "+" if Decimal(str(item.amount)) >= 0 else "-"
                lines.append(f"{index}. {_balance_tx_label(item.type.value)}: {sign}{amount_text} сум")
        lines.append("")
        lines.append(f"Текущий баланс: {format_money(user.balance, 'сум').replace(' сум', '')} сум")
        await callback.answer()
        await answer_or_edit(
            callback,
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="menu:profile", style="danger")]]
            ),
        )

    @router.callback_query(F.data == "profile:orders")
    async def profile_orders_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user is None:
                await callback.answer()
                return
            orders = await list_orders_for_user(session, user.id, limit=20)
        if not orders:
            await callback.answer()
            await answer_or_edit(
                callback,
                "<b>📦 Ваши заказы</b>\n\nЗаказов пока нет.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="menu:profile", style="danger")]]
                ),
            )
            return
        await callback.answer()
        await answer_or_edit(callback, "<b>📦 Ваши заказы</b>", reply_markup=_orders_markup(orders, "ru"))

    @router.callback_query(F.data.startswith("order:detail:"))
    async def order_detail_handler(callback: CallbackQuery) -> None:
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user is None:
                await callback.answer()
                return
            order = await get_order_by_id(session, order_id)
        await callback.answer()
        if order is None or order.user_id != user.id:
            await answer_or_edit(callback, "Заказ не найден.")
            return
        lines = [
            f"<b>{order_display_number(order)}</b>",
            f"💎 {escape(order.service_name_snapshot or order.product_name_snapshot)}",
            f"📦 {escape(order.product_type_snapshot or '-')}",
            f"💰 {format_money(order.amount, order.currency)}",
            f"⏳ {order_status_label(order.status.value, language)}",
        ]
        if (order.delivery_content or "").strip():
            lines.extend(["", "Данные по заказу:", escape(order.delivery_content)])
        await answer_or_edit(
            callback,
            "\n".join(lines),
            reply_markup=order_detail_markup(order, language, app.settings.support_url),
        )

    return router


async def _handle_topup_receipt(
    message: Message,
    state: FSMContext,
    app: AppContext,
    bot: Bot,
    *,
    file_id: str,
    file_type: str,
) -> None:
    data = await state.get_data()
    amount_value = data.get("topup_amount")
    method_code = data.get("topup_method")
    if not amount_value or not method_code:
        await message.answer("Данные пополнения не найдены. Начните заново из профиля.")
        await state.clear()
        return

    async with app.session_factory() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        language = await get_user_language(session, message.from_user.id, app.settings.default_language)
        payment_method = await get_payment_method_by_code(session, method_code)
        if user is None or payment_method is None:
            await message.answer("Не удалось создать заявку на пополнение.")
            await state.clear()
            return
        topup = await create_topup(
            session,
            user=user,
            amount=amount_value,
            payment_method=payment_method.code,
            receipt_file_id=file_id,
            receipt_file_type=file_type,
        )
        await session.commit()
        payment_name = payment_title(payment_method, language)

    await state.clear()
    await message.answer(
        "✅ Заявка на пополнение создана\n\n"
        f"💰 Сумма: {int(amount_value):,} сум\n".replace(",", " ")
        + f"💳 Способ: {payment_name}\n"
        + "⏳ Статус: Ожидает проверки\n\n"
        + "Администратор проверит оплату и зачислит баланс.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")]]
        ),
    )
    await _notify_admins_about_topup(
        bot,
        app,
        topup=topup,
        user=user,
        payment_title_text=payment_name,
        receipt_file_id=file_id,
        receipt_file_type=file_type,
    )


def build_profile_router(app: AppContext, bot: Bot) -> Router:
    router = Router(name="profile")

    @router.callback_query(F.data == "menu:profile")
    async def profile_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user is None:
                await callback.answer()
                return
            orders_count = await count_orders_for_user(session, user.id)
        await callback.answer()
        await answer_or_edit(
            callback,
            _profile_text(user, orders_count, language),
            reply_markup=profile_markup(language, app.settings.support_url),
        )

    @router.callback_query(F.data == "profile:promo")
    async def profile_promo_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            prompt = await format_text(session, "user.promo_enter", language, fallback="Введите промокод.")
        await state.set_state(UserFlowState.waiting_promo_code)
        await state.update_data(promo_return="profile")
        await callback.answer()
        await answer_or_edit(
            callback,
            prompt,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=_back_text(language), callback_data="menu:profile", style="danger")]]
            ),
        )

    @router.callback_query(F.data == "profile:topup")
    async def profile_topup_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            _topup_start_text(language),
            reply_markup=_topup_amounts_markup_local(language),
        )

    @router.callback_query(F.data.startswith("topup:amount:"))
    async def topup_amount_handler(callback: CallbackQuery, state: FSMContext) -> None:
        amount_token = callback.data.split(":")[-1]
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        if amount_token == "custom":
            await state.set_state(UserFlowState.waiting_topup_custom_amount)
            await callback.answer()
            await answer_or_edit(
                callback,
                _topup_custom_prompt_text(language),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text=_back_text(language), callback_data="profile:topup", style="danger")]]
                ),
            )
            return
        if not amount_token.isdigit() or Decimal(amount_token) < MIN_TOPUP_AMOUNT:
            await callback.answer(_topup_amount_min_text(language), show_alert=True)
            return
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            _topup_method_select_text(language, amount_token),
            reply_markup=_topup_methods_markup_local(language, amount_token),
        )

    @router.message(UserFlowState.waiting_topup_custom_amount)
    async def topup_custom_amount_handler(message: Message, state: FSMContext) -> None:
        raw_value = (message.text or "").replace(" ", "").strip()
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
        if not raw_value.isdigit() or int(raw_value) <= 0:
            await message.answer(_topup_amount_invalid_text(language))
            return
        if Decimal(raw_value) < MIN_TOPUP_AMOUNT:
            await message.answer(_topup_amount_min_text(language))
            return
        await state.clear()
        await message.answer(
            _topup_method_select_text(language, raw_value),
            reply_markup=_topup_methods_markup_local(language, raw_value),
        )

    @router.callback_query(F.data.startswith("topup:method:"))
    async def topup_method_handler(callback: CallbackQuery, state: FSMContext) -> None:
        _, _, amount_value, method_code = callback.data.split(":")
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            if not amount_value.isdigit() or Decimal(amount_value) < MIN_TOPUP_AMOUNT:
                await callback.answer(_topup_amount_min_text(language), show_alert=True)
                return
            payment_method = await get_payment_method_by_code(session, method_code)
            if payment_method is None:
                error_text = "Payment method not found." if language == "en" else ("To'lov usuli topilmadi." if language == "uz" else "Способ оплаты не найден.")
                await callback.answer(error_text, show_alert=True)
                return
            instruction = payment_instruction(payment_method, language)
            payment_name = _topup_payment_method_name(
                method_code,
                payment_title(payment_method, language),
                language,
            )
        await state.set_state(UserFlowState.waiting_topup_receipt)
        await state.update_data(topup_amount=amount_value, topup_method=method_code)
        await callback.answer()
        if method_code == "click" and CLICK_QR_IMAGE_PATH.exists():
            if callback.message is not None:
                try:
                    await callback.message.delete()
                except Exception:
                    pass
            await bot.send_photo(
                callback.from_user.id,
                photo=FSInputFile(str(CLICK_QR_IMAGE_PATH)),
                caption=_topup_click_text(language, amount_value),
                reply_markup=_topup_receipt_markup_local(language, amount_value),
            )
            return
        await answer_or_edit(
            callback,
            _topup_payment_text(language, payment_name, amount_value, instruction),
            reply_markup=_topup_receipt_markup_local(language, amount_value),
        )

    @router.callback_query(F.data.startswith("topup:back:"))
    async def topup_back_handler(callback: CallbackQuery, state: FSMContext) -> None:
        amount_value = callback.data.split(":")[-1]
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        await state.clear()
        if not amount_value.isdigit() or Decimal(amount_value) < MIN_TOPUP_AMOUNT:
            await callback.answer()
            await answer_or_edit(
                callback,
                _topup_start_text(language),
                reply_markup=_topup_amounts_markup_local(language),
            )
            return
        await callback.answer()
        await answer_or_edit(
            callback,
            _topup_method_select_text(language, amount_value),
            reply_markup=_topup_methods_markup_local(language, amount_value),
        )

    @router.message(UserFlowState.waiting_topup_receipt, F.photo)
    async def topup_receipt_photo_handler(message: Message, state: FSMContext) -> None:
        await _handle_topup_receipt(message, state, app, bot, file_id=message.photo[-1].file_id, file_type="photo")

    @router.message(UserFlowState.waiting_topup_receipt, F.document)
    async def topup_receipt_document_handler(message: Message, state: FSMContext) -> None:
        await _handle_topup_receipt(message, state, app, bot, file_id=message.document.file_id, file_type="document")

    @router.message(UserFlowState.waiting_topup_receipt)
    async def topup_receipt_invalid_handler(message: Message) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
        await message.answer(_topup_receipt_invalid_text(language))

    @router.callback_query(F.data == "profile:history")
    async def profile_history_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user is None:
                await callback.answer()
                return
            history = await list_balance_transactions(session, user.id, limit=10)
        lines = [_history_title_text(language), ""]
        if not history:
            lines.append(_history_empty_text(language))
        else:
            for index, item in enumerate(history, start=1):
                amount_text = _sum_text(abs(item.amount), language)
                sign = "+" if Decimal(str(item.amount)) >= 0 else "-"
                lines.append(f"{index}. {_balance_tx_label(item.type.value, language)}: {sign}{amount_text}")
        lines.append("")
        lines.append(_history_current_balance_text(language, user.balance))
        await callback.answer()
        await answer_or_edit(
            callback,
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=_back_text(language), callback_data="menu:profile", style="danger")]]
            ),
        )

    @router.callback_query(F.data == "profile:orders")
    async def profile_orders_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user is None:
                await callback.answer()
                return
            orders = await list_orders_for_user(session, user.id, limit=20)
        if not orders:
            await callback.answer()
            await answer_or_edit(
                callback,
                _orders_empty_text(language),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text=_back_text(language), callback_data="menu:profile", style="danger")]]
                ),
            )
            return
        await callback.answer()
        await answer_or_edit(callback, _orders_title_text(language), reply_markup=_orders_markup(orders, language))

    @router.callback_query(F.data.startswith("order:detail:"))
    async def order_detail_handler(callback: CallbackQuery) -> None:
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user is None:
                await callback.answer()
                return
            order = await get_order_by_id(session, order_id)
        await callback.answer()
        if order is None or order.user_id != user.id:
            await answer_or_edit(callback, _order_not_found_text(language))
            return
        lines = [
            f"<b>{order_display_number(order)}</b>",
            f"💎 {escape(order.service_name_snapshot or order.product_name_snapshot)}",
            f"📦 {escape(order.product_type_snapshot or '-')}",
            f"💰 {format_money(order.amount, order.currency)}",
            f"⏳ {order_status_label(order.status.value, language)}",
        ]
        if (order.delivery_content or "").strip():
            lines.extend(["", _order_details_caption(language), escape(order.delivery_content)])
        await answer_or_edit(
            callback,
            "\n".join(lines),
            reply_markup=order_detail_markup(order, language, app.settings.support_url),
        )

    return router


async def _handle_topup_receipt(
    message: Message,
    state: FSMContext,
    app: AppContext,
    bot: Bot,
    *,
    file_id: str,
    file_type: str,
) -> None:
    data = await state.get_data()
    amount_value = data.get("topup_amount")
    method_code = data.get("topup_method")
    async with app.session_factory() as session:
        language = await get_user_language(session, message.from_user.id, app.settings.default_language)
        if not amount_value or not method_code:
            await message.answer(_topup_state_missing_text(language))
            await state.clear()
            return
        if not str(amount_value).isdigit() or Decimal(str(amount_value)) < MIN_TOPUP_AMOUNT:
            await message.answer(_topup_amount_min_text(language))
            await state.clear()
            return
        user = await get_user_by_telegram_id(session, message.from_user.id)
        payment_method = await get_payment_method_by_code(session, method_code)
        if user is None or payment_method is None:
            await message.answer(_topup_create_failed_text(language))
            await state.clear()
            return
        topup = await create_topup(
            session,
            user=user,
            amount=amount_value,
            payment_method=payment_method.code,
            receipt_file_id=file_id,
            receipt_file_type=file_type,
        )
        await session.commit()
        payment_name = _topup_payment_method_name(
            payment_method.code,
            payment_title(payment_method, language),
            language,
        )

    await state.clear()
    await message.answer(
        _topup_created_text(language, amount_value, payment_name),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=_menu_text(language), callback_data="menu:main")]]
        ),
    )
    await _notify_admins_about_topup(
        bot,
        app,
        topup=topup,
        user=user,
        payment_title_text=payment_name,
        receipt_file_id=file_id,
        receipt_file_type=file_type,
    )
