#!/usr/bin/env python3
"""
Telegram bot that translates unknown phrases using OpenAI and stores them in a queue for later addition to Anki.
"""
import os
import logging
import json
import datetime
import threading
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, ForceReply, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from openai import AsyncOpenAI
import aiohttp
from flask import Flask, request, jsonify

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
# Set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Create logs directory if it doesn't exist
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

# Create a directory for the card queue if it doesn't exist
queue_dir = Path("card_queue")
queue_dir.mkdir(exist_ok=True)

# Queue file path
QUEUE_FILE = queue_dir / "pending_cards.json"

# API settings
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "5000"))
API_SECRET = os.getenv("API_SECRET", "change_this_in_production")

# Function to log data to JSON file
def log_to_file(data, log_type):
    """
    Log data to a JSON file in the logs directory.

    Args:
        data (dict): The data to log
        log_type (str): Type of log entry (e.g., 'openai_request', 'openai_response', 'user_message')
    """
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    log_file = logs_dir / f"{today}.json"

    # Add timestamp and log type
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "type": log_type,
        "data": data
    }

    # Append to the log file
    with open(log_file, "a") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

# Get environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANKI_DECK_NAME = os.getenv("ANKI_DECK_NAME")
ANKI_NOTE_TYPE = os.getenv("ANKI_NOTE_TYPE", "Basic")
ANKI_FRONT_FIELD = os.getenv("ANKI_FRONT_FIELD", "Front")
ANKI_BACK_FIELD = os.getenv("ANKI_BACK_FIELD", "Back")
ANKI_SENTENCE_FIELD = os.getenv("ANKI_SENTENCE_FIELD", "Sentence")

# Initialize OpenAI client
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Queue management functions
def load_queue():
    """Load the card queue from file."""
    if not QUEUE_FILE.exists():
        return []

    try:
        with open(QUEUE_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.error("Error decoding queue file. Starting with empty queue.")
        return []
    except Exception as e:
        logger.error(f"Error loading queue: {e}")
        return []

def save_queue(queue):
    """Save the card queue to file."""
    try:
        with open(QUEUE_FILE, 'w') as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving queue: {e}")

def add_to_queue(card_data):
    """Add a card to the queue."""
    queue = load_queue()

    # Generate a unique ID for the card
    card_id = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{len(queue)}"
    card_data["id"] = card_id
    card_data["timestamp"] = datetime.datetime.now().isoformat()
    card_data["status"] = "pending"

    queue.append(card_data)
    save_queue(queue)

    return card_id

def mark_card_as_added(card_id):
    """Mark a card as added in the queue."""
    queue = load_queue()

    for card in queue:
        if card["id"] == card_id:
            card["status"] = "added"
            card["added_at"] = datetime.datetime.now().isoformat()
            save_queue(queue)
            return True

    return False

def get_pending_cards():
    """Get all pending cards from the queue."""
    queue = load_queue()
    return [card for card in queue if card["status"] == "pending"]

async def translate_with_openai(text, target_language="French", additional_prompt=""):
    """Translate text using OpenAI."""

    # Determine language settings based on target_language
    if target_language == "German":
        target_lang = "German"
        example_lang = "German"
        example_sentence_lang = "German"
        from_lang = "Russian (or English if the word makes more sense in English)"
    else:  # Default to French
        target_lang = "French"
        example_lang = "French"
        example_sentence_lang = "French"
        from_lang = "Russian (or English if the word makes more sense in English)"

    # Create examples based on target language
    if target_lang == "German":
        example1_request = "der Tisch"
        example1_translation = "[RUS] стол"
        example1_sentence = "Ich habe mein Buch auf den Tisch gelegt."

        example2_request = "арбуз"
        example2_translation = "[GER] die Wassermelone"
        example2_sentence = "Diese Wassermelone ist sehr reif."
    else:  # French examples
        example1_request = "la table"
        example1_translation = "[ENG] the table"
        example1_sentence = "J'ai posé mon livre sur la table."

        example2_request = "арбуз"
        example2_translation = "[FRE] la pastèque"
        example2_sentence = "Cette pastèque est très mûre."

    prompt = f"""
        You are a helpful translator. Translate the following text to {target_lang} or from {target_lang} to {from_lang} and provide a brief explanation or context if relevant.
    The sentence should always be in {example_sentence_lang}.
    {additional_prompt}
    You are used for Telegram Bot with Anki card, so keep the response structured as follows:

    Request: {example1_request}
    Translation: {example1_translation}
    Sentence: {example1_sentence}

    Request: {example2_request}
    Translation: {example2_translation}
    Sentence: {example2_sentence}

    Request: {text}

    """

    try:

        # Log the request to OpenAI
        request_data = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ],
            "max_tokens": 150
        }
        log_to_file(request_data, "openai_request")

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ],
            max_tokens=150
        )

        # Log the response from OpenAI
        response_data = {
            "content": response.choices[0].message.content.strip(),
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }
        log_to_file(response_data, "openai_response")

        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error translating with OpenAI: {e}")

        # Log the error
        error_data = {
            "error": str(e),
            "text": text,
            "additional_prompt": additional_prompt
        }
        log_to_file(error_data, "openai_error")

        return f"Error translating: {str(e)}"

def load_user_configs():
    """Load user configurations from the user_configs.json file."""
    try:
        with open("user_configs.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Return default configs if file doesn't exist or is invalid
        return {"default": {"deck_name": "Default", "note_type": "Basic"}}

def save_user_configs(configs):
    """Save user configurations to the user_configs.json file."""
    with open("user_configs.json", "w") as f:
        json.dump(configs, indent=2)

def get_user_config(user_id):
    """Get the configuration for a specific user."""
    configs = load_user_configs()
    user_id_str = str(user_id) if user_id else "default"

    # Return user-specific config if it exists, otherwise return default
    return configs.get(user_id_str, configs.get("default", {"deck_name": "Default", "note_type": "Basic"}))

def update_user_config(user_id, deck_name, note_type):
    """Update the configuration for a specific user."""
    configs = load_user_configs()
    user_id_str = str(user_id) if user_id else "default"

    # Update or create user config
    configs[user_id_str] = {
        "deck_name": deck_name,
        "note_type": note_type
    }

    save_user_configs(configs)

async def queue_card_for_anki(front, back, sentence="", user_id=None):
    """Queue a card for later addition to Anki."""
    try:
        # Get user-specific Anki configuration
        user_config = get_user_config(user_id)

        # Create card data
        card_data = {
            "deck_name": user_config["deck_name"],
            "model_name": user_config["note_type"],
            "fields": {
                ANKI_FRONT_FIELD: front,
                ANKI_BACK_FIELD: back
            },
            "tags": ["telegram-bot", "auto-generated"],
            "user_id": user_id
        }

        # Add sentence field if provided
        if sentence and ANKI_SENTENCE_FIELD:
            card_data["fields"][ANKI_SENTENCE_FIELD] = sentence

        # Log the card data
        log_to_file(card_data, "card_queued")

        # Add to queue
        card_id = add_to_queue(card_data)

        return True, card_id
    except Exception as e:
        logger.error(f"Error queueing card: {e}")

        # Log the error
        error_data = {
            "error": str(e),
            "front": front,
            "back": back,
            "sentence": sentence
        }
        log_to_file(error_data, "queue_error")

        return False, str(e)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user

    # Create inline keyboard with language options
    keyboard = [
        [
            InlineKeyboardButton("French", callback_data="lang_French"),
            InlineKeyboardButton("German", callback_data="lang_German")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Set default language if not already set
    if 'target_language' not in context.user_data:
        context.user_data['target_language'] = 'French'

    # Reset the setup state
    context.user_data['setup_state'] = 'language'

    await update.message.reply_markdown_v2(
        f'Hi {user.mention_markdown_v2()}\! Please select your target language:',
        reply_markup=reply_markup,
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "Send me any phrase you want to translate and add to Anki.\n"
        "Commands:\n"
        "/start - Start the bot and configure your Anki settings\n"
        "/help - Show this help message\n"
        "/language [language] - Set target language (French or German)\n"
        "/config - Configure your Anki deck name and note type"
    )

def parse_translation_response(response_text):
    """Parse the translation response from OpenAI."""
    lines = response_text.strip().split('\n')
    translation = ""
    sentence = ""

    for line in lines:
        if line.startswith("Translation:"):
            # Extract translation without language tag
            translation_text = line.replace("Translation:", "").strip()
            # Remove language tag if present
            if "[" in translation_text and "]" in translation_text:
                translation = translation_text.split("]", 1)[1].strip()
            else:
                translation = translation_text
        elif line.startswith("Sentence:"):
            sentence = line.replace("Sentence:", "").strip()

    return translation, sentence

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the user message."""
    text = update.message.text
    target_language = context.user_data.get('target_language', 'French')

    # Check if we're in the setup process
    setup_state = context.user_data.get('setup_state', None)

    if setup_state == 'deck_name':
        # User is providing their Anki deck name
        context.user_data['temp_deck_name'] = text

        # Create confirmation keyboard
        keyboard = [
            [
                InlineKeyboardButton("Confirm", callback_data="confirm_deck"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Ask for confirmation
        await update.message.reply_text(
            f"You entered: {text}\n\nIs this the correct Anki deck name?",
            reply_markup=reply_markup
        )
        return

    elif setup_state == 'note_type':
        # User is providing their Anki note type
        context.user_data['temp_note_type'] = text

        # Create confirmation keyboard
        keyboard = [
            [
                InlineKeyboardButton("Confirm", callback_data="confirm_note_type"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Ask for confirmation
        await update.message.reply_text(
            f"You entered: {text}\n\nIs this the correct Anki note type?",
            reply_markup=reply_markup
        )
        return

    # Normal message handling (translation)
    # Log the user message
    user_data = {
        "user_id": update.effective_user.id,
        "username": update.effective_user.username,
        "message": text,
        "chat_id": update.effective_chat.id,
        "target_language": target_language
    }
    log_to_file(user_data, "user_message")

    # Send a "typing" action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    # Translate the text
    translation_response = await translate_with_openai(text, target_language)

    # Parse the translation response
    translation, sentence = parse_translation_response(translation_response)

    # Store the translation data in the user's context
    context.user_data['current_translation'] = {
        'original': text,
        'translation': translation,
        'sentence': sentence,
        'prompt': None,  # Will be used for retry functionality
        'flipped': False  # Track if the card is flipped
    }

    # Create inline keyboard with Add/Discard/Retry/Flip options
    keyboard = [
        [
            InlineKeyboardButton("Add", callback_data="add"),
            InlineKeyboardButton("Discard", callback_data="discard"),
            InlineKeyboardButton("Retry", callback_data="retry"),
            InlineKeyboardButton("Flip", callback_data="flip")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send the translation with the options
    response = f"Translation result (Flipped: No):\n\n📝 Front: {text}\n\n🔄 Back: {translation}\n\n📋 Example: {sentence}\n\nWhat would you like to do?"
    await update.message.reply_text(response, reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks from inline keyboards."""
    query = update.callback_query
    await query.answer()  # Answer the callback query to stop the loading animation

    # Check if this is a language selection callback
    if query.data.startswith("lang_"):
        # Extract the language from the callback data
        selected_language = query.data.replace("lang_", "")

        # Set the language in user data
        context.user_data['target_language'] = selected_language

        # Log the language selection
        language_data = {
            "user_id": update.effective_user.id,
            "username": update.effective_user.username,
            "action": "language_selection",
            "selected_language": selected_language
        }
        log_to_file(language_data, "user_action")

        # Update the message to confirm language selection and ask for Anki deck name
        await query.edit_message_text(
            f"Target language set to {selected_language}.\n\n"
            f"Please enter your Anki deck name (e.g., 'French::Vocabulary'):"
        )

        # Update setup state to wait for deck name
        context.user_data['setup_state'] = 'deck_name'
        return

    # Check if this is an Anki deck name confirmation
    if query.data == "confirm_deck":
        # Get the deck name from user data
        deck_name = context.user_data.get('temp_deck_name', 'Default')

        # Ask for note type
        await query.edit_message_text(
            f"Anki deck name set to: {deck_name}\n\n"
            f"Please enter your Anki note type (e.g., 'Basic', 'Basic with Sentence'):"
        )

        # Update setup state to wait for note type
        context.user_data['setup_state'] = 'note_type'
        return

    # Check if this is an Anki note type confirmation
    if query.data == "confirm_note_type":
        # Get the note type from user data
        note_type = context.user_data.get('temp_note_type', 'Basic')
        deck_name = context.user_data.get('temp_deck_name', 'Default')

        # Save user configuration
        update_user_config(
            update.effective_user.id,
            deck_name,
            note_type
        )

        # Log the configuration
        config_data = {
            "user_id": update.effective_user.id,
            "username": update.effective_user.username,
            "action": "anki_config_update",
            "deck_name": deck_name,
            "note_type": note_type
        }
        log_to_file(config_data, "user_action")

        # Complete the setup
        await query.edit_message_text(
            f"Setup complete!\n\n"
            f"Target language: {context.user_data.get('target_language', 'French')}\n"
            f"Anki deck name: {deck_name}\n"
            f"Anki note type: {note_type}\n\n"
            f"You can now send me any phrase you want to translate and add to Anki."
        )

        # Clear temporary data
        if 'temp_deck_name' in context.user_data:
            del context.user_data['temp_deck_name']
        if 'temp_note_type' in context.user_data:
            del context.user_data['temp_note_type']
        if 'setup_state' in context.user_data:
            del context.user_data['setup_state']

        return

    # Handle other button actions (for translations)
    # Get the current translation data from user context
    translation_data = context.user_data.get('current_translation', {})
    if not translation_data:
        await query.edit_message_text("Translation data not found. Please try again.")
        return

    original = translation_data.get('original', '')
    translation = translation_data.get('translation', '')
    sentence = translation_data.get('sentence', '')

    # Log the user action
    action_data = {
        "user_id": update.effective_user.id,
        "username": update.effective_user.username,
        "action": query.data,
        "original": original,
        "translation": translation,
        "sentence": sentence
    }
    log_to_file(action_data, "user_action")

    # Handle different button actions
    if query.data == "add":
        # Check if the card is flipped
        flipped = translation_data.get('flipped', False)

        # Determine which is front and which is back based on flipped state
        front = translation if flipped else original
        back = original if flipped else translation

        # Queue the card for later addition to Anki
        success, result = await queue_card_for_anki(
            front, 
            back, 
            sentence, 
            user_id=update.effective_user.id
        )

        if success:
            response = f"✅ Queued for Anki (Flipped: {'Yes' if flipped else 'No'}):\n\n📝 Front: {front}\n\n🔄 Back: {back}\n\n📋 Example: {sentence}\n\nThe card will be added to Anki when your local helper syncs."
        else:
            response = f"❌ Failed to queue for Anki: {result} (Flipped: {'Yes' if flipped else 'No'}):\n\n📝 Front: {front}\n\n🔄 Back: {back}\n\n📋 Example: {sentence}"

        await query.edit_message_text(response)

    elif query.data == "discard":
        # Check if the card is flipped
        flipped = translation_data.get('flipped', False)

        # Determine which is front and which is back based on flipped state
        front = translation if flipped else original
        back = original if flipped else translation

        # Discard the translation
        await query.edit_message_text(f"Translation discarded (Flipped: {'Yes' if flipped else 'No'}):\n\n📝 Front: {front}\n\n🔄 Back: {back}")

    elif query.data == "retry":
        # Check if the card is flipped
        flipped = translation_data.get('flipped', False)

        # Determine which is front and which is back based on flipped state
        front = translation if flipped else original
        back = original if flipped else translation

        # Ask for additional context
        await query.edit_message_text(
            f"Please provide additional context or instructions for the translation (Flipped: {'Yes' if flipped else 'No'}):\n\n"
            f"📝 Front: {front}\n\n"
            f"Current back: {back}\n\n"
            f"Reply to this message with your additional instructions."
        )

        # Store the message ID to identify the retry request later
        context.user_data['awaiting_retry'] = query.message.message_id

    elif query.data == "flip":
        # Flip the original and translation
        flipped = translation_data.get('flipped', False)

        # Toggle the flipped state
        flipped = not flipped
        context.user_data['current_translation']['flipped'] = flipped

        # Create the keyboard again
        keyboard = [
            [
                InlineKeyboardButton("Add", callback_data="add"),
                InlineKeyboardButton("Discard", callback_data="discard"),
                InlineKeyboardButton("Retry", callback_data="retry"),
                InlineKeyboardButton("Flip", callback_data="flip")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Determine which is front and which is back based on flipped state
        front = translation if flipped else original
        back = original if flipped else translation

        # Update the message with flipped content
        response = f"Translation result (Flipped: {'Yes' if flipped else 'No'}):\n\n📝 Front: {front}\n\n🔄 Back: {back}\n\n📋 Example: {sentence}\n\nWhat would you like to do?"
        await query.edit_message_text(response, reply_markup=reply_markup)

async def handle_retry_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the user's response to a retry request."""
    # Check if we're awaiting a retry response
    if 'awaiting_retry' not in context.user_data or 'current_translation' not in context.user_data:
        # If not, handle as a normal message
        await handle_message(update, context)
        return

    # Get the additional context provided by the user
    additional_context = update.message.text

    # Get the original translation data
    translation_data = context.user_data['current_translation']
    original = translation_data['original']

    # Log the retry attempt
    retry_data = {
        "user_id": update.effective_user.id,
        "username": update.effective_user.username,
        "original": original,
        "previous_translation": translation_data.get('translation', ''),
        "previous_sentence": translation_data.get('sentence', ''),
        "additional_context": additional_context
    }
    log_to_file(retry_data, "retry_attempt")

    # Send a "typing" action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    # Create a new prompt with the additional context
    enhanced_prompt = (f"This is the retry attempt for the task the original translation was:"
                       f" Request: {original} \n Response: {translation_data['translation']} \n Sentence: {translation_data['sentence']}"
                       f" \n\nAdditional context: {additional_context}")

    # Store the enhanced prompt for reference
    context.user_data['current_translation']['prompt'] = enhanced_prompt

    # Get the user's target language
    target_language = context.user_data.get('target_language', 'French')

    # Translate with the enhanced prompt and target language
    # Pass the target language and enhanced prompt as separate parameters
    translation_response = await translate_with_openai(original, target_language, enhanced_prompt)

    # Parse the translation response
    translation, sentence = parse_translation_response(translation_response)

    # Update the translation data
    context.user_data['current_translation']['translation'] = translation
    context.user_data['current_translation']['sentence'] = sentence
    # Preserve the flipped state (if it doesn't exist, it will default to False)

    # Create inline keyboard with Add/Discard/Retry/Flip options
    keyboard = [
        [
            InlineKeyboardButton("Add", callback_data="add"),
            InlineKeyboardButton("Discard", callback_data="discard"),
            InlineKeyboardButton("Retry", callback_data="retry"),
            InlineKeyboardButton("Flip", callback_data="flip")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Check if the card is flipped
    flipped = context.user_data['current_translation'].get('flipped', False)

    # Determine which is front and which is back based on flipped state
    front = translation if flipped else original
    back = original if flipped else translation

    # Send the updated translation with the options
    response = f"Updated translation with additional context (Flipped: {'Yes' if flipped else 'No'}):\n\n📝 Front: {front}\n\n🔄 Back: {back}\n\n📋 Example: {sentence}\n\nWhat would you like to do?"
    await update.message.reply_text(response, reply_markup=reply_markup)

    # Clear the awaiting_retry flag
    del context.user_data['awaiting_retry']

# Flask API for the local helper
app = Flask(__name__)

@app.route('/api/cards/pending', methods=['GET'])
def get_pending_cards_api():
    """API endpoint to get pending cards."""
    # Check API secret
    if request.headers.get('X-API-Secret') != API_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    pending_cards = get_pending_cards()
    return jsonify(pending_cards)

@app.route('/api/cards/mark-added', methods=['POST'])
def mark_cards_as_added_api():
    """API endpoint to mark cards as added."""
    # Check API secret
    if request.headers.get('X-API-Secret') != API_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    if not data or 'card_ids' not in data:
        return jsonify({"error": "Missing card_ids parameter"}), 400

    card_ids = data['card_ids']
    results = {}

    for card_id in card_ids:
        results[card_id] = mark_card_as_added(card_id)

    return jsonify({"results": results})

def run_flask_app():
    """Run the Flask app in a separate thread."""
    # Try the configured port first
    port = API_PORT
    max_port_attempts = 10  # Try up to 10 ports (API_PORT to API_PORT+9)

    for attempt in range(max_port_attempts):
        try:
            if attempt > 0:
                logger.info(f"Trying alternative port: {port}")
            # Log the actual port being used
            if attempt == 0:
                logger.info(f"API server starting on {API_HOST}:{port}")
            else:
                logger.info(f"API server starting on alternative port {API_HOST}:{port}")

            app.run(host=API_HOST, port=port)
            # If we get here, the app started successfully (this won't actually be reached due to app.run blocking)
            return port
        except OSError as e:
            if "Address already in use" in str(e):
                if attempt < max_port_attempts - 1:
                    # Try the next port
                    port += 1
                else:
                    # We've tried all ports and none worked
                    logger.warning(f"API server could not start: Tried ports {API_PORT} to {port}, but all are in use. The API will not be available.")
                    return None
            else:
                logger.error(f"API server error: {e}")
                return None  # For other errors, don't try more ports

async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Configure Anki settings."""
    user_id = update.effective_user.id
    user_config = get_user_config(user_id)

    # Start the configuration process
    context.user_data['setup_state'] = 'deck_name'

    await update.message.reply_text(
        f"Current Anki configuration:\n"
        f"Deck name: {user_config['deck_name']}\n"
        f"Note type: {user_config['note_type']}\n\n"
        f"Let's update your configuration.\n\n"
        f"Please enter your Anki deck name (e.g., 'French::Vocabulary'):"
    )

async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the target language."""
    # Check if a language was provided
    if context.args and len(context.args) > 0:
        requested_language = context.args[0].capitalize()

        # Validate the language
        if requested_language in ["French", "German"]:
            # Set the language in user data
            context.user_data['target_language'] = requested_language
            await update.message.reply_text(f"Target language set to {requested_language}.")
        else:
            # Create inline keyboard with language options
            keyboard = [
                [
                    InlineKeyboardButton("French", callback_data="lang_French"),
                    InlineKeyboardButton("German", callback_data="lang_German")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "Please select a valid language:",
                reply_markup=reply_markup
            )
    else:
        # If no language was provided, show the current language and options
        current_language = context.user_data.get('target_language', 'French')

        # Create inline keyboard with language options
        keyboard = [
            [
                InlineKeyboardButton("French", callback_data="lang_French"),
                InlineKeyboardButton("German", callback_data="lang_German")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"Current target language: {current_language}\nSelect a new language:",
            reply_markup=reply_markup
        )

def main() -> None:
    """Start the bot and API server."""
    # Create the Application and pass it your bot's token
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("language", language_command))
    application.add_handler(CommandHandler("config", config_command))

    # Register callback query handler for button presses
    application.add_handler(CallbackQueryHandler(button_callback))

    # Register message handler for retry responses first (to have higher priority)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_retry_response))

    # Log bot startup
    startup_data = {
        "bot_token_available": bool(TELEGRAM_BOT_TOKEN),
        "openai_api_key_available": bool(OPENAI_API_KEY),
        "anki_field_names": {
            "front": ANKI_FRONT_FIELD,
            "back": ANKI_BACK_FIELD,
            "sentence": ANKI_SENTENCE_FIELD
        },
        "api_host": API_HOST,
        "api_port": API_PORT,
        "environment": {
            "python_version": os.sys.version,
            "platform": os.sys.platform
        }
    }
    log_to_file(startup_data, "bot_startup")

    # Start the Flask app in a separate thread
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()
    # Note: The actual port being used will be logged in the run_flask_app function

    # Start the Bot
    logger.info("Bot started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set in environment variables")
        exit(1)
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not set in environment variables")
        exit(1)
    if not ANKI_FRONT_FIELD:
        logger.error("ANKI_FRONT_FIELD not set in environment variables")
        exit(1)
    if not ANKI_BACK_FIELD:
        logger.error("ANKI_BACK_FIELD not set in environment variables")
        exit(1)
    if not ANKI_SENTENCE_FIELD:
        logger.error("ANKI_SENTENCE_FIELD not set in environment variables")
        exit(1)

    main()
