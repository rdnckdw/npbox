import logging
import datetime
import gspread
import os
import pytz
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, request

# Настройки
TOKEN = os.environ.get("BOT_TOKEN")  # Railway хранит токены в переменных окружения
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")  # ID Google Таблицы
SHEET_NAME = 'Лист1'
CREDS_FILE = 'creds.json'

EMPLOYEES = ['Марина', 'Лиза', 'Вадим', 'Саша', 'Костя', 'Руслан']

CHOOSE_NAME, ENTER_TIME = range(2)

# Временной диапазон (по Киеву)
WORK_START = 9
WORK_END = 20
TIMEZONE = pytz.timezone("Europe/Kyiv")

logging.basicConfig(level=logging.INFO)

# Google Sheets
def get_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

# Проверка рабочего времени
def is_within_work_hours() -> bool:
    now = datetime.datetime.now(TIMEZONE)
    return WORK_START <= now.hour < WORK_END

# Команды
def start(update: Update, context: CallbackContext) -> int:
    if not is_within_work_hours():
        update.message.reply_text("Бот работает только с 09:00 до 20:00 по Киеву.")
        return ConversationHandler.END

    reply_keyboard = [[name] for name in EMPLOYEES]
    update.message.reply_text(
        "Привет! Выбери своё имя:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return CHOOSE_NAME

def choose_name(update: Update, context: CallbackContext) -> int:
    name = update.message.text
    if name not in EMPLOYEES:
        update.message.reply_text("Пожалуйста, выбери имя из списка.")
        return CHOOSE_NAME
    context.user_data['name'] = name
    update.message.reply_text("Теперь введи время (например, 10:00):")
    return ENTER_TIME

def enter_time(update: Update, context: CallbackContext) -> int:
    time_input = update.message.text.strip()
    name = context.user_data['name']
    today = datetime.date.today().strftime('%d.%m.%Y')

    try:
        sheet = get_sheet()
        data = sheet.get_all_values()

        row_index = None
        for i, row in enumerate(data):
            if row and row[0] == name:
                row_index = i + 1
                break

        if row_index is None:
            update.message.reply_text("Не удалось найти строку сотрудника.")
            return ConversationHandler.END

        col_index = None
        header_row = data[0]
        for j, col in enumerate(header_row):
            if col.strip() == today:
                col_index = j + 1
                break

        if col_index is None:
            update.message.reply_text(f"Дата {today} не найдена в таблице.")
            return ConversationHandler.END

        sheet.update_cell(row_index, col_index, time_input)
        update.message.reply_text(f"✅ Время {time_input} для {name} записано на {today}.")
    except Exception as e:
        logging.error(str(e))
        update.message.reply_text("Произошла ошибка при записи в таблицу.")
    
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

# Flask для webhook
app = Flask(__name__)
updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher

conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        CHOOSE_NAME: [MessageHandler(Filters.text & ~Filters.command, choose_name)],
        ENTER_TIME: [MessageHandler(Filters.text & ~Filters.command, enter_time)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)
dp.add_handler(conv_handler)

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), updater.bot)
    updater.dispatcher.process_update(update)
    return 'ok'

@app.route('/')
def index():
    return 'Бот работает!'

if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 5000))
    HEROKU_APP_URL = os.environ.get('RAILWAY_URL')  # Пример: https://your-app.up.railway.app

    if HEROKU_APP_URL:
        webhook_url = f"{HEROKU_APP_URL}/{TOKEN}"
        updater.bot.set_webhook(webhook_url)

    app.run(host='0.0.0.0', port=PORT)
