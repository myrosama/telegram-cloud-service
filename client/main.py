# client/main.py
import os
import sys
import telebot
import time
import uuid

# This allows the script to find our other project modules
# In a real packaged app, this would be handled differently, but it's good for development.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    # We need the service bot's token to communicate with it.
    from bot.config import BOT_TOKEN as SERVICE_BOT_TOKEN
except ImportError:
    print("---FATAL ERROR---")
    print("Could not import the service bot's token from bot/config.py.")
    print("Please ensure the 'bot' folder from the service repository is available.")
    sys.exit(1)

# --- Configuration ---
# Path to a file that will store this client's unique ID
CLIENT_ID_FILE = "client_id.txt"

# --- Client Identity Functions ---
def get_client_id():
    """Gets the unique ID for this client, creating one if it doesn't exist."""
    if os.path.exists(CLIENT_ID_FILE):
        with open(CLIENT_ID_FILE, 'r') as f:
            return f.read().strip()
    else:
        # Generate a new unique ID and save it
        client_id = str(uuid.uuid4())
        with open(CLIENT_ID_FILE, 'w') as f:
            f.write(client_id)
        print(f"First time run: Generated a new unique Client ID: {client_id}")
        return client_id

# --- Main Application Logic ---
def main():
    """The main function for the client daemon."""
    client_id = get_client_id()
    
    print("="*40)
    print("  Telegram Cloud Client Daemon")
    print(f"  Client ID: {client_id}")
    print("="*40)

    try:
        # Note: We are using the SERVICE_BOT_TOKEN here to listen for commands
        bot = telebot.TeleBot(SERVICE_BOT_TOKEN)
        bot.get_me()
        print("Successfully connected to the main service bot.")
        print("This application will now run in the background and wait for commands.")
        print("You can now use your bot on Telegram to manage your files.")
        print("(Press Ctrl+C to exit)")

    except Exception as e:
        print("\n---FATAL CONNECTION ERROR---")
        print("Could not connect to the main service bot.")
        print(f"Error: {e}")
        return

    # In a real GUI application, this would be a proper background loop.
    # For our console app, we can just use a simple loop to keep it running.
    # We will replace this later with actual command polling.
    while True:
        try:
            # This is a placeholder for where the app will ask the bot for new commands
            time.sleep(10) 
        except KeyboardInterrupt:
            print("\nExiting daemon.")
            break

if __name__ == "__main__":
    main()
