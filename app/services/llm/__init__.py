"""LLM Service - Natural language generation for AI responses"""

# FIX: The main class lives in service.py, not client.py.
# The old __init__.py had `from .client import ...` which caused an ImportError
# because there is no client.py in this package.
from .client import LLMService, get_llm_service
from .memory import get_conversation_memory, ConversationMemory
from .constants import LEYSCO_PROFILE

__all__ = [
    'LLMService',
    'get_llm_service',
    'get_conversation_memory',
    'ConversationMemory',
    'LEYSCO_PROFILE'
]
