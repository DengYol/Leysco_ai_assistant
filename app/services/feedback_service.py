"""
app/services/feedback_service.py
=================================
Feedback Loop Service
Tracks user interactions and learns from them.

FEATURES:
- Track suggestion clicks
- Re-rank suggestions based on popularity
- Build user preference profiles
- Weekly learning model updates
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)


@dataclass
class FeedbackEvent:
    """Single feedback event"""
    id: str
    user_id: int
    tenant_code: str
    session_id: str
    intent: str
    suggestion_text: str
    action: str  # "clicked" or "ignored"
    created_at: str


class FeedbackService:
    """
    Tracks user feedback and learns from it.
    Used to re-rank suggestions and personalize responses.
    """
    
    # Cache keys
    SUGGESTION_STATS_KEY = "feedback:suggestion_stats"
    INTENT_PREFERENCES_KEY = "feedback:intent_preferences"
    USER_PROFILE_KEY = "feedback:user_profile:{user_id}"
    
    # TTLs
    STATS_TTL = 86400  # 24 hours
    USER_PROFILE_TTL = 604800  # 7 days
    
    def __init__(self):
        self.cache = get_cache_service()
        self._batch_buffer = []
    
    # =========================================================
    # MAIN FEEDBACK METHODS
    # =========================================================
    
    async def record_suggestion_click(
        self,
        user_id: int,
        tenant_code: str,
        session_id: str,
        intent: str,
        suggestion_text: str
    ) -> None:
        """
        Record that a user clicked a suggestion.
        This is POSITIVE feedback.
        """
        event = FeedbackEvent(
            id=f"{datetime.now().timestamp()}_{user_id}",
            user_id=user_id,
            tenant_code=tenant_code,
            session_id=session_id,
            intent=intent,
            suggestion_text=suggestion_text,
            action="clicked",
            created_at=datetime.now().isoformat()
        )
        
        await self._process_feedback(event)
        logger.info(f"📊 Feedback: User {user_id} clicked '{suggestion_text}' for intent {intent}")
    
    async def record_suggestion_ignore(
        self,
        user_id: int,
        tenant_code: str,
        session_id: str,
        intent: str,
        suggestion_text: str
    ) -> None:
        """
        Record that a user ignored a suggestion (didn't click).
        This is NEUTRAL/NEGATIVE feedback.
        """
        event = FeedbackEvent(
            id=f"{datetime.now().timestamp()}_{user_id}",
            user_id=user_id,
            tenant_code=tenant_code,
            session_id=session_id,
            intent=intent,
            suggestion_text=suggestion_text,
            action="ignored",
            created_at=datetime.now().isoformat()
        )
        
        await self._process_feedback(event)
    
    async def _process_feedback(self, event: FeedbackEvent) -> None:
        """Process feedback event - update statistics."""
        
        # Update suggestion statistics
        await self._update_suggestion_stats(event)
        
        # Update user profile
        await self._update_user_profile(event)
        
        # Update intent preferences
        await self._update_intent_preferences(event)
        
        # Add to batch for database storage
        self._batch_buffer.append(asdict(event))
        if len(self._batch_buffer) >= 50:
            await self._flush_batch()
    
    async def _update_suggestion_stats(self, event: FeedbackEvent) -> None:
        """Update global suggestion statistics."""
        stats_key = f"{self.SUGGESTION_STATS_KEY}:{event.tenant_code}"
        
        # Get current stats
        stats = await self.cache.get_simple_async(stats_key) or {}
        
        # Initialize nested structure
        if event.intent not in stats:
            stats[event.intent] = {}
        
        if event.suggestion_text not in stats[event.intent]:
            stats[event.intent][event.suggestion_text] = {
                "clicks": 0,
                "ignores": 0,
                "click_rate": 0.0
            }
        
        # Update counter
        if event.action == "clicked":
            stats[event.intent][event.suggestion_text]["clicks"] += 1
        else:
            stats[event.intent][event.suggestion_text]["ignores"] += 1
        
        # Recalculate click rate
        total = stats[event.intent][event.suggestion_text]["clicks"] + \
                stats[event.intent][event.suggestion_text]["ignores"]
        stats[event.intent][event.suggestion_text]["click_rate"] = \
            stats[event.intent][event.suggestion_text]["clicks"] / total if total > 0 else 0
        
        # Save back to cache
        await self.cache.set_simple_async(stats_key, stats, ttl=self.STATS_TTL)
    
    async def _update_user_profile(self, event: FeedbackEvent) -> None:
        """Update user-specific preference profile."""
        profile_key = self.USER_PROFILE_KEY.format(user_id=event.user_id)
        
        profile = await self.cache.get_simple_async(profile_key) or {
            "user_id": event.user_id,
            "tenant_code": event.tenant_code,
            "preferred_intents": {},
            "preferred_suggestions": {},
            "total_interactions": 0,
            "last_active": None
        }
        
        # Update preferred intents
        if event.intent not in profile["preferred_intents"]:
            profile["preferred_intents"][event.intent] = 0
        profile["preferred_intents"][event.intent] += 1
        
        # Update preferred suggestions
        if event.suggestion_text not in profile["preferred_suggestions"]:
            profile["preferred_suggestions"][event.suggestion_text] = 0
        profile["preferred_suggestions"][event.suggestion_text] += 1
        
        profile["total_interactions"] += 1
        profile["last_active"] = datetime.now().isoformat()
        
        await self.cache.set_simple_async(profile_key, profile, ttl=self.USER_PROFILE_TTL)
    
    async def _update_intent_preferences(self, event: FeedbackEvent) -> None:
        """Update intent-level preferences."""
        prefs_key = f"{self.INTENT_PREFERENCES_KEY}:{event.tenant_code}"
        
        prefs = await self.cache.get_simple_async(prefs_key) or {}
        
        if event.intent not in prefs:
            prefs[event.intent] = {
                "total_clicks": 0,
                "total_ignores": 0,
                "top_suggestions": []
            }
        
        if event.action == "clicked":
            prefs[event.intent]["total_clicks"] += 1
        else:
            prefs[event.intent]["total_ignores"] += 1
        
        await self.cache.set_simple_async(prefs_key, prefs, ttl=self.STATS_TTL)
    
    # =========================================================
    # SUGGESTION RE-RANKING (The Learning Part)
    # =========================================================
    
    async def reorder_suggestions(
        self,
        tenant_code: str,
        intent: str,
        suggestions: List[str],
        user_id: Optional[int] = None
    ) -> List[str]:
        """
        Reorder suggestions based on feedback.
        Most popular suggestions come first.
        
        Args:
            tenant_code: Company code
            intent: Current intent
            suggestions: Original list of suggestions
            user_id: Optional user ID for personalization
        
        Returns:
            Reordered list of suggestions
        """
        if not suggestions:
            return suggestions
        
        # Get global statistics
        stats_key = f"{self.SUGGESTION_STATS_KEY}:{tenant_code}"
        stats = await self.cache.get_simple_async(stats_key) or {}
        
        intent_stats = stats.get(intent, {})
        
        # Score each suggestion
        scored = []
        for suggestion in suggestions:
            suggestion_stats = intent_stats.get(suggestion, {})
            
            # Base score from global click rate
            global_score = suggestion_stats.get("click_rate", 0.5)
            
            scored.append({
                "suggestion": suggestion,
                "score": global_score
            })
        
        # Sort by score (highest first)
        scored.sort(key=lambda x: x["score"], reverse=True)
        
        # Personalize if user_id provided
        if user_id:
            scored = await self._personalize_suggestions(
                tenant_code, intent, scored, user_id
            )
        
        return [s["suggestion"] for s in scored]
    
    async def _personalize_suggestions(
        self,
        tenant_code: str,
        intent: str,
        scored_suggestions: List[Dict],
        user_id: int
    ) -> List[Dict]:
        """Apply personalization based on user history."""
        profile_key = self.USER_PROFILE_KEY.format(user_id=user_id)
        profile = await self.cache.get_simple_async(profile_key)
        
        if not profile:
            return scored_suggestions
        
        # Boost suggestions the user has clicked before
        user_prefs = profile.get("preferred_suggestions", {})
        
        for item in scored_suggestions:
            suggestion = item["suggestion"]
            if suggestion in user_prefs:
                # Boost by 20% for each previous click (capped at 2x)
                boost = min(1.0, user_prefs[suggestion] * 0.2)
                item["score"] = min(1.0, item["score"] + boost)
        
        # Re-sort after personalization
        scored_suggestions.sort(key=lambda x: x["score"], reverse=True)
        
        return scored_suggestions
    
    # =========================================================
    # ANALYTICS METHODS
    # =========================================================
    
    async def get_suggestion_performance(
        self,
        tenant_code: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get performance metrics for suggestions."""
        stats_key = f"{self.SUGGESTION_STATS_KEY}:{tenant_code}"
        stats = await self.cache.get_simple_async(stats_key) or {}
        
        # Calculate overall metrics
        total_clicks = 0
        total_ignores = 0
        intent_performance = []
        
        for intent, suggestions in stats.items():
            intent_clicks = sum(s.get("clicks", 0) for s in suggestions.values())
            intent_ignores = sum(s.get("ignores", 0) for s in suggestions.values())
            
            total_clicks += intent_clicks
            total_ignores += intent_ignores
            
            intent_performance.append({
                "intent": intent,
                "clicks": intent_clicks,
                "ignores": intent_ignores,
                "click_rate": round(intent_clicks / (intent_clicks + intent_ignores) * 100, 1) if (intent_clicks + intent_ignores) > 0 else 0
            })
        
        # Find top performing suggestions
        top_suggestions = []
        for intent, suggestions in stats.items():
            for suggestion, data in suggestions.items():
                top_suggestions.append({
                    "intent": intent,
                    "suggestion": suggestion,
                    "clicks": data.get("clicks", 0),
                    "click_rate": round(data.get("click_rate", 0) * 100, 1)
                })
        
        top_suggestions.sort(key=lambda x: x["click_rate"], reverse=True)
        
        return {
            "total_clicks": total_clicks,
            "total_ignores": total_ignores,
            "overall_click_rate": round(total_clicks / (total_clicks + total_ignores) * 100, 1) if (total_clicks + total_ignores) > 0 else 0,
            "intent_performance": sorted(intent_performance, key=lambda x: x["click_rate"], reverse=True),
            "top_suggestions": top_suggestions[:10],
            "timestamp": datetime.now().isoformat()
        }
    
    async def get_user_insights(self, user_id: int) -> Dict[str, Any]:
        """Get insights for a specific user."""
        profile_key = self.USER_PROFILE_KEY.format(user_id=user_id)
        profile = await self.cache.get_simple_async(profile_key)
        
        if not profile:
            return {
                "user_id": user_id,
                "has_data": False,
                "message": "No feedback data for this user yet"
            }
        
        # Get top preferences
        top_intents = sorted(
            profile.get("preferred_intents", {}).items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        top_suggestions = sorted(
            profile.get("preferred_suggestions", {}).items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        return {
            "user_id": user_id,
            "has_data": True,
            "total_interactions": profile.get("total_interactions", 0),
            "last_active": profile.get("last_active"),
            "top_intents": [{"intent": i, "count": c} for i, c in top_intents],
            "top_suggestions": [{"suggestion": s, "count": c} for s, c in top_suggestions]
        }
    
    async def _flush_batch(self) -> None:
        """Flush batch buffer to storage."""
        if not self._batch_buffer:
            return
        
        batch = self._batch_buffer.copy()
        self._batch_buffer = []
        
        try:
            # Write to JSON file for now (can replace with database)
            import aiofiles
            import os
            
            os.makedirs("logs/feedback", exist_ok=True)
            filename = f"logs/feedback/feedback_{datetime.now().strftime('%Y%m%d')}.json"
            
            async with aiofiles.open(filename, 'a') as f:
                for record in batch:
                    await f.write(json.dumps(record) + "\n")
            
            logger.debug(f"✅ Flushed {len(batch)} feedback events")
        except Exception as e:
            logger.error(f"Failed to flush feedback batch: {e}")


# Singleton instance
_feedback_service = None


def get_feedback_service() -> FeedbackService:
    """Get or create FeedbackService singleton."""
    global _feedback_service
    if _feedback_service is None:
        _feedback_service = FeedbackService()
    return _feedback_service