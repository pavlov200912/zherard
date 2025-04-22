#!/usr/bin/env python3
"""
Helper script that syncs pending cards from the server to Anki.
This script can run on a remote server and connect to a local Anki instance via SSH tunnel.

To set up the SSH tunnel from your local machine to the remote server:
    ssh -R 8765:localhost:8765 username@remote_server_ip

This creates a reverse tunnel that forwards requests to port 8765 on the remote server
to port 8765 on your local machine where Anki Connect is running.
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

def is_anki_running():
    """Check if Anki is running by testing the AnkiConnect API."""
    try:
        payload = {
            "action": "version",
            "version": 6
        }
        response = requests.post(ANKI_CONNECT_URL, json=payload, timeout=5)
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
        # Extract card data
        deck_name = card_data.get("deck_name")
        model_name = card_data.get("model_name")
        fields = card_data.get("fields", {})
        tags = card_data.get("tags", [])

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

        # Send request to AnkiConnect
        response = requests.post(ANKI_CONNECT_URL, json=payload, timeout=10)
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
    # Check if Anki is running
    if not is_anki_running():
        logger.info("Anki is not running. Skipping this sync.")
        return

    # Get pending cards
    pending_cards = get_pending_cards()
    if not pending_cards:
        logger.info("No pending cards found.")
        return

    logger.info(f"Found {len(pending_cards)} pending cards to process.")

    # Process each card
    successful_card_ids = []
    for card in pending_cards:
        card_id = card.get("id")
        if not card_id:
            logger.warning("Card missing ID, skipping.")
            continue

        logger.info(f"Processing card {card_id}")
        success, result = add_card_to_anki(card)

        if success:
            logger.info(f"Successfully added card {card_id} to Anki.")
            successful_card_ids.append(card_id)
        else:
            # If the error is about duplicate, we can consider it as "added"
            if "already exists" in str(result).lower() or "duplicate" in str(result).lower():
                logger.info(f"Card {card_id} already exists in Anki, marking as added.")
                successful_card_ids.append(card_id)
            else:
                logger.error(f"Failed to add card {card_id}: {result}")

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
    logger.info(f"AnkiConnect URL: {ANKI_CONNECT_URL}")
    logger.info(f"Check interval: {CHECK_INTERVAL} seconds")

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
