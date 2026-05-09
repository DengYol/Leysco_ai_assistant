"""
app/services/activity_logger.py
================================
Activity Logger & Analytics Service
Tracks all AI interactions for audit, analytics, and improvement.

FEATURES:
- Log all user queries and AI responses
- Track response times and success rates
- Monitor suggestion acceptance
- Provide analytics endpoints for managers
- Export data for reporting
"""

import logging
import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict
import uuid

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)


@dataclass
class ActivityLog:
    """Data class for a single activity log entry"""
    id: str
    user_id: int
    user_role: str
    tenant_code: str
    session_id: str
    intent: str
    query: str
    response_preview: str
    response_length: int
    processing_time_ms: int
    suggestions_shown: List[str]
    suggestion_accepted: Optional[str]
    context_used: bool
    success: bool
    error_message: Optional[str]
    created_at: str


class ActivityLogger:
    """
    Logs all AI interactions for analytics and audit.
    Uses dual storage: Redis for recent (fast queries), Database for archive.
    """
    
    # Cache TTL for recent logs (24 hours)
    RECENT_TTL = 86400  # 24 hours
    
    # Batch insert size
    BATCH_SIZE = 100
    
    def __init__(self):
        self.cache = get_cache_service()
        self._batch_buffer = []
        self._batch_lock = asyncio.Lock()
        
        # Start background batch processor
        asyncio.create_task(self._batch_processor())
    
    # =========================================================
    # MAIN LOGGING METHOD
    # =========================================================
    
    async def log_query(
        self,
        user_id: int,
        user_role: str,
        tenant_code: str,
        session_id: str,
        intent: str,
        query: str,
        response: str,
        processing_time_ms: int,
        suggestions_shown: List[str] = None,
        suggestion_accepted: str = None,
        context_used: bool = False,
        success: bool = True,
        error_message: str = None
    ) -> None:
        """
        Log a user query and AI response.
        
        Args:
            user_id: User identifier
            user_role: "manager" or "sales_rep"
            tenant_code: Company code
            session_id: Conversation session ID
            intent: Detected intent
            query: Original user message
            response: AI response text
            processing_time_ms: Time to process request
            suggestions_shown: List of suggestion chips shown
            suggestion_accepted: Which suggestion was clicked (if any)
            context_used: Whether conversation context was used
            success: Whether request succeeded
            error_message: Error message if failed
        """
        try:
            log_entry = ActivityLog(
                id=str(uuid.uuid4()),
                user_id=user_id,
                user_role=user_role,
                tenant_code=tenant_code,
                session_id=session_id,
                intent=intent,
                query=query[:500],  # Truncate for storage
                response_preview=response[:200] if response else "",
                response_length=len(response) if response else 0,
                processing_time_ms=processing_time_ms,
                suggestions_shown=suggestions_shown or [],
                suggestion_accepted=suggestion_accepted,
                context_used=context_used,
                success=success,
                error_message=error_message[:500] if error_message else None,
                created_at=datetime.now().isoformat()
            )
            
            # Store in Redis for recent queries (fast access)
            await self._store_recent(log_entry)
            
            # Add to batch for database insertion
            async with self._batch_lock:
                self._batch_buffer.append(asdict(log_entry))
                
                # Trigger batch insert if buffer is full
                if len(self._batch_buffer) >= self.BATCH_SIZE:
                    asyncio.create_task(self._flush_batch())
            
            # Log to file as well (for backup)
            logger.info(
                f"📊 ACTIVITY | User: {user_id} | Role: {user_role} | "
                f"Intent: {intent} | Time: {processing_time_ms}ms | "
                f"Success: {success} | Context: {context_used}"
            )
            
        except Exception as e:
            logger.error(f"Failed to log activity: {e}", exc_info=True)
    
    async def _store_recent(self, log_entry: ActivityLog) -> None:
        """Store log entry in Redis for recent queries."""
        try:
            # Add to sorted set with timestamp as score
            key = f"activity:recent:{log_entry.tenant_code}"
            score = datetime.now().timestamp()
            
            # Use zadd (not zadd_async) - the cache service has this method
            # The cache service's zadd method handles both Redis and memory cache
            await self.cache.zadd_async(key, {log_entry.id: score})
            
            # Store the full entry as a hash
            await self.cache.hset_async(f"activity:entry:{log_entry.id}", asdict(log_entry))
            
            # Keep only last 1000 entries per tenant
            await self.cache.zremrangebyrank_async(key, 0, -1001)
            
            # Set expiry
            await self.cache.expire_async(key, self.RECENT_TTL)
            
        except Exception as e:
            logger.warning(f"Failed to store recent activity in Redis: {e}")
    
    async def _flush_batch(self) -> None:
        """Flush batch buffer to database."""
        async with self._batch_lock:
            if not self._batch_buffer:
                return
            
            batch = self._batch_buffer.copy()
            self._batch_buffer = []
        
        try:
            await self._insert_to_database(batch)
            logger.debug(f"✅ Flushed {len(batch)} activity logs to database")
        except Exception as e:
            logger.error(f"Failed to flush batch to database: {e}")
            # Re-add to buffer for retry
            async with self._batch_lock:
                self._batch_buffer.extend(batch)
    
    async def _insert_to_database(self, batch: List[Dict]) -> None:
        """
        Insert batch to database.
        This is a placeholder - implement with your actual database.
        """
        # TODO: Implement with your database (PostgreSQL, MySQL, etc.)
        # Example with asyncpg:
        # async with db_pool.acquire() as conn:
        #     await conn.executemany("""
        #         INSERT INTO ai_activity_log 
        #         (id, user_id, user_role, tenant_code, session_id, intent, 
        #          query, response_preview, response_length, processing_time_ms,
        #          suggestions_shown, suggestion_accepted, context_used, 
        #          success, error_message, created_at)
        #         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
        #     """, batch)
        
        # For now, log to file
        logger.info(f"📊 BATCH INSERT: {len(batch)} records ready for database")
        
        # Also write to JSON file for backup
        try:
            import aiofiles
            import os
            # Create logs directory if it doesn't exist
            os.makedirs("logs", exist_ok=True)
            filename = f"logs/activity_{datetime.now().strftime('%Y%m%d')}.json"
            async with aiofiles.open(filename, 'a') as f:
                for record in batch:
                    await f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write to JSON backup: {e}")
    
    async def _batch_processor(self) -> None:
        """Background task to flush batch periodically."""
        while True:
            await asyncio.sleep(60)  # Every minute
            await self._flush_batch()
    
    # =========================================================
    # QUERY METHODS FOR ANALYTICS
    # =========================================================
    
    async def get_recent_activity(
        self,
        tenant_code: str,
        limit: int = 100,
        hours: int = 24
    ) -> List[Dict]:
        """Get recent activity for a tenant."""
        try:
            key = f"activity:recent:{tenant_code}"
            
            # Get recent entries
            entries = await self.cache.zrevrangebyscore_async(
                key, 
                max=datetime.now().timestamp(),
                min=datetime.now().timestamp() - (hours * 3600),
                start=0,
                num=limit
            )
            
            results = []
            for entry_id in entries:
                entry = await self.cache.hgetall_async(f"activity:entry:{entry_id}")
                if entry:
                    results.append(entry)
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get recent activity: {e}")
            return []
    
    async def get_analytics_summary(
        self,
        tenant_code: str,
        period: str = "today"  # today, yesterday, week, month
    ) -> Dict[str, Any]:
        """
        Get analytics summary for a tenant.
        
        Args:
            tenant_code: Company code
            period: today, yesterday, week, month
        
        Returns:
            Summary statistics
        """
        # Calculate date range
        end_date = datetime.now()
        if period == "today":
            start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "yesterday":
            end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
            start_date = end_date - timedelta(days=1)
        elif period == "week":
            start_date = end_date - timedelta(days=7)
        elif period == "month":
            start_date = end_date - timedelta(days=30)
        else:
            start_date = end_date - timedelta(days=1)
        
        # Get activity from recent cache first, then database
        recent = await self.get_recent_activity(tenant_code, limit=1000)
        
        # Filter by date range
        filtered = []
        for entry in recent:
            created_at = datetime.fromisoformat(entry.get("created_at", ""))
            if start_date <= created_at <= end_date:
                filtered.append(entry)
        
        if not filtered:
            return self._empty_summary(period, start_date, end_date)
        
        # Calculate statistics
        total_queries = len(filtered)
        successful = sum(1 for e in filtered if e.get("success", True))
        failed = total_queries - successful
        
        # Intent distribution
        intent_counts = Counter(e.get("intent", "UNKNOWN") for e in filtered)
        top_intents = [{"intent": k, "count": v} for k, v in intent_counts.most_common(10)]
        
        # User activity
        user_counts = Counter(e.get("user_id") for e in filtered)
        active_users = len(user_counts)
        
        # Response times
        response_times = [e.get("processing_time_ms", 0) for e in filtered if e.get("processing_time_ms", 0) > 0]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        max_response_time = max(response_times) if response_times else 0
        min_response_time = min(response_times) if response_times else 0
        
        # Context usage
        context_used_count = sum(1 for e in filtered if e.get("context_used", False))
        context_used_percent = (context_used_count / total_queries * 100) if total_queries > 0 else 0
        
        # Suggestion acceptance
        suggestions_shown = sum(len(e.get("suggestions_shown", [])) for e in filtered)
        suggestions_accepted = sum(1 for e in filtered if e.get("suggestion_accepted"))
        acceptance_rate = (suggestions_accepted / suggestions_shown * 100) if suggestions_shown > 0 else 0
        
        # Role distribution
        role_counts = Counter(e.get("user_role", "unknown") for e in filtered)
        
        return {
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_queries": total_queries,
            "successful": successful,
            "failed": failed,
            "success_rate": round(successful / total_queries * 100, 1) if total_queries > 0 else 0,
            "active_users": active_users,
            "top_intents": top_intents,
            "response_times": {
                "average_ms": round(avg_response_time, 1),
                "min_ms": min_response_time,
                "max_ms": max_response_time,
                "p95_ms": self._percentile(response_times, 95) if response_times else 0
            },
            "context_usage": {
                "used_count": context_used_count,
                "used_percent": round(context_used_percent, 1)
            },
            "suggestions": {
                "shown_count": suggestions_shown,
                "accepted_count": suggestions_accepted,
                "acceptance_rate": round(acceptance_rate, 1)
            },
            "user_roles": dict(role_counts),
            "timestamp": datetime.now().isoformat()
        }
    
    async def get_intent_analytics(
        self,
        tenant_code: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get detailed intent analytics."""
        # Get activity
        recent = await self.get_recent_activity(tenant_code, limit=5000)
        
        # Filter by days
        cutoff = datetime.now() - timedelta(days=days)
        filtered = []
        for entry in recent:
            created_at = datetime.fromisoformat(entry.get("created_at", ""))
            if created_at >= cutoff:
                filtered.append(entry)
        
        if not filtered:
            return {"error": "No data available", "intents": []}
        
        # Group by intent
        intent_data = defaultdict(lambda: {
            "count": 0,
            "avg_response_time": [],
            "success_count": 0,
            "context_used_count": 0
        })
        
        for entry in filtered:
            intent = entry.get("intent", "UNKNOWN")
            intent_data[intent]["count"] += 1
            if entry.get("processing_time_ms"):
                intent_data[intent]["avg_response_time"].append(entry["processing_time_ms"])
            if entry.get("success", True):
                intent_data[intent]["success_count"] += 1
            if entry.get("context_used"):
                intent_data[intent]["context_used_count"] += 1
        
        # Format results
        results = []
        for intent, data in intent_data.items():
            avg_time = sum(data["avg_response_time"]) / len(data["avg_response_time"]) if data["avg_response_time"] else 0
            results.append({
                "intent": intent,
                "count": data["count"],
                "percentage": round(data["count"] / len(filtered) * 100, 1),
                "avg_response_time_ms": round(avg_time, 1),
                "success_rate": round(data["success_count"] / data["count"] * 100, 1),
                "context_used_rate": round(data["context_used_count"] / data["count"] * 100, 1)
            })
        
        # Sort by count descending
        results.sort(key=lambda x: x["count"], reverse=True)
        
        return {
            "total_queries": len(filtered),
            "days_analyzed": days,
            "unique_intents": len(results),
            "intents": results[:20],
            "timestamp": datetime.now().isoformat()
        }
    
    async def get_user_analytics(
        self,
        tenant_code: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get user-level analytics."""
        recent = await self.get_recent_activity(tenant_code, limit=5000)
        
        cutoff = datetime.now() - timedelta(days=days)
        filtered = []
        for entry in recent:
            created_at = datetime.fromisoformat(entry.get("created_at", ""))
            if created_at >= cutoff:
                filtered.append(entry)
        
        if not filtered:
            return {"error": "No data available", "users": []}
        
        # Group by user
        user_data = defaultdict(lambda: {
            "user_id": None,
            "user_role": None,
            "query_count": 0,
            "total_response_time": 0,
            "avg_response_time": 0,
            "last_active": None,
            "top_intents": Counter(),
            "context_used_count": 0,
            "suggestions_accepted": 0
        })
        
        for entry in filtered:
            user_id = entry.get("user_id")
            if not user_id:
                continue
            
            user_data[user_id]["user_id"] = user_id
            user_data[user_id]["user_role"] = entry.get("user_role", "unknown")
            user_data[user_id]["query_count"] += 1
            user_data[user_id]["total_response_time"] += entry.get("processing_time_ms", 0)
            user_data[user_id]["top_intents"][entry.get("intent", "UNKNOWN")] += 1
            if entry.get("context_used"):
                user_data[user_id]["context_used_count"] += 1
            if entry.get("suggestion_accepted"):
                user_data[user_id]["suggestions_accepted"] += 1
            
            created_at = entry.get("created_at")
            if created_at:
                if not user_data[user_id]["last_active"] or created_at > user_data[user_id]["last_active"]:
                    user_data[user_id]["last_active"] = created_at
        
        # Calculate averages and format
        results = []
        for user_id, data in user_data.items():
            results.append({
                "user_id": data["user_id"],
                "user_role": data["user_role"],
                "query_count": data["query_count"],
                "avg_response_time_ms": round(data["total_response_time"] / data["query_count"], 1) if data["query_count"] > 0 else 0,
                "last_active": data["last_active"],
                "top_intent": data["top_intents"].most_common(1)[0][0] if data["top_intents"] else "N/A",
                "context_usage_rate": round(data["context_used_count"] / data["query_count"] * 100, 1) if data["query_count"] > 0 else 0,
                "suggestions_accepted": data["suggestions_accepted"]
            })
        
        # Sort by query count descending
        results.sort(key=lambda x: x["query_count"], reverse=True)
        
        return {
            "total_users": len(results),
            "total_queries": len(filtered),
            "days_analyzed": days,
            "users": results[:20],
            "timestamp": datetime.now().isoformat()
        }
    
    async def get_performance_trends(
        self,
        tenant_code: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """Get performance trends over time."""
        recent = await self.get_recent_activity(tenant_code, limit=5000)
        
        cutoff = datetime.now() - timedelta(days=days)
        filtered = []
        for entry in recent:
            created_at = datetime.fromisoformat(entry.get("created_at", ""))
            if created_at >= cutoff:
                filtered.append(entry)
        
        if not filtered:
            return {"error": "No data available", "trends": []}
        
        # Group by day
        daily_data = defaultdict(lambda: {
            "date": None,
            "query_count": 0,
            "avg_response_time": [],
            "success_count": 0,
            "context_used_count": 0
        })
        
        for entry in filtered:
            created_at = datetime.fromisoformat(entry.get("created_at", ""))
            date_key = created_at.strftime("%Y-%m-%d")
            
            daily_data[date_key]["date"] = date_key
            daily_data[date_key]["query_count"] += 1
            if entry.get("processing_time_ms"):
                daily_data[date_key]["avg_response_time"].append(entry["processing_time_ms"])
            if entry.get("success", True):
                daily_data[date_key]["success_count"] += 1
            if entry.get("context_used"):
                daily_data[date_key]["context_used_count"] += 1
        
        # Format results
        results = []
        for date_key, data in sorted(daily_data.items()):
            avg_time = sum(data["avg_response_time"]) / len(data["avg_response_time"]) if data["avg_response_time"] else 0
            results.append({
                "date": date_key,
                "query_count": data["query_count"],
                "avg_response_time_ms": round(avg_time, 1),
                "success_rate": round(data["success_count"] / data["query_count"] * 100, 1) if data["query_count"] > 0 else 0,
                "context_usage_rate": round(data["context_used_count"] / data["query_count"] * 100, 1) if data["query_count"] > 0 else 0
            })
        
        return {
            "days": days,
            "trends": results,
            "timestamp": datetime.now().isoformat()
        }
    
    async def export_analytics_csv(
        self,
        tenant_code: str,
        days: int = 30
    ) -> str:
        """Export analytics as CSV string."""
        recent = await self.get_recent_activity(tenant_code, limit=10000)
        
        cutoff = datetime.now() - timedelta(days=days)
        filtered = []
        for entry in recent:
            created_at = datetime.fromisoformat(entry.get("created_at", ""))
            if created_at >= cutoff:
                filtered.append(entry)
        
        if not filtered:
            return "No data available"
        
        # Build CSV
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "Timestamp", "User ID", "User Role", "Intent", "Query",
            "Response Time (ms)", "Success", "Context Used", "Suggestion Accepted"
        ])
        
        # Data rows
        for entry in filtered:
            writer.writerow([
                entry.get("created_at", ""),
                entry.get("user_id", ""),
                entry.get("user_role", ""),
                entry.get("intent", ""),
                entry.get("query", ""),
                entry.get("processing_time_ms", 0),
                "Yes" if entry.get("success", True) else "No",
                "Yes" if entry.get("context_used", False) else "No",
                entry.get("suggestion_accepted", "") or ""
            ])
        
        return output.getvalue()
    
    # =========================================================
    # HELPER METHODS
    # =========================================================
    
    def _percentile(self, values: List[float], percentile: int) -> float:
        """Calculate percentile of a list of values."""
        if not values:
            return 0
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile / 100)
        return round(sorted_values[min(index, len(sorted_values) - 1)], 1)
    
    def _empty_summary(self, period: str, start_date: datetime, end_date: datetime) -> Dict:
        """Return empty summary when no data."""
        return {
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_queries": 0,
            "successful": 0,
            "failed": 0,
            "success_rate": 0,
            "active_users": 0,
            "top_intents": [],
            "response_times": {"average_ms": 0, "min_ms": 0, "max_ms": 0, "p95_ms": 0},
            "context_usage": {"used_count": 0, "used_percent": 0},
            "suggestions": {"shown_count": 0, "accepted_count": 0, "acceptance_rate": 0},
            "user_roles": {},
            "timestamp": datetime.now().isoformat(),
            "message": "No activity data available for this period"
        }


# Singleton instance
_activity_logger = None


def get_activity_logger() -> ActivityLogger:
    """Get or create ActivityLogger singleton."""
    global _activity_logger
    if _activity_logger is None:
        _activity_logger = ActivityLogger()
    return _activity_logger