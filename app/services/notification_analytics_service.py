"""
Notification Analytics Service - Phase 2
=========================================
Tracks notification metrics: volume, engagement, performance.

Metrics:
- Notification volume over time
- Category breakdown
- User engagement (read rate, response time)
- Escalation metrics
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import notification_models
from app.models.notification_models import Notification, NotificationAnalytics

logger = logging.getLogger(__name__)


class NotificationAnalyticsService:
    """Analytics for notifications"""
    
    def __init__(self):
        logger.info("✅ NotificationAnalyticsService initialized")
    
    async def get_summary(self, user_id: int, days: int = 30) -> Dict:
        """
        Get analytics summary for user.
        
        Args:
            user_id: User ID
            days: Look back period (default 30 days)
        
        Returns:
            Dict with metrics
        """
        session = None
        try:
            if notification_models.db_manager is None:
                return {}
            
            session: Session = notification_models.db_manager.get_session()
            
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Total notifications in period
            total = session.query(func.count(Notification.id)).filter(
                Notification.user_id == user_id,
                Notification.created_at >= cutoff_date
            ).scalar() or 0
            
            # Read vs unread
            read_count = session.query(func.count(Notification.id)).filter(
                Notification.user_id == user_id,
                Notification.created_at >= cutoff_date,
                Notification.is_read == True
            ).scalar() or 0
            
            unread_count = session.query(func.count(Notification.id)).filter(
                Notification.user_id == user_id,
                Notification.created_at >= cutoff_date,
                Notification.is_read == False
            ).scalar() or 0
            
            read_rate = (read_count / total * 100) if total > 0 else 0
            
            # Escalations
            escalations = session.query(func.count(Notification.id)).filter(
                Notification.user_id == user_id,
                Notification.created_at >= cutoff_date,
                Notification.is_escalated == True
            ).scalar() or 0
            
            # By priority
            by_priority = {}
            for priority in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                count = session.query(func.count(Notification.id)).filter(
                    Notification.user_id == user_id,
                    Notification.created_at >= cutoff_date,
                    Notification.priority == priority
                ).scalar() or 0
                if count > 0:
                    by_priority[priority] = count
            
            # By category
            by_category = {}
            categories = session.query(Notification.category).filter(
                Notification.user_id == user_id,
                Notification.created_at >= cutoff_date
            ).distinct().all()
            
            for cat_row in categories:
                category = cat_row[0]
                if category:
                    count = session.query(func.count(Notification.id)).filter(
                        Notification.user_id == user_id,
                        Notification.created_at >= cutoff_date,
                        Notification.category == category
                    ).scalar() or 0
                    by_category[category] = count
            
            return {
                "period_days": days,
                "total": total,
                "read": read_count,
                "unread": unread_count,
                "read_rate_percent": round(read_rate, 2),
                "escalations": escalations,
                "by_priority": by_priority,
                "by_category": by_category
            }
            
        except Exception as e:
            logger.error(f"Error getting analytics summary: {e}")
            return {}
        finally:
            if session:
                session.close()
    
    async def get_timeline(
        self,
        user_id: int,
        days: int = 30,
        group_by: str = "day"  # day, week, month
    ) -> List[Dict]:
        """
        Get notification timeline (volume over time).
        
        Args:
            user_id: User ID
            days: Look back period
            group_by: Grouping interval
        
        Returns:
            List of timeline points with counts
        """
        session = None
        try:
            if notification_models.db_manager is None:
                return []
            
            session: Session = notification_models.db_manager.get_session()
            
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            notifications = session.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.created_at >= cutoff_date
            ).all()
            
            # Group by date
            timeline_data = defaultdict(int)
            
            for notif in notifications:
                if group_by == "day":
                    key = notif.created_at.date().isoformat()
                elif group_by == "week":
                    week_start = notif.created_at.date() - timedelta(days=notif.created_at.weekday())
                    key = week_start.isoformat()
                elif group_by == "month":
                    key = notif.created_at.strftime("%Y-%m")
                else:
                    key = notif.created_at.date().isoformat()
                
                timeline_data[key] += 1
            
            # Convert to sorted list
            result = [
                {"date": date, "count": count}
                for date, count in sorted(timeline_data.items())
            ]
            
            logger.debug(f"Timeline for user {user_id}: {len(result)} data points")
            return result
            
        except Exception as e:
            logger.error(f"Error getting timeline: {e}")
            return []
        finally:
            if session:
                session.close()
    
    async def get_by_category(self, user_id: int, days: int = 30) -> Dict:
        """Get notification breakdown by category"""
        session = None
        try:
            if notification_models.db_manager is None:
                return {}
            
            session: Session = notification_models.db_manager.get_session()
            
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            results = session.query(
                Notification.category,
                Notification.priority,
                func.count(Notification.id).label("count")
            ).filter(
                Notification.user_id == user_id,
                Notification.created_at >= cutoff_date
            ).group_by(
                Notification.category,
                Notification.priority
            ).all()
            
            by_category = defaultdict(lambda: {"total": 0, "by_priority": {}})
            
            for category, priority, count in results:
                cat = category or "unknown"
                by_category[cat]["total"] += count
                by_category[cat]["by_priority"][priority] = count
            
            return dict(by_category)
            
        except Exception as e:
            logger.error(f"Error getting category breakdown: {e}")
            return {}
        finally:
            if session:
                session.close()
    
    async def get_engagement_stats(self, user_id: int, days: int = 30) -> Dict:
        """
        Get user engagement metrics.
        
        Metrics:
        - Average time to read notification
        - Read rate
        - Action rate (clicked action)
        """
        session = None
        try:
            if notification_models.db_manager is None:
                return {}
            
            session: Session = notification_models.db_manager.get_session()
            
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Notifications sent
            total_sent = session.query(func.count(Notification.id)).filter(
                Notification.user_id == user_id,
                Notification.created_at >= cutoff_date
            ).scalar() or 0
            
            # Notifications read
            read = session.query(func.count(Notification.id)).filter(
                Notification.user_id == user_id,
                Notification.created_at >= cutoff_date,
                Notification.is_read == True
            ).scalar() or 0
            
            read_rate = (read / total_sent * 100) if total_sent > 0 else 0
            
            # Average time to read (estimated from read_at - created_at)
            notif_with_read = session.query(
                func.avg(Notification.read_at - Notification.created_at).label("avg_time")
            ).filter(
                Notification.user_id == user_id,
                Notification.created_at >= cutoff_date,
                Notification.is_read == True,
                Notification.read_at.isnot(None)
            ).scalar()
            
            avg_time_to_read_seconds = 0
            if notif_with_read:
                try:
                    # This is a timedelta
                    avg_time_to_read_seconds = notif_with_read.total_seconds()
                except:
                    pass
            
            # Actions taken on actionable notifications
            actionable = session.query(func.count(Notification.id)).filter(
                Notification.user_id == user_id,
                Notification.created_at >= cutoff_date,
                Notification.actionable == True
            ).scalar() or 0
            
            action_rate = (read / actionable * 100) if actionable > 0 else 0
            
            # Average priority
            priority_values = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
            avg_priority = session.query(
                func.avg(
                    func.coalesce(
                        func.cast(
                            func.field("priority"), type_=None
                        ),
                        2
                    )
                )
            ).filter(
                Notification.user_id == user_id,
                Notification.created_at >= cutoff_date
            ).scalar()
            
            return {
                "period_days": days,
                "total_sent": total_sent,
                "total_read": read,
                "read_rate_percent": round(read_rate, 2),
                "avg_time_to_read_seconds": round(avg_time_to_read_seconds, 2),
                "actionable_notifications": actionable,
                "action_rate_percent": round(action_rate, 2)
            }
            
        except Exception as e:
            logger.error(f"Error getting engagement stats: {e}")
            return {}
        finally:
            if session:
                session.close()


# Global service instance
_analytics_service = None


def get_analytics_service() -> NotificationAnalyticsService:
    """Get analytics service singleton"""
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = NotificationAnalyticsService()
    return _analytics_service