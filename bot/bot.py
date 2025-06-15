# bot/bot.py
import os
import json
import telebot
from telebot import types
import time
import shutil

from config import BOT_TOKEN

# --- NEW: Centralized Data Directory ---
# Both the bot and client will now use a shared folder in the user's home directory.
DATA_DIR = os.path.join(os.path.expanduser("~"), ".telegram_cloud_service")
os.makedirs(DATA_DIR, exist_ok=True) # Ensure the directory exists

USER_DB_PATH = os.path.join(DATA_DIR, "user_database.json")
TASK_QUEUE_PATH = os.path.join(DATA_DIR, "task_queue.json")

# A dictionary to keep track of what each user is currently doing
user_states = {}

# --- Database Helper Functions ---
def load_json_db(path):
    """Safely loads a JSON file."""
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

def save_json_db(data, path):
    """
    Atomically saves data to a JSON file by writing to a temporary file
    and then renaming it. This prevents read/write race conditions.
    """
    temp_path = path + ".tmp"
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    # The rename operation is atomic on most operating systems
    shutil.move(temp_path, path)

# --- Bot Initialization ---
bot = telebot.TeleBot(BOT_TOKEN)
print("Service Bot is running...")
print(f"Data directory is: {DATA_DIR}")

# --- Command Handlers ---
@bot.message_handler(commands=['reset'])
def handle_reset(message):
    """Allows a user to completely reset their data and start over."""
    user_id = str(message.chat.id)
    
    user_states.pop(user_id, None)
    
    user_db = load_json_db(USER_DB_PATH)
    user_data_existed = user_id in user_db
    if user_data_existed:
        user_db.pop(user_id, None)
        save_json_db(user_db, USER_DB_PATH)
    
    task_db = load_json_db(TASK_QUEUE_PATH)
    if user_id in task_db:
        task_db.pop(user_id, None)
        save_json_db(task_db, TASK_QUEUE_PATH)

    reset_message = (
        "Your data has been completely reset on the server.\n\n"
        "**IMPORTANT NEXT STEP:**\n"
        "The client app saves its ID in a file. To fully reset, you must find and delete this file at the following location on your computer:\n"
        f"`{os.path.join(DATA_DIR, 'client_id.txt')}`\n\n"
        "After you have deleted that file, send /start to begin the setup process again."
    )
    if user_data_existed:
        bot.send_message(user_id, reset_message, parse_mode="Markdown")
    else:
        bot.send_message(user_id, "You have no data to reset. Please send /start to begin the setup process.")


@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = str(message.chat.id)
    user_db = load_json_db(USER_DB_PATH)

    welcome_text = (
        "👋 **Welcome to Telegram Cloud Service!**\n\n"
        "This bot will help you turn your own Telegram account into a secure, private, and unlimited cloud storage system.\n\n"
        "Let's get you set up."
    )
    bot.send_message(user_id, welcome_text, parse_mode="Markdown")

    if user_id in user_db and "client_id" in user_db[user_id]:
        bot.send_message(user_id, "It looks like you're already set up! You can now use commands like `/upload` or `/files`. If you want to start over, send /reset.")
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
    
    bot.send_message(user_id, "OK, I've sent a command to your desktop app. Please use the file window that appears on your computer to select the file you want to upload.")

# ... (rest of the setup functions remain the same) ...
def setup_step1_ask_for_bot(message):
    user_id = str(message.chat.id)
    text = (
        "**Step 1: Create Your Own Bot**\n\n"
        "To ensure your files are completely private, you need your own personal bot.\n\n"
        "1. Open a chat with **@BotFather** on Telegram.\n"
        "2. Send the `/newbot` command.\n"
        "3. Follow his instructions to choose a name and username for your bot.\n"
        "4. **BotFather will give you a unique BOT TOKEN.** It's a long string of characters.\n\n"
        "Once you have your token, please paste it here."
    )
    bot.send_message(user_id, text, parse_mode="Markdown")
    user_states[user_id] = 'awaiting_token'

@bot.message_handler(func=lambda message: user_states.get(str(message.chat.id)) == 'awaiting_token')
def handle_token_input(message):
    user_id = str(message.chat.id)
    token = message.text.strip()
    if ":" not in token or len(token) < 40:
        bot.send_message(user_id, "That doesn't look like a valid bot token.")
        return
    bot.send_message(user_id, "✅ Great! Token received. Let's test it...")
    try:
        test_bot = telebot.TeleBot(token)
        test_bot.get_me()
        bot.send_message(user_id, "✅ Token is valid! Your bot is reachable.")
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
        "2. Add the bot you just created as an admin.\n"
        "3. Post any message in your channel (e.g., 'hello').\n"
        "4. **Forward that message to me.**"
    )
    bot.send_message(user_id, text, parse_mode="Markdown")
    user_states[user_id] = 'awaiting_forward'

@bot.message_handler(
    func=lambda message: user_states.get(str(message.chat.id)) == 'awaiting_forward',
    content_types=['text', 'photo', 'document', 'video']
)
def handle_forwarded_message(message):
    user_id = str(message.chat.id)
    if message.forward_from_chat and message.forward_from_chat.type == 'channel':
        channel_id = message.forward_from_chat.id
        bot.send_message(user_id, f"✅ Channel detected! Your Channel ID is `{channel_id}`. I've saved it.", parse_mode="Markdown")
        user_db = load_json_db(USER_DB_PATH)
        if user_id not in user_db: user_db[user_id] = {}
        user_db[user_id]["channel_id"] = channel_id
        save_json_db(user_db, USER_DB_PATH)
        setup_step3_ask_for_client_id(message)
    else:
        bot.send_message(user_id, "That doesn't seem to be a forwarded message from a channel.")

def setup_step3_ask_for_client_id(message):
    user_id = str(message.chat.id)
    text = (
        "**Step 3: Connect Your Computer**\n\n"
        "1. Download the desktop app from **(placeholder)**.\n"
        "2. Run the application.\n"
        "3. The app will display a unique **Client ID**.\n\n"
        "Please copy that Client ID and paste it here."
    )
    bot.send_message(user_id, text, parse_mode="Markdown")
    user_states[user_id] = 'awaiting_client_id'

@bot.message_handler(func=lambda message: user_states.get(str(message.chat.id)) == 'awaiting_client_id')
def handle_client_id_input(message):
    user_id = str(message.chat.id)
    client_id = message.text.strip()
    try:
        import uuid
        uuid.UUID(client_id, version=4)
    except ValueError:
        bot.send_message(user_id, "That doesn't look like a valid Client ID.")
        return
    bot.send_message(user_id, "✅ Client ID received and saved!")
    user_db = load_json_db(USER_DB_PATH)
    if user_id not in user_db: user_db[user_id] = {}
    user_db[user_id]["client_id"] = client_id
    save_json_db(user_db, USER_DB_PATH)
    setup_complete(message)

def setup_complete(message):
    user_id = str(message.chat.id)
    text = (
        "🎉 **Setup Complete!** 🎉\n\n"
        "You are all set. You can now use `/upload`."
    )
    bot.send_message(user_id, text, parse_mode="Markdown")
    user_states.pop(user_id, None)

bot.infinity_polling()
