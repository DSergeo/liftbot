import json

# Русско-украинский словарь (можно расширять)
ru_to_ua_translations = {
    "океановская": "вул. Океанівська",
    "рыбная": "вул. Рибна",
    "озерная": "вул. Озерна",
    "озёрная": "вул. Озерна",
    "богоявленский": "пр. Богоявленський",
    "корабелів": "пр. Корабелів",
    "боговленский": "пр. Богоявленський",
    # Добавь сюда другие при необходимости
}

def generate_partial_keys(street_name):
    street_name = street_name.lower()
    words = street_name.split()
    keys = set()
    keys.add(street_name)
    for w in words:
        if len(w) >= 3:
            keys.add(w[:3])
            keys.add(w[1:4] if len(w) > 3 else w[1:])
        else:
            keys.add(w)
        keys.add(w)
    if len(words) > 1:
        keys.add(" ".join(words))
        for i in range(len(words)):
            part_words = words[:i+1]
            partial = " ".join([w[:3] for w in part_words])
            keys.add(partial)
            first_word = part_words[0]
            if len(first_word) > 1:
                first_word_skip = first_word[1:4] if len(first_word) > 3 else first_word[1:]
                keys.add(" ".join([first_word_skip] + part_words[1:]))
    return keys

def main():
    with open("addresses.json", encoding="utf-8") as f:
        address_data = json.load(f)

    map_ru_to_ua = {}

    for district in address_data:
        for street in address_data[district]:
            street_lower = street.lower()
            map_ru_to_ua[street_lower] = street
            partial_keys = generate_partial_keys(street_lower)
            for key in partial_keys:
                if key not in map_ru_to_ua:
                    map_ru_to_ua[key] = street

    # Добавим вручную русские названия
    for ru, ua in ru_to_ua_translations.items():
        map_ru_to_ua[ru.lower()] = ua
        for key in generate_partial_keys(ru.lower()):
            if key not in map_ru_to_ua:
                map_ru_to_ua[key] = ua

    # Сохраняем
    with open("map_ru_to_ua.json", "w", encoding="utf-8") as f:
        json.dump(map_ru_to_ua, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
