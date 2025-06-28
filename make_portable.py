#!/usr/bin/env python3
"""
Скрипт для створення повністю переносимої версії проекту
"""

import os
import shutil
import requests
from pathlib import Path
import subprocess

def create_directories():
    """Створює необхідні директорії"""
    dirs = [
        'static/css',
        'static/js', 
        'static/fonts',
        'static/images',
        'uploads',
        'logs'
    ]
    
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
    print("✓ Створені необхідні директорії")

def download_external_resources():
    """Завантажує всі зовнішні ресурси локально"""
    resources = {
        'static/css/bootstrap.min.css': 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
        'static/css/fontawesome.min.css': 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
        'static/css/bootstrap-icons.css': 'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css',
        'static/js/bootstrap.bundle.min.js': 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
        'static/js/chart.min.js': 'https://cdn.jsdelivr.net/npm/chart.js@4.3.0/dist/chart.min.js',
        'static/js/xlsx.full.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js'
    }
    
    print("Завантаження зовнішніх ресурсів...")
    for local_path, url in resources.items():
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                f.write(response.content)
            print(f"✓ {local_path}")
        except Exception as e:
            print(f"✗ Помилка завантаження {url}: {e}")

def download_font_awesome_fonts():
    """Завантажує шрифти Font Awesome"""
    try:
        # Завантажуємо CSS і знаходимо посилання на шрифти
        css_response = requests.get('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css')
        css_content = css_response.text
        
        import re
        # Шукаємо URL шрифтів
        font_urls = re.findall(r'url\(([^)]+\.woff2?)\)', css_content)
        
        for font_url in font_urls:
            font_url = font_url.strip('"\'')
            if font_url.startswith('../'):
                font_url = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/' + font_url[3:]
            
            font_name = Path(font_url).name
            font_response = requests.get(font_url)
            
            with open(f'static/fonts/{font_name}', 'wb') as f:
                f.write(font_response.content)
        
        # Оновлюємо CSS для використання локальних шрифтів
        updated_css = css_content
        for font_url in font_urls:
            font_name = Path(font_url.strip('"\'').split('/')[-1]).name
            updated_css = updated_css.replace(font_url, f'../fonts/{font_name}')
        
        with open('static/css/fontawesome.min.css', 'w', encoding='utf-8') as f:
            f.write(updated_css)
            
        print("✓ Завантажені шрифти Font Awesome")
    except Exception as e:
        print(f"✗ Помилка завантаження шрифтів: {e}")

def create_portable_env():
    """Створює .env файл для переносимості"""
    env_content = """# Автоматично згенерований .env файл для переносимості
FLASK_SECRET_KEY=change-this-in-production-$(openssl rand -hex 16)
SESSION_SECRET=change-this-in-production-$(openssl rand -hex 16)
TELEGRAM_TOKEN=your-telegram-bot-token-here
DATABASE_URL=sqlite:///requests.db
FLASK_ENV=production
FLASK_DEBUG=False
PORT=5000
LOG_LEVEL=INFO
"""
    
    if not Path('.env').exists():
        with open('.env', 'w') as f:
            f.write(env_content)
        print("✓ Створений .env файл")
    else:
        print("✓ .env файл вже існує")

def generate_secrets():
    """Генерує безпечні секретні ключі"""
    try:
        import secrets
        secret_key = secrets.token_hex(32)
        session_secret = secrets.token_hex(32)
        
        # Оновлюємо .env файл
        env_path = Path('.env')
        if env_path.exists():
            content = env_path.read_text()
            content = content.replace('change-this-in-production-$(openssl rand -hex 16)', secret_key)
            content = content.replace('change-this-in-production-$(openssl rand -hex 16)', session_secret)
            env_path.write_text(content)
            print("✓ Згенеровані безпечні секретні ключі")
    except Exception as e:
        print(f"✗ Помилка генерації ключів: {e}")

def create_requirements_txt():
    """Створює requirements.txt файл"""
    requirements = """Flask==2.3.2
gunicorn==21.2.0
cryptography==41.0.3
email-validator==2.0.0
flask-login==0.6.2
flask-sqlalchemy==3.0.5
geopy==2.3.0
oauthlib==3.2.2
openpyxl==3.1.2
psycopg2-binary==2.9.7
pyjwt==2.8.0
pytelegrambotapi==4.12.0
python-dotenv==1.0.0
python-telegram-bot==20.4
pytz==2023.3
pywebpush==1.14.0
schedule==1.2.0
telebot==0.0.5
requests==2.31.0
"""
    
    with open('requirements_portable.txt', 'w') as f:
        f.write(requirements)
    print("✓ Створений requirements_portable.txt")

def create_run_script():
    """Створює скрипт запуску для різних систем"""
    
    # Скрипт для Linux/Ubuntu
    linux_script = """#!/bin/bash
# Скрипт запуску для Linux/Ubuntu

echo "Запуск системи управління ліфтами..."

# Перевірка віртуального середовища
if [ ! -d "venv" ]; then
    echo "Створення віртуального середовища..."
    python3 -m venv venv
fi

# Активація середовища
source venv/bin/activate

# Встановлення залежностей
echo "Встановлення залежностей..."
pip install -r requirements_portable.txt

# Перевірка .env файлу
if [ ! -f ".env" ]; then
    echo "Створення .env файлу..."
    cp .env.example .env
    echo "УВАГА: Налаштуйте .env файл перед продакшн використанням!"
fi

# Запуск додатку
echo "Запуск сервера на http://localhost:5000"
python main.py
"""

    # Скрипт для Windows
    windows_script = """@echo off
REM Скрипт запуску для Windows

echo Запуск системи управління ліфтами...

REM Перевірка віртуального середовища
if not exist "venv" (
    echo Створення віртуального середовища...
    python -m venv venv
)

REM Активація середовища
call venv\\Scripts\\activate

REM Встановлення залежностей
echo Встановлення залежностей...
pip install -r requirements_portable.txt

REM Перевірка .env файлу
if not exist ".env" (
    echo Створення .env файлу...
    copy .env.example .env
    echo УВАГА: Налаштуйте .env файл перед продакшн використанням!
)

REM Запуск додатку
echo Запуск сервера на http://localhost:5000
python main.py

pause
"""

    with open('run_linux.sh', 'w') as f:
        f.write(linux_script)
    
    with open('run_windows.bat', 'w') as f:
        f.write(windows_script)
    
    # Робимо Linux скрипт виконуваним
    os.chmod('run_linux.sh', 0o755)
    
    print("✓ Створені скрипти запуску для Linux та Windows")

def switch_to_offline_mode():
    """Переключає templates на офлайн режим"""
    layout_path = Path('templates/layout.html')
    layout_offline_path = Path('templates/layout_offline.html')
    
    if layout_offline_path.exists():
        # Створюємо резервну копію оригінального layout
        shutil.copy(layout_path, 'templates/layout_online.html')
        
        # Замінюємо на офлайн версію
        shutil.copy(layout_offline_path, layout_path)
        
        print("✓ Переключено на офлайн режим (оригінал збережений як layout_online.html)")
    else:
        print("✗ Файл layout_offline.html не знайдений")

def create_portable_archive():
    """Створює архів проекту для переносу"""
    print("Створення переносимого архіву...")
    
    # Файли які потрібно включити
    include_files = [
        'main.py',
        'config.py',
        'install_ubuntu.sh',
        'nginx.conf',
        '.env.example',
        'requirements_portable.txt',
        'run_linux.sh',
        'run_windows.bat',
        'README_UBUNTU.md',
        'static/',
        'templates/',
        'requests.db',
        'addresses.json',
        'map_ru_to_ua.json'
    ]
    
    # Створюємо архів
    try:
        import tarfile
        with tarfile.open('elevator_system_portable.tar.gz', 'w:gz') as tar:
            for item in include_files:
                if os.path.exists(item):
                    tar.add(item)
        print("✓ Створений архів elevator_system_portable.tar.gz")
    except Exception as e:
        print(f"✗ Помилка створення архіву: {e}")

def main():
    """Основна функція"""
    print("=== Створення переносимої версії системи ===\n")
    
    # Послідовність операцій
    create_directories()
    download_external_resources()
    download_font_awesome_fonts()
    create_portable_env()
    generate_secrets()
    create_requirements_txt()
    create_run_script()
    switch_to_offline_mode()
    
    print("\n=== Переносима версія готова! ===")
    print("\nДля використання на новому сервері:")
    print("1. Скопіюйте всі файли проекту")
    print("2. Запустіть: chmod +x run_linux.sh && ./run_linux.sh")
    print("3. Або: ./install_ubuntu.sh для системного встановлення")
    print("\nДля Windows: запустіть run_windows.bat")

if __name__ == '__main__':
    main()