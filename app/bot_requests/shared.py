import os
import json
import sqlite3
from datetime import datetime, timedelta
import pytz
import telebot
from telebot import types
from geopy.geocoders import Nominatim
from dotenv import load_dotenv
import logging
import subprocess
from pywebpush import webpush, WebPushException

# Загружаем переменные окружения
load_dotenv()

# Конфигурация логирования
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация бота (объект bot будет импортирован из __init__.py, но здесь пока оставим для полноты)
# BOT_TOKEN = os.getenv("BOT_TOKEN")
# bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Глобальные переменные
user_states = {}
requests_list = []
chat_action_allowed = {"участок№1": True, "участок№2": True}
RIGHTS_FILE = "chat_rights.json"
AUTHORIZED_USERS_FILE = "authorized_users.json"
authorized_users = {}

# Push-уведомления
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_CLAIMS = {"sub": "mailto:elestack.ms@gmail.com"}
SUBS_FILE = "subscriptions.json"
subscriptions = []


# Часовой пояс
kyiv_tz = pytz.timezone("Europe/Kyiv")

# Права нажатия
action_rights = {"allow_chat_actions": True}

# ---------- сгенерировать карту RU→UA при старте ----------
subprocess.run(["python3", "generate_ru_to_ua.py"], check=True)

with open("addresses.json", encoding="utf-8") as f:
    address_data = json.load(f)
with open("map_ru_to_ua.json", encoding="utf-8") as f:
    map_ru_to_ua = json.load(f)

def clean_currency_format(value):
    """Converts Ukrainian formatted currency (with commas) to float"""
    if value is None:
        return 0.0
    return float(str(value).replace(',', '.').replace(' ', ''))

def format_currency_ua(value):
    """Formats currency in Ukrainian format: 72861.44 -> 72,861,44 ₴"""
    if not value:
        return "0,00 ₴"
    
    # Convert to float if string
    if isinstance(value, str):
        value = clean_currency_format(value)
    
    # Format with thousands separator and comma as decimal separator
    formatted = f"{value:,.2f}".replace(',', '|').replace('.', ',').replace('|', ',')
    return f"{formatted} ₴"
    
# Районы и чаты персонала
districts = [
    ("Заводський р-н",  "участок№2", ["+380683038651", "+380663038652"]),
    ("Центральний р-н", "участок№2", ["+380683038651", "+380663038652"]),
    ("Інгульський р-н", "участок№2", ["+380683038651", "+380663038652"]),
    ("Корабельний р-н", "участок№1", ["+380683038602", "+380503038602"]),
]
district_names = [d[0] for d in districts]
district_ids = {d[0]: d[1] for d in districts}
district_phones = {d[0]: d[2] for d in districts}
personnel_chats = {"участок№1": -1002647024429, "участок№2": -1002530162702} # Заглушки, используйте свои актуальные ID чатов

# Данные адресов
address_data = {}
map_ru_to_ua = {}
STREET_WORDS_TO_REMOVE = ["вулиця", "проспект", "площа", "провулок", "вул", "просп", "пер", "ул", "улица", "street", "st", "avenue"]

def clean_street_name(name: str) -> str:
    name = name.lower()
    for word in STREET_WORDS_TO_REMOVE:
        name = name.replace(word, "")
    return name.strip()

def match_address(street_raw: str, building: str, district: str) -> str | None:
    street_key = street_raw.lower().strip()
    ua_name = map_ru_to_ua.get(street_key)
    if not ua_name:
        for k, v in map_ru_to_ua.items():
            if street_key.startswith(k) or k.startswith(street_key):
                ua_name = v
                break
    if not ua_name:
        return None

    building = building.lower()
    if district not in address_data:
        return None

    for full, houses in address_data[district].items():
        if ua_name.lower() in full.lower():
            # Проверяем, есть ли номер дома в списке домов для этой улицы
            if building in [h.lower() for h in houses]:
                return full
    return None


# Функции для загрузки/сохранения глобального состояния
def save_authorized_users():
    with open(AUTHORIZED_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(authorized_users, f, ensure_ascii=False, indent=2)
    print("✅ Збережено authorized_users.json")

def load_authorized_users():
    global authorized_users
    if os.path.exists(AUTHORIZED_USERS_FILE):
        with open(AUTHORIZED_USERS_FILE, "r", encoding="utf-8") as f:
            authorized_users = json.load(f)
            print("✅ Завантажено authorized_users.json")
    else:
        print("ℹ️ authorized_users.json не знайдено, створюємо новий.")
        authorized_users = {"ADMINS": []} # Пример: Добавьте ID админов здесь
        save_authorized_users()


def load_action_rights():
    global chat_action_allowed
    if os.path.exists(RIGHTS_FILE):
        with open(RIGHTS_FILE, encoding="utf-8") as f:
            chat_action_allowed = json.load(f)
            print("✅ Завантажено chat_rights.json")
    else:
        print("ℹ️ chat_rights.json не знайдено, використовуємо значення за замовчуванням.")

def save_action_rights():
    with open(RIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(chat_action_allowed, f, ensure_ascii=False)
    print("✅ Збережено chat_rights.json")

def save_subscriptions():
    with open(SUBS_FILE, "w", encoding="utf-8") as f:
        json.dump(subscriptions, f, ensure_ascii=False, indent=2)
    print("✅ Збережено subscriptions.json")

def load_subscriptions():
    global subscriptions
    if os.path.exists(SUBS_FILE):
        with open(SUBS_FILE, "r", encoding="utf-8") as f:
            subscriptions = json.load(f)
            print("✅ Завантажено subscriptions.json")
    else:
        print("ℹ️ subscriptions.json не знайдено, створюємо новий.")
        subscriptions = []
        save_subscriptions()

def load_address_data():
    global address_data, map_ru_to_ua
    try:
        with open("address_data.json", "r", encoding="utf-8") as f:
            full_data = json.load(f)
            address_data = full_data.get("address_data", {})
            map_ru_to_ua = full_data.get("map_ru_to_ua", {})
            print("✅ Завантажено address_data.json")
    except FileNotFoundError:
        print("❌ address_data.json не знайдено.")
        address_data = {}
        map_ru_to_ua = {}
    except json.JSONDecodeError:
        print("❌ Помилка декодування JSON у address_data.json.")
        address_data = {}
        map_ru_to_ua = {}

def log_action(user_id, action_type, details=None):
    """
    Функция для логирования действий бота.
    Записывает действия в консоль и, при желании, в файл.
    """
    timestamp = datetime.now(kyiv_tz).strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "timestamp": timestamp,
        "user_id": user_id,
        "action_type": action_type,
        "details": details if details is not None else {}
    }
    # Выводим в консоль
    print(f"📝 LOG_ACTION: {json.dumps(log_entry, ensure_ascii=False)}")

    # Опционально: можно записывать в отдельный файл логов
    # try:
    #     with open("bot_actions_log.json", "a", encoding="utf-8") as f:
    #         json.dump(log_entry, ensure_ascii=False)
    #         f.write("\n") # Добавляем новую строку для каждой записи
    # except Exception as e:
    #     print(f"⚠️ Ошибка при записи в лог-файл: {e}")

# Функции для работы с базой данных
def init_database():
    conn = sqlite3.connect('requests.db')
    cursor = conn.cursor()
    cursor.execute('''
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
    ''')
    conn.commit()
    conn.close()

def save_requests_to_db():
    conn = sqlite3.connect('requests.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM requests') # Очищаем и перезаписываем для простоты
    for r in requests_list:
        cursor.execute('''
            INSERT INTO requests (
                name, district, address, entrance, issue, phone,
                timestamp, completed, completed_time, processed_by,
                chat_msg_id, status, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            r.get("name", ""), r.get("district", ""), r.get("address", ""),
            r.get("entrance", ""), r.get("issue", ""), r.get("phone", ""),
            r.get("timestamp", ""), r.get("completed", False),
            r.get("completed_time", ""), r.get("processed_by", ""),
            r.get("chat_msg_id", ""), r.get("status", "pending"),
            r.get("user_id", None)
        ))
    conn.commit()
    conn.close()
    print("✅ Заявки збережено в базу даних.")


def load_requests_from_db():
    global requests_list
    conn = sqlite3.connect('requests.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM requests')
    rows = cursor.fetchall()
    requests_list = []
    for row in rows:
        req = {
            "id": row[0],
            "name": row[1],
            "district": row[2],
            "address": row[3],
            "entrance": row[4],
            "issue": row[5],
            "phone": row[6],
            "timestamp": row[7],
            "completed": bool(row[8]),
            "completed_time": row[9],
            "processed_by": row[10],
            "chat_msg_id": row[11],
            "status": row[12],
            "user_id": row[13]
        }
        requests_list.append(req)
    conn.close()
    print(f"✅ Завантажено {len(requests_list)} заявок з бази даних.")

def send_push(title, body):
    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub,
                data=json.dumps({"title": title, "body": body}),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS
            )
            print(f"✅ Push-уведомление отправлено для {sub['endpoint']}")
        except WebPushException as e:
            if e.response.status_code == 404:
                print(f"❌ Push-подписка не найдена, удаляем: {sub['endpoint']}")
                subscriptions.remove(sub)
                save_subscriptions()
            else:
                print(f"⚠️ Ошибка отправки push-уведомления: {e}")
        except Exception as e:
            print(f"⚠️ Неизвестная ошибка при отправке push-уведомления: {e}")