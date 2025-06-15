# bot/bot.py
import os
import json
import telebot
from telebot import types

# --- This is the fix ---
# It now correctly imports the token from your config file.
from config import BOT_TOKEN

# This will be our simple database to store user credentials.
# It's a JSON file mapping user_id to their credentials.
USER_DB_PATH = "user_database.json"

# A dictionary to keep track of what each user is currently doing (e.g., 'awaiting_token').
user_states = {}

# --- Database Helper Functions ---
def load_user_db():
    """Loads the user database from the JSON file."""
    if not os.path.exists(USER_DB_PATH):
        return {}
    with open(USER_DB_PATH, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_user_db(data):
    """Saves the user database to the JSON file."""
    with open(USER_DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# --- Bot Initialization ---
bot = telebot.TeleBot(BOT_TOKEN)
print("Service Bot is running...")

# --- Command Handlers ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    """Handles the /start command, beginning the user onboarding process."""
    user_id = str(message.chat.id)
    user_db = load_user_db()

    welcome_text = (
        "👋 **Welcome to Telegram Cloud Service!**\n\n"
        "This bot will help you turn your own Telegram account into a secure, private, and unlimited cloud storage system.\n\n"
        "Let's get you set up."
    )
    bot.send_message(user_id, welcome_text, parse_mode="Markdown")

    # Check if user is already registered
    if user_id in user_db and "client_id" in user_db[user_id]:
        bot.send_message(user_id, "It looks like you're already set up! You can now use commands like `/upload` or `/files`.")
    else:
        # Start the setup process
        setup_step1_ask_for_bot(message)

def setup_step1_ask_for_bot(message):
    """Guides the user to create their own bot."""
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
    # Set the user's state so we know they are expected to send a token next
    user_states[user_id] = 'awaiting_token'


# --- Message Handlers for Setup ---
@bot.message_handler(func=lambda message: user_states.get(str(message.chat.id)) == 'awaiting_token')
def handle_token_input(message):
    """Handles the user pasting their bot token."""
    user_id = str(message.chat.id)
    token = message.text.strip()

    # Basic validation to see if it looks like a token
    if ":" not in token or len(token) < 40:
        bot.send_message(user_id, "That doesn't look like a valid bot token. Please get the correct token from @BotFather and paste it here.")
        return

    bot.send_message(user_id, "✅ Great! Token received. Let's test it...")

    try:
        # Try to connect with the user's token to see if it's valid
        test_bot = telebot.TeleBot(token)
        test_bot.get_me()
        bot.send_message(user_id, "✅ Token is valid! Your bot is reachable.")
        
        # Save the token and move to the next step
        user_db = load_user_db()
        user_db[user_id] = {"bot_token": token}
        save_user_db(user_db)
        
        setup_step2_ask_for_channel(message)

    except Exception as e:
        bot.send_message(user_id, f"❌ I couldn't connect with that token. Please make sure it's correct and try again. Error: {e}")
        return


def setup_step2_ask_for_channel(message):
    """Guides the user to create a channel and add their bot."""
    user_id = str(message.chat.id)
    text = (
        "**Step 2: Create Your Private Channel**\n\n"
        "Now, let's create the secure vault where your files will be stored.\n\n"
        "1. Create a new **Private Channel**.\n"
        "2. Go to the channel's info, then 'Administrators', and add the bot you just created as an admin.\n"
        "3. Post any message in your channel (e.g., 'hello').\n"
        "4. **Forward that message to me.** This will allow me to securely get the Channel ID."
    )
    bot.send_message(user_id, text, parse_mode="Markdown")
    user_states[user_id] = 'awaiting_forward'


@bot.message_handler(
    func=lambda message: user_states.get(str(message.chat.id)) == 'awaiting_forward',
    content_types=['text', 'photo', 'document', 'video'] # Listen for any forwarded message
)
def handle_forwarded_message(message):
    """Handles the user forwarding a message to get the channel ID."""
    user_id = str(message.chat.id)
    
    if message.forward_from_chat and message.forward_from_chat.type == 'channel':
        channel_id = message.forward_from_chat.id
        bot.send_message(user_id, f"✅ Channel detected! Your Channel ID is `{channel_id}`. I've saved it.", parse_mode="Markdown")
        
        # Save the channel ID
        user_db = load_user_db()
        user_db[user_id]["channel_id"] = channel_id
        save_user_db(user_db)
        
        setup_step3_ask_for_client_id(message)
    else:
        bot.send_message(user_id, "That doesn't seem to be a forwarded message from a channel. Please follow the instructions and forward a message from your private channel.")


def setup_step3_ask_for_client_id(message):
    """Asks the user to run the desktop app and provide its ID."""
    user_id = str(message.chat.id)
    text = (
        "**Step 3: Connect Your Computer**\n\n"
        "The final step is to link your computer to this service.\n\n"
        "1. Download the desktop app from **(placeholder for your download link)**.\n"
        "2. Run the application. A terminal window will open.\n"
        "3. The app will display a unique **Client ID**.\n\n"
        "Please copy that Client ID and paste it here."
    )
    bot.send_message(user_id, text, parse_mode="Markdown")
    user_states[user_id] = 'awaiting_client_id'

@bot.message_handler(func=lambda message: user_states.get(str(message.chat.id)) == 'awaiting_client_id')
def handle_client_id_input(message):
    """Handles the user pasting their Client ID."""
    user_id = str(message.chat.id)
    client_id = message.text.strip()

    # Basic validation for UUID format
    try:
        import uuid
        uuid.UUID(client_id, version=4)
    except ValueError:
        bot.send_message(user_id, "That doesn't look like a valid Client ID. Please copy the full ID from the desktop app and try again.")
        return

    bot.send_message(user_id, "✅ Client ID received and saved!")

    user_db = load_user_db()
    user_db[user_id]["client_id"] = client_id
    save_user_db(user_db)

    setup_complete(message)

def setup_complete(message):
    """Confirms that the setup is complete."""
    user_id = str(message.chat.id)
    text = (
        "🎉 **Setup Complete!** 🎉\n\n"
        "You are all set. Your personal cloud storage is ready.\n\n"
        "You can now use commands like `/upload` to begin storing files. Keep the desktop application running in the background."
    )
    bot.send_message(user_id, text, parse_mode="Markdown")
    # Clear the user's state
    user_states.pop(user_id, None)


# This makes the bot run continuously
bot.infinity_polling()
