"""AI Routes Module - Chat, Streaming, and AI-powered endpoints

This module is being refactored from the monolithic ai_routes.py.
Current status:
- Original file moved to ai_routes_original.py
- Constants, schemas, and utilities extracted
- Router now imports from the original file
- Gradually moving code into separate modules
"""

from .router import router
from .constants import *
from .schemas import AIRequest, AIResponse, StreamChunk
from .utils import utf8_json_response, ensure_utf8_string

__all__ = [
    'router',
    'AIRequest',
    'AIResponse', 
    'StreamChunk',
    'utf8_json_response',
    'ensure_utf8_string'
]