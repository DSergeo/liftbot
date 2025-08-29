# run_bots.py

import os
import threading
import time
import schedule
import logging
import pytz
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telebot import types
import threading
from flask import Flask, jsonify, request
from flask_cors import CORS

load_dotenv()

bot_api_app = Flask(__name__)
CORS(bot_api_app, resources={r"/*": {"origins": "*"}})
# ====== Логирование ======
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ====== Импорт ботов и их логики ======
from app.bot_maintenance.shared import bot as maintenance_bot, init_database as init_maintenance_db
from app.bot_maintenance import handlers
from app.bot_requests.shared import (
    bot as requests_bot,
    init_database as init_requests_db,
    save_requests_to_db,
    load_requests_from_db,
    requests_list,
    personnel_chats,
    district_ids,
    district_phones
)
from app.bot_requests import handlers
# ====== Путь к токенам ======
BOT_TOKEN_REQUESTS = os.getenv("BOT_TOKEN_REQUESTS")
BOT_TOKEN_MAINTENANCE = os.getenv("BOT_TOKEN_MAINTENANCE")

# ====== ИНИЦИАЛИЗАЦИЯ БАЗ ДАННЫХ ======
init_maintenance_db()
logger.info("maintenance.db created.")
init_requests_db()
load_requests_from_db()

@bot_api_app.route("/requests_data")
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


@bot_api_app.route("/complete_request/<int:idx>", methods=["POST"])
def complete_request_api(idx):
    if 0 <= idx < len(requests_list):
        r = requests_list[idx]
        r.update(
            completed=True,
            completed_time=datetime.now(kyiv_tz).strftime("%Y-%m-%d %H:%M:%S"),
            processed_by="Оператор з веб"
        )
        save_requests_to_db()

        try:
            requests_bot.edit_message_reply_markup(
                chat_id=personnel_chats[district_ids[r["district"]]],
                message_id=int(r["chat_msg_id"]),
                reply_markup=None
            )
        except: pass

        try:
            requests_bot.send_message(r["user_id"], "✅ Ваша заявка виконана.")
        except: pass
        return jsonify({"success": True})
    return jsonify({"success": False})

@bot_api_app.route("/not_working_request/<int:idx>", methods=["POST"])
def not_working_request_api(idx):
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
            requests_bot.edit_message_reply_markup(
                chat_id=personnel_chats[district_ids[r["district"]]],
                message_id=int(r["chat_msg_id"]),
                reply_markup=new_kb
            )

        except: pass

        try:
            phones = "\n".join(f"📞 {n}" for n in district_phones[r["district"]])
            requests_bot.send_message(r["user_id"],
                             "⚠️ Заявку відпрацьовано, але ліфт не працює.\n" + phones)
        except: pass
        return jsonify({"success": True})
    return jsonify({"success": False})

@bot_api_app.route("/delete_request/<int:idx>", methods=["POST"])
def delete_request_api(idx):
    logger.info(f"Получен запрос на удаление заявки с индексом: {idx}")
    
    # Проверяем, является ли индекс валидным
    if 0 <= idx < len(requests_list):
        try:
            logger.info(f"requests_list до удаления: {len(requests_list)} элементов")
            
            # Внимание: если вы удаляете элемент из списка по индексу, а затем перезагружаете страницу
            # и отправляете тот же запрос, индекс может указывать на другой элемент или быть невалидным.
            # Убедитесь, что ваш фронтенд всегда использует актуальные индексы.
            
            del requests_list[idx]
            save_requests_to_db()
            
            logger.info(f"Заявка с индексом {idx} успешно удалена.")
            logger.info(f"requests_list после удаления: {len(requests_list)} элементов")
            
            return jsonify({"success": True})
        except Exception as e:
            logger.error(f"Ошибка при удалении заявки с индексом {idx}: {e}", exc_info=True)
            return jsonify({"success": False})
    else:
        logger.warning(f"Получен неверный индекс для удаления: {idx}. requests_list имеет {len(requests_list)} элементов.")
        return jsonify({"success": False})

@bot_api_app.route("/update_status/<int:idx>/<action>", methods=["POST"])
def update_status_api(idx, action):
    logger.info(f"🔄 Запит на оновлення заявки #{idx}, дія: {action}")

    if 0 <= idx < len(requests_list):
        r = requests_list[idx]

        # фиксируем время и исполнителя
        r["completed"] = True
        r["completed_time"] = datetime.now(kyiv_tz).strftime("%Y-%m-%d %H:%M:%S")
        r["processed_by"] = "Оператор з веб"

        if action == "done":
            r["status"] = "done"
        elif action == "not_working":
            r["status"] = "error"

        save_requests_to_db()
        logger.info(f"✅ Заявка #{idx} оновлена в БД зі статусом: {r['status']}")

        try:
            if action == "not_working":
                # залишити тільки кнопку "✅ Виконано"
                new_kb = types.InlineKeyboardMarkup()
                new_kb.add(
                    types.InlineKeyboardButton("✅ Виконано", callback_data=f"status:done:{idx}")
                )
                requests_bot.edit_message_reply_markup(
                    chat_id=personnel_chats[district_ids[r["district"]]],
                    message_id=int(r["chat_msg_id"]),
                    reply_markup=new_kb
                )
                logger.info(f"↩️ Кнопки замінено на ✅ Виконано (district {r['district']})")
            else:
                # якщо "✅ Виконано" — видаляємо всі кнопки
                requests_bot.edit_message_reply_markup(
                    chat_id=personnel_chats[district_ids[r["district"]]],
                    message_id=int(r["chat_msg_id"]),
                    reply_markup=None
                )
                logger.info(f"🗑 Кнопки видалено у чаті (district {r['district']})")
        except Exception as e:
            logger.warning(f"⚠️ Не вдалося оновити кнопки: {e}")

        try:
            if action == "done":
                requests_bot.send_message(r["user_id"], "✅ Ваша заявка виконана.")
                logger.info(f"📩 Користувачу {r['user_id']} надіслано повідомлення: виконано")
            elif action == "not_working":
                phones = "\n".join(f"📞 {n}" for n in district_phones[r["district"]])
                requests_bot.send_message(
                    r["user_id"],
                    f"⚠️ Заявку відпрацьовано, але ліфт не працює.\n{phones}"
                )
                logger.info(f"📩 Користувачу {r['user_id']} надіслано повідомлення: ліфт не працює")
        except Exception as e:
            logger.error(f"⚠️ Не вдалося надіслати повідомлення користувачу {r['user_id']}: {e}")

        return jsonify({"success": True})

    logger.error(f"❌ Заявки #{idx} не існує")
    return jsonify({"success": False})

# ====== VAPID ключи для Web Push ======
@bot_api_app.route("/vapid_public_key")
def get_vapid_key_api():
    return jsonify({"key": VAPID_PUBLIC_KEY})

@bot_api_app.route("/subscribe_push", methods=["POST"])
def subscribe_push_api():
    sub = request.get_json()
    if sub and sub not in subscriptions:
        subscriptions.append(sub)
        save_subscriptions()
    return jsonify({"success": True})

# ====== Планировщик ======
kyiv_tz = pytz.timezone("Europe/Kyiv")

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
        requests_bot.send_message(chat, "📋 <b>Невиконані заявки:</b>\n" + " \n".join(lines), parse_mode="HTML")


def sched_loop():
    test_delay_minutes = 0 # 🔹 меняй только эту цифру
    if test_delay_minutes > 0:
        run_time = (datetime.now() + timedelta(minutes=test_delay_minutes)).strftime("%H:%M")
        logger.info(f"⏰ Тестовый запуск через {test_delay_minutes} мин, в {run_time}")
        schedule.every().day.at(run_time).do(send_daily)
    else:
        logger.info("⏰ Боевой режим: каждый день в 08:30")
        schedule.every().day.at("08:30").do(send_daily)

    while True:
        schedule.run_pending()
        time.sleep(60)

# ====== Запуск ботов в отдельных потоках ======
def start_requests_bot():
    logger.info("Запускается бот заявок...")
    while True:
        try:
            requests_bot.infinity_polling(timeout=60, long_polling_timeout=60, allowed_updates=True)
        except Exception as e:
            logger.error(f"Polling заявок упал: {e}", exc_info=True)
            time.sleep(5)

def start_maintenance_bot():
    logger.info("Запускается бот ТО...")
    while True:
        try:
            maintenance_bot.infinity_polling(timeout=60, long_polling_timeout=60, allowed_updates=True)
        except Exception as e:
            logger.error(f"Polling ТО упал: {e}", exc_info=True)
            time.sleep(5)

# === Запуск ===
if __name__ == "__main__":

    # Запускаем Flask-API в отдельном потоке
    threading.Thread(target=lambda: bot_api_app.run(host="127.0.0.1", port=5001)).start() 

    # Запускаем планировщик в отдельном потоке
    threading.Thread(target=sched_loop, daemon=True).start()
    
    # Запускаем ботов в отдельных потоках
    threading.Thread(target=start_requests_bot, daemon=True).start()
    threading.Thread(target=start_maintenance_bot, daemon=True).start()
    
    logger.info("Боты и планировщик запущены. Приложение работает...")

    # Бесконечный цикл, чтобы основной процесс не завершился
    while True:
        time.sleep(1)