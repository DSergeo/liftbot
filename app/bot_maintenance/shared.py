# app/bot_maintenance/shared.py
import os
import json
import sqlite3
import logging
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List
from pytz import timezone
import telebot
import math

logger = logging.getLogger(__name__)

# Timezone
kyiv_tz = timezone("Europe/Kyiv")

# Paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "maintenance.db")
ADDRESSES_JSON = os.path.join(PROJECT_ROOT, "addresses.json")  # твой файл с геоточек

# Shared runtime state
maintenance_logs: List[Dict[str, Any]] = []   # список выполненных ТО
maintenance_schedule: Dict[str, List[str]] = {}  # {address_key: ["YYYY-MM-DD", ...]}
user_states: Dict[int, Dict[str, Any]] = {}   # временные состояния пользователей
address_data: Dict[str, Any] = {}             # полный словарь адресов/подъездов

# ---------- Bot instance ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN_MAINTENANCE") or ""
if not BOT_TOKEN:
    logger.warning("BOT_TOKEN_MAINTENANCE not set — bot will not run without token")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ---------- Utils ----------
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между двумя точками в метрах (без внешних зависимостей)."""
    R = 6371000.0
    f1 = math.radians(lat1)
    f2 = math.radians(lat2)
    df = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(df/2)**2 + math.cos(f1) * math.cos(f2) * math.sin(dl/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def normalize_text(s: str) -> str:
    """Для грубого сопоставления адресов в графике и в базе адресов."""
    s = (s or "").lower()
    repl = {
        "просп.": "", "пр.": "", "вул.": "", "улица": "", "вулиця": "",
        "проспект": "", "просп": "", "ул.": "", "  ": " "
    }
    for k,v in repl.items():
        s = s.replace(k, v)
    return " ".join(s.split()).strip()

def schedule_key_candidates(street: str, building: str) -> List[str]:
    """
    Возвращает список возможных ключей для поиска в графике.
    В excel-расшифровке часто ключ выглядит как 'вул. Айвазовского 7_1', '... 7_2' и т.п.
    Здесь мы вернём все ключи из графика, которые начинаются со 'street building'.
    """
    prefix_norm = normalize_text(f"{street} {building}")
    candidates = []
    for addr_key in maintenance_schedule.keys():
        if normalize_text(addr_key).startswith(prefix_norm):
            candidates.append(addr_key)
    return candidates

# ---------- Addresses loader ----------
def load_addresses() -> None:
    global address_data
    try:
        with open(ADDRESSES_JSON, "r", encoding="utf-8") as f:
            address_data = json.load(f)
        logger.info("Loaded addresses.json with %d districts", len(address_data))
    except Exception:
        address_data = {}
        logger.exception("Failed to load addresses.json from %s", ADDRESSES_JSON)

def find_address_by_geo(lat: float, lon: float) -> Optional[Tuple[str, str, str, str]]:
    """
    Ищем ближайший подъезд в пределах своего радиуса и только если active == true.
    Возвращает (district, street, building, entrance) или None.
    """
    if not address_data:
        return None

    best = None
    best_dist = float("inf")

    # Структура: district -> street -> building -> entrance -> {lat, lon, radius, active}
    for district, streets in address_data.items():
        for street, buildings in streets.items():
            for building, entrances in buildings.items():
                for entrance, point in entrances.items():
                    try:
                        plat = float(point.get("lat"))
                        plon = float(point.get("lon"))
                        pradius = float(point.get("radius", 0))
                        active = bool(point.get("active", True))
                    except Exception:
                        continue
                    if not active:
                        continue
                    d = haversine_m(lat, lon, plat, plon)
                    # Совпадение – только если попали в радиус точки
                    if d <= pradius and d < best_dist:
                        best_dist = d
                        best = (district, street, building, entrance)

    return best

def get_entrances_for_building(street: str, building: str) -> List[str]:
    """Возвращает список всех подъездов для найденного дома (из addresses.json)."""
    for d_streets in address_data.values():
        if street in d_streets:
            b = d_streets[street].get(building, {})
            return sorted([e for e in b.keys()], key=lambda x: (len(x), x))
    return []

# ---------- Database helpers ----------
def init_database(db_path: Optional[str] = None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    # Логи ТО
    cur.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mechanic_name TEXT,
            district TEXT,
            address TEXT,
            entrance TEXT,
            date TEXT,
            photo_file_id TEXT,
            notes TEXT,
            verified BOOLEAN DEFAULT 0,
            created_at TEXT
        )
    """)
    # График ТО (таблица для загрузки из excel)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT,
            reg_number TEXT,
            mechanic TEXT,
            month TEXT,
            day INTEGER
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
                mechanic_name, district, address, entrance, date,
                photo_file_id, notes, verified, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            log.get("mechanic_name", ""),
            log.get("district", ""),
            log.get("address", ""),
            log.get("entrance", ""),
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

def load_maintenance_schedule():
    """
    Загружаем график ТО в память (dict[address_key] = [YYYY-MM-DD, ...], год фикс 2025).
    Ключ address_key — как в excel-столбце "Адреса ліфта" (например: 'вул. Айвазовского 7_1').
    """
    global maintenance_schedule
    path = DB_PATH
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT address, month, day FROM maintenance_schedule")
        rows = cur.fetchall()
        maintenance_schedule.clear()
        month_map = {
            "Січень": 1, "Лютий": 2, "Березень": 3, "Квітень": 4,
            "Травень": 5, "Червень": 6, "Липень": 7, "Серпень": 8,
            "Вересень": 9, "Жовтень": 10, "Листопад": 11, "Грудень": 12
        }
        for address, month, day in rows:
            m = month_map.get(month)
            if not m or not day:
                continue
            date_str = f"2025-{m:02d}-{int(day):02d}"
            maintenance_schedule.setdefault(address, []).append(date_str)
        logger.info("Loaded maintenance_schedule with %d addresses", len(maintenance_schedule))
    except Exception:
        logger.exception("Failed to load maintenance schedule")
    finally:
        conn.close()

# ---------- Bootstrap on import ----------
try:
    init_database()
except Exception:
    logger.exception("init_database failed")

try:
    load_addresses()
except Exception:
    logger.exception("load_addresses failed")

try:
    load_maintenance_schedule()
except Exception:
    logger.exception("load_maintenance_schedule failed")
