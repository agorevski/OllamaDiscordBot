import discord
from discord import app_commands
import aiohttp
import asyncio
import os
import json
import traceback
from dotenv import load_dotenv
from typing import Optional, Dict, List, Tuple
from ollama_client import OllamaClient

from user_state_manager import UserStateManager

# Load environment variables
load_dotenv()

# Constants
MESSAGE_CHUNK_SIZE = 1900  # Discord limit is 2000, use 1900 for safety margin
STREAM_UPDATE_INTERVAL = 1.5  # Seconds between updates to respect rate limits


def validate_config() -> Dict[str, str]:
    """Validate and return configuration values"""
    errors = []
    
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        errors.append("DISCORD_BOT_TOKEN not set")
    elif not token.strip():
        errors.append("DISCORD_BOT_TOKEN is empty")
    
    host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
    if not host.startswith(('http://', 'https://')):
        errors.append(f"OLLAMA_HOST must start with http:// or https://, got: {host}")
    
    default_model = os.getenv('OLLAMA_DEFAULT_MODEL', 'llama2')
    
    if errors:
        for error in errors:
            print(f"❌ Configuration Error: {error}")
        raise ValueError(f"Configuration errors:\n" + "\n".join(f"- {e}" for e in errors))
    
    return {'token': token, 'host': host, 'default_model': default_model}


async def update_chunked_messages(
    interaction: discord.Interaction,
    content: str,
    sent_messages: List[discord.WebhookMessage],
    chunk_size: int = MESSAGE_CHUNK_SIZE
) -> Tuple[List[discord.WebhookMessage], List[str]]:
    """
    Update or create chunked messages for long content.
    
    Returns:
        Tuple of (updated sent_messages list, list of error messages)
    """
    chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
    errors = []
    
    for idx, chunk in enumerate(chunks):
        try:
            if idx < len(sent_messages):
                await sent_messages[idx].edit(content=chunk)
            else:
                new_msg = await interaction.followup.send(chunk, ephemeral=True)
                sent_messages.append(new_msg)
        except discord.errors.NotFound:
            # Message was deleted, create a new one
            try:
                new_msg = await interaction.followup.send(chunk, ephemeral=True)
                if idx < len(sent_messages):
                    sent_messages[idx] = new_msg
                else:
                    sent_messages.append(new_msg)
            except discord.errors.HTTPException as e:
                error_msg = f"Failed to send replacement message chunk {idx}: {e}"
                errors.append(error_msg)
                print(error_msg)
        except discord.errors.HTTPException as e:
            error_msg = f"Discord API error updating chunk {idx}: {e}"
            errors.append(error_msg)
            print(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error updating chunk {idx}: {e}"
            errors.append(error_msg)
            print(error_msg)
            traceback.print_exc()
    
    return sent_messages, errors


# Configuration - validated at startup
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
OLLAMA_DEFAULT_MODEL = os.getenv('OLLAMA_DEFAULT_MODEL', 'llama2')

print(f"Token: {'Set' if DISCORD_TOKEN else 'Not set'}, Ollama Host: {OLLAMA_HOST}")


class OllamaBot(discord.Client):
    def __init__(self, ollama_client: Optional[OllamaClient] = None, ollama_host: str = OLLAMA_HOST):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self._ollama_client = ollama_client  # Injected client (optional)
        self._ollama_host = ollama_host
        self.ollama: Optional[OllamaClient] = None  # Will be initialized in setup_hook
        self.state = UserStateManager()  # Manages per-user state
        self.default_model = OLLAMA_DEFAULT_MODEL  # Default model, will be updated on startup
    
    async def setup_hook(self):
        """Setup the bot and sync commands globally"""
        # Use injected client or create new one
        if self._ollama_client:
            self.ollama = self._ollama_client
            # Assume injected client is already initialized
        else:
            self.ollama = OllamaClient(self._ollama_host)
            await self.ollama.__aenter__()
        
        # Sync commands globally to work across all guilds
        await self.tree.sync()
        print("Commands synced globally (may take ~1 hour to propagate)")
    
    async def close(self):
        """Cleanup resources when bot shuts down"""
        # Only cleanup if we created the client ourselves
        if self.ollama and not self._ollama_client:
            await self.ollama.__aexit__(None, None, None)
        await super().close()


# Initialize bot
bot = OllamaBot()


@bot.event
async def on_ready():
    guild_count = len(bot.guilds)
    guild_names = [guild.name for guild in bot.guilds]
    print(f'{bot.user} has connected to Discord!')
    print(f'Connected to {guild_count} guild(s): {", ".join(guild_names)}')
    
    # Check Ollama connection
    if await bot.ollama.check_connection():
        print(f"✓ Connected to Ollama at {OLLAMA_HOST}")
        
        # Get available models and set default
        models = await bot.ollama.list_models()
        if models:
            bot.default_model = models[0]
            print(f"✓ Available models: {', '.join(models)}")
            print(f"✓ Default model set to: {bot.default_model}")
        else:
            print("⚠ No models found. Please pull a model using 'ollama pull <model_name>'")
    else:
        print(f"✗ Could not connect to Ollama at {OLLAMA_HOST}")
        print("  Make sure Ollama is running with: ollama serve")
    
    print("\nBot is ready! Use slash commands in your Discord server.")


@bot.tree.command(name="chat", description="Chat with Ollama AI")
@app_commands.describe(message="Your message to the AI")
async def chat(interaction: discord.Interaction, message: str):
    """Chat with the current Ollama model with real-time streaming"""
    await interaction.response.defer(ephemeral=True)
    
    user_id = interaction.user.id
    
    # Get user's current model or use default
    model = bot.state.get_model(user_id, bot.default_model)
    
    # Get user's system prompt if set
    system_prompt = bot.state.get_system_prompt(user_id)
    
    # Get user's conversation context
    context = bot.state.get_context(user_id)
    
    # Initialize streaming response
    header = f"**Model:** {model}\n**You:** {message}\n\n**AI:** "
    accumulated_response = ""
    last_update_time = asyncio.get_event_loop().time()
    sent_messages: List[discord.WebhookMessage] = []
    final_context = None
    all_errors: List[str] = []
    
    # Stream the response
    try:
        async for token, is_done, context_data in bot.ollama.generate(
            model=model,
            prompt=message,
            system=system_prompt,
            context=context
        ):
            if is_done:
                final_context = context_data
                break
            
            accumulated_response += token
            current_time = asyncio.get_event_loop().time()
            
            # Update message periodically to show streaming effect
            if current_time - last_update_time >= STREAM_UPDATE_INTERVAL:
                display_text = header + accumulated_response
                sent_messages, errors = await update_chunked_messages(
                    interaction, display_text, sent_messages
                )
                all_errors.extend(errors)
                last_update_time = current_time
        
        # Final update with complete response
        final_display = header + accumulated_response
        
        # Update context
        if final_context:
            bot.state.set_context(user_id, final_context)
        
        # Handle final message display
        sent_messages, errors = await update_chunked_messages(
            interaction, final_display, sent_messages
        )
        all_errors.extend(errors)
        
        # Notify user if there were errors during updates
        if all_errors:
            error_summary = f"\n\n⚠️ Completed with {len(all_errors)} message update error(s)"
            try:
                await interaction.followup.send(error_summary, ephemeral=True)
            except discord.errors.HTTPException:
                print(f"Could not send error summary to user: {all_errors}")
                
    except aiohttp.ClientError as e:
        error_msg = f"❌ Connection error: Could not reach Ollama server. {str(e)}"
        if sent_messages:
            try:
                await sent_messages[0].edit(content=header + error_msg)
            except discord.errors.HTTPException:
                await interaction.followup.send(header + error_msg, ephemeral=True)
        else:
            await interaction.followup.send(header + error_msg, ephemeral=True)
    except discord.errors.HTTPException as e:
        error_msg = f"❌ Discord API error: {str(e)}"
        print(f"Discord API error in chat command: {e}")
        traceback.print_exc()
        try:
            await interaction.followup.send(error_msg, ephemeral=True)
        except discord.errors.HTTPException:
            print("Failed to send error message to user")
    except Exception as e:
        error_msg = f"❌ Unexpected error during streaming: {str(e)}"
        print(f"Unexpected error in chat command: {e}")
        traceback.print_exc()
        if sent_messages:
            try:
                await sent_messages[0].edit(content=header + error_msg)
            except discord.errors.HTTPException:
                try:
                    await interaction.followup.send(header + error_msg, ephemeral=True)
                except discord.errors.HTTPException:
                    print("Failed to send error message to user")
        else:
            try:
                await interaction.followup.send(header + error_msg, ephemeral=True)
            except discord.errors.HTTPException:
                print("Failed to send error message to user")


@bot.tree.command(name="switch_model", description="Switch to a different Ollama model")
@app_commands.describe(model_name="Name of the model to switch to")
async def switch_model(interaction: discord.Interaction, model_name: str):
    """Switch to a different model"""
    await interaction.response.defer(ephemeral=True)
    
    # Get available models
    try:
        models = await bot.ollama.list_models()
    except aiohttp.ClientError as e:
        await interaction.followup.send(
            f"❌ Could not connect to Ollama: {str(e)}",
            ephemeral=True
        )
        return
    
    if not models:
        await interaction.followup.send(
            "❌ Could not retrieve models from Ollama. Make sure Ollama is running.",
            ephemeral=True
        )
        return
    
    # Check if model exists
    if model_name not in models:
        await interaction.followup.send(
            f"❌ Model '{model_name}' not found.\n\nAvailable models:\n" + "\n".join(f"• {m}" for m in models),
            ephemeral=True
        )
        return
    
    # Switch model for this user
    user_id = interaction.user.id
    bot.state.set_model(user_id, model_name)
    
    # Clear conversation context when switching models
    bot.state.clear_context(user_id)
    
    await interaction.followup.send(
        f"✅ Switched to model: **{model_name}**\nConversation context has been reset.",
        ephemeral=True
    )


@bot.tree.command(name="list_models", description="List all available Ollama models")
async def list_models(interaction: discord.Interaction):
    """List all available models"""
    await interaction.response.defer(ephemeral=True)
    
    try:
        models = await bot.ollama.list_models()
    except aiohttp.ClientError as e:
        await interaction.followup.send(
            f"❌ Could not connect to Ollama: {str(e)}",
            ephemeral=True
        )
        return
    
    if not models:
        await interaction.followup.send(
            "❌ No models found. Make sure Ollama is running and you have pulled at least one model.\n\n"
            "Pull a model with: `ollama pull llama2`",
            ephemeral=True
        )
        return
    
    user_id = interaction.user.id
    current_model = bot.state.get_model(user_id, bot.default_model)
    
    model_list = "\n".join(f"{'➤' if m == current_model else '•'} {m}" for m in models)
    
    await interaction.followup.send(
        f"**Available Ollama Models:**\n{model_list}\n\n(➤ = currently selected)",
        ephemeral=True
    )


@bot.tree.command(name="current_model", description="Show your currently selected model")
async def current_model(interaction: discord.Interaction):
    """Show current model"""
    user_id = interaction.user.id
    model = bot.state.get_model(user_id, bot.default_model)
    
    system_prompt = bot.state.get_system_prompt(user_id) or "None"
    has_context = bot.state.has_context(user_id)
    
    await interaction.response.send_message(
        f"**Current Settings:**\n"
        f"• Model: **{model}**\n"
        f"• System Prompt: {system_prompt if system_prompt != 'None' else 'None'}\n"
        f"• Conversation Context: {'Active' if has_context else 'Empty'}",
        ephemeral=True
    )


@bot.tree.command(name="system_prompt", description="Set a custom system prompt")
@app_commands.describe(prompt="The system prompt to use (leave empty to clear)")
async def system_prompt(interaction: discord.Interaction, prompt: Optional[str] = None):
    """Set or clear system prompt"""
    user_id = interaction.user.id
    
    if prompt:
        bot.state.set_system_prompt(user_id, prompt)
        await interaction.response.send_message(
            f"✅ System prompt set to:\n```{prompt}```",
            ephemeral=True
        )
    else:
        bot.state.clear_system_prompt(user_id)
        await interaction.response.send_message(
            "✅ System prompt cleared. Using model defaults.",
            ephemeral=True
        )
    
    # Clear context when changing system prompt
    bot.state.clear_context(user_id)


@bot.tree.command(name="clear_context", description="Clear your conversation context")
async def clear_context(interaction: discord.Interaction):
    """Clear conversation context"""
    user_id = interaction.user.id
    
    if bot.state.clear_context(user_id):
        await interaction.response.send_message(
            "✅ Conversation context cleared. Starting fresh!",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "ℹ️ Your conversation context is already empty.",
            ephemeral=True
        )


@bot.tree.command(name="help", description="Show bot usage information")
async def help_command(interaction: discord.Interaction):
    """Show help information"""
    help_text = """
**Discord Ollama Bot Commands**

All responses are private (only you can see them).

**Chat Commands:**
• `/chat <message>` - Chat with the AI
• `/clear_context` - Start a fresh conversation

**Model Management:**
• `/list_models` - See all available models
• `/switch_model <name>` - Change to a different model
• `/current_model` - View your current settings

**Advanced:**
• `/system_prompt <prompt>` - Set custom behavior for the AI
• `/help` - Show this help message

**Tips:**
- Each user has their own conversation context
- Context is maintained across messages for continuity
- Switch models anytime without affecting other users
- System prompts let you customize AI behavior
"""
    
    await interaction.response.send_message(help_text, ephemeral=True)


# Run the bot
if __name__ == "__main__":
    # Validate configuration before starting
    try:
        config = validate_config()
    except ValueError as e:
        print(f"\n{e}")
        print("\nPlease create a .env file with your configuration")
        exit(1)
    
    print("Starting bot with multi-guild support...")
    print("Note: Commands are synced globally and work across all guilds")
    
    # Create bot with dependency injection support
    ollama_client = OllamaClient(config['host'])
    bot = OllamaBot(ollama_host=config['host'])
    bot.run(config['token'])
