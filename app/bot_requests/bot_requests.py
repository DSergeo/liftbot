# app/bot_requests/bot_requests.py
from flask import Blueprint, render_template, session, redirect, url_for, jsonify, request, send_file
from app.bot_requests.handlers import *  # registers handlers on bot
from app.bot_requests.shared import personnel_chats, district_ids, district_phones
from app.requests.services import requests_list, load_requests_from_db, save_requests_to_db
from app.bot_requests.services import start_scheduler_thread
from app.core.config import Config
from telebot import TeleBot, types
import io
from openpyxl import Workbook
from datetime import datetime
import sqlite3

def start_bot_requests_thread():
    import threading
    from .handlers import bot_polling_loop

    thread = threading.Thread(target=bot_polling_loop, daemon=True)
    thread.start()


bot_requests_bp = Blueprint("bot_requests_bp", __name__)

# create a TeleBot instance and expose it for handlers via shared module
from app.shared_bot import bot_instance as bot  # shared bot instance

# Routes (web) — Many of these were in monolith; we map them into blueprint

@bot_requests_bp.route("/requests_data")
def requests_data():
    try:
        load_requests_from_db()
        formatted = []
        for i, req in enumerate(requests_list):
            formatted.append({
                "id": i + 1,
                "timestamp": req.get("timestamp", ""),
                "name": req.get("name", ""),
                "phone": req.get("phone", ""),
                "address": req.get("address", ""),
                "entrance": req.get("entrance", ""),
                "district": req.get("district", ""),
                "issue": req.get("issue", ""),
                "status": req.get("status", "pending"),
                "completed": bool(req.get("completed", False)),
                "processed_by": req.get("processed_by", ""),
                "completed_time": req.get("completed_time", ""),
                "user_id": req.get("user_id", "")
            })
        return jsonify({"requests": formatted})
    except Exception as e:
        print("requests_data error:", e)
        return jsonify({"error": "Failed to load requests", "requests": []})

@bot_requests_bp.route("/export")
def export_from_db():
    try:
        conn = sqlite3.connect(Config.DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM requests")
        rows = c.fetchall()
        headers = [desc[0] for desc in c.description]
        conn.close()

        wb = Workbook()
        ws = wb.active
        ws.append(headers)
        for row in rows:
            ws.append(row)
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(output, download_name="requests_export.xlsx", as_attachment=True,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        print("export error:", e)
        return "Export failed", 500

@bot_requests_bp.route("/complete_request/<int:idx>", methods=["POST"])
def complete_request(idx):
    if 0 <= idx < len(requests_list):
        r = requests_list[idx]
        r.update(
            completed=True,
            completed_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            processed_by="Оператор з веб"
        )
        save_requests_to_db()
        try:
            bot.edit_message_reply_markup(
                chat_id=personnel_chats[district_ids[r["district"]]],
                message_id=int(r["chat_msg_id"]),
                reply_markup=None
            )
        except Exception:
            pass
        try:
            bot.send_message(r["user_id"], "✅ Ваша заявка виконана.")
        except Exception:
            pass
        return jsonify({"success": True})
    return jsonify({"success": False})

@bot_requests_bp.route("/not_working_request/<int:idx>", methods=["POST"])
def not_working_request(idx):
    if 0 <= idx < len(requests_list):
        r = requests_list[idx]
        r.update(
            completed=True,
            completed_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            processed_by="Оператор з веб"
        )
        save_requests_to_db()
        try:
            new_kb = types.InlineKeyboardMarkup()
            new_kb.add(types.InlineKeyboardButton("✅ Виконано", callback_data=f"status:done:{idx}"))
            bot.edit_message_reply_markup(chat_id=personnel_chats[district_ids[r["district"]]],
                                          message_id=int(r["chat_msg_id"]), reply_markup=new_kb)
        except Exception:
            pass
        try:
            phones = "\n".join(f"📞 {n}" for n in district_phones[r["district"]])
            bot.send_message(r["user_id"], "⚠️ Заявку відпрацьовано, але ліфт не працює.\n" + phones)
        except Exception:
            pass
        return jsonify({"success": True})
    return jsonify({"success": False})

@bot_requests_bp.route("/delete_request/<int:idx>", methods=["POST"])
def delete_request(idx):
    if 0 <= idx < len(requests_list):
        try:
            del requests_list[idx]
            save_requests_to_db()
            return jsonify({"success": True})
        except Exception:
            return jsonify({"success": False})
    return jsonify({"success": False})

@bot_requests_bp.route("/get_chat_rights")
def get_chat_rights():
    from app.bot_requests.shared import chat_action_allowed
    return jsonify(chat_action_allowed)

@bot_requests_bp.route("/toggle_actions", methods=["POST"])
def toggle_chat_actions():
    data = request.get_json(force=True)
    section = data.get("section")
    enabled = data.get("enabled")
    from app.bot_requests.shared import chat_action_allowed, save_action_rights
    if section in chat_action_allowed:
        chat_action_allowed[section] = enabled
        save_action_rights()
        return jsonify({"success": True})
    return jsonify({"success": False})

@bot_requests_bp.route("/update_status/<int:idx>/<action>", methods=["POST"])
def update_status(idx, action):
    if 0 <= idx < len(requests_list):
        r = requests_list[idx]
        r.update(
            completed=True,
            completed_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            processed_by="Оператор з веб"
        )
        if action == "done":
            r["status"] = "done"
        elif action == "not_working":
            r["status"] = "error"
        save_requests_to_db()
        try:
            if action == "not_working":
                new_kb = types.InlineKeyboardMarkup()
                new_kb.add(types.InlineKeyboardButton("✅ Виконано", callback_data=f"status:done:{idx}"))
                bot.edit_message_reply_markup(chat_id=personnel_chats[district_ids[r["district"]]],
                                              message_id=int(r["chat_msg_id"]),
                                              reply_markup=new_kb)
            else:
                bot.edit_message_reply_markup(chat_id=personnel_chats[district_ids[r["district"]]],
                                              message_id=int(r["chat_msg_id"]),
                                              reply_markup=None)
        except Exception as e:
            print("update_status edit error:", e)
        try:
            if action == "done":
                bot.send_message(r["user_id"], "✅ Ваша заявка виконана.")
            elif action == "not_working":
                phones = "\n".join(f"📞 {n}" for n in district_phones[r["district"]])
                bot.send_message(r["user_id"], f"⚠️ Заявку відпрацьовано, але ліфт не працює.\n{phones}")
        except Exception:
            pass
        return jsonify({"success": True})
    return jsonify({"success": False})
