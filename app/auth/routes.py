# app/auth/routes.py
from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
import json
from datetime import datetime, timedelta
from app.core.config import Config
import os

auth_bp = Blueprint("auth", __name__, url_prefix="")

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        action = request.form.get("action", "login")
        if action == "login":
            email = request.form.get("email")
            password = request.form.get("password")
            remember = request.form.get("remember")
            try:
                with open(Config.USERS_JSON, "r", encoding="utf-8") as f:
                    users_db = json.load(f)
            except FileNotFoundError:
                users_db = {}
            user = users_db.get(email)
            if not user or user.get("password") != password:
                return render_template("login.html", error="Невірний email або пароль")
            if not user.get("profile_completed", False):
                session["temp_user_email"] = email
                return redirect(url_for("auth.profile_setup"))
            session["user_email"] = email
            session["user_name"] = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            session["user_role"] = user.get("role", "operator")
            session["phone"] = user.get("phone", "")
            session["role"] = user.get("role", "operator")
            if user.get("avatar"):
                session["user_avatar"] = user.get("avatar")
            if remember:
                session.permanent = True
            return redirect(url_for("auth.index"))
    return render_template("login.html")

@auth_bp.route("/register", methods=["POST"])
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
    try:
        with open(Config.USERS_JSON, "r", encoding="utf-8") as f:
            users_db = json.load(f)
    except FileNotFoundError:
        users_db = {}
    if email in users_db:
        return render_template("login.html", error="Користувач з таким email вже існує")
    users_db[email] = {
        "email": email,
        "phone": phone,
        "password": password,
        "created_at": datetime.now().isoformat(),
        "profile_completed": False
    }
    with open(Config.USERS_JSON, "w", encoding="utf-8") as f:
        json.dump(users_db, f, ensure_ascii=False, indent=2)
    session["temp_user_email"] = email
    return redirect(url_for("auth.profile_setup"))

@auth_bp.route("/profile_setup", methods=["GET", "POST"])
def profile_setup():
    if "temp_user_email" not in session:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        email = session["temp_user_email"]
        try:
            with open(Config.USERS_JSON, "r", encoding="utf-8") as f:
                users_db = json.load(f)
        except FileNotFoundError:
            return redirect(url_for("auth.login"))
        if email not in users_db:
            return redirect(url_for("auth.login"))
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
        avatar = request.files.get("avatar")
        if avatar and avatar.filename:
            upload_dir = os.path.join("static", "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            avatar_filename = f"avatar_{email.replace('@','_').replace('.','_')}.jpg"
            avatar.save(os.path.join(upload_dir, avatar_filename))
            users_db[email]["avatar"] = f"uploads/{avatar_filename}"
        with open(Config.USERS_JSON, "w", encoding="utf-8") as f:
            json.dump(users_db, f, ensure_ascii=False, indent=2)
        session.pop("temp_user_email", None)
        session["user_email"] = email
        session["user_name"] = f"{users_db[email]['first_name']} {users_db[email]['last_name']}"
        session["user_role"] = users_db[email]["role"]
        session["phone"] = users_db[email].get("phone", "")
        session["role"] = users_db[email]["role"]
        return redirect(url_for("auth.index"))
    return render_template("profile_setup.html")

@auth_bp.route("/")
def index():
    if "user_email" not in session:
        session.clear()
        return redirect(url_for("auth.login"))
    if "selected_company" not in session:
        return redirect(url_for("auth.select_company"))
    if "user_avatar" not in session:
        session["user_avatar"] = f"https://via.placeholder.com/30x30/6c757d/ffffff?text={session.get('user_name','U')[0]}"
    return render_template("index.html")

@auth_bp.route("/select-company", methods=["GET", "POST"])
def select_company():
    if "user_email" not in session:
        return redirect(url_for("auth.login"))
    try:
        with open(Config.COMPANY_SETTINGS_JSON, "r", encoding="utf-8") as f:
            companies = json.load(f)
    except FileNotFoundError:
        companies = {
            "1": {"name": "ТОВ 'Ліфт Сервіс'", "vat_status": False, "services": "ОСББ та УК без ПДВ"},
            "2": {"name": "ТОВ 'Ліфт Сервіс Плюс'", "vat_status": True, "services": "ЖЕКи та УК з ПДВ"}
        }
    if request.method == "POST":
        company_id = request.form.get("company_id")
        if company_id in companies:
            company_data = companies.get(company_id, {})
            session["selected_company"] = company_id
            session["company_name"] = company_data.get("name", "")
            session["company_vat_status"] = company_data.get("vat_status", False)
            session["company_services"] = company_data.get("services", "")
            return redirect(url_for("auth.index"))
    return render_template("select_company.html", companies=companies)

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
