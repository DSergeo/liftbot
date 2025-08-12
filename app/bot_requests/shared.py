# app/bot_requests/shared.py
"""
Shared state and utilities for bot + web dashboard.

Содержит:
- общие переменные (requests_list, user_states, district_* и т.д.)
- sqlite helper'ы: init_database, save_requests_to_db, load_requests_from_db
- функции для адресов: match_address, clean_street_name
- создание telebot.TeleBot (читает BOT_TOKEN из окружения)
- простые утилиты: log_action, save_authorized_users, send_push (stub)
"""

from __future__ import annotations

import os
import json
import sqlite3
import subprocess
import logging
from datetime import datetime
from typing import Optional

from pytz import timezone

# third-party
import telebot

logger = logging.getLogger(__name__)

# timezone
kyiv_tz = timezone("Europe/Kyiv")

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # app/bot_requests
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))  # repo root
DB_PATH = os.path.join(PROJECT_ROOT, "requests.db")
ADDRESSES_JSON = os.path.join(PROJECT_ROOT, "addresses.json")
MAP_RU_TO_UA_JSON = os.path.join(PROJECT_ROOT, "map_ru_to_ua.json")
AUTHORIZED_USERS_FILE = os.path.join(PROJECT_ROOT, "authorized_users.json")
SUBS_FILE = os.path.join(PROJECT_ROOT, "subscriptions.json")

# Ensure DB_PATH directory exists (usually project root exists)
# ---------- shared runtime state ----------
requests_list: list[dict] = []        # основной список заявок в памяти
user_states: dict = {}               # временные состояния пользователей (приём заявки)

# default control flags
chat_action_allowed = {"участок№1": True, "участок№2": True}

# districts / personnel — можно править здесь
districts = [
    ("Заводський р-н",  "участок№2", ["+380683038651", "+380663038652"]),
    ("Центральний р-н", "участок№2", ["+380683038651", "+380663038652"]),
    ("Інгульський р-н", "участок№2", ["+380683038651", "+380663038652"]),
    ("Корабельний р-н", "участок№1", ["+380683038602", "+380503038602"]),
]
district_names = [d[0] for d in districts]
district_ids = {d[0]: d[1] for d in districts}
district_phones = {d[0]: d[2] for d in districts}
personnel_chats = {"участок№1": -1002647024429, "участок№2": -1002530162702}

# Authorized users structure (loaded/saved to JSON)
authorized_users: dict = {}
# chat_rights.json / other files handled by main; тут — только helpers

# ---------- Load address files (if present) ----------
address_data: dict = {}
map_ru_to_ua: dict = {}

def _load_address_files():
    global address_data, map_ru_to_ua
    # optional: run generator if map file missing
    try:
        if not os.path.exists(MAP_RU_TO_UA_JSON) and os.path.exists(os.path.join(PROJECT_ROOT, "generate_ru_to_ua.py")):
            subprocess.run(["python3", os.path.join(PROJECT_ROOT, "generate_ru_to_ua.py")], check=True)
    except Exception as e:
        logger.warning("Map generation failed: %s", e)

    try:
        if os.path.exists(ADDRESSES_JSON):
            with open(ADDRESSES_JSON, encoding="utf-8") as f:
                address_data = json.load(f)
        else:
            address_data = {}

        if os.path.exists(MAP_RU_TO_UA_JSON):
            with open(MAP_RU_TO_UA_JSON, encoding="utf-8") as f:
                map_ru_to_ua = json.load(f)
        else:
            map_ru_to_ua = {}
    except Exception as e:
        logger.exception("Failed to load address/map JSONs: %s", e)
        address_data = {}
        map_ru_to_ua = {}

_load_address_files()

# ---------- DB helpers ----------
def init_database(db_path: Optional[str] = None):
    """Create requests.db and table if not exists."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            district TEXT,
            address TEXT,
            entrance TEXT,
            issue TEXT,
            phone TEXT,
            timestamp TEXT,
            completed BOOLEAN DEFAULT 0,
            completed_time TEXT,
            processed_by TEXT,
            chat_msg_id TEXT,
            status TEXT DEFAULT 'pending',
            user_id INTEGER
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Initialized database at %s", path)

def save_requests_to_db(db_path: Optional[str] = None):
    """Overwrite requests table with current requests_list."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM requests")
        for r in requests_list:
            cur.execute("""
                INSERT INTO requests (
                    name, district, address, entrance, issue, phone,
                    timestamp, completed, completed_time, processed_by,
                    chat_msg_id, status, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r.get("name", ""), r.get("district", ""), r.get("address", ""),
                r.get("entrance", ""), r.get("issue", ""), r.get("phone", ""),
                r.get("timestamp", ""), int(bool(r.get("completed", False))),
                r.get("completed_time", ""), r.get("processed_by", ""),
                r.get("chat_msg_id", ""), r.get("status", "pending"),
                r.get("user_id", 0)
            ))
        conn.commit()
    except Exception:
        logger.exception("Failed to save requests to DB")
    finally:
        conn.close()

def load_requests_from_db(db_path: Optional[str] = None) -> list[dict]:
    """Load requests from DB into requests_list (in-memory)."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM requests ORDER BY id")
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description]
        requests_list.clear()
        for row in rows:
            r = dict(zip(columns, row))
            r.pop("id", None)
            if not r.get("status"):
                r["status"] = "pending"
            # sqlite stores completed as 0/1 possibly; normalize
            r["completed"] = bool(r.get("completed", False))
            requests_list.append(r)
        logger.info("Loaded %d requests from DB", len(requests_list))
        return requests_list
    except sqlite3.Error:
        logger.exception("DB load error, reinitializing DB")
        init_database(path)
        return []
    finally:
        conn.close()

# ---------- Address helpers ----------
STREET_WORDS_TO_REMOVE = [
    "вулиця", "проспект", "площа", "провулок", "вул", "просп", "пер",
    "ул", "улица", "street", "st", "avenue"
]

def clean_street_name(name: str) -> str:
    if not name:
        return ""
    s = name.lower()
    for w in STREET_WORDS_TO_REMOVE:
        s = s.replace(w, "")
    return s.strip()

def match_address(street_raw: str, building: str, district: str) -> Optional[str]:
    """Try to match user input street+building to full street name from address_data using map_ru_to_ua."""
    if not street_raw:
        return None
    street_key = street_raw.lower().strip()
    ua_name = map_ru_to_ua.get(street_key)
    if not ua_name:
        for k, v in map_ru_to_ua.items():
            if street_key.startswith(k) or k.startswith(street_key):
                ua_name = v
                break
    if not ua_name:
        # fallback: maybe cleaned street matches part of keys
        for full in address_data.get(district, {}):
            if street_key in full.lower():
                ua_name = full
                break
    if not ua_name:
        return None

    b_norm = building.lower()
    for full, houses in address_data.get(district, {}).items():
        try:
            houses_lower = [h.lower() for h in houses]
        except Exception:
            houses_lower = []
        if ua_name.lower() in full.lower() and b_norm in houses_lower:
            return full
    return None

# ---------- Authorized users helpers ----------
def save_authorized_users():
    try:
        with open(AUTHORIZED_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(authorized_users, f, ensure_ascii=False, indent=2)
        logger.info("Saved authorized_users.json")
    except Exception:
        logger.exception("Failed to save authorized users")

def load_authorized_users():
    global authorized_users
    try:
        if os.path.exists(AUTHORIZED_USERS_FILE):
            with open(AUTHORIZED_USERS_FILE, encoding="utf-8") as f:
                authorized_users = json.load(f)
            logger.info("Loaded authorized_users.json")
        else:
            authorized_users = {}
    except Exception:
        logger.exception("Failed to load authorized users")
        authorized_users = {}

load_authorized_users()

# ---------- Logging helper ----------
def log_action(user_id: int, action_type: str, details: Optional[dict] = None):
    ts = datetime.now(kyiv_tz).strftime("%Y-%m-%d %H:%M:%S")
    entry = {"timestamp": ts, "user_id": user_id, "action_type": action_type, "details": details or {}}
    logger.info("LOG_ACTION: %s", json.dumps(entry, ensure_ascii=False))

# ---------- Web-push helper (stub) ----------
def send_push(title: str, body: str):
    # Minimal stub for web-push integration — main.py can override or import pywebpush directly
    logger.debug("send_push called: %s — %s", title, body)
    # If you have pywebpush configured, implement here or keep as stub.

# ---------- Bot instance ----------
# To avoid circular imports, we create the TeleBot here and export it.
BOT_TOKEN = os.environ.get("BOT_TOKEN_REQUESTS") or ""
if not BOT_TOKEN:
    logger.warning("BOT_TOKEN_REQUESTS not set — bot will not be able to run without a token")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ---------- Convenience initialization ----------
# Initialize DB file if needed
init_database()
# Load requests into memory on import
load_requests_from_db()

# Export names for from app.bot_requests.shared import *
__all__ = [
    "bot", "requests_list", "user_states",
    "save_requests_to_db", "load_requests_from_db", "init_database",
    "match_address", "clean_street_name",
    "district_names", "district_ids", "district_phones", "personnel_chats",
    "authorized_users", "save_authorized_users", "log_action", "send_push",
    "address_data", "map_ru_to_ua", "kyiv_tz", "DB_PATH", "PROJECT_ROOT"
]
