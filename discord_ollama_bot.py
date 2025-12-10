import discord
from discord import app_commands
import aiohttp
import asyncio
import os
from dotenv import load_dotenv
from typing import Optional, Dict, List

# Load environment variables
load_dotenv()

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
OLLAMA_HOST = os.getenv('OLLAMA_HOST')

print(f"Token: {'Set' if DISCORD_TOKEN else 'Not set'}, Ollama Host: {OLLAMA_HOST}")

# Store user conversations and settings
user_contexts: Dict[int, List[Dict]] = {}
user_models: Dict[int, str] = {}
user_system_prompts: Dict[int, str] = {}

class OllamaClient:
    """Client for interacting with local Ollama instance"""

    def __init__(self, host: str):
        self.host = host
        self.api_url = f"{host}/api"

    async def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        context: Optional[List] = None):
        """Generate a response from Ollama with streaming support"""
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": True
            }
            
            if system:
                payload["system"] = system
            
            if context:
                payload["context"] = context
            
            try:
                async with session.post(f"{self.api_url}/generate", json=payload) as response:
                    if response.status == 200:
                        full_response = ""
                        final_context = None
                        
                        # Stream the response line by line
                        async for line in response.content:
                            if line:
                                try:
                                    import json
                                    chunk = json.loads(line.decode('utf-8'))
                                    token = chunk.get('response', '')
                                    full_response += token
                                    
                                    # Get context from final chunk
                                    if chunk.get('done', False):
                                        final_context = chunk.get('context')
                                    
                                    # Yield each token as it arrives
                                    if token:
                                        yield token, False, final_context
                                except json.JSONDecodeError:
                                    continue
                        
                        # Signal completion
                        yield '', True, final_context
                    else:
                        error_text = await response.text()
                        yield f"Error: Ollama returned status {response.status}: {error_text}", True, None
            except aiohttp.ClientError as e:
                yield f"Error connecting to Ollama: {str(e)}", True, None
    
    async def list_models(self) -> List[str]:
        """Get list of available models"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.api_url}/tags") as response:
                    if response.status == 200:
                        data = await response.json()
                        return [model['name'] for model in data.get('models', [])]
                    else:
                        return []
            except aiohttp.ClientError:
                return []
    
    async def check_connection(self) -> bool:
        """Check if Ollama is accessible"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.host}") as response:
                    return response.status == 200
            except aiohttp.ClientError:
                return False

class OllamaBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.ollama = OllamaClient(OLLAMA_HOST)
        self.default_model = "dolphin24b"  # Default model, will be updated on startup
    
    async def setup_hook(self):
        """Setup the bot and sync commands globally"""
        # Sync commands globally to work across all guilds
        await self.tree.sync()
        print("Commands synced globally (may take ~1 hour to propagate)")

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
    model = user_models.get(user_id, bot.default_model)
    
    # Get user's system prompt if set
    system_prompt = user_system_prompts.get(user_id)
    
    # Get user's conversation context
    context = user_contexts.get(user_id)
    
    # Initialize streaming response
    header = f"**Model:** {model}\n**You:** {message}\n\n**AI:** "
    accumulated_response = ""
    last_update_time = asyncio.get_event_loop().time()
    update_interval = 1.5  # Update every 1.5 seconds to respect rate limits
    sent_messages = []  # Track all messages (for multi-part responses)
    final_context = None
    
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
            if current_time - last_update_time >= update_interval or is_done:
                display_text = header + accumulated_response
                
                # Split content into chunks of 1900 characters
                chunks = [display_text[i:i+1900] for i in range(0, len(display_text), 1900)]
                
                # Update or create messages for each chunk
                for idx, chunk in enumerate(chunks):
                    try:
                        if idx < len(sent_messages):
                            # Update existing message
                            await sent_messages[idx].edit(content=chunk)
                        else:
                            # Create new message for additional chunk
                            new_msg = await interaction.followup.send(chunk, ephemeral=True)
                            sent_messages.append(new_msg)
                    except discord.errors.NotFound:
                        # Message was deleted, create a new one
                        new_msg = await interaction.followup.send(chunk, ephemeral=True)
                        if idx < len(sent_messages):
                            sent_messages[idx] = new_msg
                        else:
                            sent_messages.append(new_msg)
                    except Exception as e:
                        # Log error but continue
                        print(f"Error updating message chunk {idx}: {e}")
                
                last_update_time = current_time
        
        # Final update with complete response
        final_display = header + accumulated_response
        
        # Update context
        if final_context:
            user_contexts[user_id] = final_context
        
        # Handle final message display with same multi-chunk logic
        final_chunks = [final_display[i:i+1900] for i in range(0, len(final_display), 1900)]
        
        for idx, chunk in enumerate(final_chunks):
            try:
                if idx < len(sent_messages):
                    # Update existing message with final content
                    await sent_messages[idx].edit(content=chunk)
                else:
                    # Create new message if we need more chunks than before
                    new_msg = await interaction.followup.send(chunk, ephemeral=True)
                    sent_messages.append(new_msg)
            except discord.errors.NotFound:
                # Message was deleted, create a new one
                new_msg = await interaction.followup.send(chunk, ephemeral=True)
                if idx < len(sent_messages):
                    sent_messages[idx] = new_msg
                else:
                    sent_messages.append(new_msg)
            except Exception as e:
                print(f"Error in final update for chunk {idx}: {e}")
                
    except Exception as e:
        error_msg = f"❌ Error during streaming: {str(e)}"
        if sent_messages:
            try:
                await sent_messages[0].edit(content=header + error_msg)
            except:
                await interaction.followup.send(header + error_msg, ephemeral=True)
        else:
            await interaction.followup.send(header + error_msg, ephemeral=True)

@bot.tree.command(name="switch_model", description="Switch to a different Ollama model")
@app_commands.describe(model_name="Name of the model to switch to")
async def switch_model(interaction: discord.Interaction, model_name: str):
    """Switch to a different model"""
    await interaction.response.defer(ephemeral=True)
    
    # Get available models
    models = await bot.ollama.list_models()
    
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
    user_models[user_id] = model_name
    
    # Clear conversation context when switching models
    if user_id in user_contexts:
        del user_contexts[user_id]
    
    await interaction.followup.send(
        f"✓ Switched to model: **{model_name}**\nConversation context has been reset.",
        ephemeral=True
    )

@bot.tree.command(name="list_models", description="List all available Ollama models")
async def list_models(interaction: discord.Interaction):
    """List all available models"""
    await interaction.response.defer(ephemeral=True)
    
    models = await bot.ollama.list_models()
    
    if not models:
        await interaction.followup.send(
            "❌ No models found. Make sure Ollama is running and you have pulled at least one model.\n\n"
            "Pull a model with: `ollama pull llama2`",
            ephemeral=True
        )
        return
    
    user_id = interaction.user.id
    current_model = user_models.get(user_id, bot.default_model)
    
    model_list = "\n".join(f"{'➤' if m == current_model else '•'} {m}" for m in models)
    
    await interaction.followup.send(
        f"**Available Ollama Models:**\n{model_list}\n\n(➤ = currently selected)",
        ephemeral=True
    )

@bot.tree.command(name="current_model", description="Show your currently selected model")
async def current_model(interaction: discord.Interaction):
    """Show current model"""
    user_id = interaction.user.id
    model = user_models.get(user_id, bot.default_model)
    
    system_prompt = user_system_prompts.get(user_id, "None")
    has_context = user_id in user_contexts and len(user_contexts[user_id]) > 0
    
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
        user_system_prompts[user_id] = prompt
        await interaction.response.send_message(
            f"✓ System prompt set to:\n```{prompt}```",
            ephemeral=True
        )
    else:
        if user_id in user_system_prompts:
            del user_system_prompts[user_id]
        await interaction.response.send_message(
            "✓ System prompt cleared. Using model defaults.",
            ephemeral=True
        )
    
    # Clear context when changing system prompt
    if user_id in user_contexts:
        del user_contexts[user_id]

@bot.tree.command(name="clear_context", description="Clear your conversation context")
async def clear_context(interaction: discord.Interaction):
    """Clear conversation context"""
    user_id = interaction.user.id
    
    if user_id in user_contexts:
        del user_contexts[user_id]
        await interaction.response.send_message(
            "✓ Conversation context cleared. Starting fresh!",
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
    if not DISCORD_TOKEN:
        print("Error: DISCORD_BOT_TOKEN not found in environment variables")
        print("Please create a .env file with your bot token")
        exit(1)
    
    print("Starting bot with multi-guild support...")
    print("Note: Commands are synced globally and work across all guilds")
    bot.run(DISCORD_TOKEN)
