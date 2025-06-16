# client/main.py
import os
import sys
import time
import uuid
import json
import tkinter as tk
from tkinter import filedialog, messagebox

# Add the script's own directory to the Python path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Third-party libraries must be imported after the path is set
try:
    import telebot
    from config import SERVICE_BOT_TOKEN
    from uploader_bot import perform_upload as uploader_function
    from downloader import perform_download as downloader_function
except ImportError as e:
    print(f"---FATAL ERROR---: Could not import necessary modules: {e}")
    print("Please run 'pip install -r requirements.txt' before running.")
    sys.exit(1)

# --- Configuration ---
DATA_DIR = os.path.join(os.path.expanduser("~"), ".telegram_cloud_service")
CLIENT_ID_FILE = os.path.join(DATA_DIR, "client_id.txt")
CLIENT_SETTINGS_FILE = os.path.join(DATA_DIR, "client_settings.json")
USER_DB_PATH = os.path.join(DATA_DIR, 'user_database.json')
TASK_QUEUE_PATH = os.path.join(DATA_DIR, 'task_queue.json')

# --- Helper Functions ---
def get_client_id():
    """Gets or creates the unique client ID."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CLIENT_ID_FILE):
        client_id = str(uuid.uuid4())
        with open(CLIENT_ID_FILE, 'w') as f: f.write(client_id)
        return client_id
    else:
        with open(CLIENT_ID_FILE, 'r') as f: return f.read().strip()

def load_json(path):
    if not os.path.exists(path): return {}
    with open(path, 'r', encoding='utf-8') as f:
        try: return json.load(f)
        except: return {}

def save_json(data, path):
    temp_path = path + ".tmp"
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    os.replace(temp_path, path)

def open_file_dialog_blocking():
    """Opens a file dialog and blocks until it's closed."""
    # This function is now guaranteed to work because it's called from the main thread.
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    filepath = filedialog.askopenfilename(title="Select a file to upload")
    root.destroy()
    return filepath

def first_time_setup_gui(client_id):
    """Handles the first-time setup process using a robust Tkinter window."""
    root = tk.Tk()
    root.withdraw()

    setup_win = tk.Toplevel(root)
    setup_win.title("Cloud Client - First Time Setup")
    setup_win.geometry("450x250")
    setup_win.resizable(False, False)
    setup_win.attributes('-topmost', True)
    
    def select_folder_and_finish():
        download_path = filedialog.askdirectory(parent=setup_win, title="Select Default Download Folder")
        if download_path:
            settings = {'download_path': download_path}
            save_json(settings, CLIENT_SETTINGS_FILE)
            messagebox.showinfo("Setup Complete", f"Download folder set to:\n{settings['download_path']}", parent=setup_win)
            setup_win.destroy()
            root.quit()
        else:
            messagebox.showwarning("No Folder Selected", "You must select a download folder to continue.", parent=setup_win)

    tk.Label(setup_win, text="Welcome! To link this app, please provide\nthe following Client ID to your Telegram bot:", pady=10).pack()
    id_entry = tk.Entry(setup_win, justify='center', font=('Courier', 12))
    id_entry.insert(0, client_id)
    id_entry.config(state='readonly')
    id_entry.pack(pady=5, padx=20, fill='x')
    tk.Button(setup_win, text="Copy ID to Clipboard", command=lambda: [setup_win.clipboard_clear(), setup_win.clipboard_append(id_entry.get())]).pack(pady=5)
    tk.Button(setup_win, text="Select Download Folder & Finish", command=select_folder_and_finish, pady=10).pack()
    
    root.mainloop()

# --- Main Application Logic ---
if __name__ == "__main__":
    client_id = get_client_id()
    print("="*50)
    print("         Telegram Cloud Client Daemon")
    print("="*50)
    print(f"Client ID: {client_id}")
    print(f"Data Directory: {DATA_DIR}")
    print("="*50)

    # --- Simplified and Robust Startup ---
    if not os.path.exists(CLIENT_SETTINGS_FILE):
        print("First time run or reset detected. Launching setup window...")
        first_time_setup_gui(client_id)
        print("Setup window closed. Please complete registration with the bot if you haven't already.")

    print("\nConnecting to service bot...")
    try:
        service_bot = telebot.TeleBot(SERVICE_BOT_TOKEN)
        service_bot.get_me()
        print("✅ Successfully connected.")
    except Exception as e:
        print(f"---FATAL CONNECTION ERROR---: {e}")
        sys.exit()

    print("Waiting for registration to complete...")
    my_user_id = None
    while my_user_id is None:
        user_db = load_json(USER_DB_PATH)
        for uid, data in user_db.items():
            if data.get("client_id") == client_id:
                my_user_id = uid
                break
        time.sleep(5)
    
    print("✅ Successfully Linked to Telegram User!")
    print("--- Client is now running. Waiting for commands. ---")
    print("(You can minimize this window. Press Ctrl+C here to exit.)")

    # --- Main Polling Loop ---
    while True:
        try:
            tasks_db = load_json(TASK_QUEUE_PATH)
            my_task = tasks_db.get(my_user_id)

            if my_task and my_task.get("status") == "pending":
                print(f"\nReceived '{my_task.get('task')}' command from bot.")
                my_task["status"] = "processing"
                save_json(tasks_db, TASK_QUEUE_PATH)

                user_db = load_json(USER_DB_PATH)
                user_credentials = user_db.get(my_user_id, {})
                user_bot_token = user_credentials.get("bot_token")

                if my_task.get("task") == "upload":
                    filepath = open_file_dialog_blocking()
                    if filepath:
                        user_channel_id = user_credentials.get("channel_id")
                        uploader_function(user_bot_token, user_channel_id, filepath, service_bot, my_user_id)
                    else:
                        print("User cancelled file selection.")
                        service_bot.send_message(my_user_id, "Upload cancelled.")

                elif my_task.get("task") == "download":
                    client_settings = load_json(CLIENT_SETTINGS_FILE)
                    download_path = client_settings.get("download_path")
                    if download_path:
                        filename = my_task.get("filename")
                        files_db_path = os.path.join(DATA_DIR, f"user_{my_user_id}_files.json")
                        files_db = load_json(files_db_path)
                        file_info = files_db.get(filename)
                        if file_info:
                            file_info['name'] = filename
                            downloader_function(user_bot_token, file_info, download_path)

                tasks_db.pop(my_user_id, None)
                save_json(tasks_db, TASK_QUEUE_PATH)
                print("\nTask complete. Waiting for next command...")

            time.sleep(5)
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"An error occurred in the main loop: {e}")
            time.sleep(15)
