# client/main.py
import os
import sys
import telebot
import time
import uuid
import json
from tkinter import Tk, filedialog

# This allows the script to find our other project modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    # We need the service bot's token to communicate with it.
    from bot.config import BOT_TOKEN as SERVICE_BOT_TOKEN
    from client.uploader_bot import perform_upload
except ImportError:
    print("---FATAL ERROR---")
    print("Could not import necessary modules. Ensure bot and client folders are structured correctly.")
    sys.exit(1)

# --- Configuration ---
CLIENT_ID_FILE = "client_id.txt"
# This client needs to know where the bot's user database is to find its credentials
USER_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'bot', 'user_database.json'))
# This is the shared file for communication
TASK_QUEUE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'bot', 'task_queue.json'))


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
        except json.JSONDecodeError:
            return {}

def save_json(data, path):
    """Saves data to a JSON file."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def open_file_dialog():
    """Opens a native file dialog for the user to select a file."""
    root = Tk()
    root.withdraw()  # Hide the main tkinter window
    root.attributes('-topmost', True) # Bring the dialog to the front
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
        print("Waiting for commands... (Checking every 5 seconds)")
        print("Keep this window open. You can now use /upload on Telegram.")
        print("(Press Ctrl+C to exit)")

    except Exception as e:
        print(f"\n---FATAL CONNECTION ERROR---: {e}")
        return
    
    # Find the user_id associated with this client
    user_db = load_json(USER_DB_PATH)
    my_user_id = None
    for uid, data in user_db.items():
        if data.get("client_id") == client_id:
            my_user_id = uid
            break
    
    if not my_user_id:
        print("\nCould not find a registered user for this Client ID.")
        print("Please complete the setup process with the bot on Telegram.")
        return

    print(f"Linked to Telegram User ID: {my_user_id}")

    # The main polling loop
    while True:
        try:
            tasks_db = load_json(TASK_QUEUE_PATH)
            my_task = tasks_db.get(my_user_id)

            if my_task and my_task.get("status") == "pending" and my_task.get("task") == "upload":
                print("\nReceived 'upload' command from bot.")
                
                # Mark task as in-progress
                my_task["status"] = "processing"
                save_json(tasks_db, TASK_QUEUE_PATH)

                # Get the user's credentials
                user_bot_token = user_db[my_user_id].get("bot_token")
                user_channel_id = user_db[my_user_id].get("channel_id")

                if not user_bot_token or not user_channel_id:
                    print("Error: Missing user's bot token or channel ID.")
                    service_bot.send_message(my_user_id, "❌ Upload failed: Your configuration is incomplete.")
                else:
                    # Open file dialog and perform upload
                    selected_file = open_file_dialog()
                    if selected_file:
                        print(f"User selected file: {selected_file}")
                        perform_upload(user_bot_token, user_channel_id, selected_file, service_bot, my_user_id)
                    else:
                        print("User cancelled file selection.")
                        service_bot.send_message(my_user_id, "Upload cancelled because no file was selected.")
                
                # Mark task as complete
                tasks_db.pop(my_user_id, None)
                save_json(tasks_db, TASK_QUEUE_PATH)
                print("Task complete. Waiting for next command...")

            time.sleep(5) 
        except KeyboardInterrupt:
            print("\nExiting daemon.")
            break
        except Exception as e:
            print(f"An error occurred in the main loop: {e}")
            time.sleep(15) # Wait longer after an error

if __name__ == "__main__":
    main()
