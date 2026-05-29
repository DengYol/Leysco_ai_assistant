"""
Database Models for Notifications System
==========================================
SQLAlchemy ORM models for persistent notification storage.

Database: PostgreSQL
ORM: SQLAlchemy 2.0+

FIXED: Renamed 'metadata' column to 'metadata_json' (metadata is a reserved word in SQLAlchemy)
UPDATED: Create chat models tables in init_db() to avoid circular imports
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, JSON, Index, ForeignKey,
    create_engine, text, Numeric
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()


class Notification(Base):
    """
    Notification model for persistent storage.
    
    Stores all notifications (alerts, informational, critical).
    Includes indexes for efficient querying.
    """
    __tablename__ = "notifications"
    
    # Primary key
    id = Column(String(255), primary_key=True, nullable=False)
    
    # Foreign keys
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    
    # Notification content
    title = Column(String(255), nullable=False)
    message = Column(String(1000), nullable=False)
    priority = Column(String(20), nullable=False, default='LOW')  # CRITICAL, HIGH, MEDIUM, LOW
    category = Column(String(50), nullable=False, default='general')  # alert, inventory, delivery, etc.
    icon = Column(String(100), nullable=False, default='notifications')
    action = Column(String(500), nullable=True)  # What action to take (e.g., "price of item")
    
    # Metadata - FIXED: renamed from 'metadata' to 'metadata_json' (metadata is SQLAlchemy reserved)
    actionable = Column(Boolean, default=True)
    metadata_json = Column(JSON, nullable=True)  # Additional data (item_name, quantity, etc.)
    
    # Status
    is_read = Column(Boolean, default=False, index=True)
    read_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)  # When notification becomes stale
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Escalation tracking
    is_escalated = Column(Boolean, default=False)
    escalated_at = Column(DateTime, nullable=True)
    escalated_to_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="notifications")
    escalated_to = relationship("User", foreign_keys=[escalated_to_user_id])
    
    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_user_id_created_at', 'user_id', 'created_at'),
        Index('idx_user_id_is_read', 'user_id', 'is_read'),
        Index('idx_user_id_priority', 'user_id', 'priority'),
        Index('idx_user_id_expires_at', 'user_id', 'expires_at'),
        Index('idx_priority_is_read', 'priority', 'is_read'),
        Index('idx_category', 'category'),
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON response"""
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'priority': self.priority,
            'category': self.category,
            'icon': self.icon,
            'action': self.action,
            'actionable': self.actionable,
            'metadata': self.metadata_json or {},
            'is_read': self.is_read,
            'is_escalated': self.is_escalated,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'read_at': self.read_at.isoformat() if self.read_at else None,
        }
    
    def is_expired(self) -> bool:
        """Check if notification has expired"""
        return datetime.utcnow() > self.expires_at
    
    def mark_as_read(self) -> None:
        """Mark notification as read"""
        self.is_read = True
        self.read_at = datetime.utcnow()
    
    def mark_as_escalated(self, escalated_to_user_id: int) -> None:
        """Mark notification as escalated"""
        self.is_escalated = True
        self.escalated_at = datetime.utcnow()
        self.escalated_to_user_id = escalated_to_user_id


class NotificationEscalation(Base):
    """
    Track escalation history of notifications.
    
    When a critical notification is unread for too long,
    it gets escalated to a manager.
    """
    __tablename__ = "notification_escalations"
    
    id = Column(String(255), primary_key=True, nullable=False)
    notification_id = Column(String(255), ForeignKey('notifications.id'), nullable=False, index=True)
    
    # Who it was assigned to and escalated to
    assigned_to_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    escalated_to_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Status
    status = Column(String(50), nullable=False, default='pending')  # pending, escalated, acknowledged
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    escalated_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    
    # Relationships
    notification = relationship("Notification", backref="escalations")
    assigned_to = relationship("User", foreign_keys=[assigned_to_user_id])
    escalated_to = relationship("User", foreign_keys=[escalated_to_user_id])
    
    __table_args__ = (
        Index('idx_notification_id_status', 'notification_id', 'status'),
        Index('idx_escalated_to_user_id', 'escalated_to_user_id'),
    )


class NotificationAnalytics(Base):
    """
    Track notification interactions for analytics.
    
    Records: viewed, clicked, dismissed, escalated, etc.
    Used to measure notification effectiveness.
    """
    __tablename__ = "notification_analytics"
    
    id = Column(String(255), primary_key=True, nullable=False)
    notification_id = Column(String(255), ForeignKey('notifications.id'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    
    # Action taken
    action = Column(String(50), nullable=False)  # viewed, clicked, dismissed, escalated
    action_intent = Column(String(100), nullable=True)  # What was the resulting action
    
    # Timing
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    time_to_action_seconds = Column(Integer, nullable=True)  # Seconds from notification to action
    
    __table_args__ = (
        Index('idx_user_id_timestamp', 'user_id', 'timestamp'),
        Index('idx_notification_id_action', 'notification_id', 'action'),
    )


class UserNotificationPreference(Base):
    """
    User notification preferences and settings.
    
    Controls which notifications user receives and how.
    """
    __tablename__ = "user_notification_preferences"
    
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True, nullable=False)
    
    # Category toggles (which alerts to receive)
    alert_out_of_stock = Column(Boolean, default=True)
    alert_low_stock = Column(Boolean, default=True)
    alert_overdue_delivery = Column(Boolean, default=True)
    alert_slow_moving = Column(Boolean, default=False)
    alert_price_change = Column(Boolean, default=True)
    alert_customer_credit = Column(Boolean, default=True)
    alert_late_payment = Column(Boolean, default=True)
    alert_system = Column(Boolean, default=True)
    
    # Quiet hours (don't show notifications during these times)
    quiet_hours_enabled = Column(Boolean, default=False)
    quiet_start_time = Column(String(5), nullable=True)  # "18:00" (6 PM)
    quiet_end_time = Column(String(5), nullable=True)    # "09:00" (9 AM)
    
    # Delivery channels
    push_enabled = Column(Boolean, default=True)  # Mobile push notifications
    email_critical = Column(Boolean, default=True)  # Email for CRITICAL priority
    email_high = Column(Boolean, default=False)  # Email for HIGH priority
    
    # Digest settings
    digest_enabled = Column(Boolean, default=False)  # Daily/weekly digest instead of realtime
    digest_frequency = Column(String(20), default='daily')  # daily, weekly
    digest_time = Column(String(5), default='09:00')  # When to send digest
    
    # Snoozed notifications
    snoozed_until = Column(DateTime, nullable=True)  # Don't show notifications until this time
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = relationship("User", backref="notification_preferences")


class User(Base):
    """
    Minimal user model for foreign key references.
    
    If you already have a User model, you can remove this
    and update the foreign keys to reference your existing User model.
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, nullable=False)
    username = Column(String(255), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================================
# Database Connection & Session Management
# ============================================================================

class DatabaseManager:
    """Manage database connection and sessions"""
    
    def __init__(self, database_url: str):
        """
        Initialize database manager.
        
        Args:
            database_url: PostgreSQL connection string
                Example: postgresql://user:password@localhost:5432/leysco
        """
        self.database_url = database_url
        self.engine = None
        self.SessionLocal = None
    
    def initialize(self):
        """Create engine and session factory"""
        self.engine = create_engine(
            self.database_url,
            echo=False,  # Set to True for SQL debugging
            pool_pre_ping=True,  # Verify connection before using
            pool_size=10,
            max_overflow=20,
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )
        logger.info("✅ Database manager initialized")
    
    def create_all_tables(self):
        """Create all tables in the database"""
        if self.engine is None:
            raise RuntimeError("Database manager not initialized. Call initialize() first.")
        
        Base.metadata.create_all(bind=self.engine)
        logger.info("✅ All database tables created")
    
    def get_session(self):
        """Get a new database session"""
        if self.SessionLocal is None:
            raise RuntimeError("Database manager not initialized. Call initialize() first.")
        return self.SessionLocal()
    
    def drop_all_tables(self):
        """Drop all tables (use with caution!)"""
        if self.engine is None:
            raise RuntimeError("Database manager not initialized. Call initialize() first.")
        
        Base.metadata.drop_all(bind=self.engine)
        logger.info("⚠️ All database tables dropped")


# ============================================================================
# Helper Functions
# ============================================================================

def get_db():
    """Dependency injection for FastAPI"""
    db = db_manager.get_session()
    try:
        yield db
    finally:
        db.close()


# Global database manager instance
db_manager: DatabaseManager = None


def init_db(database_url: str):
    """
    Initialize the database.
    
    Call this once at application startup.
    
    Args:
        database_url: PostgreSQL connection string
    
    Example:
        init_db("postgresql://user:pass@localhost/leysco")
    """
    global db_manager
    db_manager = DatabaseManager(database_url)
    db_manager.initialize()
    
    # Create notification tables
    db_manager.create_all_tables()
    logger.info("✅ All notification tables created")
    
    # NEW: Create chat tables (lazy import to avoid circular imports)
    try:
        from app.models.chat_models import Base as ChatBase
        ChatBase.metadata.create_all(bind=db_manager.engine)
        logger.info("✅ Chat model tables created")
    except Exception as e:
        logger.warning(f"⚠️ Could not create chat tables: {e}")
    
    # NEW: Lazy import chat models to register them
    try:
        from app.models.chat_models import ConversationSession, ChatMessage
        logger.info("✅ Chat models registered")
    except Exception as e:
        logger.warning(f"⚠️ Could not register chat models: {e}")
    
    logger.info("✅ Database initialization complete")