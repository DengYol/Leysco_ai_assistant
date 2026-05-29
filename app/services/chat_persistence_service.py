"""
Chat Persistence Service - Save/Load Conversations
==================================================
Handles saving and loading chat messages from the database.

Key features:
- Save messages immediately to database
- Load conversation history on startup
- Handle graceful shutdown
- Keep in-memory cache for performance
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.models import notification_models
from app.models.chat_models import ConversationSession, ChatMessage

logger = logging.getLogger(__name__)


class ChatPersistenceService:
    """Service for saving and loading chat conversations"""
    
    def __init__(self):
        logger.info("✅ ChatPersistenceService initialized")
    
    # ========================================================================
    # SESSION OPERATIONS
    # ========================================================================
    
    async def create_session(
        self,
        session_id: str,
        user_id: int,
        company_code: str,
        title: str = None,
        context: dict = None
    ) -> bool:
        """Create a new conversation session"""
        session = None
        try:
            if notification_models.db_manager is None:
                logger.warning("Database not initialized - session not persisted")
                return False
            
            session = notification_models.db_manager.get_session()
            
            # Check if already exists
            existing = session.query(ConversationSession).filter(
                ConversationSession.id == session_id
            ).first()
            
            if existing:
                logger.debug(f"Session {session_id} already exists")
                return True
            
            # Create new
            conv_session = ConversationSession(
                id=session_id,
                user_id=user_id,
                company_code=company_code,
                title=title,
                context_data=context or {},
                created_at=datetime.utcnow()
            )
            
            session.add(conv_session)
            session.commit()
            
            logger.info(f"✅ Created session {session_id} for user {user_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            if session:
                session.rollback()
            return False
        finally:
            if session:
                session.close()
    
    async def get_session(self, session_id: str) -> Optional[dict]:
        """Get session metadata"""
        session = None
        try:
            if notification_models.db_manager is None:
                return None
            
            session = notification_models.db_manager.get_session()
            
            conv_session = session.query(ConversationSession).filter(
                ConversationSession.id == session_id
            ).first()
            
            if conv_session:
                return conv_session.to_dict()
            
            return None
        
        except Exception as e:
            logger.error(f"Error getting session: {e}")
            return None
        finally:
            if session:
                session.close()
    
    async def update_session_metadata(
        self,
        session_id: str,
        **kwargs
    ) -> bool:
        """Update session metadata (title, context, etc.)"""
        session = None
        try:
            if notification_models.db_manager is None:
                return False
            
            session = notification_models.db_manager.get_session()
            
            conv_session = session.query(ConversationSession).filter(
                ConversationSession.id == session_id
            ).first()
            
            if not conv_session:
                return False
            
            # Update allowed fields
            allowed_fields = {'title', 'description', 'context_data', 'last_intent', 'last_entity_mentioned'}
            for key, value in kwargs.items():
                if key in allowed_fields and hasattr(conv_session, key):
                    setattr(conv_session, key, value)
            
            conv_session.updated_at = datetime.utcnow()
            session.commit()
            
            logger.debug(f"✅ Updated session {session_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error updating session: {e}")
            if session:
                session.rollback()
            return False
        finally:
            if session:
                session.close()
    
    # ========================================================================
    # MESSAGE OPERATIONS
    # ========================================================================
    
    async def save_message(
        self,
        message_id: str,
        session_id: str,
        user_id: int,
        role: str,
        content: str,
        intent: str = None,
        entities: dict = None,
        processing_time_ms: int = None,
        model_used: str = None
    ) -> bool:
        """Save a single message to database"""
        session = None
        try:
            if notification_models.db_manager is None:
                logger.warning("Database not initialized - message not persisted")
                return False
            
            session = notification_models.db_manager.get_session()
            
            # Create message
            chat_message = ChatMessage(
                id=message_id,
                session_id=session_id,
                user_id=user_id,
                role=role,
                content=content,
                intent=intent,
                entities=entities or {},
                processing_time_ms=processing_time_ms,
                model_used=model_used,
                created_at=datetime.utcnow()
            )
            
            session.add(chat_message)
            
            # Increment message count on session
            conv_session = session.query(ConversationSession).filter(
                ConversationSession.id == session_id
            ).first()
            
            if conv_session:
                conv_session.message_count += 1
                conv_session.updated_at = datetime.utcnow()
                if intent:
                    conv_session.last_intent = intent
            
            session.commit()
            
            logger.debug(f"✅ Saved message {message_id} to session {session_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error saving message: {e}")
            if session:
                session.rollback()
            return False
        finally:
            if session:
                session.close()
    
    async def get_session_history(
        self,
        session_id: str,
        limit: int = 100
    ) -> List[dict]:
        """Get all messages in a session"""
        session = None
        try:
            if notification_models.db_manager is None:
                logger.warning("Database not initialized")
                return []
            
            session = notification_models.db_manager.get_session()
            
            messages = session.query(ChatMessage).filter(
                ChatMessage.session_id == session_id,
                ChatMessage.is_deleted == False
            ).order_by(ChatMessage.created_at.asc()).limit(limit).all()
            
            result = [msg.to_dict() for msg in messages]
            
            logger.debug(f"✅ Retrieved {len(result)} messages from session {session_id}")
            return result
        
        except Exception as e:
            logger.error(f"Error getting history: {e}")
            return []
        finally:
            if session:
                session.close()
    
    async def get_user_sessions(
        self,
        user_id: int,
        company_code: str,
        limit: int = 20
    ) -> List[dict]:
        """Get all sessions for a user"""
        session = None
        try:
            if notification_models.db_manager is None:
                return []
            
            session = notification_models.db_manager.get_session()
            
            sessions = session.query(ConversationSession).filter(
                ConversationSession.user_id == user_id,
                ConversationSession.company_code == company_code,
                ConversationSession.is_active == True,
                ConversationSession.archived_at == None
            ).order_by(ConversationSession.created_at.desc()).limit(limit).all()
            
            result = [s.to_dict() for s in sessions]
            
            logger.debug(f"✅ Retrieved {len(result)} sessions for user {user_id}")
            return result
        
        except Exception as e:
            logger.error(f"Error getting sessions: {e}")
            return []
        finally:
            if session:
                session.close()
    
    # ========================================================================
    # CLEANUP OPERATIONS
    # ========================================================================
    
    async def archive_session(self, session_id: str) -> bool:
        """Archive a conversation (soft delete)"""
        session = None
        try:
            if notification_models.db_manager is None:
                return False
            
            session = notification_models.db_manager.get_session()
            
            conv_session = session.query(ConversationSession).filter(
                ConversationSession.id == session_id
            ).first()
            
            if conv_session:
                conv_session.is_active = False
                conv_session.archived_at = datetime.utcnow()
                session.commit()
                
                logger.info(f"✅ Archived session {session_id}")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Error archiving session: {e}")
            if session:
                session.rollback()
            return False
        finally:
            if session:
                session.close()
    
    async def cleanup_old_sessions(self, days: int = 90) -> int:
        """Delete conversations older than N days"""
        session = None
        try:
            if notification_models.db_manager is None:
                return 0
            
            session = notification_models.db_manager.get_session()
            
            cutoff_date = datetime.utcnow() - __import__('datetime').timedelta(days=days)
            
            deleted = session.query(ConversationSession).filter(
                ConversationSession.created_at < cutoff_date
            ).delete()
            
            session.commit()
            
            logger.info(f"🧹 Cleaned up {deleted} old conversations")
            return deleted
        
        except Exception as e:
            logger.error(f"Error cleaning up: {e}")
            if session:
                session.rollback()
            return 0
        finally:
            if session:
                session.close()


# Global service instance
_chat_persistence_service = None


def get_chat_persistence_service() -> ChatPersistenceService:
    """Get chat persistence service singleton"""
    global _chat_persistence_service
    if _chat_persistence_service is None:
        _chat_persistence_service = ChatPersistenceService()
    return _chat_persistence_service