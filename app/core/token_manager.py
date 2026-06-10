"""
app/core/token_manager.py
=========================

Token management system with expiration and refresh token support.

Features:
  - JWT token generation and validation
  - Token expiration tracking
  - Refresh token rotation
  - Token blacklisting
  - Configurable token lifetime

Usage:
  from app.core.token_manager import TokenManager, get_token_manager
  
  manager = get_token_manager()
  
  # Create token
  token = manager.create_token(
      user_id=123,
      role="sales_rep",
      company_code="TEST001",
      expires_in_hours=24
  )
  
  # Validate token
  claims = manager.validate_token(token)
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import jwt
import logging
import os
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# TOKEN TYPES
# ============================================================================

class TokenType(Enum):
    """Token types"""
    ACCESS = "access"
    REFRESH = "refresh"
    API = "api"


# ============================================================================
# TOKEN CLAIMS
# ============================================================================

class TokenClaims:
    """JWT token claims"""
    
    def __init__(
        self,
        user_id: int,
        role: str,
        company_code: str,
        token_type: str = "access",
        expires_at: Optional[datetime] = None,
        issued_at: Optional[datetime] = None,
    ):
        self.user_id = user_id
        self.role = role
        self.company_code = company_code
        self.token_type = token_type
        self.expires_at = expires_at or (datetime.utcnow() + timedelta(hours=24))
        self.issued_at = issued_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "user_id": self.user_id,
            "role": self.role,
            "company_code": self.company_code,
            "token_type": self.token_type,
            "exp": int(self.expires_at.timestamp()),
            "iat": int(self.issued_at.timestamp()),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenClaims":
        """Create from dictionary"""
        return cls(
            user_id=data["user_id"],
            role=data["role"],
            company_code=data["company_code"],
            token_type=data.get("token_type", "access"),
            expires_at=datetime.fromtimestamp(data["exp"]),
            issued_at=datetime.fromtimestamp(data["iat"]),
        )


# ============================================================================
# TOKEN MANAGER
# ============================================================================

class TokenManager:
    """
    Token management with JWT and refresh token support.
    
    Features:
    - JWT token generation and validation
    - Refresh token rotation
    - Token blacklisting
    - Expiration tracking
    """
    
    def __init__(self):
        """Initialize token manager"""
        self.secret_key = os.getenv(
            "JWT_SECRET_KEY",
            "your-secret-key-change-in-production"
        )
        self.algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        self.access_token_expire_hours = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", 24))
        self.refresh_token_expire_days = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 30))
        
        # In-memory blacklist (use Redis in production)
        self.blacklist = set()
        
        logger.info("✅ TokenManager initialized")
        logger.info(f"   - Algorithm: {self.algorithm}")
        logger.info(f"   - Access token lifetime: {self.access_token_expire_hours} hours")
        logger.info(f"   - Refresh token lifetime: {self.refresh_token_expire_days} days")
    
    def create_token(
        self,
        user_id: int,
        role: str,
        company_code: str,
        token_type: str = "access",
        expires_in_hours: Optional[int] = None,
    ) -> str:
        """
        Create a new JWT token.
        
        Args:
            user_id: User ID
            role: User role
            company_code: Company/tenant code
            token_type: "access" or "refresh"
            expires_in_hours: Custom expiration (hours)
        
        Returns:
            JWT token string
        """
        if expires_in_hours is None:
            if token_type == "refresh":
                expires_in_hours = self.refresh_token_expire_days * 24
            else:
                expires_in_hours = self.access_token_expire_hours
        
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=expires_in_hours)
        
        claims = TokenClaims(
            user_id=user_id,
            role=role,
            company_code=company_code,
            token_type=token_type,
            expires_at=expires_at,
            issued_at=now,
        )
        
        try:
            token = jwt.encode(
                claims.to_dict(),
                self.secret_key,
                algorithm=self.algorithm,
            )
            logger.info(
                f"Token created: user={user_id}, role={role}, type={token_type}",
                extra={"user_id": user_id, "token_type": token_type}
            )
            return token
        except Exception as e:
            logger.error(f"Failed to create token: {e}")
            raise
    
    def validate_token(self, token: str) -> Optional[TokenClaims]:
        """
        Validate and decode JWT token.
        
        Args:
            token: JWT token string
        
        Returns:
            TokenClaims if valid, None if invalid
        """
        try:
            # Check blacklist
            if token in self.blacklist:
                logger.warning("Token is blacklisted")
                return None
            
            # Decode and validate
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )
            
            # Check expiration
            exp = payload.get("exp")
            if exp and datetime.fromtimestamp(exp) < datetime.utcnow():
                logger.warning("Token expired")
                return None
            
            return TokenClaims.from_dict(payload)
        
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return None
    
    def refresh_token(self, old_token: str) -> Optional[str]:
        """
        Create a new access token from a refresh token.
        
        Args:
            old_token: Valid refresh token
        
        Returns:
            New access token string, or None if invalid
        """
        claims = self.validate_token(old_token)
        if not claims:
            logger.warning("Cannot refresh with invalid token")
            return None
        
        if claims.token_type != "refresh":
            logger.warning("Cannot refresh with non-refresh token")
            return None
        
        # Create new access token
        new_token = self.create_token(
            user_id=claims.user_id,
            role=claims.role,
            company_code=claims.company_code,
            token_type="access",
        )
        
        # Blacklist old refresh token
        self.blacklist.add(old_token)
        
        logger.info(f"Token refreshed: user={claims.user_id}")
        return new_token
    
    def blacklist_token(self, token: str):
        """Add token to blacklist (logout)"""
        self.blacklist.add(token)
        logger.info("Token blacklisted")
    
    def get_token_info(self, token: str) -> Optional[Dict[str, Any]]:
        """Get token information without validation"""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_signature": False},
            )
            return payload
        except Exception as e:
            logger.error(f"Cannot decode token: {e}")
            return None
    
    def is_token_expired(self, token: str) -> bool:
        """Check if token is expired"""
        claims = self.validate_token(token)
        return claims is None
    
    def get_token_ttl(self, token: str) -> Optional[int]:
        """Get token time-to-live in seconds"""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_signature": False},
            )
            exp = payload.get("exp")
            if exp:
                ttl = int(exp - datetime.utcnow().timestamp())
                return max(0, ttl)
        except Exception:
            pass
        return None


# ============================================================================
# GLOBAL TOKEN MANAGER INSTANCE
# ============================================================================

_token_manager_instance: Optional[TokenManager] = None


def get_token_manager() -> TokenManager:
    """Get or create global token manager instance"""
    global _token_manager_instance
    if _token_manager_instance is None:
        _token_manager_instance = TokenManager()
    return _token_manager_instance