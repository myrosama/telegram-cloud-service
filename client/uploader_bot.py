# client/uploader_bot.py
import os
import sys
import time
import json
import shutil
import math
import telebot
import tkinter as tk
from tkinter import ttk

# Add the script's own directory to the Python path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from splitter import split_file

# --- Centralized Data Directory ---
DATA_DIR = os.path.join(os.path.expanduser("~"), ".telegram_cloud_service")

# --- Database Functions ---
def load_json_db(path):
    if not os.path.exists(path): return {}
    with open(path, 'r', encoding='utf-8') as f:
        try: return json.load(f)
        except: return {}

def save_json_db(data, path):
    temp_path = path + ".tmp"
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    os.replace(temp_path, path)

# --- GUI Status Window Class ---
class StatusWindow:
    def __init__(self, filename, total_parts):
        self.root = tk.Tk()
        self.root.title(f"Uploading: {filename}")
        self.root.geometry("400x120")
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)
        
        self.status_label = tk.Label(self.root, text="Initializing...", justify=tk.LEFT, anchor="w")
        self.status_label.pack(pady=10, padx=10, fill='x')
        
        self.progress_bar = ttk.Progressbar(self.root, orient='horizontal', length=380, mode='determinate', maximum=total_parts)
        self.progress_bar.pack(pady=10, padx=10)
        self.root.update()

    def update(self, text, value):
        if self.root and self.root.winfo_exists():
            self.status_label.config(text=text)
            self.progress_bar['value'] = value
            self.root.update_idletasks()

    def close(self):
        if self.root and self.root.winfo_exists():
            self.root.destroy()

# --- CORE UPLOAD LOGIC ---
def perform_upload(user_bot_token, user_channel_id, file_path, service_bot_instance, user_telegram_id):
    if not os.path.exists(file_path):
        service_bot_instance.send_message(user_telegram_id, f"❌ Upload failed: File not found.")
        return

    user_bot = telebot.TeleBot(user_bot_token)
    original_filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    user_files_db_path = os.path.join(DATA_DIR, f"user_{user_telegram_id}_files.json")
    user_files_db = load_json_db(user_files_db_path)
    
    uploaded_message_info = []
    start_part_index = 0
    chunk_size = 19 * 1024 * 1024
    total_parts = math.ceil(file_size / chunk_size)

    if original_filename in user_files_db:
        existing_data = user_files_db[original_filename]
        num_parts_on_record = len(existing_data.get("messages", []))
        if 0 < num_parts_on_record < total_parts:
            start_part_index = num_parts_on_record
            uploaded_message_info = existing_data["messages"]
    
    status_window = StatusWindow(original_filename, total_parts)
    
    try:
        parts_paths, _ = split_file(file_path)
    except Exception as e:
        status_window.update(f"Error: Could not split file.", 0)
        service_bot_instance.send_message(user_telegram_id, f"❌ Upload failed: {e}")
        time.sleep(3); status_window.close(); return

    service_bot_instance.send_message(user_telegram_id, f"🚀 Starting upload of '{original_filename}'...")
    
    try:
        for i in range(start_part_index, total_parts):
            part_path = parts_paths[i]
            part_name = os.path.basename(part_path)
            
            status_window.update(f"Uploading part {i+1} of {total_parts}...", i)
            
            uploaded_successfully = False
            for attempt in range(5):
                try:
                    with open(part_path, 'rb') as part_file:
                        message = user_bot.send_document(user_channel_id, part_file, visible_file_name=part_name, caption=part_name, timeout=90)
                    uploaded_message_info.append({'message_id': message.id, 'file_id': message.document.file_id})
                    
                    user_files_db[original_filename] = {
                        "messages": uploaded_message_info, "total_parts": total_parts,
                        "file_size_bytes": file_size, "chunk_size": chunk_size, "upload_method": "bot"
                    }
                    save_json_db(user_files_db, user_files_db_path)
                    
                    uploaded_successfully = True
                    break
                except telebot.apihelper.ApiTelegramException as e:
                    if e.error_code == 429:
                        retry_after = json.loads(e.result.text)['parameters']['retry_after']
                        status_window.update(f"Rate limit hit. Waiting {retry_after}s...", i)
                        time.sleep(retry_after)
                    else: raise e
                except Exception as e:
                    if attempt < 4:
                        status_window.update(f"Part {i+1} failed. Retrying...", i)
                        time.sleep(5 * (attempt + 1))
                    else: raise e
            
            if not uploaded_successfully:
                raise Exception(f"Failed to upload part {part_name} after multiple retries.")
            
            time.sleep(1)

        status_window.update("✅ Upload Complete!", total_parts)
        service_bot_instance.send_message(user_telegram_id, f"✅ Successfully uploaded '{original_filename}'.")
    
    except Exception as e:
        status_window.update(f"❌ Upload Failed: {e}", start_part_index)
        service_bot_instance.send_message(user_telegram_id, f"❌ Upload failed. Your progress has been saved.")
    
    finally:
        temp_dir = f"{file_path}_parts"
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        time.sleep(3)
        status_window.close()
