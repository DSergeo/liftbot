import os
from pathlib import Path

# Базовий шлях проекту (автоматично визначається)
BASE_DIR = Path(__file__).parent.absolute()

class Config:
    """Конфігурація додатку для переносимості між різними системами"""
    
    # Секретні ключі
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or os.environ.get('SESSION_SECRET') or 'fallback-key-change-in-production'
    
    # База даних (SQLite для переносимості)
    DATABASE_PATH = BASE_DIR / 'requests.db'
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DATABASE_PATH}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Telegram Bot
    TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
    
    # Статичні файли
    STATIC_FOLDER = BASE_DIR / 'static'
    TEMPLATES_FOLDER = BASE_DIR / 'templates'
    
    # Логи
    LOG_FILE = BASE_DIR / 'flask.log'
    
    # Uploads
    UPLOAD_FOLDER = BASE_DIR / 'uploads'
    
    # JSON файли даних
    DATA_FILES = {
        'addresses': BASE_DIR / 'addresses.json',
        'authorized_users': BASE_DIR / 'authorized_users.json',
        'subscriptions': BASE_DIR / 'subscriptions.json',
        'users': BASE_DIR / 'users.json',
        'chat_rights': BASE_DIR / 'chat_rights.json',
        'district_representatives': BASE_DIR / 'district_representatives.json',
        'company_settings': BASE_DIR / 'company_settings.json',
        'not_working_requests': BASE_DIR / 'not_working_requests.json',
        'map_ru_to_ua': BASE_DIR / 'map_ru_to_ua.json',
        'auth_sessions': BASE_DIR / 'auth_sessions.json'
    }
    
    @classmethod
    def init_app(cls, app):
        """Ініціалізація додатку з конфігурацією"""
        # Створення необхідних директорій
        cls.UPLOAD_FOLDER.mkdir(exist_ok=True)
        
        # Створення порожніх JSON файлів якщо їх немає
        for file_path in cls.DATA_FILES.values():
            if not file_path.exists():
                if 'settings' in file_path.name:
                    file_path.write_text('{}')
                else:
                    file_path.write_text('[]')