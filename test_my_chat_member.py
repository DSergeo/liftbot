import telebot

API_TOKEN = '7447752085:AAG8Hpg2pF3nG3tmI1b7YEwUIGYDhhZ6Law'

bot = telebot.TeleBot(API_TOKEN)

@bot.my_chat_member_handler()
def handle_my_chat_member(update):
    print("📥 СПРАЦЮВАЛО @my_chat_member_handler!")
    print(f"👤 Кого торкнулося: {update.new_chat_member.user.id}")
    print(f"📌 Старий статус: {update.old_chat_member.status}")
    print(f"📌 Новий статус: {update.new_chat_member.status}")

# Запускаємо polling
bot.polling(
    none_stop=True,
    allowed_updates=["my_chat_member"]
)
