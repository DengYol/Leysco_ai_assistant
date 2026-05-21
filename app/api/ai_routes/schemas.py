"""Request/Response models for AI endpoints"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class AIRequest(BaseModel):
    """AI chat request model"""
    message: str
    session_id: str | None = None
    stream: bool = False


class AIResponse(BaseModel):
    """AI chat response model"""
    intent: str
    entities: dict
    result: str
    data: list = []
    suggestions: list[str] = []
    session_id: str = ""
    processing_time_ms: int = 0
    context_used: bool = False


class StreamChunk(BaseModel):
    """Streaming response chunk model"""
    type: str  # "intent", "entities", "text", "done", "error"
    content: str
    data: dict | None = None