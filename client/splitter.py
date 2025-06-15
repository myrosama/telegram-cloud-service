# client/splitter.py
import os

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

def join_files(parts_list, output_file):
    """Joins a list of file parts back into a single file."""
    with open(output_file, 'wb') as outfile:
        for part_path in parts_list:
            with open(part_path, 'rb') as part_file:
                outfile.write(part_file.read())
    return output_file
