"""Prompt building for LLM Service"""

import random
from typing import Optional, Dict, Any
from .constants import (
    LANGUAGE_INSTRUCTIONS,
    INTENT_SYSTEM_PROMPTS,
    DEFAULT_SYSTEM_PROMPT,
    LEYSCO_PROFILE
)
from .memory import get_conversation_memory
from .utils import get_response_styles


class PromptBuilder:
    """Builds system prompts with context and style variations"""
    
    def __init__(self):
        self._last_response_styles: Dict[str, str] = {}
    
    def _get_response_style(self, intent: str) -> str:
        """Get a varied response style for the intent."""
        styles = get_response_styles()
        intent_styles = styles.get(intent, ["friendly", "helpful", "professional"])
        
        # Get last used style for this intent
        last_style = self._last_response_styles.get(intent)
        
        # Pick a different style if possible
        available_styles = [s for s in intent_styles if s != last_style]
        if not available_styles:
            available_styles = intent_styles
        
        chosen = random.choice(available_styles)
        self._last_response_styles[intent] = chosen
        return chosen
    
    def build(
        self,
        intent: Optional[str] = None,
        db_context: Any = None,
        language: Optional[str] = None,
        session_id: Optional[str] = None,
        user_message: str = "",
        formatted_data: Optional[str] = None
    ) -> str:
        """Build enhanced system prompt with conversation context"""
        parts = []
        
        # Language instruction
        lang_key = (language or "en").lower().strip()
        lang_instruction = LANGUAGE_INSTRUCTIONS.get(lang_key, "")
        if lang_instruction:
            parts.append(f"=== LANGUAGE INSTRUCTION ===\n{lang_instruction}\n")
        
        # Response style for this intent
        intent_key = (intent or "GENERAL").upper()
        style = self._get_response_style(intent_key)
        parts.append(f"=== RESPONSE STYLE ===\nUse a {style} and conversational tone.\n")
        
        # Base identity
        parts.append(
            "You are a friendly, helpful AI assistant for Leysco Limited.\n"
            "You speak like a knowledgeable colleague, not a robot.\n"
        )
        parts.append(f"--- COMPANY PROFILE ---\n{LEYSCO_PROFILE}\n")
        
        # Intent-specific instructions
        intent_instruction = INTENT_SYSTEM_PROMPTS.get(intent_key, DEFAULT_SYSTEM_PROMPT)
        parts.append(f"--- YOUR ROLE ---\n{intent_instruction}\n")
        
        # Conversation history (if available)
        if session_id:
            memory = get_conversation_memory()
            recent_context = memory.get_recent_context(session_id)
            if recent_context:
                parts.append(recent_context)
        
        # Database context
        if formatted_data:
            parts.append(
                f"--- LEYSCO100 SYSTEM DATA ---\n"
                f"The following data was retrieved from the database:\n"
                f"{formatted_data}\n"
                f"Base your answer on this data. Do NOT invent values not shown.\n"
            )
        
        # Final instruction
        parts.append(
            "Remember: Be conversational, friendly, and helpful. "
            "Use natural language like you're talking to a colleague. "
            "Avoid robotic phrases like 'based on the data provided'. "
            "Use **bold** for important numbers and names. "
            "End by asking if they need anything else."
        )
        
        return "\n".join(parts)


# Singleton
_prompt_builder = PromptBuilder()


def get_prompt_builder() -> PromptBuilder:
    """Get global prompt builder instance"""
    return _prompt_builder