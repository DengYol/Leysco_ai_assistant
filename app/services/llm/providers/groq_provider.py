"""Groq LLM provider"""

import logging
from typing import Optional

from app.core.config import settings
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    logger.warning("Groq library not installed")


class GroqProvider(BaseLLMProvider):
    """Groq API provider"""
    
    def __init__(self):
        self._client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize Groq client"""
        if not GROQ_AVAILABLE:
            logger.warning("Groq not available - library not installed")
            return
        
        api_key = settings.GROQ_API_KEY
        if not api_key:
            logger.warning("GROQ_API_KEY not set in environment")
            return
        
        try:
            self._client = Groq(api_key=api_key)
            logger.info("✅ Groq client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Groq: {e}")
            self._client = None
    
    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[str]:
        """Generate response using Groq"""
        if not self._client:
            logger.error("Groq client not available")
            return None
        
        try:
            logger.info("📡 Sending request to Groq...")
            
            response = self._client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=max_tokens,
            )
            
            result = response.choices[0].message.content
            tokens_used = getattr(response.usage, 'total_tokens', 0)
            logger.info(f"✅ Groq response: {len(result)} chars, {tokens_used} tokens")
            return self.clean_response(result)
            
        except Exception as e:
            logger.error(f"Groq generation error: {e}")
            return None
    
    def is_available(self) -> bool:
        """Check if Groq is available"""
        return self._client is not None
    
    def get_name(self) -> str:
        return "groq"