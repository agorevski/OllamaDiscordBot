"""
User Activity Logger for Discord Ollama Bot

Logs user inputs and model outputs for tracking and analysis.
Logs are stored locally in a rotating file format.
"""

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional


class UserLogger:
    """Handles logging of user interactions with the bot"""
    
    def __init__(self, log_dir: str = "logs", enabled: bool = True):
        """
        Initialize the user logger.
        
        Args:
            log_dir: Directory to store log files
            enabled: Whether logging is enabled
        """
        self.enabled = enabled
        self.log_dir = log_dir
        self.logger: Optional[logging.Logger] = None
        
        if self.enabled:
            self._setup_logger()
    
    def _setup_logger(self) -> None:
        """Set up the rotating file logger"""
        # Create logs directory if it doesn't exist
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Create logger
        self.logger = logging.getLogger("user_activity")
        self.logger.setLevel(logging.INFO)
        
        # Avoid adding duplicate handlers
        if not self.logger.handlers:
            # Create rotating file handler (10MB max, keep 5 backups)
            log_file = os.path.join(self.log_dir, "user_activity.log")
            handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding="utf-8"
            )
            
            # Set format
            formatter = logging.Formatter(
                "%(asctime)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(formatter)
            
            self.logger.addHandler(handler)
    
    def log_interaction(
        self,
        user_id: int,
        username: str,
        guild_name: Optional[str],
        model: str,
        input_message: str,
        output_response: str,
        success: bool = True
    ) -> None:
        """
        Log a user interaction with the bot.
        
        Args:
            user_id: Discord user ID
            username: Discord username
            guild_name: Name of the guild (server), or None for DMs
            model: AI model used
            input_message: User's input message
            output_response: Model's response (truncated if too long)
            success: Whether the interaction was successful
        """
        if not self.enabled or not self.logger:
            return
        
        # Truncate long responses to prevent massive log files
        max_output_length = 5000
        truncated_output = output_response
        if len(output_response) > max_output_length:
            truncated_output = output_response[:max_output_length] + "... [truncated]"
        
        # Escape newlines for cleaner log format
        input_escaped = input_message.replace("\n", "\\n")
        output_escaped = truncated_output.replace("\n", "\\n")
        
        # Build log entry
        status = "SUCCESS" if success else "ERROR"
        guild_display = guild_name or "DM"
        
        log_entry = (
            f"[{status}] "
            f"USER_ID={user_id} "
            f"USERNAME={username} "
            f"GUILD={guild_display} "
            f"MODEL={model} | "
            f"INPUT: {input_escaped} | "
            f"OUTPUT: {output_escaped}"
        )
        
        self.logger.info(log_entry)
    
    def log_error(
        self,
        user_id: int,
        username: str,
        guild_name: Optional[str],
        model: str,
        input_message: str,
        error_message: str
    ) -> None:
        """
        Log an error during user interaction.
        
        Args:
            user_id: Discord user ID
            username: Discord username
            guild_name: Name of the guild (server), or None for DMs
            model: AI model used
            input_message: User's input message
            error_message: Error message
        """
        self.log_interaction(
            user_id=user_id,
            username=username,
            guild_name=guild_name,
            model=model,
            input_message=input_message,
            output_response=f"ERROR: {error_message}",
            success=False
        )
