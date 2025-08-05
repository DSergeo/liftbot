#!/usr/bin/env python3
"""
Тест функции удаления пользователей из чата
"""
import json
from types import SimpleNamespace

# Загружаем текущее состояние
def load_authorized_users():
    with open('authorized_users.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def save_authorized_users(data):
    with open('authorized_users.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# Симулируем обработчик удаления пользователя
def simulate_user_left(user_id, chat_id, section):
    print(f"🧪 ТЕСТ: Симуляция удаления пользователя {user_id} из чата {chat_id} (район: {section})")
    
    # Загружаем текущие данные
    authorized_users = load_authorized_users()
    
    print(f"📋 Состояние ДО удаления:")
    print(f"   {section}: {authorized_users.get(section, [])}")
    
    changed = False
    
    # Удаляем из authorized_users (структура со словарями)
    if section in authorized_users and isinstance(authorized_users[section], dict):
        authorized_list = authorized_users[section].get("authorized", [])
        if user_id in authorized_list:
            authorized_users[section]["authorized"].remove(user_id)
            print(f"✅ Удален пользователь {user_id} из authorized для {section}")
            changed = True
        
        # Удаляем из представителей района
        if authorized_users[section].get("representative") == user_id:
            authorized_users[section]["representative"] = None
            print(f"✅ Удален представитель {user_id} для {section}")
            changed = True
    
    if changed:
        save_authorized_users(authorized_users)
        print(f"💾 Файл сохранен")
        
        print(f"📋 Состояние ПОСЛЕ удаления:")
        print(f"   {section}: {authorized_users.get(section, [])}")
        
        return True
    else:
        print(f"❌ Пользователь {user_id} не был найден в авторизованных для {section}")
        return False

if __name__ == "__main__":
    print("🧪 Тестирование функции удаления пользователей из чата")
    print("=" * 50)
    
    # Тест 1: Удаление существующего пользователя
    result = simulate_user_left(123456789, -1001234567890, "участок№1")
    
    print("\n" + "=" * 50)
    print(f"🏆 Результат теста: {'✅ УСПЕШНО' if result else '❌ НЕУДАЧНО'}")