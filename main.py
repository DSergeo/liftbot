
from dotenv import load_dotenv

load_dotenv()
from flask import Flask, render_template, jsonify, send_file, request, session, redirect, url_for

import os, json, threading, subprocess, time, schedule, logging
from flask import Flask, render_template, jsonify, send_file, request
import telebot
from telebot import types
from geopy.geocoders import Nominatim
import sqlite3
from datetime import datetime, timedelta
import pytz


logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-for-sessions-123456789')
BOT_TOKEN = os.getenv("BOT_TOKEN_REQUESTS")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
user_states, requests_list = {}, []
chat_action_allowed = {"участок№1": True, "участок№2": True}
RIGHTS_FILE = "chat_rights.json"

AUTHORIZED_USERS_FILE = "authorized_users.json"
authorized_users = {}

# Импортируем Blueprints
from app.contacts.routes import contacts_html, contacts_api
from app.counterparties.routes import counterparty_html, counterparties_api
from app.contracts.routes import contract_html, contract_api

# Регистрируем Blueprints
app.register_blueprint(contacts_html)
app.register_blueprint(contacts_api)
app.register_blueprint(counterparty_html)
app.register_blueprint(counterparties_api)
app.register_blueprint(contract_html)
app.register_blueprint(contract_api)

if os.path.exists(AUTHORIZED_USERS_FILE):
    with open(AUTHORIZED_USERS_FILE, encoding="utf-8") as f:
        authorized_users = json.load(f)

def save_authorized_users():
    with open(AUTHORIZED_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(authorized_users, f, ensure_ascii=False, indent=2)
    print("✅ Збережено authorized_users.json")

# --- ДОБАВЬТЕ ЭТУ ФУНКЦИЮ log_action СЮДА ---
def log_action(user_id, action_type, details=None):
    """
    Функция для логирования действий бота.
    Записывает действия в консоль и, при желании, в файл.
    """
    timestamp = datetime.now(pytz.timezone("Europe/Kyiv")).strftime("%Y-%m-%d %H:%M:%S")
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
    #         json.dump(log_entry, f, ensure_ascii=False)
    #         f.write("\n") # Добавляем новую строку для каждой записи
    # except Exception as e:
    #     print(f"⚠️ Ошибка при записи в лог-файл: {e}")
# --- КОНЕЦ ДОБАВЛЕННОЙ ФУНКЦИИ ---

from pywebpush import webpush, WebPushException
from dotenv import load_dotenv

load_dotenv()
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_CLAIMS = {"sub": "elestack.ms@gmail.com"}

SUBS_FILE = "subscriptions.json"
subscriptions = []

if os.path.exists(SUBS_FILE):
    with open(SUBS_FILE, encoding="utf-8") as f:
        subscriptions = json.load(f)

def save_subscriptions():
    with open(SUBS_FILE, "w", encoding="utf-8") as f:
        json.dump(subscriptions, f, ensure_ascii=False, indent=2)

def send_push(title, body):
    payload = json.dumps({"title": title, "body": body})
    for sub in subscriptions:
        try:
            webpush(subscription_info=sub, data=payload,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=VAPID_CLAIMS)
        except WebPushException as e:
            print("❌ Push error:", e)

@app.route("/vapid_public_key")
def get_vapid_key():
    return jsonify({"key": VAPID_PUBLIC_KEY})


@app.route("/subscribe_push", methods=["POST"])
def subscribe_push():
    sub = request.get_json()
    if sub and sub not in subscriptions:
        subscriptions.append(sub)
        save_subscriptions()
    return jsonify({"success": True})

@app.route("/stats_data")
def stats_data():
    pending = sum(1 for r in requests_list if not r["completed"])
    done = sum(1 for r in requests_list if r["completed"] and r.get("status") == "done")
    error = sum(1 for r in requests_list if r["completed"] and r.get("status") == "error")
    return jsonify({"pending": pending, "done": done, "error": error})

def load_action_rights():
    global chat_action_allowed
    if os.path.exists(RIGHTS_FILE):
        with open(RIGHTS_FILE, encoding="utf-8") as f:
            chat_action_allowed = json.load(f)

def save_action_rights():
    with open(RIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(chat_action_allowed, f, ensure_ascii=False)

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

# ========== SQLite Database ==========
def init_database():
    """Инициализация базы данных"""
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
    """Сохранение всех заявок в базу данных"""
    conn = sqlite3.connect('requests.db')
    cursor = conn.cursor()

    # Очищаем таблицу и заново записываем все заявки
    cursor.execute('DELETE FROM requests')

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
            r.get("user_id", 0)
        ))

    conn.commit()
    conn.close()

def load_requests_from_db():
    """Загрузка заявок из базы данных"""
    conn = sqlite3.connect('requests.db')
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT * FROM requests ORDER BY id')
        rows = cursor.fetchall()

        # Получаем названия столбцов
        columns = [description[0] for description in cursor.description]
        
        requests_list.clear()  # Clear existing list
        for row in rows:
            r = dict(zip(columns, row))
            # Удаляем id из словаря (он не нужен в requests_list)
            r.pop('id', None)
            if not r.get("status"):
                r["status"] = "pending"
            requests_list.append(r)
        
        print(f"Loaded {len(requests_list)} requests from database")
        return requests_list
    except sqlite3.Error as e:
        print(f"Ошибка при загрузке из базы данных: {e}")
        init_database()
        return []
    finally:
        conn.close()

# ========== SQLite Database ==========
# Старая Excel функция удалена
# ========== Адреса ==========
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
    for full, houses in address_data[district].items():
        if ua_name.lower() in full.lower() and building in [h.lower() for h in houses]:
            return full
    return None

STREET_WORDS_TO_REMOVE = ["вулиця", "проспект", "площа", "провулок", "вул", "просп", "пер", "ул", "улица", "street", "st", "avenue"]

def clean_street_name(name: str) -> str:
    name = name.lower()
    for word in STREET_WORDS_TO_REMOVE:
        name = name.replace(word, "")
    return name.strip()

# Initialize database and load existing requests at startup
init_database()
load_requests_from_db()

@bot.message_handler(commands=["start"])
def cmd_start(msg):
    if msg.chat.type != "private":
        return
    user_states[msg.chat.id] = {"step": "name", "user_id": msg.chat.id}
    bot.send_message(msg.chat.id, "👋 <b>Вітаю!</b>\nЯ бот для прийома заявок з ремонту ліфтів.\n\nВведіть ваше ім’я будь ласка:")

@bot.message_handler(commands=["заявки"])
def cmd_requests(msg):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🕐 Очікують", callback_data="filter:pending"),
        types.InlineKeyboardButton("✅ Виконані", callback_data="filter:done"),
        types.InlineKeyboardButton("❌ Не працює", callback_data="filter:error"),
    )
    bot.send_message(msg.chat.id, "Оберіть тип заявок для перегляду:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.chat.type == "private", content_types=["text"])
def handle_text(msg):
    st = user_states.get(msg.chat.id)
    if not st:
        return bot.send_message(msg.chat.id, "Натисніть /start щоб почати.")
    step = st["step"]

    if step == "name":
        st["name"] = " ".join(msg.text.split())
        st["step"] = "choose_input"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("📍 Надіслати геолокацію", "✏️ Ввести адресу вручну")
        return bot.send_message(msg.chat.id, "Оберіть спосіб введення адреси:", reply_markup=kb)

    if step == "choose_input":
        if msg.text == "✏️ Ввести адресу вручну":
            st["step"] = "choose_district"
            kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            for d in district_names:
                kb.add(d)
            return bot.send_message(msg.chat.id, "Оберіть район:", reply_markup=kb)
        if msg.text == "📍 Надіслати геолокацію":
            return bot.send_message(msg.chat.id, "📎 Надішліть геолокацію через скрепку.")
        return bot.send_message(msg.chat.id, "Будь ласка, оберіть опцію з клавіатури.")

    if step == "choose_district":
        if msg.text not in district_names:
            return bot.send_message(msg.chat.id, "❌ Невірний район, спробуйте ще.")
        st["district"], st["step"] = msg.text, "enter_address"
        return bot.send_message(msg.chat.id, "Введіть адресу (Лазурна 32):", reply_markup=types.ReplyKeyboardRemove())

    if step == "enter_address":
        parts = msg.text.split()
        if len(parts) < 2:
            return bot.send_message(msg.chat.id, "❌ Формат: назва вулиці + номер будинку")
        street, b = " ".join(parts[:-1]), parts[-1]
        found = match_address(street, b, st["district"])
        if not found:
            return bot.send_message(msg.chat.id, "❌ Адреса не знайдена, спробуйте ще.")
        st["address"] = f"{found}, {b}"
        st["step"] = "enter_entrance"
        return bot.send_message(msg.chat.id, "Введіть номер під'їзду:", reply_markup=types.ReplyKeyboardRemove())

    if step == "enter_entrance":
        print("➡️ Введено під'їзд:", msg.text)
        print("➡️ Адреса:", st.get("address"))
        print("➡️ Район:", st.get("district"))
        if not msg.text.isdigit() or len(msg.text) > 2:
            return bot.send_message(msg.chat.id, "❌ Введіть лише цифри (не більше 2):")

        st["entrance"] = msg.text

        # ➡️ Перевірка на блокування адреси після ❌
        print(f"➡️ Введено під'їзд: {st['entrance']}")
        print(f"➡️ Адреса: {st['address']}")
        print(f"➡️ Район: {st['district']}")
        print("🧾 Перевірка на блокування адреси...")

        for req in requests_list:
            if (
                req.get("address") == st["address"] and
                req.get("entrance") == st["entrance"] and
                req.get("status") == "error"
            ):
                try:
                    created_time = kyiv_tz.localize(datetime.strptime(req["timestamp"], "%Y-%m-%d %H:%M:%S"))
                except Exception as e:
                    print(f"⛔️ Помилка розбору дати: {e}")
                    continue

                print(f"🔍 Перевірка заявки: {req['address']} {req['entrance']} {req['status']}")
                print(f"🕒 Час помилки: {req['timestamp']}")

                now = datetime.now(kyiv_tz)
                weekday = created_time.weekday()  # Пн=0, Нд=6
                deadline = created_time + timedelta(hours=24)

                # Якщо Пт/Сб/Нд — продовжити блокування до понеділка 13:25
                if weekday in (4, 5, 6):
                    monday = created_time + timedelta(days=(7 - weekday))
                    deadline = monday.replace(hour=13, minute=25, second=0, microsecond=0)

                if now < deadline:
                    message = "⚠️ Необхідні документи піготуються і будуть передані управлляючій компанії або ОСББ"
                else:
                    message = "⚠️ Необхідні документи передані управлляючій компанії або ОСББ"

                phones = "\n".join(f"📞 {n}" for n in district_phones.get(st["district"], []))
                client_msg = f"{message}\n{phones}"

                kb = types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("📨 Створити нову заявку", callback_data="start")
                )

                bot.send_message(msg.chat.id, client_msg, reply_markup=kb)
                user_states.pop(msg.chat.id, None)
                return

        st["step"] = "enter_issue"
        return bot.send_message(msg.chat.id, "✍️ Опишіть проблему:")


    if step == "enter_issue":
        st["issue"] = msg.text
        st["step"] = "enter_phone"
        return bot.send_message(msg.chat.id, "📞 Телефон (10 цифр):")

    if step == "enter_phone":
        if not msg.text.isdigit() or len(msg.text) != 10:
            return bot.send_message(msg.chat.id, "❌ Має бути 10 цифр.")
        st["phone"] = "+38" + msg.text
        st["timestamp"] = datetime.now(kyiv_tz).strftime("%Y-%m-%d %H:%M:%S")        
        st.update(
            completed=False,
            completed_time="",
            processed_by="",
            status="pending"
        )
        idx = len(requests_list)
        requests_list.append(st.copy())

        # Формування повідомлення для клієнта
        client_msg = (
            "✅ <b>Заявку прийнято!</b>\n\n"
            "📋 <b>Дані заявки:</b>\n"
            f"👤 Ім'я: <b>{st['name']}</b>\n"
            f"📍 Адреса: <b>{st['address']} п.{st['entrance']}</b>\n"
            f"🏙️ Район: <b>{st['district']}</b>\n"
            f"🔧 Проблема: {st['issue']}\n"
            f"📱 Телефон: {st['phone']}"
        )

        # Надсилання клієнту
        kb = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("📨 Створити нову заявку", callback_data="start"))
        bot.send_message(msg.chat.id, client_msg, reply_markup=kb)

        # Надсилання у чат персоналу
        group = personnel_chats[district_ids[st["district"]]]
        group_kb = types.InlineKeyboardMarkup()
        group_kb.add(
            types.InlineKeyboardButton("✅ Виконано", callback_data=f"status:done:{idx}"),
            types.InlineKeyboardButton("🚫 Не працює", callback_data=f"status:not_working:{idx}")
        )
        sent = bot.send_message(group, client_msg, reply_markup=group_kb)
        requests_list[idx]["chat_msg_id"] = sent.message_id
        requests_list[idx]["user_id"] = msg.chat.id

        # Зберігаємо вже з повною інформацією
        save_requests_to_db()

        # 🔔 Веб-пуш
        send_push("Нова заявка", f"{st['address']} — {st['issue']}")

        # Повідомлення про аварійну службу
        phone_msg = "🔴🚨 <b>АВАРІЙНА СЛУЖБА</b> 🚨🔴\n\n"
        for n in district_phones[st["district"]]:
            phone_msg += f"📞 <a href='tel:{n}'>{n}</a>\n"
        phone_msg += "\u0336".join("⏱️ Працюємо цілодобово!")
        bot.send_message(msg.chat.id, phone_msg)

        # Очистити стан
        user_states.pop(msg.chat.id)


@bot.message_handler(content_types=["location"])
def handle_location(msg):
    chat_id = msg.chat.id
    state = user_states.get(chat_id)
    if not state or state.get("step") != "choose_input":
        return

    latitude, longitude = msg.location.latitude, msg.location.longitude
    geolocator = Nominatim(user_agent="lift-bot", timeout=10)

    try:
        location = geolocator.reverse((latitude, longitude), language="uk")
        if not location or "road" not in location.raw["address"]:
            raise ValueError("No road in address")

        road_raw = location.raw["address"]["road"]
        house_number = location.raw["address"].get("house_number", "").lower()
        road_cleaned = clean_street_name(road_raw)

        found_district = None
        matched_street = None
        for district, streets in address_data.items():
            for street_name, buildings in streets.items():
                if road_cleaned in street_name.lower():
                    matched_street = street_name
                    found_district = district
                    break
            if matched_street:
                break

        if not matched_street or not house_number:
            return bot.send_message(chat_id, "❌ Не вдалося визначити адресу або номер будинку.\nСпробуйте ввести адресу вручну.")

        state["district"] = found_district
        state["address"] = f"{matched_street}, {house_number}"
        state["step"] = "enter_entrance"

        bot.send_message(chat_id, f"📍 Адреса: <b>{state['address']}</b>\n🏙️ Район: <b>{state['district']}</b>", parse_mode="HTML")
        bot.send_message(chat_id, "Введіть номер під'їзду:", reply_markup=types.ReplyKeyboardRemove())

    except Exception as e:
        logger.warning(f"Geolocation error: {e}")
        bot.send_message(chat_id, "❌ Не вдалося визначити адресу за геолокацією.\nБудь ласка, введіть її вручну.")
        state["step"] = "choose_district"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for d in district_names:
            kb.add(d)
        bot.send_message(chat_id, "Оберіть район:", reply_markup=kb)

@bot.chat_member_handler()
def handle_new_member(msg):
    # Додано нового користувача в чат
    if msg.new_chat_member.status != "member":
        return

    chat_id = msg.chat.id
    user = msg.new_chat_member.user
    user_id = user.id

    # Знайдемо дільницю за chat_id
    section = None
    for sect, cid in personnel_chats.items():
        if cid == chat_id:
            section = sect
            break
    if not section:
        return

    # Якщо вже авторизований або адмін — не надсилаємо привітання
    if user_id in authorized_users.get(section, {}).get("authorized", []) \
       or user_id in authorized_users.get("ADMINS", []) \
       or user_id == bot.get_me().id:
        return

    # Надсилаємо кнопку авторизації
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔐 Авторизація", callback_data=f"auth:{section}"))
    bot.send_message(chat_id, f"👋 Вітаю, {user.first_name}!\nНатисніть кнопку для авторизації:", reply_markup=kb)

# Обработчик удаления участника из чата
@bot.message_handler(content_types=['left_chat_member'])
def handle_left_chat_member(msg):
    user = msg.left_chat_member
    user_id = user.id
    chat_id = msg.chat.id

    print(f"📥 Пользователь {user_id} ({user.first_name}) покинул чат {chat_id}")

    # Определяем район по чату
    section = None
    for sect, cid in personnel_chats.items():
        if cid == chat_id:
            section = sect
            break

    if not section:
        print(f"❌ Не удалось определить район для чата {chat_id}")
        return

    changed = False

    # Удаляем из authorized_users (структура со словарями)
    if section in authorized_users and isinstance(authorized_users[section], dict):
        authorized_list = authorized_users[section].get("authorized", [])
        if user_id in authorized_list:
            authorized_users[section]["authorized"].remove(user_id)
            print(f"✅ Удален пользователь {user_id} из authorized для {section}")
            changed = True

        # Удаляем из представителей района
        if authorized_users[section].get("representative") == user_id:
            authorized_users[section]["representative"] = None
            print(f"✅ Удален представитель {user_id} для {section}")
            changed = True

    if changed:
        save_authorized_users()

        # Добавляем запись в журнал
        log_action(user_id, "left_chat", {
            "section": section,
            "user_name": user.first_name,
            "chat_id": chat_id
        })

        print(f"🔁 Видалено user_id {user_id} із authorized_users для {section}")
    else:
        print(f"❌ Пользователь {user_id} не был найден в авторизованных для {section}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("auth:"))
def cb_auth(call):
    section = call.data.split(":")[1]
    user_id = call.from_user.id

    # Ініціалізуємо структуру, якщо її ще немає
    authorized_users.setdefault(section, {})
    authorized_users[section].setdefault("authorized", [])

    # Додаємо user_id, якщо ще не доданий
    if user_id not in authorized_users[section]["authorized"]:
        authorized_users[section]["authorized"].append(user_id)
        save_authorized_users()

    bot.answer_callback_query(call.id, "✅ Ви авторизовані.")
    bot.edit_message_text("✅ Ви авторизовані для цього району.", call.message.chat.id, call.message.message_id)

@bot.message_handler(commands=["призначити"])
def cmd_assign(msg):
    if msg.chat.id not in personnel_chats.values():
        return bot.reply_to(msg, "❌ Лише в чаті району.")

    if msg.from_user.id not in authorized_users.get("ADMINS", []):
        return bot.reply_to(msg, "⛔️ Тільки адміністратор може призначати.")

    # Визначаємо район
    section = None
    for sect, chat_id in personnel_chats.items():
        if chat_id == msg.chat.id:
            section = sect
            break
    if not section:
        return

    # Вибір з авторизованих
    members = authorized_users.get(section, {}).get("authorized", [])
    if not members:
        return bot.reply_to(msg, "❌ Немає авторизованих користувачів у цьому районі.")

    kb = types.InlineKeyboardMarkup(row_width=1)
    for uid in members:
        try:
            user = bot.get_chat_member(msg.chat.id, uid).user
            name = user.first_name or f"ID {uid}"
        except:
            name = f"ID {uid}"  # fallback якщо не вдається отримати ім’я
        btn = types.InlineKeyboardButton(
            f"👤 {name}",
            callback_data=f"assign_rep:{section}:{uid}"
        )
        kb.add(btn)
    bot.send_message(msg.chat.id, "Оберіть представника:", reply_markup=kb)

@bot.message_handler(commands=["скасувати"])
def cmd_unassign(msg):
    if msg.chat.id not in personnel_chats.values():
        return bot.reply_to(msg, "❌ Лише в чаті району.")

    if msg.from_user.id not in authorized_users.get("ADMINS", []):
        return bot.reply_to(msg, "⛔️ Тільки адміністратор може скасувати.")

    # Визначення району
    section = None
    for sect, chat_id in personnel_chats.items():
        if chat_id == msg.chat.id:
            section = sect
            break
    if not section:
        return

    rep = authorized_users.get(section, {}).get("representative")
    if not rep:
        return bot.reply_to(msg, "❌ Представник не призначений.")

    # Отримати ім’я представника через get_chat_member
    try:
        member = bot.get_chat_member(msg.chat.id, rep)
        name = member.user.first_name
    except Exception as e:
        name = f"{rep} (невідомо)"

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(f"🗑️ {name}", callback_data=f"unassign_rep:{section}:{rep}"))
    bot.send_message(msg.chat.id, "Скасувати представника:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("assign_rep:"))
def cb_assign_rep(call):
    _, section, user_id = call.data.split(":")
    user_id = int(user_id)

    authorized_users.setdefault(section, {})["representative"] = user_id
    save_authorized_users()
    bot.answer_callback_query(call.id, "✅ Призначено.")
    bot.edit_message_text("✅ Користувача призначено представником.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("unassign_rep:"))
def cb_unassign_rep(call):
    _, section, user_id = call.data.split(":")
    user_id = int(user_id)

    if authorized_users.get(section, {}).get("representative") == user_id:
        authorized_users[section]["representative"] = None
        save_authorized_users()
    bot.answer_callback_query(call.id, "✅ Скасовано.")
    bot.edit_message_text("🗑️ Представника скасовано.", call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda call: call.data == "start")
def handle_start_callback(call):
    bot.answer_callback_query(call.id)
    return cmd_start(call.message)

@bot.callback_query_handler(func=lambda c: True)
def cb(call):
    if call.data == "start":
        return cmd_start(call.message)

    if call.data.startswith("filter:"):
        bot.answer_callback_query(call.id)
        filter_type = call.data.split(":")[1]

        # Визначаємо район цього чату
        chat_id = call.message.chat.id
        section = None
        for sect, cid in personnel_chats.items():
            if cid == chat_id:
                section = sect
                break

        if not section:
            return bot.send_message(chat_id, "❌ Ця команда доступна лише в чатах дільниць.")

        # Фільтруємо заявки лише для цього району
        filtered = []
        for i, r in enumerate(requests_list):
            if district_ids[r["district"]] != section:
                continue
            if filter_type == "pending" and not r["completed"]:
                filtered.append((i, r))
            elif filter_type == "done" and r.get("status") == "done":
                filtered.append((i, r))
            elif filter_type == "error" and r.get("status") == "error":
                filtered.append((i, r))

        if not filtered:
            return bot.send_message(chat_id, "❌ Немає заявок для цього району за обраним фільтром.")

        status_names = {
            "pending": "🕐 Очікують",
            "done": "✅ Виконані",
            "error": "❌ Не працює"
        }
        msg_lines = [f"<b>{status_names.get(filter_type, 'Заявки')}:</b>"]

        for idx, r in filtered:
            url = f"https://t.me/c/{str(chat_id)[4:]}/{r['chat_msg_id']}"
            msg_lines.append(f"📍 <a href='{url}'>{r['address']} п.{r['entrance']}</a> — {r['issue']}")

        bot.send_message(chat_id, "\n".join(msg_lines), parse_mode="HTML", disable_web_page_preview=True)
        return

    if not call.data.startswith("status:"):
        return

    _, action, idx = call.data.split(":")
    idx = int(idx)
    if idx >= len(requests_list):
        return

    r = requests_list[idx]

    # 🔒 Перевірка дозволу на натискання кнопок
    section = district_ids.get(r["district"])
    if not chat_action_allowed.get(section, True):
        rep = authorized_users.get(section, {}).get("representative")
        allowed = (
            call.from_user.id in authorized_users.get("ADMINS", []) or
            call.from_user.id == rep
        )
        if not allowed:
            return bot.answer_callback_query(call.id, "⛔️ Дію заборонено.")

    # ✅ Виконано
    if action == "done":
        r.update(
            completed=True,
            completed_time=datetime.now(kyiv_tz).strftime("%Y-%m-%d %H:%M:%S"),
            processed_by=call.from_user.first_name,
            status="done"
        )
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except:
            pass
        try:
            bot.send_message(r["user_id"], "✅ Ваша заявка виконана.")
        except:
            pass

    # 🚫 Не працює
    elif action == "not_working":
        r.update(
            completed=False,
            processed_by=call.from_user.first_name,
            status="error"
        )
        # Видаляємо лише кнопку 🚫
        try:
            new_kb = types.InlineKeyboardMarkup()
            new_kb.add(
                types.InlineKeyboardButton("✅ Виконано", callback_data=f"status:done:{idx}")
            )
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=new_kb)
        except:
            pass
        try:
            phones = "\n".join(f"📞 {n}" for n in district_phones[r['district']])
            bot.send_message(r["user_id"], f"⚠️ Заявку відпрацьовано, але ліфт не працює.\n{phones}")
        except:
            pass

    # Зберігаємо оновлення
    save_requests_to_db()
    bot.answer_callback_query(call.id)

         # ========== Flask ==========
@app.route("/get_action_rights")
def get_action_rights():
    return jsonify(chat_action_allowed)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        action = request.form.get("action", "login")
        
        if action == "login":
            email = request.form.get("email")
            password = request.form.get("password")
            remember = request.form.get("remember")
            
            # Simple authentication for demo - in production use proper password hashing
            # Check if user exists in our user database
            try:
                with open("users.json", "r", encoding="utf-8") as f:
                    users_db = json.load(f)
            except FileNotFoundError:
                users_db = {}
            
            user = users_db.get(email)
            if not user or user.get("password") != password:
                return render_template("login.html", error="Невірний email або пароль")
            
            if not user.get("profile_completed", False):
                session["temp_user_email"] = email
                return redirect(url_for("profile_setup"))
            
            # Successful login
            session["user_email"] = email
            session["user_name"] = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            session["user_role"] = user.get("role", "operator")
            session["phone"] = user.get("phone", "")
            session["role"] = user.get("role", "operator")
            if user.get("avatar"):
                session["user_avatar"] = user.get("avatar")
            
            if remember:
                session.permanent = True
            
            return redirect(url_for("index"))
    
    return render_template("login.html")

@app.route("/register", methods=["POST"])
def register():
    email = request.form.get("email")
    phone = request.form.get("phone")
    password = request.form.get("password")
    confirm_password = request.form.get("confirm_password")
    agree_terms = request.form.get("agree_terms")
    
    if password != confirm_password:
        return render_template("login.html", error="Паролі не співпадають")
    
    if not agree_terms:
        return render_template("login.html", error="Необхідно погодитися з умовами використання")
    
    # Load existing users
    try:
        with open("users.json", "r", encoding="utf-8") as f:
            users_db = json.load(f)
    except FileNotFoundError:
        users_db = {}
    
    # Check if user already exists
    if email in users_db:
        return render_template("login.html", error="Користувач з таким email вже існує")
    
    # Create new user
    users_db[email] = {
        "email": email,
        "phone": phone,
        "password": password,  # In production, hash this!
        "created_at": datetime.now().isoformat(),
        "profile_completed": False
    }
    
    # Save users database
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(users_db, f, ensure_ascii=False, indent=2)
    
    # Set session for profile setup
    session["temp_user_email"] = email
    return redirect(url_for("profile_setup"))

@app.route("/profile_setup", methods=["GET", "POST"])
def profile_setup():
    if "temp_user_email" not in session:
        return redirect(url_for("login"))
    
    if request.method == "POST":
        email = session["temp_user_email"]
        
        # Load users database
        try:
            with open("users.json", "r", encoding="utf-8") as f:
                users_db = json.load(f)
        except FileNotFoundError:
            return redirect(url_for("login"))
        
        if email not in users_db:
            return redirect(url_for("login"))
        
        # Update user profile
        users_db[email].update({
            "first_name": request.form.get("first_name"),
            "last_name": request.form.get("last_name"),
            "department": request.form.get("department"),
            "role": request.form.get("role"),
            "bio": request.form.get("bio"),
            "email_notifications": bool(request.form.get("email_notifications")),
            "push_notifications": bool(request.form.get("push_notifications")),
            "new_request_notifications": bool(request.form.get("new_request_notifications")),
            "completed_request_notifications": bool(request.form.get("completed_request_notifications")),
            "profile_completed": True,
            "profile_completed_at": datetime.now().isoformat()
        })
        
        # Handle avatar upload (basic implementation)
        avatar = request.files.get("avatar")
        if avatar and avatar.filename:
            # In production, save to proper storage
            users_db[email]["avatar"] = f"avatar_{email.replace('@', '_').replace('.', '_')}.jpg"
        
        # Save updated users database
        with open("users.json", "w", encoding="utf-8") as f:
            json.dump(users_db, f, ensure_ascii=False, indent=2)
        
        # Complete registration and log in
        session.pop("temp_user_email", None)
        session["user_email"] = email
        session["user_name"] = f"{users_db[email]['first_name']} {users_db[email]['last_name']}"
        session["user_role"] = users_db[email]["role"]
        session["phone"] = users_db[email]["phone"]
        session["role"] = users_db[email]["role"]
        
        return redirect(url_for("index"))
    
    return render_template("profile_setup.html")

@app.route("/complete_profile", methods=["POST"])
def complete_profile():
    return profile_setup()  # Redirect to the same handler

@app.route("/")
def index():
    # Check if user is properly authenticated
    if "user_email" not in session:
        # Clear any old session data and redirect to login
        session.clear()
        return redirect(url_for("login"))
    
    # Check if user has selected a company
    if "selected_company" not in session:
        return redirect(url_for("select_company"))
    
    # Set default avatar if not exists
    if "user_avatar" not in session:
        session["user_avatar"] = f"https://via.placeholder.com/30x30/6c757d/ffffff?text={session.get('user_name', 'U')[0]}"
        
    return render_template("index.html")

@app.route("/select-company", methods=["GET", "POST"])
def select_company():
    if "user_email" not in session:
        return redirect(url_for("login"))
    
    # Load company settings to get current names
    try:
        with open("company_settings.json", "r", encoding="utf-8") as f:
            companies = json.load(f)
    except FileNotFoundError:
        companies = {
            "1": {
                "name": "ТОВ 'Ліфт Сервіс'",
                "vat_status": False,
                "services": "ОСББ та УК без ПДВ"
            },
            "2": {
                "name": "ТОВ 'Ліфт Сервіс Плюс'",
                "vat_status": True,
                "services": "ЖЕКи та УК з ПДВ"
            }
        }
    
    if request.method == "POST":
        company_id = request.form.get("company_id")
        if company_id in ["1", "2"]:
            company_data = companies.get(company_id, {})
            session["selected_company"] = company_id
            session["company_name"] = company_data.get("name", "")
            session["company_vat_status"] = company_data.get("vat_status", False)
            session["company_services"] = company_data.get("services", "")
            return redirect(url_for("index"))
    
    return render_template("select_company.html", companies=companies)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/analytics")
def analytics():
    # Temporary bypass for development
    if "phone" not in session:
        session["phone"] = "dev"
        session["role"] = "admin"
    return render_template("analytics.html")

@app.route("/account", methods=["GET", "POST"])
def account():
    if "user_email" not in session:
        return redirect(url_for("login"))
    
    user_email = session["user_email"]
    
    # Load user data from users database
    try:
        with open("users.json", "r", encoding="utf-8") as f:
            users_db = json.load(f)
    except FileNotFoundError:
        users_db = {}
    
    if request.method == "POST":
        print(f"POST request received for user: {user_email}")
        print(f"Form data: {dict(request.form)}")
        print(f"Files: {dict(request.files)}")
        
        # Update user profile
        if user_email in users_db:
            users_db[user_email].update({
                "first_name": request.form.get("first_name"),
                "last_name": request.form.get("last_name"),
                "phone": request.form.get("phone"),
                "department": request.form.get("department"),
                "bio": request.form.get("bio"),
                "updated_at": datetime.now().isoformat()
            })
            
            # Handle avatar upload
            avatar = request.files.get("avatar")
            print(f"Avatar file: {avatar}")
            if avatar and avatar.filename:
                print(f"Avatar filename: {avatar.filename}")
                import os
                # Create static/uploads directory if it doesn't exist
                upload_dir = os.path.join('static', 'uploads')
                os.makedirs(upload_dir, exist_ok=True)
                print(f"Upload directory created: {upload_dir}")
                
                # Save the file
                avatar_filename = f"avatar_{user_email.replace('@', '_').replace('.', '_')}.jpg"
                avatar_path = os.path.join(upload_dir, avatar_filename)
                print(f"Saving avatar to: {avatar_path}")
                avatar.save(avatar_path)
                
                # Store relative path in database
                users_db[user_email]["avatar"] = f"uploads/{avatar_filename}"
                print(f"Avatar path stored in DB: uploads/{avatar_filename}")
            
            # Save updated users database
            with open("users.json", "w", encoding="utf-8") as f:
                json.dump(users_db, f, ensure_ascii=False, indent=2)
            
            # Update session with new data
            session["user_name"] = f"{users_db[user_email]['first_name']} {users_db[user_email]['last_name']}"
            if users_db[user_email].get("avatar"):
                session["user_avatar"] = users_db[user_email]["avatar"]
            
            return render_template("account.html", user=users_db[user_email], success="Профіль успішно оновлено!")
    
    user_data = users_db.get(user_email, {})
    return render_template("account.html", user=user_data)

@app.route("/users")
def users():
    # Check authentication and admin role
    if "user_email" not in session:
        return redirect(url_for("login"))
    
    # Load users database
    try:
        with open("users.json", "r", encoding="utf-8") as f:
            users_db = json.load(f)
    except FileNotFoundError:
        users_db = {}
    
    # Calculate statistics
    total_users = len(users_db)
    active_users = sum(1 for user in users_db.values() if user.get('profile_completed', False))
    admin_users = sum(1 for user in users_db.values() if user.get('role') == 'admin')
    
    # Calculate new users this week
    from datetime import timedelta
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    new_users_week = sum(1 for user in users_db.values() 
                        if user.get('created_at', '') > week_ago)
    
    return render_template("users.html", 
                         users=users_db,
                         active_users=active_users,
                         admin_users=admin_users,
                         new_users_week=new_users_week)

@app.route("/users/<email>/toggle-status", methods=["POST"])
def toggle_user_status(email):
    if "user_email" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    try:
        with open("users.json", "r", encoding="utf-8") as f:
            users_db = json.load(f)
    except FileNotFoundError:
        return jsonify({"success": False, "error": "Users database not found"}), 404
    
    if email not in users_db:
        return jsonify({"success": False, "error": "User not found"}), 404
    
    data = request.get_json()
    activate = data.get("activate", True)
    
    users_db[email]["profile_completed"] = activate
    users_db[email]["updated_at"] = datetime.now().isoformat()
    
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(users_db, f, ensure_ascii=False, indent=2)
    
    return jsonify({"success": True})

@app.route("/users/<email>/delete", methods=["DELETE"])
def delete_user(email):
    if "user_email" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    current_email = session["user_email"]
    try:
        with open("users.json", "r", encoding="utf-8") as f:
            users_db = json.load(f)
    except FileNotFoundError:
        return jsonify({"success": False, "error": "Users database not found"}), 404
    
    if users_db.get(current_email, {}).get("role") != "admin":
        return jsonify({"success": False, "error": "Admin access required"}), 403
    
    if email not in users_db:
        return jsonify({"success": False, "error": "User not found"}), 404
    
    if email == current_email:
        return jsonify({"success": False, "error": "Cannot delete your own account"}), 400
    
    del users_db[email]
    
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(users_db, f, ensure_ascii=False, indent=2)
    
    return jsonify({"success": True})

@app.route("/customers")
def customers():
    if "user_email" not in session:
        return redirect(url_for("login"))
    
    # Load customers from requests data
    customers_data = {}
    for req in requests_list:
        phone = req.get("phone")
        if phone and phone not in customers_data:
            customers_data[phone] = {
                "name": req.get("name", "Невідомо"),
                "phone": phone,
                "addresses": [],
                "requests_count": 0,
                "last_request": req.get("timestamp", "")
            }
        
        if phone in customers_data:
            address = req.get("address", "")
            if address and address not in customers_data[phone]["addresses"]:
                customers_data[phone]["addresses"].append(address)
            customers_data[phone]["requests_count"] += 1
            
            # Update last request if newer
            if req.get("timestamp", "") > customers_data[phone]["last_request"]:
                customers_data[phone]["last_request"] = req.get("timestamp", "")
    
    return render_template("customers.html", customers=customers_data)

@app.route("/settings/company", methods=["GET", "POST"])
def settings_company():
    if "user_email" not in session:
        return redirect(url_for("login"))
    
    if "selected_company" not in session:
        return redirect(url_for("select_company"))
    
    company_id = session["selected_company"]
    
    # Load company settings
    try:
        with open("company_settings.json", "r", encoding="utf-8") as f:
            companies = json.load(f)
    except FileNotFoundError:
        companies = {
            "1": {
                "name": "ТОВ 'Ліфт Сервіс'",
                "vat_status": False,
                "services": "ОСББ та УК без ПДВ",
                "address": "м. Миколаїв, вул. Адміральська, 15",
                "phone": "+380512123456",
                "email": "info@liftsevice.com.ua",
                "tax_number": "12345678",
                "bank_account": "UA123456789012345678901234567",
                "bank_name": "ПриватБанк",
                "mfo": "305299",
                "director": "Іваненко Олександр Володимирович",
                "accountant": "Петренко Наталія Іванівна"
            },
            "2": {
                "name": "ТОВ 'Ліфт Сервіс Плюс'",
                "vat_status": True,
                "services": "ЖЕКи та УК з ПДВ",
                "address": "м. Миколаїв, вул. Соборна, 28",
                "phone": "+380512654321",
                "email": "info@liftserviceplus.com.ua",
                "tax_number": "87654321",
                "vat_number": "876543210",
                "bank_account": "UA987654321098765432109876543",
                "bank_name": "ПриватБанк",
                "mfo": "305299",
                "director": "Сидоренко Михайло Петрович",
                "accountant": "Коваленко Олена Сергіївна"
            }
        }
    
    if request.method == "POST":
        # Update company settings
        company_data = companies.get(company_id, {})
        company_data.update({
            "name": request.form.get("company_name"),
            "address": request.form.get("address"),
            "phone": request.form.get("phone"),
            "email": request.form.get("email"),
            "tax_number": request.form.get("tax_number"),
            "bank_account": request.form.get("bank_account"),
            "bank_name": request.form.get("bank_name"),
            "mfo": request.form.get("mfo"),
            "director": request.form.get("director"),
            "accountant": request.form.get("accountant")
        })
        
        if company_data.get("vat_status"):
            company_data["vat_number"] = request.form.get("vat_number")
        
        companies[company_id] = company_data
        
        # Save to file
        with open("company_settings.json", "w", encoding="utf-8") as f:
            json.dump(companies, f, ensure_ascii=False, indent=2)
        
        # Update session
        session["company_name"] = company_data["name"]
        
        return redirect(url_for("settings_company"))
    
    current_company = companies.get(company_id, {})
    return render_template("settings/company_multi.html", company=current_company)

@app.route("/settings/localization")
def settings_localization():
    if "user_email" not in session:
        return redirect(url_for("login"))
    return render_template("settings/localization.html")

@app.route("/settings/theme")
def settings_theme():
    if "user_email" not in session:
        return redirect(url_for("login"))
    return render_template("settings/theme.html")

@app.route("/settings/logo")
def settings_logo():
    if "user_email" not in session:
        return redirect(url_for("login"))
    return render_template("settings/logo.html")

@app.route("/documents/invoice")
def documents_invoice():
    if "user_email" not in session:
        return redirect(url_for("login"))
    return render_template("documents/invoice.html")

@app.route("/documents/work-report")
def documents_work_report():
    if "user_email" not in session:
        return redirect(url_for("login"))
    return render_template("documents/work-report.html")

#contract route#


@app.route("/registries/work-reports")
def registries_work_reports():
    if "user_email" not in session:
        return redirect(url_for("login"))
    return render_template("registries/work-reports.html")

@app.route("/analytics/data")
def analytics_data():
    if "phone" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Статистика по статусам
    status_stats = {"pending": 0, "done": 0, "error": 0}
    district_stats = {}
    daily_stats = {}
    hourly_stats = {}
    
    from datetime import datetime, timedelta
    import pytz
    kyiv_tz = pytz.timezone('Europe/Kiev')
    
    for req in requests_list:
        # Статистика по статусам
        status = req.get("status", "pending")
        if status in status_stats:
            status_stats[status] += 1
        
        # Статистика по районам
        district = req.get("district", "Невідомо")
        district_stats[district] = district_stats.get(district, 0) + 1
        
        # Статистика по дням (последние 7 дней)
        try:
            req_date = datetime.strptime(req["timestamp"], "%Y-%m-%d %H:%M:%S")
            date_key = req_date.strftime("%Y-%m-%d")
            daily_stats[date_key] = daily_stats.get(date_key, 0) + 1
            
            # Статистика по часам
            hour_key = req_date.hour
            hourly_stats[hour_key] = hourly_stats.get(hour_key, 0) + 1
        except:
            pass
    
    # Генерируем данные для последних 7 дней
    today = datetime.now(kyiv_tz).date()
    last_7_days = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        last_7_days.append({
            "date": date.strftime("%d.%m"),
            "count": daily_stats.get(date_str, 0)
        })
    
    # Генерируем данные по часам (0-23)
    hourly_data = []
    for hour in range(24):
        hourly_data.append({
            "hour": f"{hour:02d}:00",
            "count": hourly_stats.get(hour, 0)
        })
    
    return jsonify({
        "status_stats": status_stats,
        "district_stats": district_stats,
        "daily_stats": last_7_days,
        "hourly_stats": hourly_data,
        "total_requests": len(requests_list)
    })

@app.route("/requests_data")
def data():
    return jsonify({"requests": requests_list})


@app.route("/export")
def export_from_db():
    import openpyxl
    from openpyxl import Workbook
    from io import BytesIO
    import sqlite3

    # Підключення до БД
    conn = sqlite3.connect("requests.db")
    c = conn.cursor()
    c.execute("SELECT * FROM requests")
    rows = c.fetchall()
    headers = [desc[0] for desc in c.description]
    conn.close()

    # Створення Excel-файлу
    wb = Workbook()
    ws = wb.active
    ws.append(headers)  # заголовки
    for row in rows:
        ws.append(row)

    # Зберегти у пам’ять (а не файл)
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    # Надіслати як файл
    return send_file(
        output,
        download_name="requests_export.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route("/complete_request/<int:idx>", methods=["POST"])
def complete_request(idx):
    if 0 <= idx < len(requests_list):
        r = requests_list[idx]
        r.update(
            completed=True,
            completed_time=datetime.now(kyiv_tz).strftime("%Y-%m-%d %H:%M:%S"),
            processed_by="Оператор з веб"
        )
        save_requests_to_db()

        try:
            bot.edit_message_reply_markup(
                chat_id=personnel_chats[district_ids[r["district"]]],
                message_id=int(r["chat_msg_id"]),
                reply_markup=None
            )
        except: pass

        try:
            bot.send_message(r["user_id"], "✅ Ваша заявка виконана.")
        except: pass
        return jsonify({"success": True})
    return jsonify({"success": False})


@app.route("/not_working_request/<int:idx>", methods=["POST"])
def not_working_request(idx):
    if 0 <= idx < len(requests_list):
        r = requests_list[idx]
        r.update(
            completed=True,
            completed_time=datetime.now(kyiv_tz).strftime("%Y-%m-%d %H:%M:%S"),
            processed_by="Оператор з веб"
        )
        save_requests_to_db()

        try:
            from telebot import types  # убедитесь, что импорт есть наверху

            new_kb = types.InlineKeyboardMarkup()
            new_kb.add(types.InlineKeyboardButton("✅ Виконано", callback_data=f"status:done:{idx}"))
            bot.edit_message_reply_markup(
                chat_id=personnel_chats[district_ids[r["district"]]],
                message_id=int(r["chat_msg_id"]),
                reply_markup=new_kb
            )

        except: pass

        try:
            phones = "\n".join(f"📞 {n}" for n in district_phones[r["district"]])
            bot.send_message(r["user_id"],
                             "⚠️ Заявку відпрацьовано, але ліфт не працює.\n" + phones)
        except: pass
        return jsonify({"success": True})
    return jsonify({"success": False})


@app.route("/delete_request/<int:idx>", methods=["POST"])
def delete_request(idx):
    if 0 <= idx < len(requests_list):
        try:
            del requests_list[idx]
            save_requests_to_db()
            return jsonify({"success": True})
        except:
            return jsonify({"success": False})
    return jsonify({"success": False})

@app.route("/requests_data")
def requests_data():
    """API endpoint for fetching requests data for the dashboard"""
    try:
        # Ensure we have the latest data from database
        load_requests_from_db()
        
        # Format requests for frontend from the same list the bot uses
        formatted_requests = []
        for i, req in enumerate(requests_list):
            formatted_req = {
                "id": i + 1,
                "timestamp": req.get("timestamp", ""),
                "name": req.get("name", ""),
                "phone": req.get("phone", ""),
                "address": req.get("address", ""),
                "entrance": req.get("entrance", ""),
                "district": req.get("district", ""),
                "issue": req.get("issue", ""),
                "status": req.get("status", "pending"),
                "completed": req.get("completed", False),
                "processed_by": req.get("processed_by", ""),
                "completed_time": req.get("completed_time", ""),
                "user_id": req.get("user_id", "")
            }
            formatted_requests.append(formatted_req)
        
        return jsonify({"requests": formatted_requests})
    except Exception as e:
        print(f"Error in requests_data: {e}")
        return jsonify({"error": "Failed to load requests", "requests": []})


# Состояние включения кнопок (по умолчанию — True)
chat_action_allowed = {"участок№1": True, "участок№2": True}
@app.route("/get_chat_rights")
def get_chat_rights():
    return jsonify(chat_action_allowed)

@app.route("/toggle_actions", methods=["POST"])
def toggle_chat_actions():
    data = json.loads(request.data)
    section = data.get("section")
    enabled = data.get("enabled")
    if section in chat_action_allowed:
        chat_action_allowed[section] = enabled
        save_action_rights()
        return jsonify({"success": True})
    return jsonify({"success": False})


@app.route("/update_status/<int:idx>/<action>", methods=["POST"])
def update_status(idx, action):
    if 0 <= idx < len(requests_list):
        r = requests_list[idx]
        r.update(
            completed=True,
            completed_time=datetime.now(kyiv_tz).strftime("%Y-%m-%d %H:%M:%S"),
            processed_by="Оператор з веб"
        )
        if action == "done":
            r["status"] = "done"
        elif action == "not_working":
            r["status"] = "error"
        save_requests_to_db()
        try:
            if action == "not_working":
                # залишити тільки кнопку "✅ Виконано"
                new_kb = types.InlineKeyboardMarkup()
                new_kb.add(
                    types.InlineKeyboardButton("✅ Виконано", callback_data=f"status:done:{idx}")
                )
                bot.edit_message_reply_markup(
                    chat_id=personnel_chats[district_ids[r["district"]]],
                    message_id=int(r["chat_msg_id"]),
                    reply_markup=new_kb
                )
            else:
                # якщо "✅ Виконано" — видаляємо всі кнопки
                bot.edit_message_reply_markup(
                    chat_id=personnel_chats[district_ids[r["district"]]],
                    message_id=int(r["chat_msg_id"]),
                    reply_markup=None
                )
        except Exception as e:
            print(f"⚠️ Не вдалося оновити кнопки: {e}")

        try:
            if action == "done":
                bot.send_message(r["user_id"], "✅ Ваша заявка виконана.")
            elif action == "not_working":
                phones = "\n".join(f"📞 {n}" for n in district_phones[r["district"]])
                bot.send_message(r["user_id"], f"⚠️ Заявку відпрацьовано, але ліфт не працює.\n{phones}")
        except: pass

        return jsonify({"success": True})

    return jsonify({"success": False})

# ========== щоденний звіт ==========
def send_daily():
    summary = {}
    for i, r in enumerate(requests_list):
        if r["completed"]:
            continue
        chat = personnel_chats[district_ids[r["district"]]]
        summary.setdefault(chat, [])
        url = f"https://t.me/c/{str(chat)[4:]}/{r['chat_msg_id']}"
        summary[chat].append(f"#{i + 1} <a href='{url}'>{r['address']} п.{r['entrance']}</a>")
    for chat, lines in summary.items():
        bot.send_message(chat, "📋 <b>Невиконані заявки:</b>\n" + " \n".join(lines))


def sched_loop():
    schedule.every().day.at("08:30").do(send_daily)
    while True:
        schedule.run_pending()
        time.sleep(60)


# ========== run ==========
if __name__ == "__main__":
    app.secret_key = "дуже_секретний_рядок_тут"

    # Инициализация базы данных
    init_database()
    load_requests_from_db()
    threading.Thread(target=sched_loop, daemon=True).start()
    def start_bot():
        bot.polling(none_stop=True, allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"])

    # Запускаємо бота у потоці
    threading.Thread(target=start_bot, daemon=True).start()

    load_action_rights()
    app.run(host="0.0.0.0", port=5000)
