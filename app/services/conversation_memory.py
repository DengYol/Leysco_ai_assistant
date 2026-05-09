"""
app/services/conversation_memory.py
====================================
Manages conversation context across multiple turns.
Stores session data, remembers previous queries, and enables contextual understanding.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import deque
import hashlib

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)


class ConversationMemory:
    """
    Stores and retrieves conversation context for each session.
    Enables AI to remember previous questions and answers.
    """
    
    # Maximum number of messages to keep per session
    MAX_HISTORY = 20
    
    # Session timeout (seconds) - 30 minutes
    SESSION_TIMEOUT = 1800
    
    # Maximum items to store in context (prevent memory bloat)
    MAX_CONTEXT_ITEMS = 50
    
    def __init__(self):
        self.cache = get_cache_service()
        self._sessions = {}  # Fallback in-memory store
    
    def _get_session_key(self, session_id: str) -> str:
        """Generate cache key for session."""
        return f"conversation_session:{session_id}"
    
    def get_or_create_session(self, session_id: str, user_id: str = None, tenant_code: str = None) -> Dict:
        """
        Get existing session or create new one.
        """
        cache_key = self._get_session_key(session_id)
        
        # Try to get from cache
        session = self.cache.get_simple(cache_key)
        
        if session:
            # Check if session expired
            last_activity = session.get("last_activity")
            if last_activity:
                last_time = datetime.fromisoformat(last_activity)
                if (datetime.now() - last_time).seconds < self.SESSION_TIMEOUT:
                    logger.info(f"📚 Retrieved existing session: {session_id}")
                    return session
            
            # Session expired, create new
            logger.info(f"⏰ Session expired: {session_id}")
        
        # Create new session
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "tenant_code": tenant_code,
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
            "conversation_history": [],
            "context": {
                "last_intent": None,
                "last_entities": {},
                "last_results": [],
                "referenced_items": [],
                "referenced_customers": [],
                "last_action": None,
                "pending_action": None,
                "quotation_draft": None,
                "current_selection": None
            },
            "message_count": 0
        }
        
        self.cache.set_simple(cache_key, session, ttl=self.SESSION_TIMEOUT)
        logger.info(f"✨ Created new session: {session_id}")
        
        return session
    
    def add_message(self, session_id: str, role: str, content: str, data: Any = None) -> None:
        """
        Add a message to conversation history.
        
        Args:
            session_id: Session identifier
            role: "user" or "assistant"
            content: Message text
            data: Optional structured data (e.g., API results)
        """
        session = self.get_or_create_session(session_id)
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        
        if data:
            # Truncate large data to prevent memory bloat
            if isinstance(data, list) and len(data) > self.MAX_CONTEXT_ITEMS:
                message["data"] = data[:self.MAX_CONTEXT_ITEMS]
                message["data_truncated"] = True
                message["data_total"] = len(data)
            elif isinstance(data, dict):
                # Keep only essential fields
                message["data"] = self._prune_data(data)
            else:
                message["data"] = data
        
        session["conversation_history"].append(message)
        
        # Keep only last N messages
        if len(session["conversation_history"]) > self.MAX_HISTORY:
            session["conversation_history"] = session["conversation_history"][-self.MAX_HISTORY:]
        
        session["message_count"] += 1
        session["last_activity"] = datetime.now().isoformat()
        
        self._save_session(session)
        logger.info(f"📝 Added {role} message to session {session_id} (total: {session['message_count']})")
    
    def update_context(
        self, 
        session_id: str, 
        intent: str = None, 
        entities: Dict = None,
        results: Any = None,
        action: str = None
    ) -> None:
        """
        Update the context with latest intent, entities, and results.
        This is the KEY method for remembering previous queries.
        """
        session = self.get_or_create_session(session_id)
        context = session["context"]
        
        if intent:
            context["last_intent"] = intent
        
        if entities:
            # Merge entities (don't overwrite everything)
            if context.get("last_entities"):
                context["last_entities"].update(entities)
            else:
                context["last_entities"] = entities.copy()
        
        if results is not None:
            # Store last results for context
            if isinstance(results, list):
                context["last_results"] = results[:self.MAX_CONTEXT_ITEMS]
                
                # Extract referenced items for quick lookup
                items = []
                customers = []
                for item in results[:20]:
                    if isinstance(item, dict):
                        if item.get("ItemCode") or item.get("item_code"):
                            items.append({
                                "code": item.get("ItemCode") or item.get("item_code"),
                                "name": item.get("ItemName") or item.get("item_name"),
                                "price": item.get("Price") or item.get("price")
                            })
                        if item.get("CardCode") or item.get("customer_code"):
                            customers.append({
                                "code": item.get("CardCode") or item.get("customer_code"),
                                "name": item.get("CardName") or item.get("customer_name")
                            })
                
                if items:
                    context["referenced_items"] = items[:10]
                if customers:
                    context["referenced_customers"] = customers[:10]
                
            elif isinstance(results, dict):
                context["last_results"] = self._prune_data(results)
        
        if action:
            context["last_action"] = action
        
        session["last_activity"] = datetime.now().isoformat()
        self._save_session(session)
        logger.info(f"🔄 Updated context for session {session_id}: intent={intent}, action={action}")
    
    def get_context(self, session_id: str) -> Dict:
        """
        Get current context for a session.
        """
        session = self.get_or_create_session(session_id)
        return session.get("context", {})
    
    def get_conversation_history(self, session_id: str, limit: int = 10) -> List[Dict]:
        """
        Get recent conversation history.
        """
        session = self.get_or_create_session(session_id)
        history = session.get("conversation_history", [])
        return history[-limit:] if limit else history
    
    def get_last_user_message(self, session_id: str) -> Optional[str]:
        """
        Get the last user message.
        """
        session = self.get_or_create_session(session_id)
        history = session.get("conversation_history", [])
        
        for msg in reversed(history):
            if msg.get("role") == "user":
                return msg.get("content")
        
        return None
    
    def get_last_assistant_response(self, session_id: str) -> Optional[Dict]:
        """
        Get the last assistant response (with data).
        """
        session = self.get_or_create_session(session_id)
        history = session.get("conversation_history", [])
        
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                return msg
        
        return None
    
    def resolve_reference(self, session_id: str, reference: str) -> Optional[Dict]:
        """
        Resolve a reference like "the first one" or "that customer" to actual data.
        
        Examples:
        - "the first one" → first item in last_results
        - "that customer" → last referenced customer
        - "its price" → price of last referenced item
        """
        context = self.get_context(session_id)
        last_results = context.get("last_results", [])
        
        reference_lower = reference.lower()
        
        # Handle ordinal references
        ordinals = {
            "first": 0, "1st": 0, "one": 0,
            "second": 1, "2nd": 1, "two": 1,
            "third": 2, "3rd": 2, "three": 2,
            "fourth": 3, "4th": 3, "four": 3,
            "fifth": 4, "5th": 4, "five": 4
        }
        
        for word, index in ordinals.items():
            if word in reference_lower:
                if index < len(last_results):
                    return last_results[index]
        
        # Handle "that customer", "this item", "the previous one"
        if "customer" in reference_lower and context.get("referenced_customers"):
            return context["referenced_customers"][0]
        
        if "item" in reference_lower and context.get("referenced_items"):
            return context["referenced_items"][0]
        
        # Handle "its price" - return price of last item
        if "price" in reference_lower and context.get("referenced_items"):
            return {"price": context["referenced_items"][0].get("price")}
        
        return None
    
    def set_pending_action(self, session_id: str, action: str, data: Dict) -> None:
        """
        Set a pending action waiting for confirmation.
        Used for multi-turn operations like quotation creation.
        """
        session = self.get_or_create_session(session_id)
        session["context"]["pending_action"] = {
            "action": action,
            "data": data,
            "created_at": datetime.now().isoformat()
        }
        self._save_session(session)
        logger.info(f"⏳ Set pending action for session {session_id}: {action}")
    
    def get_pending_action(self, session_id: str) -> Optional[Dict]:
        """
        Get pending action if exists.
        """
        session = self.get_or_create_session(session_id)
        pending = session["context"].get("pending_action")
        
        if pending:
            # Check if expired (10 minutes)
            created_at = datetime.fromisoformat(pending["created_at"])
            if (datetime.now() - created_at).seconds > 600:
                self.clear_pending_action(session_id)
                return None
        
        return pending
    
    def clear_pending_action(self, session_id: str) -> None:
        """
        Clear pending action.
        """
        session = self.get_or_create_session(session_id)
        session["context"]["pending_action"] = None
        self._save_session(session)
        logger.info(f"✅ Cleared pending action for session {session_id}")
    
    def clear_session(self, session_id: str) -> None:
        """
        Clear entire session (new conversation).
        """
        cache_key = self._get_session_key(session_id)
        self.cache.delete_simple(cache_key)
        if session_id in self._sessions:
            del self._sessions[session_id]
        logger.info(f"🗑️ Cleared session: {session_id}")
    
    def _save_session(self, session: Dict) -> None:
        """Save session to cache."""
        cache_key = self._get_session_key(session["session_id"])
        self.cache.set_simple(cache_key, session, ttl=self.SESSION_TIMEOUT)
    
    def _prune_data(self, data: Dict) -> Dict:
        """Remove large or unnecessary fields from stored data."""
        pruned = {}
        
        # Keep only essential fields
        essential_fields = [
            "ItemCode", "ItemName", "CardCode", "CardName", 
            "DocNum", "DocTotal", "Price", "Quantity",
            "code", "name", "price", "quantity"
        ]
        
        for key, value in data.items():
            if key in essential_fields:
                pruned[key] = value
            elif isinstance(value, (str, int, float, bool)):
                pruned[key] = value
        
        return pruned
    
    def get_session_summary(self, session_id: str) -> Dict:
        """
        Get a summary of the session (for debugging/analytics).
        """
        session = self.get_or_create_session(session_id)
        
        return {
            "session_id": session_id,
            "message_count": session.get("message_count", 0),
            "duration_minutes": self._get_session_duration(session),
            "last_intent": session.get("context", {}).get("last_intent"),
            "referenced_items_count": len(session.get("context", {}).get("referenced_items", [])),
            "referenced_customers_count": len(session.get("context", {}).get("referenced_customers", [])),
            "has_pending_action": session.get("context", {}).get("pending_action") is not None
        }
    
    def _get_session_duration(self, session: Dict) -> float:
        """Calculate session duration in minutes."""
        created = session.get("created_at")
        if not created:
            return 0
        
        created_time = datetime.fromisoformat(created)
        last_time = datetime.fromisoformat(session.get("last_activity", created))
        
        return round((last_time - created_time).total_seconds() / 60, 1)


# Singleton instance
_conversation_memory = None


def get_conversation_memory() -> ConversationMemory:
    """Get or create ConversationMemory singleton."""
    global _conversation_memory
    if _conversation_memory is None:
        _conversation_memory = ConversationMemory()
    return _conversation_memory