# client/uploader_bot.py
import os
import sys
import time
import json
import shutil
import math
import telebot
from tqdm import tqdm

# Add the script's own directory to the Python path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Now we can import the local splitter module
from splitter import split_file

# --- Centralized Data Directory ---
DATA_DIR = os.path.join(os.path.expanduser("~"), ".telegram_cloud_service")
# Define the path for the file database for this specific user
# This is now handled within the perform_upload function

# --- Database Functions ---
def load_json_db(path):
    """Safely loads a JSON file."""
    if not os.path.exists(path): return {}
    with open(path, 'r', encoding='utf-8') as f:
        try: return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError): return {}

def save_json_db(data, path):
    """Atomically saves data to a JSON file."""
    temp_path = path + ".tmp"
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    shutil.move(temp_path, path)

# --- CORE UPLOAD LOGIC ---
def perform_upload(user_bot_token, user_channel_id, file_path, service_bot_instance, user_telegram_id):
    """The main function to handle splitting and uploading for a specific user."""
    if not os.path.exists(file_path):
        service_bot_instance.send_message(user_telegram_id, f"❌ Upload failed: File '{os.path.basename(file_path)}' not found on your computer.")
        return False

    print("Connecting with user's bot token...")
    user_bot = telebot.TeleBot(user_bot_token)
    
    original_filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    
    # Define a user-specific database for their uploaded files
    user_files_db_path = os.path.join(DATA_DIR, f"user_{user_telegram_id}_files.json")
    user_files_db = load_json_db(user_files_db_path)
    
    uploaded_message_info = []
    start_part_index = 0

    # Automatic Resume Logic
    if original_filename in user_files_db:
        existing_data = user_files_db[original_filename]
        # Use math.ceil to correctly calculate total parts
        total_parts_calc = math.ceil(file_size / existing_data.get("chunk_size", 19*1024*1024))
        num_parts_on_record = len(existing_data.get("messages", []))
        
        if 0 < num_parts_on_record < total_parts_calc:
            print(f"Found incomplete upload for '{original_filename}'. Automatically resuming from part {num_parts_on_record + 1}.")
            start_part_index = num_parts_on_record
            uploaded_message_info = existing_data["messages"]

    # Step 1: Split file into temporary parts on disk
    try:
        parts_paths, total_parts = split_file(file_path)
        if not parts_paths:
            service_bot_instance.send_message(user_telegram_id, f"⚠️ The file '{original_filename}' is empty. Nothing was uploaded.")
            return True
    except Exception as e:
        service_bot_instance.send_message(user_telegram_id, f"❌ Upload failed: Could not split the file. Error: {e}")
        return False
        
    print(f"Uploading '{original_filename}' ({file_size / 1024**2:.2f} MB) in {total_parts} parts.")
    service_bot_instance.send_message(user_telegram_id, f"🚀 Starting upload of '{original_filename}' ({total_parts} parts)...")
    
    try:
        # Step 2: Upload each part one-by-one from the disk
        with tqdm(total=total_parts, unit="part", desc="Uploading", initial=start_part_index) as pbar:
            for i in range(start_part_index, total_parts):
                part_path = parts_paths[i]
                part_name = os.path.basename(part_path)
                
                # Robust retry loop for each part
                for attempt in range(5):
                    try:
                        with open(part_path, 'rb') as part_file:
                            message = user_bot.send_document(
                                chat_id=user_channel_id,
                                document=part_file,
                                visible_file_name=part_name,
                                caption=part_name,
                                timeout=90
                            )
                        uploaded_message_info.append({
                            'message_id': message.id,
                            'file_id': message.document.file_id
                        })
                        
                        # --- Save progress after EACH successful part ---
                        user_files_db[original_filename] = {
                            "messages": uploaded_message_info,
                            "total_parts": total_parts,
                            "file_size_bytes": file_size,
                            "chunk_size": 19*1024*1024, # Store chunk size for resume calculation
                            "upload_method": "bot"
                        }
                        save_json_db(user_files_db, user_files_db_path)
                        
                        break  # Success, break the retry loop
                    
                    except telebot.apihelper.ApiTelegramException as e:
                        if e.error_code == 429:
                            retry_after = json.loads(e.result.text)['parameters']['retry_after']
                            print(f"\nRate limit hit. Waiting {retry_after}s...")
                            time.sleep(retry_after)
                        else:
                            raise e
                    except Exception as e:
                        print(f"\nUpload of {part_name} failed on attempt {attempt + 1}. Error: {e}")
                        if attempt < 4:
                            time.sleep(5)
                        else:
                            raise e # All retries failed
                else:
                    # This 'else' belongs to the 'for attempt' loop.
                    # It runs if the loop completes without a 'break'.
                    raise Exception(f"Failed to upload part {part_name} after multiple retries.")
                
                pbar.update(1)
                # --- Proactive delay to avoid rate limiting ---
                time.sleep(1)
    
    except Exception as e:
        print(f"\nUpload process failed critically. Error: {e}")
        service_bot_instance.send_message(user_telegram_id, f"❌ Upload for '{original_filename}' failed. Please try again. Your progress has been saved.")
        return False
    
    finally:
        # Step 3: Clean up temporary files
        temp_dir = f"{file_path}_parts"
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            print(f"Cleaned up temporary directory: {temp_dir}")
        
    print(f"\n✅ Successfully uploaded '{original_filename}'.")
    service_bot_instance.send_message(user_telegram_id, f"✅ Successfully uploaded '{original_filename}'.")
    return True
