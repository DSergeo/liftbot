from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session
import sqlite3
import traceback
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

    # --- Работа только с counterparties и contacts_counterparties ---
    cursor.execute('''CREATE TABLE IF NOT EXISTS counterparties (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS contacts_counterparties (
        contact_id INTEGER NOT NULL,
        counterparty_id INTEGER NOT NULL,
        PRIMARY KEY (contact_id, counterparty_id),
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
        FOREIGN KEY (counterparty_id) REFERENCES counterparties(id) ON DELETE CASCADE
    )''')
    cursor.execute("DELETE FROM contacts_counterparties WHERE contact_id = ?", (contact_id,))
    for cp in attached_companies:
        # Если это id (число) — используем напрямую, если строка — ищем/создаём
        try:
            counterparty_id = int(cp)
        except (ValueError, TypeError):
            cursor.execute("SELECT id FROM counterparties WHERE name = ?", (cp,))
            row = cursor.fetchone()
            if row:
                counterparty_id = row[0]
            else:
                cursor.execute("INSERT INTO counterparties (name) VALUES (?)", (cp,))
                counterparty_id = cursor.lastrowid
        cursor.execute("INSERT OR IGNORE INTO contacts_counterparties (contact_id, counterparty_id) VALUES (?, ?)", (contact_id, counterparty_id))
    conn.commit()
    conn.close()
    return redirect(url_for("contacts_page"))

# Blueprint для API
contacts_api = Blueprint("contacts_api", __name__, url_prefix="/api/contacts")

@contacts_api.route("/", methods=["GET"])
def api_get_contacts():
    if "user_email" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM contacts")
        columns = [desc[0] for desc in cursor.description]
        contacts = [dict(zip(columns, row)) for row in cursor.fetchall()]
        print(f"[DEBUG] Загружено контактов: {len(contacts)}")
        cursor.execute('''
            SELECT cc.contact_id, c.id as counterparty_id, c.companyName as counterparty_name
            FROM contacts_counterparties cc
            JOIN counterparties c ON cc.counterparty_id = c.id
        ''')
        counterparty_links = cursor.fetchall()
        from collections import defaultdict
        contact_to_counterparties = defaultdict(list)
        for contact_id, counterparty_id, counterparty_name in counterparty_links:
            contact_to_counterparties[contact_id].append({"id": counterparty_id, "name": counterparty_name})
        for contact in contacts:
            contact["counterparties"] = contact_to_counterparties.get(contact["id"], [])
        conn.close()
        print(f"[DEBUG] Ответ contacts: {contacts}")
        return jsonify({"success": True, "contacts": contacts})
    except Exception as e:
        print("❌ Error loading contacts:", e)
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

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
    attached_companies = data.get("attachedCompanies", [])
    try:
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        print("[DEBUG] Сохраняем контакт:", data)
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
        print(f"[DEBUG] Новый contact_id: {contact_id}")
        cursor.execute('''CREATE TABLE IF NOT EXISTS counterparties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS contacts_counterparties (
            contact_id INTEGER NOT NULL,
            counterparty_id INTEGER NOT NULL,
            PRIMARY KEY (contact_id, counterparty_id),
            FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
            FOREIGN KEY (counterparty_id) REFERENCES counterparties(id) ON DELETE CASCADE
        )''')
        cursor.execute("DELETE FROM contacts_counterparties WHERE contact_id = ?", (contact_id,))
        print(f"[DEBUG] Привязка контрагентов: {attached_companies}")
        for cp in attached_companies:
            try:
                counterparty_id = int(cp)
            except (ValueError, TypeError):
                cursor.execute("SELECT id FROM counterparties WHERE name = ?", (cp,))
                row = cursor.fetchone()
                if row:
                    counterparty_id = row[0]
                else:
                    cursor.execute("INSERT INTO counterparties (name) VALUES (?)", (cp,))
                    counterparty_id = cursor.lastrowid
            print(f"[DEBUG] Привязываем contact_id={contact_id} к counterparty_id={counterparty_id}")
            cursor.execute("INSERT OR IGNORE INTO contacts_counterparties (contact_id, counterparty_id) VALUES (?, ?)", (contact_id, counterparty_id))
        conn.commit()
        conn.close()
        print("[DEBUG] Контакт успешно сохранён!")
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Error saving contact:", e)
        traceback.print_exc()
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

        # --- Работа с counterparties и contacts_counterparties ---
        cursor.execute('''CREATE TABLE IF NOT EXISTS counterparties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS contacts_counterparties (
            contact_id INTEGER NOT NULL,
            counterparty_id INTEGER NOT NULL,
            PRIMARY KEY (contact_id, counterparty_id),
            FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
            FOREIGN KEY (counterparty_id) REFERENCES counterparties(id) ON DELETE CASCADE
        )''')
        cursor.execute("DELETE FROM contacts_counterparties WHERE contact_id = ?", (contact_id,))
        for cp in attached_companies:
            try:
                counterparty_id = int(cp)
            except (ValueError, TypeError):
                cursor.execute("SELECT id FROM counterparties WHERE name = ?", (cp,))
                row = cursor.fetchone()
                if row:
                    counterparty_id = row[0]
                else:
                    cursor.execute("INSERT INTO counterparties (name) VALUES (?)", (cp,))
                    counterparty_id = cursor.lastrowid
            cursor.execute("INSERT OR IGNORE INTO contacts_counterparties (contact_id, counterparty_id) VALUES (?, ?)", (contact_id, counterparty_id))

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