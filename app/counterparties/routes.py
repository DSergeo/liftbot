from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session
import sqlite3
from app.utils import get_company_db_path

# Blueprint для HTML-страницы
counterparty_html = Blueprint("counterparty_html", __name__)

@counterparty_html.route("/counterparty")
def counterparty_page():
    if "user_email" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect(get_company_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM counterparties")
    columns = [desc[0] for desc in cursor.description]
    counterparties = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return render_template("counterparty.html", counterparties=counterparties)

@counterparty_html.route("/counterparty/save", methods=["POST"])
def save_counterparty_html():
    if "user_email" not in session:
        return redirect(url_for("login"))
    data = request.form
    fields = [
    "companyName", "edrpou", "iban", "bank", "mfo", "director", "accountant",
    "address", "phone", "email", "vatNumber", "taxNumber", "certificateNumber",
    "certificateDate", "legalForm", "customerType",
    "legalAddress", "city", "region", "postalCode", "website", "industry", "description"
]
    conn = sqlite3.connect(get_company_db_path())
    cursor = conn.cursor()
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS counterparties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {", ".join([f + " TEXT" for f in fields])}
        )
    ''')
    cursor.execute(f'''
        INSERT INTO counterparties ({", ".join(fields)})
        VALUES ({", ".join(["?" for _ in fields])})
    ''', tuple(data.get(f, "") for f in fields))
    conn.commit()
    conn.close()
    return redirect(url_for("counterparty_page"))

# Blueprint для API
counterparties_api = Blueprint("counterparties_api", __name__, url_prefix="/api/counterparties")

@counterparties_api.route("/", methods=["GET"])
def api_get_counterparties():
    if "user_email" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    conn = sqlite3.connect(get_company_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM counterparties")
    columns = [desc[0] for desc in cursor.description]
    data = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"success": True, "counterparties": data})

@counterparties_api.route("/", methods=["POST"])
def api_save_counterparty():
    if "user_email" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.get_json()
    fields = [
    "companyName", "edrpou", "iban", "bank", "mfo", "director", "accountant",
    "address", "phone", "email", "vatNumber", "taxNumber", "certificateNumber",
    "certificateDate", "legalForm", "customerType",
    "legalAddress", "city", "region", "postalCode", "website", "industry", "description"
]
    try:
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS counterparties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {", ".join([f + " TEXT" for f in fields])}
            )
        ''')
        cursor.execute(f'''
            INSERT INTO counterparties ({", ".join(fields)})
            VALUES ({", ".join(["?" for _ in fields])})
        ''', tuple(data.get(f, "") for f in fields))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Error saving counterparty:", e)
        return jsonify({"success": False, "error": str(e)}), 500

@counterparties_api.route("/<int:counterparty_id>", methods=["PUT"])
def api_update_counterparty(counterparty_id):
    if "user_email" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.get_json()
    fields = [
    "companyName", "edrpou", "iban", "bank", "mfo", "director", "accountant",
    "address", "phone", "email", "vatNumber", "taxNumber", "certificateNumber",
    "certificateDate", "legalForm", "customerType",
    "legalAddress", "city", "region", "postalCode", "website", "industry", "description"
]
    try:
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        updates = ", ".join([f"{field} = ?" for field in fields])
        values = [data.get(f, "") for f in fields]
        values.append(counterparty_id)
        cursor.execute(f'''
            UPDATE counterparties
            SET {updates}
            WHERE id = ?
        ''', values)
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Error updating counterparty:", e)
        return jsonify({"success": False, "error": str(e)}), 500

@counterparties_api.route("/<int:counterparty_id>", methods=["DELETE"])
def api_delete_counterparty(counterparty_id):
    if "user_email" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        cursor.execute("DELETE FROM counterparties WHERE id = ?", (counterparty_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Error deleting counterparty:", e)
        return jsonify({"success": False, "error": str(e)}), 500