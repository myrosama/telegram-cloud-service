# client/uploader_bot.py
import os
import sys
import time
import json
import math
import telebot
from tqdm import tqdm

# This allows the script to find our other project modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- CONFIGURATION & CONSTANTS ---
# This DB path is now relative to the client app, for storing local upload progress.
UPLOAD_DB_PATH = "upload_progress.json" 
CHUNK_SIZE = int(19 * 1024 * 1024)
UPLOAD_RETRIES = 10

# --- UPLOAD DATABASE FUNCTIONS ---
def load_upload_db():
    if not os.path.exists(UPLOAD_DB_PATH):
        return {}
    with open(UPLOAD_DB_PATH, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_upload_db(data):
    with open(UPLOAD_DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# --- Generator for splitting files ---
def split_file(file_path, chunk_size):
    """
    A generator function that reads a file and yields it chunk by chunk.
    This is memory-efficient as it doesn't load the whole file at once.
    """
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk

# --- CORE UPLOAD LOGIC ---
def perform_upload(user_bot_token, user_channel_id, file_path, service_bot_instance, user_telegram_id):
    """The main function to handle splitting and uploading for a specific user."""
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found.")
        service_bot_instance.send_message(user_telegram_id, f"❌ Upload failed: File '{os.path.basename(file_path)}' not found on your computer.")
        return False

    print("Connecting with user's bot token...")
    user_bot = telebot.TeleBot(user_bot_token)
    
    original_filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    total_parts = math.ceil(file_size / CHUNK_SIZE)

    upload_db = load_upload_db()
    uploaded_message_info = []
    start_part_index = 0

    # Automatic resume logic
    if original_filename in upload_db:
        existing_data = upload_db[original_filename]
        num_parts_on_record = len(existing_data.get("messages", []))
        if 0 < num_parts_on_record < total_parts:
            print(f"Resuming upload for '{original_filename}' from part {num_parts_on_record + 1}.")
            start_part_index = num_parts_on_record
            uploaded_message_info = existing_data["messages"]
    
    print(f"Uploading '{original_filename}' ({file_size / 1024**2:.2f} MB) in {total_parts} parts.")
    service_bot_instance.send_message(user_telegram_id, f"🚀 Starting upload of '{original_filename}' ({total_parts} parts)...")

    try:
        with tqdm(total=total_parts, unit="part", desc="Overall Progress", initial=start_part_index) as pbar:
            part_generator = split_file(file_path, CHUNK_SIZE)
            
            for _ in range(start_part_index):
                next(part_generator)

            for i, chunk_data in enumerate(part_generator, start=start_part_index):
                part_name = f"{original_filename}.part{i + 1}"

                for attempt in range(UPLOAD_RETRIES):
                    try:
                        message = user_bot.send_document(
                            chat_id=user_channel_id,
                            document=chunk_data,
                            visible_file_name=part_name,
                            caption=part_name,
                            timeout=90
                        )
                        uploaded_message_info.append({
                            'message_id': message.id,
                            'file_id': message.document.file_id
                        })
                        upload_db[original_filename] = {
                            "messages": uploaded_message_info,
                            "total_parts": total_parts,
                            "file_size_bytes": file_size,
                        }
                        save_upload_db(upload_db)
                        break  # Success
                    
                    except telebot.apihelper.ApiTelegramException as e:
                        if e.error_code == 429:
                            retry_after = json.loads(e.result.text)['parameters']['retry_after']
                            print(f"\nRate limit hit. Waiting {retry_after}s...")
                            time.sleep(retry_after)
                            continue
                        else:
                            raise e
                    except Exception as e:
                        print(f"\nUpload of {part_name} failed on attempt {attempt + 1}. Error: {e}")
                        if attempt < UPLOAD_RETRIES - 1:
                            time.sleep(5)
                        else:
                            raise e
                
                pbar.update(1)
                # Proactive 1-second delay to avoid rate limiting
                time.sleep(1) 

    except Exception as e:
        print(f"\nUpload process failed critically. Last progress was saved. Error: {e}")
        service_bot_instance.send_message(user_telegram_id, f"❌ Upload for '{original_filename}' failed. Please try again. Last progress has been saved.")
        return False

    print(f"\n✅ Successfully uploaded '{original_filename}'.")
    # Notify the user via the service bot upon successful completion
    service_bot_instance.send_message(user_telegram_id, f"✅ Successfully uploaded '{original_filename}'.")
    return True
