# client/splitter.py
import os
import math

# Fixed chunk size: 19MB to be safe for the bot API.
CHUNK_SIZE = int(19 * 1024 * 1024)

def split_file(file_path):
    """
    Splits a file into smaller temporary chunks on disk and returns a list of their paths.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File to split not found: {file_path}")

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        return [], 0 # Return empty list if file is empty
    
    total_parts = math.ceil(file_size / CHUNK_SIZE)
    base_name = os.path.basename(file_path)
    
    # Create a temporary directory for the parts
    temp_dir = f"{file_path}_parts"
    os.makedirs(temp_dir, exist_ok=True)
    
    part_num = 1
    parts_paths = []

    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            
            part_name = f"{base_name}.part{part_num}"
            part_path = os.path.join(temp_dir, part_name)
            
            with open(part_path, 'wb') as pf:
                pf.write(chunk)
            
            parts_paths.append(part_path)
            part_num += 1

    return parts_paths, total_parts
