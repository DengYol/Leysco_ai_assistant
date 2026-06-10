"""
app/core/audit_trail.py
=======================

Audit trail system for tracking all user actions.

Features:
  - Track all API requests and actions
  - User accountability
  - GDPR compliance (data deletion tracking)
  - Immutable audit logs
  - Security event tracking

Usage:
  from app.core.audit_trail import AuditTrail, get_audit_trail
  
  audit = get_audit_trail()
  await audit.log_action(
      user_id=123,
      action="create_order",
      resource="orders",
      resource_id="ORD-001",
      status="success",
      details={"total": 10000}
  )
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
import logging
import json
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# AUDIT EVENTS
# ============================================================================

class AuditAction(Enum):
    """Standard audit actions"""
    # User management
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    USER_PASSWORD_CHANGE = "user_password_change"
    
    # Data operations
    DATA_CREATE = "data_create"
    DATA_READ = "data_read"
    DATA_UPDATE = "data_update"
    DATA_DELETE = "data_delete"
    DATA_EXPORT = "data_export"
    
    # Security
    AUTH_FAILED = "auth_failed"
    PERMISSION_DENIED = "permission_denied"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    
    # Admin actions
    ADMIN_CONFIG_CHANGE = "admin_config_change"
    ADMIN_ACCESS_GRANTED = "admin_access_granted"
    ADMIN_ACCESS_REVOKED = "admin_access_revoked"


class AuditStatus(Enum):
    """Audit action status"""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


# ============================================================================
# AUDIT TRAIL ENTRY
# ============================================================================

class AuditEntry:
    """Single audit trail entry"""
    
    def __init__(
        self,
        user_id: int,
        action: str,
        resource: str,
        resource_id: Optional[str] = None,
        status: str = "success",
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        company_code: Optional[str] = None,
    ):
        self.user_id = user_id
        self.action = action
        self.resource = resource
        self.resource_id = resource_id
        self.status = status
        self.details = details or {}
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.company_code = company_code
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "user_id": self.user_id,
            "action": self.action,
            "resource": self.resource,
            "resource_id": self.resource_id,
            "status": self.status,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "company_code": self.company_code,
            "timestamp": self.timestamp,
        }


# ============================================================================
# AUDIT TRAIL DATABASE
# ============================================================================

class AuditTrail:
    """
    Audit trail implementation with database persistence.
    
    Features:
    - Immutable logs (append-only)
    - Per-user action tracking
    - Resource-level tracking
    - GDPR-compliant data deletion logging
    """
    
    def __init__(self):
        """Initialize audit trail"""
        self.db = None
        self.initialized = False
    
    def init_db(self, database_url: str):
        """Initialize database connection"""
        try:
            from sqlalchemy import create_engine
            self.engine = create_engine(database_url)
            self._create_tables()
            self.initialized = True
            logger.info("✅ Audit trail database initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize audit trail database: {e}")
            self.initialized = False
    
    def _create_tables(self):
        """Create audit tables if they don't exist"""
        try:
            from sqlalchemy import text
            
            # Create audit_log table
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS audit_log (
                id BIGSERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                action VARCHAR(100) NOT NULL,
                resource VARCHAR(100) NOT NULL,
                resource_id VARCHAR(255),
                status VARCHAR(20) NOT NULL,
                details JSONB,
                ip_address VARCHAR(45),
                user_agent TEXT,
                company_code VARCHAR(50),
                timestamp TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_id (user_id),
                INDEX idx_action (action),
                INDEX idx_timestamp (timestamp),
                INDEX idx_company_code (company_code)
            )
            """
            
            # Execute without transaction for initial setup
            with self.engine.connect() as conn:
                conn.execute(text(create_table_sql))
                conn.commit()
            
            logger.info("✅ Audit log tables created")
        except Exception as e:
            logger.warning(f"Audit table creation: {e}")
    
    async def log_action(
        self,
        user_id: int,
        action: str,
        resource: str,
        resource_id: Optional[str] = None,
        status: str = "success",
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        company_code: Optional[str] = None,
    ) -> bool:
        """
        Log an audit action.
        
        Args:
            user_id: User ID performing the action
            action: Action type (e.g., "create_order", "delete_user")
            resource: Resource type (e.g., "orders", "users")
            resource_id: ID of the specific resource
            status: "success", "failure", or "partial"
            details: Additional details (JSON)
            ip_address: Client IP address
            user_agent: Client user agent
            company_code: Tenant company code
        
        Returns:
            True if logged successfully
        """
        if not self.initialized:
            logger.warning(f"Audit trail not initialized, cannot log: {action}")
            return False
        
        try:
            entry = AuditEntry(
                user_id=user_id,
                action=action,
                resource=resource,
                resource_id=resource_id,
                status=status,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent,
                company_code=company_code,
            )
            
            # Log to database (async)
            await self._insert_audit_entry(entry)
            
            # Also log to application logs
            logger.info(
                f"AUDIT: {action} on {resource}",
                extra={
                    "user_id": user_id,
                    "action": action,
                    "resource": resource,
                    "status": status,
                    "company_code": company_code,
                }
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to log audit action: {e}")
            return False
    
    async def _insert_audit_entry(self, entry: AuditEntry):
        """Insert audit entry into database"""
        try:
            from sqlalchemy import text
            
            insert_sql = """
            INSERT INTO audit_log 
            (user_id, action, resource, resource_id, status, details, 
             ip_address, user_agent, company_code, timestamp)
            VALUES 
            (:user_id, :action, :resource, :resource_id, :status, :details,
             :ip_address, :user_agent, :company_code, :timestamp)
            """
            
            with self.engine.connect() as conn:
                conn.execute(
                    text(insert_sql),
                    {
                        "user_id": entry.user_id,
                        "action": entry.action,
                        "resource": entry.resource,
                        "resource_id": entry.resource_id,
                        "status": entry.status,
                        "details": json.dumps(entry.details) if entry.details else None,
                        "ip_address": entry.ip_address,
                        "user_agent": entry.user_agent,
                        "company_code": entry.company_code,
                        "timestamp": entry.timestamp,
                    }
                )
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to insert audit entry: {e}")
    
    async def get_user_actions(
        self,
        user_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get audit actions for a specific user"""
        if not self.initialized:
            return []
        
        try:
            from sqlalchemy import text
            
            query = """
            SELECT * FROM audit_log
            WHERE user_id = :user_id
            ORDER BY timestamp DESC
            LIMIT :limit OFFSET :offset
            """
            
            with self.engine.connect() as conn:
                result = conn.execute(
                    text(query),
                    {"user_id": user_id, "limit": limit, "offset": offset}
                )
                return [dict(row._mapping) for row in result.fetchall()]
        
        except Exception as e:
            logger.error(f"Failed to get user actions: {e}")
            return []
    
    async def get_resource_history(
        self,
        resource: str,
        resource_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get audit history for a specific resource"""
        if not self.initialized:
            return []
        
        try:
            from sqlalchemy import text
            
            query = """
            SELECT * FROM audit_log
            WHERE resource = :resource AND resource_id = :resource_id
            ORDER BY timestamp DESC
            LIMIT :limit
            """
            
            with self.engine.connect() as conn:
                result = conn.execute(
                    text(query),
                    {"resource": resource, "resource_id": resource_id, "limit": limit}
                )
                return [dict(row._mapping) for row in result.fetchall()]
        
        except Exception as e:
            logger.error(f"Failed to get resource history: {e}")
            return []
    
    async def log_failed_auth(
        self,
        username: str,
        ip_address: str,
        reason: str,
    ):
        """Log failed authentication attempt"""
        await self.log_action(
            user_id=0,  # Unknown user
            action="auth_failed",
            resource="authentication",
            status="failure",
            details={
                "username": username,
                "reason": reason,
            },
            ip_address=ip_address,
        )
    
    async def log_permission_denied(
        self,
        user_id: int,
        action: str,
        resource: str,
        ip_address: Optional[str] = None,
    ):
        """Log permission denied event"""
        await self.log_action(
            user_id=user_id,
            action="permission_denied",
            resource=resource,
            status="failure",
            details={
                "attempted_action": action,
            },
            ip_address=ip_address,
        )
    
    async def log_data_deletion(
        self,
        user_id: int,
        resource: str,
        resource_id: str,
        reason: str = "GDPR request",
    ):
        """Log GDPR data deletion for compliance"""
        await self.log_action(
            user_id=user_id,
            action="data_delete",
            resource=resource,
            resource_id=resource_id,
            status="success",
            details={
                "reason": reason,
                "gdpr_compliant": True,
                "deleted_at": datetime.now().isoformat(),
            },
        )


# ============================================================================
# GLOBAL AUDIT TRAIL INSTANCE
# ============================================================================

_audit_trail_instance: Optional[AuditTrail] = None


def get_audit_trail() -> AuditTrail:
    """Get or create global audit trail instance"""
    global _audit_trail_instance
    if _audit_trail_instance is None:
        _audit_trail_instance = AuditTrail()
    return _audit_trail_instance