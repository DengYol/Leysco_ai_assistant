"""Conversation memory management for LLM Service"""

import time
from typing import Dict, List, Optional
from datetime import datetime

from .constants import MAX_HISTORY_EXCHANGES


class ConversationMemory:
    """Manages conversation history per session"""
    
    def __init__(self):
        self._history: Dict[str, List[Dict]] = {}
        self._max_history = MAX_HISTORY_EXCHANGES
    
    def get_history(self, session_id: str) -> List[Dict]:
        """Get conversation history for a session."""
        return self._history.get(session_id, [])
    
    def add_exchange(self, session_id: str, user_message: str, assistant_response: str):
        """Add exchange to conversation history."""
        if session_id not in self._history:
            self._history[session_id] = []
        
        self._history[session_id].append({
            "user": user_message[:500],  # Limit length
            "assistant": assistant_response[:500],
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only last N exchanges
        if len(self._history[session_id]) > self._max_history:
            self._history[session_id] = self._history[session_id][-self._max_history:]
    
    def clear(self, session_id: str):
        """Clear conversation history for a session."""
        if session_id in self._history:
            del self._history[session_id]
    
    def get_recent_context(self, session_id: str, limit: int = 3) -> str:
        """Get recent conversation context as string."""
        history = self.get_history(session_id)
        if not history:
            return ""
        
        context_parts = ["--- RECENT CONVERSATION ---"]
        for exchange in history[-limit:]:
            context_parts.append(f"User: {exchange['user'][:200]}")
            context_parts.append(f"Assistant: {exchange['assistant'][:200]}")
        
        return "\n".join(context_parts)


# Global instance
_conversation_memory = ConversationMemory()


def get_conversation_memory() -> ConversationMemory:
    """Get global conversation memory instance."""
    return _conversation_memory