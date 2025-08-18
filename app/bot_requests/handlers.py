import json, os, tempfile
import logging
from datetime import datetime, timedelta
from pytz import timezone
from pathlib import Path
from geopy.geocoders import Nominatim
import telebot
import unicodedata
from telebot import types
from app.bot_requests.shared import user_states, address_data, chat_action_allowed

from app.bot_requests.shared import (
    requests_list,
    save_requests_to_db,
    match_address,
    clean_street_name,
    district_names,
    district_ids,
    district_phones,
    personnel_chats,
    authorized_users,
    save_authorized_users,
    log_action,
    bot,
    send_push,
)

logger = logging.getLogger(__name__)

kyiv_tz = timezone("Europe/Kyiv")

# и если нужно, user_states объяви в shared и импортируй сюда
#from app.bot_requests.shared import user_states, address_data
#from app.bot_requests.shared import chat_action_allowed
ADDRESSES_FILE = "addresses.json"


@bot.message_handler(commands=["start"])
def cmd_start(msg):
    if msg.chat.type != "private":
        return
    user_states[msg.chat.id] = {"step": "name", "user_id": msg.chat.id}
    bot.send_message(msg.chat.id, "👋 <b>Вітаю!</b>\nЯ бот для прийома заявок з ремонту ліфтів.\n\nВведіть ваше ім’я будь ласка:")

@bot.message_handler(commands=["requests"])
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
        street, b_raw = " ".join(parts[:-1]), parts[-1]
        b = b_raw.upper()  # нормализация буквы в доме
        found = match_address(street, b, st["district"])
        if not found:
            return bot.send_message(msg.chat.id, "❌ Адреса не знайдена, спробуйте ще.")

        houses = address_data.get(st["district"], {}).get(found, {})
        entrances = houses.get(b, {}) 
        if not entrances:
            return bot.send_message(msg.chat.id, "❌ Такого будинку немає в базі.")

        if all(not v.get("active", True) for v in entrances.values()):
            return bot.send_message(msg.chat.id, "⛔️ Цей адрес не обслуговується компанією Елестек.")
    
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
        try:
            street_name, house_num = st["address"].split(", ")
            entrances = address_data.get(st["district"], {}).get(street_name, {}).get(house_num, {})	

            if st["entrance"] not in entrances:
                return bot.send_message(msg.chat.id, "❌ Такого під'їзду немає в базі.")

            if not entrances[st["entrance"]].get("active", True):
                return bot.send_message(msg.chat.id, "⛔️ Цей під'їзд не обслуговується компанією Елестек.")
        except Exception as e:
            print("⛔️ Помилка перевірки під'їзду:", e)
            return bot.send_message(msg.chat.id, "❌ Помилка перевірки адреси, спробуйте ще.")

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
        house_number_raw = location.raw["address"].get("house_number", "")
        house_number = house_number_raw.upper()  # нормализация буквы дома
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
        
        entrances = address_data.get(found_district, {}).get(matched_street, {}).get(house_number, {})
        if not entrances:
            return bot.send_message(chat_id, "❌ Цей будинок відсутній у базі.")
        if all(not v.get("active", True) for v in entrances.values()):
            return bot.send_message(chat_id, "⛔️ Цей адрес не обслуговується компанією Елестек.")

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

@bot.message_handler(commands=["assign"])
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

@bot.message_handler(commands=["unassign"])
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

@bot.message_handler(commands=["help"])
def cmd_help(msg):
    commands_list = [
        "/start – почати роботу з ботом",
        "/requests – перегляд заявок (🕐 очікують, ✅ виконані, ❌ не працює)",
        "/assign – призначити представника району (адмін)",
        "/unassign – скасувати представника району (адмін)",
        "/disable – вимкнути будинок або під'їзд",
        "/enable – увімкнути будинок або під'їзд",
    ]
    bot.send_message(msg.chat.id, "📋 <b>Список команд:</b>\n\n" + "\n".join(commands_list), parse_mode="HTML")


# ADDRESSES_FILE і address_data у тебе вже є (імпорт із shared)
# from app.bot_requests.shared import address_data, ADDRESSES_FILE, clean_street_name, personnel_chats, user_states, bot
# ↑ переконайся, що clean_street_name імпортовано

def _save_atomic(data, path):
    """Безпечний запис JSON: спочатку у tmp-файл, потім атомарна заміна."""
    dirpath = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".addresses.", dir=dirpath)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)  # атомарна заміна
    except Exception:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise

def refresh_addresses():
    """Підтягнути актуальні адреси з файлу в address_data без створення нового об'єкта."""
    try:
        with open(ADDRESSES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        address_data.clear()
        address_data.update(data)
    except FileNotFoundError:
        logger.warning("ADDRESSES_FILE not found, using in-memory address_data")
    except Exception as e:
        logger.exception(f"Failed to refresh addresses: {e}")

def save_addresses():
    """Зберегти оновлені адреси без втрати структури."""
    _save_atomic(address_data, ADDRESSES_FILE)

@bot.message_handler(commands=["disable", "enable"])
def cmd_disable_enable(msg):
    # ✅ лише в районних групових чатах
    if msg.chat.type == "private":
        return bot.reply_to(msg, "⛔️ Ця команда доступна лише у чаті району.")
    if msg.chat.id not in personnel_chats.values():
        return bot.reply_to(msg, "⛔️ Це не чат району.")

    step = "enable" if msg.text.startswith("/enable") else "disable"
    user_states[msg.chat.id] = {"step": step}
    bot.send_message(
        msg.chat.id,
        "✏️ Введіть адресу (наприклад: Лазурна 32 або Лазурна 32 п.1):"
    )

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step") in ("disable", "enable"))
def handle_disable_enable(msg):
    step = user_states[msg.chat.id]["step"]
    enable = (step == "enable")

    text = msg.text.strip()
    parts = text.split()
    if len(parts) < 2:
        return bot.send_message(msg.chat.id, "❌ Формат: Вулиця + Номер (і за бажанням п.Х)")

    # Розбір "вулиця будинок [п.X]"
    entrance = None
    if parts[-1].lower().startswith("п."):
        entrance = parts[-1][2:]
        house = parts[-2]
        street_q = " ".join(parts[:-2])
    else:
        house = parts[-1]
        street_q = " ".join(parts[:-1])

    # Нормалізація для пошуку
    try:
        street_q_norm = clean_street_name(street_q)
    except Exception:
        street_q_norm = street_q.lower()

    # Підтягнемо актуальні дані з диска (щоб не перетерти чужі паралельні зміни)
    refresh_addresses()

    found = False
    for district, streets in address_data.items():
        for street_name, houses in streets.items():
            # м'яке порівняння по нормалізованій назві
            try:
                name_norm = clean_street_name(street_name)
            except Exception:
                name_norm = street_name.lower()

            if street_q_norm in name_norm:
                if house in houses:
                    if entrance:  # конкретний під'їзд
                        if entrance in houses[house]:
                            # змінюємо лише прапорець active
                            houses[house][entrance]["active"] = enable
                            bot.send_message(
                                msg.chat.id,
                                f"✅ {street_name} {house} п.{entrance} {'увімкнено' if enable else 'вимкнено'}"
                            )
                            found = True
                        else:
                            return bot.send_message(msg.chat.id, "❌ Такого під'їзду немає.")
                    else:  # увесь будинок
                        for ent_key, ent_val in houses[house].items():
                            # ent_val — це словник під'їзду; чіпаємо тільки active
                            if isinstance(ent_val, dict):
                                ent_val["active"] = enable
                        bot.send_message(
                            msg.chat.id,
                            f"✅ Усі під'їзди {street_name} {house} {'увімкнено' if enable else 'вимкнено'}"
                        )
                        found = True
    if not found:
        return bot.send_message(msg.chat.id, "❌ Такої адреси не знайдено.")

    try:
        save_addresses()
    except Exception as e:
        logger.exception("save_addresses failed")
        return bot.send_message(msg.chat.id, f"⛔️ Помилка збереження: {e}")

    # очищаємо state тільки після успішного сейву
    user_states.pop(msg.chat.id, None)
