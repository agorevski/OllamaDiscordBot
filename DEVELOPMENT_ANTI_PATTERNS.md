# Development Anti-Patterns in discord_ollama_bot.py

This document catalogs development anti-patterns identified in the Discord Ollama Bot codebase. Each pattern includes severity level, location, problem description, and recommended solutions.

---

## 1. Resource Leaks - Multiple ClientSession Instances

**Severity:** 🔴 High  
**Location:** `OllamaClient` class methods (lines 31, 73, 86)

### Problem
Every method in `OllamaClient` creates a new `aiohttp.ClientSession()` within the method scope:

```python
# In generate() - line 31
async with aiohttp.ClientSession() as session:
    # ...

# In list_models() - line 73
async with aiohttp.ClientSession() as session:
    # ...

# In check_connection() - line 86
async with aiohttp.ClientSession() as session:
    # ...
```

Creating sessions for each request is inefficient and can lead to:
- Resource exhaustion with high traffic
- Connection pool overhead
- Unnecessary TCP handshakes
- Memory leaks if not properly closed

### Best Practice
Create a single session during initialization and reuse it throughout the class lifecycle:

```python
class OllamaClient:
    def __init__(self, host: str):
        self.host = host
        self.api_url = f"{host}/api"
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
```

---

## 2. Import Inside Function

**Severity:** 🟡 Medium  
**Location:** Line 52 inside `generate()` method

### Problem
The `json` module is imported inside an async loop:

```python
async for line in response.content:
    if line:
        try:
            import json  # ❌ Import inside loop
            chunk = json.loads(line.decode('utf-8'))
```

This violates Python conventions and creates unnecessary overhead on every iteration.

### Best Practice
Move all imports to module level (top of file):

```python
import json  # At the top with other imports
```

---

## 3. Missing Type Hints

**Severity:** 🟡 Low-Medium  
**Location:** Throughout `OllamaClient` class

### Problem
Several functions lack complete type hints, particularly the `generate()` method which returns an async generator:

```python
async def generate(
    self,
    model: str,
    prompt: str,
    system: Optional[str] = None,
    context: Optional[List] = None):  # ❌ No return type
```

Inconsistent type hints reduce:
- Code maintainability
- IDE autocomplete support
- Static analysis capabilities

### Best Practice
Add comprehensive type hints for all methods:

```python
from typing import AsyncGenerator, Tuple

async def generate(
    self,
    model: str,
    prompt: str,
    system: Optional[str] = None,
    context: Optional[List] = None
) -> AsyncGenerator[Tuple[str, bool, Optional[List]], None]:
    # ...
```

---

## 4. Global Mutable State

**Severity:** 🔴 Medium-High  
**Location:** Module level (lines 15-17)

### Problem
Three module-level dictionaries store user state:

```python
user_contexts: Dict[int, List[Dict]] = {}
user_models: Dict[int, str] = {}
user_system_prompts: Dict[int, str] = {}
```

Issues with global mutable state:
- Not thread-safe (though asyncio is single-threaded)
- Lost on restart
- Harder to test and mock
- Violates encapsulation principles
- Cannot easily swap implementations

### Best Practice
Encapsulate state in a dedicated class:

```python
class UserStateManager:
    def __init__(self):
        self._contexts: Dict[int, List[Dict]] = {}
        self._models: Dict[int, str] = {}
        self._system_prompts: Dict[int, str] = {}
    
    def get_context(self, user_id: int) -> Optional[List[Dict]]:
        return self._contexts.get(user_id)
    
    def set_context(self, user_id: int, context: List[Dict]) -> None:
        self._contexts[user_id] = context
    
    # ... additional methods
```

---

## 5. Repeated Code - Message Chunking Logic

**Severity:** 🟡 Medium  
**Location:** Lines 179-200 and 212-232

### Problem
Nearly identical message chunking and updating logic appears twice in the `chat()` command:

```python
# First occurrence (streaming updates)
chunks = [display_text[i:i+1900] for i in range(0, len(display_text), 1900)]
for idx, chunk in enumerate(chunks):
    try:
        if idx < len(sent_messages):
            await sent_messages[idx].edit(content=chunk)
        else:
            new_msg = await interaction.followup.send(chunk, ephemeral=True)
            sent_messages.append(new_msg)
    # ... error handling

# Second occurrence (final update) - nearly identical code
```

This violates the DRY (Don't Repeat Yourself) principle.

### Best Practice
Extract into a reusable helper method:

```python
async def update_chunked_messages(
    interaction: discord.Interaction,
    content: str,
    sent_messages: List,
    chunk_size: int = 1900
) -> List:
    """Update or create chunked messages for long content"""
    chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
    
    for idx, chunk in enumerate(chunks):
        try:
            if idx < len(sent_messages):
                await sent_messages[idx].edit(content=chunk)
            else:
                new_msg = await interaction.followup.send(chunk, ephemeral=True)
                sent_messages.append(new_msg)
        except discord.errors.NotFound:
            new_msg = await interaction.followup.send(chunk, ephemeral=True)
            if idx < len(sent_messages):
                sent_messages[idx] = new_msg
            else:
                sent_messages.append(new_msg)
    
    return sent_messages
```

---

## 6. Bare Exception Handling

**Severity:** 🟡 Medium  
**Location:** Lines 199, 224, 227, 243

### Problem
Multiple locations use overly broad exception catching:

```python
# Line 199 - too broad
except Exception as e:
    print(f"Error updating message chunk {idx}: {e}")

# Line 224 - no exception type at all!
except:
    await interaction.followup.send(header + error_msg, ephemeral=True)

# Line 243 - too broad
except Exception as e:
    error_msg = f"❌ Error during streaming: {str(e)}"
```

Catching all exceptions:
- Hides bugs and makes debugging difficult
- Can catch unexpected errors (KeyboardInterrupt, SystemExit, etc.)
- Reduces code reliability

### Best Practice
Catch specific exceptions or log full tracebacks:

```python
import traceback

try:
    # ... code
except discord.errors.NotFound:
    # Handle specific error
    pass
except discord.errors.HTTPException as e:
    # Handle Discord API errors
    print(f"Discord API error: {e}")
except Exception as e:
    # Only as last resort, with full logging
    print(f"Unexpected error: {e}")
    traceback.print_exc()
    raise  # Re-raise after logging
```

---

## 7. Silent Failures

**Severity:** 🟡 Medium  
**Location:** Lines 199, 227

### Problem
Errors are printed to console but execution continues without user notification:

```python
except Exception as e:
    # Log error but continue - user has no visibility!
    print(f"Error updating message chunk {idx}: {e}")
```

Users experience:
- Partial message updates without knowing why
- No indication that something went wrong
- Confusion about incomplete responses

### Best Practice
Accumulate errors and notify users:

```python
errors = []

try:
    # ... operation
except discord.errors.HTTPException as e:
    errors.append(f"Message update failed: {e}")
    print(f"Error updating message chunk {idx}: {e}")

# After loop
if errors:
    await interaction.followup.send(
        f"⚠️ Completed with {len(errors)} error(s):\n" + "\n".join(errors),
        ephemeral=True
    )
```

---

## 8. Hard-Coded Magic Numbers

**Severity:** 🟢 Low  
**Location:** Lines 171, 176, 208

### Problem
Magic numbers reduce code readability:

```python
update_interval = 1.5  # What does 1.5 represent?
chunks = [display_text[i:i+1900] for i in range(0, len(display_text), 1900)]  # Why 1900?
```

### Best Practice
Define as named constants with documentation:

```python
# Discord rate limiting and message constraints
STREAM_UPDATE_INTERVAL = 1.5  # Seconds between updates to respect rate limits
MESSAGE_CHUNK_SIZE = 1900     # Discord limit is 2000, use 1900 for safety margin
MAX_CONTEXT_LENGTH = 4096     # Maximum tokens to keep in conversation context
```

---

## 9. Inconsistent Error Messages

**Severity:** 🟢 Low  
**Location:** Throughout command handlers

### Problem
Error messages use inconsistent emoji, formatting, and styles:

```python
"✓ Switched to model: **{model_name}**"
"❌ Could not retrieve models"
"⚠ No models found"
"✗ Could not connect to Ollama"
"ℹ️ Your conversation context is already empty"
"➤ = currently selected"
```

This reduces user experience consistency and professionalism.

### Best Practice
Create message formatting helpers:

```python
class MessageFormatter:
    @staticmethod
    def success(message: str) -> str:
        return f"✅ {message}"
    
    @staticmethod
    def error(message: str) -> str:
        return f"❌ **Error:** {message}"
    
    @staticmethod
    def warning(message: str) -> str:
        return f"⚠️ **Warning:** {message}"
    
    @staticmethod
    def info(message: str) -> str:
        return f"ℹ️ {message}"
```

---

## 10. Missing Validation

**Severity:** 🟡 Medium  
**Location:** Lines 11-12, 108, throughout

### Problem
No validation of configuration values:

```python
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
OLLAMA_HOST = os.getenv('OLLAMA_HOST')
# No validation that OLLAMA_HOST is a valid URL
# Token format not checked until connection attempt
```

Invalid configuration leads to:
- Cryptic runtime errors
- Difficult debugging
- Poor user experience

### Best Practice
Add validation functions:

```python
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
    
    if errors:
        raise ValueError(f"Configuration errors:\n" + "\n".join(f"- {e}" for e in errors))
    
    return {'token': token, 'host': host}
```

---

## 11. Tight Coupling

**Severity:** 🟡 Medium  
**Location:** `OllamaBot.__init__()` (line 108)

### Problem
`OllamaBot` directly instantiates `OllamaClient`:

```python
class OllamaBot(discord.Client):
    def __init__(self):
        # ...
        self.ollama = OllamaClient(OLLAMA_HOST)  # ❌ Tight coupling
```

This makes:
- Unit testing difficult (can't mock)
- Swapping implementations hard
- Configuration inflexible

### Best Practice
Use dependency injection:

```python
class OllamaBot(discord.Client):
    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.ollama = ollama_client or OllamaClient(OLLAMA_HOST)
        self.default_model = "dolphin24b"

# In main:
if __name__ == "__main__":
    ollama = OllamaClient(OLLAMA_HOST)
    bot = OllamaBot(ollama_client=ollama)
    bot.run(DISCORD_TOKEN)
```

---

## 12. Inefficient Context Storage

**Severity:** 🟢 Low-Medium  
**Location:** `user_contexts` dictionary usage

### Problem
`user_contexts` stores the full context array which can grow unbounded:

```python
user_contexts: Dict[int, List[Dict]] = {}
# Context keeps growing with each message
```

Long conversations can:
- Consume excessive memory
- Slow down API requests (sending large contexts)
- Eventually hit Ollama's context limits

### Best Practice
Implement context trimming:

```python
MAX_CONTEXT_TOKENS = 4096  # or configurable per model

def trim_context(context: List[Dict], max_tokens: int = MAX_CONTEXT_TOKENS) -> List[Dict]:
    """Keep only recent context within token limits"""
    # Implementation depends on tokenizer
    # Simple approach: keep last N entries
    MAX_ENTRIES = 10
    if len(context) > MAX_ENTRIES:
        return context[-MAX_ENTRIES:]
    return context

# When storing context:
if final_context:
    user_contexts[user_id] = trim_context(final_context)
```

---

## Summary by Priority

### 🔴 High Priority (Fix First)
1. **Resource Leaks** - ClientSession management
2. **Import Inside Function** - Move to module level
3. **Global Mutable State** - Encapsulate in classes

### 🟡 Medium Priority (Important)
4. **Repeated Code** - Extract message chunking logic
5. **Bare Exception Handling** - Use specific exceptions
6. **Silent Failures** - Notify users of errors
7. **Missing Validation** - Validate configuration
8. **Tight Coupling** - Use dependency injection

### 🟢 Low Priority (Nice to Have)
9. **Missing Type Hints** - Complete type annotations
10. **Hard-Coded Magic Numbers** - Extract to constants
11. **Inconsistent Error Messages** - Standardize formatting
12. **Inefficient Context Storage** - Add trimming logic

---

## Recommended Refactoring Approach

1. **Phase 1 - Critical Fixes**
   - Fix ClientSession leaks (prevents resource exhaustion)
   - Move import statement (simple, immediate benefit)
   - Add configuration validation (prevents runtime errors)

2. **Phase 2 - Code Quality**
   - Extract duplicate chunking logic (improves maintainability)
   - Improve exception handling (better debugging)
   - Add user error notifications (better UX)

3. **Phase 3 - Architecture**
   - Encapsulate global state (better design)
   - Implement dependency injection (testability)
   - Add complete type hints (tooling support)

4. **Phase 4 - Polish**
   - Extract magic numbers (readability)
   - Standardize messages (consistency)
   - Add context trimming (performance)

Each phase can be implemented independently and tested before moving to the next.
