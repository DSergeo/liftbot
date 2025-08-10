# app/requests/services.py
import sqlite3
from datetime import datetime
from app.core.config import Config
from app.utils import timestamp_now

# in-memory list used by the app
requests_list = []

def init_database():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            district TEXT,
            address TEXT,
            entrance TEXT,
            issue TEXT,
            phone TEXT,
            timestamp TEXT,
            completed BOOLEAN DEFAULT 0,
            completed_time TEXT,
            processed_by TEXT,
            chat_msg_id TEXT,
            status TEXT DEFAULT 'pending',
            user_id INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def save_requests_to_db():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM requests')
    for r in requests_list:
        cursor.execute('''
            INSERT INTO requests (
                name, district, address, entrance, issue, phone,
                timestamp, completed, completed_time, processed_by,
                chat_msg_id, status, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            r.get("name", ""), r.get("district", ""), r.get("address", ""),
            r.get("entrance", ""), r.get("issue", ""), r.get("phone", ""),
            r.get("timestamp", ""), int(bool(r.get("completed", False))),
            r.get("completed_time", ""), r.get("processed_by", ""),
            str(r.get("chat_msg_id", "")), r.get("status", "pending"),
            int(r.get("user_id", 0))
        ))
    conn.commit()
    conn.close()

def load_requests_from_db():
    global requests_list
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM requests ORDER BY id')
        rows = cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        requests_list = []
        for row in rows:
            r = dict(zip(cols, row))
            r["completed"] = bool(r.get("completed"))
            if not r.get("status"):
                r["status"] = "pending"
            # optional: convert id to int etc.
            requests_list.append(r)
        print(f"Loaded {len(requests_list)} requests from DB")
    except Exception as e:
        print("DB load error:", e)
        init_database()
    finally:
        conn.close()
