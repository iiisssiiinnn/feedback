# main.py
import os
import sqlite3
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler, filters,
                          ContextTypes, ConversationHandler, CallbackQueryHandler)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [7585381324]  # Здесь ID администратора (можно расширить)

REGISTER, GET_NAME, GET_POSITION, MAIN_MENU, HANDLE_MESSAGE = range(5)

conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    position TEXT
)''')
conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if user:
        return await show_main_menu(update, context)
    else:
        await update.message.reply_text("Добро пожаловать! Пожалуйста, введите своё ФИО:")
        return GET_NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Теперь введите вашу должность:")
    return GET_POSITION

async def get_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = context.user_data['name']
    position = update.message.text
    user_id = update.effective_user.id
    cursor.execute("INSERT OR REPLACE INTO users (user_id, name, position) VALUES (?, ?, ?)",
                   (user_id, name, position))
    conn.commit()
    return await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = [["📢 Жалоба", "💡 Идея"], ["📬 Сообщение", "📄 FAQ"]]
    reply_markup = ReplyKeyboardMarkup(menu, resize_keyboard=True)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    return MAIN_MENU

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT name, position FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    name, position = result if result else ("Неизвестно", "-")
    text = update.message.text

    if text == "📄 FAQ":
        await update.message.reply_text("Часто задаваемые вопросы:\n1. Когда зарплата?\n2. Как взять выходной?\n3. К кому обратиться по вопросам смен?")
    elif text in ["📢 Жалоба", "💡 Идея", "📬 Сообщение"]:
        context.user_data['category'] = text
        await update.message.reply_text("Введите ваш текст:")
        return HANDLE_MESSAGE
    else:
        category = context.user_data.get('category', 'Сообщение')
        msg = f"🔔 {category} от {name} ({position}):\n{text}"
        for admin_id in ADMIN_IDS:
            await context.bot.send_message(chat_id=admin_id, text=msg)
        await update.message.reply_text("Спасибо, ваше сообщение отправлено.")
        return await show_main_menu(update, context)

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("Доступ запрещён")

    keyboard = [
        [InlineKeyboardButton("📣 Уведомление", callback_data='notify')],
        [InlineKeyboardButton("📊 Опрос", callback_data='poll')],
        [InlineKeyboardButton("🗑️ Удалить сотрудника", callback_data='remove_user')]
    ]
    await update.message.reply_text("Админ-панель:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == 'notify':
        context.user_data['admin_action'] = 'notify'
        await query.edit_message_text("Введите текст уведомления:")
    elif action == 'poll':
        context.user_data['admin_action'] = 'poll'
        await query.edit_message_text("Введите опрос в формате: Вопрос;Вариант1;Вариант2;...")
    elif action == 'remove_user':
        context.user_data['admin_action'] = 'remove_user'
        await query.edit_message_text("Введите user_id сотрудника для удаления:")

    return HANDLE_MESSAGE

async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get('admin_action')
    text = update.message.text

    if action == 'notify':
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        for (uid,) in users:
            await context.bot.send_message(chat_id=uid, text=f"📣 Уведомление от администрации:\n{text}")
        await update.message.reply_text("Уведомление отправлено.")
    elif action == 'poll':
        parts = text.split(';')
        question = parts[0]
        options = parts[1:]
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        for (uid,) in users:
            await context.bot.send_poll(chat_id=uid, question=question, options=options, is_anonymous=True)
        await update.message.reply_text("Опрос отправлен.")
    elif action == 'remove_user':
        cursor.execute("DELETE FROM users WHERE user_id = ?", (text,))
        conn.commit()
        await update.message.reply_text("Пользователь удалён, если он существовал.")

    return MAIN_MENU

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            GET_POSITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_position)],
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
            HANDLE_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_message)]
        },
        fallbacks=[CommandHandler("admin", admin)]
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(admin_choice))

    print("Бот запущен...")
    app.run_polling()

