@app.route("/contacts")
def contacts():
    if "user_email" not in session:
        return redirect(url_for("login"))
    return render_template("contacts.html")

@app.route("/contacts/save", methods=["POST"])
def save_contact():
    if "user_email" not in session:
        return redirect(url_for("login"))

    data = request.form  # або request.get_json() якщо буде API

    conn = sqlite3.connect(get_company_db_path())
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firstName TEXT,
            lastName TEXT,
            middleName TEXT,
            position TEXT,
            department TEXT,
            phone TEXT,
            mobile TEXT,
            email TEXT,
            website TEXT,
            skype TEXT,
            company TEXT,
            industry TEXT,
            contactType TEXT,
            city TEXT,
            street TEXT,
            postalCode TEXT,
            status TEXT,
            description TEXT
        )
    ''')

    cursor.execute('''
        INSERT INTO contacts (
            firstName, lastName, middleName, position, department,
            phone, mobile, email, website, skype,
            company, industry, contactType,
            city, street, postalCode, status, description
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get("firstName"),
        data.get("lastName"),
        data.get("middleName"),
        data.get("position"),
        data.get("department"),
        data.get("phone"),
        data.get("mobile"),
        data.get("email"),
        data.get("website"),
        data.get("skype"),
        data.get("company"),
        data.get("industry"),
        data.get("contactType"),
        data.get("city"),
        data.get("street"),
        data.get("postalCode"),
        data.get("status"),
        data.get("description")
    ))

    conn.commit()
    conn.close()
    return redirect(url_for("contacts"))
 
@app.route("/api/contacts", methods=["GET"])
def get_contacts():
    if "user_email" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    try:
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM contacts")
        columns = [desc[0] for desc in cursor.description]
        contacts = [dict(zip(columns, row)) for row in cursor.fetchall()]

        conn.close()
        return jsonify({"success": True, "contacts": contacts})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500 

@app.route("/api/contacts", methods=["POST"])
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
        conn = sqlite3.connect(get_company_db_path())  # Повертає правильну базу
        cursor = conn.cursor()

        cursor.execute(f"""
            INSERT INTO contacts ({", ".join(fields)})
            VALUES ({", ".join(["?"] * len(fields))})
        """, tuple(data.get(f, "") for f in fields))

        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/contacts/<int:contact_id>", methods=["PUT"])
def update_contact(contact_id):
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

        set_clause = ", ".join([f"{f} = ?" for f in fields])
        values = [data.get(f, "") for f in fields]
        values.append(contact_id)

        cursor.execute(f"""
            UPDATE contacts SET {set_clause} WHERE id = ?
        """, tuple(values))

        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/contacts/<int:contact_id>", methods=["DELETE"])
def delete_contact(contact_id):
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
        return jsonify({"success": False, "error": str(e)}), 500