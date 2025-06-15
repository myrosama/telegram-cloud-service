# client/main.py
import os
import sys
import time
import uuid
import json

# Add the script's own directory to the Python path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import telebot
from tkinter import Tk, filedialog

try:
    from config import SERVICE_BOT_TOKEN
    # We rename the import to avoid confusion with the function name
    from uploader_bot import perform_upload as uploader_function
except ImportError as e:
    print("---FATAL ERROR---")
    print(f"Could not import necessary modules: {e}")
    print("Please ensure 'config.py' and 'uploader_bot.py' are in the same directory as this script.")
    sys.exit(1)

# --- Configuration ---
CLIENT_ID_FILE = "client_id.txt"
BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'bot'))
USER_DB_PATH = os.path.join(BOT_DIR, 'user_database.json')
TASK_QUEUE_PATH = os.path.join(BOT_DIR, 'task_queue.json')


# --- Helper Functions ---
def get_client_id():
    """Gets the unique ID for this client, creating one if it doesn't exist."""
    if os.path.exists(CLIENT_ID_FILE):
        with open(CLIENT_ID_FILE, 'r') as f:
            return f.read().strip()
    else:
        client_id = str(uuid.uuid4())
        with open(CLIENT_ID_FILE, 'w') as f:
            f.write(client_id)
        print(f"First time run: Generated a new unique Client ID: {client_id}")
        return client_id

def load_json(path):
    """Safely loads a JSON file."""
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

def save_json(data, path):
    """Saves data to a JSON file."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def open_file_dialog():
    """Opens a native file dialog for the user to select a file."""
    root = Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    filepath = filedialog.askopenfilename(title="Select a file to upload")
    root.destroy()
    return filepath

# --- Main Application Logic ---
def main():
    """The main function for the client daemon."""
    client_id = get_client_id()
    
    print("="*40)
    print("  Telegram Cloud Client Daemon")
    print(f"  Client ID: {client_id}")
    print("="*40)

    try:
        service_bot = telebot.TeleBot(SERVICE_BOT_TOKEN)
        service_bot.get_me()
        print("Successfully connected to the main service bot.")

    except Exception as e:
        print(f"\n---FATAL CONNECTION ERROR---: {e}")
        return
    
    # --- Registration Loop ---
    my_user_id = None
    print("Waiting for registration...")
    print("Please complete the setup process with the bot on Telegram using the Client ID above.")
    while not my_user_id:
        try:
            user_db = load_json(USER_DB_PATH)
            # --- NEW DEBUG LINE ---
            # This will print the contents of the database it's reading every 5 seconds.
            print(f"Checking database... Found {len(user_db)} user(s). Content: {json.dumps(user_db)}") 
            
            for uid, data in user_db.items():
                if data.get("client_id") == client_id:
                    my_user_id = uid
                    break
            if not my_user_id:
                time.sleep(5)
        except KeyboardInterrupt:
            print("\nExiting during registration check.")
            return
    
    print("\n✅ Successfully Linked to Telegram User!")
    print("Waiting for commands... Keep this window open.")

    # The main polling loop
    while True:
        try:
            tasks_db = load_json(TASK_QUEUE_PATH)
            my_task = tasks_db.get(my_user_id)

            if my_task and my_task.get("status") == "pending" and my_task.get("task") == "upload":
                print("\nReceived 'upload' command from bot.")
                
                my_task["status"] = "processing"
                save_json(tasks_db, TASK_QUEUE_PATH)

                # We need to re-load the user_db here to get the latest credentials
                user_db = load_json(USER_DB_PATH) 
                user_credentials = user_db.get(my_user_id, {})
                user_bot_token = user_credentials.get("bot_token")
                user_channel_id = user_credentials.get("channel_id")

                if not user_bot_token or not user_channel_id:
                    print("Error: Missing user's bot token or channel ID in the database.")
                    service_bot.send_message(my_user_id, "❌ Upload failed: Your configuration is incomplete. Please /reset and start again.")
                else:
                    selected_file = open_file_dialog()
                    if selected_file:
                        print(f"User selected file: {selected_file}")
                        uploader_function(user_bot_token, user_channel_id, selected_file, service_bot, my_user_id)
                    else:
                        print("User cancelled file selection.")
                        service_bot.send_message(my_user_id, "Upload cancelled because no file was selected.")
                
                tasks_db.pop(my_user_id, None)
                save_json(tasks_db, TASK_QUEUE_PATH)
                print("\nTask complete. Waiting for next command...")

            time.sleep(5) 
        except KeyboardInterrupt:
            print("\nExiting daemon.")
            break
        except Exception as e:
            print(f"An error occurred in the main loop: {e}")
            time.sleep(15)

if __name__ == "__main__":
    main()
