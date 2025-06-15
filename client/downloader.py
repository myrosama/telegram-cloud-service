# client/downloader.py
import os
import sys
import json
import time
import shutil
import random
import requests
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Add the script's own directory to the Python path ---
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- CONFIGURATION & CONSTANTS ---
DOWNLOAD_FOLDER = "downloads"
# Increased concurrent downloads for more speed
CONCURRENT_DOWNLOADS = 35
DOWNLOAD_RETRIES = 5 # Number of times to retry a failed part download

# --- Self-Contained Join Function ---
def join_files_here(parts_list, output_file):
    """Joins a list of file parts into a single output file."""
    print("\nJoining parts...")
    with open(output_file, 'wb') as outfile:
        for part_path in tqdm(parts_list, desc="Joining"):
            with open(part_path, 'rb') as part_file:
                outfile.write(part_file.read())
    return output_file

# --- Worker function for concurrent downloading with robust retries ---
def download_part_worker(bot_token, file_id, part_path):
    """This function runs in a separate thread to download one part, with smart retries."""
    delay = 3  # Initial delay in seconds for retries
    
    # --- Add a small, random "jitter" to stagger requests ---
    time.sleep(random.uniform(0, 1))

    for attempt in range(DOWNLOAD_RETRIES):
        try:
            # Get file path from Telegram with a longer timeout
            file_info_from_api = requests.get(f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}", timeout=30).json()
            
            if not file_info_from_api.get('ok'):
                description = file_info_from_api.get('description', 'Unknown API Error')
                # If error is "wrong file_id", no point in retrying
                if "wrong file_id" in description:
                    print(f"\n[FATAL] Error for file_id {file_id}: {description}")
                    return None
                raise requests.exceptions.RequestException(f"API Error: {description}")
            
            file_path_on_server = file_info_from_api['result']['file_path']
            file_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path_on_server}"
            
            # Stream the download with a generous timeout
            response = requests.get(file_url, stream=True, timeout=120)
            response.raise_for_status() # Raise an exception for bad status codes
            
            with open(part_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            # Success
            return part_path
        
        except requests.exceptions.RequestException as e:
            print(f"\nWarning: Attempt {attempt + 1}/{DOWNLOAD_RETRIES} failed for a part. Error: {e}")
            if attempt < DOWNLOAD_RETRIES - 1:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff: 3s, 6s, 12s...
            else:
                print(f"\n[FATAL] Failed to download part with file_id {file_id} after {DOWNLOAD_RETRIES} attempts.")
                return None
    return None

# --- CORE DOWNLOAD LOGIC ---
def perform_download(user_bot_token, file_info):
    """The main function to handle downloading and joining for a specific user."""
    file_to_download = file_info['name']
    messages = file_info.get("messages", [])
    if not messages:
        print(f"Error: No message data found for '{file_to_download}'.")
        return False

    total_parts = file_info["total_parts"]
    
    print(f"Starting download for '{file_to_download}' ({total_parts} parts)...")
    print(f"Using up to {CONCURRENT_DOWNLOADS} concurrent connections.")

    temp_download_dir = os.path.join(DOWNLOAD_FOLDER, f"{file_to_download}_parts")
    os.makedirs(temp_download_dir, exist_ok=True)
    
    downloaded_parts_paths = []
    failed_parts = 0

    try:
        with ThreadPoolExecutor(max_workers=CONCURRENT_DOWNLOADS) as executor:
            future_to_part = {
                executor.submit(download_part_worker, user_bot_token, msg_info['file_id'], os.path.join(temp_download_dir, f"part_{i}")): i
                for i, msg_info in enumerate(messages)
            }

            results = {}
            with tqdm(total=total_parts, unit="part", desc=f"Downloading {file_to_download}") as pbar:
                for future in as_completed(future_to_part):
                    part_index = future_to_part[future]
                    result_path = future.result()
                    if result_path:
                        results[part_index] = result_path
                    else:
                        failed_parts += 1
                    pbar.update(1)

        if failed_parts > 0:
            print(f"\nError: Could not download {failed_parts} part(s) after multiple retries. Aborting join process.")
            return False

        print("\nAll parts downloaded successfully. Now joining them...")
        
        # Ensure results are sorted correctly before joining
        sorted_paths = [results[i] for i in sorted(results.keys())]

        final_output_path = os.path.join(DOWNLOAD_FOLDER, file_to_download)
        join_files_here(sorted_paths, final_output_path)

        print(f"\n✅ Success! File '{file_to_download}' reassembled in '{DOWNLOAD_FOLDER}'.")
        return True

    except Exception as e:
        print(f"\n---FATAL DOWNLOAD ERROR---: {e}")
        return False
    finally:
        # Cleanup
        if os.path.exists(temp_download_dir):
            shutil.rmtree(temp_download_dir)
            print(f"Cleaned up temporary directory: {temp_download_dir}")

