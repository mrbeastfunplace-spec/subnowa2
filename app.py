from bot_app import run as _run_new_app

if __name__ == '__main__':
    _run_new_app()
    raise SystemExit

import asyncio
import os
import atexit
import sqlite3
import random
import string
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

if os.name == "nt":
    import msvcrt
else:
    import fcntl


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = "8640666329:AAEvZDhBO72GVrnZI37y8bG3PRpV3yvNCGE"

ADMIN_IDS = [7716923294]

SUPPORT_URL = "https://t.me/subnowa_supportbot"
ABOUT_URL = "https://subnowa.site"
REVIEW_URL = "https://t.me/subbowaotzib"
REQUIRED_CHANNEL = "@UZB_TREND_MUCIQALAR_BASS_HIT"

DB_PATH = "bot.db"
POLLING_LOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".polling.lock")

CARD_NUMBER = "9860100126034816"
CLICK_NUMBER = "+998"
USDT_TRC20_ADDRESS = "TUr3m7sAWpiysQs5S1jQkbxcvJARqAD8Rs"
CLICK_QR_IMAGE_PATH = r"C:/bot/subnowa_bot/media/click.png.jpg"

CHATGPT_PLUS_PRICE_UZS = 99000
CAPCUT_PRO_PRICE_UZS = 49000

CHATGPT_PLUS_PRICE_USD = 8.5
CAPCUT_PRO_PRICE_USD = 3.49

# Premium custom emoji IDs for button icons
EMOJI_ID_CHATGPT = "5359726582447487916"
EMOJI_ID_CAPCUT = "5364339557712020484"
EMOJI_ID_GROK = "5330337435500951363"
EMOJI_ID_ADOBE = "5357394595594388140"
EMOJI_ID_BACK = "5330337435500951363"
EMOJI_ID_SUPPORT = "5424972470023104089"
EMOJI_ID_GLOBE = "5443038326535759644"
EMOJI_ID_SUBS = "5407076281898512830"
EMOJI_ID_PROFILE = "5447410659077661506"
EMOJI_ID_TELEGRAM = "5424972470023104089"

_polling_lock_handle = None


# =========================================================
# BOT
# =========================================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


# =========================================================
# FSM
# =========================================================

class PromoState(StatesGroup):
    waiting_code = State()


class MultiOrderState(StatesGroup):
    waiting_quantity = State()


class TrialState(StatesGroup):
    waiting_name = State()
    waiting_phone = State()
    waiting_gmail = State()


class ChatGPTMonthLeadState(StatesGroup):
    waiting_gmail_choice = State()
    waiting_gmail = State()


class PaymentState(StatesGroup):
    waiting_check = State()


class AdminPanelState(StatesGroup):
    waiting_capcut_account = State()

# =========================================================
# ADMIN BROADCAST STATE
# =========================================================

# State used for admin broadcast messages. Once an admin enters /broadcast,
# the bot will prompt for the message to send. The next message from the admin
# (text, photo, document, etc.) will be copied to all users, then the state
# will be cleared.
class BroadcastState(StatesGroup):
    waiting_message = State()
    waiting_button_type = State()
    waiting_bot_button_text = State()
    waiting_url_button = State()
    waiting_confirm = State()


# =========================================================
# DB
# =========================================================

def get_db():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        full_name TEXT,
        language TEXT DEFAULT '',
        language_selected INTEGER DEFAULT 0,
        created_at TEXT,
        last_seen_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT UNIQUE,
        telegram_id INTEGER,
        product_code TEXT,
        product_name TEXT,
        price_uzs REAL DEFAULT 0,
        price_usd REAL DEFAULT 0,
        payment_method TEXT DEFAULT '',
        status TEXT DEFAULT 'new',
        details TEXT DEFAULT '',
        created_at TEXT,
        expires_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS capcut_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT,
        password TEXT,
        is_used INTEGER DEFAULT 0,
        used_by INTEGER DEFAULT 0,
        used_at TEXT DEFAULT ''
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS promo_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        discount_percent REAL DEFAULT 0,
        discount_amount REAL DEFAULT 0,
        is_active INTEGER DEFAULT 1
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS multi_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        username TEXT,
        full_name TEXT,
        service_name TEXT,
        quantity INTEGER,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS custom_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        username TEXT,
        full_name TEXT,
        request_name TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS free_trials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT UNIQUE,
        telegram_id INTEGER,
        username TEXT,
        full_name TEXT,
        phone TEXT,
        gmail TEXT,
        status TEXT DEFAULT 'on_review',
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()

    # Add additional columns for subscription reminders. These columns may
    # already exist; if so, SQLite will raise an exception which we catch
    # silently. orders.expires_at is already created in the initial schema,
    # but reminder_sent is new. free_trials receives expires_at and
    # reminder_sent. We perform these ALTER TABLE commands here so that
    # existing databases are upgraded when the bot starts.
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE orders ADD COLUMN reminder_sent INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE users ADD COLUMN language_selected INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE users ADD COLUMN last_seen_at TEXT")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE free_trials ADD COLUMN username TEXT")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE free_trials ADD COLUMN expires_at TEXT")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE free_trials ADD COLUMN reminder_sent INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cur.execute(
            """
            UPDATE users
            SET
                language = COALESCE(language, ''),
                last_seen_at = COALESCE(last_seen_at, created_at, ?)
            """,
            (now_str(),)
        )
    except Exception:
        pass
    conn.commit()
    conn.close()


def now_dt():
    return datetime.now()


def now_str():
    return now_dt().strftime("%Y-%m-%d %H:%M:%S")


def acquire_polling_lock() -> bool:
    global _polling_lock_handle

    if _polling_lock_handle is not None:
        return True

    handle = open(POLLING_LOCK_PATH, "a+", encoding="utf-8")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write("0")
            handle.flush()

        handle.seek(0)
        if os.name == "nt":
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        handle.seek(0)
        handle.write(str(os.getpid()).ljust(16))
        handle.flush()
        _polling_lock_handle = handle
        return True
    except OSError:
        handle.close()
        return False


def release_polling_lock():
    global _polling_lock_handle

    if _polling_lock_handle is None:
        return

    try:
        _polling_lock_handle.seek(0)
        if os.name == "nt":
            msvcrt.locking(_polling_lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(_polling_lock_handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        try:
            _polling_lock_handle.close()
        finally:
            _polling_lock_handle = None


atexit.register(release_polling_lock)


def generate_order_number() -> str:
    return "#" + "".join(random.choices(string.digits, k=10))


def format_price_uzs(value: float) -> str:
    return f"{int(value):,}".replace(",", " ")


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def table_has_column(table_name: str, column_name: str) -> bool:
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(f"PRAGMA table_info({table_name})")
        columns = cur.fetchall()
        return any(column[1] == column_name for column in columns)
    finally:
        conn.close()


def normalize_language(language: str | None) -> str:
    return language if language in {"ru", "uz", "en"} else "ru"


def has_selected_language(user_id: int) -> bool:
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT language_selected FROM users WHERE telegram_id = ?",
            (user_id,)
        )
        row = cur.fetchone()
    except Exception:
        row = None
    conn.close()
    return bool(row and row[0])


def touch_user_activity(user_id: int):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE users SET last_seen_at = ? WHERE telegram_id = ?",
            (now_str(), user_id)
        )
        conn.commit()
    finally:
        conn.close()


def is_valid_gmail(value: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@gmail\.com", value.strip(), flags=re.IGNORECASE))


def extract_gmail_from_text(value: str | None) -> str:
    if not value:
        return ""

    match = re.search(r"([A-Za-z0-9._%+-]+@gmail\.com)", value, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def get_last_chatgpt_gmail(telegram_id: int) -> str:
    conn = get_db()
    cur = conn.cursor()
    latest_gmail = ""
    latest_created_at = ""

    try:
        cur.execute(
            """
            SELECT details, created_at
            FROM orders
            WHERE telegram_id = ? AND product_code = 'chatgpt_plus_1m'
            ORDER BY id DESC
            LIMIT 10
            """,
            (telegram_id,)
        )
        for details, created_at in cur.fetchall():
            gmail = extract_gmail_from_text(details)
            if gmail:
                latest_gmail = gmail
                latest_created_at = created_at or ""
                break

        cur.execute(
            """
            SELECT gmail, created_at
            FROM free_trials
            WHERE telegram_id = ? AND gmail IS NOT NULL AND gmail != ''
            ORDER BY id DESC
            LIMIT 1
            """,
            (telegram_id,)
        )
        trial_row = cur.fetchone()
        if trial_row:
            trial_gmail, trial_created_at = trial_row
            if trial_gmail and (not latest_created_at or (trial_created_at or "") > latest_created_at):
                latest_gmail = trial_gmail
    finally:
        conn.close()

    return latest_gmail


def get_main_menu_text(user_id: int) -> str:
    main_title = strip_tg_emoji_tags(t(user_id, "main_title"))
    main_text = strip_tg_emoji_tags(t(user_id, "main_text")).format(
        ABOUT_URL=ABOUT_URL,
        REVIEW_URL=REVIEW_URL,
    )
    return f"<b>{main_title}</b>\n\n{main_text}"


def add_user_if_not_exists(user_id: int, username: str | None, full_name: str) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE telegram_id = ?", (user_id,))
    exists = cur.fetchone()
    if exists:
        conn.close()
        return False

    cur.execute("""
    INSERT INTO users (
        telegram_id, username, full_name, language,
        language_selected, created_at, last_seen_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, username or "", full_name, "", 0, now_str(), now_str()))
    conn.commit()
    conn.close()
    return True


def get_user_language(user_id: int) -> str:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT language FROM users WHERE telegram_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return normalize_language(row[0] if row else None)


def set_user_language(user_id: int, language: str):
    language = normalize_language(language)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE users
        SET language = ?, language_selected = 1, last_seen_at = ?
        WHERE telegram_id = ?
        """,
        (language, now_str(), user_id)
    )
    conn.commit()
    conn.close()


def create_order(
    telegram_id: int,
    product_code: str,
    product_name: str,
    price_uzs: float,
    price_usd: float = 0,
    details: str = ""
) -> str:
    order_number = generate_order_number()
    created_at = now_dt()
    expires_at = created_at + timedelta(minutes=30)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO orders (
        order_number, telegram_id, product_code, product_name,
        price_uzs, price_usd, payment_method, status, details,
        created_at, expires_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        order_number,
        telegram_id,
        product_code,
        product_name,
        price_uzs,
        price_usd,
        "",
        "new",
        details,
        created_at.strftime("%Y-%m-%d %H:%M:%S"),
        expires_at.strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    conn.close()
    return order_number


def get_order(order_number: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT order_number, telegram_id, product_code, product_name,
           price_uzs, price_usd, payment_method, status, details,
           created_at, expires_at
    FROM orders
    WHERE order_number = ?
    """, (order_number,))
    row = cur.fetchone()
    conn.close()
    return row


def update_order_payment_method(order_number: str, payment_method: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    UPDATE orders
    SET payment_method = ?, status = 'waiting_check'
    WHERE order_number = ?
    """, (payment_method, order_number))
    conn.commit()
    conn.close()


def update_order_status(order_number: str, status: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    UPDATE orders
    SET status = ?
    WHERE order_number = ?
    """, (status, order_number))
    conn.commit()
    conn.close()


def get_user_orders(telegram_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT order_number, product_name, price_uzs, status, created_at
    FROM orders
    WHERE telegram_id = ? AND status = 'completed'
    ORDER BY id DESC
    """, (telegram_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_free_capcut_account():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT id, login, password
    FROM capcut_accounts
    WHERE is_used = 0
    ORDER BY id ASC
    LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()
    return row


def mark_capcut_account_used(account_id: int, user_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    UPDATE capcut_accounts
    SET is_used = 1, used_by = ?, used_at = ?
    WHERE id = ?
    """, (user_id, now_str(), account_id))
    conn.commit()
    conn.close()


def add_capcut_account(login: str, password: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO capcut_accounts (login, password, is_used)
    VALUES (?, ?, 0)
    """, (login, password))
    conn.commit()
    conn.close()


def count_free_capcut_accounts() -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM capcut_accounts WHERE is_used = 0")
    count = cur.fetchone()[0]
    conn.close()
    return count

# =========================================================
# SUBSCRIPTION EXPIRY AND REMINDER HELPERS
# =========================================================

def update_order_expiry(order_number: str, days: int):
    """
    Update the expires_at date for a paid order and reset the reminder flag.
    When a subscription is purchased, the order expires in `days` days from
    now and should trigger a reminder before expiry.
    """
    expiry = (now_dt() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE orders
        SET expires_at = ?, reminder_sent = 0
        WHERE order_number = ?
        """,
        (expiry, order_number)
    )
    conn.commit()
    conn.close()


def update_free_trial_expiry(order_number: str, days: int):
    """
    Update the expires_at date for an approved free trial and reset the
    reminder flag. Free trials typically last a few days and require a
    reminder shortly before expiration.
    """
    expiry = (now_dt() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE free_trials
        SET expires_at = ?, reminder_sent = 0
        WHERE order_number = ?
        """,
        (expiry, order_number)
    )
    conn.commit()
    conn.close()


def mark_order_reminded(order_number: str):
    """Mark an order as having received a subscription reminder."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE orders SET reminder_sent = 1 WHERE order_number = ?", (order_number,))
    conn.commit()
    conn.close()


def mark_trial_reminded(order_number: str):
    """Mark a free trial as having received a reminder."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE free_trials SET reminder_sent = 1 WHERE order_number = ?", (order_number,))
    conn.commit()
    conn.close()


def get_due_reminders():
    """
    Return a list of subscriptions that are approaching expiration and have not
    yet received a reminder. Each item in the returned list is a tuple:
    (telegram_id, product_name, days_left, order_number, is_trial). For
    normal paid subscriptions, a reminder is sent 3 days before expiry. For
    free trial subscriptions, a reminder is sent 1 day before expiry.
    """
    results: list[tuple[int, str, int, str, bool]] = []
    current = now_dt()
    conn = get_db()
    cur = conn.cursor()

    # Paid orders with upcoming expiry
    cur.execute(
        """
        SELECT order_number, telegram_id, product_name, expires_at, reminder_sent
        FROM orders
        WHERE status = 'completed' AND reminder_sent = 0 AND expires_at IS NOT NULL AND expires_at != ''
        """
    )
    rows = cur.fetchall()
    for order_number, telegram_id, product_name, expires_at_str, reminder_sent in rows:
        try:
            exp_dt = datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        days_left = (exp_dt - current).days
        if 0 <= days_left <= 3:
            results.append((telegram_id, product_name, days_left, order_number, False))

    # Free trials with upcoming expiry
    cur.execute(
        """
        SELECT order_number, telegram_id, expires_at, reminder_sent, status
        FROM free_trials
        WHERE reminder_sent = 0 AND expires_at IS NOT NULL AND expires_at != ''
        """
    )
    trials = cur.fetchall()
    for order_number, telegram_id, expires_at_str, reminder_sent, status in trials:
        # Only remind trials that have been approved/completed (not on_review)
        if status not in ('approved', 'completed'):
            continue
        try:
            exp_dt = datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        days_left = (exp_dt - current).days
        if 0 <= days_left <= 1:
            results.append((telegram_id, "ChatGPT Plus (trial)", days_left, order_number, True))
    conn.close()
    return results


# =========================================================
# REMINDER LOOP
# =========================================================

async def reminder_loop():
    """
    Periodically check for subscriptions and trials that are close to expiry and
    send a reminder message. This task runs in the background and sleeps
    between checks to reduce load. Reminders are sent three days before
    expiry for paid subscriptions and one day before expiry for free trials.
    """
    while True:
        try:
            due_list = get_due_reminders()
            for telegram_id, product_name, days_left, order_number, is_trial in due_list:
                # Build localized message using the user's language
                lang = get_user_language(telegram_id) or "ru"
                msg_template = TEXTS.get(lang, TEXTS["ru"]).get("reminder_message")
                if msg_template:
                    text = msg_template.format(product=product_name, days=days_left)
                else:
                    text = (
                        f"У вас скоро закончится подписка на {product_name}.\n\n"
                        f"До окончания осталось {days_left} дней. Пожалуйста, продлите подписку."
                    )
                # Provide a button that leads back to the subscriptions menu
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text=t(telegram_id, "btn_subscriptions"), callback_data="open_subscriptions")]
                    ]
                )
                try:
                    await bot.send_message(telegram_id, text, reply_markup=kb)
                except Exception as e:
                    print("Reminder send error", telegram_id, e)
                # Mark the subscription/trial as reminded
                if is_trial:
                    mark_trial_reminded(order_number)
                else:
                    mark_order_reminded(order_number)
        except Exception as e:
            # Log unexpected errors and continue
            print("Error in reminder loop", e)
        # Sleep for 12 hours before checking again
        await asyncio.sleep(60 * 60 * 12)


def add_multi_request(telegram_id: int, username: str, full_name: str, service_name: str, quantity: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO multi_requests (
        telegram_id, username, full_name, service_name, quantity, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (telegram_id, username, full_name, service_name, quantity, now_str()))
    conn.commit()
    conn.close()


def add_custom_request(telegram_id: int, username: str, full_name: str, request_name: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO custom_requests (
        telegram_id, username, full_name, request_name, created_at
    )
    VALUES (?, ?, ?, ?, ?)
    """, (telegram_id, username, full_name, request_name, now_str()))
    conn.commit()
    conn.close()


def create_free_trial(telegram_id: int, username: str, full_name: str, phone: str, gmail: str) -> str:
    order_number = generate_order_number()
    conn = get_db()
    cur = conn.cursor()
    # Calculate expiry 3 days from now for free trial
    expiry = (now_dt() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    if table_has_column("free_trials", "username"):
        cur.execute(
            """
            INSERT INTO free_trials (
                order_number, telegram_id, username, full_name, phone, gmail,
                status, created_at, expires_at, reminder_sent
            )
            VALUES (?, ?, ?, ?, ?, ?, 'on_review', ?, ?, 0)
            """,
            (order_number, telegram_id, username, full_name, phone, gmail, now_str(), expiry)
        )
    else:
        cur.execute(
            """
            INSERT INTO free_trials (
                order_number, telegram_id, full_name, phone, gmail,
                status, created_at, expires_at, reminder_sent
            )
            VALUES (?, ?, ?, ?, ?, 'on_review', ?, ?, 0)
            """,
            (order_number, telegram_id, full_name, phone, gmail, now_str(), expiry)
        )
    conn.commit()
    conn.close()
    return order_number


def get_free_trial(order_number: str):
    conn = get_db()
    cur = conn.cursor()
    if table_has_column("free_trials", "username"):
        cur.execute("""
        SELECT order_number, telegram_id, username, full_name, phone, gmail, status, created_at
        FROM free_trials
        WHERE order_number = ?
        """, (order_number,))
    else:
        cur.execute("""
        SELECT order_number, telegram_id, '' as username, full_name, phone, gmail, status, created_at
        FROM free_trials
        WHERE order_number = ?
        """, (order_number,))
    row = cur.fetchone()
    conn.close()
    return row


def has_used_free_trial(telegram_id: int) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM free_trials WHERE telegram_id = ?",
        (telegram_id,)
    )
    count = cur.fetchone()[0]
    conn.close()
    return count > 0


def update_free_trial_status(order_number: str, status: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    UPDATE free_trials
    SET status = ?
    WHERE order_number = ?
    """, (status, order_number))
    conn.commit()
    conn.close()


# =========================================================
# TEXTS
# =========================================================

TEXTS = {
    "ru": {
        "choose_language": "Выберите язык",
        "main_title": (
            "<tg-emoji emoji-id='5312016504939087914'>💮</tg-emoji> Добро пожаловать в\n"
            "<tg-emoji emoji-id='5332807088940785741'>S</tg-emoji>"
            "<tg-emoji emoji-id='5330069773139059849'>U</tg-emoji>"
            "<tg-emoji emoji-id='5330453760395191684'>B</tg-emoji>"
            "<tg-emoji emoji-id='5359736027080565026'>N</tg-emoji>"
            "<tg-emoji emoji-id='5361583176550457135'>O</tg-emoji>"
            "<tg-emoji emoji-id='5395613572531232916'>V</tg-emoji>"
            "<tg-emoji emoji-id='5226734466315067436'>A</tg-emoji>"
        ),
        "main_text": (
            "│ — удобный доступ к цифровым сервисам без лишних сложностей.\n\n"
            "<tg-emoji emoji-id='5407076281898512830'>🔥</tg-emoji> Здесь можно подключить:\n"
            "<tg-emoji emoji-id='5359726582447487916'>🤖</tg-emoji> ChatGPT PLUS\n"
            "<tg-emoji emoji-id='5364339557712020484'>🎬</tg-emoji> CapCut PRO\n"
            "<tg-emoji emoji-id='5330337435500951363'>🚀</tg-emoji> Grok\n"
            "<tg-emoji emoji-id='5357394595594388140'>🎨</tg-emoji> Adobe и другие сервисы\n\n"
            "<tg-emoji emoji-id='5438176453621457379'>⚡</tg-emoji> Как всё происходит:\n"
            "— выбираете сервис\n"
            "— оформляете заявку\n"
            "— получаете доступ\n\n"
            "<tg-emoji emoji-id='5447410659077661506'>💬</tg-emoji> Мы остаёмся на связи и помогаем на каждом этапе.\n\n"
            "Почему выбирают нас?\n"
            "✅ Быстрое подключение\n"
            "✅ Проверенные решения\n"
            "✅ Поддержка 24/7\n\n"
            "<tg-emoji emoji-id='5443038326535759644'>🌐</tg-emoji> <a href='{ABOUT_URL}'>Сайт</a>\n"
            "<tg-emoji emoji-id='5424972470023104089'>💬</tg-emoji> <a href='{REVIEW_URL}'>Отзывы</a>\n\n"
            "<tg-emoji emoji-id='5469778417045574463'>👇</tg-emoji> Выберите нужный раздел ниже <tg-emoji emoji-id='5469778417045574463'>👇</tg-emoji>"
        ),
        "subscriptions_title": "Выберите сервис",
        "profile_title": "Ваш профиль\n\nВыберите раздел 👇",
        "faq_title": "FAQ",
        "promo_enter": "Введите промокод.",
        "promo_invalid": "К сожалению, такого промокода не существует.",
        "no_orders": "У вас пока нет заказов.",
        "grok_unavailable": "В данный момент недоступно.",
        "capcut_locked": "Этот тариф пока недоступен.",
        "custom_text": "Какую подписку вы хотели бы ещё получить дешевле?",
        "custom_sent": "✅ Ваша заявка принята.\n\nАдминистратор увидит ваш запрос и свяжется с вами при необходимости.",
        "multi_quantity": "Сколько аккаунтов вы хотите?",
        "multi_done": "✅ Ваша заявка принята.\n\nАдминистратор получил информацию о количестве и свяжется с вами.",
        "trial_name": "Введите имя.",
        "trial_phone": "Введите номер телефона.",
        "trial_gmail": "Введите Gmail для подключения ChatGPT.",
        "invalid_gmail": "Введите корректный Gmail в формате name@gmail.com.",
        "trial_subscribe": "Подпишитесь на канал и нажмите кнопку проверки.",
        "trial_not_subscribed": "Вы ещё не подписались на канал.",
        "trial_already_used": "Вы уже использовали пробную подписку.",
        "trial_created": (
            "Заказ: {order_number}\n"
            "Товар: ChatGPT PLUS (3 дня)\n"
            "Стоимость: БЕСПЛАТНО\n"
            "Статус: заказ в обработке"
        ),
        "trial_approved": (
            "✅ Ваш заказ подтверждён.\n\n"
            "Заказ: {order_number}\n"
            "Товар: ChatGPT PLUS (3 дня)\n"
            "Стоимость: БЕСПЛАТНО\n"
            "Срок доступа: 3 дня\n\n"
            "<blockquote>Что будет дальше:\n"
            "1. Мы отправим приглашение на указанный Gmail.\n"
            "2. Вам нужно открыть письмо и подтвердить подключение.\n"
            "3. После подтверждения Plus активируется автоматически.</blockquote>\n\n"
            "Проверьте папки «Входящие» и «Спам». Если письмо не пришло, напишите в поддержку."
        ),
        "trial_rejected": "Пробные подписки закончились. Пожалуйста, выберите другой тип подписки.",
        "chatgpt_month_name": "Введите имя для оформления подписки.",
        "chatgpt_month_gmail_choice": "Мы нашли Gmail, который вы уже использовали для ChatGPT:\n\n<b>{gmail}</b>\n\nОформить подписку на этот Gmail или указать другой?",
        "chatgpt_month_gmail": "Введите Gmail, на который нужно подключить ChatGPT Plus.",
        "chatgpt_month_selected_gmail": "Оформление будет выполнено на Gmail:\n<b>{gmail}</b>\n\nПодпишитесь на канал и нажмите кнопку проверки, чтобы мы создали заказ.",
        "chatgpt_month_subscribe": "Подпишитесь на канал и нажмите кнопку проверки, чтобы мы создали заказ.",
        "chatgpt_month_not_subscribed": "Вы ещё не подписались на канал.",
        "chatgpt_month_continue": "Данные приняты. Заказ сформирован.",
        "order_cancelled": (
            "Заказ {order_number}\n"
            "Статус: отменён\n"
            "Сообщение: заказ отменён"
        ),
        "payment_rejected": (
            "Ваша оплата отклонена.\n\n"
            "Проверьте чек или свяжитесь с техподдержкой."
        ),
        "stock_empty": (
            "В данный момент товар закончился.\n\n"
            "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
        ),
        "chatgpt_menu_text": "<tg-emoji emoji-id='5359726582447487916'>🤖</tg-emoji> ChatGPT Plus/Pro\n\nВыберите тариф ниже 👇",
        "capcut_menu_text": "<tg-emoji emoji-id='5364339557712020484'>🎬</tg-emoji> CapCut Pro\n\nВыберите тариф ниже 👇",
        "chatgpt_1m_text": (
            "💠 ChatGPT PLUS (1 месяц)\n"
            f"💰 Цена: {format_price_uzs(CHATGPT_PLUS_PRICE_UZS)} сум (~750 ₽)\n"
            "────────────────\n"
            "⚙️ Как проходит подключение\n"
            "1. Мы отправляем вам специальную ссылку с приглашением на PLUS в вашу почту\n"
            "2. Вы переходите по ссылке и авторизуетесь в своём аккаунте\n"
            "3. Подписка ChatGPT PLUS активируется автоматически\n"
            "⏱ Срок действия — 25-30 дней с момента активации\n\n"
            "🔐 Безопасность\n"
            "— Без передачи паролей\n"
            "— Вход осуществляется только вами\n"
            "— Используются официальные методы подключения\n\n"
            "— Поддержка на всех этапах подключения 💬\n"
            "— Доступно для пользователей из СНГ и других стран\n"
            "⸻\n"
            "✅ Преимущества\n"
            "✔️ Быстрое подключение\n"
            "✔️ Прозрачные условия\n"
            "✔️ Сопровождение после покупки"
        ),
        "capcut_1m_text": (
            "CapCut Pro (1 месяц)\n"
            f"Цена: {format_price_uzs(CAPCUT_PRO_PRICE_UZS)} сум (~350 ₽)\n\n"
            "<blockquote>"
            "Как проходит подключение:\n"
            "1. Мы выдаём готовый аккаунт после ✅ подтверждения оплаты.\n"
            "2. Вы входите через почту.\n"
            "3. Если у вас уже есть аккаунт, сначала выйдите из него.\n"
            "</blockquote>\n\n"
            "Срок действия — 30 дней."
        ),
        "invoice_title": (
            "Заказ: {order_number}\n"
            "Товар: {product_name}\n"
            "Стоимость: {price_uzs} сум{usd_part}\n\n"
            "Счёт действителен 30 минут.\n"
            "Статус обновится после оплаты."
        ),
        "pay_click_text": (
            "Заказ: {order_number}\n"
            "Товар: {product_name}\n"
            "Стоимость: {price_uzs} сум\n\n"
            "Для оплаты:\n"
            "1. Откройте Click\n"
            "2. Отсканируйте Qrcod\n"
            "3. Ведите сумму {price_uzs} сум\n"
            "4. Подтвердите оплату\n\n"
            "После оплаты отправьте чек в этот бот."
        ),
        "pay_card_text": (
            "Заказ: {order_number}\n"
            "Товар: {product_name}\n"
            "Стоимость: {price_uzs} сум\n\n"
            "Реквизиты:\n"
            "{card_number}\n\n"
            "Введите сумму: {price_uzs} сум\n\n"
            "После оплаты отправьте чек в этот бот."
        ),
        "pay_crypto_text": (
            "Заказ: {order_number}\n"
            "Товар: {product_name}\n"
            "Стоимость: {price_usd}$\n\n"
            "USDT (TRC20):\n"
            "{wallet}\n\n"
            "После оплаты отправьте чек в этот бот."
        ),
        "check_wait": "✅ Чек получен.\n\nМы отправили его администратору на проверку. После подтверждения статус заказа обновится.",
        "chatgpt_paid": (
            "✅ Ваш заказ подтверждён.\n\n"
            "🤖 <b>Что вы оформили:</b>\n"
            "ChatGPT PLUS на 1 месяц\n"
            "Номер заказа: {order_number}\n"
            "Срок доступа: 30 дней\n\n"
            "⚙️ <b>Как пройдёт подключение:</b>\n"
            "Мы подключим подписку на Gmail, который вы указали при оформлении. На эту почту придёт приглашение для активации Plus.\n\n"
            "📩 <b>Что потребуется от вас:</b>\n"
            "1. Открыть письмо на Gmail.\n"
            "2. Принять приглашение.\n"
            "3. Убедиться, что вход выполнен в нужный аккаунт ChatGPT.\n\n"
            "⏳ <b>Сроки:</b>\n"
            "Обычно подключение занимает от нескольких минут до нескольких часов после подтверждения оплаты.\n\n"
            "✨ После активации подписка начнёт работать автоматически. Если письмо не пришло, проверьте папки «Спам» и «Промоакции».\n\n"
            "💬 Если возникнут вопросы или задержка с подключением, напишите в поддержку: "
            f"<a href='{SUPPORT_URL}'>связаться с поддержкой</a>."
        ),
        "capcut_paid": (
            "✅ Ваш заказ подтверждён.\n\n"
            "🎬 <b>Что вы оформили:</b>\n"
            "CapCut Pro на 1 месяц\n"
            "Номер заказа: {order_number}\n"
            "Срок доступа: 30 дней\n\n"
            "🔐 <b>Данные для входа:</b>\n"
            "Логин: {login}\n"
            "Пароль: {password}\n\n"
            "⚙️ <b>Как начать пользоваться:</b>\n"
            "1. Если у вас уже открыт другой аккаунт CapCut, сначала выйдите из него.\n"
            "2. Затем войдите по данным выше.\n"
            "3. После входа Pro-функции будут доступны в аккаунте.\n\n"
            "⏳ <b>Сроки:</b>\n"
            "Доступ уже готов, пользоваться можно сразу после входа.\n\n"
            "💬 Если не получается войти или что-то работает некорректно, напишите в поддержку: "
            f"<a href='{SUPPORT_URL}'>связаться с поддержкой</a>."
        ),
        "history_title": "История заказов",
        "details_title": "Детали заказа",
        "status_completed": "выполнен",
        "status_paid": "оплачен",
        "status_rejected": "отклонён",
        "status_cancelled": "отменён",
        "status_new": "новый",
        "status_waiting_check": "ожидает чек",
        "status_on_review": "на проверке",
        "status_expired": "истёк",
        "label_order": "Заказ",
        "label_product": "Товар",
        "label_amount": "Сумма",
        "label_status": "Статус",
        "label_date": "Дата",
        "btn_subscriptions": "💎 Подписки / тарифы",
        "btn_profile": "👤 Профиль",
        "btn_languages": "🌐 Языки",
        "btn_support": "💬 Задать вопрос",
        "btn_about": "ℹ️ О нас",
        "btn_faq": "❓ FAQ",
        "btn_history": "📜 История заказов",
        "btn_promo": "🎁 Промокод",
        "btn_back": "◀ Назад",
        "btn_menu": "🏠 Меню",
        "btn_chatgpt": "ChatGPT Plus/Pro",
        "btn_capcut": "CapCut Pro",
        "btn_grok": "Super Grok",
        "btn_other": "Другое",
        "btn_buy": "Оформить",
        "btn_use_this_gmail": "На этот",
        "btn_use_other_gmail": "Другой",
        "btn_confirm": "Подтвердить",
        "btn_cancel": "Отменить",
        "btn_question": "У меня есть вопрос",
        "btn_several": "Хочу несколько",
        "btn_trial": "Попробовать 3 дня бесплатно",
        "btn_promocode": "Есть промокод",
        "btn_order_details": "📄 Детали заказа",
        "btn_review": "💬 Оставить отзыв",
        "btn_check_sub": "Проверить подписку",
        "btn_click": "Click",
        "btn_card": "Humo/Visa",
        "btn_crypto": "USDT",
        "btn_custom_own": "Хочу своё",
        "faq_text": (
            "1. Что я получу после оплаты?\n"
            "Вы получите подтверждение заказа и дальнейшие инструкции по подключению.\n\n"
            "2. Как подключается ChatGPT Plus?\n"
            "Мы отправляем приглашение на ваш Gmail, после принятия подписка активируется.\n\n"
            "3. Как подключается CapCut Pro?\n"
            "После подтверждения оплаты вы получаете готовые данные для входа.\n\n"
            "4. Сколько времени занимает подключение?\n"
            "Обычно от нескольких минут до нескольких часов, в зависимости от очереди.\n\n"
            "5. Какие способы оплаты доступны?\n"
            "Click, Humo, Visa и USDT (TRC20).\n\n"
            "6. Нужен ли VPN для использования?\n"
            "В большинстве случаев нет.\n\n"
            "7. Можно ли заказать несколько аккаунтов?\n"
            "Да, используйте кнопку «Хочу несколько», и администратор обработает заявку.\n\n"
            "8. Что делать, если письмо не пришло?\n"
            "Проверьте папки «Спам» и «Промоакции», затем напишите в поддержку.\n\n"
            "9. Можно ли заказать другой сервис?\n"
            "Да, в разделе «Другое» можно оставить заявку на нужную подписку.\n\n"
            "10. Что делать, если возникла проблема после покупки?\n"
            "Напишите в поддержку, указав номер заказа и суть проблемы."
        ),
        # Message sent when a subscription or trial is about to expire
        "reminder_message": (
            "У вас скоро закончится подписка на <b>{product}</b>.\n\n"
            "До окончания осталось <b>{days} дней</b>. Чтобы продолжить пользоваться всеми функциями, продлите подписку на следующий месяц.\n"
            "Нажмите кнопку ниже 👇"
        ),
    },

    "uz": {
        "choose_language": "Tilni tanlang",
        # Use premium custom emojis for the brand name "SUBNOVA" and service icons in Uzbek.
        "main_title": (
            # Each <tg-emoji> wraps a single character; the inner character is the fallback
            "<tg-emoji emoji-id='5332807088940785741'>S</tg-emoji>"
            "<tg-emoji emoji-id='5330069773139059849'>U</tg-emoji>"
            "<tg-emoji emoji-id='5330453760395191684'>B</tg-emoji>"
            "<tg-emoji emoji-id='5359736027080565026'>N</tg-emoji>"
            "<tg-emoji emoji-id='5361583176550457135'>O</tg-emoji>"
            "<tg-emoji emoji-id='5395613572531232916'>V</tg-emoji>"
            "<tg-emoji emoji-id='5226734466315067436'>A</tg-emoji> ga xush kelibsiz"
        ),
        "main_text": (
            "Raqamli xizmatlarga oddiy va qulay ulanish.\n\n"
            "<tg-emoji emoji-id='5407076281898512830'>🔥</tg-emoji> Bu yerda quyidagilar mavjud:\n"
            "<tg-emoji emoji-id='5359726582447487916'>🤖</tg-emoji> ChatGPT PLUS\n"
            "<tg-emoji emoji-id='5364339557712020484'>🎬</tg-emoji> CapCut PRO\n"
            "<tg-emoji emoji-id='5330337435500951363'>🚀</tg-emoji> Grok\n"
            "<tg-emoji emoji-id='5357394595594388140'>🎨</tg-emoji> Adobe va boshqa xizmatlar\n\n"
            "<tg-emoji emoji-id='5438176453621457379'>⚡</tg-emoji> Qanday ishlaydi:\n"
            "— xizmatni tanlaysiz\n"
            "— buyurtma berasiz\n"
            "— kirish ma'lumotini olasiz\n\n"
            "<tg-emoji emoji-id='5447410659077661506'>💬</tg-emoji> Har bir bosqichda yordam beramiz.\n\n"
            "Nega bizni tanlashadi?\n"
            "✅ Tez ulanish\n"
            "✅ Ishonchli yechimlar\n"
            "✅ 24/7 qo'llab-quvvatlash\n\n"
            f"<tg-emoji emoji-id='5443038326535759644'>🌐</tg-emoji> <a href='{ABOUT_URL}'>Sayt</a>\n"
            f"<tg-emoji emoji-id='5424972470023104089'>💬</tg-emoji> <a href='{REVIEW_URL}'>Fikrlar</a>\n\n"
            "👇 Quyidagi bo'limni tanlang 👇"
        ),
        "subscriptions_title": "Xizmatni tanlang",
        "profile_title": "Sizning profilingiz\n\nBo‘limni tanlang 👇",
        "faq_title": "FAQ",
        "promo_enter": "Promokodni kiriting.",
        "promo_invalid": "Afsuski, bunday promokod mavjud emas.",
        "no_orders": "Sizda hali buyurtmalar yo‘q.",
        "grok_unavailable": "Hozircha mavjud emas.",
        "capcut_locked": "Bu tarif hozircha mavjud emas.",
        "custom_text": "Qaysi obunani arzonroq olishni xohlaysiz?",
        "custom_sent": "✅ So‘rovingiz qabul qilindi.\n\nAdministrator uni ko‘rib chiqadi va kerak bo‘lsa bog‘lanadi.",
        "multi_quantity": "Nechta akkaunt kerak?",
        "multi_done": "✅ So‘rovingiz qabul qilindi.\n\nAdministrator miqdor bo‘yicha ma'lumotni oldi va tez orada bog‘lanadi.",
        "trial_name": "Ismingizni kiriting.",
        "trial_phone": "Telefon raqamingizni kiriting.",
        "trial_gmail": "ChatGPT uchun Gmail kiriting.",
        "invalid_gmail": "To‘g‘ri Gmail kiriting: name@gmail.com",
        "trial_subscribe": "Kanalga obuna bo‘ling va tekshirish tugmasini bosing.",
        "trial_not_subscribed": "Siz hali kanalga obuna bo‘lmadingiz.",
        "trial_already_used": "Siz sinov obunasidan allaqachon foydalangansiz.",
        "trial_created": (
            "Buyurtma: {order_number}\n"
            "Mahsulot: ChatGPT PLUS (3 kun)\n"
            "Narx: BEPUL\n"
            "Holat: buyurtma ko‘rib chiqilmoqda"
        ),
        "trial_approved": (
            "✅ Buyurtmangiz tasdiqlandi.\n\n"
            "Buyurtma: {order_number}\n"
            "Mahsulot: ChatGPT PLUS (3 kun)\n"
            "Narx: BEPUL\n"
            "Muddat: 3 kun\n\n"
            "Havola emailingizga yuboriladi. Xatni ochib tasdiqlaganingizdan keyin 3 kunlik Plus faollashadi."
        ),
        "trial_rejected": "Sinov obunalari tugagan. Iltimos, boshqa turdagi obunani tanlang.",
        "chatgpt_month_name": "Obunani rasmiylashtirish uchun ismingizni kiriting.",
        "chatgpt_month_gmail_choice": "Siz ilgari ChatGPT uchun ishlatgan Gmail topildi:\n\n<b>{gmail}</b>\n\nObunani shu Gmailga rasmiylashtiraylikmi yoki boshqasini kiritasizmi?",
        "chatgpt_month_gmail": "ChatGPT Plus ulash uchun Gmail kiriting.",
        "chatgpt_month_selected_gmail": "Obuna quyidagi Gmail uchun rasmiylashtiriladi:\n<b>{gmail}</b>\n\nBuyurtma yaratish uchun kanalga obuna bo‘ling va tekshirish tugmasini bosing.",
        "chatgpt_month_subscribe": "Buyurtma yaratish uchun kanalga obuna bo‘ling va tekshirish tugmasini bosing.",
        "chatgpt_month_not_subscribed": "Siz hali kanalga obuna bo‘lmadingiz.",
        "chatgpt_month_continue": "Ma’lumotlar qabul qilindi. Buyurtma yaratildi.",
        "order_cancelled": (
            "Buyurtma {order_number}\n"
            "Holat: bekor qilindi\n"
            "Xabar: buyurtma bekor qilindi"
        ),
        "payment_rejected": (
            "To‘lovingiz rad etildi.\n\n"
            "Chekni tekshiring yoki yordam xizmatiga murojaat qiling."
        ),
        "stock_empty": (
            "Hozirda mahsulot tugagan.\n\n"
            "Iltimos, keyinroq urinib ko‘ring yoki yordamga yozing."
        ),
        "chatgpt_menu_text": "<tg-emoji emoji-id='5359726582447487916'>🤖</tg-emoji> ChatGPT Plus/Pro\n\nTarifni tanlang 👇",
        "capcut_menu_text": "<tg-emoji emoji-id='5364339557712020484'>🎬</tg-emoji> CapCut Pro\n\nTarifni tanlang 👇",
        "chatgpt_1m_text": (
            "💠 ChatGPT PLUS (1 oy)\n"
            f"💰 Narx: {format_price_uzs(CHATGPT_PLUS_PRICE_UZS)} so‘m (~750 ₽)\n"
            "────────────────\n"
            "⚙️ Ulanish qanday amalga oshadi\n"
            "1. PLUS uchun maxsus taklif havolasini emailingizga yuboramiz\n"
            "2. Havola orqali akkauntingizga kirasiz va tasdiqlaysiz\n"
            "3. ChatGPT PLUS obunasi avtomatik faollashadi\n"
            "⏱ Amal qilish muddati — faollashtirilgan paytdan boshlab 25-30 kun\n\n"
            "🔐 Xavfsizlik\n"
            "— Parollarni topshirish talab qilinmaydi\n"
            "— Tizimga faqat siz o‘zingiz kirasiz\n"
            "— Faqat rasmiy ulash usullaridan foydalaniladi\n\n"
            "— Ulanishning barcha bosqichlarida yordam beramiz 💬\n"
            "— MDH va boshqa davlat foydalanuvchilari uchun mos\n"
            "⸻\n"
            "✅ Afzalliklar\n"
            "✔️ Tez ulanish\n"
            "✔️ Shaffof shartlar\n"
            "✔️ Xariddan keyingi yordam"
        ),
        "capcut_1m_text": (
            "CapCut Pro (1 oy)\n"
            f"Narx: {format_price_uzs(CAPCUT_PRO_PRICE_UZS)} so‘m\n\n"
            "<blockquote>"
            "Ulash tartibi:\n"
            "1. To‘lovdan keyin tayyor akkaunt beriladi.\n"
            "2. Email orqali kirasiz.\n"
            "3. Agar akkauntingiz bo‘lsa, avval undan chiqing.\n"
            "</blockquote>\n\n"
            "Muddati — 30 kun."
        ),
        "invoice_title": (
            "Buyurtma: {order_number}\n"
            "Mahsulot: {product_name}\n"
            "Narx: {price_uzs} so‘m{usd_part}\n\n"
            "Hisob 30 daqiqa amal qiladi.\n"
            "Holat to‘lovdan keyin yangilanadi."
        ),
        "pay_click_text": (
            "Buyurtma: {order_number}\n"
            "Mahsulot: {product_name}\n"
            "Narx: {price_uzs} so‘m\n\n"
            "To‘lov uchun:\n"
            "1. Click ni oching\n"
            "2. qrcodni skanerlang\n"
            "3. Summani kiriting= {price_uzs} so‘m\n"
            "4. To‘lovni tasdiqlang\n\n"
            "To‘lovdan keyin chekni shu botga yuboring."
        ),
        "pay_card_text": (
            "Buyurtma: {order_number}\n"
            "Mahsulot: {product_name}\n"
            "Narx: {price_uzs} so‘m\n\n"
            "Karta raqami:\n"
            "{card_number}\n\n"
            "Summani kiriting: {price_uzs} so‘m\n\n"
            "To‘lovdan keyin chekni shu botga yuboring."
        ),
        "pay_crypto_text": (
            "Buyurtma: {order_number}\n"
            "Mahsulot: {product_name}\n"
            "Narx: {price_usd}$\n\n"
            "USDT (TRC20):\n"
            "{wallet}\n\n"
            "To‘lovdan keyin chekni shu botga yuboring."
        ),
        "check_wait": "✅ Chek qabul qilindi.\n\nAdministrator tekshirganidan keyin buyurtma holati yangilanadi.",
        "chatgpt_paid": (
            "✅ Buyurtmangiz tasdiqlandi.\n\n"
            "🤖 Rasmiylashtirilgan xizmat: ChatGPT PLUS (1 oy)\n"
            "Buyurtma: {order_number}\n"
            "Muddat: 30 kun\n\n"
            "Ulash Gmail'ingiz orqali amalga oshiriladi. Emailga yuborilgan taklifni tasdiqlaganingizdan keyin obuna avtomatik faollashadi.\n\n"
            "Odatda ulash bir necha daqiqadan bir necha soatgacha davom etadi. Agar xat kelmasa, Spam va Promotions bo‘limlarini tekshiring.\n\n"
            f"Muammo bo‘lsa, yordam xizmatiga yozing: <a href='{SUPPORT_URL}'>support</a>."
        ),
        "capcut_paid": (
            "✅ Buyurtmangiz tasdiqlandi.\n\n"
            "🎬 Rasmiylashtirilgan xizmat: CapCut Pro (1 oy)\n"
            "Buyurtma: {order_number}\n"
            "Muddat: 30 kun\n\n"
            "Login: {login}\n"
            "Parol: {password}\n\n"
            "Avval eski akkauntdan chiqing, keyin ushbu ma'lumotlar bilan kiring. Kirganingizdan so‘ng Pro funksiyalar darhol ishlaydi.\n\n"
            f"Muammo bo‘lsa, yordam xizmatiga yozing: <a href='{SUPPORT_URL}'>support</a>."
        ),
        "history_title": "Buyurtmalar tarixi",
        "details_title": "Buyurtma tafsilotlari",
        "status_completed": "bajarildi",
        "status_paid": "to‘landi",
        "status_rejected": "rad etildi",
        "status_cancelled": "bekor qilindi",
        "status_new": "yangi",
        "status_waiting_check": "chek kutilmoqda",
        "status_on_review": "tekshiruvda",
        "status_expired": "muddati tugagan",
        "label_order": "Buyurtma",
        "label_product": "Mahsulot",
        "label_amount": "Summa",
        "label_status": "Holat",
        "label_date": "Sana",
        "btn_subscriptions": "💎 Obunalar / tariflar",
        "btn_profile": "👤 Profil",
        "btn_languages": "🌐 Tillar",
        "btn_support": "💬 Savol berish",
        "btn_about": "ℹ️ Biz haqimizda",
        "btn_faq": "❓ FAQ",
        "btn_history": "📜 Buyurtmalar tarixi",
        "btn_promo": "🎁 Promokod",
        "btn_back": "◀ Orqaga",
        "btn_menu": "🏠 Menyu",
        "btn_chatgpt": "ChatGPT Plus/Pro",
        "btn_capcut": "CapCut Pro",
        "btn_grok": "Super Grok",
        "btn_other": "Boshqa",
        "btn_buy": "Rasmiylashtirish",
        "btn_use_this_gmail": "Shu Gmail",
        "btn_use_other_gmail": "Boshqa",
        "btn_confirm": "Tasdiqlash",
        "btn_cancel": "Bekor qilish",
        "btn_question": "Savolim bor",
        "btn_several": "Bir nechta kerak",
        "btn_trial": "3 kun bepul sinab ko‘rish",
        "btn_promocode": "Promokod bor",
        "btn_order_details": "📄 Buyurtma tafsilotlari",
        "btn_review": "💬 Fikr qoldirish",
        "btn_check_sub": "Obunani tekshirish",
        "btn_click": "Click",
        "btn_card": "Humo/Visa",
        "btn_crypto": "USDT",
        "btn_custom_own": "O‘zimnikini xohlayman",
        "faq_text": (
            "1. To‘lovdan keyin nima olaman?\n"
            "Buyurtma tasdig‘i va ulash bo‘yicha ko‘rsatmalar olasiz.\n\n"
            "2. ChatGPT Plus qanday ulanadi?\n"
            "Gmail'ingizga yuborilgan havolani tasdiqlaysiz va obuna faollashadi.\n\n"
            "3. CapCut Pro qanday beriladi?\n"
            "To‘lov tasdiqlangach, tayyor login va parol yuboriladi.\n\n"
            "4. Ulanish qancha vaqt oladi?\n"
            "Odatda bir necha daqiqadan bir necha soatgacha.\n\n"
            "5. Qanday to‘lov usullari mavjud?\n"
            "Click, Humo, Visa va USDT (TRC20).\n\n"
            "6. VPN kerakmi?\n"
            "Ko‘p hollarda yo‘q.\n\n"
            "7. Bir nechta akkaunt buyurtma qilish mumkinmi?\n"
            "Ha, «Bir nechta kerak» tugmasi orqali so‘rov yuboring.\n\n"
            "8. Xat kelmasa nima qilaman?\n"
            "Spam va Promotions papkalarini tekshiring, keyin yordamga yozing.\n\n"
            "9. Boshqa xizmat buyurtma qilish mumkinmi?\n"
            "Ha, «Boshqa» bo‘limida so‘rov qoldiring.\n\n"
            "10. Xariddan keyin muammo bo‘lsa nima qilaman?\n"
            "Buyurtma raqami bilan yordam xizmatiga yozing."
        ),

        # Xabarnoma: obuna muddati tugash arafasida eslatish
        "reminder_message": (
            "<b>{product}</b> obunangiz muddati tez orada tugaydi.\n\n"
            "Tugashiga <b>{days} kun</b> qoldi. Barcha funksiyalardan foydalanishni davom ettirish uchun obunani yangilang.\n"
            "Quyidagi tugmani bosing 👇"
        ),
    },

    "en": {
        "choose_language": "Choose language",
        # Use premium custom emojis for the brand name "SUBNOVA" and service icons in English.
        "main_title": (
            "Welcome to "
            # Each <tg-emoji> wraps a single character; the inner character is the fallback
            "<tg-emoji emoji-id='5332807088940785741'>S</tg-emoji>"
            "<tg-emoji emoji-id='5330069773139059849'>U</tg-emoji>"
            "<tg-emoji emoji-id='5330453760395191684'>B</tg-emoji>"
            "<tg-emoji emoji-id='5359736027080565026'>N</tg-emoji>"
            "<tg-emoji emoji-id='5361583176550457135'>O</tg-emoji>"
            "<tg-emoji emoji-id='5395613572531232916'>V</tg-emoji>"
            "<tg-emoji emoji-id='5226734466315067436'>A</tg-emoji>"
        ),
        "main_text": (
            "Seamless access to digital services without the hassle.\n\n"
            "<tg-emoji emoji-id='5407076281898512830'>🔥</tg-emoji> Available services:\n"
            "<tg-emoji emoji-id='5359726582447487916'>🤖</tg-emoji> ChatGPT PLUS\n"
            "<tg-emoji emoji-id='5364339557712020484'>🎬</tg-emoji> CapCut PRO\n"
            "<tg-emoji emoji-id='5330337435500951363'>🚀</tg-emoji> Grok\n"
            "<tg-emoji emoji-id='5357394595594388140'>🎨</tg-emoji> Adobe and other services\n\n"
            "<tg-emoji emoji-id='5438176453621457379'>⚡</tg-emoji> How it works:\n"
            "— choose a service\n"
            "— place your order\n"
            "— get access\n\n"
            "<tg-emoji emoji-id='5447410659077661506'>💬</tg-emoji> We help you at every step.\n\n"
            "Why choose us?\n"
            "✅ Fast connection\n"
            "✅ Proven solutions\n"
            "✅ 24/7 support\n\n"
            f"<tg-emoji emoji-id='5443038326535759644'>🌐</tg-emoji> <a href='{ABOUT_URL}'>Website</a>\n"
            f"<tg-emoji emoji-id='5424972470023104089'>💬</tg-emoji> <a href='{REVIEW_URL}'>Reviews</a>\n\n"
            "👇 Choose a section below 👇"
        ),
        "subscriptions_title": "Choose a service",
        "profile_title": "Your profile\n\nChoose a section 👇",
        "faq_title": "FAQ",
        "promo_enter": "Enter promo code.",
        "promo_invalid": "Sorry, this promo code does not exist.",
        "no_orders": "You have no orders yet.",
        "grok_unavailable": "Currently unavailable.",
        "capcut_locked": "This tariff is currently unavailable.",
        "custom_text": "Which subscription would you like to get cheaper?",
        "custom_sent": "✅ Your request has been accepted.\n\nThe admin will review it and contact you if needed.",
        "multi_quantity": "How many accounts do you need?",
        "multi_done": "✅ Your request has been accepted.\n\nThe admin received the quantity and will contact you soon.",
        "trial_name": "Enter your name.",
        "trial_phone": "Enter your phone number.",
        "trial_gmail": "Enter your Gmail for ChatGPT activation.",
        "invalid_gmail": "Enter a valid Gmail address in the format name@gmail.com.",
        "trial_subscribe": "Subscribe to the channel and press the verification button.",
        "trial_not_subscribed": "You have not subscribed to the channel yet.",
        "trial_already_used": "You have already used the trial subscription.",
        "trial_created": (
            "Order: {order_number}\n"
            "Product: ChatGPT PLUS (3 days)\n"
            "Price: FREE\n"
            "Status: order is under review"
        ),
        "trial_approved": (
            "✅ Your order has been approved.\n\n"
            "Order: {order_number}\n"
            "Product: ChatGPT PLUS (3 days)\n"
            "Price: FREE\n"
            "Access period: 3 days\n\n"
            "We will send an invitation to your Gmail. Open the email and accept it to activate Plus."
        ),
        "trial_rejected": "Trial subscriptions are out of stock. Please choose another subscription.",
        "chatgpt_month_name": "Enter your name to continue subscription setup.",
        "chatgpt_month_gmail_choice": "We found a Gmail you already used for ChatGPT:\n\n<b>{gmail}</b>\n\nDo you want to use this Gmail or enter another one?",
        "chatgpt_month_gmail": "Enter your Gmail for ChatGPT Plus activation.",
        "chatgpt_month_selected_gmail": "The subscription will be set up for this Gmail:\n<b>{gmail}</b>\n\nSubscribe to the channel and press the verification button so we can create your order.",
        "chatgpt_month_subscribe": "Subscribe to the channel and press the verification button so we can create your order.",
        "chatgpt_month_not_subscribed": "You have not subscribed to the channel yet.",
        "chatgpt_month_continue": "Your data has been received. The order has been created.",
        "order_cancelled": (
            "Order {order_number}\n"
            "Status: cancelled\n"
            "Message: order cancelled"
        ),
        "payment_rejected": (
            "Your payment was rejected.\n\n"
            "Please check your receipt or contact support."
        ),
        "stock_empty": (
            "This item is currently out of stock.\n\n"
            "Please try again later or contact support."
        ),
        "chatgpt_menu_text": "<tg-emoji emoji-id='5359726582447487916'>🤖</tg-emoji> ChatGPT Plus/Pro\n\nChoose a tariff below 👇",
        "capcut_menu_text": "<tg-emoji emoji-id='5364339557712020484'>🎬</tg-emoji> CapCut Pro\n\nChoose a tariff below 👇",
        "chatgpt_1m_text": (
            "💠 ChatGPT PLUS (1 month)\n"
            f"💰 Price: {format_price_uzs(CHATGPT_PLUS_PRICE_UZS)} UZS (~750 ₽)\n"
            "────────────────\n"
            "⚙️ How activation works\n"
            "1. We send a special PLUS invitation link to your email\n"
            "2. You open the link and sign in to your account\n"
            "3. ChatGPT PLUS activates automatically\n"
            "⏱ Access period — 25-30 days from activation\n\n"
            "🔐 Security\n"
            "— No password sharing required\n"
            "— Only you sign in to your account\n"
            "— Official connection methods are used\n\n"
            "— Support is available at every stage 💬\n"
            "— Available for users from CIS and other countries\n"
            "⸻\n"
            "✅ Benefits\n"
            "✔️ Fast activation\n"
            "✔️ Clear conditions\n"
            "✔️ Support after purchase"
        ),
        "capcut_1m_text": (
            "CapCut Pro (1 month)\n"
            f"Price: {format_price_uzs(CAPCUT_PRO_PRICE_UZS)} UZS\n\n"
            "<blockquote>"
            "Activation process:\n"
            "1. After ✅ payment confirmation, you receive a ready account.\n"
            "2. Sign in via email.\n"
            "3. If you already have an account, sign out first.\n"
            "</blockquote>\n\n"
            "Duration — 30 days."
        ),
        "invoice_title": (
            "Order: {order_number}\n"
            "Product: {product_name}\n"
            "Price: {price_uzs} UZS{usd_part}\n\n"
            "The invoice is valid for 30 minutes.\n"
            "Status will update after payment."
        ),
        "pay_click_text": (
            "Order: {order_number}\n"
            "Product: {product_name}\n"
            "Price: {price_uzs} UZS\n\n"
            "To pay:\n"
            "1. Open Click\n"
            "2. scan qrcod\n"
            "3. Enter amount: {price_uzs} UZS\n"
            "4. Confirm the payment\n\n"
            "After payment, send the receipt to this bot."
        ),
        "pay_card_text": (
            "Order: {order_number}\n"
            "Product: {product_name}\n"
            "Price: {price_uzs} UZS\n\n"
            "Card number:\n"
            "{card_number}\n\n"
            "Enter amount: {price_uzs} UZS\n\n"
            "After payment, send the receipt to this bot."
        ),
        "pay_crypto_text": (
            "Order: {order_number}\n"
            "Product: {product_name}\n"
            "Price: {price_usd}$\n\n"
            "USDT (TRC20):\n"
            "{wallet}\n\n"
            "After payment, send the receipt to this bot."
        ),
        "check_wait": "✅ Receipt received.\n\nWe sent it to the admin for review. Order status will update after confirmation.",
        "chatgpt_paid": (
            "✅ Your order has been approved.\n\n"
            "🤖 Product: ChatGPT PLUS (1 month)\n"
            "Order: {order_number}\n"
            "Access period: 30 days\n\n"
            "We will connect the subscription to the Gmail you provided. You will receive an invitation email and the subscription will activate after you accept it.\n\n"
            "Connection usually takes from a few minutes to a few hours after payment confirmation. Please also check Spam and Promotions.\n\n"
            f"If you need help, contact support: <a href='{SUPPORT_URL}'>support</a>."
        ),
        "capcut_paid": (
            "✅ Your order has been approved.\n\n"
            "🎬 Product: CapCut Pro (1 month)\n"
            "Order: {order_number}\n"
            "Access period: 30 days\n\n"
            "Login: {login}\n"
            "Password: {password}\n\n"
            "Sign out from any previous CapCut account first, then log in with these details. Access is ready immediately after login.\n\n"
            f"If something goes wrong, contact support: <a href='{SUPPORT_URL}'>support</a>."
        ),
        "history_title": "Order history",
        "details_title": "Order details",
        "status_completed": "completed",
        "status_paid": "paid",
        "status_rejected": "rejected",
        "status_cancelled": "cancelled",
        "status_new": "new",
        "status_waiting_check": "waiting for receipt",
        "status_on_review": "under review",
        "status_expired": "expired",
        "label_order": "Order",
        "label_product": "Product",
        "label_amount": "Amount",
        "label_status": "Status",
        "label_date": "Date",
        "btn_subscriptions": "💎 Subscriptions / Tariffs",
        "btn_profile": "👤 Profile",
        "btn_languages": "🌐 Languages",
        "btn_support": "💬 Support",
        "btn_about": "ℹ️ About us",
        "btn_faq": "❓ FAQ",
        "btn_history": "📜 Order history",
        "btn_promo": "🎁 Promo code",
        "btn_back": "◀ Back",
        "btn_menu": "🏠 Menu",
        "btn_chatgpt": "ChatGPT Plus/Pro",
        "btn_capcut": "CapCut Pro",
        "btn_grok": "Super Grok",
        "btn_other": "Other",
        "btn_buy": "Proceed",
        "btn_use_this_gmail": "Use this",
        "btn_use_other_gmail": "Other",
        "btn_confirm": "Confirm",
        "btn_cancel": "Cancel",
        "btn_question": "I have a question",
        "btn_several": "I need several",
        "btn_trial": "Try 3 days for free",
        "btn_promocode": "I have a promo code",
        "btn_order_details": "📄 Order details",
        "btn_review": "💬 Leave a review",
        "btn_check_sub": "Check subscription",
        "btn_click": "Click",
        "btn_card": "Humo/Visa",
        "btn_crypto": "USDT",
        "btn_custom_own": "I want my own",
        "faq_text": (
            "1. What do I receive after payment?\n"
            "You receive order confirmation and connection instructions.\n\n"
            "2. How is ChatGPT Plus activated?\n"
            "We send an invitation to your Gmail and the subscription activates after you accept it.\n\n"
            "3. How is CapCut Pro delivered?\n"
            "After payment confirmation you receive ready-to-use login details.\n\n"
            "4. How long does activation take?\n"
            "Usually from a few minutes to a few hours.\n\n"
            "5. Which payment methods are available?\n"
            "Click, Humo, Visa, and USDT (TRC20).\n\n"
            "6. Do I need a VPN?\n"
            "Usually no.\n\n"
            "7. Can I order several accounts?\n"
            "Yes, use the several-accounts button and the admin will process it.\n\n"
            "8. What if the email does not arrive?\n"
            "Check Spam and Promotions, then contact support.\n\n"
            "9. Can I request another service?\n"
            "Yes, use the Other section and send your request.\n\n"
            "10. What should I do if there is a problem after purchase?\n"
            "Contact support and include your order number."
        ),

        # Reminder message sent when a subscription or trial is nearing expiry
        "reminder_message": (
            "Your <b>{product}</b> subscription is about to expire.\n\n"
            "Only <b>{days} days</b> left. To continue enjoying all features, please renew your subscription for the next month.\n"
            "Tap the button below 👇"
        ),
    },
}


def t(user_id: int, key: str) -> str:
    lang = get_user_language(user_id) or "ru"
    return TEXTS.get(lang, TEXTS["ru"]).get(key, TEXTS["ru"].get(key, key))


# =========================================================
# HELPERS
# =========================================================

def localized_status(user_id: int, status: str) -> str:
    key = f"status_{status}"
    return t(user_id, key)


async def is_subscribed_to_required_channel(user_id: int) -> bool:
    try:
        member = await asyncio.wait_for(
            bot.get_chat_member(REQUIRED_CHANNEL, user_id),
            timeout=10
        )
        print("SUB CHECK STATUS:", member.status)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        print("SUB CHECK ERROR:", e)
        return False


def plain_text_from_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value)


def strip_tg_emoji_tags(value: str) -> str:
    return re.sub(r"<tg-emoji\b[^>]*>(.*?)</tg-emoji>", r"\1", value, flags=re.DOTALL)


def is_entity_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "entity_text_invalid" in message
        or "can't parse entities" in message
        or "parse entities" in message
        or "unsupported start tag" in message
        or 'tag "tg-emoji"' in message
        or "document_invalid" in message
        or "document invalid" in message
    )


def log_ui_send_error(context: str, exc: Exception):
    print(f"{context}: {type(exc).__name__}: {exc}")


async def safe_answer_message(message: Message, text: str, reply_markup=None):
    touch_user_activity(message.from_user.id)

    try:
        await message.answer(text, reply_markup=reply_markup)
        return
    except Exception as send_error:
        if is_entity_error(send_error):
            await message.answer(
                plain_text_from_html(text),
                reply_markup=reply_markup,
                parse_mode=None
            )
            return
        log_ui_send_error("SAFE ANSWER MESSAGE FAILED", send_error)
        raise


async def safe_send_user_message(chat_id: int, text: str, reply_markup=None):
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
        return
    except Exception as send_error:
        if is_entity_error(send_error):
            await bot.send_message(
                chat_id,
                plain_text_from_html(text),
                reply_markup=reply_markup,
                parse_mode=None
            )
            return
        log_ui_send_error("SAFE SEND USER MESSAGE FAILED", send_error)
        raise


async def safe_edit_text(callback: CallbackQuery, text: str, reply_markup=None):
    touch_user_activity(callback.from_user.id)

    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
        return
    except Exception as edit_error:
        if is_entity_error(edit_error):
            clean_text = plain_text_from_html(text)
            try:
                await callback.message.edit_text(
                    clean_text,
                    reply_markup=reply_markup,
                    parse_mode=None
                )
                return
            except Exception:
                await callback.message.answer(
                    clean_text,
                    reply_markup=reply_markup,
                    parse_mode=None
                )
                return
        else:
            log_ui_send_error("SAFE EDIT TEXT FAILED ON EDIT", edit_error)

    try:
        await callback.message.answer(text, reply_markup=reply_markup)
    except Exception as send_error:
        if is_entity_error(send_error):
            await callback.message.answer(
                plain_text_from_html(text),
                reply_markup=reply_markup,
                parse_mode=None
            )
            return
        log_ui_send_error("SAFE EDIT TEXT FAILED ON ANSWER", send_error)
        raise


def build_broadcast_reply_markup(button_data: dict | None):
    if not button_data:
        return None

    if button_data["type"] == "url":
        button = InlineKeyboardButton(text=button_data["text"], url=button_data["target"])
    else:
        button = InlineKeyboardButton(text=button_data["text"], callback_data=button_data["target"])

    return InlineKeyboardMarkup(inline_keyboard=[[button]])


async def send_broadcast_preview(target_chat_id: int, state: FSMContext):
    data = await state.get_data()
    chat_id = data.get("broadcast_message_chat_id")
    msg_id = data.get("broadcast_message_id")
    button_data = data.get("broadcast_button")
    reply_markup = build_broadcast_reply_markup(button_data)

    if not chat_id or not msg_id:
        return False

    try:
        if reply_markup:
            await bot.copy_message(
                chat_id=target_chat_id,
                from_chat_id=chat_id,
                message_id=msg_id,
                reply_markup=reply_markup,
            )
        else:
            await bot.copy_message(
                chat_id=target_chat_id,
                from_chat_id=chat_id,
                message_id=msg_id,
            )
    except Exception as e:
        print("BROADCAST PREVIEW ERROR:", e)
        return False

    await bot.send_message(
        target_chat_id,
        "Предпросмотр готов. Проверьте сообщение выше и подтвердите отправку.",
        reply_markup=admin_broadcast_confirm_kb()
    )
    return True


async def send_admin_message(text: str, reply_markup=None):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, reply_markup=reply_markup)
        except Exception as e:
            print("ADMIN SEND ERROR:", e)


async def send_admin_photo(file_id: str, caption: str, reply_markup=None):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(admin_id, photo=file_id, caption=caption, reply_markup=reply_markup)
        except Exception as e:
            print("ADMIN PHOTO ERROR:", e)


def admin_panel_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
                InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="admin_add_account"),
            ],
            [
                InlineKeyboardButton(text="🎬 CapCut", callback_data="admin_capcut"),
                InlineKeyboardButton(text="📦 Заказы", callback_data="admin_orders"),
            ],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        ]
    )


def admin_back_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_panel")],
        ]
    )


def admin_broadcast_type_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📲 Кнопка в сценарий бота", callback_data="broadcast_type_bot")],
            [InlineKeyboardButton(text="🌐 Кнопка на сайт", callback_data="broadcast_type_url")],
            [InlineKeyboardButton(text="⏭ Без кнопки", callback_data="broadcast_type_skip")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")],
        ]
    )


def admin_broadcast_confirm_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_confirm_send", style="success"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_confirm_cancel", style="danger"),
            ]
        ]
    )


def main_menu_kb(user_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(user_id, "btn_subscriptions"),
                    callback_data="open_subscriptions"
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(user_id, "btn_profile"),
                    callback_data="open_profile"
                ),
                InlineKeyboardButton(
                    text=t(user_id, "btn_languages"),
                    callback_data="open_languages"
                ),
            ],
            [InlineKeyboardButton(text=t(user_id, "btn_support"), url=SUPPORT_URL)],
            [
                InlineKeyboardButton(text=t(user_id, "btn_about"), url=ABOUT_URL),
                InlineKeyboardButton(text=t(user_id, "btn_faq"), callback_data="open_faq"),
            ],
        ]
    )


def language_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇿 O‘zbek", callback_data="set_lang_uz"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru"),
                InlineKeyboardButton(text="🇺🇸 English", callback_data="set_lang_en"),
            ]
        ]
    )


def profile_kb(user_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(user_id, "btn_history"), callback_data="profile_history")],
            [
                InlineKeyboardButton(text=t(user_id, "btn_support"), url=SUPPORT_URL),
                InlineKeyboardButton(text=t(user_id, "btn_promo"), callback_data="profile_promo"),
            ],
            [InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="back_main", style="danger")],
        ]
    )


def subscriptions_kb(user_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(user_id, "btn_chatgpt"), callback_data="open_chatgpt", icon_custom_emoji_id=EMOJI_ID_CHATGPT)],
            [InlineKeyboardButton(text=t(user_id, "btn_capcut"), callback_data="open_capcut", icon_custom_emoji_id=EMOJI_ID_CAPCUT)],
            [InlineKeyboardButton(text=t(user_id, "btn_grok"), callback_data="open_grok", icon_custom_emoji_id=EMOJI_ID_GROK)],
            [InlineKeyboardButton(text=t(user_id, "btn_other"), callback_data="open_other", icon_custom_emoji_id=EMOJI_ID_ADOBE)],
            [InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="back_main", style="danger")],
        ]
    )


def chatgpt_menu_kb(user_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"ChatGPT Plus 1 месяц — {format_price_uzs(CHATGPT_PLUS_PRICE_UZS)} сум",
                callback_data="chatgpt_1m",
                icon_custom_emoji_id=EMOJI_ID_CHATGPT
            )],
            [InlineKeyboardButton(text=t(user_id, "btn_trial"), callback_data="chatgpt_trial")],
            [InlineKeyboardButton(text=t(user_id, "btn_several"), callback_data="multi_chatgpt")],
            [InlineKeyboardButton(text=t(user_id, "btn_question"), url=SUPPORT_URL)],
            [
                InlineKeyboardButton(text=t(user_id, "btn_menu"), callback_data="back_main"),
                InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="open_subscriptions", style="danger"),
            ],
        ]
    )


def capcut_menu_kb(user_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"CapCut Pro 1 месяц — {format_price_uzs(CAPCUT_PRO_PRICE_UZS)} сум",
                callback_data="capcut_1m",
                icon_custom_emoji_id=EMOJI_ID_CAPCUT
            )],
            [InlineKeyboardButton(
                text="CapCut Pro 12 месяцев — недоступно",
                callback_data="capcut_locked",
                style="danger"
            )],
            [InlineKeyboardButton(text=t(user_id, "btn_several"), callback_data="multi_capcut")],
            [InlineKeyboardButton(text=t(user_id, "btn_question"), url=SUPPORT_URL)],
            [
                InlineKeyboardButton(text=t(user_id, "btn_menu"), callback_data="back_main"),
                InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="open_subscriptions", style="danger"),
            ],
        ]
    )


def other_menu_kb(user_id: int):
    lang = get_user_language(user_id)
    games_text = "Игровые ценности" if lang == "ru" else ("O‘yin valyutalari" if lang == "uz" else "Game values")
    music_text = "Музыка" if lang == "ru" else ("Musiqa" if lang == "uz" else "Music")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Adobe Cloud", callback_data="other_adobe", icon_custom_emoji_id=EMOJI_ID_ADOBE)],
            [InlineKeyboardButton(text=games_text, callback_data="other_games")],
            [InlineKeyboardButton(text="Telegram Premium", callback_data="other_telegram", icon_custom_emoji_id=EMOJI_ID_TELEGRAM)],
            [InlineKeyboardButton(text="Yandex Go", callback_data="other_yandex")],
            [InlineKeyboardButton(text=music_text, callback_data="other_music")],
            [InlineKeyboardButton(text=t(user_id, "btn_custom_own"), callback_data="other_custom_own")],
            [InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="open_subscriptions", style="danger")],
        ]
    )


def details_menu_kb(user_id: int, product_key: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(user_id, "btn_buy"),
                    callback_data=f"buy_{product_key}",
                    style="success"
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(user_id, "btn_back"),
                    callback_data=f"back_to_{product_key}",
                    style="danger",
                ),
                InlineKeyboardButton(
                    text=t(user_id, "btn_menu"),
                    callback_data="back_main"
                ),
            ],
        ]
    )


def invoice_menu_kb(user_id: int, order_number: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(user_id, "btn_click"),
                    callback_data=f"pay_click:{order_number}",
                    style="success"
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(user_id, "btn_card"),
                    callback_data=f"pay_card:{order_number}",
                    style="success"
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(user_id, "btn_crypto"),
                    callback_data=f"pay_crypto:{order_number}",
                    style="success"
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(user_id, "btn_promocode"),
                    callback_data=f"promo_from_invoice:{order_number}",
                    icon_custom_emoji_id=EMOJI_ID_GLOBE
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(user_id, "btn_cancel"),
                    callback_data=f"cancel_order:{order_number}",
                    style="danger"
                ),
                InlineKeyboardButton(
                    text=t(user_id, "btn_menu"),
                    callback_data="back_main"
                ),
            ],
        ]
    )


def payment_back_menu_kb(user_id: int, order_number: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(user_id, "btn_cancel"),
                    callback_data=f"cancel_order:{order_number}",
                    style="danger"
                ),
                InlineKeyboardButton(
                    text=t(user_id, "btn_menu"),
                    callback_data="back_main"
                ),
            ],
            [InlineKeyboardButton(text=t(user_id, "btn_support"), url=SUPPORT_URL)],
        ]
    )


def order_done_menu_kb(user_id: int, order_number: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(user_id, "btn_order_details"), callback_data=f"order_details:{order_number}", icon_custom_emoji_id=EMOJI_ID_PROFILE)],
            [InlineKeyboardButton(text=t(user_id, "btn_review"), url=REVIEW_URL, icon_custom_emoji_id=EMOJI_ID_SUPPORT)],
            [InlineKeyboardButton(text=t(user_id, "btn_menu"), callback_data="back_main", icon_custom_emoji_id=EMOJI_ID_SUBS)],
        ]
    )


def trial_subscribe_kb(user_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")],
            [InlineKeyboardButton(text=t(user_id, "btn_check_sub"), callback_data="trial_check_sub", style="success")],
            [InlineKeyboardButton(text=t(user_id, "btn_menu"), callback_data="back_main")],
        ]
    )


def chatgpt_month_subscribe_kb(user_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")],
            [InlineKeyboardButton(text=t(user_id, "btn_check_sub"), callback_data="chatgpt_month_check_sub", style="success")],
            [InlineKeyboardButton(text=t(user_id, "btn_menu"), callback_data="back_main")],
        ]
    )


def chatgpt_gmail_choice_kb(user_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(user_id, "btn_use_this_gmail"), callback_data="chatgpt_month_use_saved_gmail", style="success")],
            [InlineKeyboardButton(text=t(user_id, "btn_use_other_gmail"), callback_data="chatgpt_month_use_other_gmail", style="danger")],
            [InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="chatgpt_1m", style="danger")],
        ]
    )


def admin_trial_kb(order_number: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить", callback_data=f"trial_approve:{order_number}", style="success")],
            [InlineKeyboardButton(text="Отклонить", callback_data=f"trial_reject:{order_number}", style="danger")],
        ]
    )


def admin_payment_kb(order_number: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить", callback_data=f"approve_payment:{order_number}", style="success")],
            [InlineKeyboardButton(text="Отклонить", callback_data=f"reject_payment:{order_number}", style="danger")],
        ]
    )


# =========================================================
# START / LANGUAGE
# =========================================================

@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    is_new = add_user_if_not_exists(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name
    )
    touch_user_activity(message.from_user.id)
    await state.clear()

    if is_new:
        await send_admin_message(
            f"🆕 Новый подписчик\n\n"
            f"ID: <code>{message.from_user.id}</code>\n"
            f"Username: @{message.from_user.username or 'нет'}\n"
            f"Имя: {message.from_user.full_name}"
        )

    if has_selected_language(message.from_user.id):
        await safe_answer_message(
            message,
            get_main_menu_text(message.from_user.id),
            reply_markup=main_menu_kb(message.from_user.id)
        )
        return

    await message.answer(f"<b>{TEXTS['ru']['choose_language']}</b>", reply_markup=language_kb())


async def apply_language_selection(callback: CallbackQuery, state: FSMContext, lang: str):
    add_user_if_not_exists(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name
    )
    set_user_language(callback.from_user.id, lang)
    await state.clear()
    await safe_edit_text(
        callback,
        get_main_menu_text(callback.from_user.id),
        reply_markup=main_menu_kb(callback.from_user.id)
    )


@dp.callback_query(F.data == "set_lang_ru")
async def set_language_ru_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await apply_language_selection(callback, state, "ru")


@dp.callback_query(F.data == "set_lang_uz")
async def set_language_uz_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await apply_language_selection(callback, state, "uz")


@dp.callback_query(F.data == "set_lang_en")
async def set_language_en_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await apply_language_selection(callback, state, "en")


# =========================================================
# MAIN NAVIGATION
# =========================================================

@dp.callback_query(F.data == "back_main")
async def back_main_handler(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_text(
        callback,
        get_main_menu_text(callback.from_user.id),
        reply_markup=main_menu_kb(callback.from_user.id)
    )


@dp.callback_query(F.data == "open_languages")
async def open_languages_handler(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_text(
        callback,
        f"<b>{t(callback.from_user.id, 'choose_language')}</b>",
        reply_markup=language_kb()
    )


@dp.callback_query(F.data == "open_faq")
async def open_faq_handler(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_text(
        callback,
        f"<b>{t(callback.from_user.id, 'faq_title')}</b>\n\n{t(callback.from_user.id, 'faq_text')}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(callback.from_user.id, "btn_back"), callback_data="back_main", style="danger")]
            ]
        )
    )


@dp.callback_query(F.data == "open_profile")
async def open_profile_handler(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_text(
        callback,
        f"<b>{t(callback.from_user.id, 'profile_title')}</b>",
        reply_markup=profile_kb(callback.from_user.id)
    )


@dp.callback_query(F.data == "profile_promo")
async def profile_promo_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(PromoState.waiting_code)
    await state.update_data(return_to="profile")
    await safe_edit_text(
        callback,
        t(callback.from_user.id, "promo_enter"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(callback.from_user.id, "btn_back"), callback_data="open_profile", style="danger")]
            ]
        )
    )


@dp.callback_query(F.data.startswith("promo_from_invoice:"))
async def promo_from_invoice_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    order_number = callback.data.split(":", 1)[1]
    await state.set_state(PromoState.waiting_code)
    await state.update_data(return_to=f"invoice:{order_number}")
    await safe_edit_text(
        callback,
        t(callback.from_user.id, "promo_enter"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(callback.from_user.id, "btn_back"), callback_data=f"back_invoice:{order_number}", style="danger")]
            ]
        )
    )


@dp.callback_query(F.data.startswith("back_invoice:"))
async def back_invoice_handler(callback: CallbackQuery):
    await callback.answer()
    order_number = callback.data.split(":", 1)[1]
    order = get_order(order_number)
    if not order:
        await callback.message.answer("Заказ не найден")
        return

    _, _, _, product_name, price_uzs, price_usd, _, _, _, _, _ = order
    usd_part = f" / {price_usd}$" if price_usd else ""
    text = t(callback.from_user.id, "invoice_title").format(
        order_number=order_number,
        product_name=product_name,
        price_uzs=format_price_uzs(price_uzs),
        usd_part=usd_part
    )
    await safe_edit_text(callback, text, reply_markup=invoice_menu_kb(callback.from_user.id, order_number))


@dp.message(PromoState.waiting_code)
async def promo_input_handler(message: Message, state: FSMContext):
    touch_user_activity(message.from_user.id)
    data = await state.get_data()
    return_to = data.get("return_to", "profile")
    await message.answer(t(message.from_user.id, "promo_invalid"))
    await state.clear()

    if return_to == "profile":
        await message.answer(
            f"<b>{t(message.from_user.id, 'profile_title')}</b>",
            reply_markup=profile_kb(message.from_user.id)
        )
    elif isinstance(return_to, str) and return_to.startswith("invoice:"):
        order_number = return_to.split(":", 1)[1]
        order = get_order(order_number)
        if order:
            _, _, _, product_name, price_uzs, price_usd, _, _, _, _, _ = order
            usd_part = f" / {price_usd}$" if price_usd else ""
            text = t(message.from_user.id, "invoice_title").format(
                order_number=order_number,
                product_name=product_name,
                price_uzs=format_price_uzs(price_uzs),
                usd_part=usd_part
            )
            await message.answer(text, reply_markup=invoice_menu_kb(message.from_user.id, order_number))



@dp.callback_query(F.data == "profile_history")
async def profile_history_handler(callback: CallbackQuery):
    await callback.answer()
    orders = get_user_orders(callback.from_user.id)

    if not orders:
        await safe_edit_text(
            callback,
            t(callback.from_user.id, "no_orders"),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=t(callback.from_user.id, "btn_back"), callback_data="open_profile", style="danger")]
                ]
            )
        )
        return

    blocks = [f"<b>{t(callback.from_user.id, 'history_title')}</b>\n"]
    for order_number, product_name, price_uzs, status, created_at in orders[:10]:
        blocks.append(
            f"{t(callback.from_user.id, 'label_order')}: {order_number}\n"
            f"{t(callback.from_user.id, 'label_product')}: {product_name}\n"
            f"{t(callback.from_user.id, 'label_amount')}: {format_price_uzs(price_uzs)}\n"
            f"{t(callback.from_user.id, 'label_status')}: {localized_status(callback.from_user.id, status)}\n"
            f"{t(callback.from_user.id, 'label_date')}: {created_at}"
        )

    await safe_edit_text(
        callback,
        "\n\n".join(blocks),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                    [InlineKeyboardButton(text=t(callback.from_user.id, "btn_back"), callback_data="open_profile", style="danger")]
            ]
        )
    )


# =========================================================
# SUBSCRIPTIONS
# =========================================================

@dp.callback_query(F.data == "open_subscriptions")
async def open_subscriptions_handler(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_text(
        callback,
        f"<b>{t(callback.from_user.id, 'subscriptions_title')}</b>",
        reply_markup=subscriptions_kb(callback.from_user.id)
    )


@dp.callback_query(F.data == "open_grok")
async def open_grok_handler(callback: CallbackQuery):
    await callback.answer(t(callback.from_user.id, "grok_unavailable"), show_alert=True)


@dp.callback_query(F.data == "open_other")
async def open_other_handler(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_text(
        callback,
        t(callback.from_user.id, "custom_text"),
        reply_markup=other_menu_kb(callback.from_user.id)
    )


@dp.callback_query(F.data.in_({
    "other_adobe",
    "other_games",
    "other_telegram",
    "other_yandex",
    "other_music",
    "other_custom_own",
}))
async def custom_request_handler(callback: CallbackQuery):
    await callback.answer()
    touch_user_activity(callback.from_user.id)

    lang = get_user_language(callback.from_user.id)
    request_map = {
        "other_adobe": "Adobe Cloud",
        "other_games": "Игровые ценности" if lang == "ru" else ("O‘yin valyutalari" if lang == "uz" else "Game values"),
        "other_telegram": "Telegram Premium",
        "other_yandex": "Yandex Go",
        "other_music": "Музыка" if lang == "ru" else ("Musiqa" if lang == "uz" else "Music"),
        "other_custom_own": t(callback.from_user.id, "btn_custom_own"),
    }
    request_name = request_map.get(callback.data)
    if not request_name:
        await callback.answer("Раздел не найден", show_alert=True)
        return

    add_custom_request(
        callback.from_user.id,
        callback.from_user.username or "",
        callback.from_user.full_name,
        request_name
    )

    await send_admin_message(
        f"Новая заявка из раздела «Другое»\n\n"
        f"Пользователь: {callback.from_user.full_name}\n"
        f"Username: @{callback.from_user.username or 'нет'}\n"
        f"ID: <code>{callback.from_user.id}</code>\n"
        f"Запрос: {request_name}"
    )

    await safe_edit_text(
        callback,
        t(callback.from_user.id, "custom_sent"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(callback.from_user.id, "btn_menu"), callback_data="back_main")]
            ]
        )
    )


@dp.callback_query(F.data == "open_chatgpt")
async def open_chatgpt_handler(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_text(
        callback,
        t(callback.from_user.id, "chatgpt_menu_text"),
        reply_markup=chatgpt_menu_kb(callback.from_user.id)
    )


@dp.callback_query(F.data == "open_capcut")
async def open_capcut_handler(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_text(
        callback,
        t(callback.from_user.id, "capcut_menu_text"),
        reply_markup=capcut_menu_kb(callback.from_user.id)
    )


@dp.callback_query(F.data == "capcut_locked")
async def capcut_locked_handler(callback: CallbackQuery):
    await callback.answer(t(callback.from_user.id, "capcut_locked"), show_alert=True)


# =========================================================
# MULTI REQUESTS
# =========================================================

@dp.callback_query(F.data.in_({"multi_chatgpt", "multi_capcut"}))
async def multi_start_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    service_name = "ChatGPT Plus" if callback.data == "multi_chatgpt" else "CapCut Pro"
    await state.set_state(MultiOrderState.waiting_quantity)
    await state.update_data(service_name=service_name)

    await safe_edit_text(
        callback,
        t(callback.from_user.id, "multi_quantity"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(callback.from_user.id, "btn_back"), callback_data="open_subscriptions", style="danger")]
            ]
        )
    )


@dp.message(MultiOrderState.waiting_quantity)
async def multi_quantity_handler(message: Message, state: FSMContext):
    touch_user_activity(message.from_user.id)

    if not message.text or not message.text.isdigit():
        await message.answer("Введите число.")
        return

    quantity = int(message.text)
    if quantity <= 0:
        await message.answer("Введите число больше нуля.")
        return

    data = await state.get_data()
    service_name = data.get("service_name")
    if not service_name:
        await state.clear()
        await safe_answer_message(
            message,
            get_main_menu_text(message.from_user.id),
            reply_markup=main_menu_kb(message.from_user.id)
        )
        return

    add_multi_request(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.full_name,
        service_name,
        quantity
    )

    await send_admin_message(
        f"Новая заявка «Хочу несколько»\n\n"
        f"Пользователь: {message.from_user.full_name}\n"
        f"Username: @{message.from_user.username or 'нет'}\n"
        f"ID: <code>{message.from_user.id}</code>\n"
        f"Сервис: {service_name}\n"
        f"Количество: {quantity}"
    )

    await message.answer(t(message.from_user.id, "multi_done"))
    await state.clear()


# =========================================================
# FREE TRIAL
# =========================================================

@dp.callback_query(F.data == "chatgpt_trial")
async def chatgpt_trial_start(callback: CallbackQuery, state: FSMContext):
    if has_used_free_trial(callback.from_user.id):
        await callback.answer(
            t(callback.from_user.id, "trial_already_used"),
            show_alert=True
        )
        return

    await callback.answer()
    await state.set_state(TrialState.waiting_name)
    await safe_edit_text(
        callback,
        t(callback.from_user.id, "trial_name"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(callback.from_user.id, "btn_back"), callback_data="open_chatgpt", style="danger")]
            ]
        )
    )


@dp.message(TrialState.waiting_name)
async def trial_name_handler(message: Message, state: FSMContext):
    touch_user_activity(message.from_user.id)
    name = (message.text or "").strip()
    if not name:
        await message.answer(t(message.from_user.id, "trial_name"))
        return

    await state.update_data(trial_name=name)
    await state.set_state(TrialState.waiting_phone)
    await message.answer(t(message.from_user.id, "trial_phone"))


@dp.message(TrialState.waiting_phone)
async def trial_phone_handler(message: Message, state: FSMContext):
    touch_user_activity(message.from_user.id)
    phone = (message.text or "").strip()
    if not phone:
        await message.answer(t(message.from_user.id, "trial_phone"))
        return

    await state.update_data(trial_phone=phone)
    await state.set_state(TrialState.waiting_gmail)
    await message.answer(t(message.from_user.id, "trial_gmail"))


@dp.message(TrialState.waiting_gmail)
async def trial_gmail_handler(message: Message, state: FSMContext):
    touch_user_activity(message.from_user.id)
    gmail = (message.text or "").strip()
    if not is_valid_gmail(gmail):
        await message.answer(t(message.from_user.id, "invalid_gmail"))
        return

    await state.update_data(trial_gmail=gmail)
    await message.answer(
        t(message.from_user.id, "trial_subscribe"),
        reply_markup=trial_subscribe_kb(message.from_user.id)
    )


@dp.callback_query(F.data == "trial_check_sub")
async def trial_check_sub_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    if not await is_subscribed_to_required_channel(callback.from_user.id):
        await safe_answer_message(callback.message, t(callback.from_user.id, "trial_not_subscribed"))
        return

    data = await state.get_data()
    full_name = data.get("trial_name", "")
    phone = data.get("trial_phone", "")
    gmail = data.get("trial_gmail", "")
    if not full_name or not phone or not gmail:
        await state.clear()
        await safe_answer_message(
            callback.message,
            "Данные для пробной подписки не найдены. Пожалуйста, начните оформление заново.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=t(callback.from_user.id, "btn_menu"), callback_data="back_main")]
                ]
            )
        )
        return

    order_number = create_free_trial(
        callback.from_user.id,
        callback.from_user.username or "",
        full_name,
        phone,
        gmail
    )

    await send_admin_message(
        f"Новая заявка на 3 дня бесплатно\n\n"
        f"Пользователь: {callback.from_user.full_name}\n"
        f"Username: @{callback.from_user.username or 'нет'}\n"
        f"ID: <code>{callback.from_user.id}</code>\n"
        f"Заказ: {order_number}\n"
        f"Gmail: {gmail}\n"
        f"Телефон: {phone}",
        reply_markup=admin_trial_kb(order_number)
    )

    await safe_edit_text(
        callback,
        t(callback.from_user.id, "trial_created").format(order_number=order_number),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(callback.from_user.id, "btn_menu"), callback_data="back_main")]
            ]
        )
    )

    await state.clear()


@dp.callback_query(F.data.startswith("trial_approve:"))
async def trial_approve_handler(callback: CallbackQuery):
    await callback.answer()

    order_number = callback.data.split(":", 1)[1]
    trial = get_free_trial(order_number)
    if not trial:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    _, telegram_id, _, _, _, _, _, _ = trial
    update_free_trial_status(order_number, "approved")

    # Set expiry for the free trial (3 days) and reset reminder flag
    update_free_trial_expiry(order_number, 3)

    await safe_send_user_message(
        telegram_id,
        t(telegram_id, "trial_approved").format(order_number=order_number),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(telegram_id, "btn_review"), url=REVIEW_URL)],
                [InlineKeyboardButton(text=t(telegram_id, "btn_menu"), callback_data="back_main")]
            ]
        )
    )

    await safe_edit_text(callback, "Заявка подтверждена.")


@dp.callback_query(F.data.startswith("trial_reject:"))
async def trial_reject_handler(callback: CallbackQuery):
    await callback.answer()

    order_number = callback.data.split(":", 1)[1]
    trial = get_free_trial(order_number)
    if not trial:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    _, telegram_id, _, _, _, _, _, _ = trial
    update_free_trial_status(order_number, "rejected")

    await bot.send_message(
        telegram_id,
        t(telegram_id, "trial_rejected"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(telegram_id, "btn_menu"), callback_data="back_main")]
            ]
        )
    )

    await safe_edit_text(callback, "Заявка отклонена.")


# =========================================================
# CHATGPT MONTH LEAD BEFORE BUY
# =========================================================

@dp.callback_query(F.data.in_({"chatgpt_1m", "chatgpt_1m_start"}))
async def chatgpt_1m_start_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await safe_edit_text(
        callback,
        t(callback.from_user.id, "chatgpt_1m_text"),
        reply_markup=details_menu_kb(callback.from_user.id, "chatgpt_1m")
    )


@dp.message(ChatGPTMonthLeadState.waiting_gmail)
async def chatgpt_month_gmail_handler(message: Message, state: FSMContext):
    touch_user_activity(message.from_user.id)
    gmail = (message.text or "").strip()
    if not is_valid_gmail(gmail):
        await message.answer(t(message.from_user.id, "invalid_gmail"))
        return

    await state.update_data(chatgpt_month_gmail=gmail)
    await message.answer(
        t(message.from_user.id, "chatgpt_month_subscribe"),
        reply_markup=chatgpt_month_subscribe_kb(message.from_user.id)
    )


@dp.callback_query(F.data == "chatgpt_month_use_saved_gmail")
async def chatgpt_month_use_saved_gmail_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    saved_gmail = data.get("saved_chatgpt_gmail", "")
    if not saved_gmail:
        await state.set_state(ChatGPTMonthLeadState.waiting_gmail)
        await safe_edit_text(
            callback,
            t(callback.from_user.id, "chatgpt_month_gmail"),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=t(callback.from_user.id, "btn_back"), callback_data="chatgpt_1m", style="danger")]
                ]
            )
        )
        return

    await state.update_data(chatgpt_month_gmail=saved_gmail)
    await safe_edit_text(
        callback,
        t(callback.from_user.id, "chatgpt_month_selected_gmail").format(gmail=saved_gmail),
        reply_markup=chatgpt_month_subscribe_kb(callback.from_user.id)
    )


@dp.callback_query(F.data == "chatgpt_month_use_other_gmail")
async def chatgpt_month_use_other_gmail_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ChatGPTMonthLeadState.waiting_gmail)
    await safe_edit_text(
        callback,
        t(callback.from_user.id, "chatgpt_month_gmail"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(callback.from_user.id, "btn_back"), callback_data="chatgpt_1m", style="danger")]
            ]
        )
    )


@dp.callback_query(F.data == "chatgpt_month_check_sub")
async def chatgpt_month_check_sub_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    if not await is_subscribed_to_required_channel(callback.from_user.id):
        await callback.message.answer(t(callback.from_user.id, "chatgpt_month_not_subscribed"))
        return

    data = await state.get_data()
    gmail_value = data.get("chatgpt_month_gmail", "")
    if not gmail_value:
        await state.clear()
        await safe_answer_message(
            callback.message,
            get_main_menu_text(callback.from_user.id),
            reply_markup=main_menu_kb(callback.from_user.id)
        )
        return

    order_number = create_order(
        telegram_id=callback.from_user.id,
        product_code="chatgpt_plus_1m",
        product_name="ChatGPT PLUS (1 месяц)",
        price_uzs=CHATGPT_PLUS_PRICE_UZS,
        price_usd=CHATGPT_PLUS_PRICE_USD,
        details=f"Gmail: {gmail_value}"
    )

    await send_admin_message(
        f"Новая заявка ChatGPT Plus 1 месяц\n\n"
        f"Пользователь: {callback.from_user.full_name}\n"
        f"Username: @{callback.from_user.username or 'нет'}\n"
        f"ID: <code>{callback.from_user.id}</code>\n"
        f"Заказ: {order_number}\n"
        f"Gmail: {gmail_value}"
    )

    await state.clear()

    text = t(callback.from_user.id, "invoice_title").format(
        order_number=order_number,
        product_name="ChatGPT PLUS (1 месяц)",
        price_uzs=format_price_uzs(CHATGPT_PLUS_PRICE_UZS),
        usd_part=" (~750 ₽)"
    )

    await safe_edit_text(
        callback,
        text,
        reply_markup=invoice_menu_kb(callback.from_user.id, order_number)
    )


# =========================================================
# PRODUCT DETAILS
# =========================================================

@dp.callback_query(F.data == "capcut_1m")
async def capcut_1m_handler(callback: CallbackQuery):
    await callback.answer()

    if count_free_capcut_accounts() <= 0:
        await safe_edit_text(
            callback,
            t(callback.from_user.id, "stock_empty"),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=t(callback.from_user.id, "btn_menu"), callback_data="back_main")],
                    [InlineKeyboardButton(text=t(callback.from_user.id, "btn_support"), url=SUPPORT_URL)],
                ]
            )
        )
        return

    await safe_edit_text(
        callback,
        t(callback.from_user.id, "capcut_1m_text"),
        reply_markup=details_menu_kb(callback.from_user.id, "capcut_1m")
    )


@dp.callback_query(F.data == "back_to_chatgpt_1m")
async def back_to_chatgpt_1m_handler(callback: CallbackQuery):
    await callback.answer()
    await open_chatgpt_handler(callback)


@dp.callback_query(F.data == "back_to_capcut_1m")
async def back_to_capcut_1m_handler(callback: CallbackQuery):
    await callback.answer()
    await open_capcut_handler(callback)


# =========================================================
# BUY / INVOICE
# =========================================================

@dp.callback_query(F.data == "buy_chatgpt_1m")
async def buy_chatgpt_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    saved_gmail = get_last_chatgpt_gmail(callback.from_user.id)

    if saved_gmail:
        await state.set_state(ChatGPTMonthLeadState.waiting_gmail_choice)
        await state.update_data(saved_chatgpt_gmail=saved_gmail, chatgpt_month_gmail="")
        await safe_edit_text(
            callback,
            t(callback.from_user.id, "chatgpt_month_gmail_choice").format(gmail=saved_gmail),
            reply_markup=chatgpt_gmail_choice_kb(callback.from_user.id)
        )
        return

    await state.set_state(ChatGPTMonthLeadState.waiting_gmail)
    await safe_edit_text(
        callback,
        t(callback.from_user.id, "chatgpt_month_gmail"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(callback.from_user.id, "btn_back"), callback_data="chatgpt_1m", style="danger")]
            ]
        )
    )


@dp.callback_query(F.data == "buy_capcut_1m")
async def buy_capcut_handler(callback: CallbackQuery):
    await callback.answer()

    if count_free_capcut_accounts() <= 0:
        await safe_edit_text(
            callback,
            t(callback.from_user.id, "stock_empty"),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=t(callback.from_user.id, "btn_menu"), callback_data="back_main")],
                    [InlineKeyboardButton(text=t(callback.from_user.id, "btn_support"), url=SUPPORT_URL)],
                ]
            )
        )
        return

    order_number = create_order(
        telegram_id=callback.from_user.id,
        product_code="capcut_pro_1m",
        product_name="CapCut Pro (1 месяц)",
        price_uzs=CAPCUT_PRO_PRICE_UZS,
        price_usd=CAPCUT_PRO_PRICE_USD
    )

    text = t(callback.from_user.id, "invoice_title").format(
        order_number=order_number,
        product_name="CapCut Pro (1 месяц)",
        price_uzs=format_price_uzs(CAPCUT_PRO_PRICE_UZS),
        usd_part=" (~350 ₽)"
    )

    await safe_edit_text(
        callback,
        text,
        reply_markup=invoice_menu_kb(callback.from_user.id, order_number)
    )


# =========================================================
# PAYMENT
# =========================================================

@dp.callback_query(F.data.startswith("pay_click:"))
async def pay_click_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    order_number = callback.data.split(":", 1)[1]
    order = get_order(order_number)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    _, _, _, product_name, price_uzs, _, _, _, _, _, _ = order
    update_order_payment_method(order_number, "click")

    await state.set_state(PaymentState.waiting_check)
    await state.update_data(order_number=order_number)

    click_text = t(callback.from_user.id, "pay_click_text").format(
        order_number=order_number,
        product_name=product_name,
        price_uzs=format_price_uzs(price_uzs),
        click_number=CLICK_NUMBER
    )

    if os.path.exists(CLICK_QR_IMAGE_PATH):
        await callback.message.answer_photo(
            photo=FSInputFile(CLICK_QR_IMAGE_PATH),
            caption=click_text,
            reply_markup=payment_back_menu_kb(callback.from_user.id, order_number)
        )
        return

    await safe_edit_text(
        callback,
        click_text,
        reply_markup=payment_back_menu_kb(callback.from_user.id, order_number)
    )


@dp.callback_query(F.data.startswith("pay_card:"))
async def pay_card_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    order_number = callback.data.split(":", 1)[1]
    order = get_order(order_number)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    _, _, _, product_name, price_uzs, _, _, _, _, _, _ = order
    update_order_payment_method(order_number, "card")

    await state.set_state(PaymentState.waiting_check)
    await state.update_data(order_number=order_number)

    await safe_edit_text(
        callback,
        t(callback.from_user.id, "pay_card_text").format(
            order_number=order_number,
            product_name=product_name,
            price_uzs=format_price_uzs(price_uzs),
            card_number=CARD_NUMBER
        ),
        reply_markup=payment_back_menu_kb(callback.from_user.id, order_number)
    )


@dp.callback_query(F.data.startswith("pay_crypto:"))
async def pay_crypto_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    order_number = callback.data.split(":", 1)[1]
    order = get_order(order_number)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    _, _, _, product_name, _, price_usd, _, _, _, _, _ = order
    update_order_payment_method(order_number, "crypto")

    await state.set_state(PaymentState.waiting_check)
    await state.update_data(order_number=order_number)

    await safe_edit_text(
        callback,
        t(callback.from_user.id, "pay_crypto_text").format(
            order_number=order_number,
            product_name=product_name,
            price_usd=price_usd,
            wallet=USDT_TRC20_ADDRESS
        ),
        reply_markup=payment_back_menu_kb(callback.from_user.id, order_number)
    )


@dp.callback_query(F.data.startswith("cancel_order:"))
async def cancel_order_handler(callback: CallbackQuery):
    await callback.answer()
    order_number = callback.data.split(":", 1)[1]
    update_order_status(order_number, "cancelled")

    await safe_edit_text(
        callback,
        t(callback.from_user.id, "order_cancelled").format(order_number=order_number),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(callback.from_user.id, "btn_menu"), callback_data="back_main")]
            ]
        )
    )


# =========================================================
# CHECK / ADMIN APPROVE
# =========================================================

@dp.message(PaymentState.waiting_check, F.photo)
async def payment_check_photo_handler(message: Message, state: FSMContext):
    touch_user_activity(message.from_user.id)
    data = await state.get_data()
    order_number = data.get("order_number")
    if not order_number:
        await message.answer("Заказ не найден.")
        await state.clear()
        return

    order = get_order(order_number)
    if not order:
        await message.answer("Заказ не найден.")
        await state.clear()
        return

    _, _, _, product_name, price_uzs, price_usd, payment_method, _, _, _, _ = order

    caption = (
        f"Новый чек\n\n"
        f"Заказ: {order_number}\n"
        f"Товар: {product_name}\n"
        f"Сумма: {format_price_uzs(price_uzs)} сум"
        f"{f' / {price_usd}$' if payment_method == 'crypto' else ''}\n"
        f"Метод: {payment_method}\n"
        f"Пользователь: {message.from_user.full_name}\n"
        f"Username: @{message.from_user.username or 'нет'}\n"
        f"ID: <code>{message.from_user.id}</code>"
    )

    update_order_status(order_number, "on_review")

    await send_admin_photo(
        message.photo[-1].file_id,
        caption,
        reply_markup=admin_payment_kb(order_number)
    )

    await message.answer(t(message.from_user.id, "check_wait"))
    await state.clear()


@dp.message(PaymentState.waiting_check, F.document)
async def payment_check_document_handler(message: Message, state: FSMContext):
    touch_user_activity(message.from_user.id)
    data = await state.get_data()
    order_number = data.get("order_number")
    if not order_number:
        await message.answer("Заказ не найден.")
        await state.clear()
        return

    order = get_order(order_number)
    if not order:
        await message.answer("Заказ не найден.")
        await state.clear()
        return

    _, _, _, product_name, price_uzs, price_usd, payment_method, _, _, _, _ = order

    caption = (
        f"Новый чек\n\n"
        f"Заказ: {order_number}\n"
        f"Товар: {product_name}\n"
        f"Сумма: {format_price_uzs(price_uzs)} сум"
        f"{f' / {price_usd}$' if payment_method == 'crypto' else ''}\n"
        f"Метод: {payment_method}\n"
        f"Пользователь: {message.from_user.full_name}\n"
        f"Username: @{message.from_user.username or 'нет'}\n"
        f"ID: <code>{message.from_user.id}</code>"
    )

    update_order_status(order_number, "on_review")

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_document(
                admin_id,
                document=message.document.file_id,
                caption=caption,
                reply_markup=admin_payment_kb(order_number)
            )
        except Exception as e:
            print("ADMIN DOCUMENT ERROR:", e)

    await message.answer(t(message.from_user.id, "check_wait"))
    await state.clear()


@dp.callback_query(F.data.startswith("approve_payment:"))
async def approve_payment_handler(callback: CallbackQuery):
    await callback.answer()
    order_number = callback.data.split(":", 1)[1]
    order = get_order(order_number)

    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    _, telegram_id, product_code, _, _, _, _, _, _, _, _ = order
    update_order_status(order_number, "paid")

    if product_code == "capcut_pro_1m":
        account = get_free_capcut_account()

        if not account:
            await safe_send_user_message(
                telegram_id,
                t(telegram_id, "stock_empty"),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text=t(telegram_id, "btn_support"), url=SUPPORT_URL)],
                        [InlineKeyboardButton(text=t(telegram_id, "btn_menu"), callback_data="back_main")]
                    ]
                )
            )
            await safe_edit_text(callback, "✅ Оплата подтверждена, но свободных аккаунтов нет.")
            return

        acc_id, login, password = account
        mark_capcut_account_used(acc_id, telegram_id)
        update_order_status(order_number, "completed")
        # CapCut Pro subscriptions also expire in 30 days; set expiry and reset reminder flag
        update_order_expiry(order_number, 30)

        await safe_send_user_message(
            telegram_id,
            t(telegram_id, "capcut_paid").format(
                order_number=order_number,
                login=login,
                password=password
            ),
            reply_markup=order_done_menu_kb(telegram_id, order_number)
        )
    else:
        update_order_status(order_number, "completed")
        # ChatGPT Plus subscriptions last for 30 days; set expiry and reset reminder flag
        update_order_expiry(order_number, 30)
        await safe_send_user_message(
            telegram_id,
            t(telegram_id, "chatgpt_paid").format(order_number=order_number),
            reply_markup=order_done_menu_kb(telegram_id, order_number)
        )

    await safe_edit_text(callback, "✅ Оплата подтверждена.")


@dp.callback_query(F.data.startswith("reject_payment:"))
async def reject_payment_handler(callback: CallbackQuery):
    await callback.answer()
    order_number = callback.data.split(":", 1)[1]
    order = get_order(order_number)

    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    _, telegram_id, _, _, _, _, _, _, _, _, _ = order
    update_order_status(order_number, "rejected")

    await bot.send_message(
        telegram_id,
        t(telegram_id, "payment_rejected"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(telegram_id, "btn_support"), url=SUPPORT_URL)],
                [InlineKeyboardButton(text=t(telegram_id, "btn_menu"), callback_data="back_main")]
            ]
        )
    )

    await safe_edit_text(callback, "❌ Оплата отклонена.")


# =========================================================
# ORDER DETAILS
# =========================================================

@dp.callback_query(F.data.startswith("order_details:"))
async def order_details_handler(callback: CallbackQuery):
    await callback.answer()
    order_number = callback.data.split(":", 1)[1]
    order = get_order(order_number)

    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    _, _, _, product_name, price_uzs, price_usd, payment_method, status, _, created_at, expires_at = order

    usd_part = f" / {price_usd}$" if price_usd else ""
    text = (
        f"<b>{t(callback.from_user.id, 'details_title')}</b>\n\n"
        f"{t(callback.from_user.id, 'label_order')}: {order_number}\n"
        f"{t(callback.from_user.id, 'label_product')}: {product_name}\n"
        f"{t(callback.from_user.id, 'label_amount')}: {format_price_uzs(price_uzs)}{usd_part}\n"
        f"{t(callback.from_user.id, 'label_status')}: {localized_status(callback.from_user.id, status)}\n"
        f"{t(callback.from_user.id, 'label_date')}: {created_at}\n"
        f"Method: {payment_method or '-'}\n"
        f"Expires: {expires_at}"
    )

    await safe_edit_text(
        callback,
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(callback.from_user.id, "btn_menu"), callback_data="back_main")],
                [InlineKeyboardButton(text=t(callback.from_user.id, "btn_review"), url=REVIEW_URL)],
            ]
        )
    )


# =========================================================
# ADMIN COMMANDS
# =========================================================

def get_admin_stats_text() -> str:
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    users_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM users WHERE language_selected = 1")
    users_with_language = cur.fetchone()[0]

    now = now_dt()
    active_day = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    active_week = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("SELECT COUNT(*) FROM users WHERE last_seen_at IS NOT NULL AND last_seen_at >= ?", (active_day,))
    active_24h = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM users WHERE last_seen_at IS NOT NULL AND last_seen_at >= ?", (active_week,))
    active_7d = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM orders")
    orders_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'")
    completed_orders = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM orders WHERE status IN ('new', 'waiting_check', 'on_review', 'paid')")
    active_orders = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM free_trials")
    trials_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM multi_requests")
    multi_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM custom_requests")
    custom_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM capcut_accounts WHERE is_used = 0")
    free_capcut = cur.fetchone()[0]

    conn.close()

    return (
        "📊 Статистика бота\n\n"
        f"Пользователей: {users_count}\n"
        f"Язык выбран: {users_with_language}\n"
        f"Активны за 24 часа: {active_24h}\n"
        f"Активны за 7 дней: {active_7d}\n\n"
        f"Всего заказов: {orders_count}\n"
        f"Завершённых заказов: {completed_orders}\n"
        f"Активных заказов: {active_orders}\n"
        f"Пробных заявок: {trials_count}\n"
        f"Заявок «Хочу несколько»: {multi_count}\n"
        f"Заявок «Другое»: {custom_count}\n"
        f"Свободных CapCut аккаунтов: {free_capcut}"
    )


def get_admin_capcut_text() -> str:
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM capcut_accounts")
    total_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM capcut_accounts WHERE is_used = 0")
    free_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM capcut_accounts WHERE is_used = 1")
    used_count = cur.fetchone()[0]

    conn.close()

    return (
        "🎬 CapCut\n\n"
        f"Всего аккаунтов: {total_count}\n"
        f"Свободных: {free_count}\n"
        f"Выданных: {used_count}\n\n"
        "Через кнопку «Добавить аккаунт» можно быстро пополнить пул."
    )


def get_admin_orders_text() -> str:
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT order_number, product_name, status, created_at
        FROM orders
        ORDER BY id DESC
        LIMIT 10
        """
    )
    orders = cur.fetchall()

    cur.execute(
        """
        SELECT order_number, full_name, status, created_at
        FROM free_trials
        ORDER BY id DESC
        LIMIT 5
        """
    )
    trials = cur.fetchall()
    conn.close()

    lines = ["📦 Последние заказы\n"]
    if orders:
        for order_number, product_name, status, created_at in orders:
            lines.append(f"{order_number} | {product_name} | {status} | {created_at}")
    else:
        lines.append("Заказов пока нет.")

    lines.append("\n🎁 Последние пробные заявки")
    if trials:
        for order_number, full_name, status, created_at in trials:
            lines.append(f"{order_number} | {full_name} | {status} | {created_at}")
    else:
        lines.append("Пробных заявок пока нет.")

    lines.append("\nДля поиска конкретного заказа: /find_order #XXXXXXXXXX")
    return "\n".join(lines)


async def start_broadcast_flow(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Отправьте сообщение для рассылки.\n"
        "Поддерживаются текст, фото, видео, документ и другие вложения."
    )
    await state.set_state(BroadcastState.waiting_message)


@dp.message(F.text == "/admin")
async def admin_panel_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    touch_user_activity(message.from_user.id)
    await state.clear()
    await message.answer("Админ-панель", reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "admin_panel")
async def admin_panel_callback_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    await callback.answer()
    await state.clear()
    await safe_edit_text(callback, "Админ-панель", reply_markup=admin_panel_kb())


@dp.message(F.text == "/stats")
async def admin_stats_handler(message: Message):
    if not is_admin(message.from_user.id):
        return

    touch_user_activity(message.from_user.id)
    await message.answer(get_admin_stats_text(), reply_markup=admin_back_kb())


@dp.callback_query(F.data == "admin_stats")
async def admin_stats_callback_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    await callback.answer()
    await safe_edit_text(callback, get_admin_stats_text(), reply_markup=admin_back_kb())


@dp.callback_query(F.data == "admin_capcut")
async def admin_capcut_callback_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    await callback.answer()
    await safe_edit_text(callback, get_admin_capcut_text(), reply_markup=admin_back_kb())


@dp.callback_query(F.data == "admin_orders")
async def admin_orders_callback_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    await callback.answer()
    await safe_edit_text(callback, get_admin_orders_text(), reply_markup=admin_back_kb())


@dp.callback_query(F.data == "admin_add_account")
async def admin_add_account_callback_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    await callback.answer()
    await state.set_state(AdminPanelState.waiting_capcut_account)
    await safe_edit_text(
        callback,
        "Отправьте логин и пароль аккаунта CapCut одним сообщением.\n\nФормат: <code>login password</code>",
        reply_markup=admin_back_kb()
    )


@dp.message(AdminPanelState.waiting_capcut_account)
async def admin_add_capcut_from_panel_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    touch_user_activity(message.from_user.id)
    parts = (message.text or "").strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Неверный формат. Используйте: <code>login password</code>")
        return

    login, password = parts[0].strip(), parts[1].strip()
    add_capcut_account(login, password)
    await state.clear()
    await message.answer("✅ Аккаунт CapCut добавлен.", reply_markup=admin_panel_kb())


@dp.message(F.text.startswith("/add_capcut "))
async def add_capcut_handler(message: Message):
    if not is_admin(message.from_user.id):
        return

    touch_user_activity(message.from_user.id)
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Используй: /add_capcut логин пароль")
        return

    login = parts[1].strip()
    password = parts[2].strip()
    add_capcut_account(login, password)
    await message.answer("✅ Аккаунт добавлен.", reply_markup=admin_panel_kb())


# =========================================================
# ADMIN BROADCAST AND ADMIN TOOLS
# =========================================================

@dp.message(F.text == "/broadcast")
async def broadcast_command_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    touch_user_activity(message.from_user.id)
    await start_broadcast_flow(message, state)


@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_callback_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    await callback.answer()
    await callback.message.answer("Открываю сценарий рассылки.")
    await start_broadcast_flow(callback.message, state)


@dp.message(BroadcastState.waiting_message)
async def process_broadcast_message(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    touch_user_activity(message.from_user.id)
    await state.update_data(
        broadcast_message_chat_id=message.chat.id,
        broadcast_message_id=message.message_id,
        broadcast_button=None,
    )
    await message.answer(
        "Выберите тип кнопки для рассылки:",
        reply_markup=admin_broadcast_type_kb()
    )
    await state.set_state(BroadcastState.waiting_button_type)


@dp.callback_query(F.data == "broadcast_cancel")
async def broadcast_cancel_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    await callback.answer("Рассылка отменена")
    await state.clear()
    await callback.message.answer("Сценарий рассылки отменён.", reply_markup=admin_panel_kb())


@dp.callback_query(BroadcastState.waiting_button_type, F.data == "broadcast_type_skip")
async def broadcast_type_skip_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    await callback.answer()
    await state.update_data(broadcast_button=None)
    preview_sent = await send_broadcast_preview(callback.message.chat.id, state)
    if preview_sent:
        await state.set_state(BroadcastState.waiting_confirm)


@dp.callback_query(BroadcastState.waiting_button_type, F.data == "broadcast_type_bot")
async def broadcast_type_bot_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    await callback.answer()
    await state.set_state(BroadcastState.waiting_bot_button_text)
    await callback.message.answer(
        "Введите текст кнопки. Эта кнопка откроет раздел подписок в боте."
    )


@dp.message(BroadcastState.waiting_bot_button_text)
async def broadcast_bot_button_text_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Текст кнопки не должен быть пустым.")
        return

    await state.update_data(
        broadcast_button={
            "type": "callback",
            "text": text,
            "target": "open_subscriptions",
        }
    )
    preview_sent = await send_broadcast_preview(message.chat.id, state)
    if preview_sent:
        await state.set_state(BroadcastState.waiting_confirm)


@dp.callback_query(BroadcastState.waiting_button_type, F.data == "broadcast_type_url")
async def broadcast_type_url_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    await callback.answer()
    await state.set_state(BroadcastState.waiting_url_button)
    await callback.message.answer(
        "Отправьте кнопку в формате:\n<code>Текст кнопки|https://example.com</code>"
    )


@dp.message(BroadcastState.waiting_url_button)
async def broadcast_url_button_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    raw_value = (message.text or "").strip()
    parts = raw_value.split("|", 1)
    if len(parts) < 2:
        await message.answer("Неверный формат. Используйте: <code>Текст кнопки|https://example.com</code>")
        return

    btn_text = parts[0].strip()
    btn_url = parts[1].strip()
    if not btn_text or not btn_url.lower().startswith(("http://", "https://")):
        await message.answer("Укажите текст кнопки и корректный URL.")
        return

    await state.update_data(
        broadcast_button={
            "type": "url",
            "text": btn_text,
            "target": btn_url,
        }
    )
    preview_sent = await send_broadcast_preview(message.chat.id, state)
    if preview_sent:
        await state.set_state(BroadcastState.waiting_confirm)


@dp.callback_query(BroadcastState.waiting_confirm, F.data == "broadcast_confirm_cancel")
async def broadcast_confirm_cancel_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    await callback.answer("Рассылка отменена")
    await state.clear()
    await callback.message.answer("Рассылка отменена.", reply_markup=admin_panel_kb())


@dp.callback_query(BroadcastState.waiting_confirm, F.data == "broadcast_confirm_send")
async def broadcast_confirm_send_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    await callback.answer()
    data = await state.get_data()
    chat_id = data.get("broadcast_message_chat_id")
    msg_id = data.get("broadcast_message_id")
    reply_markup = build_broadcast_reply_markup(data.get("broadcast_button"))

    if not chat_id or not msg_id:
        await state.clear()
        await callback.message.answer("Не удалось получить сообщение для рассылки.", reply_markup=admin_panel_kb())
        return

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users")
    user_ids = [row[0] for row in cur.fetchall()]
    conn.close()

    success_count = 0
    error_count = 0
    for uid in user_ids:
        try:
            if reply_markup:
                await bot.copy_message(
                    chat_id=uid,
                    from_chat_id=chat_id,
                    message_id=msg_id,
                    reply_markup=reply_markup,
                )
            else:
                await bot.copy_message(
                    chat_id=uid, from_chat_id=chat_id, message_id=msg_id
                )
            success_count += 1
        except Exception as e:
            print("Broadcast error to", uid, e)
            error_count += 1

    await state.clear()
    await callback.message.answer(
        "📢 Рассылка завершена.\n\n"
        f"Успешно: {success_count}\n"
        f"Ошибок: {error_count}",
        reply_markup=admin_panel_kb()
    )


@dp.message(F.text.startswith("/find_order"))
async def admin_find_order_handler(message: Message):
    """
    Allow administrators to quickly look up order or trial details by order number.
    Usage: /find_order <order_number>
    """
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используй: /find_order #XXXXXXXXXX")
        return
    order_number = parts[1].strip()
    # Ensure the order number starts with '#'
    if not order_number.startswith("#"):
        order_number = "#" + order_number
    order = get_order(order_number)
    if order:
        (
            _order_num,
            telegram_id,
            product_code,
            product_name,
            price_uzs,
            price_usd,
            payment_method,
            status,
            details,
            created_at,
            expires_at,
        ) = order
        text = (
            f"Заказ: {order_number}\n"
            f"Пользователь: {telegram_id}\n"
            f"Товар: {product_name}\n"
            f"Код товара: {product_code}\n"
            f"Сумма: {price_uzs} сум{(' / ' + str(price_usd) + '$') if price_usd else ''}\n"
            f"Метод: {payment_method or '-'}\n"
            f"Статус: {status}\n"
            f"Создан: {created_at}\n"
            f"Истекает: {expires_at or '-'}\n"
            f"Детали: {details or '-'}"
        )
        await message.answer(text)
        return
    # If not found in orders, try free trials
    trial = get_free_trial(order_number)
    if trial:
        (
            _order_num,
            telegram_id,
            username,
            full_name,
            phone,
            gmail,
            status,
            created_at,
        ) = trial
        # Expires_at and reminder_sent may not be present if DB is older; handle gracefully
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("SELECT expires_at, reminder_sent FROM free_trials WHERE order_number = ?", (order_number,))
            exp_row = cur.fetchone()
            expires_at = exp_row[0] if exp_row else "-"
        except Exception:
            expires_at = "-"
        conn.close()
        text = (
            f"Пробная заявка: {order_number}\n"
            f"Пользователь: {telegram_id}\n"
            f"Имя пользователя: {username}\n"
            f"Полное имя: {full_name}\n"
            f"Телефон: {phone}\n"
            f"Gmail: {gmail}\n"
            f"Статус: {status}\n"
            f"Создана: {created_at}\n"
            f"Истекает: {expires_at}"
        )
        await message.answer(text)
        return
    await message.answer("Заказ не найден.")


# =========================================================
# FALLBACK
# =========================================================

@dp.message()
async def fallback_handler(message: Message):
    add_user_if_not_exists(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name
    )
    touch_user_activity(message.from_user.id)

    if not has_selected_language(message.from_user.id):
        await message.answer(
            f"<b>{TEXTS['ru']['choose_language']}</b>",
            reply_markup=language_kb()
        )
        return

    await safe_answer_message(
        message,
        get_main_menu_text(message.from_user.id),
        reply_markup=main_menu_kb(message.from_user.id)
    )


# =========================================================
# MAIN
# =========================================================

async def main():
    init_db()
    if not acquire_polling_lock():
        print("BOT START BLOCKED: another local bot instance is already running. Stop it and restart this bot.")
        return

    try:
        # Launch the reminder loop as a background task. It will periodically check
        # for subscriptions nearing expiry and send notifications to users. The
        # task runs concurrently with the polling process.
        asyncio.create_task(reminder_loop())
        await dp.start_polling(bot, drop_pending_updates=True)
    except TelegramConflictError:
        print("BOT POLLING CONFLICT: Telegram reports another getUpdates request. Stop the other bot instance and restart.")
    finally:
        release_polling_lock()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())


