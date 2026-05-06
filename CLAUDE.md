# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Before making any edits to this codebase, read this file in full. It is the single source of truth for project structure and architecture. Do not read multiple files trying to reconstruct the architecture — it is documented here.**

---

## Running the bot

```bash
python bot_app.py
```

`app.py` exists but immediately delegates to `bot_app.py` — it is dead legacy code. Never edit `app.py`.

### Required `.env` variables

```
BOT_TOKEN=...
DATABASE_URL=sqlite+aiosqlite:///bot.db   # or postgresql+asyncpg://...
ADMIN_IDS=7716923294                       # comma-separated
```

Optional vars: `SUPPORT_URL`, `ABOUT_URL`, `REVIEW_URL`, `REQUIRED_CHANNEL`, `TRIAL_DURATION_DAYS`, `PAYMENT_WINDOW_HOURS`, `CHATGPT_WORKSPACES_JSON`, `PLAYWRIGHT_HEADLESS`, etc. See `config.py:Settings`.

---

## Architecture overview

### Entry point flow

`bot_app.py:main()` → loads `Settings` → creates SQLAlchemy engine → calls `db/bootstrap.py:initialize_database()` → creates aiogram `Bot` + `Dispatcher` → registers routers → starts polling.

### AppContext

`services/context.py:AppContext` is a dataclass holding `settings: Settings` and `session_factory: async_sessionmaker[AsyncSession]`. It is passed to every router builder and cascades into handlers and services. This is how handlers access the database and configuration.

### Routers

Each module exposes a `build_*_router(app: AppContext, bot: Bot) -> Router` function. Registered in `bot_app.py` in this order:

| Builder | Module | Handles |
|---|---|---|
| `build_admin_router` | `admin/router.py` | Admin panel (products, payments, texts, layouts, orders, users, stock) |
| `build_admin_workspace_router` | `handlers/admin_workspace.py` | ChatGPT workspace management from admin |
| `build_admin_broadcast_router` | `handlers/admin_broadcast.py` | Mass broadcast to all users |
| `build_catalog_router` | `handlers/catalog.py` | User-facing product catalog and checkout |
| `build_profile_router` | `handlers/profile_v2.py` | User profile, order history, balance top-up |
| `build_start_router` | `handlers/start.py` | /start, language selection, channel subscription gate |

### Database layer (`db/`)

- `db/base.py` — `Base` (SQLAlchemy `DeclarativeBase`) + all enums (`OrderStatus`, `Language`, `ProductStatus`, `PaymentProviderType`, `ChatGPTWorkspaceStatus`, etc.)
- `db/models.py` — all ORM models (see key models below)
- `db/bootstrap.py` — `initialize_database()` runs on every startup: creates tables, runs column migrations via `_ensure_column()`, then seeds/updates default data (categories, products, payment methods, texts, layouts)
- `db/session.py` — `create_engine_and_session()` returns `(engine, async_sessionmaker)`
- `db/defaults.py` — default seed data constants

**Key models:** `User`, `Product`, `Category`, `Order`, `OrderStatusHistory`, `PaymentMethod`, `InventoryItem`, `CapCutAccount`, `Topup`, `BalanceTransaction`, `CheckoutSession`, `ChatGPTWorkspace`, `Broadcast`, `TextEntry`, `Layout`, `LayoutButton` — all in `db/models.py`.

All translatable entities (`Category`, `Product`, `PaymentMethod`, `TextEntry`, `LayoutButton`) have a companion `*Translation` model with a `language` field (RU/UZ/EN).

### Services (`services/`)

Business logic lives here, not in handlers. Key services:

- `services/orders.py` — order creation, status transitions
- `services/payments.py` — payment proof handling, balance deductions
- `services/catalog.py` — product/category queries
- `services/users.py` — user upsert, blocking
- `services/inventory.py` — inventory item assignment for `inventory_auto` workflow
- `services/purchases.py` — purchase flow orchestration
- `services/checkout.py` — `CheckoutSession` management
- `services/balance.py` — balance top-up requests
- `services/topups.py` — topup approval/rejection
- `services/admin.py` — admin-side business logic
- `services/broadcast_service.py` — fan-out message sending
- `services/capcut.py` — CapCut account cleanup loop (background task)
- `services/texts.py` — fetching localised `TextEntry` values from DB
- `services/buttons.py` — building keyboards from `Layout`/`LayoutButton` DB records
- `services/workspace_router.py` — `WorkspaceRouter`: selects an available `ChatGPTWorkspaceConfig`
- `services/workspace_registry_service.py` — DB-backed workspace CRUD
- `services/chatgpt_workspace_onboarding_service.py` — Playwright onboarding flow
- `services/chatgpt_invite_service.py` — Playwright invite flow
- `services/settings.py` — reading/writing the `Setting` key-value table

### Automation (`automation/`)

Playwright-based automation for ChatGPT workspace operations:

- `automation/playwright_runner.py` — `PlaywrightRunner`: runs invite/validate operations headlessly; result type `PlaywrightInviteResult`
- `automation/selectors.py` — all CSS/XPath selectors used by the runner (change here, not in the runner)
- `automation/create_auth_state.py` / `automation/create_auth_state_runner.py` — interactive auth-state capture

### Payments (`payments/`)

- `payments/base.py` — `PaymentProvider` dataclass with `render_instructions()`
- `payments/providers.py` — provider-specific logic

### Utilities (`utils/`)

- `utils/translations.py` — `get_text(language, code)` helper
- `utils/formatting.py` — price/date/amount formatters
- `utils/messages.py` — Telegram message send/edit helpers
- `utils/order_numbers.py` — order number generation
- `utils/logger.py` — `get_logger(name)`
- `utils/polling_lock.py` — prevents two bot instances running simultaneously

### FSM states (`states.py`)

Three `StatesGroup` classes: `UserFlowState` (user-facing flows), `AdminState` (admin edit flows), `AdminBroadcastState` (broadcast wizard).

---

## Product and order model

Products have two key fields that control fulfilment:

- `workflow_type`: `manual` | `chatgpt_manual` | `inventory_auto`
- `delivery_type`: `manual` | `auto`

`inventory_auto` products (`chatgpt_ready_month`, `capcut_pro_month`) are fulfilled automatically from `InventoryItem` rows. `chatgpt_manual` products collect a Gmail address and are processed manually by an admin via Playwright invite. `manual` products require admin action with no automation.

`product.extra_data` (JSON) carries product-specific flags: `collect_gmail`, `inventory_enabled`, `variant_group`, `temporarily_unavailable`, `icon_custom_emoji_id`.

---

## Database migrations

There are no Alembic migrations. Schema changes are applied at startup in `db/bootstrap.py:ensure_runtime_schema()` using `ALTER TABLE … ADD COLUMN` guarded by `_ensure_column()`. Add new columns there when extending the schema.

---

## Deployment

Railway deployment is auto-detected via `RAILWAY_PROJECT_ID` / `RAILWAY_ENVIRONMENT` / `RAILWAY_SERVICE_ID` env vars. On Railway, persistent paths are `/data/chrome_profiles`, `/data/auth_state`, `/data/auth_profiles`, `/data/playwright_debug`.

Multi-workspace ChatGPT config is passed as `CHATGPT_WORKSPACES_JSON` (JSON array with `id`, `name`, `workspace_url`, `max_users`, `enabled`).
