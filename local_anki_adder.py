#!/usr/bin/env python3
"""
Helper script that syncs pending cards from the server to Anki.
This script can run on a remote server and connect to a local Anki instance via SSH tunnel.

Each user is automatically assigned a unique Anki Connect port based on their position in the user_configs.json file.
The default port is 8765, and each user gets the next available port (e.g., 8766, 8767, etc.).

To set up the SSH tunnel from your local machine to the remote server for a specific user:
    ssh -R <user_port>:localhost:<user_port> username@remote_server_ip

For example, for the first user (assigned port 8766):
    ssh -R 8766:localhost:8766 username@remote_server_ip

This creates a reverse tunnel that forwards requests to the specified port on the remote server
to the same port on your local machine where Anki Connect is running.

You can check the assigned port for each user in the logs when this script starts.
"""
import os
import sys
import json
import time
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path.home() / "anki_adder.log")
    ]
)
logger = logging.getLogger(__name__)

# Get environment variables
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:5000")
API_SECRET = os.getenv("API_SECRET", "change_this_in_production")
ANKI_CONNECT_URL = os.getenv("ANKI_CONNECT_URL", "http://localhost:8765")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "15"))  # Default: 10 minutes


# Path to user configurations file
USER_CONFIG_FILE = Path("user_configs.json")

def load_user_configs():
    """Load user-specific Anki configurations from JSON file."""
    with open(USER_CONFIG_FILE, 'r') as f:
        configs = json.load(f)
    logger.info(f"Loaded user configurations for {len(configs)} users")
    return configs

# Load user configurations
USER_CONFIGS = load_user_configs()

def get_anki_connect_url(user_id=None):
    """Get the Anki Connect URL for a specific user."""
    # Default Anki Connect URL
    base_url = os.getenv("ANKI_CONNECT_URL", "http://localhost:8765")
    base_port = 8765  # Default Anki Connect port

    # If no user_id is provided, return the default URL
    if not user_id:
        return base_url

    # Extract the protocol and hostname from the base URL
    if "://" in base_url:
        protocol, rest = base_url.split("://", 1)
        hostname = rest.split(":", 1)[0] if ":" in rest else rest.split("/", 1)[0]

        # Get all user IDs from the config
        user_ids = list(USER_CONFIGS.keys())

        # Skip 'default' if it exists
        if 'default' in user_ids:
            user_ids.remove('default')

        # Find the index of the current user_id in the list
        try:
            user_index = user_ids.index(str(user_id))
            # Calculate port: base_port + (index + 1)
            # This ensures the first user gets port 8766, second gets 8767, etc.
            user_port = base_port + (user_index + 1)
            logger.info(f"Assigned port {user_port} to user {user_id} (index {user_index})")
        except ValueError:
            # If user_id not found in the list, use default port
            user_port = base_port
            logger.info(f"User {user_id} not found in config, using default port {user_port}")

        # Construct the URL with the calculated port
        return f"{protocol}://{hostname}:{user_port}"

    return base_url

def is_anki_running(user_id=None):
    """Check if Anki is running by testing the AnkiConnect API for a specific user."""
    try:
        payload = {
            "action": "version",
            "version": 6
        }
        anki_url = get_anki_connect_url(user_id)
        response = requests.post(anki_url, json=payload, timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def get_server_url_with_fallback():
    """Get the server URL, trying alternative ports if the main one fails."""
    # Parse the base URL and port
    base_url = SERVER_URL

    # If the connection fails, try alternative ports
    if ":" in base_url:
        # Extract the port from the URL
        base_parts = base_url.split(":")
        if len(base_parts) >= 3:  # http:// + hostname + port
            try:
                # Get the protocol and hostname
                protocol_hostname = ":".join(base_parts[:-1])
                # Get the port and any path
                port_path = base_parts[-1].split("/", 1)
                port = int(port_path[0])
                path = "/" + port_path[1] if len(port_path) > 1 else ""

                # Return the original URL and a list of alternative URLs to try
                original_url = base_url
                alternative_urls = [
                    f"{protocol_hostname}:{port + i}{path}" for i in range(1, 10)
                ]
                return original_url, alternative_urls
            except (ValueError, IndexError):
                # If there's any error parsing, just return the original URL
                return base_url, []

    # If no port in URL or parsing failed, just return the original URL
    return base_url, []

def get_pending_cards():
    """Fetch pending cards from the server."""
    headers = {"X-API-Secret": API_SECRET}

    # Get the main server URL and alternative URLs to try
    main_url, alternative_urls = get_server_url_with_fallback()

    # Try the main URL first
    try:
        response = requests.get(f"{main_url}/api/cards/pending", headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Error connecting to main server URL {main_url}: {e}")

    # If the main URL fails, try alternative ports
    for alt_url in alternative_urls:
        try:
            logger.info(f"Trying alternative server URL: {alt_url}")
            response = requests.get(f"{alt_url}/api/cards/pending", headers=headers, timeout=5)
            if response.status_code == 200:
                logger.info(f"Successfully connected to alternative server URL: {alt_url}")
                # Update the global SERVER_URL for future requests
                global SERVER_URL
                SERVER_URL = alt_url
                return response.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error connecting to alternative server URL {alt_url}: {e}")

    # If all URLs fail, log an error and return an empty list
    logger.error("Failed to connect to server on all attempted ports")
    return []

def add_card_to_anki(card_data):
    """Add a card to Anki via AnkiConnect."""
    try:
        # Extract user information
        user_id = card_data.get("user_id")

        # Get user-specific configuration if available
        user_config = None
        if user_id:
            # Get config by user_id
            user_config = USER_CONFIGS.get(str(user_id))

        # Extract card data
        deck_name = card_data.get("deck_name")
        model_name = card_data.get("model_name")
        fields = card_data.get("fields", {})
        tags = card_data.get("tags", [])

        # Override with user-specific settings if available
        if user_config:
            # Only override if the user config has these settings
            if "deck_name" in user_config:
                deck_name = user_config["deck_name"]
            if "note_type" in user_config:
                model_name = user_config["note_type"]

            logger.info(f"Using user-specific configuration for user {user_id}")
        else:
            logger.info(f"No user-specific configuration found for user {user_id}, using default")

        # Create AnkiConnect payload
        payload = {
            "action": "addNote",
            "version": 6,
            "params": {
                "note": {
                    "deckName": deck_name,
                    "modelName": model_name,
                    "fields": fields,
                    "options": {
                        "allowDuplicate": False
                    },
                    "tags": tags
                }
            }
        }

        # Get user-specific Anki Connect URL
        anki_url = get_anki_connect_url(user_id)
        logger.info(f"Using Anki Connect URL for user {user_id}: {anki_url}")

        # Send request to AnkiConnect
        response = requests.post(anki_url, json=payload, timeout=10)
        result = response.json()

        if result.get("error"):
            logger.error(f"Error adding to Anki: {result.get('error')}")
            return False, result.get("error")

        return True, result.get("result")
    except Exception as e:
        logger.error(f"Error adding card to Anki: {e}")
        return False, str(e)

def mark_cards_as_added(card_ids):
    """Mark cards as added on the server."""
    if not card_ids:
        return {}

    try:
        headers = {"X-API-Secret": API_SECRET, "Content-Type": "application/json"}
        data = {"card_ids": card_ids}

        # Use the SERVER_URL which might have been updated in get_pending_cards
        response = requests.post(
            f"{SERVER_URL}/api/cards/mark-added", 
            headers=headers, 
            json=data,
            timeout=10
        )

        if response.status_code == 200:
            return response.json().get("results", {})
        else:
            logger.error(f"Failed to mark cards as added: {response.status_code} - {response.text}")
            return {}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error connecting to server: {e}")
        return {}

def process_pending_cards():
    """Process all pending cards."""
    # Get pending cards
    pending_cards = get_pending_cards()
    if not pending_cards:
        logger.info("No pending cards found.")
        return

    logger.info(f"Found {len(pending_cards)} pending cards to process.")

    # Group cards by user_id
    cards_by_user = {}
    for card in pending_cards:
        user_id = card.get("user_id")
        if user_id not in cards_by_user:
            cards_by_user[user_id] = []
        cards_by_user[user_id].append(card)

    # Process cards for each user separately
    successful_card_ids = []
    for user_id, user_cards in cards_by_user.items():
        # Check if Anki is running for this user
        if not is_anki_running(user_id):
            logger.info(f"Anki is not running for user {user_id}. Skipping cards for this user.")
            continue

        logger.info(f"Processing {len(user_cards)} cards for user {user_id}")

        # Process each card for this user
        for card in user_cards:
            card_id = card.get("id")
            if not card_id:
                logger.warning("Card missing ID, skipping.")
                continue

            logger.info(f"Processing card {card_id} for user {user_id}")
            success, result = add_card_to_anki(card)

            if success:
                logger.info(f"Successfully added card {card_id} to Anki for user {user_id}.")
                successful_card_ids.append(card_id)
            else:
                # If the error is about duplicate, we can consider it as "added"
                if "already exists" in str(result).lower() or "duplicate" in str(result).lower():
                    logger.info(f"Card {card_id} already exists in Anki for user {user_id}, marking as added.")
                    successful_card_ids.append(card_id)
                else:
                    logger.error(f"Failed to add card {card_id} for user {user_id}: {result}")

    # Mark successful cards as added
    if successful_card_ids:
        logger.info(f"Marking {len(successful_card_ids)} cards as added on the server.")
        results = mark_cards_as_added(successful_card_ids)

        for card_id, success in results.items():
            if success:
                logger.info(f"Card {card_id} marked as added on server.")
            else:
                logger.warning(f"Failed to mark card {card_id} as added on server.")

def main():
    """Main function to run the script."""
    logger.info("Starting Anki Helper")
    logger.info(f"Server URL: {SERVER_URL}")
    logger.info(f"Default AnkiConnect URL: {ANKI_CONNECT_URL}")
    logger.info(f"Check interval: {CHECK_INTERVAL} seconds")

    # Log user-specific Anki Connect URLs
    logger.info("User-specific Anki Connect URLs:")
    for user_id in USER_CONFIGS.keys():
        if user_id != "default":
            anki_url = get_anki_connect_url(user_id)
            logger.info(f"  User {user_id}: {anki_url}")
        else:
            logger.info(f"  Default: Using default Anki Connect URL")

    # Run once immediately
    process_pending_cards()

    # If this is a one-time run (e.g., from cron/launchd), exit
    if os.getenv("RUN_ONCE", "false").lower() == "true":
        logger.info("RUN_ONCE is set to true. Exiting.")
        return

    # Otherwise, run in a loop
    logger.info(f"Running in continuous mode. Will check every {CHECK_INTERVAL} seconds.")
    while True:
        try:
            time.sleep(CHECK_INTERVAL)
            process_pending_cards()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Exiting.")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            # Sleep a bit to avoid tight error loops
            time.sleep(10)

if __name__ == "__main__":
    main()
