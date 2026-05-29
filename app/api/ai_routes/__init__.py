"""AI Routes Module - Chat, Streaming, and AI-powered endpoints

This module is being refactored from the monolithic ai_routes.py.
Current status:
- Original file moved to ai_routes_original.py
- Constants, schemas, and utilities extracted
- Router now imports from the original file
- Gradually moving code into separate modules
- Phase 2 Tier 1 endpoints for notifications (preferences, search, analytics)
"""

from .router import router
from .constants import *
from .schemas import AIRequest, AIResponse, StreamChunk
from .utils import utf8_json_response, ensure_utf8_string

# Phase 2 Tier 1 - Notification Management Endpoints
from .preference_endpoints import router as preference_router
from .search_endpoints import router as search_router
from .notification_analytics_endpoints import router as notif_analytics_router

# Register Phase 2 routers with main router
router.include_router(preference_router)
router.include_router(search_router)
router.include_router(notif_analytics_router)

__all__ = [
    'router',
    'AIRequest',
    'AIResponse', 
    'StreamChunk',
    'utf8_json_response',
    'ensure_utf8_string',
    'preference_router',
    'search_router',
    'notif_analytics_router'
]