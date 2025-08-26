# app/bot_maintenance/handlers.py
from app.bot_maintenance.shared import (
    bot, user_states, save_maintenance_log, maintenance_schedule, kyiv_tz,
    find_address_by_geo, get_entrances_for_building, schedule_key_candidates
)
from datetime import datetime, timedelta
import logging
import re
from io import BytesIO
from telebot import types
from PIL import Image
import pytesseract
import io
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

logger = logging.getLogger(__name__)

# ---------- Keyboards ----------
def location_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("📍 Надіслати геолокацію", request_location=True))
    return kb

def entrances_keyboard(entrances: list[str]) -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=5, one_time_keyboard=True)
    for e in entrances:
        kb.add(e)
    kb.add("Інший")
    return kb

# ---------- Helpers ----------
DATE_RE = re.compile(
    r'(?P<d>\b\d{1,2})[.\-/](?P<m>\d{1,2})[.\-/](?P<y>\d{2,4})\b'
)

def ocr_date_from_image(img: Image.Image) -> datetime | None:
    """Пытаемся вытащить дату с фото (укр/рус)."""
    try:
        text = pytesseract.image_to_string(img, lang="ukr+rus")
    except Exception:
        # запасной вариант без указания языка
        text = pytesseract.image_to_string(img)
    # Ищем первую подходящую дату
    for m in DATE_RE.finditer(text):
        d = int(m.group("d"))
        mm = int(m.group("m"))
        yy = int(m.group("y"))
        if yy < 100:  # например 25 -> 2025 (грубое правило)
            yy = 2000 + yy
        try:
            return datetime(yy, mm, d)
        except ValueError:
            continue
    return None

def allowed_by_schedule(street: str, building: str, dt: datetime) -> tuple[bool, str]:
    """
    Ищем даты в графике по ключам, начинающимся на '<street> <building>'.
    Разрешаем, если найдена дата в пределах ±4 днів.
    """
    keys = schedule_key_candidates(street, building)
    if not keys:
        return False, "❌ В графіку немає записів для цього будинку."

    # Собираем все даты по найденным ключам
    planned: list[datetime] = []
    for k in keys:
        for ds in maintenance_schedule.get(k, []):
            try:
                planned.append(datetime.strptime(ds, "%Y-%m-%d"))
            except Exception:
                pass

    if not planned:
        return False, "❌ В графіку немає дат для цього будинку."

    for p in planned:
        if abs((dt - p).days) <= 4:
            return True, ""

    return False, "❌ Дата ТО не відповідає графіку (±4 дні)."

# ---------- Handlers ----------
@bot.message_handler(commands=["start"])
def start(m):
    chat_id = m.chat.id
    user_states[chat_id] = {"step": "wait_location"}
    bot.send_message(
        chat_id,
        "👋 Вітаю! Надішліть геолокацію через скріпку або натисніть кнопку нижче.",
        reply_markup=location_keyboard()
    )

# Если пользователь пишет любой текст, а состояния ещё нет — просим геолокацію
@bot.message_handler(func=lambda msg: user_states.get(msg.chat.id, {}).get("step") is None, content_types=["text"])
def first_text(m):
    chat_id = m.chat.id
    user_states[chat_id] = {"step": "wait_location"}
    bot.send_message(
        chat_id,
        "📍 Надішліть геолокацію через скріпку (або натисніть кнопку):",
        reply_markup=location_keyboard()
    )

# Принимаем геолокацию всегда (без жёсткой привязки к шагу)
@bot.message_handler(content_types=["location"])
def handle_location(msg):
    chat_id = msg.chat.id
    state = user_states.setdefault(chat_id, {})
    lat = msg.location.latitude
    lon = msg.location.longitude

    match = find_address_by_geo(lat, lon)
    if not match:
        # Не попали ни в одну активную точку/радиус
        state["step"] = "wait_location"
        bot.send_message(
            chat_id,
            "❌ Локацію не знайдено в базі (радіус 10 м). Надішліть геолокацію ще раз.",
            reply_markup=location_keyboard()
        )
        return

    district, street, building, entrance_detected = match
    all_entrances = get_entrances_for_building(street, building)

    # Запоминаем контекст дома
    state.update({
        "step": "wait_entrance",
        "district": district,
        "street": street,
        "building": building,
        "suggested_entrance": entrance_detected,
        "entrances": all_entrances
    })

    # Сообщаем, что адрес найден; просим выбрать/ввести під’їзд
    text = (
        f"🏙️ Район: <b>{district}</b>\n"
        f"📫 Адреса: <b>{street} {building}</b>\n"
        f"🚪 Під'їзд поблизу: <b>{entrance_detected}</b>\n\n"
        "Оберіть під'їзд або натисніть «Інший» і введіть номер самостійно."
    )
    kb = entrances_keyboard(all_entrances) if all_entrances else types.ReplyKeyboardRemove()
    bot.send_message(chat_id, text, reply_markup=kb)

# Обработка выбора під’їзду (кнопкой или вручную)
@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step") == "wait_entrance", content_types=["text"])
def handle_entrance(m):
    chat_id = m.chat.id
    state = user_states.setdefault(chat_id, {})
    txt = (m.text or "").strip()

    if txt == "Інший":
        bot.send_message(chat_id, "Введіть номер під'їзду цифрою (наприклад: 2).")
        state["step"] = "enter_entrance_manual"
        return

    # Если выбрали из клавиатуры
    entrances = state.get("entrances", [])
    if txt in entrances:
        state["entrance"] = txt
        state["step"] = "wait_photo"
        bot.send_message(
            chat_id,
            "📷 Надішліть фото журналу ТО. Підписувати не потрібно — бот зчитає дату, роботи та підпис.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        return

    # Если руками ввели цифру
    if txt.isdigit():
        state["entrance"] = txt
        state["step"] = "wait_photo"
        bot.send_message(
            chat_id,
            "📷 Надішліть фото журналу ТО. Підписувати не потрібно — бот зчитає дату, роботи та підпис.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        return

    bot.send_message(chat_id, "Будь ласка, оберіть під'їзд з кнопок або введіть номер (1-99).")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step") == "enter_entrance_manual", content_types=["text"])
def handle_entrance_manual(m):
    chat_id = m.chat.id
    state = user_states.setdefault(chat_id, {})
    txt = (m.text or "").strip()
    if not txt.isdigit():
        bot.send_message(chat_id, "Введіть номер під'їзду цифрою, наприклад 3.")
        return
    state["entrance"] = txt
    state["step"] = "wait_photo"
    bot.send_message(
        chat_id,
        "📷 Надішліть фото журналу ТО. Підписувати не потрібно — бот зчитає дату, роботи та підпис.",
        reply_markup=types.ReplyKeyboardRemove()
    )

# Принимаем ФОТО — основной этап фиксации ТО
@bot.message_handler(content_types=["photo"])
def handle_photo(msg):
    chat_id = msg.chat.id
    state = user_states.get(chat_id, {})
    if state.get("step") != "wait_photo":
        # Если фото пришло не по сценарию — мягкий намёк
        bot.send_message(chat_id, "Спочатку надішліть геолокацію, оберіть під'їзд і лише потім фото.")
        return

    # Скачиваем фото в память
    try:
        file_id = msg.photo[-1].file_id
        info = bot.get_file(file_id)
        raw = bot.download_file(info.file_path)
        img = Image.open(BytesIO(raw))
    except Exception:
        logger.exception("Failed to download/open photo")
        bot.send_message(chat_id, "❌ Не вдалося отримати фото. Спробуйте ще раз.")
        return

    # OCR: ищем дату
    date_dt = ocr_date_from_image(img)
    if not date_dt:
        bot.send_message(chat_id, "❌ Не вдалося зчитати дату з фото. Надішліть більш чітке фото.")
        return

    # Проверка по графику (±4 дні)
    street = state.get("street", "")
    building = state.get("building", "")
    ok, reason = allowed_by_schedule(street, building, date_dt)
    if not ok:
        bot.send_message(chat_id, reason or "❌ Дата не відповідає графіку.")
        return

    # Сохраняем лог
    mechanic_name = msg.from_user.full_name
    full_address = f"{street} {building}"
    entrance = state.get("entrance", "")
    log_entry = {
        "mechanic_name": mechanic_name,
        "district": state.get("district", ""),
        "address": full_address,
        "entrance": entrance,
        "date": date_dt.strftime("%Y-%m-%d"),
        "photo_file_id": msg.photo[-1].file_id,
        "notes": "",  # при необходимости можно дополнять OCR-текстом
        "verified": True,
        "created_at": datetime.now(kyiv_tz).isoformat()
    }
    save_maintenance_log(log_entry)

    # Готово
    bot.send_message(
        chat_id,
        f"✅ ТО за адресою <b>{full_address}</b>, під'їзд <b>{entrance}</b> зафіксовано на дату <b>{date_dt.strftime('%d.%m.%Y')}</b>."
    )

    # Сброс состояния с возможностью сразу повторить для другого під’їзду
    user_states[chat_id] = {"step": "wait_location"}
    bot.send_message(
        chat_id,
        "Якщо потрібно зафіксувати ще — надішліть нову геолокацію.",
        reply_markup=location_keyboard()
    )

# На всякий случай: если прислали текст, когда бот ждёт фото — подскажем
@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step") == "wait_photo", content_types=["text"])
def remind_photo(m):
    bot.send_message(m.chat.id, "Будь ласка, надішліть фото журналу ТО.")
