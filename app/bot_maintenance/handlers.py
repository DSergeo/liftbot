# app/bot_maintenance/handlers.py
from app.bot_maintenance.shared import bot, user_states, save_maintenance_log, maintenance_schedule, kyiv_tz
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

@bot.message_handler(content_types=['photo', 'text'])
def handle_maintenance(msg):
    """
    Обработка сообщений от механика с фото и подписью.
    Подпись должна содержать дату ТО и адрес.
    """
    chat_id = msg.chat.id
    state = user_states.get(chat_id, {})

    # Получаем имя механика
    mechanic_name = msg.from_user.full_name

    # Обязательное фото
    if not msg.photo:
        bot.send_message(chat_id, "❌ Потрібно надіслати фото виконаного ТО.")
        return

    # Получаем caption/текст с адресом и датой
    caption = msg.caption or msg.text or ""
    if not caption:
        bot.send_message(chat_id, "❌ Потрібно вказати адресу та дату ТО у підписі до фото.")
        return

    # Простейшее извлечение даты и адреса
    try:
        lines = [l.strip() for l in caption.splitlines() if l.strip()]
        date_line = next((l for l in lines if any(c.isdigit() for c in l)), None)
        address_line = next((l for l in lines if l != date_line), None)
        date_obj = datetime.strptime(date_line, "%d.%m.%Y")
    except Exception:
        bot.send_message(chat_id, "❌ Не вдалося розпізнати дату. Використовуйте формат ДД.ММ.РРРР")
        return

    # Проверка даты по графику
    scheduled_dates = maintenance_schedule.get(address_line, [])
    allowed = any(abs((date_obj - datetime.strptime(d, "%Y-%m-%d")).days) <= 4 for d in scheduled_dates)
    if not allowed:
        bot.send_message(chat_id, "❌ Дата ТО не відповідає графіку (±4 дні).")
        return

    # Сохраняем лог ТО
    log_entry = {
        "mechanic_name": mechanic_name,
        "district": state.get("district", ""),
        "address": address_line,
        "date": date_obj.strftime("%Y-%m-%d"),
        "photo_file_id": msg.photo[-1].file_id,
        "notes": caption,
        "verified": True,
        "created_at": datetime.now(kyiv_tz).isoformat()
    }
    save_maintenance_log(log_entry)

    bot.send_message(chat_id, f"✅ ТО по адресі <b>{address_line}</b> успішно зафіксовано.")
