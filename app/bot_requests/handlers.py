# app/bot_requests/handlers.py
# registration of message and callback handlers for requests bot
from telebot import types
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim
import traceback

from app.bot_requests.shared import (
    user_states, district_names, district_ids, district_phones,
    personnel_chats, address_data, map_ru_to_ua, kyiv_tz,
    authorized_users, save_authorized_users, chat_action_allowed
)
from app.requests.services import requests_list, save_requests_to_db
from app.shared_bot import bot_instance as bot
from app.utils import timestamp_now

# Helper functions
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
    houses = address_data.get(district, {})
    for full, buildings in houses.items():
        if ua_name.lower() in full.lower() and building.lower() in [h.lower() for h in buildings]:
            return full
    return None

# Handlers (copied & adapted from monolith)
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
    try:
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
            if not msg.text.isdigit() or len(msg.text) > 2:
                return bot.send_message(msg.chat.id, "❌ Введіть лише цифри (не більше 2):")

            st["entrance"] = msg.text

            # Check for blocked address due to recent error
            for req in requests_list:
                if (
                    req.get("address") == st["address"] and
                    req.get("entrance") == st["entrance"] and
                    req.get("status") == "error"
                ):
                    try:
                        created_time = kyiv_tz.localize(datetime.strptime(req["timestamp"], "%Y-%m-%d %H:%M:%S"))
                    except Exception as e:
                        continue

                    now = datetime.now(kyiv_tz)
                    weekday = created_time.weekday()
                    deadline = created_time + timedelta(hours=24)

                    if weekday in (4,5,6):  # Fri/Sat/Sun
                        monday = created_time + timedelta(days=(7-weekday))
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
            st.update(completed=False, completed_time="", processed_by="", status="pending")
            idx = len(requests_list)
            requests_list.append(st.copy())

            client_msg = (
                "✅ <b>Заявку прийнято!</b>\n\n"
                "📋 <b>Дані заявки:</b>\n"
                f"👤 Ім'я: <b>{st['name']}</b>\n"
                f"📍 Адреса: <b>{st['address']} п.{st['entrance']}</b>\n"
                f"🏙️ Район: <b>{st['district']}</b>\n"
                f"🔧 Проблема: {st['issue']}\n"
                f"📱 Телефон: {st['phone']}"
            )

            kb = types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("📨 Створити нову заявку", callback_data="start"))
            bot.send_message(msg.chat.id, client_msg, reply_markup=kb)

            group = personnel_chats.get(district_ids.get(st["district"]))
            group_kb = types.InlineKeyboardMarkup()
            group_kb.add(
                types.InlineKeyboardButton("✅ Виконано", callback_data=f"status:done:{idx}"),
                types.InlineKeyboardButton("🚫 Не працює", callback_data=f"status:not_working:{idx}")
            )
            try:
                sent = bot.send_message(group, client_msg, reply_markup=group_kb)
                requests_list[idx]["chat_msg_id"] = sent.message_id
            except Exception:
                requests_list[idx]["chat_msg_id"] = ""
            requests_list[idx]["user_id"] = msg.chat.id

            save_requests_to_db()

            try:
                # web push - use shared subscriptions if configured
                from app.bot_requests.shared import subscriptions, VAPID_CLAIMS, VAPID_PRIVATE_KEY
                # simplified: send_push implemented elsewhere if needed
            except Exception:
                pass

            phone_msg = "🔴🚨 <b>АВАРІЙНА СЛУЖБА</b> 🚨🔴\n\n"
            for n in district_phones.get(st["district"], []):
                phone_msg += f"📞 <a href='tel:{n}'>{n}</a>\n"
            phone_msg += "\u0336".join("⏱️ Працюємо цілодобово!")
            bot.send_message(msg.chat.id, phone_msg)

            user_states.pop(msg.chat.id, None)
    except Exception:
        print("handle_text error:", traceback.format_exc())

@bot.message_handler(content_types=["location"])
def handle_location(msg):
    try:
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
            bot.send_message(chat_id, "❌ Не вдалося визначити адресу за геолокацією.\nБудь ласка, введіть її вручну.")
            state["step"] = "choose_district"
            kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            for d in district_names:
                kb.add(d)
            bot.send_message(chat_id, "Оберіть район:", reply_markup=kb)
    except Exception:
        print("handle_location error:", traceback.format_exc())


@bot.chat_member_handler()
def handle_new_member(msg):
    try:
        if not hasattr(msg, "new_chat_member"):
            return
        if msg.new_chat_member.status != "member":
            return
        chat_id = msg.chat.id
        user = msg.new_chat_member.user
        user_id = user.id
        section = None
        for sect, cid in personnel_chats.items():
            if cid == chat_id:
                section = sect
                break
        if not section:
            return
        if user_id in authorized_users.get(section, {}).get("authorized", []) \
           or user_id in authorized_users.get("ADMINS", []) \
           or (bot.get_me() and user_id == bot.get_me().id):
            return
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔐 Авторизація", callback_data=f"auth:{section}"))
        bot.send_message(chat_id, f"👋 Вітаю, {user.first_name}!\nНатисніть кнопку для авторизації:", reply_markup=kb)
    except Exception:
        print("handle_new_member error:", traceback.format_exc())

@bot.message_handler(content_types=['left_chat_member'])
def handle_left_chat_member(msg):
    try:
        user = msg.left_chat_member
        user_id = user.id
        chat_id = msg.chat.id
        section = None
        for sect, cid in personnel_chats.items():
            if cid == chat_id:
                section = sect
                break
        if not section:
            return
        changed = False
        if section in authorized_users and isinstance(authorized_users[section], dict):
            authorized_list = authorized_users[section].get("authorized", [])
            if user_id in authorized_list:
                authorized_users[section]["authorized"].remove(user_id)
                changed = True
            if authorized_users[section].get("representative") == user_id:
                authorized_users[section]["representative"] = None
                changed = True
        if changed:
            save_authorized_users()
    except Exception:
        print("handle_left_chat_member error:", traceback.format_exc())

@bot.callback_query_handler(func=lambda c: c.data.startswith("auth:"))
def cb_auth(call):
    try:
        section = call.data.split(":")[1]
        user_id = call.from_user.id
        authorized_users.setdefault(section, {})
        authorized_users[section].setdefault("authorized", [])
        if user_id not in authorized_users[section]["authorized"]:
            authorized_users[section]["authorized"].append(user_id)
            save_authorized_users()
        bot.answer_callback_query(call.id, "✅ Ви авторизовані.")
        bot.edit_message_text("✅ Ви авторизовані для цього району.", call.message.chat.id, call.message.message_id)
    except Exception:
        print("cb_auth error:", traceback.format_exc())

@bot.message_handler(commands=["призначити"])
def cmd_assign(msg):
    try:
        if msg.chat.id not in personnel_chats.values():
            return bot.reply_to(msg, "❌ Лише в чаті району.")
        if msg.from_user.id not in authorized_users.get("ADMINS", []):
            return bot.reply_to(msg, "⛔️ Тільки адміністратор може призначати.")
        section = None
        for sect, chat_id in personnel_chats.items():
            if chat_id == msg.chat.id:
                section = sect
                break
        if not section:
            return
        members = authorized_users.get(section, {}).get("authorized", [])
        if not members:
            return bot.reply_to(msg, "❌ Немає авторизованих користувачів у цьому районі.")
        kb = types.InlineKeyboardMarkup(row_width=1)
        for uid in members:
            try:
                user = bot.get_chat_member(msg.chat.id, uid).user
                name = user.first_name or f"ID {uid}"
            except Exception:
                name = f"ID {uid}"
            btn = types.InlineKeyboardButton(f"👤 {name}", callback_data=f"assign_rep:{section}:{uid}")
            kb.add(btn)
        bot.send_message(msg.chat.id, "Оберіть представника:", reply_markup=kb)
    except Exception:
        print("cmd_assign error:", traceback.format_exc())

@bot.message_handler(commands=["скасувати"])
def cmd_unassign(msg):
    try:
        if msg.chat.id not in personnel_chats.values():
            return bot.reply_to(msg, "❌ Лише в чаті району.")
        if msg.from_user.id not in authorized_users.get("ADMINS", []):
            return bot.reply_to(msg, "⛔️ Тільки адміністратор може скасувати.")
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
        try:
            member = bot.get_chat_member(msg.chat.id, rep)
            name = member.user.first_name
        except Exception:
            name = f"{rep} (невідомо)"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(f"🗑️ {name}", callback_data=f"unassign_rep:{section}:{rep}"))
        bot.send_message(msg.chat.id, "Скасувати представника:", reply_markup=kb)
    except Exception:
        print("cmd_unassign error:", traceback.format_exc())

@bot.callback_query_handler(func=lambda c: c.data.startswith("assign_rep:"))
def cb_assign_rep(call):
    try:
        _, section, user_id = call.data.split(":")
        user_id = int(user_id)
        authorized_users.setdefault(section, {})["representative"] = user_id
        save_authorized_users()
        bot.answer_callback_query(call.id, "✅ Призначено.")
        bot.edit_message_text("✅ Користувача призначено представником.", call.message.chat.id, call.message.message_id)
    except Exception:
        print("cb_assign_rep error:", traceback.format_exc())

@bot.callback_query_handler(func=lambda c: c.data.startswith("unassign_rep:"))
def cb_unassign_rep(call):
    try:
        _, section, user_id = call.data.split(":")
        user_id = int(user_id)
        if authorized_users.get(section, {}).get("representative") == user_id:
            authorized_users[section]["representative"] = None
            save_authorized_users()
        bot.answer_callback_query(call.id, "✅ Скасовано.")
        bot.edit_message_text("🗑️ Представника скасовано.", call.message.chat.id, call.message.message_id)
    except Exception:
        print("cb_unassign_rep error:", traceback.format_exc())

@bot.callback_query_handler(func=lambda call: True)
def cb_general(call):
    try:
        if call.data == "start":
            bot.answer_callback_query(call.id)
            return cmd_start(call.message)
        if call.data.startswith("filter:"):
            bot.answer_callback_query(call.id)
            filter_type = call.data.split(":")[1]
            chat_id = call.message.chat.id
            section = None
            for sect, cid in personnel_chats.items():
                if cid == chat_id:
                    section = sect
                    break
            if not section:
                return bot.send_message(chat_id, "❌ Ця команда доступна лише в чатах дільниць.")
            filtered = []
            for i, r in enumerate(requests_list):
                if district_ids.get(r["district"]) != section:
                    continue
                if filter_type == "pending" and not r.get("completed"):
                    filtered.append((i, r))
                elif filter_type == "done" and r.get("status") == "done":
                    filtered.append((i, r))
                elif filter_type == "error" and r.get("status") == "error":
                    filtered.append((i, r))
            if not filtered:
                return bot.send_message(chat_id, "❌ Немає заявок для цього району за обраним фільтром.")
            status_names = {"pending": "🕐 Очікують", "done": "✅ Виконані", "error": "❌ Не працює"}
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
        section = district_ids.get(r["district"])
        if not chat_action_allowed.get(section, True):
            rep = authorized_users.get(section, {}).get("representative")
            allowed = (call.from_user.id in authorized_users.get("ADMINS", []) or call.from_user.id == rep)
            if not allowed:
                return bot.answer_callback_query(call.id, "⛔️ Дію заборонено.")
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
        elif action == "not_working":
            r.update(
                completed=False,
                processed_by=call.from_user.first_name,
                status="error"
            )
            try:
                new_kb = types.InlineKeyboardMarkup()
                new_kb.add(types.InlineKeyboardButton("✅ Виконано", callback_data=f"status:done:{idx}"))
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=new_kb)
            except:
                pass
            try:
                phones = "\n".join(f"📞 {n}" for n in district_phones[r['district']])
                bot.send_message(r["user_id"], f"⚠️ Заявку відпрацьовано, але ліфт не працює.\n{phones}")
            except:
                pass
        save_requests_to_db()
        bot.answer_callback_query(call.id)
    except Exception:
        print("cb_general error:", traceback.format_exc())
