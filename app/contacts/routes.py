from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session
import sqlite3
from app.utils import get_company_db_path

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
    conn.close()
    return render_template("contacts.html", contacts=contacts)

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
    attached_companies = request.form.getlist("attachedCompanies")
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
    contact_id = cursor.lastrowid

    # --- Работа с companies и contact_companies ---
    cursor.execute('''CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS contact_companies (
        contact_id INTEGER NOT NULL,
        company_id INTEGER NOT NULL,
        PRIMARY KEY (contact_id, company_id),
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
        FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
    )''')
    company_ids = []
    for company_name in attached_companies:
        cursor.execute("SELECT id FROM companies WHERE name = ?", (company_name,))
        row = cursor.fetchone()
        if row:
            company_id = row[0]
        else:
            cursor.execute("INSERT INTO companies (name) VALUES (?)", (company_name,))
            company_id = cursor.lastrowid
        company_ids.append(company_id)
    cursor.execute("DELETE FROM contact_companies WHERE contact_id = ?", (contact_id,))
    for company_id in company_ids:
        cursor.execute("INSERT OR IGNORE INTO contact_companies (contact_id, company_id) VALUES (?, ?)", (contact_id, company_id))
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
    # Получаем все контакты
    cursor.execute("SELECT * FROM contacts")
    columns = [desc[0] for desc in cursor.description]
    contacts = [dict(zip(columns, row)) for row in cursor.fetchall()]

    # Получаем связи контакт-компания и названия компаний
    cursor.execute('''
        SELECT cc.contact_id, c.id as company_id, c.name as company_name
        FROM contact_companies cc
        JOIN companies c ON cc.company_id = c.id
    ''')
    company_links = cursor.fetchall()
    # Формируем словарь: contact_id -> [{id, name}, ...]
    from collections import defaultdict
    contact_to_companies = defaultdict(list)
    for contact_id, company_id, company_name in company_links:
        contact_to_companies[contact_id].append({"id": company_id, "name": company_name})

    # Добавляем массив counterparties к каждому контакту
    for contact in contacts:
        contact["counterparties"] = contact_to_companies.get(contact["id"], [])

    conn.close()
    return jsonify({"success": True, "contacts": contacts})

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
    attached_companies = data.get("attachedCompanies", [])
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

        # --- Работа с companies и contact_companies ---
        cursor.execute('''CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS contact_companies (
            contact_id INTEGER NOT NULL,
            company_id INTEGER NOT NULL,
            PRIMARY KEY (contact_id, company_id),
            FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        )''')
        company_ids = []
        for company_name in attached_companies:
            cursor.execute("SELECT id FROM companies WHERE name = ?", (company_name,))
            row = cursor.fetchone()
            if row:
                company_id = row[0]
            else:
                cursor.execute("INSERT INTO companies (name) VALUES (?)", (company_name,))
                company_id = cursor.lastrowid
            company_ids.append(company_id)
        cursor.execute("DELETE FROM contact_companies WHERE contact_id = ?", (contact_id,))
        for company_id in company_ids:
            cursor.execute("INSERT OR IGNORE INTO contact_companies (contact_id, company_id) VALUES (?, ?)", (contact_id, company_id))

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