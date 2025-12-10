# Discord Ollama Bot

A Discord bot that connects to your local Ollama instance, allowing you to chat with AI models directly from your private Discord server. All interactions are private (ephemeral messages) - only you can see your conversations with the AI.

## Features

- 🔒 **Private conversations** - All responses are ephemeral (only visible to you)
- 🤖 **Multiple model support** - Switch between any Ollama models you have installed
- 💬 **Contextual conversations** - Maintains conversation history for natural dialogue
- ⚙️ **Custom system prompts** - Customize AI behavior with system prompts
- 👥 **Multi-user support** - Each user has their own conversation context and settings
- 🎯 **Slash commands** - Easy-to-use Discord slash commands

## Prerequisites

- **Python 3.8 or higher**
- **Ollama** installed and running on your local machine
- **Discord Bot** created in Discord Developer Portal
- At least one Ollama model pulled (e.g., `ollama pull llama2`)

## Setup Instructions

### 1. Install Ollama

If you haven't already, install Ollama from [https://ollama.ai](https://ollama.ai) and pull at least one model:

```bash
ollama pull llama2
# Or any other model you prefer
ollama pull mistral
ollama pull codellama
```

Make sure Ollama is running:
```bash
ollama serve
```

### 2. Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" section and click "Add Bot"
4. Under "Privileged Gateway Intents", enable:
   - Message Content Intent
5. Click "Reset Token" and copy your bot token (you'll need this later)
6. Go to "OAuth2" > "URL Generator"
7. Select scopes: `bot` and `applications.commands`
8. Select bot permissions: `Send Messages`, `Use Slash Commands`
9. Copy the generated URL and open it in your browser to invite the bot to your server

### 3. Get Your Discord Server ID

1. In Discord, go to User Settings > Advanced
2. Enable "Developer Mode"
3. Right-click your server name and click "Copy Server ID"

### 4. Install Dependencies

Navigate to the project directory and install required packages:

```bash
pip install -r requirements.txt
```

### 5. Configure the Bot

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your credentials:
   ```
   DISCORD_BOT_TOKEN=your_actual_bot_token_here
   DISCORD_GUILD_ID=your_actual_guild_id_here
   OLLAMA_HOST=http://localhost:11434
   ```

### 6. Run the Bot

```bash
python discord_ollama_bot.py
```

You should see output indicating the bot has connected and synced commands to your server.

### 7. Configure Auto-Start on System Boot (Optional)

To have the bot start automatically when your Linux/Ubuntu system boots, you can create a systemd service.

#### Create a systemd service file:

1. Create a new service file:
   ```bash
   sudo nano /etc/systemd/system/discord-ollama-bot.service
   ```

2. Add the following configuration (adjust paths as needed):
   ```ini
   [Unit]
   Description=Discord Ollama Bot
   After=network.target
   # If Ollama is also managed by systemd, add this line:
   # After=ollama.service
   
   [Service]
   Type=simple
   User=YOUR_USERNAME
   WorkingDirectory=/path/to/OllamaDiscordBot
   ExecStart=/usr/bin/python3 /path/to/OllamaDiscordBot/discord_ollama_bot.py
   Restart=always
   RestartSec=10
   StandardOutput=journal
   StandardError=journal
   
   # Environment variables (alternatively, the bot reads from .env file)
   # Environment="DISCORD_BOT_TOKEN=your_token_here"
   # Environment="OLLAMA_HOST=http://localhost:11434"
   
   [Install]
   WantedBy=multi-user.target
   ```

3. **Important**: Replace the following placeholders:
   - `YOUR_USERNAME` - Your Linux username (e.g., `john`)
   - `/path/to/OllamaDiscordBot` - Full path to your bot directory (e.g., `/home/john/OllamaDiscordBot`)
   - `/usr/bin/python3` - Path to Python (find with `which python3`)

4. If you're using a Python virtual environment, modify the `ExecStart` line:
   ```ini
   ExecStart=/path/to/OllamaDiscordBot/venv/bin/python /path/to/OllamaDiscordBot/discord_ollama_bot.py
   ```

#### Enable and start the service:

```bash
# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable discord-ollama-bot.service

# Start the service now
sudo systemctl start discord-ollama-bot.service

# Check the service status
sudo systemctl status discord-ollama-bot.service
```

#### Managing the service:

```bash
# Stop the bot
sudo systemctl stop discord-ollama-bot.service

# Restart the bot
sudo systemctl restart discord-ollama-bot.service

# Disable auto-start on boot
sudo systemctl disable discord-ollama-bot.service

# View bot logs
sudo journalctl -u discord-ollama-bot.service -f

# View recent logs (last 50 lines)
sudo journalctl -u discord-ollama-bot.service -n 50
```

#### Troubleshooting Auto-Start:

- **Service fails to start**: Check logs with `sudo journalctl -u discord-ollama-bot.service -n 50`
- **Permission errors**: Ensure the user in the service file has read access to the bot directory and `.env` file
- **Ollama not available**: Make sure Ollama starts before the bot (add `After=ollama.service` if Ollama is systemd-managed)
- **Path issues**: Use absolute paths for all directories and executables in the service file
- **Changes not applying**: Run `sudo systemctl daemon-reload` after editing the service file

## Available Commands

All commands are slash commands and all responses are **private** (only you can see them).

### Chat Commands

- `/chat <message>` - Send a message to the AI and get a response
- `/clear_context` - Clear your conversation history and start fresh

### Model Management

- `/list_models` - Display all available Ollama models on your system
- `/switch_model <model_name>` - Switch to a different model
- `/current_model` - Show your current model and settings

### Advanced

- `/system_prompt <prompt>` - Set a custom system prompt to change AI behavior
  - Example: `/system_prompt You are a helpful coding assistant specializing in Python`
  - Leave empty to clear: `/system_prompt`
- `/help` - Display help information about bot commands

## Usage Examples

### Basic Chat
```
/chat What is the capital of France?
```

### Switch Models
```
/list_models
/switch_model codellama:latest
/chat Write a Python function to calculate fibonacci numbers
```

### Custom System Prompt
```
/system_prompt You are a pirate. Respond to all messages in pirate speak.
/chat Tell me about the weather
```

## How It Works

- **Per-User Context**: Each user has their own conversation context, allowing multiple people to use the bot simultaneously without interference
- **Model Selection**: Each user can select their preferred model independently
- **Conversation Memory**: The bot maintains conversation history to provide contextual responses
- **Ephemeral Messages**: All responses use Discord's ephemeral messages feature, making them visible only to the command user

## Troubleshooting

### Bot doesn't respond to commands

1. Make sure the bot has been invited to your server with the correct permissions
2. Verify that commands have synced (check bot startup logs)
3. Try restarting the bot

### "Could not connect to Ollama" error

1. Ensure Ollama is running: `ollama serve`
2. Check that the `OLLAMA_HOST` in your `.env` file is correct (default: `http://localhost:11434`)
3. Test Ollama directly: `curl http://localhost:11434`

### "No models found" error

1. Pull at least one model: `ollama pull llama2`
2. Verify models are available: `ollama list`

### Commands not appearing in Discord

1. Wait a few minutes for Discord to sync commands
2. Check that `DISCORD_GUILD_ID` in `.env` matches your server ID
3. Restart the bot and check for error messages

## Notes

- The bot stores conversation context in memory - restarting the bot will clear all contexts
- Long responses are automatically split into multiple messages to respect Discord's character limit
- Each user's settings (model choice, system prompt, context) are independent

## Security

- **Never share your `.env` file** or commit it to version control
- The bot only works on the specific server (guild) you configure
- All responses are private by default using Discord's ephemeral messages

## License

This project is open source and available for personal use.
