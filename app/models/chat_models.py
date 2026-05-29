"""
Chat Conversation Models - Persistent Storage
==============================================
Database models for storing chat conversations and messages.

Tables:
- ConversationSession: Metadata about each conversation
- ChatMessage: Individual messages in a conversation

FIXED: Uses its own Base to avoid circular imports
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, JSON, Index, ForeignKey, Text
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Create its own Base to avoid circular imports with notification_models
Base = declarative_base()


class ConversationSession(Base):
    """
    Stores metadata about a conversation session.
    
    A session is a conversation between a user and the AI assistant.
    Multiple conversations can exist per user.
    """
    __tablename__ = "conversation_sessions"
    
    # Primary key
    id = Column(String(255), primary_key=True, nullable=False)
    
    # User info
    user_id = Column(Integer, nullable=False, index=True)
    company_code = Column(String(50), nullable=False, index=True)
    
    # Session metadata
    title = Column(String(255), nullable=True)  # User can name the conversation
    description = Column(Text, nullable=True)
    
    # Session status
    is_active = Column(Boolean, default=True)
    archived_at = Column(DateTime, nullable=True)
    
    # Context
    last_intent = Column(String(100), nullable=True)
    last_entity_mentioned = Column(String(255), nullable=True)
    message_count = Column(Integer, default=0)
    
    # Session metadata (JSON for flexibility)
    context_data = Column(JSON, nullable=True)  # Store context like:
    # {
    #   "customer_code": "CUST001",
    #   "order_id": "ORD123",
    #   "item_codes": ["ITEM1", "ITEM2"],
    #   "tags": ["urgent", "vip_customer"]
    # }
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    messages = relationship("ChatMessage", backref="session", cascade="all, delete-orphan")
    
    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_user_company_created', 'user_id', 'company_code', 'created_at'),
        Index('idx_user_active', 'user_id', 'is_active'),
        Index('idx_company_created', 'company_code', 'created_at'),
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON response"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'company_code': self.company_code,
            'title': self.title,
            'description': self.description,
            'is_active': self.is_active,
            'last_intent': self.last_intent,
            'message_count': self.message_count,
            'context': self.context_data or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ChatMessage(Base):
    """
    Stores individual messages in a conversation.
    
    Each message has:
    - Content (what was said)
    - Role (user or assistant)
    - Intent and entities (for analytics)
    - Timestamps (when it was created)
    """
    __tablename__ = "chat_messages"
    
    # Primary key
    id = Column(String(255), primary_key=True, nullable=False)
    
    # Foreign key
    session_id = Column(String(255), ForeignKey('conversation_sessions.id'), nullable=False, index=True)
    
    # Message metadata
    user_id = Column(Integer, nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    
    # Message content
    content = Column(Text, nullable=False)
    
    # Processing metadata
    intent = Column(String(100), nullable=True)  # e.g., GET_ITEM_PRICE, CREATE_QUOTE
    entities = Column(JSON, nullable=True)  # {item_name, customer_name, quantity, etc.}
    
    # Response metadata (for assistant messages)
    processing_time_ms = Column(Integer, nullable=True)  # How long it took to generate
    model_used = Column(String(50), nullable=True)  # e.g., groq, openai, llama
    confidence_score = Column(Integer, nullable=True)  # 0-100 for intent confidence
    
    # Message status
    is_edited = Column(Boolean, default=False)
    edited_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_session_created', 'session_id', 'created_at'),
        Index('idx_user_created', 'user_id', 'created_at'),
        Index('idx_role_intent', 'role', 'intent'),
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON response"""
        return {
            'id': self.id,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'role': self.role,
            'content': self.content,
            'intent': self.intent,
            'entities': self.entities or {},
            'processing_time_ms': self.processing_time_ms,
            'model_used': self.model_used,
            'confidence_score': self.confidence_score,
            'is_edited': self.is_edited,
            'is_deleted': self.is_deleted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# Helper functions for the models

def create_session_dict(
    session_id: str,
    user_id: int,
    company_code: str,
    title: str = None,
    context: dict = None
) -> dict:
    """Create a session dictionary for database storage"""
    return {
        'id': session_id,
        'user_id': user_id,
        'company_code': company_code,
        'title': title,
        'is_active': True,
        'message_count': 0,
        'context_data': context or {},
        'created_at': datetime.utcnow(),
    }


def create_message_dict(
    message_id: str,
    session_id: str,
    user_id: int,
    role: str,
    content: str,
    intent: str = None,
    entities: dict = None,
    processing_time_ms: int = None,
    model_used: str = None
) -> dict:
    """Create a message dictionary for database storage"""
    return {
        'id': message_id,
        'session_id': session_id,
        'user_id': user_id,
        'role': role,
        'content': content,
        'intent': intent,
        'entities': entities or {},
        'processing_time_ms': processing_time_ms,
        'model_used': model_used,
        'created_at': datetime.utcnow(),
    }