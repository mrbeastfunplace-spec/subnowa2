from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from config import Settings
from db.base import ButtonActionType, InventoryStatus, Language, PaymentProviderType, ProductStatus
from db.defaults import DEFAULT_CATEGORIES, DEFAULT_LAYOUTS, DEFAULT_PRODUCTS, DEFAULT_TEXTS, get_default_payment_methods, get_default_settings
from db.models import (
    Base,
    CapCutAccount,
    Category,
    CategoryTranslation,
    ChatGPTWorkspace,
    InventoryItem,
    Layout,
    LayoutButton,
    LayoutButtonTranslation,
    PaymentMethod,
    PaymentMethodTranslation,
    Product,
    ProductPaymentMethod,
    ProductTranslation,
    Setting,
    TextEntry,
    TextTranslation,
)


_CATEGORY_SLUG_MAX_LENGTH = 64
_LEGACY_UI_SYNC_SETTING_KEY = "system.legacy_ui_sync_version"
_LEGACY_UI_SYNC_VERSION = "2026-04-11-legacy-ui-v2"
_REPLACEABLE_TEXT_DEFAULTS: dict[str, dict[str, str]] = {
    "user.main_title": {"ru": "Subnowa", "uz": "Subnowa", "en": "Subnowa"},
    "user.main_body": {"ru": "Выберите раздел ниже.", "uz": "Quyidagi bo'limlardan birini tanlang.", "en": "Choose a section below."},
    "user.catalog_title": {"ru": "Каталог", "uz": "Katalog", "en": "Catalog"},
    "user.profile_title": {"ru": "Профиль", "uz": "Profil", "en": "Profile"},
    "user.no_completed_orders": {
        "ru": "У вас пока нет завершённых заказов.",
        "uz": "Sizda hali yakunlangan buyurtmalar yo'q.",
        "en": "You do not have any completed orders yet.",
    },
    "user.faq_body": {
        "ru": "Оплатите заказ, отправьте чек и дождитесь обработки. История показывает только завершённые заказы.",
        "uz": "Buyurtmani to'lang, chekni yuboring va ishlov berilishini kuting. Tarixda faqat yakunlangan buyurtmalar ko'rinadi.",
        "en": "Pay for the order, send the receipt and wait for processing. History shows completed orders only.",
    },
    "user.payment_rejected": {
        "ru": "Оплата отклонена. Если это ошибка, свяжитесь с поддержкой.",
        "uz": "To'lov rad etildi. Agar bu xato bo'lsa, qo'llab-quvvatlashga yozing.",
        "en": "Payment was rejected. Contact support if this is a mistake.",
    },
    "user.order_cancelled": {"ru": "Заказ отменён.", "uz": "Buyurtma bekor qilindi.", "en": "Order cancelled."},
    "user.stock_empty": {
        "ru": "Склад временно пуст. Свяжитесь с поддержкой или попробуйте позже.",
        "uz": "Ombor vaqtincha bo'sh. Qo'llab-quvvatlashga yozing yoki keyinroq urinib ko'ring.",
        "en": "Stock is currently empty. Contact support or try again later.",
    },
    "user.trial_gmail_prompt": {
        "ru": "Введите Gmail для пробной подписки ChatGPT.",
        "uz": "ChatGPT sinov obunasi uchun Gmail kiriting.",
        "en": "Enter the Gmail address for the ChatGPT trial.",
    },
    "user.trial_already_used": {
        "ru": "Вы уже использовали пробную подписку.",
        "uz": "Siz sinov obunasidan avval foydalangansiz.",
        "en": "You have already used the trial subscription.",
    },
    "user.trial_created": {
        "ru": "Пробная заявка создана и передана администратору.",
        "uz": "Sinov arizasi yaratildi va administratorga yuborildi.",
        "en": "Trial request created and sent to the admin.",
    },
    "user.trial_approved": {
        "ru": "Пробная подписка одобрена.",
        "uz": "Sinov obunasi tasdiqlandi.",
        "en": "Trial subscription approved.",
    },
    "user.trial_rejected": {
        "ru": "Пробная подписка отклонена.",
        "uz": "Sinov obunasi rad etildi.",
        "en": "Trial subscription rejected.",
    },
    "user.chatgpt_gmail_prompt": {
        "ru": "Введите Gmail для оформления ChatGPT Plus/Pro.",
        "uz": "ChatGPT Plus/Pro uchun Gmail kiriting.",
        "en": "Enter the Gmail address for ChatGPT Plus/Pro.",
    },
    "user.chatgpt_saved_gmail_choice": {
        "ru": "Найден Gmail <b>{gmail}</b>. Использовать его или указать другой?",
        "uz": "<b>{gmail}</b> Gmail topildi. Shu manzilni ishlatasizmi yoki boshqasini kiritasizmi?",
        "en": "Found Gmail <b>{gmail}</b>. Use it or enter another one?",
    },
    "user.custom_request_prompt": {
        "ru": "Опишите, какую подписку или товар вы хотите получить.",
        "uz": "Qanday obuna yoki mahsulot kerakligini yozing.",
        "en": "Describe the subscription or product you want.",
    },
    "user.custom_request_created": {
        "ru": "Заявка создана. Администратор рассмотрит её позже.",
        "uz": "Ariza yaratildi. Administrator keyinroq ko'rib chiqadi.",
        "en": "Request created. An admin will review it later.",
    },
    "button.back": {"ru": "Назад", "uz": "Ortga", "en": "Back"},
    "button.menu": {"ru": "Меню", "uz": "Menyu", "en": "Menu"},
    "button.buy": {"ru": "Купить", "uz": "Sotib olish", "en": "Buy"},
    "button.history": {"ru": "История", "uz": "Tarix", "en": "History"},
    "button.use_saved_gmail": {"ru": "Использовать этот Gmail", "uz": "Shu Gmailni ishlatish", "en": "Use this Gmail"},
    "button.use_other_gmail": {"ru": "Указать другой Gmail", "uz": "Boshqa Gmail kiritish", "en": "Use another Gmail"},
}
_REPLACEABLE_LAYOUT_DEFAULTS: dict[tuple[str, str], dict[str, str]] = {
    ("main_menu", "catalog"): {"ru": "Подписки", "uz": "Obunalar", "en": "Subscriptions"},
    ("main_menu", "profile"): {"ru": "Профиль", "uz": "Profil", "en": "Profile"},
    ("main_menu", "languages"): {"ru": "Языки", "uz": "Tillar", "en": "Languages"},
    ("main_menu", "support"): {"ru": "Поддержка", "uz": "Qo'llab-quvvatlash", "en": "Support"},
    ("main_menu", "about"): {"ru": "О нас", "uz": "Biz haqimizda", "en": "About"},
    ("main_menu", "faq"): {"ru": "FAQ", "uz": "FAQ", "en": "FAQ"},
    ("main_menu", "admin_profile"): {"ru": "ChatGPT Plus ChatGPT", "uz": "ChatGPT Plus ChatGPT", "en": "ChatGPT Plus ChatGPT"},
}


def _slugify(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = ascii_value.strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]+", "", slug)
    return re.sub(r"-{2,}", "-", slug).strip("-")


def _should_replace_seed_text(current_value: str | None, replaceable_default: str | None = None) -> bool:
    normalized = (current_value or "").strip()
    if not normalized:
        return True
    if replaceable_default is None:
        return False
    return normalized == replaceable_default.strip()


def _fit_slug(value: str) -> str:
    return value[:_CATEGORY_SLUG_MAX_LENGTH].strip("-")


def _slug_with_suffix(base: str, suffix: str | None = None) -> str:
    fitted_base = _fit_slug(base) or "category"
    if not suffix:
        return fitted_base

    fitted_suffix = _slugify(suffix)
    if not fitted_suffix:
        return fitted_base

    max_base_length = _CATEGORY_SLUG_MAX_LENGTH - len(fitted_suffix) - 1
    trimmed_base = _fit_slug(fitted_base[:max_base_length]) or "category"
    return f"{trimmed_base}-{fitted_suffix}"


def _category_slug_sources(category: Category | None, item: dict | None = None) -> list[str]:
    sources: list[str] = []
    if item is not None:
        explicit_slug = item.get("slug")
        if isinstance(explicit_slug, str):
            sources.append(explicit_slug)

        code = item.get("code")
        if isinstance(code, str):
            sources.append(code)

        translations = item.get("translations")
        if isinstance(translations, dict):
            for lang_code in (Language.EN.value, Language.UZ.value, Language.RU.value):
                payload = translations.get(lang_code)
                if isinstance(payload, dict):
                    name = payload.get("name")
                    if isinstance(name, str):
                        sources.append(name)

    if category is not None:
        if category.slug:
            sources.append(category.slug)
        sources.append(category.code)
        for translation in category.translations:
            if translation.name:
                sources.append(translation.name)

    return sources


def _claim_category_slug(
    category: Category,
    used_slugs: dict[str, Category],
    sources: list[str],
    *,
    preserve_current: bool,
) -> str:
    current_slug = _slugify(category.slug)
    if current_slug and used_slugs.get(current_slug) is category:
        used_slugs.pop(current_slug, None)

    ordered_sources: list[str] = []
    if preserve_current and current_slug:
        ordered_sources.append(current_slug)
    ordered_sources.extend(source for source in sources if source)

    base_slug = ""
    for source in ordered_sources:
        candidate = _slugify(source)
        if candidate:
            base_slug = candidate
            break

    if not base_slug:
        base_slug = _slugify(category.code) or "category"

    candidate = _fit_slug(base_slug) or "category"
    owner = used_slugs.get(candidate)
    if owner in (None, category):
        used_slugs[candidate] = category
        return candidate

    code_slug = _slugify(category.code)
    if code_slug:
        candidate = _slug_with_suffix(base_slug, code_slug)
        owner = used_slugs.get(candidate)
        if owner in (None, category):
            used_slugs[candidate] = category
            return candidate

    counter = 2
    while True:
        candidate = _slug_with_suffix(base_slug, str(counter))
        owner = used_slugs.get(candidate)
        if owner in (None, category):
            used_slugs[candidate] = category
            return candidate
        counter += 1


async def initialize_database(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await ensure_runtime_schema(session, settings)
        await seed_settings(session, settings)
        await seed_categories(session)
        await normalize_category_slugs(session)
        await seed_products(session)
        await ensure_commerce_products(session)
        await seed_payment_methods(session)
        await seed_texts(session)
        await seed_layouts(session, settings)
        await ensure_admin_shortcuts(session)
        await sync_legacy_ui_once(session, settings)
        await seed_product_payment_links(session)
        await migrate_legacy_capcut_inventory(session)
        await session.commit()


async def ensure_runtime_schema(session: AsyncSession, settings: Settings) -> None:
    await _ensure_column(
        session,
        "users",
        "first_name",
        {
            "postgresql": "VARCHAR(255) NOT NULL DEFAULT ''",
            "sqlite": "TEXT NOT NULL DEFAULT ''",
            "default": "TEXT NOT NULL DEFAULT ''",
        },
    )
    await _ensure_column(
        session,
        "users",
        "balance",
        {
            "postgresql": "NUMERIC(12, 2) NOT NULL DEFAULT 0",
            "sqlite": "NUMERIC(12, 2) NOT NULL DEFAULT 0",
            "default": "NUMERIC(12, 2) NOT NULL DEFAULT 0",
        },
    )
    await _ensure_column(
        session,
        "users",
        "is_blocked",
        {
            "postgresql": "BOOLEAN NOT NULL DEFAULT FALSE",
            "sqlite": "BOOLEAN NOT NULL DEFAULT 0",
            "default": "BOOLEAN NOT NULL DEFAULT 0",
        },
    )
    await _ensure_column(
        session,
        "products",
        "service_name",
        {
            "postgresql": "VARCHAR(255) NOT NULL DEFAULT ''",
            "sqlite": "TEXT NOT NULL DEFAULT ''",
            "default": "TEXT NOT NULL DEFAULT ''",
        },
    )
    await _ensure_column(
        session,
        "products",
        "product_type",
        {
            "postgresql": "VARCHAR(64) NOT NULL DEFAULT 'default'",
            "sqlite": "TEXT NOT NULL DEFAULT 'default'",
            "default": "TEXT NOT NULL DEFAULT 'default'",
        },
    )
    await _ensure_column(
        session,
        "orders",
        "service_name_snapshot",
        {
            "postgresql": "VARCHAR(255) NOT NULL DEFAULT ''",
            "sqlite": "TEXT NOT NULL DEFAULT ''",
            "default": "TEXT NOT NULL DEFAULT ''",
        },
    )
    await _ensure_column(
        session,
        "orders",
        "product_type_snapshot",
        {
            "postgresql": "VARCHAR(64) NOT NULL DEFAULT ''",
            "sqlite": "TEXT NOT NULL DEFAULT ''",
            "default": "TEXT NOT NULL DEFAULT ''",
        },
    )
    await _ensure_column(
        session,
        "orders",
        "paid_at",
        {
            "postgresql": "TIMESTAMP WITH TIME ZONE",
            "sqlite": "DATETIME",
            "default": "DATETIME",
        },
    )
    await _ensure_column(
        session,
        "orders",
        "refunded_at",
        {
            "postgresql": "TIMESTAMP WITH TIME ZONE",
            "sqlite": "DATETIME",
            "default": "DATETIME",
        },
    )
    await _ensure_column(
        session,
        "orders",
        "admin_id",
        {
            "postgresql": "BIGINT",
            "sqlite": "BIGINT",
            "default": "BIGINT",
        },
    )
    await _ensure_column(
        session,
        "orders",
        "delivery_content",
        {
            "postgresql": "TEXT",
            "sqlite": "TEXT",
            "default": "TEXT",
        },
    )
    await _ensure_column(
        session,
        "orders",
        "expires_at",
        {
            "postgresql": "TIMESTAMP WITH TIME ZONE",
            "sqlite": "DATETIME",
            "default": "DATETIME",
        },
    )
    await _ensure_column(
        session,
        "chatgpt_workspaces",
        "profile_dir",
        {
            "postgresql": "TEXT",
            "sqlite": "TEXT",
            "default": "TEXT",
        },
    )
    await _ensure_workspace_profile_dirs(session, settings)


async def _ensure_workspace_profile_dirs(session: AsyncSession, settings: Settings) -> None:
    workspaces = (await session.scalars(select(ChatGPTWorkspace))).all()
    for workspace in workspaces:
        if (workspace.profile_dir or "").strip():
            continue
        workspace.profile_dir = str(settings.playwright_profile_root / workspace.workspace_id)


async def _ensure_column(session: AsyncSession, table_name: str, column_name: str, ddl_type: str | dict[str, str]) -> None:
    connection = await session.connection()
    existing_columns = await connection.run_sync(
        lambda sync_connection: {column["name"] for column in inspect(sync_connection).get_columns(table_name)}
    )
    if column_name in existing_columns:
        return
    if isinstance(ddl_type, dict):
        resolved_type = ddl_type.get(connection.dialect.name, ddl_type.get("default"))
    else:
        resolved_type = ddl_type
    if not resolved_type:
        raise RuntimeError(f"Unsupported DDL type mapping for {table_name}.{column_name} on {connection.dialect.name}")
    await session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {resolved_type}"))


async def seed_settings(session: AsyncSession, settings: Settings) -> None:
    for item in get_default_settings(settings):
        row = await session.scalar(select(Setting).where(Setting.key == item["key"]))
        if row is None:
            row = Setting(key=item["key"])
            session.add(row)
        row.value = item["value"]
        row.value_type = item["value_type"]
        row.description = item["description"]


async def seed_categories(session: AsyncSession) -> None:
    categories = (await session.scalars(select(Category))).all()
    categories_by_code = {row.code: row for row in categories}
    used_slugs = {
        normalized_slug: row
        for row in categories
        if (normalized_slug := _slugify(row.slug))
    }

    for item in DEFAULT_CATEGORIES:
        category = categories_by_code.get(item["code"])
        if category is None:
            category = Category(code=item["code"])
            session.add(category)
            categories_by_code[category.code] = category

        category.slug = _claim_category_slug(
            category,
            used_slugs,
            _category_slug_sources(category, item),
            preserve_current=False,
        )
        category.sort_order = item["sort_order"]
        category.is_active = item["is_active"]

        existing = {tr.language.value: tr for tr in category.translations}
        for lang_code, payload in item["translations"].items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = CategoryTranslation(category=category, language=Language(lang_code))
                session.add(translation)
            translation.name = payload["name"]
            translation.description = payload["description"]


async def normalize_category_slugs(session: AsyncSession) -> None:
    categories = (await session.scalars(select(Category))).all()
    used_slugs: dict[str, Category] = {}

    for category in sorted(categories, key=lambda row: (row.id or 0, row.code)):
        category.slug = _claim_category_slug(
            category,
            used_slugs,
            _category_slug_sources(category),
            preserve_current=True,
        )


async def seed_products(session: AsyncSession) -> None:
    categories = {row.code: row for row in (await session.scalars(select(Category))).all()}
    for item in DEFAULT_PRODUCTS:
        product = await session.scalar(select(Product).where(Product.code == item["code"]))
        if product is None:
            product = Product(code=item["code"])
            session.add(product)
            product.category = categories.get(item["category_code"])
            product.status = ProductStatus(item["status"])
            product.delivery_type = item["delivery_type"]
            product.workflow_type = item["workflow_type"]
            product.price = Decimal(item["price"])
            product.currency = item["currency"]
            product.sort_order = item["sort_order"]
            product.show_in_catalog = item["show_in_catalog"]
            product.extra_data = item["extra_data"]

        existing = {tr.language.value: tr for tr in product.translations}
        for lang_code, payload in item["translations"].items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = ProductTranslation(product=product, language=Language(lang_code))
                session.add(translation)
                translation.name = payload["name"]
                translation.description = payload["description"]
                continue
            if not translation.name:
                translation.name = payload["name"]
            if not translation.description:
                translation.description = payload["description"]


async def ensure_commerce_products(session: AsyncSession) -> None:
    categories = {row.code: row for row in (await session.scalars(select(Category))).all()}
    products = {row.code: row for row in (await session.scalars(select(Product))).all()}

    definitions = [
        {
            "code": "chatgpt_plus_month",
            "category_code": "saas",
            "status": ProductStatus.ACTIVE.value,
            "service_name": "ChatGPT Pro",
            "product_type": "personal_account",
            "workflow_type": "chatgpt_manual",
            "delivery_type": "manual",
            "show_in_catalog": True,
            "sort_order": 10,
            "default_price": Decimal("79000.00"),
            "replace_prices": {Decimal("99000.00")},
            "extra_data": {
                "collect_gmail": True,
                "requires_subscription_check": True,
                "variant_group": "chatgpt_pro",
            },
            "translations": {
                "ru": {
                    "name": "ChatGPT Pro",
                    "description": "Подписка ChatGPT Pro с подключением на ваш личный аккаунт.",
                },
                "uz": {
                    "name": "ChatGPT Pro",
                    "description": "ChatGPT Pro obunasini shaxsiy akkauntingizga ulab beramiz.",
                },
                "en": {
                    "name": "ChatGPT Pro",
                    "description": "ChatGPT Pro subscription connected to your personal account.",
                },
            },
        },
        {
            "code": "chatgpt_ready_month",
            "category_code": "saas",
            "status": ProductStatus.ACTIVE.value,
            "service_name": "ChatGPT Pro",
            "product_type": "ready_access",
            "workflow_type": "inventory_auto",
            "delivery_type": "auto",
            "show_in_catalog": False,
            "sort_order": 11,
            "default_price": Decimal("49000.00"),
            "replace_prices": set(),
            "extra_data": {
                "variant_group": "chatgpt_pro",
                "inventory_enabled": True,
            },
            "translations": {
                "ru": {
                    "name": "ChatGPT Pro — Готовый аккаунт",
                    "description": "Готовый доступ ChatGPT Pro с моментальной выдачей после оплаты.",
                },
                "uz": {
                    "name": "ChatGPT Pro — Tayyor akkaunt",
                    "description": "To'lovdan keyin darhol beriladigan tayyor ChatGPT Pro akkaunti.",
                },
                "en": {
                    "name": "ChatGPT Pro — Ready account",
                    "description": "Ready-to-use ChatGPT Pro access delivered right after payment.",
                },
            },
        },
        {
            "code": "capcut_pro_month",
            "category_code": "saas",
            "status": ProductStatus.ACTIVE.value,
            "service_name": "CapCut Pro",
            "product_type": "ready_access",
            "workflow_type": "inventory_auto",
            "delivery_type": "auto",
            "show_in_catalog": False,
            "sort_order": 20,
            "default_price": Decimal("49000.00"),
            "replace_prices": set(),
            "extra_data": {
                "variant_group": "capcut_pro",
                "inventory_enabled": True,
            },
            "translations": {
                "ru": {
                    "name": "CapCut Pro",
                    "description": "CapCut Pro с автоматической выдачей готового доступа.",
                },
                "uz": {
                    "name": "CapCut Pro",
                    "description": "Tayyor kirish bilan avtomatik beriladigan CapCut Pro.",
                },
                "en": {
                    "name": "CapCut Pro",
                    "description": "CapCut Pro with instant ready-access delivery.",
                },
            },
        },
        {
            "code": "capcut_personal_month",
            "category_code": "saas",
            "status": ProductStatus.ACTIVE.value,
            "service_name": "CapCut Pro",
            "product_type": "personal_account",
            "workflow_type": "manual",
            "delivery_type": "manual",
            "show_in_catalog": True,
            "sort_order": 20,
            "default_price": Decimal("79000.00"),
            "replace_prices": set(),
            "extra_data": {
                "variant_group": "capcut_pro",
            },
            "translations": {
                "ru": {
                    "name": "CapCut Pro — Личный аккаунт",
                    "description": "Подключение CapCut Pro на ваш личный аккаунт.",
                },
                "uz": {
                    "name": "CapCut Pro — Shaxsiy akkaunt",
                    "description": "CapCut Pro obunasini shaxsiy akkauntingizga ulab beramiz.",
                },
                "en": {
                    "name": "CapCut Pro — Personal account",
                    "description": "CapCut Pro subscription connected to your personal account.",
                },
            },
        },
        {
            "code": "grok_template",
            "category_code": "saas",
            "status": ProductStatus.ACTIVE.value,
            "service_name": "Super Grok",
            "product_type": "personal_account",
            "workflow_type": "manual",
            "delivery_type": "manual",
            "show_in_catalog": True,
            "sort_order": 40,
            "default_price": Decimal("70000.00"),
            "replace_prices": set(),
            "extra_data": {
                "icon_custom_emoji_id": "5330337435500951363",
            },
            "force_translation_update": True,
            "translations": {
                "ru": {
                    "name": "Super Grok",
                    "description": (
                        "<tg-emoji emoji-id='5330337435500951363'>🤖</tg-emoji> Super Grok — Личный доступ\n"
                        "💰 Цена: 70 000 сум\n"
                        "📅 Срок доступа: 30 дней\n\n"
                        "Что вы получаете:\n"
                        "✅ Доступ к Super Grok на месяц\n"
                        "✅ Возможность пользоваться AI-инструментами для работы, учёбы и повседневных задач\n"
                        "✅ Подходит для генерации идей, текстов, анализа информации и продуктивности\n"
                        "✅ Стабильная работа на весь оплаченный период\n"
                        "✅ Гарантия 30 дней\n"
                        "✅ Техническая поддержка 24/7\n\n"
                        "Этот вариант подойдёт тем, кто хочет использовать Super Grok для быстрых ответов, идей, работы с текстами и удобной помощи в ежедневных задачах."
                    ),
                },
                "uz": {
                    "name": "Super Grok",
                    "description": (
                        "<tg-emoji emoji-id='5330337435500951363'>🤖</tg-emoji> Super Grok — Shaxsiy kirish\n"
                        "💰 Narxi: 70 000 so‘m\n"
                        "📅 Foydalanish muddati: 30 kun\n\n"
                        "Nimalarga ega bo‘lasiz:\n"
                        "✅ Super Grok’dan 1 oy davomida foydalanish\n"
                        "✅ Ish, o‘qish va kundalik vazifalar uchun AI vositalaridan foydalanish imkoniyati\n"
                        "✅ G‘oyalar yaratish, matnlar yozish, ma’lumotlarni tahlil qilish va samaradorlik uchun mos\n"
                        "✅ To‘langan muddat davomida barqaror ishlash\n"
                        "✅ 30 kunlik kafolat\n"
                        "✅ 24/7 texnik yordam\n\n"
                        "Bu variant Super Grok’dan tezkor javoblar, g‘oyalar, matnlar bilan ishlash va kundalik vazifalarda qulay yordam olish uchun foydalanmoqchi bo‘lganlar uchun mos keladi."
                    ),
                },
                "en": {
                    "name": "Super Grok",
                    "description": (
                        "<tg-emoji emoji-id='5330337435500951363'>🤖</tg-emoji> Super Grok — Personal Access\n"
                        "💰 Price: 70,000 UZS\n"
                        "📅 Access period: 30 days\n\n"
                        "What you get:\n"
                        "✅ Access to Super Grok for one month\n"
                        "✅ Ability to use AI tools for work, study, and daily tasks\n"
                        "✅ Suitable for idea generation, writing, information analysis, and productivity\n"
                        "✅ Stable access for the full paid period\n"
                        "✅ 30-day warranty\n"
                        "✅ 24/7 technical support\n\n"
                        "This option is suitable for those who want to use Super Grok for quick answers, ideas, working with texts, and convenient help with everyday tasks."
                    ),
                },
            },
        },
        {
            "code": "adobe_template",
            "category_code": "saas",
            "status": ProductStatus.ACTIVE.value,
            "service_name": "Adobe Creative Cloud",
            "product_type": "personal_account",
            "workflow_type": "manual",
            "delivery_type": "manual",
            "show_in_catalog": True,
            "sort_order": 50,
            "default_price": Decimal("120000.00"),
            "replace_prices": set(),
            "extra_data": {
                "icon_custom_emoji_id": "5357394595594388140",
            },
            "force_translation_update": True,
            "translations": {
                "ru": {
                    "name": "Adobe Creative Cloud",
                    "description": (
                        "<tg-emoji emoji-id='5357394595594388140'>🎨</tg-emoji> Adobe Creative Cloud — Личный доступ\n"
                        "💰 Цена: 120 000 сум\n"
                        "📅 Срок доступа: 4 месяца\n\n"
                        "Что вы получаете:\n"
                        "✅ Доступ к Adobe Creative Cloud для личного использования\n"
                        "✅ Подходит для дизайна, фото, видео и творческих проектов\n"
                        "✅ Возможность работать с популярными инструментами Adobe\n"
                        "✅ Стабильный доступ на весь оплаченный период\n"
                        "✅ Гарантия на срок использования\n"
                        "✅ Техническая поддержка 24/7\n\n"
                        "Этот вариант подойдёт дизайнерам, монтажёрам, SMM-специалистам и всем, кто работает с визуальным контентом и хочет получить удобный доступ к инструментам Adobe без лишних рисков."
                    ),
                },
                "uz": {
                    "name": "Adobe Creative Cloud",
                    "description": (
                        "<tg-emoji emoji-id='5357394595594388140'>🎨</tg-emoji> Adobe Creative Cloud — Shaxsiy kirish\n"
                        "💰 Narxi: 120 000 so‘m\n"
                        "📅 Foydalanish muddati: 4 oy\n\n"
                        "Nimalarga ega bo‘lasiz:\n"
                        "✅ Shaxsiy foydalanish uchun Adobe Creative Cloud’ga kirish\n"
                        "✅ Dizayn, foto, video va ijodiy loyihalar uchun mos\n"
                        "✅ Mashhur Adobe vositalari bilan ishlash imkoniyati\n"
                        "✅ To‘langan muddat davomida barqaror kirish\n"
                        "✅ Foydalanish muddati davomida kafolat\n"
                        "✅ 24/7 texnik yordam\n\n"
                        "Bu variant dizaynerlar, montajchilar, SMM-mutaxassislar va vizual kontent bilan ishlaydigan, Adobe vositalariga qulay va xavfsiz kirishni xohlaydigan foydalanuvchilar uchun mos keladi."
                    ),
                },
                "en": {
                    "name": "Adobe Creative Cloud",
                    "description": (
                        "<tg-emoji emoji-id='5357394595594388140'>🎨</tg-emoji> Adobe Creative Cloud — Personal Access\n"
                        "💰 Price: 120,000 UZS\n"
                        "📅 Access period: 4 months\n\n"
                        "What you get:\n"
                        "✅ Access to Adobe Creative Cloud for personal use\n"
                        "✅ Suitable for design, photo, video, and creative projects\n"
                        "✅ Ability to work with popular Adobe tools\n"
                        "✅ Stable access for the full paid period\n"
                        "✅ Warranty for the access period\n"
                        "✅ 24/7 technical support\n\n"
                        "This option is suitable for designers, video editors, SMM specialists, and anyone working with visual content who wants convenient access to Adobe tools without unnecessary risks."
                    ),
                },
            },
        },
        {
            "code": "google_ai_pro_gemini",
            "category_code": "saas",
            "status": ProductStatus.ACTIVE.value,
            "service_name": "Google AI Pro (Gemini)",
            "product_type": "personal_account",
            "workflow_type": "manual",
            "delivery_type": "manual",
            "show_in_catalog": True,
            "sort_order": 30,
            "default_price": Decimal("70000.00"),
            "replace_prices": set(),
            "extra_data": {
                "icon_custom_emoji_id": "5359758030198031389",
            },
            "force_translation_update": True,
            "translations": {
                "ru": {
                    "name": "Google AI Pro (Gemini)",
                    "description": (
                        "<tg-emoji emoji-id='5359758030198031389'>✨</tg-emoji> Google AI Pro (Gemini) — Личный доступ\n"
                        "💰 Цена: 70 000 сум\n"
                        "📅 Срок доступа: 30 дней\n\n"
                        "Что вы получаете:\n"
                        "✅ Доступ к Google AI Pro на месяц\n"
                        "✅ Возможность пользоваться AI-функциями Gemini для работы и учёбы\n"
                        "✅ Подходит для текстов, поиска идей, планирования и анализа информации\n"
                        "✅ Стабильная работа на весь оплаченный период\n"
                        "✅ Гарантия 30 дней\n"
                        "✅ Техническая поддержка 24/7\n\n"
                        "Этот вариант подойдёт тем, кто хочет попробовать Google AI Pro или использовать возможности Gemini для конкретных задач в течение месяца."
                    ),
                },
                "uz": {
                    "name": "Google AI Pro (Gemini)",
                    "description": (
                        "<tg-emoji emoji-id='5359758030198031389'>✨</tg-emoji> Google AI Pro (Gemini) — Shaxsiy kirish\n"
                        "💰 Narxi: 70 000 so‘m\n"
                        "📅 Foydalanish muddati: 30 kun\n\n"
                        "Nimalarga ega bo‘lasiz:\n"
                        "✅ Google AI Pro’dan 1 oy davomida foydalanish\n"
                        "✅ Ish va o‘qish uchun Gemini AI imkoniyatlaridan foydalanish\n"
                        "✅ Matnlar, g‘oyalar, rejalashtirish va ma’lumotlarni tahlil qilish uchun mos\n"
                        "✅ To‘langan muddat davomida barqaror ishlash\n"
                        "✅ 30 kunlik kafolat\n"
                        "✅ 24/7 texnik yordam\n\n"
                        "Bu variant Google AI Pro’ni sinab ko‘rmoqchi bo‘lgan yoki Gemini imkoniyatlaridan bir oy davomida aniq vazifalar uchun foydalanmoqchi bo‘lganlar uchun mos keladi."
                    ),
                },
                "en": {
                    "name": "Google AI Pro (Gemini)",
                    "description": (
                        "<tg-emoji emoji-id='5359758030198031389'>✨</tg-emoji> Google AI Pro (Gemini) — Personal Access\n"
                        "💰 Price: 70,000 UZS\n"
                        "📅 Access period: 30 days\n\n"
                        "What you get:\n"
                        "✅ Access to Google AI Pro for one month\n"
                        "✅ Ability to use Gemini AI features for work and study\n"
                        "✅ Suitable for writing, idea generation, planning, and information analysis\n"
                        "✅ Stable access for the full paid period\n"
                        "✅ 30-day warranty\n"
                        "✅ 24/7 technical support\n\n"
                        "This option is suitable for those who want to try Google AI Pro or use Gemini features for specific tasks during one month."
                    ),
                },
            },
        },
        {
            "code": "spotify_premium",
            "category_code": "saas",
            "status": ProductStatus.ACTIVE.value,
            "service_name": "Spotify Premium",
            "product_type": "personal_account",
            "workflow_type": "manual",
            "delivery_type": "manual",
            "show_in_catalog": True,
            "sort_order": 60,
            "default_price": Decimal("0.00"),
            "replace_prices": set(),
            "extra_data": {
                "icon_custom_emoji_id": "5346074681004801565",
                "temporarily_unavailable": True,
            },
            "force_translation_update": True,
            "translations": {
                "ru": {
                    "name": "Spotify Premium",
                    "description": (
                        "<tg-emoji emoji-id='5346074681004801565'>🎵</tg-emoji> Spotify Premium — Скоро доступно\n"
                        "📅 Статус: временно недоступен\n\n"
                        "Spotify Premium временно недоступен.\n"
                        "Скоро появится в продаже."
                    ),
                },
                "uz": {
                    "name": "Spotify Premium",
                    "description": (
                        "<tg-emoji emoji-id='5346074681004801565'>🎵</tg-emoji> Spotify Premium — Tez orada mavjud bo‘ladi\n"
                        "📅 Holati: vaqtincha mavjud emas\n\n"
                        "Spotify Premium hozircha mavjud emas.\n"
                        "Tez orada sotuvga chiqadi."
                    ),
                },
                "en": {
                    "name": "Spotify Premium",
                    "description": (
                        "<tg-emoji emoji-id='5346074681004801565'>🎵</tg-emoji> Spotify Premium — Coming Soon\n"
                        "📅 Status: temporarily unavailable\n\n"
                        "Spotify Premium is temporarily unavailable.\n"
                        "It will be available soon."
                    ),
                },
            },
        },
        {
            "code": "claude_ai_month",
            "category_code": "saas",
            "status": ProductStatus.ACTIVE.value,
            "service_name": "Claude AI Pro",
            "product_type": "personal_account",
            "workflow_type": "manual",
            "delivery_type": "manual",
            "show_in_catalog": True,
            "sort_order": 35,
            "default_price": Decimal("70000.00"),
            "replace_prices": set(),
            "extra_data": {
                "icon_custom_emoji_id": "",
            },
            "force_translation_update": True,
            "translations": {
                "ru": {
                    "name": "Claude AI Pro",
                    "description": (
                        "👤 Claude AI Pro — Личный доступ\n"
                        "💰 Цена: 70 000 сум\n"
                        "📅 Срок доступа: 30 дней\n\n"
                        "Что вы получаете:\n"
                        "✅ Доступ к Claude AI Pro на месяц\n"
                        "✅ Продвинутый AI-ассистент для работы и учёбы\n"
                        "✅ Поддержка длинных контекстов и сложных задач\n"
                        "✅ Стабильная работа на весь оплаченный период\n"
                        "✅ Гарантия 30 дней\n"
                        "✅ Техническая поддержка 24/7"
                    ),
                },
                "uz": {
                    "name": "Claude AI Pro",
                    "description": (
                        "👤 Claude AI Pro — Shaxsiy kirish\n"
                        "💰 Narxi: 70 000 so'm\n"
                        "📅 Foydalanish muddati: 30 kun\n\n"
                        "Nimalarga ega bo'lasiz:\n"
                        "✅ Claude AI Pro'dan 1 oy davomida foydalanish\n"
                        "✅ Ish va o'qish uchun rivojlangan AI-assistent\n"
                        "✅ Uzun kontekstlar va murakkab vazifalar uchun qo'llab-quvvatlash\n"
                        "✅ To'langan muddat davomida barqaror ishlash\n"
                        "✅ 30 kunlik kafolat\n"
                        "✅ 24/7 texnik yordam"
                    ),
                },
                "en": {
                    "name": "Claude AI Pro",
                    "description": (
                        "👤 Claude AI Pro — Personal Access\n"
                        "💰 Price: 70,000 UZS\n"
                        "📅 Access period: 30 days\n\n"
                        "What you get:\n"
                        "✅ Access to Claude AI Pro for one month\n"
                        "✅ Advanced AI assistant for work and study\n"
                        "✅ Support for long contexts and complex tasks\n"
                        "✅ Stable access for the full paid period\n"
                        "✅ 30-day warranty\n"
                        "✅ 24/7 technical support"
                    ),
                },
            },
        },
    ]

    for item in definitions:
        product = products.get(item["code"])
        if product is None:
            product = Product(code=item["code"])
            session.add(product)
            products[item["code"]] = product

        product.category = categories.get(item["category_code"])
        product.status = ProductStatus(item["status"])
        product.service_name = item["service_name"]
        product.product_type = item["product_type"]
        product.workflow_type = item["workflow_type"]
        product.delivery_type = item["delivery_type"]
        product.currency = product.currency or "UZS"
        product.sort_order = item["sort_order"]
        product.show_in_catalog = item["show_in_catalog"]

        current_price = Decimal(str(product.price or 0))
        if product.id is None or current_price in item["replace_prices"] or current_price <= 0:
            product.price = item["default_price"]

        merged_extra = dict(product.extra_data or {})
        merged_extra.update(item["extra_data"])
        product.extra_data = merged_extra

        force_translation_update = bool(item.get("force_translation_update"))
        existing = {tr.language.value: tr for tr in product.translations}
        for lang_code, payload in item["translations"].items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = ProductTranslation(product=product, language=Language(lang_code))
                session.add(translation)
            if force_translation_update or not translation.name:
                translation.name = payload["name"]
            if force_translation_update or not translation.description:
                translation.description = payload["description"]


async def migrate_legacy_capcut_inventory(session: AsyncSession) -> None:
    product = await session.scalar(select(Product).where(Product.code == "capcut_pro_month"))
    if product is None:
        return

    existing_legacy_ids = {
        item_id
        for item_id in (
            await session.scalars(
                select(InventoryItem.legacy_capcut_account_id).where(InventoryItem.legacy_capcut_account_id.is_not(None))
            )
        ).all()
        if item_id is not None
    }
    legacy_accounts = (await session.scalars(select(CapCutAccount))).all()
    for account in legacy_accounts:
        if account.id in existing_legacy_ids:
            continue
        item = InventoryItem(
            product_id=product.id,
            title="CapCut Pro",
            content=f"Логин: {account.login}\nПароль: {account.password}",
            instruction="Если у вас уже открыт другой аккаунт CapCut, сначала выйдите из него, затем войдите по этим данным.",
            status=InventoryStatus.SOLD if account.is_used else InventoryStatus.AVAILABLE,
            created_at=account.created_at,
            sold_to_user_id=account.issued_to_user_id,
            sold_order_id=account.issued_order_id,
            sold_at=account.issued_at,
            legacy_capcut_account_id=account.id,
        )
        session.add(item)


async def seed_payment_methods(session: AsyncSession) -> None:
    for item in get_default_payment_methods():
        payment = await session.scalar(select(PaymentMethod).where(PaymentMethod.code == item["code"]))
        if payment is None:
            payment = PaymentMethod(code=item["code"])
            session.add(payment)
            payment.provider_type = PaymentProviderType(item["provider_type"])
            payment.admin_title = item["admin_title"]
            payment.credentials = item["credentials"]
            payment.sort_order = item["sort_order"]
            payment.is_active = True

        existing = {tr.language.value: tr for tr in payment.translations}
        for lang_code, payload in item["translations"].items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = PaymentMethodTranslation(payment_method=payment, language=Language(lang_code))
                session.add(translation)
                translation.title = payload["title"]
                translation.instructions = payload["instructions"]
                continue
            if not translation.title:
                translation.title = payload["title"]
            if not translation.instructions:
                translation.instructions = payload["instructions"]


async def seed_texts(session: AsyncSession, force_codes: set[str] | None = None) -> None:
    for code, payload in DEFAULT_TEXTS.items():
        force_restore = force_codes is not None and code in force_codes
        entry = await session.scalar(select(TextEntry).where(TextEntry.code == code))
        if entry is None:
            entry = TextEntry(code=code)
            session.add(entry)

        entry.group_name = payload["group"]
        entry.description = payload["description"]

        existing = {tr.language.value: tr for tr in entry.translations}
        for lang_code, value in payload["translations"].items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = TextTranslation(text_entry=entry, language=Language(lang_code))
                session.add(translation)
                translation.value = value
                continue
            replaceable_default = _REPLACEABLE_TEXT_DEFAULTS.get(code, {}).get(lang_code)
            if force_restore or _should_replace_seed_text(translation.value, replaceable_default):
                translation.value = value


async def seed_layouts(session: AsyncSession, settings: Settings, force_codes: set[str] | None = None) -> None:
    replacement_map = {
        "__SUPPORT_URL__": settings.support_url,
        "__ABOUT_URL__": settings.about_url,
        "__REVIEW_URL__": settings.review_url,
    }

    for item in DEFAULT_LAYOUTS:
        force_restore = force_codes is not None and item["code"] in force_codes
        layout = await session.scalar(select(Layout).where(Layout.code == item["code"]))
        if layout is None:
            layout = Layout(code=item["code"])
            session.add(layout)
            layout.title = item["title"]
            layout.scope = item["scope"]
            layout.is_active = True
        elif force_restore:
            layout.title = item["title"]
            layout.scope = item["scope"]
            layout.is_active = True

        existing_buttons = {button.code: button for button in layout.buttons}
        for button_data in item["buttons"]:
            button = existing_buttons.get(button_data["code"])
            if button is None:
                button = LayoutButton(layout=layout, code=button_data["code"])
                session.add(button)
                button.action_type = ButtonActionType(button_data["action_type"])
                button.action_value = replacement_map.get(button_data["action_value"], button_data["action_value"])
                button.style = button_data["style"]
                button.row_index = button_data["row_index"]
                button.sort_order = button_data["sort_order"]
                button.is_active = True
            else:
                if force_restore or not button.action_value:
                    button.action_type = ButtonActionType(button_data["action_type"])
                    button.action_value = replacement_map.get(button_data["action_value"], button_data["action_value"])
                if force_restore or not button.style:
                    button.style = button_data["style"]
                if force_restore:
                    button.row_index = button_data["row_index"]
                    button.sort_order = button_data["sort_order"]
                    button.is_active = True

            existing_translations = {tr.language.value: tr for tr in button.translations}
            for lang_code, text in button_data["translations"].items():
                translation = existing_translations.get(lang_code)
                if translation is None:
                    translation = LayoutButtonTranslation(button=button, language=Language(lang_code))
                    session.add(translation)
                    translation.text = text
                    continue
                replaceable_default = _REPLACEABLE_LAYOUT_DEFAULTS.get((item["code"], button_data["code"]), {}).get(lang_code)
                if force_restore or _should_replace_seed_text(translation.text, replaceable_default):
                    translation.text = text


async def ensure_admin_shortcuts(session: AsyncSession) -> None:
    layout_id = await session.scalar(select(Layout.id).where(Layout.code == "admin_main"))
    if layout_id is None:
        return

    existing_buttons = {
        button.code: button
        for button in (
            await session.scalars(select(LayoutButton).where(LayoutButton.layout_id == layout_id))
        ).all()
    }
    desired_buttons = [
        {
            "code": "topups",
            "action_value": "admin:topups",
            "row_index": 0,
            "sort_order": 15,
            "text": "Заявки на пополнение",
        },
        {
            "code": "inventory",
            "action_value": "admin:inventory",
            "row_index": 2,
            "sort_order": 15,
            "text": "Готовые доступы",
        },
        {
            "code": "users",
            "action_value": "admin:users",
            "row_index": 3,
            "sort_order": 15,
            "text": "Пользователи",
        },
        {
            "code": "chatgpt_accounts",
            "action_value": "admin:chatgpt_accounts",
            "row_index": 3,
            "sort_order": 20,
            "text": "ChatGPT аккаунты",
        },
        {
            "code": "broadcasts",
            "action_value": "admin:broadcasts",
            "row_index": 4,
            "sort_order": 10,
            "text": "Рассылка",
        },
    ]

    for item in desired_buttons:
        button = existing_buttons.get(item["code"])
        if button is None:
            button = LayoutButton(
                layout_id=layout_id,
                code=item["code"],
                action_type=ButtonActionType.CALLBACK,
                action_value=item["action_value"],
                style="default",
                row_index=item["row_index"],
                sort_order=item["sort_order"],
                is_active=True,
            )
            session.add(button)
            await session.flush()
            existing_buttons[item["code"]] = button
        translation = await session.scalar(
            select(LayoutButtonTranslation).where(
                LayoutButtonTranslation.button_id == button.id,
                LayoutButtonTranslation.language == Language.RU,
            )
        )
        if translation is None:
            translation = LayoutButtonTranslation(button_id=button.id, language=Language.RU, text=item["text"])
            session.add(translation)
        elif not translation.text:
            translation.text = item["text"]


async def sync_legacy_ui_once(session: AsyncSession, settings: Settings) -> None:
    marker = await session.scalar(select(Setting).where(Setting.key == _LEGACY_UI_SYNC_SETTING_KEY))
    if marker is not None and marker.value == _LEGACY_UI_SYNC_VERSION:
        return

    await seed_texts(session, force_codes=set(DEFAULT_TEXTS))
    await seed_layouts(session, settings, force_codes={item["code"] for item in DEFAULT_LAYOUTS})

    if marker is None:
        marker = Setting(key=_LEGACY_UI_SYNC_SETTING_KEY)
        session.add(marker)
    marker.value = _LEGACY_UI_SYNC_VERSION
    marker.value_type = "string"
    marker.description = "One-time legacy UI sync marker"


async def seed_product_payment_links(session: AsyncSession) -> None:
    products = {row.code: row for row in (await session.scalars(select(Product))).all()}
    payments = {row.code: row for row in (await session.scalars(select(PaymentMethod))).all()}
    existing_pairs = {
        (row.product_id, row.payment_method_id)
        for row in (await session.scalars(select(ProductPaymentMethod))).all()
    }

    link_map = {
        "chatgpt_plus_month": ["click", "card", "usdt_trc20"],
        "chatgpt_ready_month": ["click", "card", "usdt_trc20"],
        "capcut_pro_month": ["click", "card", "usdt_trc20"],
        "capcut_personal_month": ["click", "card"],
        "google_ai_pro_gemini": [],
        "grok_template": [],
        "adobe_template": [],
        "spotify_premium": [],
        "claude_ai_month": [],
    }

    for product_code, payment_codes in link_map.items():
        product = products.get(product_code)
        if product is None:
            continue
        for index, payment_code in enumerate(payment_codes, start=1):
            payment = payments.get(payment_code)
            if payment is None:
                continue
            if (product.id, payment.id) in existing_pairs:
                continue
            link = ProductPaymentMethod(product=product, payment_method=payment)
            session.add(link)
            link.sort_order = index * 10
            existing_pairs.add((product.id, payment.id))

    managed_codes = {"google_ai_pro_gemini", "grok_template", "adobe_template", "spotify_premium", "claude_ai_month"}
    managed_product_ids = {
        product.id: {payments[code].id for code in link_map[product_code] if code in payments}
        for product_code in managed_codes
        if (product := products.get(product_code)) is not None and product.id is not None
    }
    for link in list((await session.scalars(select(ProductPaymentMethod))).all()):
        desired_payment_ids = managed_product_ids.get(link.product_id)
        if desired_payment_ids is not None and link.payment_method_id not in desired_payment_ids:
            await session.delete(link)
