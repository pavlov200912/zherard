#!/usr/bin/env python3
"""
Telegram bot that translates unknown phrases using OpenAI and sends them to Anki.
"""
import os
import logging
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

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
# Set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Get environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANKI_CONNECT_URL = os.getenv("ANKI_CONNECT_URL", "http://localhost:8765")
ANKI_DECK_NAME = os.getenv("ANKI_DECK_NAME")
ANKI_NOTE_TYPE = os.getenv("ANKI_NOTE_TYPE", "Basic")
ANKI_FRONT_FIELD = os.getenv("ANKI_FRONT_FIELD", "Front")
ANKI_BACK_FIELD = os.getenv("ANKI_BACK_FIELD", "Back")
ANKI_SENTENCE_FIELD = os.getenv("ANKI_SENTENCE_FIELD", "Sentence")

# Initialize OpenAI client
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

async def translate_with_openai(text, additional_prompt=""):
    """Translate text using OpenAI."""

    prompt = f"""
        You are a helpful translator. Translate the following text to French or from French to Russian (or English if the word is makes more sense in English) and provide a brief explanation or context if relevant.
    The sentence should always be in French. 
    {additional_prompt}
    You are used for Telegram Bot with Anki card, so keep the reponse sturctured as follows:

    Request: la table
    Translation: [ENG] the table
    Sentence: J'ai posé mon livre sur la table. 

    Request: арбуз
    Translation: [FRE] la pastèque
    Sentence: Cette pastèque est très mûre.

    Request: {text}
    """

    try:
        logger.info(f"Translating with OpenAI prompt: {prompt}")
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ],
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error translating with OpenAI: {e}")
        return f"Error translating: {str(e)}"

async def add_to_anki(front, back, sentence=""):
    """Add a new card to Anki via AnkiConnect."""
    try:
        fields = {
            ANKI_FRONT_FIELD: front,
            ANKI_BACK_FIELD: back
        }

        # Add sentence field if provided
        if sentence and ANKI_SENTENCE_FIELD:
            fields[ANKI_SENTENCE_FIELD] = sentence

        payload = {
            "action": "addNote",
            "version": 6,
            "params": {
                "note": {
                    "deckName": ANKI_DECK_NAME,
                    "modelName": ANKI_NOTE_TYPE,
                    "fields": fields,
                    "options": {
                        "allowDuplicate": False
                    },
                    "tags": ["telegram-bot", "auto-generated"]
                }
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(ANKI_CONNECT_URL, json=payload) as response:
                result = await response.json()

        if result.get("error"):
            logger.error(f"Error adding to Anki: {result.get('error')}")
            return False, result.get("error")

        return True, result.get("result")
    except Exception as e:
        logger.error(f"Error connecting to Anki: {e}")
        return False, str(e)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_markdown_v2(
        f'Hi {user.mention_markdown_v2()}\! Send me any phrase you want to translate and add to Anki\.',
        reply_markup=ForceReply(selective=True),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "Send me any phrase you want to translate and add to Anki.\n"
        "Commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/language [language] - Set target language (default: English)"
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
    target_language = context.user_data.get('target_language', 'English')

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
        'prompt': None  # Will be used for retry functionality
    }

    # Create inline keyboard with Add/Discard/Retry options
    keyboard = [
        [
            InlineKeyboardButton("Add", callback_data="add"),
            InlineKeyboardButton("Discard", callback_data="discard"),
            InlineKeyboardButton("Retry", callback_data="retry")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send the translation with the options
    response = f"Translation result:\n\n📝 Original: {text}\n\n🔄 Translation: {translation}\n\n📋 Example: {sentence}\n\nWhat would you like to do?"
    await update.message.reply_text(response, reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks from inline keyboards."""
    query = update.callback_query
    await query.answer()  # Answer the callback query to stop the loading animation

    # Get the current translation data from user context
    translation_data = context.user_data.get('current_translation', {})
    if not translation_data:
        await query.edit_message_text("Translation data not found. Please try again.")
        return

    original = translation_data.get('original', '')
    translation = translation_data.get('translation', '')
    sentence = translation_data.get('sentence', '')

    # Handle different button actions
    if query.data == "add":
        # Add to Anki
        success, result = await add_to_anki(original, translation, sentence)

        if success:
            response = f"✅ Added to Anki:\n\n📝 Original: {original}\n\n🔄 Translation: {translation}\n\n📋 Example: {sentence}"
        else:
            response = f"❌ Failed to add to Anki: {result}\n\n📝 Original: {original}\n\n🔄 Translation: {translation}\n\n📋 Example: {sentence}"

        await query.edit_message_text(response)

    elif query.data == "discard":
        # Discard the translation
        await query.edit_message_text(f"Translation discarded:\n\n📝 Original: {original}\n\n🔄 Translation: {translation}")

    elif query.data == "retry":
        # Ask for additional context
        await query.edit_message_text(
            f"Please provide additional context or instructions for the translation of:\n\n"
            f"📝 Original: {original}\n\n"
            f"Current translation: {translation}\n\n"
            f"Reply to this message with your additional instructions."
        )

        # Store the message ID to identify the retry request later
        context.user_data['awaiting_retry'] = query.message.message_id

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

    # Send a "typing" action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    # Create a new prompt with the additional context
    enhanced_prompt = (f"This is the retry attempt for the task the original translation was:"
                       f" Request: {original} \n Response: {translation_data['translation']} \n Sentence: {translation_data['sentence']}"
                       f" \n\nAdditional context: {additional_context}")

    # Store the enhanced prompt for reference
    context.user_data['current_translation']['prompt'] = enhanced_prompt

    # Translate with the enhanced prompt
    translation_response = await translate_with_openai(original, enhanced_prompt)

    # Parse the translation response
    translation, sentence = parse_translation_response(translation_response)

    # Update the translation data
    context.user_data['current_translation']['translation'] = translation
    context.user_data['current_translation']['sentence'] = sentence

    # Create inline keyboard with Add/Discard/Retry options
    keyboard = [
        [
            InlineKeyboardButton("Add", callback_data="add"),
            InlineKeyboardButton("Discard", callback_data="discard"),
            InlineKeyboardButton("Retry", callback_data="retry")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send the updated translation with the options
    response = f"Updated translation with additional context:\n\n📝 Original: {original}\n\n🔄 Translation: {translation}\n\n📋 Example: {sentence}\n\nWhat would you like to do?"
    await update.message.reply_text(response, reply_markup=reply_markup)

    # Clear the awaiting_retry flag
    del context.user_data['awaiting_retry']

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Register callback query handler for button presses
    application.add_handler(CallbackQueryHandler(button_callback))

    # Register message handler for retry responses first (to have higher priority)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_retry_response))

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
    if not ANKI_DECK_NAME:
        logger.error("ANKI_DECK_NAME not set in environment variables")
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
