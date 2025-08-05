import schedule
import time
from datetime import datetime
import logging

# Импортируем объект bot и глобальные переменные из bot_requests
from . import bot
from .shared import requests_list, personnel_chats, district_ids, kyiv_tz

logger = logging.getLogger(__name__)

def send_daily():
    """
    Отправляет ежедневный отчет о невыполненных заявках в соответствующие чаты персонала.
    """
    logger.info("Запускаем отправку ежедневного отчета...")
    summary = {}
    current_time_kyiv = datetime.now(kyiv_tz)

    for i, r in enumerate(requests_list):
        # Если заявка выполнена, пропускаем ее
        if r.get("completed"):
            continue

        # Проверяем, если заявка была создана более 24 часов назад и не завершена
        try:
            request_time = kyiv_tz.localize(datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S"))
            if current_time_kyiv - request_time < timedelta(hours=24):
                continue # Пропускаем заявки, которым меньше 24 часов
        except ValueError:
            logger.warning(f"Не удалось распарсить timestamp для заявки: {r.get('id')}")
            continue # Пропускаем некорректные записи

        # Определяем чат, в который нужно отправить отчет
        district_id = district_ids.get(r.get("district"))
        if not district_id:
            logger.warning(f"Не найден ID района для заявки: {r.get('id')}, район: {r.get('district')}")
            continue

        chat = personnel_chats.get(district_id)
        if not chat:
            logger.warning(f"Не найден чат персонала для района: {district_id}")
            continue

        summary.setdefault(chat, [])
        # Формируем URL для сообщения в чате
        # Убедитесь, что chat_msg_id существует и корректен
        if r.get("chat_msg_id"):
            # Для публичных супергрупп ID канала должен быть без "-100"
            chat_url_id = str(chat)[4:] if str(chat).startswith("-100") else str(chat)
            url = f"https://t.me/c/{chat_url_id}/{r['chat_msg_id']}"
            summary[chat].append(f"#{i + 1} <a href='{url}'>{r['address']} п.{r['entrance']}</a>")
        else:
            summary[chat].append(f"#{i + 1} {r['address']} п.{r['entrance']}") # без ссылки, если нет chat_msg_id

    for chat, lines in summary.items():
        if lines: # Отправляем сообщение только если есть невыполненные заявки
            message_text = "📋 <b>Невиконані заявки:</b>\n" + "\n".join(lines)
            try:
                bot.send_message(chat, message_text, parse_mode="HTML", disable_web_page_preview=True)
                logger.info(f"Отправлен ежедневный отчет в чат {chat}")
            except Exception as e:
                logger.error(f"Ошибка при отправке ежедневного отчета в чат {chat}: {e}")
        else:
            logger.info(f"В чате {chat} нет невыполненных заявок.")

def sched_loop():
    """
    Запускает планировщик для выполнения send_daily каждый день в 08:30.
    """
    logger.info("Запускаем планировщик...")
    schedule.every().day.at("08:30").do(send_daily)
    while True:
        schedule.run_pending()
        time.sleep(60) # Проверяем каждую минуту