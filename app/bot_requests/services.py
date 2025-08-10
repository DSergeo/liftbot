# app/bot_requests/services.py
import threading
import schedule
import time
from datetime import datetime
from app.requests.services import requests_list, save_requests_to_db
from app.bot_requests.shared import personnel_chats, district_ids
from app.bot_requests.shared import save_action_rights
from app.shared_bot import bot_instance  # we will expose shared bot from bot_requests.py
import traceback

def send_daily_report():
    summary = {}
    for i, r in enumerate(requests_list):
        if r.get("completed"):
            continue
        sect = district_ids.get(r.get("district"))
        chat = personnel_chats.get(sect)
        if not chat:
            continue
        summary.setdefault(chat, [])
        url = f"https://t.me/c/{str(chat)[4:]}/{r.get('chat_msg_id')}"
        summary[chat].append(f"#{i+1} <a href='{url}'>{r.get('address')} п.{r.get('entrance')}</a>")
    for chat, lines in summary.items():
        try:
            bot_instance.send_message(chat, "📋 <b>Невиконані заявки:</b>\n" + "\n".join(lines))
        except Exception as e:
            print("send_daily_report error:", e)

def sched_loop():
    schedule.every().day.at("08:30").do(send_daily_report)
    while True:
        schedule.run_pending()
        time.sleep(60)

def start_scheduler_thread():
    t = threading.Thread(target=sched_loop, daemon=True)
    t.start()
    return t
