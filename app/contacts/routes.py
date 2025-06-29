from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session
import sqlite3
from app.utils import get_company_db_path

def ensure_company_field_in_contacts():
    conn = sqlite3.connect('elestek_lift.db')
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(contacts)")
    columns = [row[1] for row in cursor.fetchall()]
    if "company" not in columns:
        cursor.execute("ALTER TABLE contacts ADD COLUMN company TEXT")
        conn.commit()
        print("✅ Добавлено поле company в таблицу contacts")
    conn.close()

# Вызовите эту функцию при старте приложения:
ensure_company_field_in_contacts()

# Blueprint для HTML-страницы
contacts_html = Blueprint("contacts_html", __name__)

@contacts_html.route("/contacts")
def contacts_page():
    if "user_email" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect(get_company_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contacts")
    columns = [desc[0] for desc in cursor.description]
    contacts = [dict(zip(columns, row)) for row in cursor.fetchall()]
    # Загрузить список компаний (контрагентов)
    cursor.execute("SELECT companyName FROM counterparties")
    companies = [row[0] for row in cursor.fetchall()]
    conn.close()
    return render_template("contacts.html", contacts=contacts, companies=companies)

@contacts_html.route("/contacts/save", methods=["POST"])
def save_contact_html():
    if "user_email" not in session:
        return redirect(url_for("login"))
    data = request.form
    fields = [
        "firstName", "lastName", "middleName", "position", "department",
        "phone", "mobile", "email", "website", "skype",
        "company", "industry", "contactType",
        "city", "street", "postalCode",
        "status", "description"
    ]
    conn = sqlite3.connect(get_company_db_path())
    cursor = conn.cursor()
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {", ".join([f + " TEXT" for f in fields])}
        )
    ''')
    cursor.execute(f'''
        INSERT INTO contacts ({", ".join(fields)})
        VALUES ({", ".join(["?"] * len(fields))})
    ''', tuple(data.get(f, "") for f in fields))
    conn.commit()
    conn.close()
    return redirect(url_for("contacts_page"))

# Blueprint для API
contacts_api = Blueprint("contacts_api", __name__, url_prefix="/api/contacts")

@contacts_api.route("/", methods=["GET"])
def api_get_contacts():
    if "user_email" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    conn = sqlite3.connect(get_company_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contacts")
    columns = [desc[0] for desc in cursor.description]
    data = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"success": True, "contacts": data})

@contacts_api.route("/", methods=["POST"])
def api_save_contact():
    if "user_email" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.get_json()
    fields = [
        "firstName", "lastName", "middleName", "position", "department",
        "phone", "mobile", "email", "website", "skype",
        "company", "industry", "contactType",
        "city", "street", "postalCode",
        "status", "description"
    ]
    try:
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {", ".join([f + " TEXT" for f in fields])}
            )
        ''')
        cursor.execute(f'''
            INSERT INTO contacts ({", ".join(fields)})
            VALUES ({", ".join(["?"] * len(fields))})
        ''', tuple(data.get(f, "") for f in fields))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Error saving contact:", e)
        return jsonify({"success": False, "error": str(e)}), 500

@contacts_api.route("/<int:contact_id>", methods=["PUT"])
def api_update_contact(contact_id):
    if "user_email" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.get_json()
    fields = [
        "firstName", "lastName", "middleName", "position", "department",
        "phone", "mobile", "email", "website", "skype",
        "company", "industry", "contactType",
        "city", "street", "postalCode",
        "status", "description"
    ]
    try:
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        updates = ", ".join([f"{field} = ?" for field in fields])
        values = [data.get(f, "") for f in fields]
        values.append(contact_id)
        cursor.execute(f'''
            UPDATE contacts
            SET {updates}
            WHERE id = ?
        ''', values)
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Error updating contact:", e)
        return jsonify({"success": False, "error": str(e)}), 500

@contacts_api.route("/<int:contact_id>", methods=["DELETE"])
def api_delete_contact(contact_id):
    if "user_email" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        cursor.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Error deleting contact:", e)
        return jsonify({"success": False, "error": str(e)}), 500

