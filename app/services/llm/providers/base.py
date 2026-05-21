"""Base provider class for LLM providers"""

from abc import ABC, abstractmethod
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers"""
    
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[str]:
        """Generate response from the provider"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available"""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Get provider name"""
        pass
    
    def clean_response(self, text: str) -> str:
        """Clean response text"""
        if not text:
            return text
        return text.strip()