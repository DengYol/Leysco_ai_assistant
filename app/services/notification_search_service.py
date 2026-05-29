"""
Notification Search & Filter Service - Phase 2
===============================================
Full-text search, filtering, and advanced queries on notifications.

Supports:
- Keyword search in title/message
- Priority filtering (CRITICAL, HIGH, MEDIUM, LOW)
- Category filtering (inventory, delivery, pricing, etc.)
- Date range filtering
- Read/unread status
- Combined queries
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from app.models import notification_models
from app.models.notification_models import Notification

logger = logging.getLogger(__name__)


class NotificationSearchService:
    """Search and filter notifications"""
    
    def __init__(self):
        logger.info("✅ NotificationSearchService initialized")
    
    async def search(
        self,
        user_id: int,
        query: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        read_status: Optional[str] = None,  # "read", "unread", or None for all
        limit: int = 50,
        offset: int = 0
    ) -> Dict:
        """
        Advanced search with multiple filters.
        
        Args:
            user_id: User ID
            query: Free text search in title/message
            priority: CRITICAL, HIGH, MEDIUM, LOW
            category: inventory, delivery, pricing, etc.
            from_date: ISO format date string (2026-05-01)
            to_date: ISO format date string (2026-05-31)
            read_status: "read", "unread", or None
            limit: Max results
            offset: Pagination offset
        
        Returns:
            Dict with notifications, total_count, and filters_applied
        """
        session = None
        try:
            if notification_models.db_manager is None:
                return {"notifications": [], "total_count": 0, "filters": {}}
            
            session: Session = notification_models.db_manager.get_session()
            
            # Start with base query
            base_query = session.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.expires_at > datetime.utcnow()
            )
            
            # Apply filters
            filters_applied = {}
            
            # Text search (title and message)
            if query:
                search_term = f"%{query}%"
                base_query = base_query.filter(
                    or_(
                        Notification.title.ilike(search_term),
                        Notification.message.ilike(search_term)
                    )
                )
                filters_applied["query"] = query
            
            # Priority filter
            if priority and priority.upper() in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                base_query = base_query.filter(Notification.priority == priority.upper())
                filters_applied["priority"] = priority.upper()
            
            # Category filter
            if category:
                base_query = base_query.filter(Notification.category == category.lower())
                filters_applied["category"] = category.lower()
            
            # Date range filter
            if from_date:
                try:
                    from_datetime = datetime.fromisoformat(from_date)
                    base_query = base_query.filter(Notification.created_at >= from_datetime)
                    filters_applied["from_date"] = from_date
                except ValueError:
                    logger.warning(f"Invalid from_date: {from_date}")
            
            if to_date:
                try:
                    to_datetime = datetime.fromisoformat(to_date)
                    base_query = base_query.filter(Notification.created_at <= to_datetime)
                    filters_applied["to_date"] = to_date
                except ValueError:
                    logger.warning(f"Invalid to_date: {to_date}")
            
            # Read status filter
            if read_status and read_status.lower() == "read":
                base_query = base_query.filter(Notification.is_read == True)
                filters_applied["read_status"] = "read"
            elif read_status and read_status.lower() == "unread":
                base_query = base_query.filter(Notification.is_read == False)
                filters_applied["read_status"] = "unread"
            
            # Get total count before pagination
            total_count = base_query.count()
            
            # Sort by priority and date
            priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            results = base_query.order_by(
                desc(Notification.created_at)
            ).offset(offset).limit(limit).all()
            
            # Sort by priority in Python
            results.sort(
                key=lambda x: (priority_order.get(x.priority, 999), -x.created_at.timestamp())
            )
            
            notifications = [n.to_dict() for n in results]
            
            logger.info(
                f"✅ Search completed for user {user_id}: "
                f"found {total_count} results (returned {len(notifications)})"
            )
            
            return {
                "notifications": notifications,
                "total_count": total_count,
                "returned_count": len(notifications),
                "offset": offset,
                "limit": limit,
                "filters": filters_applied
            }
            
        except Exception as e:
            logger.error(f"Error searching notifications: {e}")
            return {"notifications": [], "total_count": 0, "filters": {}}
        finally:
            if session:
                session.close()
    
    async def get_categories(self, user_id: int) -> Dict:
        """Get list of notification categories and their counts"""
        session = None
        try:
            if notification_models.db_manager is None:
                return {}
            
            session: Session = notification_models.db_manager.get_session()
            
            results = session.query(
                Notification.category
            ).filter(
                Notification.user_id == user_id,
                Notification.expires_at > datetime.utcnow()
            ).group_by(Notification.category).all()
            
            categories = {}
            for row in results:
                if row[0]:
                    category = row[0]
                    count = session.query(Notification).filter(
                        Notification.user_id == user_id,
                        Notification.category == category,
                        Notification.expires_at > datetime.utcnow()
                    ).count()
                    categories[category] = count
            
            logger.debug(f"Categories for user {user_id}: {categories}")
            return categories
            
        except Exception as e:
            logger.error(f"Error getting categories: {e}")
            return {}
        finally:
            if session:
                session.close()
    
    async def get_summary(self, user_id: int) -> Dict:
        """Get notification summary by priority and category"""
        session = None
        try:
            if notification_models.db_manager is None:
                return {}
            
            session: Session = notification_models.db_manager.get_session()
            
            # Count by priority
            priority_counts = {}
            for priority in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                count = session.query(Notification).filter(
                    Notification.user_id == user_id,
                    Notification.priority == priority,
                    Notification.expires_at > datetime.utcnow()
                ).count()
                if count > 0:
                    priority_counts[priority] = count
            
            # Count by category
            category_counts = await self.get_categories(user_id)
            
            # Count read/unread
            unread = session.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.is_read == False,
                Notification.expires_at > datetime.utcnow()
            ).count()
            
            read = session.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.is_read == True,
                Notification.expires_at > datetime.utcnow()
            ).count()
            
            # Total
            total = session.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.expires_at > datetime.utcnow()
            ).count()
            
            return {
                "total": total,
                "read": read,
                "unread": unread,
                "by_priority": priority_counts,
                "by_category": category_counts
            }
            
        except Exception as e:
            logger.error(f"Error getting summary: {e}")
            return {}
        finally:
            if session:
                session.close()


# Global service instance
_search_service = None


def get_search_service() -> NotificationSearchService:
    """Get search service singleton"""
    global _search_service
    if _search_service is None:
        _search_service = NotificationSearchService()
    return _search_service