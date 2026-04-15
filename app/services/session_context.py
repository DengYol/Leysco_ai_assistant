"""
Session Context Memory Engine
Handles:
- Entity persistence
- Smart merging (NEW TAKES PRIORITY)
- Reference resolution (him, it, that)
- Context prioritization
- Thread safety
- Session cleanup
"""

from collections import defaultdict
import time
import logging
import copy
import threading

logger = logging.getLogger(__name__)


class SessionContext:
    def __init__(self, ttl_seconds=1800):
        self.store = defaultdict(dict)
        self.timestamps = {}
        self.ttl = ttl_seconds
        self._lock = threading.RLock()
        logger.info(f"✅ SessionContext initialized with TTL={ttl_seconds}s")

    # ─────────────────────────────
    # 🔹 CLEAN EXPIRED SESSIONS
    # ─────────────────────────────
    def _cleanup(self):
        """Remove expired sessions based on TTL."""
        now = time.time()
        expired = [
            sid for sid, ts in self.timestamps.items()
            if now - ts > self.ttl
        ]
        for sid in expired:
            self.store.pop(sid, None)
            self.timestamps.pop(sid, None)
        if expired:
            logger.info(f"🧹 Cleaned {len(expired)} expired session(s)")

    # ─────────────────────────────
    # 🔹 GET SESSION DATA
    # ─────────────────────────────
    def get(self, session_id: str) -> dict:
        """
        Get session data for a given session ID.
        Returns a copy of the session data or empty dict if not found.
        Updates timestamp on read to keep session alive.
        """
        if not session_id:
            return {}
        
        with self._lock:
            self._cleanup()
            
            if session_id not in self.store:
                return {}
            
            # Update timestamp on read to keep session alive
            self.timestamps[session_id] = time.time()
            
            # Return a deep copy to prevent accidental mutation
            return copy.deepcopy(self.store[session_id])

    # ─────────────────────────────
    # 🔹 MERGE ENTITIES (SMART)
    # ─────────────────────────────
    def merge(self, session_id: str, new_entities: dict) -> dict:
        """
        Merge new entities into session.
        CRITICAL: NEW entities OVERRIDE old ones.
        The user's current message is the source of truth.
        """
        if not session_id:
            return {}
        
        with self._lock:
            self._cleanup()

            if session_id not in self.store:
                self.store[session_id] = {}
                logger.info(f"🆕 Created new session: {session_id}")

            existing = self.store[session_id]
            
            # CRITICAL: New entities OVERRIDE existing ones
            # The user's current message is the source of truth
            overridden = []
            for key, value in new_entities.items():
                # Skip None or empty string values
                if value is None or value == "":
                    continue
                
                # Check if we're overriding an existing value
                if key in existing and existing[key] != value:
                    overridden.append(f"{key}: '{existing[key]}' → '{value}'")
                
                # Set the new value (overrides old)
                existing[key] = value
            
            if overridden:
                logger.info(f"🔄 Session update (overrides): {', '.join(overridden)}")
            elif new_entities:
                logger.debug(f"📝 Session update (new): {new_entities}")

            self.timestamps[session_id] = time.time()
            return copy.deepcopy(existing)

    # ─────────────────────────────
    # 🔹 UPDATE FROM RESPONSE
    # ─────────────────────────────
    def update_from_response(self, session_id: str, entities: dict):
        """
        Update session with entities from the response.
        This also overrides old values.
        """
        if not session_id:
            return
        
        with self._lock:
            if session_id not in self.store:
                self.store[session_id] = {}
            
            updated = []
            for key, value in entities.items():
                if value is not None and value != "":
                    if key in self.store[session_id] and self.store[session_id][key] != value:
                        updated.append(f"{key}: '{self.store[session_id][key]}' → '{value}'")
                    self.store[session_id][key] = value
            
            if updated:
                logger.debug(f"📝 Session updated from response: {', '.join(updated)}")
            
            self.timestamps[session_id] = time.time()

    # ─────────────────────────────
    # 🔥 REFERENCE RESOLUTION
    # ─────────────────────────────
    def resolve_references(self, session_id: str, message: str, entities: dict) -> dict:
        """
        Resolve pronouns like:
        - him → customer
        - it → item
        - that → last entity
        """
        if not session_id:
            return entities

        with self._lock:
            context = self.store.get(session_id, {})

        msg = message.lower()
        resolved = False

        # 🔥 CUSTOMER REFERENCES
        if any(word in msg for word in ["him", "her", "that customer"]):
            if "customer_name" in context and not entities.get("customer_name"):
                entities["customer_name"] = context["customer_name"]
                logger.info(f"🔁 Resolved 'him/her' → customer: {context['customer_name']}")
                resolved = True

        # 🔥 ITEM REFERENCES
        if any(word in msg for word in ["it", "that item", "this item"]):
            if "item_name" in context and not entities.get("item_name"):
                entities["item_name"] = context["item_name"]
                logger.info(f"🔁 Resolved 'it' → item: {context['item_name']}")
                resolved = True

        # 🔥 GENERIC FALLBACK
        if "that" in msg and not resolved:
            for key in ["customer_name", "item_name", "warehouse"]:
                if key in context and not entities.get(key):
                    entities[key] = context[key]
                    logger.info(f"🔁 Resolved 'that' → {key}: {context[key]}")
                    break

        return entities

    # ─────────────────────────────
    # 🔹 CLEAR SESSION
    # ─────────────────────────────
    def clear(self, session_id: str):
        """
        Clear session data for a specific session.
        """
        if not session_id:
            return
        
        with self._lock:
            if session_id in self.store:
                del self.store[session_id]
            if session_id in self.timestamps:
                del self.timestamps[session_id]
            logger.info(f"🧹 Session cleared: {session_id}")

    # ─────────────────────────────
    # 🔹 DELETE SPECIFIC ENTITY
    # ─────────────────────────────
    def delete_entity(self, session_id: str, key: str):
        """
        Delete a specific entity from session.
        Useful when an entity is no longer relevant.
        """
        if not session_id or not key:
            return
        
        with self._lock:
            if session_id in self.store and key in self.store[session_id]:
                del self.store[session_id][key]
                logger.info(f"🗑️ Deleted entity '{key}' from session {session_id}")
                self.timestamps[session_id] = time.time()

    # ─────────────────────────────
    # 🔹 GET ALL SESSIONS (for debugging)
    # ─────────────────────────────
    def get_all_sessions(self) -> dict:
        """
        Get all active sessions (for debugging/monitoring).
        """
        with self._lock:
            self._cleanup()
            return copy.deepcopy(dict(self.store))

    # ─────────────────────────────
    # 🔹 GET STATS (for monitoring)
    # ─────────────────────────────
    def get_stats(self) -> dict:
        """
        Get session statistics.
        """
        with self._lock:
            self._cleanup()
            
            if not self.store:
                return {
                    "active_sessions": 0,
                    "total_entities": 0,
                    "oldest_session_age": 0,
                    "newest_session_age": 0,
                }
            
            now = time.time()
            ages = [now - ts for ts in self.timestamps.values()]
            
            return {
                "active_sessions": len(self.store),
                "total_entities": sum(len(v) for v in self.store.values()),
                "oldest_session_age": max(ages) if ages else 0,
                "newest_session_age": min(ages) if ages else 0,
                "avg_session_age": sum(ages) / len(ages) if ages else 0,
            }

    # ─────────────────────────────
    # 🔹 SESSION EXPIRE (force expire)
    # ─────────────────────────────
    def expire_session(self, session_id: str):
        """
        Force expire a session immediately.
        """
        if not session_id:
            return
        
        with self._lock:
            if session_id in self.store:
                del self.store[session_id]
            if session_id in self.timestamps:
                del self.timestamps[session_id]
            logger.info(f"⏰ Session force expired: {session_id}")


# Singleton instance
session_ctx = SessionContext()