import os
import telebot
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Инициализируем объект бота
BOT_TOKEN = os.getenv("BOT_TOKEN_REQUESTS")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

from . import handlers