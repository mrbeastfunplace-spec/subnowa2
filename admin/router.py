from __future__ import annotations

from decimal import Decimal, InvalidOperation
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select

from db.base import BalanceTransactionType, ButtonActionType, Language, OrderStatus, PaymentProviderType, ProductStatus, TopupStatus
from db.models import (
    CapCutAccount,
    Category,
    InventoryItem,
    Layout,
    LayoutButton,
    LayoutButtonTranslation,
    Order,
    PaymentMethod,
    PaymentMethodTranslation,
    Product,
    ProductPaymentMethod,
    ProductTranslation,
    TextEntry,
    TextTranslation,
    Topup,
    User,
)
from services.admin import build_stats_text
from services.balance import apply_admin_adjustment, credit_balance
from services.buttons import build_layout_markup, get_button, get_layout, list_layouts
from services.capcut import add_bulk_accounts, add_capcut_account, claim_free_account, count_free_accounts, list_accounts, purge_expired_accounts
from services.catalog import category_name, get_category, get_product, product_name, product_type_label, service_name
from services.chatgpt_invite_service import start_chatgpt_business_order
from services.context import AppContext
from services.inventory import (
    add_inventory_item,
    get_inventory_item,
    get_inventory_summary,
    list_inventory_items,
    list_inventory_products,
    soft_delete_inventory_item,
)
from services.orders import change_status, complete_order_delivery, get_order_by_id, get_order_by_reference, list_orders
from services.payments import get_payment_method, payment_title, toggle_product_payment_method
from services.purchases import refund_order
from services.texts import format_text
from services.topups import approve_topup, get_topup_by_id, list_pending_topups, reject_topup
from services.users import count_orders_for_user, find_users, get_user_by_id, get_user_language
from states import AdminState
from utils.formatting import format_datetime_local, format_money, order_display_number, order_status_label, user_display_name
from utils.messages import answer_or_edit
from utils.translations import pick_translation


def build_admin_router(app: AppContext, bot: Bot) -> Router:
    router = Router(name="admin")
    live_layout_codes = {"main_menu", "admin_main"}

    def _guard(user_id: int) -> bool:
        return app.is_admin(user_id)

    def _back_main_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Назад в админку", callback_data="admin:main")]]
        )

    def _parse_amount(value: str | None) -> Decimal | None:
        raw = (value or "").replace(" ", "").replace(",", ".").strip()
        if not raw:
            return None
        try:
            amount = Decimal(raw).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return None
        if amount <= 0:
            return None
        return amount

    async def _render_admin_main(target: Message | CallbackQuery) -> None:
        async with app.session_factory() as session:
            markup = await build_layout_markup(session, "admin_main", "ru")
            title = await format_text(session, "admin.panel_title", "ru", fallback="Админ-панель")
        await answer_or_edit(target, f"<b>{title}</b>", reply_markup=markup)

    def _admin_user_text(user: User, orders_count: int) -> str:
        username = f"@{user.username.lstrip('@')}" if (user.username or "").strip() else "—"
        return (
            "<b>👤 Профиль клиента</b>\n\n"
            f"🆔 ID: <code>{user.telegram_id}</code>\n"
            f"👤 Username: {escape(username)}\n"
            f"💰 Баланс: {format_money(user.balance, 'сум')}\n"
            f"🛒 Покупок: {orders_count}\n"
            f"📅 Регистрация: {format_datetime_local(user.created_at)}"
        )

    def _admin_user_markup(user_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить баланс", callback_data=f"admin:user:adjust:{user_id}:add")],
                [InlineKeyboardButton(text="➖ Списать баланс", callback_data=f"admin:user:adjust:{user_id}:subtract")],
                [InlineKeyboardButton(text="💬 Написать клиенту", callback_data=f"admin:user:message:{user_id}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:users")],
            ]
        )

    def _topup_view_markup(topup: Topup, pending_ids: list[int], index: int) -> InlineKeyboardMarkup:
        rows = [
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin:topup:approve:{topup.id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:topup:reject:{topup.id}", style="danger")],
        ]
        if topup.user_id:
            rows.append([InlineKeyboardButton(text="👤 Профиль клиента", callback_data=f"admin:user:view:{topup.user_id}")])
        if index + 1 < len(pending_ids):
            rows.append([InlineKeyboardButton(text="➡️ Следующая", callback_data=f"admin:topups:show:{index + 1}")])
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:main")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _render_topup_text(topup: Topup, index: int, total: int) -> str:
        username = f"@{topup.user.username}" if topup.user and (topup.user.username or "").strip() else "—"
        telegram_id = topup.user.telegram_id if topup.user else "-"
        return (
            f"<b>📥 Заявка #{topup.id}</b>\n\n"
            f"👤 Пользователь: {escape(username)}\n"
            f"🆔 ID: <code>{telegram_id}</code>\n"
            f"💰 Сумма: {format_money(topup.amount, 'сум')}\n"
            f"💳 Способ: {escape(topup.payment_method or '-')}\n"
            "⏳ Статус: Ожидает проверки\n"
            f"🕒 Дата: {format_datetime_local(topup.created_at)}\n\n"
            f"{index + 1} из {total}"
        )

    def _inventory_products_markup(products: list[Product]) -> InlineKeyboardMarkup:
        rows = [
            [InlineKeyboardButton(text=service_name(product, "ru"), callback_data=f"admin:inventory:product:{product.id}")]
            for product in products
        ]
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:main")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _inventory_product_markup(product_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить доступ", callback_data=f"admin:inventory:add:{product_id}")],
                [InlineKeyboardButton(text="📋 Список доступов", callback_data=f"admin:inventory:list:{product_id}")],
                [InlineKeyboardButton(text="🗑 Удалить доступ", callback_data=f"admin:inventory:delete_list:{product_id}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:inventory")],
            ]
        )

    def _inventory_delete_markup(product_id: int, items: list[InventoryItem]) -> InlineKeyboardMarkup:
        rows = [
            [InlineKeyboardButton(text=f"#{item.id} • {(item.title or 'Доступ')[:32]}", callback_data=f"admin:inventory:delete:{item.id}")]
            for item in items
        ]
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin:inventory:product:{product_id}")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _render_order_text(order: Order) -> str:
        details = order.details or {}
        display_name = escape(user_display_name(order.user))
        telegram_id = order.user.telegram_id if order.user else "-"
        return (
            f"<b>🛒 Заказ {order_display_number(order)}</b>\n\n"
            f"👤 Клиент: <b>{display_name}</b>\n"
            f"🆔 ID: <code>{telegram_id}</code>\n"
            f"💎 Сервис: {escape(order.service_name_snapshot or order.product_name_snapshot or 'Заказ')}\n"
            f"📦 Тип: {escape(order.product_type_snapshot or order.delivery_type or '-')}\n"
            f"💰 Оплачено: <b>{format_money(order.amount, order.currency)}</b>\n"
            f"⏳ Статус: <b>{order_status_label(order.status.value, 'ru')}</b>\n"
            f"🕒 Дата: {format_datetime_local(order.created_at)}\n"
            f"💳 Метод оплаты: {escape(order.payment_method.admin_title) if order.payment_method else '-'}\n"
            f"Gmail: {escape(str(details.get('gmail', '-')))}\n"
            f"Комментарий: {escape(order.customer_note or '-')}"
        )
        return (
            f"<b>{escape(order.product_name_snapshot or 'Заказ')}</b>\n\n"
            f"Номер: <code>{order_display_number(order)}</code>\n"
            f"Код: <code>{order.order_number}</code>\n"
            f"Пользователь: <b>{display_name}</b>\n"
            f"Telegram ID: <code>{telegram_id}</code>\n"
            f"Статус: <b>{order_status_label(order.status.value, 'ru')}</b>\n"
            f"Сумма: <b>{format_money(order.amount, order.currency)}</b>\n"
            f"Метод оплаты: {escape(order.payment_method.admin_title) if order.payment_method else '-'}\n"
            f"Тип выдачи: {escape(order.delivery_type)}\n"
            f"Gmail: {escape(str(details.get('gmail', '-')))}\n"
            f"Комментарий: {escape(order.customer_note or '-')}"
        )

    def _order_actions_markup(order: Order) -> InlineKeyboardMarkup:
        rows: list[list[InlineKeyboardButton]] = []
        if order.status in {OrderStatus.WAITING_CHECK, OrderStatus.PENDING_PAYMENT, OrderStatus.FAILED}:
            rows.append([InlineKeyboardButton(text="Подтвердить", callback_data=f"admin:approve:{order.id}")])
            rows.append([InlineKeyboardButton(text="Отклонить", callback_data=f"admin:reject:{order.id}")])
        if order.status in {OrderStatus.PAID, OrderStatus.PROCESSING, OrderStatus.WAITING}:
            rows.append([InlineKeyboardButton(text="✅ Выполнить", callback_data=f"admin:order:deliver:{order.id}")])
            rows.append([InlineKeyboardButton(text="❌ Отменить с возвратом", callback_data=f"admin:order:refund:{order.id}", style="danger")])
            rows.append([InlineKeyboardButton(text="💬 Написать клиенту", callback_data=f"admin:order:message:{order.id}")])
            if order.user_id:
                rows.append([InlineKeyboardButton(text="👤 Профиль клиента", callback_data=f"admin:user:view:{order.user_id}")])
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:orders")])
        return InlineKeyboardMarkup(inline_keyboard=rows)
        if order.status in {
            OrderStatus.WAITING_CHECK,
            OrderStatus.PAID,
            OrderStatus.PROCESSING,
            OrderStatus.WAITING,
            OrderStatus.FAILED,
        }:
            rows.append([InlineKeyboardButton(text="Подтвердить", callback_data=f"admin:approve:{order.id}")])
            rows.append([InlineKeyboardButton(text="Отклонить", callback_data=f"admin:reject:{order.id}")])
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:orders")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _user_button_texts(language: str) -> dict[str, str]:
        if language == "uz":
            return {
                "details": "📄 Buyurtma tafsilotlari",
                "support": "💬 Yordam",
                "reviews": "💬 Fikrlar",
                "menu": "🏠 Menu",
            }
        if language == "en":
            return {
                "details": "📄 Order details",
                "support": "💬 Support",
                "reviews": "💬 Reviews",
                "menu": "🏠 Menu",
            }
        return {
            "details": "📄 Детали заказа",
            "support": "💬 Поддержка",
            "reviews": "💬 Отзывы",
            "menu": "🏠 Меню",
        }

    def _user_order_markup(language: str, order: Order) -> InlineKeyboardMarkup:
        labels = _user_button_texts(language)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=labels["details"], callback_data=f"order:detail:{order.id}")],
                [InlineKeyboardButton(text=labels["support"], url=app.settings.support_url)],
                [InlineKeyboardButton(text=labels["reviews"], url=app.settings.review_url)],
                [InlineKeyboardButton(text=labels["menu"], callback_data="menu:main")],
            ]
        )

    def _user_menu_markup(language: str) -> InlineKeyboardMarkup:
        labels = _user_button_texts(language)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=labels["support"], url=app.settings.support_url)],
                [InlineKeyboardButton(text=labels["menu"], callback_data="menu:main")],
            ]
        )

    def _user_sum_text(value: Decimal | int | float | str, language: str) -> str:
        amount_text = format_money(value, "сум").replace(" сум", "")
        if language == "uz":
            return f"{amount_text} so'm"
        if language == "en":
            return f"{amount_text} UZS"
        return f"{amount_text} сум"

    def _payment_method_title(code: str | None, language: str) -> str:
        normalized = (code or "").strip().lower()
        if normalized == "card":
            return "Humo / Uzcard"
        if normalized == "usdt_trc20":
            return "Kriptovalyuta" if language == "uz" else ("Cryptocurrency" if language == "en" else "Криптовалюта")
        if normalized == "click":
            return "Click"
        return code or "-"

    def _topup_approved_user_text(language: str, amount, new_balance) -> str:
        if language == "uz":
            return (
                "✅ Balans to'ldirildi\n\n"
                f"💰 Kiritildi: {_user_sum_text(amount, language)}\n"
                f"💳 Yangi balansingiz: {_user_sum_text(new_balance, language)}\n\n"
                "Endi xaridni rasmiylashtirishingiz mumkin."
            )
        if language == "en":
            return (
                "✅ Balance credited\n\n"
                f"💰 Added: {_user_sum_text(amount, language)}\n"
                f"💳 Your new balance: {_user_sum_text(new_balance, language)}\n\n"
                "You can now complete a purchase."
            )
        return (
            "✅ Баланс пополнен\n\n"
            f"💰 Зачислено: {_user_sum_text(amount, language)}\n"
            f"💳 Ваш новый баланс: {_user_sum_text(new_balance, language)}\n\n"
            "Теперь вы можете оформить покупку."
        )

    def _topup_rejected_user_text(language: str, amount, payment_method: str | None) -> str:
        method_title = _payment_method_title(payment_method, language)
        if language == "uz":
            return (
                "❌ To'ldirish so'rovi rad etildi\n\n"
                f"💰 Summa: {_user_sum_text(amount, language)}\n"
                f"💳 Usul: {method_title}\n\n"
                "Agar siz allaqachon to'lagan bo'lsangiz, yordam bilan bog'laning."
            )
        if language == "en":
            return (
                "❌ Top-up request rejected\n\n"
                f"💰 Amount: {_user_sum_text(amount, language)}\n"
                f"💳 Method: {method_title}\n\n"
                "If you have already paid, please contact support."
            )
        return (
            "❌ Заявка на пополнение отклонена\n\n"
            f"💰 Сумма: {_user_sum_text(amount, language)}\n"
            f"💳 Способ: {method_title}\n\n"
            "Если вы уже оплатили, свяжитесь с поддержкой."
        )

    def _refund_user_text(language: str, order: Order, new_balance) -> str:
        service_title = escape(order.service_name_snapshot or order.product_name_snapshot or "Order")
        product_type = escape(order.product_type_snapshot or "-")
        if language == "uz":
            return (
                "↩️ Buyurtma bekor qilindi\n\n"
                f"💎 Xizmat: {service_title}\n"
                f"📦 Turi: {product_type}\n"
                f"💰 Balansga qaytarildi: {_user_sum_text(order.amount, language)}\n"
                f"💳 Joriy balans: {_user_sum_text(new_balance, language)}"
            )
        if language == "en":
            return (
                "↩️ Order cancelled\n\n"
                f"💎 Service: {service_title}\n"
                f"📦 Type: {product_type}\n"
                f"💰 Refunded to balance: {_user_sum_text(order.amount, language)}\n"
                f"💳 Current balance: {_user_sum_text(new_balance, language)}"
            )
        return (
            "↩️ Заказ отменён\n\n"
            f"💎 Сервис: {service_title}\n"
            f"📦 Тип: {product_type}\n"
            f"💰 Возврат на баланс: {_user_sum_text(order.amount, language)}\n"
            f"💳 Текущий баланс: {_user_sum_text(new_balance, language)}"
        )

    def _delivery_user_text(language: str, order: Order, delivery_content: str) -> str:
        service_title = escape(order.service_name_snapshot or order.product_name_snapshot or "Order")
        product_type = escape(order.product_type_snapshot or "-")
        content = escape(delivery_content)
        if language == "uz":
            return (
                "✅ Buyurtmangiz tasdiqlandi\n\n"
                f"💎 Xizmat: {service_title}\n"
                f"📦 Turi: {product_type}\n"
                f"💰 To'langan: {_user_sum_text(order.amount, language)}\n\n"
                "Buyurtma ma'lumotlari:\n"
                f"{content}\n\n"
                "Xaridingiz uchun rahmat!"
            )
        if language == "en":
            return (
                "✅ Your order has been confirmed\n\n"
                f"💎 Service: {service_title}\n"
                f"📦 Type: {product_type}\n"
                f"💰 Paid: {_user_sum_text(order.amount, language)}\n\n"
                "Order details:\n"
                f"{content}\n\n"
                "Thank you for your purchase!"
            )
        return (
            "✅ Ваш заказ подтверждён\n\n"
            f"💎 Сервис: {service_title}\n"
            f"📦 Тип: {product_type}\n"
            f"💰 Оплачено: {_user_sum_text(order.amount, language)}\n\n"
            "Данные по заказу:\n"
            f"{content}\n\n"
            "Спасибо за покупку!"
        )

    async def _send_user_message(telegram_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
        try:
            await bot.send_message(telegram_id, text, reply_markup=reply_markup)
        except Exception:
            pass

    async def _user_lang(session, order: Order) -> str:
        if order.user is None:
            return order.language or app.settings.default_language
        return await get_user_language(session, order.user.telegram_id, app.settings.default_language)

    def _processing_notice(language: str, order: Order) -> str:
        if language == "uz":
            return (
                "✅ To'lov tasdiqlandi\n\n"
                f"Buyurtma: <code>{order.order_number}</code>\n"
                f"Mahsulot: {escape(order.product_name_snapshot)}\n"
                "Holat: ishlovga o'tkazildi\n\n"
                "To'lovingiz qabul qilindi va buyurtma ishga olindi. Hozir jamoamiz ulanishni tayyorlamoqda.\n\n"
                "Hammasi tayyor bo'lishi bilan shu botda alohida xabar yuboramiz."
            )
        if language == "en":
            return (
                "✅ Payment confirmed\n\n"
                f"Order: <code>{order.order_number}</code>\n"
                f"Product: {escape(order.product_name_snapshot)}\n"
                "Status: in progress\n\n"
                "We received your payment and started processing the order. Our team is preparing the activation now.\n\n"
                "You will get a separate message in this bot as soon as everything is ready."
            )
        return (
            "✅ Оплата подтверждена\n\n"
            f"Заказ: <code>{order.order_number}</code>\n"
            f"Товар: {escape(order.product_name_snapshot)}\n"
            "Статус: передан в работу\n\n"
            "Мы получили ваш платёж и уже начали обработку заказа. Сейчас готовим подключение.\n\n"
            "Как только всё будет готово, сразу отправим отдельное сообщение в этом боте."
        )

    def _completed_notice(language: str, order: Order) -> str:
        if language == "uz":
            return (
                "🎉 Buyurtma tayyor\n\n"
                f"Buyurtma: <code>{order.order_number}</code>\n"
                f"Mahsulot: {escape(order.product_name_snapshot)}\n\n"
                "Ulanish muvaffaqiyatli yakunlandi. Agar faollashtirishdan keyin savollar qolsa, shu botdagi yordam bo'limi orqali yozing."
            )
        if language == "en":
            return (
                "🎉 Order completed\n\n"
                f"Order: <code>{order.order_number}</code>\n"
                f"Product: {escape(order.product_name_snapshot)}\n\n"
                "Activation is complete. If you need anything after that, contact support from this bot."
            )
        return (
            "🎉 Заказ готов\n\n"
            f"Заказ: <code>{order.order_number}</code>\n"
            f"Товар: {escape(order.product_name_snapshot)}\n\n"
            "Подключение завершено. Если после активации появятся вопросы, напишите в поддержку через этого бота."
        )

    def _rejected_notice(language: str, order: Order) -> str:
        if language == "uz":
            return (
                "❌ Buyurtma rad etildi\n\n"
                f"Buyurtma: <code>{order.order_number}</code>\n"
                "Agar bu xato bo'lsa, yordam xizmatiga murojaat qiling."
            )
        if language == "en":
            return (
                "❌ Order rejected\n\n"
                f"Order: <code>{order.order_number}</code>\n"
                "If this happened by mistake, please contact support."
            )
        return (
            "❌ Заказ отклонён\n\n"
            f"Заказ: <code>{order.order_number}</code>\n"
            "Если это произошло по ошибке, пожалуйста, свяжитесь с поддержкой."
        )

    def _capcut_waiting_notice(language: str, order: Order) -> str:
        if language == "uz":
            return (
                "✅ To'lov tasdiqlandi\n\n"
                f"Buyurtma: <code>{order.order_number}</code>\n"
                f"Mahsulot: {escape(order.product_name_snapshot)}\n\n"
                "To'lov qabul qilindi, lekin hozir CapCut uchun bo'sh akkaunt qolmagan. Buyurtmangiz ishlovda qoldi.\n\n"
                "Bo'sh akkaunt paydo bo'lishi bilan ma'lumotlarni shu botga yuboramiz."
            )
        if language == "en":
            return (
                "✅ Payment confirmed\n\n"
                f"Order: <code>{order.order_number}</code>\n"
                f"Product: {escape(order.product_name_snapshot)}\n\n"
                "Your payment is confirmed, but there are no free CapCut accounts right now. The order remains in progress.\n\n"
                "We will send the account details here as soon as stock appears."
            )
        return (
            "✅ Оплата подтверждена\n\n"
            f"Заказ: <code>{order.order_number}</code>\n"
            f"Товар: {escape(order.product_name_snapshot)}\n\n"
            "Платёж подтверждён, но сейчас нет свободного аккаунта CapCut. Заказ оставлен в работе.\n\n"
            "Как только появится свободный аккаунт, сразу отправим данные в этот бот."
        )

    def _capcut_ready_notice(language: str, order: Order, account: CapCutAccount) -> str:
        if language == "uz":
            return (
                "✅ To'lov tasdiqlandi\n\n"
                "🎬 CapCut Pro tayyor.\n"
                f"Buyurtma: <code>{order.order_number}</code>\n"
                f"Login: <code>{account.login}</code>\n"
                f"Parol: <code>{account.password}</code>\n\n"
                "Agar boshqa CapCut akkaunti ochiq bo'lsa, avval undan chiqing, keyin yuqoridagi ma'lumotlar bilan kiring."
            )
        if language == "en":
            return (
                "✅ Payment confirmed\n\n"
                "🎬 Your CapCut Pro is ready.\n"
                f"Order: <code>{order.order_number}</code>\n"
                f"Login: <code>{account.login}</code>\n"
                f"Password: <code>{account.password}</code>\n\n"
                "If another CapCut account is currently open, sign out first and then sign in with the credentials above."
            )
        return (
            "✅ Оплата подтверждена\n\n"
            "🎬 Ваш CapCut Pro готов.\n"
            f"Заказ: <code>{order.order_number}</code>\n"
            f"Логин: <code>{account.login}</code>\n"
            f"Пароль: <code>{account.password}</code>\n\n"
            "Если у вас уже открыт другой аккаунт CapCut, сначала выйдите из него, а затем войдите по данным выше."
        )

    def _product_list_markup(products: list[Product]) -> InlineKeyboardMarkup:
        rows = [
            [
                InlineKeyboardButton(
                    text=f"{service_name(product, 'ru')} • {product_type_label(product, 'ru')} • {format_money(product.price, product.currency)}",
                    callback_data=f"admin:product:{product.id}",
                )
            ]
            for product in products
        ]
        rows.append([InlineKeyboardButton(text="Добавить товар", callback_data="admin:products:add")])
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:main")])
        return InlineKeyboardMarkup(inline_keyboard=rows)
        rows = [[InlineKeyboardButton(text=f"{product.code} ({product.status.value})", callback_data=f"admin:product:{product.id}")] for product in products]
        rows.append([InlineKeyboardButton(text="Добавить товар", callback_data="admin:products:add")])
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:main")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _payment_list_markup(items: list[PaymentMethod]) -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(text=f"{item.admin_title} ({'on' if item.is_active else 'off'})", callback_data=f"admin:payment:{item.id}")] for item in items]
        rows.append([InlineKeyboardButton(text="Добавить метод", callback_data="admin:payments:add")])
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:main")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _stock_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Добавить аккаунт", callback_data="admin:stock:add")],
                [InlineKeyboardButton(text="Добавить пачкой", callback_data="admin:stock:bulk")],
                [InlineKeyboardButton(text="Свободные", callback_data="admin:stock:free")],
                [InlineKeyboardButton(text="Выданные", callback_data="admin:stock:used")],
                [InlineKeyboardButton(text="Назад", callback_data="admin:main")],
            ]
        )

    def _text_pages_markup(entries: list[TextEntry], page: int, total_pages: int) -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(text=entry.code, callback_data=f"admin:text:{entry.id}")] for entry in entries]
        nav_row: list[InlineKeyboardButton] = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text="◀", callback_data=f"admin:texts:{page - 1}"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text="▶", callback_data=f"admin:texts:{page + 1}"))
        if nav_row:
            rows.append(nav_row)
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:main")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _layouts_markup(layouts: list[Layout]) -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(text=f"{layout.scope}: {layout.title}", callback_data=f"admin:layout:{layout.id}")] for layout in layouts]
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:main")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    @router.message(Command("admin"))
    async def admin_command_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        await state.clear()
        await _render_admin_main(message)

    @router.message(Command("find_order"))
    async def admin_find_order_handler(message: Message) -> None:
        if not _guard(message.from_user.id):
            return
        reference = (message.text or "").partition(" ")[2].strip()
        if not reference:
            await message.answer("Используйте: <code>/find_order 123</code> или <code>/find_order #123</code>.")
            return
        async with app.session_factory() as session:
            order = await get_order_by_reference(session, reference)
        if order is None:
            await message.answer("Заказ не найден.")
            return
        await message.answer(_render_order_text(order), reply_markup=_order_actions_markup(order))

    @router.callback_query(F.data == "admin:main")
    async def admin_main_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.clear()
        await callback.answer()
        await _render_admin_main(callback)

    @router.callback_query(F.data == "admin:stats")
    async def admin_stats_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        async with app.session_factory() as session:
            text = await build_stats_text(session)
        await callback.answer()
        await answer_or_edit(callback, text, reply_markup=_back_main_markup())

    async def _show_topup_queue(target: CallbackQuery, index: int = 0) -> None:
        async with app.session_factory() as session:
            pending = await list_pending_topups(session)
        if not pending:
            await answer_or_edit(
                target,
                "<b>📥 Заявки на пополнение</b>\n\nАктивных заявок нет.",
                reply_markup=_back_main_markup(),
            )
            return
        normalized_index = max(0, min(index, len(pending) - 1))
        pending_ids = [item.id for item in pending]
        current = pending[normalized_index]
        await answer_or_edit(
            target,
            _render_topup_text(current, normalized_index, len(pending)),
            reply_markup=_topup_view_markup(current, pending_ids, normalized_index),
        )

    @router.callback_query(F.data == "admin:topups")
    @router.callback_query(F.data.startswith("admin:topups:show:"))
    async def admin_topups_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        index = 0
        if callback.data.startswith("admin:topups:show:"):
            index = int(callback.data.split(":")[-1])
        await callback.answer()
        await _show_topup_queue(callback, index)

    @router.callback_query(F.data.startswith("admin:topup:approve:"))
    async def admin_topup_approve_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        topup_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            topup = await get_topup_by_id(session, topup_id)
            if topup is None:
                await callback.answer()
                await answer_or_edit(callback, "Заявка не найдена.", reply_markup=_back_main_markup())
                return
            if topup.status != TopupStatus.PENDING:
                await callback.answer()
                await answer_or_edit(callback, "⚠️ Эта заявка уже обработана.", reply_markup=_back_main_markup())
                return
            transaction = await credit_balance(
                session,
                user_id=topup.user_id,
                amount=topup.amount,
                tx_type=BalanceTransactionType.TOPUP,
                source="topup",
                source_id=topup.id,
            )
            await approve_topup(session, topup, callback.from_user.id)
            await session.commit()
            user = topup.user
            new_balance = transaction.balance_after
            language = await get_user_language(session, user.telegram_id, app.settings.default_language) if user is not None else "ru"
        await callback.answer("Баланс пополнен")
        if user is not None:
            await _send_user_message(
                user.telegram_id,
                _topup_approved_user_text(language, topup.amount, new_balance),
            )
        await _show_topup_queue(callback, 0)

    @router.callback_query(F.data.startswith("admin:topup:reject:"))
    async def admin_topup_reject_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        topup_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            topup = await get_topup_by_id(session, topup_id)
            if topup is None:
                await callback.answer()
                await answer_or_edit(callback, "Заявка не найдена.", reply_markup=_back_main_markup())
                return
            if topup.status != TopupStatus.PENDING:
                await callback.answer()
                await answer_or_edit(callback, "⚠️ Эта заявка уже обработана.", reply_markup=_back_main_markup())
                return
            await reject_topup(session, topup, callback.from_user.id)
            await session.commit()
            user = topup.user
            language = await get_user_language(session, user.telegram_id, app.settings.default_language) if user is not None else "ru"
        await callback.answer("Заявка отклонена")
        if user is not None:
            await _send_user_message(
                user.telegram_id,
                _topup_rejected_user_text(language, topup.amount, topup.payment_method),
            )
        await _show_topup_queue(callback, 0)

    @router.callback_query(F.data == "admin:orders")
    @router.callback_query(F.data.startswith("admin:orders:"))
    async def admin_orders_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        statuses = None
        title = "Последние заказы"
        if callback.data.count(":") == 2:
            status = callback.data.split(":")[-1]
            statuses = [status]
            title = f"Заказы: {order_status_label(status, 'ru')}"
        async with app.session_factory() as session:
            orders = await list_orders(session, statuses=statuses, limit=20)
        rows = [
            [InlineKeyboardButton(text=f"{order_display_number(order)} • {order.product_name_snapshot} • {order_status_label(order.status.value, 'ru')}", callback_data=f"admin:order:{order.id}")]
            for order in orders
        ]
        rows.append([
            InlineKeyboardButton(text="На проверке", callback_data="admin:orders:waiting_check"),
            InlineKeyboardButton(text="Оплачены", callback_data="admin:orders:paid"),
        ])
        rows.append([
            InlineKeyboardButton(text="В работе", callback_data="admin:orders:processing"),
            InlineKeyboardButton(text="Все", callback_data="admin:orders"),
        ])
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:main")])
        await callback.answer()
        await answer_or_edit(
            callback,
            f"<b>{title}</b>\n\nПоиск: <code>/find_order 123</code> или <code>/find_order #123</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    @router.callback_query(F.data.regexp(r"^admin:order:\d+$"))
    async def admin_order_detail_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            order = await get_order_by_id(session, order_id)
        await callback.answer()
        if order is None:
            await answer_or_edit(callback, "Заказ не найден.", reply_markup=_back_main_markup())
            return
        await answer_or_edit(callback, _render_order_text(order), reply_markup=_order_actions_markup(order))

    @router.callback_query(F.data.startswith("admin:order:deliver:"))
    async def admin_order_delivery_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        order_id = int(callback.data.split(":")[-1])
        await state.set_state(AdminState.waiting_order_delivery)
        await state.update_data(order_id=order_id)
        await callback.answer()
        await answer_or_edit(
            callback,
            "Отправьте данные выполнения заказа: код, инструкцию, ссылку активации или описание услуги.",
            reply_markup=_back_main_markup(),
        )

    @router.callback_query(F.data.startswith("admin:order:refund:"))
    async def admin_order_refund_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            order = await get_order_by_id(session, order_id)
            if order is None:
                await callback.answer()
                await answer_or_edit(callback, "Заказ не найден.", reply_markup=_back_main_markup())
                return
            result = await refund_order(session, order=order, admin_id=callback.from_user.id)
            await session.commit()
            language = await _user_lang(session, order)
        if not result.ok:
            await callback.answer()
            await answer_or_edit(callback, "⚠️ Этот заказ уже обработан.", reply_markup=_back_main_markup())
            return
        await callback.answer("Возврат выполнен")
        if result.user is not None:
            await _send_user_message(
                result.user.telegram_id,
                _refund_user_text(language, order, result.user.balance),
                reply_markup=_user_menu_markup(language),
            )
        await answer_or_edit(callback, _render_order_text(order), reply_markup=_order_actions_markup(order))

    @router.callback_query(F.data.startswith("admin:order:message:"))
    async def admin_order_message_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            order = await get_order_by_id(session, order_id)
            if order is None or order.user is None:
                await callback.answer()
                await answer_or_edit(callback, "Клиент не найден.", reply_markup=_back_main_markup())
                return
        await state.set_state(AdminState.waiting_user_message)
        await state.update_data(user_id=order.user_id, return_callback=f"admin:order:{order_id}")
        await callback.answer()
        await answer_or_edit(callback, "Введите сообщение для клиента.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:approve:"))
    async def admin_approve_order_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            order = await get_order_by_id(session, order_id)
            if order is None:
                await callback.answer()
                return
            if order.workflow_type == "chatgpt_manual":
                launched = await start_chatgpt_business_order(app, bot, order.id, callback.from_user.id)
                await callback.answer("Автоматизация уже запущена." if not launched else "Автоматизация запущена")
                await admin_order_detail_handler(callback)
                return
            language = await _user_lang(session, order)
            if order.status in {OrderStatus.PAID, OrderStatus.PROCESSING}:
                if order.workflow_type == "capcut_auto":
                    account = order.capcut_account or await claim_free_account(session, order)
                    if account is None:
                        await callback.answer("Склад CapCut пуст.", show_alert=True)
                        return
                    await change_status(session, order, OrderStatus.COMPLETED, callback.from_user.id, "confirmed by admin")
                    await session.commit()
                    await _send_user_message(order.user.telegram_id, _capcut_ready_notice(language, order, account), reply_markup=_user_order_markup(language, order))
                else:
                    await change_status(session, order, OrderStatus.COMPLETED, callback.from_user.id, "completed by admin")
                    await session.commit()
                    await _send_user_message(order.user.telegram_id, _completed_notice(language, order), reply_markup=_user_order_markup(language, order))
            else:
                if order.workflow_type == "capcut_auto":
                    account = await claim_free_account(session, order)
                    if account is None:
                        await change_status(session, order, OrderStatus.PROCESSING, callback.from_user.id, "payment approved, stock empty")
                        await session.commit()
                        await _send_user_message(order.user.telegram_id, _capcut_waiting_notice(language, order), reply_markup=_user_order_markup(language, order))
                    else:
                        await change_status(session, order, OrderStatus.COMPLETED, callback.from_user.id, "auto issued capcut account")
                        await session.commit()
                        await _send_user_message(order.user.telegram_id, _capcut_ready_notice(language, order, account), reply_markup=_user_order_markup(language, order))
                else:
                    await change_status(session, order, OrderStatus.PROCESSING, callback.from_user.id, "payment approved")
                    await session.commit()
                    await _send_user_message(order.user.telegram_id, _processing_notice(language, order), reply_markup=_user_order_markup(language, order))
        await callback.answer("Подтверждено")
        await admin_order_detail_handler(callback)

    @router.callback_query(F.data.startswith("admin:reject:"))
    async def admin_reject_order_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            order = await get_order_by_id(session, order_id)
            if order is None:
                await callback.answer()
                return
            language = await _user_lang(session, order)
            await change_status(session, order, OrderStatus.REJECTED, callback.from_user.id, "rejected by admin")
            await session.commit()
            await _send_user_message(order.user.telegram_id, _rejected_notice(language, order), reply_markup=_user_menu_markup(language))
        await callback.answer("Отклонено")
        await admin_order_detail_handler(callback)

    @router.callback_query(F.data.startswith("admin:complete:"))
    async def admin_complete_order_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            order = await get_order_by_id(session, order_id)
            if order is None:
                await callback.answer()
                return
            language = await _user_lang(session, order)
            await change_status(session, order, OrderStatus.COMPLETED, callback.from_user.id, "completed by admin")
            await session.commit()
            await _send_user_message(order.user.telegram_id, _completed_notice(language, order), reply_markup=_user_order_markup(language, order))
        await callback.answer("Завершено")
        await admin_order_detail_handler(callback)

    @router.callback_query(F.data == "admin:stock")
    async def admin_stock_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        async with app.session_factory() as session:
            if await purge_expired_accounts(session):
                await session.commit()
            free_count = await count_free_accounts(session)
            used_count = await session.scalar(select(func.count(CapCutAccount.id)).where(CapCutAccount.is_used.is_(True))) or 0
        await callback.answer()
        await answer_or_edit(
            callback,
            "<b>Склад CapCut</b>\n\n"
            f"Свободных: <b>{free_count}</b>\n"
            f"Выданных: <b>{used_count}</b>",
            reply_markup=_stock_markup(),
        )

    @router.callback_query(F.data == "admin:stock:add")
    async def admin_stock_add_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_stock_single)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте аккаунт в формате <code>login|password</code>.", reply_markup=_back_main_markup())

    @router.callback_query(F.data == "admin:stock:bulk")
    async def admin_stock_bulk_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_stock_bulk)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте список аккаунтов, по одному на строку.\nФормат строки: <code>login|password</code>.", reply_markup=_back_main_markup())

    @router.callback_query(F.data == "admin:stock:free")
    @router.callback_query(F.data == "admin:stock:used")
    async def admin_stock_list_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        used = callback.data.endswith("used")
        async with app.session_factory() as session:
            if await purge_expired_accounts(session):
                await session.commit()
            accounts = await list_accounts(session, used=used, limit=30)
        lines = [f"<b>{'Выданные' if used else 'Свободные'} аккаунты</b>"]
        lines.append("")
        if not accounts:
            lines.append("Список пуст.")
        else:
            for account in accounts:
                suffix = f" -> order #{account.issued_order_id}" if account.issued_order_id else ""
                lines.append(f"<code>{account.login}</code> / <code>{account.password}</code>{suffix}")
        await callback.answer()
        await answer_or_edit(callback, "\n".join(lines), reply_markup=_stock_markup())

    @router.message(AdminState.waiting_stock_single)
    async def admin_stock_single_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        raw = (message.text or "").strip()
        for separator in ("|", ":", ";"):
            if separator in raw:
                login, password = [part.strip() for part in raw.split(separator, 1)]
                break
        else:
            parts = raw.split(maxsplit=1)
            if len(parts) != 2:
                await message.answer("Неверный формат. Используйте <code>login|password</code>.")
                return
            login, password = parts
        async with app.session_factory() as session:
            await add_capcut_account(session, login, password)
            await session.commit()
        await state.clear()
        await message.answer("Аккаунт добавлен.")

    @router.message(AdminState.waiting_stock_bulk)
    async def admin_stock_bulk_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        async with app.session_factory() as session:
            created = await add_bulk_accounts(session, message.text or "")
            await session.commit()
        await state.clear()
        await message.answer(f"Добавлено аккаунтов: <b>{created}</b>")

    def _product_detail_markup(product: Product) -> InlineKeyboardMarkup:
        toggle_text = "Выключить" if product.status == ProductStatus.ACTIVE else "Включить"
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Цена", callback_data=f"admin:product:price:{product.id}"),
                    InlineKeyboardButton(text="Порядок", callback_data=f"admin:product:sort:{product.id}"),
                ],
                [
                    InlineKeyboardButton(text="Фото", callback_data=f"admin:product:photo:{product.id}"),
                    InlineKeyboardButton(text=toggle_text, callback_data=f"admin:product:toggle:{product.id}"),
                ],
                [
                    InlineKeyboardButton(text="RU", callback_data=f"admin:product:lang:{product.id}:ru"),
                    InlineKeyboardButton(text="UZ", callback_data=f"admin:product:lang:{product.id}:uz"),
                    InlineKeyboardButton(text="EN", callback_data=f"admin:product:lang:{product.id}:en"),
                ],
                [InlineKeyboardButton(text="Методы оплаты", callback_data=f"admin:product:payments:{product.id}")],
                [InlineKeyboardButton(text="Удалить", callback_data=f"admin:product:delete:{product.id}")],
                [InlineKeyboardButton(text="Назад", callback_data="admin:products")],
            ]
        )

    def _payment_detail_markup(payment: PaymentMethod) -> InlineKeyboardMarkup:
        toggle_text = "Выключить" if payment.is_active else "Включить"
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Реквизиты", callback_data=f"admin:payment:creds:{payment.id}"),
                    InlineKeyboardButton(text="Порядок", callback_data=f"admin:payment:sort:{payment.id}"),
                ],
                [
                    InlineKeyboardButton(text="Фото", callback_data=f"admin:payment:photo:{payment.id}"),
                    InlineKeyboardButton(text=toggle_text, callback_data=f"admin:payment:toggle:{payment.id}"),
                ],
                [
                    InlineKeyboardButton(text="RU", callback_data=f"admin:payment:lang:{payment.id}:ru"),
                    InlineKeyboardButton(text="UZ", callback_data=f"admin:payment:lang:{payment.id}:uz"),
                    InlineKeyboardButton(text="EN", callback_data=f"admin:payment:lang:{payment.id}:en"),
                ],
                [InlineKeyboardButton(text="Удалить", callback_data=f"admin:payment:delete:{payment.id}")],
                [InlineKeyboardButton(text="Назад", callback_data="admin:payments")],
            ]
        )

    @router.callback_query(F.data == "admin:products")
    async def admin_products_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        async with app.session_factory() as session:
            products = list((await session.scalars(select(Product).order_by(Product.sort_order, Product.id))).all())
        await callback.answer()
        await answer_or_edit(callback, "<b>💎 Товары / тарифы</b>", reply_markup=_product_list_markup(products))

    @router.callback_query(F.data.regexp(r"^admin:product:\d+$"))
    async def admin_product_detail_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        parts = callback.data.split(":")
        if len(parts) != 3:
            return
        product_id = int(parts[-1])
        async with app.session_factory() as session:
            product = await get_product(session, product_id)
        await callback.answer()
        if product is None:
            await answer_or_edit(callback, "Товар не найден.", reply_markup=_back_main_markup())
            return
        ru_name = pick_translation(product.translations, "ru", "name") or product.code
        uz_name = pick_translation(product.translations, "uz", "name")
        en_name = pick_translation(product.translations, "en", "name")
        payment_names = ", ".join(link.payment_method.admin_title for link in product.payment_links) or "-"
        category_text = category_name(product.category, "ru") if product.category else "-"
        text = (
            f"<b>{ru_name}</b>\n\n"
            f"Code: <code>{product.code}</code>\n"
            f"Категория: {category_text}\n"
            f"RU: {ru_name}\n"
            f"UZ: {uz_name or '-'}\n"
            f"EN: {en_name or '-'}\n"
            f"Цена: <b>{format_money(product.price, product.currency)}</b>\n"
            f"Статус: <b>{product.status.value}</b>\n"
            f"Выдача: {product.delivery_type}\n"
            f"Workflow: {product.workflow_type}\n"
            f"Порядок: {product.sort_order}\n"
            f"Фото file_id: {product.photo_file_id or '-'}\n"
            f"Методы оплаты: {payment_names}"
        )
        await answer_or_edit(callback, text, reply_markup=_product_detail_markup(product))

    @router.callback_query(F.data == "admin:products:add")
    async def admin_products_add_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_product_create)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте: <code>code|category_code|price|currency|workflow_type|delivery_type</code>", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:product:toggle:"))
    async def admin_product_toggle_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            product = await get_product(session, product_id)
            if product is None:
                await callback.answer()
                return
            product.status = ProductStatus.HIDDEN if product.status == ProductStatus.ACTIVE else ProductStatus.ACTIVE
            await session.commit()
        await callback.answer("Сохранено")
        callback.data = f"admin:product:{product_id}"
        await admin_product_detail_handler(callback)

    @router.callback_query(F.data.startswith("admin:product:price:"))
    async def admin_product_price_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_product_price)
        await state.update_data(product_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте новую цену.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:product:sort:"))
    async def admin_product_sort_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_product_sort)
        await state.update_data(product_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте новый порядок.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:product:photo:"))
    async def admin_product_photo_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_product_photo)
        await state.update_data(product_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте фото товара.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:product:lang:"))
    async def admin_product_lang_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        _, _, _, product_id, lang = callback.data.split(":")
        await state.set_state(AdminState.waiting_product_translation)
        await state.update_data(product_id=int(product_id), language=lang)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте: <code>Название || Описание</code>", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:product:payments:"))
    async def admin_product_payments_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            product = await get_product(session, product_id)
            payments = list((await session.scalars(select(PaymentMethod).order_by(PaymentMethod.sort_order, PaymentMethod.id))).all())
        if product is None:
            await callback.answer()
            return
        attached = {link.payment_method_id for link in product.payment_links}
        rows = [[InlineKeyboardButton(text=f"{'✅' if payment.id in attached else '▫️'} {payment.admin_title}", callback_data=f"admin:product:paytoggle:{product.id}:{payment.id}")] for payment in payments]
        rows.append([InlineKeyboardButton(text="Назад", callback_data=f"admin:product:{product.id}")])
        await callback.answer()
        await answer_or_edit(callback, f"<b>Методы оплаты для {product_name(product, 'ru')}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    @router.callback_query(F.data.startswith("admin:product:paytoggle:"))
    async def admin_product_paytoggle_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        _, _, _, product_id, payment_id = callback.data.split(":")
        async with app.session_factory() as session:
            await toggle_product_payment_method(session, int(product_id), int(payment_id))
            await session.commit()
        await callback.answer("Сохранено")
        callback.data = f"admin:product:payments:{product_id}"
        await admin_product_payments_handler(callback)

    @router.callback_query(F.data.startswith("admin:product:delete:"))
    async def admin_product_delete_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            product = await get_product(session, product_id)
            if product is None:
                await callback.answer()
                return
            await session.delete(product)
            await session.commit()
        await callback.answer("Удалено")
        await admin_products_handler(callback)

    @router.callback_query(F.data == "admin:payments")
    async def admin_payments_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        async with app.session_factory() as session:
            payments = list((await session.scalars(select(PaymentMethod).order_by(PaymentMethod.sort_order, PaymentMethod.id))).all())
        await callback.answer()
        await answer_or_edit(callback, "<b>Способы оплаты</b>", reply_markup=_payment_list_markup(payments))

    @router.callback_query(F.data.regexp(r"^admin:payment:\d+$"))
    async def admin_payment_detail_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        parts = callback.data.split(":")
        if len(parts) != 3:
            return
        payment_id = int(parts[-1])
        async with app.session_factory() as session:
            payment = await get_payment_method(session, payment_id)
        if payment is None:
            await callback.answer()
            return
        text = (
            f"<b>{payment.admin_title}</b>\n\n"
            f"Code: <code>{payment.code}</code>\n"
            f"Тип: {payment.provider_type.value}\n"
            f"Реквизиты: <code>{payment.credentials or '-'}</code>\n"
            f"Статус: {'on' if payment.is_active else 'off'}\n"
            f"Порядок: {payment.sort_order}\n"
            f"Фото file_id: {payment.photo_file_id or '-'}\n"
            f"RU: {payment_title(payment, 'ru')}\n"
            f"UZ: {payment_title(payment, 'uz') or '-'}\n"
            f"EN: {payment_title(payment, 'en') or '-'}"
        )
        await callback.answer()
        await answer_or_edit(callback, text, reply_markup=_payment_detail_markup(payment))

    @router.callback_query(F.data == "admin:payments:add")
    async def admin_payment_add_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_payment_create)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте: <code>code|type|admin_title</code>", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:payment:toggle:"))
    async def admin_payment_toggle_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        payment_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            payment = await get_payment_method(session, payment_id)
            if payment is None:
                await callback.answer()
                return
            payment.is_active = not payment.is_active
            await session.commit()
        await callback.answer("Сохранено")
        callback.data = f"admin:payment:{payment_id}"
        await admin_payment_detail_handler(callback)

    @router.callback_query(F.data.startswith("admin:payment:creds:"))
    async def admin_payment_creds_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_payment_credentials)
        await state.update_data(payment_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте новые реквизиты.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:payment:sort:"))
    async def admin_payment_sort_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_payment_sort)
        await state.update_data(payment_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте новый порядок.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:payment:photo:"))
    async def admin_payment_photo_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_payment_photo)
        await state.update_data(payment_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте фото/QR для метода оплаты.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:payment:lang:"))
    async def admin_payment_lang_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        _, _, _, payment_id, lang = callback.data.split(":")
        await state.set_state(AdminState.waiting_payment_translation)
        await state.update_data(payment_id=int(payment_id), language=lang)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте: <code>Название || Инструкция</code>", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:payment:delete:"))
    async def admin_payment_delete_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        payment_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            payment = await get_payment_method(session, payment_id)
            if payment is None:
                await callback.answer()
                return
            await session.delete(payment)
            await session.commit()
        await callback.answer("Удалено")
        await admin_payments_handler(callback)

    @router.callback_query(F.data == "admin:texts")
    @router.callback_query(F.data.startswith("admin:texts:"))
    async def admin_texts_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        page = int(callback.data.split(":")[-1]) if callback.data.count(":") == 2 else 0
        page_size = 10
        async with app.session_factory() as session:
            all_entries = list((await session.scalars(select(TextEntry).order_by(TextEntry.group_name, TextEntry.code))).all())
        total_pages = max((len(all_entries) + page_size - 1) // page_size, 1)
        page = min(max(page, 0), total_pages - 1)
        items = all_entries[page * page_size:(page + 1) * page_size]
        await callback.answer()
        await answer_or_edit(callback, "<b>Тексты</b>", reply_markup=_text_pages_markup(items, page, total_pages))

    @router.callback_query(F.data.regexp(r"^admin:text:\d+$"))
    async def admin_text_detail_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        text_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            entry = await session.scalar(select(TextEntry).where(TextEntry.id == text_id))
        if entry is None:
            await callback.answer()
            return
        text = (
            f"<b>{entry.code}</b>\n\n"
            f"Группа: {entry.group_name}\n"
            f"Описание: {entry.description or '-'}\n\n"
            f"RU:\n{pick_translation(entry.translations, 'ru', 'value') or '-'}\n\n"
            f"UZ:\n{pick_translation(entry.translations, 'uz', 'value') or '-'}\n\n"
            f"EN:\n{pick_translation(entry.translations, 'en', 'value') or '-'}"
        )
        await callback.answer()
        await answer_or_edit(
            callback,
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="RU", callback_data=f"admin:text:lang:{entry.id}:ru"),
                        InlineKeyboardButton(text="UZ", callback_data=f"admin:text:lang:{entry.id}:uz"),
                        InlineKeyboardButton(text="EN", callback_data=f"admin:text:lang:{entry.id}:en"),
                    ],
                    [InlineKeyboardButton(text="Назад", callback_data="admin:texts")],
                ]
            ),
        )

    @router.callback_query(F.data.startswith("admin:text:lang:"))
    async def admin_text_lang_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        _, _, _, text_id, lang = callback.data.split(":")
        await state.set_state(AdminState.waiting_text_translation)
        await state.update_data(text_id=int(text_id), language=lang)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте новое значение текста.", reply_markup=_back_main_markup())

    def _button_detail_markup(button: LayoutButton) -> InlineKeyboardMarkup:
        toggle_text = "Выключить" if button.is_active else "Включить"
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Назначение", callback_data=f"admin:button:action:{button.id}"),
                    InlineKeyboardButton(text="Ряд", callback_data=f"admin:button:row:{button.id}"),
                ],
                [
                    InlineKeyboardButton(text="Порядок", callback_data=f"admin:button:sort:{button.id}"),
                    InlineKeyboardButton(text="Цвет", callback_data=f"admin:button:style:{button.id}"),
                ],
                [
                    InlineKeyboardButton(text="RU", callback_data=f"admin:button:lang:{button.id}:ru"),
                    InlineKeyboardButton(text="UZ", callback_data=f"admin:button:lang:{button.id}:uz"),
                    InlineKeyboardButton(text="EN", callback_data=f"admin:button:lang:{button.id}:en"),
                ],
                [
                    InlineKeyboardButton(text=toggle_text, callback_data=f"admin:button:toggle:{button.id}"),
                    InlineKeyboardButton(text="Удалить", callback_data=f"admin:button:delete:{button.id}"),
                ],
                [InlineKeyboardButton(text="Назад", callback_data=f"admin:layout:{button.layout_id}")],
            ]
        )

    @router.callback_query(F.data == "admin:buttons")
    async def admin_buttons_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        async with app.session_factory() as session:
            layouts = [layout for layout in await list_layouts(session) if layout.code in live_layout_codes]
        await callback.answer()
        await answer_or_edit(
            callback,
            (
                "<b>Кнопки</b>\n\n"
                "Здесь редактируются только живые layout-экраны: главное меню пользователя и админка.\n"
                "Кнопки каталога, оплаты и профиля пока задаются кодом и не меняются из этого раздела."
            ),
            reply_markup=_layouts_markup(layouts),
        )

    @router.callback_query(F.data.regexp(r"^admin:layout:\d+$"))
    async def admin_layout_detail_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        layout_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            layout = await session.scalar(select(Layout).where(Layout.id == layout_id))
        if layout is None:
            await callback.answer()
            return
        rows = [
            [
                InlineKeyboardButton(
                    text=f"{button.code} ({button.row_index}/{button.sort_order}, {button.style})",
                    callback_data=f"admin:button:{button.id}",
                )
            ]
            for button in sorted(layout.buttons, key=lambda item: (item.row_index, item.sort_order, item.id))
        ]
        rows.append([InlineKeyboardButton(text="Добавить кнопку", callback_data=f"admin:layout:add:{layout.id}")])
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:buttons")])
        await callback.answer()
        await answer_or_edit(
            callback,
            f"<b>{layout.title}</b>\nCode: <code>{layout.code}</code>\nScope: {layout.scope}\n\nИзменения этого лейаута применяются сразу в боте.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    @router.callback_query(F.data.startswith("admin:layout:add:"))
    async def admin_button_add_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_button_create)
        await state.update_data(layout_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте: <code>code|callback_or_url|action_value|row|sort|text_ru|text_uz|text_en</code>", reply_markup=_back_main_markup())

    @router.callback_query(F.data.regexp(r"^admin:button:\d+$"))
    async def admin_button_detail_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        button_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            button = await get_button(session, button_id)
        if button is None:
            await callback.answer()
            return
        layout_code = button.layout.code if button.layout else "-"
        text = (
            f"<b>{button.code}</b>\n\n"
            f"Лейаут: <code>{layout_code}</code>\n"
            f"Тип: {button.action_type.value}\n"
            f"Назначение: <code>{button.action_value}</code>\n"
            f"Ряд: {button.row_index}\n"
            f"Порядок: {button.sort_order}\n"
            f"Цвет: {button.style}\n"
            f"Активна: {button.is_active}\n\n"
            f"Примечание: стиль применяется только к layout-кнопкам этого экрана.\n\n"
            f"RU: {pick_translation(button.translations, 'ru', 'text') or '-'}\n"
            f"UZ: {pick_translation(button.translations, 'uz', 'text') or '-'}\n"
            f"EN: {pick_translation(button.translations, 'en', 'text') or '-'}"
        )
        await callback.answer()
        await answer_or_edit(callback, text, reply_markup=_button_detail_markup(button))

    @router.callback_query(F.data.startswith("admin:button:lang:"))
    async def admin_button_lang_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        _, _, _, button_id, lang = callback.data.split(":")
        await state.set_state(AdminState.waiting_button_translation)
        await state.update_data(button_id=int(button_id), language=lang)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте новый текст кнопки.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:button:action:"))
    async def admin_button_action_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_button_action)
        await state.update_data(button_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте: <code>callback|action</code> или <code>url|https://...</code>", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:button:row:"))
    async def admin_button_row_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_button_row)
        await state.update_data(button_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте номер ряда.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:button:sort:"))
    async def admin_button_sort_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_button_sort)
        await state.update_data(button_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте порядок сортировки.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:button:style:"))
    async def admin_button_style_cycle_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        button_id = int(callback.data.split(":")[-1])
        styles = ["default", "primary", "success", "danger"]
        async with app.session_factory() as session:
            button = await get_button(session, button_id)
            if button is None:
                await callback.answer()
                return
            current_index = styles.index(button.style) if button.style in styles else 0
            button.style = styles[(current_index + 1) % len(styles)]
            await session.commit()
        await callback.answer(f"Цвет: {button.style}")
        callback.data = f"admin:button:{button_id}"
        await admin_button_detail_handler(callback)

    @router.callback_query(F.data.startswith("admin:button:toggle:"))
    async def admin_button_toggle_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        button_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            button = await get_button(session, button_id)
            if button is None:
                await callback.answer()
                return
            button.is_active = not button.is_active
            await session.commit()
        await callback.answer("Сохранено")
        callback.data = f"admin:button:{button_id}"
        await admin_button_detail_handler(callback)

    @router.callback_query(F.data.startswith("admin:button:delete:"))
    async def admin_button_delete_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        button_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            button = await get_button(session, button_id)
            if button is None:
                await callback.answer()
                return
            layout_id = button.layout_id
            await session.delete(button)
            await session.commit()
        await callback.answer("Удалено")
        callback.data = f"admin:layout:{layout_id}"
        await admin_layout_detail_handler(callback)

    @router.callback_query(F.data == "admin:users")
    async def admin_users_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_user_lookup)
        await callback.answer()
        await answer_or_edit(
            callback,
            "<b>👤 Пользователи</b>\n\nОтправьте username, Telegram ID или внутренний ID пользователя.",
            reply_markup=_back_main_markup(),
        )

    @router.callback_query(F.data.startswith("admin:user:view:"))
    async def admin_user_view_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        user_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            user = await get_user_by_id(session, user_id)
            if user is None:
                await callback.answer()
                await answer_or_edit(callback, "Пользователь не найден.", reply_markup=_back_main_markup())
                return
            orders_count = await count_orders_for_user(session, user.id)
        await callback.answer()
        await answer_or_edit(callback, _admin_user_text(user, orders_count), reply_markup=_admin_user_markup(user.id))

    @router.callback_query(F.data.startswith("admin:user:adjust:"))
    async def admin_user_adjust_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        _, _, _, user_id, mode = callback.data.split(":")
        await state.set_state(AdminState.waiting_balance_adjustment)
        await state.update_data(user_id=int(user_id), adjustment_mode=mode)
        prompt = "Введите сумму пополнения в сумах." if mode == "add" else "Введите сумму списания в сумах."
        await callback.answer()
        await answer_or_edit(callback, prompt, reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:user:message:"))
    async def admin_user_message_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        user_id = int(callback.data.split(":")[-1])
        await state.set_state(AdminState.waiting_user_message)
        await state.update_data(user_id=user_id, return_callback=f"admin:user:view:{user_id}")
        await callback.answer()
        await answer_or_edit(callback, "Введите сообщение для клиента.", reply_markup=_back_main_markup())

    @router.callback_query(F.data == "admin:inventory")
    async def admin_inventory_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        async with app.session_factory() as session:
            products = await list_inventory_products(session)
        await callback.answer()
        await answer_or_edit(callback, "<b>📦 Готовые доступы</b>\n\nВыберите сервис:", reply_markup=_inventory_products_markup(products))

    @router.callback_query(F.data.startswith("admin:inventory:product:"))
    async def admin_inventory_product_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            product = await get_product(session, product_id)
            if product is None:
                await callback.answer()
                await answer_or_edit(callback, "Товар не найден.", reply_markup=_back_main_markup())
                return
            summary = await get_inventory_summary(session, product_id)
        text = (
            f"<b>📦 {escape(service_name(product, 'ru'))} — готовые доступы</b>\n\n"
            f"📦 Всего добавлено: {summary['total_count']}\n"
            f"✅ Доступно: {summary['available_count']}\n"
            f"🛒 Продано: {summary['sold_count']}\n"
            f"⏳ Зарезервировано: {summary['reserved_count']}\n"
            f"🗑 Удалено: {summary['deleted_count']}"
        )
        await callback.answer()
        await answer_or_edit(callback, text, reply_markup=_inventory_product_markup(product_id))

    @router.callback_query(F.data.startswith("admin:inventory:add:"))
    async def admin_inventory_add_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        product_id = int(callback.data.split(":")[-1])
        await state.set_state(AdminState.waiting_inventory_item)
        await state.update_data(product_id=product_id)
        await callback.answer()
        await answer_or_edit(
            callback,
            "➕ Добавление готового доступа\n\nОтправьте данные товара в формате:\n\nНазвание:\nКод / доступ:\nИнструкция:",
            reply_markup=_back_main_markup(),
        )

    @router.callback_query(F.data.startswith("admin:inventory:list:"))
    async def admin_inventory_list_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            product = await get_product(session, product_id)
            items = await list_inventory_items(session, product_id=product_id, limit=30)
        if product is None:
            await callback.answer()
            await answer_or_edit(callback, "Товар не найден.", reply_markup=_back_main_markup())
            return
        lines = [f"<b>📋 {escape(service_name(product, 'ru'))}</b>", ""]
        if not items:
            lines.append("Доступов пока нет.")
        else:
            for item in items:
                lines.append(f"#{item.id} • {escape(item.title or 'Доступ')} • {item.status.value}")
        await callback.answer()
        await answer_or_edit(
            callback,
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin:inventory:product:{product_id}")]]
            ),
        )

    @router.callback_query(F.data.startswith("admin:inventory:delete_list:"))
    async def admin_inventory_delete_list_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            items = await list_inventory_items(session, product_id=product_id, limit=30)
        available_items = [item for item in items if item.status.value == "available"]
        await callback.answer()
        if not available_items:
            await answer_or_edit(
                callback,
                "Нет доступных позиций для удаления.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin:inventory:product:{product_id}")]]
                ),
            )
            return
        await answer_or_edit(callback, "<b>🗑 Выберите доступ для удаления</b>", reply_markup=_inventory_delete_markup(product_id, available_items))

    @router.callback_query(F.data.startswith("admin:inventory:delete:"))
    async def admin_inventory_delete_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        item_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            item = await get_inventory_item(session, item_id)
            if item is None:
                await callback.answer()
                await answer_or_edit(callback, "Доступ не найден.", reply_markup=_back_main_markup())
                return
            product_id = item.product_id
            await soft_delete_inventory_item(session, item)
            await session.commit()
        await callback.answer("Удалено")
        callback.data = f"admin:inventory:product:{product_id}"
        await admin_inventory_product_handler(callback)

    @router.message(AdminState.waiting_user_lookup)
    async def admin_user_lookup_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        async with app.session_factory() as session:
            users = await find_users(session, message.text or "", limit=10)
        if not users:
            await message.answer("Пользователи не найдены.")
            return
        rows = [
            [
                InlineKeyboardButton(
                    text=f"{user_display_name(user)} • {format_money(user.balance, 'сум')}",
                    callback_data=f"admin:user:view:{user.id}",
                )
            ]
            for user in users
        ]
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:main")])
        await state.clear()
        await message.answer("<b>Результаты поиска</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    @router.message(AdminState.waiting_balance_adjustment)
    async def admin_balance_adjustment_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        amount = _parse_amount(message.text)
        if amount is None:
            await message.answer("Введите сумму числом больше нуля.")
            return
        delta = amount if data.get("adjustment_mode") == "add" else -amount
        async with app.session_factory() as session:
            user = await get_user_by_id(session, int(data["user_id"]))
            if user is None:
                await message.answer("Пользователь не найден.")
                await state.clear()
                return
            transaction = await apply_admin_adjustment(
                session,
                user_id=user.id,
                delta=delta,
                source="admin_adjustment",
                source_id=message.from_user.id,
            )
            if transaction is None:
                await message.answer("Недостаточно средств на балансе клиента.")
                return
            await session.commit()
            orders_count = await count_orders_for_user(session, user.id)
            sign = "+" if delta > 0 else "-"
            change_text = format_money(abs(delta), "сум")
        await state.clear()
        await _send_user_message(
            user.telegram_id,
            "🛠 Баланс изменён администратором\n\n"
            f"Изменение: {sign}{change_text}\n"
            f"Новый баланс: {format_money(user.balance, 'сум')}",
        )
        await message.answer(_admin_user_text(user, orders_count), reply_markup=_admin_user_markup(user.id))

    @router.message(AdminState.waiting_user_message)
    async def admin_user_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            user = await get_user_by_id(session, int(data["user_id"]))
        if user is None:
            await message.answer("Пользователь не найден.")
            await state.clear()
            return
        await _send_user_message(user.telegram_id, message.text or "")
        await state.clear()
        await message.answer("Сообщение отправлено клиенту.")

    @router.message(AdminState.waiting_inventory_item)
    async def admin_inventory_item_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        text = (message.text or "").strip()
        if not text:
            await message.answer("Отправьте текст с данными доступа.")
            return

        title_lines: list[str] = []
        content_lines: list[str] = []
        instruction_lines: list[str] = []
        bucket = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            normalized = line.lower().rstrip(":")
            if normalized in {"название", "title"}:
                bucket = "title"
                continue
            if normalized in {"код / доступ", "код/доступ", "код", "доступ", "content"}:
                bucket = "content"
                continue
            if normalized in {"инструкция", "instruction"}:
                bucket = "instruction"
                continue
            if bucket == "title":
                title_lines.append(raw_line)
            elif bucket == "content":
                content_lines.append(raw_line)
            elif bucket == "instruction":
                instruction_lines.append(raw_line)

        title = "\n".join(title_lines).strip()
        content = "\n".join(content_lines).strip()
        instruction = "\n".join(instruction_lines).strip()
        if not title or not content:
            await message.answer("Нужны как минимум поля «Название» и «Код / доступ».")
            return

        async with app.session_factory() as session:
            product = await get_product(session, int(data["product_id"]))
            if product is None:
                await message.answer("Товар не найден.")
                await state.clear()
                return
            await add_inventory_item(
                session,
                product_id=product.id,
                title=title,
                content=content,
                instruction=instruction,
            )
            await session.commit()
        await state.clear()
        await message.answer(
            "✅ Готовый доступ добавлен\n\n"
            f"💎 Сервис: {service_name(product, 'ru')}\n"
            "📦 Тип: Готовый доступ\n"
            "📌 Статус: Доступен"
        )

    @router.message(AdminState.waiting_order_delivery)
    async def admin_order_delivery_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        delivery_content = (message.text or "").strip()
        if not delivery_content:
            await message.answer("Отправьте текст с данными заказа.")
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            order = await get_order_by_id(session, int(data["order_id"]))
            if order is None:
                await message.answer("Заказ не найден.")
                await state.clear()
                return
            await complete_order_delivery(
                session,
                order,
                delivery_content=delivery_content,
                admin_id=message.from_user.id,
            )
            await session.commit()
            language = await _user_lang(session, order)
        await state.clear()
        if order.user is not None:
            await _send_user_message(
                order.user.telegram_id,
                _delivery_user_text(language, order, delivery_content),
                reply_markup=_user_order_markup(language, order),
            )
        await message.answer("Заказ выполнен и отправлен клиенту.")

    @router.message(AdminState.waiting_product_create)
    async def admin_product_create_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        parts = [part.strip() for part in (message.text or "").split("|")]
        if len(parts) != 6:
            await message.answer("Неверный формат.")
            return
        code, category_code, price, currency, workflow_type, delivery_type = parts
        async with app.session_factory() as session:
            category = await session.scalar(select(Category).where(Category.code == category_code))
            product = Product(
                code=code,
                category_id=category.id if category else None,
                price=price,
                currency=currency,
                workflow_type=workflow_type,
                delivery_type=delivery_type,
                status=ProductStatus.HIDDEN,
                sort_order=100,
            )
            session.add(product)
            await session.flush()
            for lang in ("ru", "uz", "en"):
                session.add(ProductTranslation(product_id=product.id, language=Language(lang), name=code, description=""))
            await session.commit()
        await state.clear()
        await message.answer("Товар создан.")

    @router.message(AdminState.waiting_product_price)
    async def admin_product_price_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            product = await get_product(session, int(data["product_id"]))
            if product is None:
                await message.answer("Товар не найден.")
                return
            product.price = message.text.strip()
            await session.commit()
        await state.clear()
        await message.answer("Цена обновлена.")

    @router.message(AdminState.waiting_product_sort)
    async def admin_product_sort_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        if not (message.text or "").strip().isdigit():
            await message.answer("Нужно целое число.")
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            product = await get_product(session, int(data["product_id"]))
            if product is None:
                await message.answer("Товар не найден.")
                return
            product.sort_order = int(message.text.strip())
            await session.commit()
        await state.clear()
        await message.answer("Порядок обновлён.")

    @router.message(AdminState.waiting_product_translation)
    async def admin_product_translation_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        name, _, description = (message.text or "").partition("||")
        async with app.session_factory() as session:
            translation = await session.scalar(
                select(ProductTranslation).where(
                    ProductTranslation.product_id == int(data["product_id"]),
                    ProductTranslation.language == data["language"],
                )
            )
            if translation is None:
                await message.answer("Перевод не найден.")
                return
            translation.name = name.strip() or translation.name
            translation.description = description.strip()
            await session.commit()
        await state.clear()
        await message.answer("Перевод товара обновлён.")

    @router.message(AdminState.waiting_product_photo, F.photo)
    async def admin_product_photo_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            product = await get_product(session, int(data["product_id"]))
            if product is None:
                await message.answer("Товар не найден.")
                return
            product.photo_file_id = message.photo[-1].file_id
            await session.commit()
        await state.clear()
        await message.answer("Фото товара обновлено.")

    @router.message(AdminState.waiting_payment_create)
    async def admin_payment_create_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        parts = [part.strip() for part in (message.text or "").split("|")]
        if len(parts) != 3:
            await message.answer("Неверный формат.")
            return
        code, provider_type, admin_title = parts
        async with app.session_factory() as session:
            payment = PaymentMethod(code=code, provider_type=PaymentProviderType(provider_type), admin_title=admin_title, credentials="", sort_order=100, is_active=True)
            session.add(payment)
            await session.flush()
            for lang in ("ru", "uz", "en"):
                session.add(PaymentMethodTranslation(payment_method_id=payment.id, language=Language(lang), title=admin_title, instructions="{credentials}"))
            await session.commit()
        await state.clear()
        await message.answer("Метод оплаты создан.")

    @router.message(AdminState.waiting_payment_credentials)
    async def admin_payment_credentials_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            payment = await get_payment_method(session, int(data["payment_id"]))
            if payment is None:
                await message.answer("Метод не найден.")
                return
            payment.credentials = message.text or ""
            await session.commit()
        await state.clear()
        await message.answer("Реквизиты обновлены.")

    @router.message(AdminState.waiting_payment_sort)
    async def admin_payment_sort_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        if not (message.text or "").strip().isdigit():
            await message.answer("Нужно число.")
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            payment = await get_payment_method(session, int(data["payment_id"]))
            if payment is None:
                await message.answer("Метод не найден.")
                return
            payment.sort_order = int(message.text.strip())
            await session.commit()
        await state.clear()
        await message.answer("Порядок обновлён.")

    @router.message(AdminState.waiting_payment_translation)
    async def admin_payment_translation_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        title, _, instructions = (message.text or "").partition("||")
        async with app.session_factory() as session:
            translation = await session.scalar(
                select(PaymentMethodTranslation).where(
                    PaymentMethodTranslation.payment_method_id == int(data["payment_id"]),
                    PaymentMethodTranslation.language == data["language"],
                )
            )
            if translation is None:
                await message.answer("Перевод не найден.")
                return
            translation.title = title.strip() or translation.title
            translation.instructions = instructions.strip() or translation.instructions
            await session.commit()
        await state.clear()
        await message.answer("Перевод оплаты обновлён.")

    @router.message(AdminState.waiting_payment_photo, F.photo)
    async def admin_payment_photo_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            payment = await get_payment_method(session, int(data["payment_id"]))
            if payment is None:
                await message.answer("Метод не найден.")
                return
            payment.photo_file_id = message.photo[-1].file_id
            await session.commit()
        await state.clear()
        await message.answer("Фото оплаты обновлено.")

    @router.message(AdminState.waiting_text_translation)
    async def admin_text_translation_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            translation = await session.scalar(
                select(TextTranslation).where(
                    TextTranslation.text_id == int(data["text_id"]),
                    TextTranslation.language == data["language"],
                )
            )
            if translation is None:
                await message.answer("Перевод не найден.")
                return
            translation.value = message.text or ""
            await session.commit()
        await state.clear()
        await message.answer("Текст обновлён.")

    @router.message(AdminState.waiting_button_create)
    async def admin_button_create_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        parts = [part.strip() for part in (message.text or "").split("|")]
        if len(parts) != 8:
            await message.answer("Неверный формат.")
            return
        code, action_type, action_value, row, sort, text_ru, text_uz, text_en = parts
        data = await state.get_data()
        async with app.session_factory() as session:
            button = LayoutButton(layout_id=int(data["layout_id"]), code=code, action_type=ButtonActionType(action_type), action_value=action_value, row_index=int(row), sort_order=int(sort), style="default", is_active=True)
            session.add(button)
            await session.flush()
            for lang, value in {"ru": text_ru, "uz": text_uz, "en": text_en}.items():
                session.add(LayoutButtonTranslation(button_id=button.id, language=Language(lang), text=value))
            await session.commit()
        await state.clear()
        await message.answer("Кнопка создана.")

    @router.message(AdminState.waiting_button_translation)
    async def admin_button_translation_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            translation = await session.scalar(
                select(LayoutButtonTranslation).where(
                    LayoutButtonTranslation.button_id == int(data["button_id"]),
                    LayoutButtonTranslation.language == data["language"],
                )
            )
            if translation is None:
                await message.answer("Перевод кнопки не найден.")
                return
            translation.text = message.text or ""
            await session.commit()
        await state.clear()
        await message.answer("Текст кнопки обновлён.")

    @router.message(AdminState.waiting_button_action)
    async def admin_button_action_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        raw = [part.strip() for part in (message.text or "").split("|", 1)]
        if len(raw) != 2:
            await message.answer("Используйте формат type|value.")
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            button = await get_button(session, int(data["button_id"]))
            if button is None:
                await message.answer("Кнопка не найдена.")
                return
            button.action_type = ButtonActionType(raw[0])
            button.action_value = raw[1]
            await session.commit()
        await state.clear()
        await message.answer("Назначение кнопки обновлено.")

    @router.message(AdminState.waiting_button_row)
    async def admin_button_row_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        if not (message.text or "").strip().isdigit():
            await message.answer("Нужно число.")
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            button = await get_button(session, int(data["button_id"]))
            if button is None:
                await message.answer("Кнопка не найдена.")
                return
            button.row_index = int(message.text.strip())
            await session.commit()
        await state.clear()
        await message.answer("Ряд кнопки обновлён.")

    @router.message(AdminState.waiting_button_sort)
    async def admin_button_sort_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        if not (message.text or "").strip().isdigit():
            await message.answer("Нужно число.")
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            button = await get_button(session, int(data["button_id"]))
            if button is None:
                await message.answer("Кнопка не найдена.")
                return
            button.sort_order = int(message.text.strip())
            await session.commit()
        await state.clear()
        await message.answer("Порядок кнопки обновлён.")

    return router
