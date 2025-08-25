# app/bot_maintenance/shared.py
import os
import json
import sqlite3
import logging
from datetime import datetime
from typing import Optional
from pytz import timezone
import telebot

logger = logging.getLogger(__name__)

# Timezone
kyiv_tz = timezone("Europe/Kyiv")

# Paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "maintenance.db")

# Shared runtime state
maintenance_logs: list[dict] = []        # список выполненных ТО
maintenance_schedule: dict = {}          # график ТО (можно загрузить из JSON)
user_states: dict = {}                   # временные состояния пользователей (приём ТО)

# ---------- Bot instance ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN_MAINTENANCE") or ""
if not BOT_TOKEN:
    logger.warning("BOT_TOKEN_MAINTENANCE not set — bot will not run without token")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ---------- Database helpers ----------
def init_database(db_path: Optional[str] = None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mechanic_name TEXT,
            district TEXT,
            address TEXT,
            date TEXT,
            photo_file_id TEXT,
            notes TEXT,
            verified BOOLEAN DEFAULT 0,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Initialized maintenance DB at %s", path)

def save_maintenance_log(log: dict):
    path = DB_PATH
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO maintenance_logs (
                mechanic_name, district, address, date, photo_file_id, notes, verified, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            log.get("mechanic_name", ""),
            log.get("district", ""),
            log.get("address", ""),
            log.get("date", ""),
            log.get("photo_file_id", ""),
            log.get("notes", ""),
            int(log.get("verified", False)),
            log.get("created_at", datetime.now(kyiv_tz).isoformat())
        ))
        conn.commit()
        maintenance_logs.append(log)
    except Exception:
        logger.exception("Failed to save maintenance log")
    finally:
        conn.close()

def load_maintenance_logs():
    path = DB_PATH
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM maintenance_logs ORDER BY id")
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description]
        maintenance_logs.clear()
        for row in rows:
            maintenance_logs.append(dict(zip(columns, row)))
        return maintenance_logs
    except Exception:
        logger.exception("Failed to load maintenance logs")
        return []
    finally:
        conn.close()
