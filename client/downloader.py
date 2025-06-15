# client/downloader.py
import os
import sys
import json
import requests
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# This allows the script to find our other project modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- CONFIGURATION & CONSTANTS ---
DOWNLOAD_FOLDER = "downloads"
CONCURRENT_DOWNLOADS = 10 # A stable number for concurrent downloads

# --- Self-Contained Join Function ---
def join_files_here(parts_list, output_file):
    print("\nJoining parts...")
    with open(output_file, 'wb') as outfile:
        for part_path in tqdm(parts_list, desc="Joining"):
            with open(part_path, 'rb') as part_file:
                outfile.write(part_file.read())
    return output_file

# --- Worker function for concurrent downloading ---
def download_part_worker(bot_token, file_id, part_path):
    """This function runs in a separate thread to download one part."""
    try:
        file_info_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
        file_info_res = requests.get(file_info_url, timeout=20).json()
        
        if not file_info_res.get('ok'):
            raise Exception(f"API Error: {file_info_res.get('description')}")
        
        file_path_on_server = file_info_res['result']['file_path']
        file_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path_on_server}"
        
        response = requests.get(file_url, stream=True, timeout=60)
        response.raise_for_status()
        
        with open(part_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return part_path
    except Exception as e:
        print(f"\nError downloading part with file_id {file_id}: {e}")
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
                    pbar.update(1)

        if len(results) != total_parts:
            print(f"\nError: Download failed. Expected {total_parts} parts, but only got {len(results)}.")
            return False

        # Sort the paths by part index before joining
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
            for i in range(total_parts):
                part_path = os.path.join(temp_download_dir, f"part_{i}")
                if os.path.exists(part_path):
                    os.remove(part_path)
            if not os.listdir(temp_download_dir):
                os.rmdir(temp_download_dir)
