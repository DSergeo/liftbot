import openpyxl
import json

# путь к Excel
excel_file = "addresses.xlsx"
# путь к JSON
json_file = "addresses.json"

wb = openpyxl.load_workbook(excel_file)
sheet = wb.active

addresses = {}

for row in sheet.iter_rows(min_row=2, values_only=True):  # пропускаем заголовки
    district, street_full, coords = row
    if not district or not street_full or not coords:
        continue

    try:
        # street_full: "вул. Гліба Бабіча 14_1"
        parts = street_full.split()
        street_name = " ".join(parts[:-1])  # "вул. Гліба Бабіча"
        house_part = parts[-1]              # "14_1"

        if "_" not in house_part:
            continue  # пропускаем если нет подъезда

        house, entrance = house_part.split("_")  # "14", "1"

        lat_str, lon_str = coords.split(",")
        lat, lon = float(lat_str.strip()), float(lon_str.strip())

        # создаем структуру
        addresses.setdefault(district, {})
        addresses[district].setdefault(street_name, {})
        addresses[district][street_name].setdefault(house, {})
        addresses[district][street_name][house][entrance] = {
            "lat": lat,
            "lon": lon,
            "radius": 10,
            "active": True  # 👈 по умолчанию все включены
        }

    except Exception as e:
        print(f"⚠️ Ошибка при обработке строки {street_full}: {e}")

# сохраняем в JSON
with open(json_file, "w", encoding="utf-8") as f:
    json.dump(addresses, f, ensure_ascii=False, indent=2)

print(f"✅ Готово! Сохранено в {json_file}")
