# bot/bot.py
import os
import json
import telebot
from telebot import types
import time
import shutil

from config import BOT_TOKEN

# --- Centralized Data Directory ---
DATA_DIR = os.path.join(os.path.expanduser("~"), ".telegram_cloud_service")
os.makedirs(DATA_DIR, exist_ok=True) 

USER_DB_PATH = os.path.join(DATA_DIR, "user_database.json")
TASK_QUEUE_PATH = os.path.join(DATA_DIR, "task_queue.json")

# A dictionary to keep track of what each user is currently doing
user_states = {}

# --- Database Helper Functions ---
def load_json_db(path):
    if not os.path.exists(path): return {}
    with open(path, 'r', encoding='utf-8') as f:
        try: return json.load(f)
        except: return {}

def save_json_db(data, path):
    temp_path = path + ".tmp"
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    shutil.move(temp_path, path)

# --- Bot Initialization ---
bot = telebot.TeleBot(BOT_TOKEN)
print("Service Bot is running...")
print(f"Data directory is: {DATA_DIR}")

# --- Command Handlers ---
@bot.message_handler(commands=['reset'])
def handle_reset(message):
    user_id = str(message.chat.id)
    if user_states.get(user_id) == 'awaiting_reset_confirmation':
        user_states.pop(user_id, None)
        user_db = load_json_db(USER_DB_PATH)
        if user_id in user_db:
            user_db.pop(user_id, None)
            save_json_db(user_db, USER_DB_PATH)
        user_files_db_path = os.path.join(DATA_DIR, f"user_{user_id}_files.json")
        if os.path.exists(user_files_db_path): os.remove(user_files_db_path)
        task_db = load_json_db(TASK_QUEUE_PATH)
        if user_id in task_db:
            task_db.pop(user_id, None)
            save_json_db(task_db, TASK_QUEUE_PATH)
        reset_message = (
            "✅ **Your data has been permanently deleted from the server.**\n\n"
            "To re-sync, please **restart the DaemonClient app** on your computer. The setup window will appear again."
        )
        bot.send_message(user_id, reset_message, parse_mode="Markdown")
    else:
        warning_message = (
            "⚠️ **WARNING!** This will delete all your data. This action cannot be undone.\n\n"
            "Send `/reset` again within 60 seconds to confirm."
        )
        bot.send_message(user_id, warning_message, parse_mode="Markdown")
        user_states[user_id] = 'awaiting_reset_confirmation'
        time.sleep(60)
        if user_states.get(user_id) == 'awaiting_reset_confirmation':
            user_states.pop(user_id, None)

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = str(message.chat.id)
    user_db = load_json_db(USER_DB_PATH)
    welcome_text = (
        "👋 **Welcome to Telegram Cloud Service!**\n\nLet's get you set up."
    )
    bot.send_message(user_id, welcome_text, parse_mode="Markdown")
    if user_id in user_db and "client_id" in user_db[user_id]:
        bot.send_message(user_id, "It looks like you're already set up! Use `/files` or `/upload`. To start over, send /reset.")
    else:
        setup_step1_ask_for_bot(message)

@bot.message_handler(commands=['upload'])
def handle_upload_command(message):
    user_id = str(message.chat.id)
    user_db = load_json_db(USER_DB_PATH)
    if user_id not in user_db or "client_id" not in user_db[user_id]:
        bot.send_message(user_id, "You need to complete the setup process first. Please send /start to begin.")
        return
    tasks_db = load_json_db(TASK_QUEUE_PATH)
    tasks_db[user_id] = {"task": "upload", "status": "pending"}
    save_json_db(tasks_db, TASK_QUEUE_PATH)
    bot.send_message(user_id, "OK, I've sent a command to your desktop app. Please use the file window that appears on your computer to select the file.")

@bot.message_handler(commands=['files'])
def handle_files_command(message):
    user_id = str(message.chat.id)
    user_db = load_json_db(USER_DB_PATH)
    if user_id not in user_db or "client_id" not in user_db[user_id]:
        bot.send_message(user_id, "You need to complete the setup process first. Send /start.")
        return
    user_files_db_path = os.path.join(DATA_DIR, f"user_{user_id}_files.json")
    user_files_db = load_json_db(user_files_db_path)
    if not user_files_db:
        bot.send_message(user_id, "You haven't uploaded any files yet.")
        return
    markup = types.InlineKeyboardMarkup()
    for filename, data in user_files_db.items():
        size_mb = data.get('file_size_bytes', 0) / (1024*1024)
        button_text = f"{filename} ({size_mb:.2f} MB)"
        callback_data = f"download::{filename}"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=callback_data))
    bot.send_message(user_id, "Here are your uploaded files. Click one to download:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("download::"))
def handle_download_callback(call):
    user_id = str(call.message.chat.id)
    filename = call.data.split("::")[1]
    bot.answer_callback_query(call.id, f"Requesting download for {filename}...")
    tasks_db = load_json_db(TASK_QUEUE_PATH)
    tasks_db[user_id] = {"task": "download", "filename": filename, "status": "pending"}
    save_json_db(tasks_db, TASK_QUEUE_PATH)
    bot.send_message(user_id, f"OK, I've sent the download command for '{filename}' to your desktop app.")

def setup_step1_ask_for_bot(message):
    user_id = str(message.chat.id)
    text = (
        "**Step 1: Create Your Own Bot**\n\n"
        "1. Open a chat with **@BotFather**.\n"
        "2. Send `/newbot` and follow his instructions.\n"
        "3. **BotFather will give you a BOT TOKEN.**\n\n"
        "Once you have your token, please paste it here."
    )
    bot.send_message(user_id, text, parse_mode="Markdown")
    user_states[user_id] = 'awaiting_token'

@bot.message_handler(func=lambda message: user_states.get(str(message.chat.id)) == 'awaiting_token')
def handle_token_input(message):
    user_id = str(message.chat.id)
    token = message.text.strip()
    if ":" not in token or len(token) < 40:
        bot.send_message(user_id, "That doesn't look like a valid bot token."); return
    bot.send_message(user_id, "✅ Token received. Testing...")
    try:
        telebot.TeleBot(token).get_me()
        bot.send_message(user_id, "✅ Token is valid!")
        user_db = load_json_db(USER_DB_PATH)
        user_db[user_id] = {"bot_token": token}
        save_json_db(user_db, USER_DB_PATH)
        setup_step2_ask_for_channel(message)
    except Exception as e:
        bot.send_message(user_id, f"❌ I couldn't connect with that token. Error: {e}")

def setup_step2_ask_for_channel(message):
    user_id = str(message.chat.id)
    text = (
        "**Step 2: Create Your Private Channel**\n\n"
        "1. Create a new **Private Channel**.\n"
        "2. Add your new bot as an **admin**.\n"
        "3. Post any message in your channel.\n"
        "4. **Forward that message to me.**"
    )
    bot.send_message(user_id, text, parse_mode="Markdown")
    user_states[user_id] = 'awaiting_forward'

@bot.message_handler(func=lambda message: user_states.get(str(message.chat.id)) == 'awaiting_forward', content_types=['text', 'document', 'photo', 'video'])
def handle_forwarded_message(message):
    user_id = str(message.chat.id)
    if message.forward_from_chat and message.forward_from_chat.type == 'channel':
        channel_id = message.forward_from_chat.id
        bot.send_message(user_id, f"✅ Channel detected! ID: `{channel_id}`.", parse_mode="Markdown")
        user_db = load_json_db(USER_DB_PATH)
        if user_id not in user_db: user_db[user_id] = {}
        user_db[user_id]["channel_id"] = channel_id
        save_json_db(user_db, USER_DB_PATH)
        setup_step3_ask_for_client_app(message)
    else:
        bot.send_message(user_id, "That wasn't a forwarded message from a channel.")

def setup_step3_ask_for_client_app(message):
    user_id = str(message.chat.id)
    text = (
        "**Step 3: Connect Your Computer**\n\n"
        "1. I will now send you the desktop app. Please download and run it.\n"
        "2. A setup window will open with a **Client ID** and will ask you to choose a download folder.\n\n"
        "Please copy the Client ID from the app and paste it here."
    )
    bot.send_message(user_id, text, parse_mode="Markdown")
    try:
        script_dir = os.path.dirname(__file__)
        app_path = os.path.join(script_dir, '..', 'dist', 'DaemonClient.exe')
        with open(app_path, 'rb') as app_file:
            bot.send_document(user_id, app_file, caption="Here is the client application.")
        user_states[user_id] = 'awaiting_client_id'
    except Exception as e:
        bot.send_message(user_id, f"Error sending client app: {e}")

@bot.message_handler(func=lambda message: user_states.get(str(message.chat.id)) == 'awaiting_client_id')
def handle_client_id_input(message):
    user_id = str(message.chat.id)
    client_id = message.text.strip()
    try:
        import uuid
        uuid.UUID(client_id, version=4)
        bot.send_message(user_id, "✅ Client ID received and saved!")
        user_db = load_json_db(USER_DB_PATH)
        if user_id not in user_db: user_db[user_id] = {}
        user_db[user_id]["client_id"] = client_id
        save_json_db(user_db, USER_DB_PATH)
        setup_complete(message)
    except ValueError:
        bot.send_message(user_id, "That doesn't look like a valid Client ID.")

def setup_complete(message):
    user_id = str(message.chat.id)
    # --- UPDATED TEXT ---
    text = (
        "🎉 **Setup Complete!** 🎉\n\n"
        "You are all set. You can now use `/upload` and `/files`.\n\n"
        "**Important:** For this service to work, you must **keep the DaemonClient application running** on your computer."
    )
    bot.send_message(user_id, text, parse_mode="Markdown")
    user_states.pop(user_id, None)

bot.infinity_polling()
