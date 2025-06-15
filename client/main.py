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
    # The import names now match the uploader file we created.
    from uploader_bot import perform_upload as uploader_function
    from downloader import perform_download as downloader_function
except ImportError as e:
    print("---FATAL ERROR---")
    print(f"Could not import necessary modules: {e}")
    print("Please ensure 'config.py', 'uploader_bot.py', and 'downloader.py' are in the same directory.")
    sys.exit(1)

# --- Configuration ---
DATA_DIR = os.path.join(os.path.expanduser("~"), ".telegram_cloud_service")
CLIENT_ID_FILE = os.path.join(DATA_DIR, "client_id.txt")
USER_DB_PATH = os.path.join(DATA_DIR, 'user_database.json')
TASK_QUEUE_PATH = os.path.join(DATA_DIR, 'task_queue.json')


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
    if not os.path.exists(path): return {}
    with open(path, 'r', encoding='utf-8') as f:
        try: return json.load(f)
        except: return {}

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
    print(f"  Data Directory: {DATA_DIR}")
    print("="*40)

    try:
        service_bot = telebot.TeleBot(SERVICE_BOT_TOKEN)
        service_bot.get_me()
        print("Successfully connected to the main service bot.")
    except Exception as e:
        print(f"\n---FATAL CONNECTION ERROR---: {e}")
        return
    
    # Registration Loop
    my_user_id = None
    print("Waiting for registration...")
    while not my_user_id:
        try:
            user_db = load_json(USER_DB_PATH)
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

    # Main polling loop
    while True:
        try:
            user_db = load_json(USER_DB_PATH) # Reload user_db in the loop to get fresh credentials
            tasks_db = load_json(TASK_QUEUE_PATH)
            my_task = tasks_db.get(my_user_id)

            if my_task and my_task.get("status") == "pending":
                # Mark task as processing immediately
                my_task["status"] = "processing"
                save_json(tasks_db, TASK_QUEUE_PATH)
                
                user_credentials = user_db.get(my_user_id, {})
                user_bot_token = user_credentials.get("bot_token")

                if not user_bot_token:
                    service_bot.send_message(my_user_id, "❌ Task failed: Could not find your bot token.")
                
                # --- Handle Upload Task ---
                elif my_task.get("task") == "upload":
                    print("\nReceived 'upload' command from bot.")
                    user_channel_id = user_credentials.get("channel_id")
                    if not user_channel_id:
                        service_bot.send_message(my_user_id, "❌ Upload failed: Your configuration is incomplete.")
                    else:
                        selected_file = open_file_dialog()
                        if selected_file:
                            uploader_function(user_bot_token, user_channel_id, selected_file, service_bot, my_user_id)
                        else:
                            service_bot.send_message(my_user_id, "Upload cancelled because no file was selected.")
                
                # --- Handle Download Task ---
                elif my_task.get("task") == "download":
                    print("\nReceived 'download' command from bot.")
                    filename_to_download = my_task.get("filename")
                    
                    user_files_db_path = os.path.join(DATA_DIR, f"user_{my_user_id}_files.json")
                    user_files_db = load_json(user_files_db_path)
                    file_info = user_files_db.get(filename_to_download)
                    
                    if not file_info:
                        service_bot.send_message(my_user_id, f"❌ Download failed: Could not find data for '{filename_to_download}'.")
                    else:
                        # --- THIS IS THE FIX ---
                        # Add the filename to the dictionary before passing it to the downloader.
                        file_info['name'] = filename_to_download
                        downloader_function(user_bot_token, file_info)

                # Remove the completed/processed task
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
