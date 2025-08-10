# app/bot_requests/shared.py
import os
import json
import pytz
from datetime import datetime, timedelta
from app.core.config import Config
from app.utils import load_json, save_json

# Globals used by bot_requests
user_states = {}
# requests_list is imported from app.requests.services to avoid duplication

AUTHORIZED_USERS_FILE = Config.AUTHORIZED_USERS_FILE
SUBS_FILE = Config.SUBS_FILE
RIGHTS_FILE = Config.RIGHTS_FILE
ADDRESSES_FILE = Config.ADDRESSES_FILE
MAP_RU_TO_UA_FILE = Config.MAP_RU_TO_UA

authorized_users = load_json(AUTHORIZED_USERS_FILE, {})
subscriptions = load_json(SUBS_FILE, [])
chat_action_allowed = load_json(RIGHTS_FILE, {"участок№1": True, "участок№2": True})

# Load addresses and mapping
address_data = load_json(ADDRESSES_FILE, {})
map_ru_to_ua = load_json(MAP_RU_TO_UA_FILE, {})

# Districts (as in monolith)
districts = [
    ("Заводський р-н",  "участок№2", ["+380683038651", "+380663038652"]),
    ("Центральний р-н", "участок№2", ["+380683038651", "+380663038652"]),
    ("Інгульський р-н", "участок№2", ["+380683038651", "+380663038652"]),
    ("Корабельний р-н", "участок№1", ["+380683038602", "+380503038602"]),
]
district_names = [d[0] for d in districts]
district_ids = {d[0]: d[1] for d in districts}
district_phones = {d[0]: d[2] for d in districts}
personnel_chats = {"участок№1": -1002647024429, "участок№2": -1002530162702}  # keep your real ids

kyiv_tz = pytz.timezone("Europe/Kyiv")

# Helpers
def save_authorized_users():
    save_json(AUTHORIZED_USERS_FILE, authorized_users)
    print("Saved authorized_users.json")

def save_subscriptions():
    save_json(SUBS_FILE, subscriptions)
    print("Saved subscriptions.json")

def save_action_rights():
    save_json(RIGHTS_FILE, chat_action_allowed)
    print("Saved chat_action_rights.json")
