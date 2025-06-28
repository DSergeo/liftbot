# Вихідний образ
FROM python:3.11-slim

# Робоча директорія
WORKDIR /app

# Копіюємо файли
COPY . .

# Встановлюємо pip + залежності
RUN pip install --no-cache-dir --upgrade pip
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# Відкриваємо порт Flask (5000 за замовчуванням)
EXPOSE 5000

# Запускаємо Flask-сервер (з Gunicorn — для продакшену)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app"]
