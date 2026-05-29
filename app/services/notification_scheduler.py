"""
Background scheduled jobs for notifications.
Handles cleanup and escalation tasks.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.notification_service import get_notification_service

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: AsyncIOScheduler = None


async def cleanup_expired_notifications_job():
    """
    Delete notifications older than 7 days.
    Runs daily at 2:00 AM.
    """
    try:
        logger.info("🧹 Starting notification cleanup job...")
        notification_service = get_notification_service()
        
        deleted_count = await notification_service.cleanup_expired_notifications()
        
        logger.info(f"✅ Cleanup completed. Deleted {deleted_count} expired notifications")
        
    except Exception as e:
        logger.error(f"❌ Error in cleanup job: {e}", exc_info=True)


async def check_escalation_job():
    """
    Check for critical notifications that need escalation.
    Runs every hour.
    
    If a CRITICAL notification is unread for > 2 hours, escalate to manager.
    """
    try:
        logger.info("🔄 Starting escalation check job...")
        notification_service = get_notification_service()
        
        # For now, escalate to manager user_id=1 (you can make this configurable)
        # TODO: Get list of all managers and check escalations for each
        MANAGER_USER_ID = 1
        
        escalated_count = await notification_service.check_escalation_needed(MANAGER_USER_ID)
        
        if escalated_count > 0:
            logger.warning(f"⚠️ Escalated {escalated_count} notifications to manager")
        else:
            logger.debug("No escalations needed")
        
    except Exception as e:
        logger.error(f"❌ Error in escalation job: {e}", exc_info=True)


def init_scheduler():
    """
    Initialize the APScheduler.
    
    Call this once at application startup in main.py:
    
    Example:
        from app.services.notification_scheduler import init_scheduler
        
        @app.on_event("startup")
        async def startup():
            init_scheduler()
    """
    global _scheduler
    
    if _scheduler is not None:
        logger.warning("Scheduler already initialized")
        return
    
    try:
        _scheduler = AsyncIOScheduler()
        
        # Add cleanup job - Daily at 2:00 AM
        _scheduler.add_job(
            cleanup_expired_notifications_job,
            CronTrigger(hour=2, minute=0),
            id='notification_cleanup',
            name='Notification Cleanup',
            replace_existing=True,
            misfire_grace_time=60
        )
        logger.info("✅ Scheduled notification cleanup: Daily at 2:00 AM")
        
        # Add escalation check job - Every hour
        _scheduler.add_job(
            check_escalation_job,
            CronTrigger(minute=0),
            id='notification_escalation',
            name='Notification Escalation Check',
            replace_existing=True,
            misfire_grace_time=30
        )
        logger.info("✅ Scheduled escalation check: Every hour")
        
        _scheduler.start()
        logger.info("✅ Background scheduler started successfully")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize scheduler: {e}", exc_info=True)
        raise


def shutdown_scheduler():
    """
    Shutdown the scheduler.
    
    Call this at application shutdown:
    
    Example:
        from app.services.notification_scheduler import shutdown_scheduler
        
        @app.on_event("shutdown")
        async def shutdown():
            shutdown_scheduler()
    """
    global _scheduler
    
    if _scheduler is None:
        return
    
    try:
        _scheduler.shutdown()
        logger.info("✅ Background scheduler shut down")
    except Exception as e:
        logger.error(f"Error shutting down scheduler: {e}")


def get_scheduler() -> AsyncIOScheduler:
    """Get the scheduler instance"""
    return _scheduler


def add_custom_job(
    func,
    trigger_type: str = 'cron',
    job_id: str = None,
    name: str = None,
    **trigger_kwargs
):
    """
    Add a custom job to the scheduler.
    
    Example:
        # Run every 5 minutes
        add_custom_job(
            my_function,
            trigger_type='interval',
            job_id='my_job',
            name='My Job',
            minutes=5
        )
        
        # Run at specific time
        add_custom_job(
            my_function,
            trigger_type='cron',
            job_id='my_job',
            hour=14,  # 2 PM
            minute=30
        )
    """
    if _scheduler is None:
        logger.error("Scheduler not initialized")
        return
    
    try:
        from apscheduler.triggers.interval import IntervalTrigger
        from apscheduler.triggers.cron import CronTrigger
        
        if trigger_type == 'interval':
            trigger = IntervalTrigger(**trigger_kwargs)
        elif trigger_type == 'cron':
            trigger = CronTrigger(**trigger_kwargs)
        else:
            raise ValueError(f"Unknown trigger type: {trigger_type}")
        
        _scheduler.add_job(
            func,
            trigger,
            id=job_id,
            name=name,
            replace_existing=True
        )
        logger.info(f"✅ Added job: {name or job_id}")
        
    except Exception as e:
        logger.error(f"❌ Error adding job: {e}")


# ============================================================================
# MANUAL JOB RUNNERS (for testing)
# ============================================================================

async def run_cleanup_now():
    """Run cleanup immediately (useful for testing)"""
    await cleanup_expired_notifications_job()


async def run_escalation_now():
    """Run escalation check immediately (useful for testing)"""
    await check_escalation_job()