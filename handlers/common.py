from __future__ import annotations

from decimal import Decimal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.models import Category, Order, PaymentMethod, Product
from services.catalog import (
    category_name,
    product_name,
    product_type_icon,
    product_type_label,
    service_name,
)
from services.payments import payment_title
from utils.formatting import format_money, order_display_number, order_status_label


def _back_label(language: str) -> str:
    return "◀ Назад" if language == "ru" else ("◀ Orqaga" if language == "uz" else "◀ Back")


def _menu_label(language: str) -> str:
    return "🏠 Меню" if language == "ru" else ("🏠 Menyu" if language == "uz" else "🏠 Menu")


def _support_label(language: str) -> str:
    return "💬 Задать вопрос" if language == "ru" else ("💬 Savol berish" if language == "uz" else "💬 Support")


def _history_label(language: str) -> str:
    return "📜 История баланса" if language == "ru" else ("📜 Balans tarixi" if language == "uz" else "📜 Balance history")


def _orders_label(language: str) -> str:
    return "📦 Мои заказы" if language == "ru" else ("📦 Buyurtmalarim" if language == "uz" else "📦 My orders")


def _topup_label(language: str) -> str:
    return "💳 Пополнить баланс" if language == "ru" else ("💳 Balansni to'ldirish" if language == "uz" else "💳 Top up balance")


def _promo_label(language: str) -> str:
    return "🎁 Промокод" if language == "ru" else ("🎁 Promokod" if language == "uz" else "🎁 Promo code")


def _promo_invoice_label(language: str) -> str:
    return "Есть промокод" if language == "ru" else ("Promokod bor" if language == "uz" else "I have a promo code")


def _cancel_label(language: str) -> str:
    return "Отменить" if language == "ru" else ("Bekor qilish" if language == "uz" else "Cancel")


def _subscribe_label(language: str) -> str:
    return "Подписаться" if language == "ru" else ("Obuna bo'lish" if language == "uz" else "Subscribe")


def _check_subscription_label(language: str) -> str:
    return "Проверить подписку" if language == "ru" else ("Obunani tekshirish" if language == "uz" else "Check subscription")


def language_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang:uz"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
            ]
        ]
    )


def simple_back_markup(callback_data: str = "menu:main", text: str = "◀ Назад") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=callback_data)]])


def categories_markup(categories: list[Category], language: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=category_name(category, language), callback_data=f"catalog:cat:{category.id}")]
        for category in categories
    ]
    custom_text = "Другое" if language == "ru" else ("Boshqa" if language == "uz" else "Other")
    rows.append([InlineKeyboardButton(text=custom_text, callback_data="custom:open")])
    rows.append([InlineKeyboardButton(text=_back_label(language), callback_data="menu:main", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def products_markup(products: list[Product], language: str, category_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=service_name(product, language), callback_data=f"product:view:{product.id}")]
        for product in products
    ]
    rows.append(
        [
            InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main"),
            InlineKeyboardButton(text=_back_label(language), callback_data=f"catalog:back:{category_id}", style="danger"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_markup(
    product: Product,
    language: str,
    include_trial: bool = False,
    support_url: str | None = None,
    variants: list[Product] | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if variants and len(variants) > 1:
        for variant in variants:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{product_type_icon(variant)} {product_type_label(variant, language)} — {format_money(variant.price, variant.currency)}",
                        callback_data=f"product:variant:{variant.id}",
                        style="success",
                    )
                ]
            )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Оформить" if language == "ru" else ("Rasmiylashtirish" if language == "uz" else "Proceed"),
                    callback_data=f"product:buy:{product.id}",
                    style="success",
                )
            ]
        )
    if include_trial:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Попробовать 3 дня бесплатно" if language == "ru" else ("3 kun bepul sinab ko'rish" if language == "uz" else "Try 3 days for free"),
                    callback_data="product:trial",
                )
            ]
        )
    if support_url:
        rows.append([InlineKeyboardButton(text=_support_label(language), url=support_url)])
    if product.category_id:
        rows.append(
            [
                InlineKeyboardButton(text=_back_label(language), callback_data=f"catalog:cat:{product.category_id}", style="danger"),
                InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main"),
            ]
        )
    else:
        rows.append([InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def gmail_choice_markup(product_id: int, language: str) -> InlineKeyboardMarkup:
    use_saved = "На этот Gmail" if language == "ru" else ("Shu Gmail" if language == "uz" else "Use this Gmail")
    use_other = "Другой Gmail" if language == "ru" else ("Boshqa Gmail" if language == "uz" else "Other Gmail")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=use_saved, callback_data=f"chatgpt:saved:{product_id}", style="success")],
            [InlineKeyboardButton(text=use_other, callback_data=f"chatgpt:other:{product_id}", style="danger")],
            [InlineKeyboardButton(text=_back_label(language), callback_data=f"product:view:{product_id}", style="danger")],
        ]
    )


def subscription_check_markup(product_id: int, language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_subscribe_label(language), url="https://t.me/")],
            [InlineKeyboardButton(text=_check_subscription_label(language), callback_data=f"trial:check:{product_id}", style="success")],
            [InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")],
        ]
    )


def payment_methods_markup(
    order_id: int,
    methods: list[PaymentMethod],
    language: str,
    support_url: str | None = None,
    allow_promo: bool = False,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=payment_title(method, language), callback_data=f"order:pay:{order_id}:{method.id}", style="success")]
        for method in methods
    ]
    rows.append(
        [
            InlineKeyboardButton(text=_cancel_label(language), callback_data=f"order:cancel:{order_id}", style="danger"),
            InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main"),
        ]
    )
    if support_url:
        rows.append([InlineKeyboardButton(text=_support_label(language), url=support_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_back_markup(order_id: int, language: str, support_url: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=_cancel_label(language), callback_data=f"order:cancel:{order_id}", style="danger"),
            InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main"),
        ]
    ]
    if support_url:
        rows.append([InlineKeyboardButton(text=_support_label(language), url=support_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_markup(language: str, support_url: str | None = None, include_promo: bool = True) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=_topup_label(language), callback_data="profile:topup")],
        [InlineKeyboardButton(text=_orders_label(language), callback_data="profile:orders")],
        [InlineKeyboardButton(text=_history_label(language), callback_data="profile:history")],
    ]
    if support_url:
        rows.append([InlineKeyboardButton(text=_support_label(language), url=support_url)])
    if include_promo:
        rows.append([InlineKeyboardButton(text=_promo_label(language), callback_data="profile:promo")])
    rows.append([InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_detail_markup(order: Order, language: str, support_url: str | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=order_status_label(order.status.value, language), callback_data="noop")]]
    if support_url:
        rows.append([InlineKeyboardButton(text=_support_label(language), url=support_url)])
    rows.append([InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def completed_orders_markup(orders: list[Order], language: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{order_display_number(order)} • {order.product_name_snapshot}", callback_data=f"order:detail:{order.id}")]
        for order in orders
    ]
    rows.append([InlineKeyboardButton(text=_back_label(language), callback_data="menu:profile", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def topup_amounts_markup(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="80 000 сум", callback_data="topup:amount:80000")],
            [InlineKeyboardButton(text="150 000 сум", callback_data="topup:amount:150000")],
            [InlineKeyboardButton(text="200 000 сум", callback_data="topup:amount:200000")],
            [InlineKeyboardButton(text="✍️ Другая сумма", callback_data="topup:amount:custom")],
            [InlineKeyboardButton(text=_back_label(language), callback_data="menu:profile", style="danger")],
            [InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")],
        ]
    )


def topup_methods_markup(language: str, amount: Decimal | int | str) -> InlineKeyboardMarkup:
    amount_value = str(int(Decimal(str(amount))))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Click", callback_data=f"topup:method:{amount_value}:click")],
            [InlineKeyboardButton(text="Humo / Uzcard", callback_data=f"topup:method:{amount_value}:card")],
            [InlineKeyboardButton(text="Криптовалюта", callback_data=f"topup:method:{amount_value}:usdt_trc20")],
            [InlineKeyboardButton(text=_back_label(language), callback_data="profile:topup", style="danger")],
            [InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")],
        ]
    )


def topup_receipt_markup(language: str, amount: Decimal | int | str) -> InlineKeyboardMarkup:
    amount_value = str(int(Decimal(str(amount))))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_back_label(language), callback_data=f"topup:back:{amount_value}", style="danger")],
            [InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")],
        ]
    )


def insufficient_balance_markup(language: str, back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_topup_label(language), callback_data="profile:topup")],
            [InlineKeyboardButton(text=_back_label(language), callback_data=back_callback, style="danger")],
            [InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")],
        ]
    )


def purchase_confirmation_markup(checkout_id: int, language: str) -> InlineKeyboardMarkup:
    yes_text = "✅ Да, оплатить" if language == "ru" else ("✅ Ha, to'lash" if language == "uz" else "✅ Yes, pay")
    no_text = "❌ Нет, отменить" if language == "ru" else ("❌ Yo'q, bekor qilish" if language == "uz" else "❌ No, cancel")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=yes_text, callback_data=f"checkout:pay:{checkout_id}", style="success")],
            [InlineKeyboardButton(text=no_text, callback_data=f"checkout:cancel:{checkout_id}", style="danger")],
            [InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")],
        ]
    )


def ready_access_empty_markup(language: str, product_id: int, support_url: str | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="👤 Личный вариант", callback_data=f"product:view:{product_id}")]]
    if support_url:
        rows.append([InlineKeyboardButton(text=_support_label(language), url=support_url)])
    rows.append([InlineKeyboardButton(text=_back_label(language), callback_data=f"product:view:{product_id}", style="danger")])
    rows.append([InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
