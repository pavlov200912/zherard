# Telegram Translation Bot with Anki Integration

A Telegram bot that translates unknown phrases using OpenAI and sends them to your Anki deck for language learning.

## Features

- Translate phrases from any language using OpenAI's GPT models
- Automatically add translations to your Anki deck
- Customize the target language for translations
- Simple and intuitive Telegram interface

## Requirements

- Python 3.7+
- Telegram Bot Token (from [BotFather](https://t.me/botfather))
- OpenAI API Key
- Anki with [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on installed

## Setup

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/telegram-translation-bot.git
   cd telegram-translation-bot
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file based on the `.env.example` template:
   ```
   cp .env.example .env
   ```

4. Edit the `.env` file with your credentials:
   ```
   # Telegram Bot Token (get from BotFather)
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

   # OpenAI API Key
   OPENAI_API_KEY=your_openai_api_key_here

   # Anki Connect settings
   ANKI_CONNECT_URL=http://localhost:8765
   ANKI_DECK_NAME=your_anki_deck_name
   ANKI_NOTE_TYPE=Basic (or your custom note type)
   ANKI_FRONT_FIELD=Front
   ANKI_BACK_FIELD=Back
   ANKI_SENTENCE_FIELD=Sentence
   ```

5. Make sure Anki is running with AnkiConnect add-on installed.

## Usage

1. Start the bot:
   ```
   python main.py
   ```

2. Open Telegram and start a conversation with your bot.

3. Use the following commands:
   - `/start` - Start the bot
   - `/help` - Show help message
   - `/language [language]` - Set target language (default: English)

4. Send any phrase you want to translate, and the bot will:
   - Translate it using OpenAI
   - Add it to your Anki deck
   - Reply with the translation

## Anki Setup

### Installing Anki
1. Download Anki from the official website: [https://apps.ankiweb.net/](https://apps.ankiweb.net/)
   - Windows: Download and run the installer
   - macOS: Download the .dmg file, open it, and drag Anki to your Applications folder
   - Linux: Follow the instructions on the download page for your distribution

2. Install Anki by following the installation prompts for your operating system.

### Installing AnkiConnect Add-on
1. Open Anki after installation.
2. Go to `Tools` > `Add-ons` > `Get Add-ons...`
3. Enter the AnkiConnect code: `2055492159`
4. Click `OK` to install the add-on.
5. Restart Anki to complete the installation.

### Setting Up Your Deck
1. In Anki, click `Create Deck` at the bottom of the window.
2. Name your deck to match the `ANKI_DECK_NAME` in your `.env` file (e.g., `French::Telegram`).
3. If you're using a nested deck structure (like `French::Telegram`), first create the parent deck (`French`), then create the child deck by naming it with the full path.

### Running Anki Server
1. Make sure Anki is running whenever you use the bot.
2. AnkiConnect runs automatically in the background when Anki is open.
3. By default, AnkiConnect listens on `http://localhost:8765` (this should match your `ANKI_CONNECT_URL` in the `.env` file).
4. You can verify AnkiConnect is working by opening a web browser and navigating to `http://localhost:8765`. If it's working, you'll see a blank page or a JSON response.

### Creating a Custom Note Type with Sentence Field
1. In Anki, click on `Tools` > `Manage Note Types`.
2. Click `Add` to create a new note type.
3. Select `Clone: Basic` (or any other note type you want to base it on).
4. Give it a name (e.g., `Basic with Sentence`) and click `OK`.
5. Select your new note type from the list and click `Fields`.
6. Click `Add` and name the new field `Sentence` (or whatever you specified in your `.env` file).
7. Click `Save` to save your changes.
8. Click `Cards` to customize how the sentence appears on your cards.
9. In the card template, you can add the sentence field using `{{Sentence}}` in the front or back template.
10. Click `Save` when you're done.
11. Update your `.env` file to use the new note type:
    ```
    ANKI_NOTE_TYPE=Basic with Sentence
    ANKI_FRONT_FIELD=Front
    ANKI_BACK_FIELD=Back
    ANKI_SENTENCE_FIELD=Sentence
    ```

## Troubleshooting

### Anki Connection Issues
- If the bot can't connect to Anki, make sure:
  - Anki is running and visible on your desktop (not minimized or hidden)
  - AnkiConnect add-on is installed correctly (check Tools > Add-ons to verify)
  - The Anki deck specified in your `.env` file exists exactly as spelled
  - AnkiConnect is listening on the URL specified in your `.env` file (default: http://localhost:8765)
  - Your firewall isn't blocking connections to port 8765
  - You're running the bot on the same machine as Anki, or have configured AnkiConnect for remote access

### AnkiConnect Remote Access (Optional)
If you need to run the bot on a different machine than Anki:
1. In Anki, go to Tools > Add-ons > AnkiConnect > Config
2. Change the configuration to:
   ```json
   {
     "webBindAddress": "0.0.0.0",
     "webBindPort": 8765
   }
   ```
3. Restart Anki
4. Update your `.env` file to use the IP address of the machine running Anki:
   ```
   ANKI_CONNECT_URL=http://your_anki_machine_ip:8765
   ```

### Common Error Messages
- "Failed to connect to Anki" - Anki is not running or AnkiConnect is not installed
- "Deck not found" - The deck name in your `.env` file doesn't match any deck in Anki
- "Note type not found" - The note type specified doesn't exist in your Anki collection
- "Field 'Sentence' not found" - The sentence field name in your `.env` file doesn't match any field in your note type

### Translation Issues
- If translations aren't working, check:
  - Your OpenAI API key is valid
  - You have sufficient credits in your OpenAI account
  - Your internet connection is stable

## License

MIT
