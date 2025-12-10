"""
User State Manager for Discord Ollama Bot

Manages per-user conversation state including:
- Conversation contexts (message history)
- Selected AI models
- Custom system prompts
"""

from typing import Optional, Dict, List


class UserStateManager:
    """Manages per-user conversation state"""
    
    def __init__(self):
        self._contexts: Dict[int, List[Dict]] = {}
        self._models: Dict[int, str] = {}
        self._system_prompts: Dict[int, str] = {}
    
    def get_context(self, user_id: int) -> Optional[List[Dict]]:
        """Get user's conversation context"""
        return self._contexts.get(user_id)
    
    def set_context(self, user_id: int, context: List[Dict]) -> None:
        """Set user's conversation context"""
        self._contexts[user_id] = context
    
    def clear_context(self, user_id: int) -> bool:
        """Clear user's context. Returns True if context existed."""
        return self._contexts.pop(user_id, None) is not None
    
    def has_context(self, user_id: int) -> bool:
        """Check if user has active context"""
        return user_id in self._contexts and len(self._contexts[user_id]) > 0
    
    def get_model(self, user_id: int, default: str) -> str:
        """Get user's selected model or default"""
        return self._models.get(user_id, default)
    
    def set_model(self, user_id: int, model: str) -> None:
        """Set user's selected model"""
        self._models[user_id] = model
    
    def get_system_prompt(self, user_id: int) -> Optional[str]:
        """Get user's system prompt"""
        return self._system_prompts.get(user_id)
    
    def set_system_prompt(self, user_id: int, prompt: str) -> None:
        """Set user's system prompt"""
        self._system_prompts[user_id] = prompt
    
    def clear_system_prompt(self, user_id: int) -> bool:
        """Clear user's system prompt. Returns True if prompt existed."""
        return self._system_prompts.pop(user_id, None) is not None
