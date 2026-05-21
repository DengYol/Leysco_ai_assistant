"""Gemini LLM provider"""

import logging
from typing import Optional

from app.core.config import settings
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("Google GenAI library not installed")


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider"""
    
    def __init__(self):
        self._client = None
        self._model = "gemini-1.5-flash"
        self._available = False
        self._init_client()
    
    def _init_client(self):
        """Initialize Gemini client"""
        if not GEMINI_AVAILABLE:
            logger.warning("Gemini not available - google-genai library not installed")
            return
        
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            logger.warning("GEMINI_API_KEY not set in environment")
            return
        
        try:
            self._client = genai.Client(api_key=api_key)
            self._available = True
            logger.info("✅ Gemini client initialized (free tier)")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            self._available = False
    
    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[str]:
        """Generate response using Gemini"""
        if not self._available:
            logger.error("Gemini client not available")
            return None
        
        try:
            # Combine system and user prompts for Gemini
            combined_prompt = f"{system_prompt}\n\nUser: {user_prompt}"
            
            response = self._client.models.generate_content(
                model=self._model,
                contents=combined_prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.7,
                    top_p=0.95,
                )
            )
            
            # Check for blocking
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                logger.warning(f"Gemini blocked: {response.prompt_feedback.block_reason}")
                return "I'm unable to respond to that request."
            
            # Extract text from response
            if response.text:
                result = response.text.strip()
                logger.info(f"✅ Gemini response: {len(result)} chars")
                return self.clean_response(result)
            else:
                logger.warning("Gemini returned empty response")
                return None
                
        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
            return None
    
    def is_available(self) -> bool:
        return self._available
    
    def get_name(self) -> str:
        return "gemini"