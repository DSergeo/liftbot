from dotenv import load_dotenv
load_dotenv()

import os, json, threading, subprocess, time, schedule, logging
from flask import Flask, render_template, jsonify, send_file, request, session, redirect, url_for
import telebot
from telebot import types
from geopy.geocoders import Nominatim
import sqlite3
from datetime import datetime, timedelta
import pytz

# ====== Бот ТО (Maintenance) ======
from app.bot_maintenance.shared import bot as maintenance_bot, init_database as init_maintenance_db
#import app.bot_maintenance.handlers  # подключаем хендлеры бота ТО
from app.bot_maintenance import handlers   # просто импорт, чтобы зарегистрировались хендлеры
#from app.bot_maintenance.shared import bot, init_database
# ====== Бот заявок (Requests) ======
from app.bot_requests.shared import (
    bot as requests_bot,
    init_database as init_requests_db,
    save_requests_to_db,
    load_requests_from_db,
    requests_list,
    match_address,
    clean_street_name,
    district_names,
    district_ids,
    district_phones,
    personnel_chats,
    user_states,
    chat_action_allowed
)
from app.bot_requests import handlers  # подключаем хендлеры бота заявок

# ====== Логирование ======
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ====== Flask ======
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-for-sessions-123456789')

# ====== Путь к токенам ======
BOT_TOKEN_REQUESTS = os.getenv("BOT_TOKEN_REQUESTS")
BOT_TOKEN_MAINTENANCE = os.getenv("BOT_TOKEN_MAINTENANCE")

RIGHTS_FILE = "chat_rights.json"
AUTHORIZED_USERS_FILE = "authorized_users.json"
authorized_users = {}

# ====== ИНИЦИАЛИЗАЦИЯ БАЗ ======
init_maintenance_db()  # создаёт maintenance.db для бота ТО
logger.info("maintenance.db created.")

init_requests_db()      # создаёт requests.db для бота заявок
load_requests_from_db() # загружаем заявки в память

# ====== Blueprints ======

from app.contacts.routes import contacts_html, contacts_api
from app.counterparties.routes import counterparty_html, counterparties_api
from app.contracts.routes import contract_html, contract_api

app.register_blueprint(contacts_html)
app.register_blueprint(contacts_api)
app.register_blueprint(counterparty_html)
app.register_blueprint(counterparties_api)
app.register_blueprint(contract_html)
app.register_blueprint(contract_api)

# Права нажатия (если нужно)
# action_rights = {"allow_chat_actions": True}


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
#chat_action_allowed = {"участок№1": True, "участок№2": True}
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

# ====== VAPID ключи для Web Push ======
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

# ====== Планировщик ======
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
        requests_bot.send_message(chat, "📋 <b>Невиконані заявки:</b>\n" + " \n".join(lines))

def sched_loop():
    #====== через 5 минут от текущего момента ==========
    #run_time = (datetime.now() + timedelta(minutes=1)).strftime("%H:%M")
    #print(f"⏰ Тестовое время запуска: {run_time}")
    #schedule.every().day.at(run_time).do(send_daily)

    #======= каждый день в 08:30 ===========
    schedule.every().day.at("08:30").do(send_daily)
    while True:
        schedule.run_pending()
        time.sleep(60)

# ====== Запуск ======
if __name__ == "__main__":
    threading.Thread(target=sched_loop, daemon=True).start()

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

    threading.Thread(target=start_requests_bot, daemon=True).start()
    threading.Thread(target=start_maintenance_bot, daemon=True).start()

    load_action_rights()
    app.run(host="0.0.0.0", port=5000)
