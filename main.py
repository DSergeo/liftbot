from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, jsonify, send_file, request, session, redirect, url_for
import os
import json
import threading
import subprocess
import logging
import telebot # Для работы с ботом
import time # Для time.sleep

# Импортируем объект бота
from app.bot_requests import bot

# Импортируем глобальные переменные и функции
from app.bot_requests.shared import (
    user_states, requests_list, chat_action_allowed, RIGHTS_FILE,
    AUTHORIZED_USERS_FILE, authorized_users, personnel_chats, district_ids,
    VAPID_PUBLIC_KEY, VAPID_CLAIMS, subscriptions, SUBS_FILE,
    init_database, load_requests_from_db, load_action_rights,
    save_action_rights, load_authorized_users, save_authorized_users,
    load_subscriptions, save_subscriptions, load_address_data, send_push,
    log_action
)

# Импортируем обработчики (их не нужно явно импортировать, они регистрируются через bot)
# from app.bot_requests import handlers # Эту строку можно удалить, т.к. обработчики уже привязаны к 'bot'

# Импортируем сервисы (планировщик)
from app.bot_requests.services import sched_loop

# Настройка логирования
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-for-sessions-123456789')

# ======== ВАЖНО: регистрация Blueprint'ов, если они есть =========
# Если этих Blueprints нет или они не нужны, удалите эти строки.
try:
    from app.contacts.routes import contacts_html, contacts_api
    from app.counterparties.routes import counterparty_html, counterparties_api
    from app.contracts.routes import contract_html, contract_api

    app.register_blueprint(contacts_html)
    app.register_blueprint(contacts_api)
    app.register_blueprint(counterparty_html)
    app.register_blueprint(counterparties_api)
    app.register_blueprint(contract_html)
    app.register_blueprint(contract_api)
except ImportError as e:
    logger.warning(f"Не удалось импортировать один из Blueprints: {e}. Пропустите, если они не нужны.")
# =================================================================

# Функция для запуска бота в режиме long polling
def start_bot():
    logger.info("Бот запускается в режиме long polling...")

    # Проверяем информацию о вебхуке ПЕРЕД удалением
    try:
        webhook_info_before = bot.get_webhook_info()
        logger.info(f"Webhook info BEFORE remove: URL={webhook_info_before.url}, Pending Updates={webhook_info_before.pending_update_count}")
    except Exception as e:
        logger.error(f"Ошибка при получении информации о вебхуке ДО удаления: {e}")

    # Пытаемся удалить вебхук
    try:
        bot.remove_webhook()
        time.sleep(0.1) # Небольшая задержка, чтобы убедиться
        logger.info("Вебхук успешно удален.")
    except Exception as e:
        logger.error(f"Ошибка при попытке удалить вебхук: {e}")

    # Проверяем информацию о вебхуке ПОСЛЕ удаления
    try:
        webhook_info_after = bot.get_webhook_info()
        logger.info(f"Webhook info AFTER remove: URL={webhook_info_after.url}, Pending Updates={webhook_info_after.pending_update_count}")
    except Exception as e:
        logger.error(f"Ошибка при получении информации о вебхуке ПОСЛЕ удаления: {e}")

    # Запускаем long polling
    bot.infinity_polling()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/manifest.json')
def manifest():
    return send_file('manifest.json', mimetype='application/manifest+json')

@app.route('/service-worker.js')
def service_worker():
    return send_file('service-worker.js', mimetype='application/javascript')

@app.route('/subscribe', methods=['POST'])
def subscribe():
    if not request.json:
        return jsonify({'error': 'No data provided'}), 400

    subscription_info = request.json
    if subscription_info not in subscriptions:
        subscriptions.append(subscription_info)
        save_subscriptions()
        print("✅ Новая подписка добавлена:", subscription_info)
        return jsonify({'message': 'Subscription added successfully'}), 200
    else:
        print("ℹ️ Подписка уже существует:", subscription_info)
        return jsonify({'message': 'Subscription already exists'}), 200

@app.route("/admin_panel")
def admin_panel():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("admin.html",
                           authorized_users=authorized_users,
                           personnel_chats=personnel_chats,
                           chat_action_allowed=chat_action_allowed,
                           district_names=district_names,
                           requests_list=requests_list)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form["password"]
        # Используем os.getenv("ADMIN_PASSWORD")
        if password == os.getenv("ADMIN_PASSWORD"):
            session["logged_in"] = True
            log_action("admin", "login_success")
            return redirect(url_for("admin_panel"))
        else:
            log_action("admin", "login_failure", {"ip": request.remote_addr})
            return "Неверный пароль", 401
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    log_action("admin", "logout")
    return redirect(url_for("login"))

@app.route("/toggle_chat_action", methods=["POST"])
def toggle_chat_action():
    if not session.get("logged_in"):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    data = request.json
    chat_name = data.get("chat_name")
    if chat_name in chat_action_allowed:
        chat_action_allowed[chat_name] = not chat_action_allowed[chat_name]
        save_action_rights()
        log_action("admin", "toggle_chat_action", {"chat": chat_name, "status": chat_action_allowed[chat_name]})
        return jsonify({"success": True, "status": chat_action_allowed[chat_name]})
    return jsonify({"success": False, "message": "Invalid chat name"})

@app.route("/add_admin", methods=["POST"])
def add_admin():
    if not session.get("logged_in"):
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    data = request.json
    admin_id = int(data["admin_id"])
    if "ADMINS" not in authorized_users:
        authorized_users["ADMINS"] = []
    if admin_id not in authorized_users["ADMINS"]:
        authorized_users["ADMINS"].append(admin_id)
        save_authorized_users()
        log_action("admin", "add_admin", {"admin_id": admin_id})
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Admin already exists"})

@app.route("/remove_admin", methods=["POST"])
def remove_admin():
    if not session.get("logged_in"):
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    data = request.json
    admin_id = int(data["admin_id"])
    if "ADMINS" in authorized_users and admin_id in authorized_users["ADMINS"]:
        authorized_users["ADMINS"].remove(admin_id)
        save_authorized_users()
        log_action("admin", "remove_admin", {"admin_id": admin_id})
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Admin not found"})

@app.route("/delete_request/<int:index>", methods=["DELETE"])
def delete_request(index):
    if not session.get("logged_in"):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    if 0 <= index < len(requests_list):
        deleted_request = requests_list.pop(index)
        save_requests_to_db()
        log_action("admin", "delete_request", {"index": index, "request_info": deleted_request})
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Request not found"})

@app.route("/mark_request_completed/<int:index>", methods=["POST"])
def mark_request_completed(index):
    if not session.get("logged_in"):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    if 0 <= index < len(requests_list):
        r = requests_list[index]
        if not r.get("completed"):
            r.update(
                completed=True,
                completed_time=datetime.now(kyiv_tz).strftime("%Y-%m-%d %H:%M:%S"), # kyiv_tz from shared
                processed_by="Admin Panel",
                status="done"
            )
            save_requests_to_db()

            # Обновление сообщения в чате, если есть chat_msg_id
            try:
                chat_id_for_bot = personnel_chats[district_ids[r["district"]]]
                message_id = r.get("chat_msg_id")
                if chat_id_for_bot and message_id:
                    # В режиме long polling, bot.edit_message_reply_markup будет работать напрямую
                    bot.edit_message_reply_markup(chat_id_for_bot, message_id, reply_markup=None)
            except Exception as e:
                logger.error(f"Не удалось обновить разметку сообщения в чате: {e}")

            log_action("admin", "mark_completed", {"index": index, "request_info": r})
            return jsonify({"success": True})
    return jsonify({"success": False, "message": "Request not found or already completed"})


@app.route("/mark_request_error/<int:index>", methods=["POST"])
def mark_request_error(index):
    if not session.get("logged_in"):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    if 0 <= index < len(requests_list):
        r = requests_list[index]
        if r.get("status") != "error":
            r.update(
                completed=False,
                processed_by="Admin Panel",
                status="error"
            )
            save_requests_to_db()
            log_action("admin", "mark_error", {"index": index, "request_info": r})
            return jsonify({"success": True})
    return jsonify({"success": False, "message": "Request not found or already in error state"})


# ========== run ==========\
if __name__ == "__main__":
    # app.secret_key = "дуже_секретний_рядок_тут" # Эта строка теперь берется из os.environ.get

    # Инициализация базы данных и загрузка данных
    init_database()
    load_requests_from_db()
    load_action_rights()
    load_authorized_users()
    load_subscriptions()
    load_address_data() # Загружаем данные по адресам

    # Запускаем бота в отдельном потоке (long polling)
    # Эта строка заменяет bot.set_webhook и связана с функцией start_bot
    threading.Thread(target=start_bot, daemon=True).start()
    logger.info("Поток бота запущен в режиме long polling.")

    # Запуск планировщика в отдельном потоке
    scheduler_thread = threading.Thread(target=sched_loop, daemon=True)
    scheduler_thread.start()
    logger.info("Поток планировщика запущен.")

    # Запуск Flask приложения
    # Вы можете указать порт здесь или использовать переменную окружения PORT
    FLASK_PORT = int(os.getenv("PORT", 5000)) # Используем PORT из .env, если есть
    logger.info(f"Приложение Flask запускается на порту {FLASK_PORT}...")
    app.run(host="0.0.0.0", port=FLASK_PORT)