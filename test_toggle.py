# test_toggle.py

# Імітуємо ваші змінні
district_ids = {
    "Заводський р-н": "участок№2",
    "Центральний р-н": "участок№2",
    "Інгульський р-н": "участок№2",
    "Корабельний р-н": "участок№1"
}

chat_action_allowed = {
    "участок№1": True,
    "участок№2": False  # ← тут заборонено
}

# Тестова заявка
test_request = {
    "district": "Центральний р-н"
}

# Імітація callback виклику
def simulate_button_press(r):
    section = district_ids.get(r["district"])
    if not chat_action_allowed.get(section, True):
        print(f"⛔️ Кнопки заборонені для {section}")
    else:
        print(f"✅ Кнопки дозволені для {section}")

simulate_button_press(test_request)
