#!/bin/bash

# Установка для Ubuntu/Debian системы
echo "Установка системы управления лифтами для Ubuntu..."

# Обновление системы
sudo apt update
sudo apt upgrade -y

# Установка Python и pip
sudo apt install -y python3 python3-pip python3-venv sqlite3

# Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей Python
pip install Flask==2.3.2
pip install gunicorn==21.2.0
pip install cryptography==41.0.3
pip install email-validator==2.0.0
pip install flask-login==0.6.2
pip install flask-sqlalchemy==3.0.5
pip install geopy==2.3.0
pip install oauthlib==3.2.2
pip install openpyxl==3.1.2
pip install psycopg2-binary==2.9.7
pip install pyjwt==2.8.0
pip install pytelegrambotapi==4.12.0
pip install python-dotenv==1.0.0
pip install python-telegram-bot==20.4
pip install pytz==2023.3
pip install pywebpush==1.14.0
pip install schedule==1.2.0
pip install telebot==0.0.5

# Создание системного сервиса
sudo tee /etc/systemd/system/elevator-management.service > /dev/null <<EOF
[Unit]
Description=Elevator Management System
After=network.target

[Service]
Type=exec
User=$USER
WorkingDirectory=$(pwd)
Environment=PATH=$(pwd)/venv/bin
ExecStart=$(pwd)/venv/bin/gunicorn --bind 0.0.0.0:5000 --workers 1 --timeout 120 main:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Создание .env файла если его нет
if [ ! -f .env ]; then
    echo "SESSION_SECRET=$(openssl rand -hex 32)" > .env
    echo "TELEGRAM_TOKEN=YOUR_TELEGRAM_BOT_TOKEN" >> .env
    echo "FLASK_SECRET_KEY=$(openssl rand -hex 32)" >> .env
    echo "Создан файл .env с базовыми настройками"
fi

# Права доступа
chmod +x main.py
chmod 644 requests.db 2>/dev/null || echo "База данных будет создана при первом запуске"

# Активация сервиса
sudo systemctl daemon-reload
sudo systemctl enable elevator-management
sudo systemctl start elevator-management

echo "Установка завершена!"
echo "Сервис доступен по адресу: http://localhost:5000"
echo "Для просмотра логов: sudo journalctl -u elevator-management -f"
echo "Для остановки сервиса: sudo systemctl stop elevator-management"
echo "Для запуска сервиса: sudo systemctl start elevator-management"
echo ""
echo "Не забудьте настроить TELEGRAM_TOKEN в файле .env"