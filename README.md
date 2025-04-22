# Telegram Translation Bot with Anki Integration

A Telegram bot that translates unknown phrases using OpenAI and sends them to your Anki deck for language learning. The system uses a server-client architecture that allows the bot to run 24/7 on a remote server while syncing with Anki when your local machine is online.

## Features

- Translate phrases from any language using OpenAI's GPT models
- Queue translations on the server and sync to Anki when available
- Automatically add translations to your Anki deck
- Customize the target language for translations
- Simple and intuitive Telegram interface
- 24/7 bot availability even when your local machine is offline

## Requirements

- Python 3.7+
- Telegram Bot Token (from [BotFather](https://t.me/botfather))
- OpenAI API Key
- A server to host the bot (for 24/7 availability)
- A local machine with Anki and [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on installed

## Architecture

The system consists of two main components:

### Standard Setup (Components on Different Machines)

1. **Server Bot (`server_bot.py`)**: 
   - Runs on your remote server
   - Handles Telegram messages
   - Calls OpenAI for translations
   - Stores card data in a queue
   - Exposes an API for the local helper

2. **Local Helper (`local_anki_adder.py`)**: 
   - Runs on your local machine where Anki is installed
   - Checks periodically if Anki is running
   - Fetches pending cards from the server
   - Adds cards to Anki via AnkiConnect
   - Reports back to the server which cards were successfully added

### Alternative Setup (Both Components on Remote Server)

You can also run both components on the remote server and connect to Anki on your local machine via an SSH tunnel:

1. **Server Bot (`server_bot.py`)**: 
   - Runs on your remote server
   - Functions the same as in the standard setup

2. **Local Helper (`local_anki_adder.py`)**: 
   - Also runs on your remote server
   - Connects to AnkiConnect on your local machine via SSH tunnel
   - Otherwise functions the same as in the standard setup

## Setup

### 1. Clone this repository:
```
git clone https://github.com/yourusername/telegram-translation-bot.git
cd telegram-translation-bot
```

### 2. Install the required dependencies:
```
pip install -r requirements.txt
```

### 3. Create a `.env` file based on the `.env.example` template:
```
cp .env.example .env
```

### 4. Edit the `.env` file with your credentials:

For the server:
```
# Telegram Bot Token (get from BotFather)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# OpenAI API Key
OPENAI_API_KEY=your_openai_api_key_here

# Anki settings (still needed for card structure)
ANKI_DECK_NAME=your_anki_deck_name
ANKI_NOTE_TYPE=Basic (or your custom note type)
ANKI_FRONT_FIELD=Front
ANKI_BACK_FIELD=Back
ANKI_SENTENCE_FIELD=Sentence

# API settings
API_HOST=0.0.0.0
API_PORT=5000  # If this port is in use, the server will automatically try ports 5001-5009
API_SECRET=your_secure_secret_here
```

For the local helper (create a separate `.env` file on your local machine):
```
# Server connection
SERVER_URL=http://your_server_ip:5000
API_SECRET=your_secure_secret_here

# Anki Connect settings
ANKI_CONNECT_URL=http://localhost:8765

# Check interval in seconds (default: 600 = 10 minutes)
CHECK_INTERVAL=600

# Set to "true" if you want to run once and exit (useful for cron/launchd)
RUN_ONCE=false
```

### 5. Make sure Anki is installed on your local machine with AnkiConnect add-on.

## Usage

### Standard Setup (Components on Different Machines)

#### Server Setup

1. Deploy the server bot to your remote server.

2. Start the server bot:
   ```
   python server_bot.py
   ```

3. The server will start the Telegram bot and a Flask API server on the specified port.

#### Local Helper Setup

1. Install the local helper on your machine where Anki is installed.

2. Start the local helper:
   ```
   python local_anki_adder.py
   ```

3. The helper will run in the background, periodically checking for new cards to add to Anki.

4. Alternatively, you can set up the helper to run automatically:
   - On macOS: Use launchd (see instructions below)
   - On Windows: Use Task Scheduler
   - On Linux: Use cron or systemd

### Alternative Setup (Both Components on Remote Server)

This setup allows you to run both the server bot and the local helper on the remote server, while still connecting to Anki on your local machine.

#### SSH Tunnel Setup

1. On your local machine (where Anki is installed), set up an SSH tunnel to the remote server:
   ```
   ssh -R 8765:localhost:8765 username@remote_server_ip
   ```
   This creates a reverse tunnel that forwards requests to port 8765 on the remote server to port 8765 on your local machine.

2. For a persistent tunnel that stays connected even if your connection drops, you can use:
   ```
   ssh -R 8765:localhost:8765 -N -o "ServerAliveInterval 60" -o "ExitOnForwardFailure yes" username@remote_server_ip
   ```

3. On macOS or Linux, you can use tools like `autossh` for a more robust tunnel:
   ```
   autossh -M 0 -R 8765:localhost:8765 -N username@remote_server_ip
   ```

#### Remote Server Setup

1. Deploy both `server_bot.py` and `local_anki_adder.py` to your remote server.

2. Configure the `.env` file on the remote server:
   ```
   # Telegram Bot Token (get from BotFather)
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

   # OpenAI API Key
   OPENAI_API_KEY=your_openai_api_key_here

   # Anki settings
   ANKI_DECK_NAME=your_anki_deck_name
   ANKI_NOTE_TYPE=Basic (or your custom note type)
   ANKI_FRONT_FIELD=Front
   ANKI_BACK_FIELD=Back
   ANKI_SENTENCE_FIELD=Sentence

   # API settings
   API_HOST=0.0.0.0
   API_PORT=5000
   API_SECRET=your_secure_secret_here

   # For local_anki_adder.py
   SERVER_URL=http://localhost:5000
   ANKI_CONNECT_URL=http://localhost:8765
   CHECK_INTERVAL=600
   RUN_ONCE=false
   ```

3. Start the server bot:
   ```
   python server_bot.py
   ```

4. Start the local helper:
   ```
   python local_anki_adder.py
   ```

5. Both components will now run on the remote server, with the local helper connecting to Anki on your local machine through the SSH tunnel.

6. Make sure to keep Anki running on your local machine and maintain the SSH tunnel for the system to work properly.

### Using the Bot

1. Open Telegram and start a conversation with your bot.

2. Use the following commands:
   - `/start` - Start the bot
   - `/help` - Show help message
   - `/language [language]` - Set target language (default: English)

3. Send any phrase you want to translate, and the bot will:
   - Translate it using OpenAI
   - Queue it for addition to Anki
   - Reply with the translation

4. The queued cards will be added to Anki the next time your local helper syncs and Anki is running.

### Setting up Automatic Runs on macOS (launchd)

1. Create a plist file in `~/Library/LaunchAgents/com.yourusername.ankiadder.plist`:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
       <key>Label</key>
       <string>com.yourusername.ankiadder</string>
       <key>ProgramArguments</key>
       <array>
           <string>/path/to/python</string>
           <string>/path/to/local_anki_adder.py</string>
       </array>
       <key>StartInterval</key>
       <integer>600</integer>
       <key>RunAtLoad</key>
       <true/>
       <key>StandardOutPath</key>
       <string>/tmp/ankiadder.log</string>
       <key>StandardErrorPath</key>
       <string>/tmp/ankiadder.err</string>
       <key>EnvironmentVariables</key>
       <dict>
           <key>RUN_ONCE</key>
           <string>true</string>
       </dict>
   </dict>
   </plist>
   ```

2. Load the launchd job:
   ```
   launchctl load ~/Library/LaunchAgents/com.yourusername.ankiadder.plist
   ```

3. This will run the helper every 10 minutes (600 seconds).

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

### Server Bot Issues
- If the server bot fails to start:
  - Check that all required environment variables are set in the `.env` file
  - The server will automatically try alternative ports (up to 10 ports) if the default API port is already in use
  - If you see a message like "API server could not start: Tried ports 5000 to 5009, but all are in use", you can:
    - Wait for one of the ports to become available
    - Manually set a different port in the `.env` file (e.g., `API_PORT=6000`)
    - Close applications that might be using those ports
  - Ensure you have proper permissions to create directories for logs and the card queue
  - Check that Flask is installed correctly (`pip install flask`)

- If the API is not accessible:
  - Verify the server's firewall allows connections on the API port
  - Check that `API_HOST` is set to `0.0.0.0` to allow external connections
  - Note that if the default port was in use, the server might be running on an alternative port
  - Check the server logs to see which port was actually used (look for "API server starting on" messages)
  - Update your local helper's `SERVER_URL` to use the correct port
  - Ensure the server has a stable internet connection

### Local Helper Issues
- If the local helper can't connect to the server:
  - Verify the `SERVER_URL` in the local `.env` file is correct
  - The local helper will automatically try alternative ports (up to 10 ports) if the main server URL fails
  - If you see a message like "Trying alternative server URL", it means the helper is attempting to connect to the server on different ports
  - If you see "Successfully connected to alternative server URL", it means the helper found a working port and will use it for future requests
  - Check that the `API_SECRET` matches between server and local helper
  - Ensure the server is running and accessible from your local network
  - Check if any firewalls are blocking the connection

- If cards aren't being added to Anki:
  - Verify Anki is running when the helper checks for cards
  - Check the helper logs for any error messages
  - Ensure AnkiConnect is installed and functioning correctly
  - Verify the deck and note type exist in your Anki collection

### Anki Connection Issues
- If the local helper can't connect to Anki, make sure:
  - Anki is running and visible on your desktop (not minimized or hidden)
  - AnkiConnect add-on is installed correctly (check Tools > Add-ons to verify)
  - The Anki deck specified in your `.env` file exists exactly as spelled
  - AnkiConnect is listening on the URL specified in your `.env` file (default: http://localhost:8765)
  - Your firewall isn't blocking connections to port 8765

### SSH Tunnel Issues (Alternative Setup)
- If you're using the alternative setup with both components on the remote server:
  - Verify the SSH tunnel is active by running `netstat -an | grep 8765` on the remote server
  - If the tunnel is not showing up, try reestablishing it from your local machine
  - Make sure your SSH connection stays alive by using the ServerAliveInterval option
  - Consider using `autossh` for a more robust tunnel that automatically reconnects
  - Check that your local machine's firewall allows incoming connections on the SSH port
  - Ensure Anki is running on your local machine while the tunnel is active
  - If you're getting "Connection refused" errors, check that AnkiConnect is properly installed and Anki is running

### Common Error Messages
- "Failed to connect to server" - The server is not running or not accessible
- "Unauthorized" - The API_SECRET doesn't match between server and local helper
- "Failed to connect to Anki" - Anki is not running or AnkiConnect is not installed
- "Connection refused" - When using SSH tunnel, the tunnel might be down or Anki is not running
- "Deck not found" - The deck name in your `.env` file doesn't match any deck in Anki
- "Note type not found" - The note type specified doesn't exist in your Anki collection
- "Field not found" - A field name in your `.env` file doesn't match any field in your note type
- "Channel closed" - SSH tunnel has been closed, needs to be reestablished

### Translation Issues
- If translations aren't working, check:
  - Your OpenAI API key is valid
  - You have sufficient credits in your OpenAI account
  - Your internet connection is stable

### Debugging
- Check the server logs for API and bot-related issues
- Check the local helper logs (default: `~/anki_adder.log`) for Anki connection issues
- For launchd issues on macOS, check the system logs:
  ```
  log show --predicate 'processImagePath contains "ankiadder"' --last 1h
  ```

## License

MIT
