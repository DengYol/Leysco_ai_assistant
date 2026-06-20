"""Prompt building for LLM Service"""

import asyncio
import inspect
import logging
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

logger = logging.getLogger(__name__)


def _call_get_knowledge(intent_key: str) -> str:
    """
    Safely call get_knowledge regardless of whether it is sync or async.

    The original implementation in leysco_knowledge_base.py is declared
    `async def get_knowledge(...)` even though it only reads from an in-memory
    dict and never actually awaits anything.  Calling it without `await` in a
    synchronous context (like _build_system_prompt) causes the
    "coroutine was never awaited" RuntimeWarning and returns None instead of
    the knowledge content.

    This helper detects which case we're in and handles both:
      - If get_knowledge is a plain function  → call it directly.
      - If get_knowledge is a coroutine func  → run it safely:
          * Inside a running event loop  → schedule and wait via run_coroutine_threadsafe
          * Outside a running event loop → use asyncio.run()
    """
    try:
        from app.ai_engine.leysco_knowledge_base import get_knowledge
    except ImportError:
        logger.warning("leysco_knowledge_base not found, skipping knowledge injection")
        return ""

    try:
        if not inspect.iscoroutinefunction(get_knowledge):
            # Already a plain sync function — just call it
            return get_knowledge(intent_key) or ""

        # It's async — run it safely
        try:
            loop = asyncio.get_running_loop()
            # We are inside a running loop (e.g. called from an async context
            # via asyncio.to_thread).  Use run_coroutine_threadsafe so we don't
            # try to nest event loops.
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(get_knowledge(intent_key), loop)
            return future.result(timeout=2) or ""
        except RuntimeError:
            # No running loop — safe to use asyncio.run()
            return asyncio.run(get_knowledge(intent_key)) or ""

    except Exception as e:
        logger.warning(f"get_knowledge({intent_key!r}) failed: {e}")
        return ""


class PromptBuilder:
    """Builds system prompts with context and style variations"""
    
    def __init__(self):
        self._last_response_styles: Dict[str, str] = {}
    
    def _get_response_style(self, intent: str) -> str:
        """Get a varied response style for the intent."""
        styles = get_response_styles()
        intent_styles = styles.get(intent, ["friendly", "helpful", "professional"])
        
        last_style = self._last_response_styles.get(intent)
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
        """Build enhanced system prompt with conversation context."""
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
        
        # FIX: Use the safe wrapper instead of calling get_knowledge() directly.
        # Previously this was:
        #   kb_content = get_knowledge(intent_key)          ← returned a coroutine object
        # Now it safely awaits the coroutine where necessary.
        if intent_key not in ("GENERAL", "UNKNOWN"):
            kb_content = _call_get_knowledge(intent_key)
            if kb_content:
                parts.append(f"--- LEYSCO KNOWLEDGE BASE ---\n{kb_content}\n")
        
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