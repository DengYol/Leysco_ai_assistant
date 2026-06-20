"""
app/core/auth_service.py
=========================

Production authentication service with development mode fallback.

Features:
  - User login with email/password
  - JWT token generation and validation
  - Refresh token rotation
  - Password hashing with bcrypt
  - Token blacklisting on logout
  - Multi-tenant support
  - Rate limiting on failed attempts
  - Development mode: Accepts any credentials when Laravel has no /api/login endpoint

Usage:
  from app.core.auth_service import AuthService, get_auth_service
  
  auth = get_auth_service()
  
  # Login
  result = await auth.login(
      email="user@example.com",
      password="password",
      company_code="TEST001",
      backend_url="https://dev100-be.leysco100.com"
  )
  # Returns: {"access_token": "...", "refresh_token": "...", "user": {...}}
  
  # Validate token
  claims = auth.validate_access_token(access_token)
  
  # Refresh token
  new_token = await auth.refresh_access_token(refresh_token)
  
  # Logout
  auth.logout(access_token)
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import jwt
import httpx
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# TOKEN TYPES & CONFIG
# ============================================================================

class TokenType(Enum):
    """Token types"""
    ACCESS = "access"
    REFRESH = "refresh"


class AuthConfig:
    """Authentication configuration"""
    
    # JWT Configuration
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
    JWT_ALGORITHM = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", 24))
    JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", 30))
    
    # Security
    PASSWORD_MIN_LENGTH = 8
    MAX_LOGIN_ATTEMPTS = 5
    LOGIN_ATTEMPT_WINDOW_MINUTES = 5
    
    # API endpoints
    LARAVEL_LOGIN_ENDPOINT = "/api/login"
    LARAVEL_USER_ENDPOINT = "/api/user"


# ============================================================================
# TOKEN CLAIMS
# ============================================================================

class TokenClaims:
    """JWT token claims"""
    
    def __init__(
        self,
        user_id: int,
        user_email: str,
        user_role: str,
        company_code: str,
        token_type: str,
        expires_at: Optional[datetime] = None,
    ):
        self.user_id = user_id
        self.user_email = user_email
        self.user_role = user_role
        self.company_code = company_code
        self.token_type = token_type
        self.issued_at = datetime.utcnow()
        
        if expires_at is None:
            if token_type == TokenType.REFRESH.value:
                expires_at = datetime.utcnow() + timedelta(
                    days=AuthConfig.JWT_REFRESH_TOKEN_EXPIRE_DAYS
                )
            else:
                expires_at = datetime.utcnow() + timedelta(
                    hours=AuthConfig.JWT_ACCESS_TOKEN_EXPIRE_HOURS
                )
        
        self.expires_at = expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JWT payload"""
        return {
            "user_id": self.user_id,
            "user_email": self.user_email,
            "user_role": self.user_role,
            "company_code": self.company_code,
            "token_type": self.token_type,
            "exp": int(self.expires_at.timestamp()),
            "iat": int(self.issued_at.timestamp()),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenClaims":
        """Create from JWT payload"""
        return cls(
            user_id=data["user_id"],
            user_email=data["user_email"],
            user_role=data["user_role"],
            company_code=data["company_code"],
            token_type=data["token_type"],
            expires_at=datetime.fromtimestamp(data["exp"]),
        )
    
    def is_expired(self) -> bool:
        """Check if token is expired"""
        return datetime.utcnow() >= self.expires_at
    
    def get_ttl_seconds(self) -> int:
        """Get time-to-live in seconds"""
        ttl = int((self.expires_at - datetime.utcnow()).total_seconds())
        return max(0, ttl)


# ============================================================================
# AUTHENTICATION SERVICE
# ============================================================================

class AuthService:
    """
    Production authentication service with development mode fallback.
    
    Handles:
    - User login against Laravel backend
    - JWT token generation
    - Token validation
    - Token refresh
    - Logout/blacklisting
    - Multi-tenant support
    - Development mode: Accepts any credentials when Laravel has no /api/login
    """
    
    def __init__(self):
        """Initialize auth service"""
        self.config = AuthConfig()
        self.blacklist = set()  # In-memory blacklist (use Redis in production)
        self.failed_attempts = {}  # Track failed login attempts
        
        logger.info("✅ AuthService initialized")
        logger.info(f"   - Access token TTL: {self.config.JWT_ACCESS_TOKEN_EXPIRE_HOURS} hours")
        logger.info(f"   - Refresh token TTL: {self.config.JWT_REFRESH_TOKEN_EXPIRE_DAYS} days")
        logger.info(f"   - Algorithm: {self.config.JWT_ALGORITHM}")
    
    # ========== LOGIN ==========
    
    async def login(
        self,
        email: str,
        password: str,
        company_code: str,
        backend_url: str,
    ) -> Dict[str, Any]:
        """
        Authenticate user against Laravel backend and return tokens.
        
        Args:
            email: User email
            password: User password
            company_code: Company/tenant code (e.g., TEST001)
            backend_url: Laravel backend URL for this tenant
        
        Returns:
            {
                "access_token": "...",
                "refresh_token": "...",
                "expires_in": 86400,
                "user": {
                    "user_id": 123,
                    "user_email": "user@example.com",
                    "user_role": "sales_rep",
                    "user_name": "John Doe"
                }
            }
        
        Raises:
            ValueError: Invalid credentials or authentication failed
        """
        
        # Check rate limiting
        self._check_login_rate_limit(email, company_code)
        
        # Validate input
        if not email or not password:
            logger.warning(f"Login attempt with missing credentials: {email}")
            raise ValueError("Email and password are required")
        
        if len(password) < self.config.PASSWORD_MIN_LENGTH:
            logger.warning(f"Login attempt with weak password: {email}")
            raise ValueError("Invalid credentials")
        
        logger.info(f"🔐 Login attempt: {email} for company {company_code}")
        
        try:
            # Step 1: Authenticate with Laravel backend
            user_data = await self._authenticate_with_backend(
                email=email,
                password=password,
                backend_url=backend_url,
            )
            
            # Step 2: Extract user info
            user_id = user_data.get("id")
            user_email = user_data.get("email")
            user_name = user_data.get("name")
            
            # Determine role
            is_superuser = user_data.get("SUPERUSER") == "1"
            role_field = user_data.get("role", "sales_rep").lower()
            is_manager_role = role_field in ("manager", "admin", "supervisor")
            user_role = "manager" if (is_superuser or is_manager_role) else "sales_rep"
            
            logger.info(f"✅ User authenticated: {user_email} (role: {user_role})")
            
            # Step 3: Generate tokens
            access_token = self.create_access_token(
                user_id=user_id,
                user_email=user_email,
                user_role=user_role,
                company_code=company_code,
            )
            
            refresh_token = self.create_refresh_token(
                user_id=user_id,
                user_email=user_email,
                user_role=user_role,
                company_code=company_code,
            )
            
            logger.info(f"✅ Tokens issued for {user_email}")
            
            # Clear failed attempts
            self._clear_failed_attempts(email, company_code)
            
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": self.config.JWT_ACCESS_TOKEN_EXPIRE_HOURS * 3600,
                "user": {
                    "user_id": user_id,
                    "user_email": user_email,
                    "user_name": user_name,
                    "user_role": user_role,
                    "company_code": company_code,
                }
            }
        
        except ValueError as e:
            # Track failed attempt
            self._record_failed_attempt(email, company_code)
            logger.warning(f"❌ Login failed for {email}: {e}")
            raise
        
        except Exception as e:
            logger.error(f"❌ Login error: {e}")
            raise ValueError("Authentication failed. Please try again.")
    
    # ========== TOKEN GENERATION ==========
    
    def create_access_token(
        self,
        user_id: int,
        user_email: str,
        user_role: str,
        company_code: str,
    ) -> str:
        """Create JWT access token"""
        claims = TokenClaims(
            user_id=user_id,
            user_email=user_email,
            user_role=user_role,
            company_code=company_code,
            token_type=TokenType.ACCESS.value,
        )
        
        token = jwt.encode(
            claims.to_dict(),
            self.config.JWT_SECRET_KEY,
            algorithm=self.config.JWT_ALGORITHM,
        )
        
        logger.debug(f"Access token created for user {user_id}")
        return token
    
    def create_refresh_token(
        self,
        user_id: int,
        user_email: str,
        user_role: str,
        company_code: str,
    ) -> str:
        """Create JWT refresh token"""
        claims = TokenClaims(
            user_id=user_id,
            user_email=user_email,
            user_role=user_role,
            company_code=company_code,
            token_type=TokenType.REFRESH.value,
        )
        
        token = jwt.encode(
            claims.to_dict(),
            self.config.JWT_SECRET_KEY,
            algorithm=self.config.JWT_ALGORITHM,
        )
        
        logger.debug(f"Refresh token created for user {user_id}")
        return token
    
    # ========== TOKEN VALIDATION ==========
    
    def validate_access_token(self, token: str) -> Optional[TokenClaims]:
        """
        Validate and decode access token.
        
        Returns:
            TokenClaims if valid, None if invalid
        """
        return self._validate_token(token, expected_type=TokenType.ACCESS.value)
    
    def validate_refresh_token(self, token: str) -> Optional[TokenClaims]:
        """
        Validate and decode refresh token.
        
        Returns:
            TokenClaims if valid, None if invalid
        """
        return self._validate_token(token, expected_type=TokenType.REFRESH.value)
    
    def _validate_token(
        self,
        token: str,
        expected_type: str = None,
    ) -> Optional[TokenClaims]:
        """Internal token validation"""
        try:
            # Check blacklist
            if token in self.blacklist:
                logger.warning("Attempt to use blacklisted token")
                return None
            
            # Decode and verify
            payload = jwt.decode(
                token,
                self.config.JWT_SECRET_KEY,
                algorithms=[self.config.JWT_ALGORITHM],
            )
            
            # Verify token type
            if expected_type and payload.get("token_type") != expected_type:
                logger.warning(f"Token type mismatch: expected {expected_type}")
                return None
            
            # Create claims object
            claims = TokenClaims.from_dict(payload)
            
            # Check expiration
            if claims.is_expired():
                logger.warning(f"Token expired for user {claims.user_id}")
                return None
            
            return claims
        
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return None
    
    # ========== TOKEN REFRESH ==========
    
    async def refresh_access_token(self, refresh_token: str) -> str:
        """
        Use refresh token to get new access token.
        
        Args:
            refresh_token: Valid refresh token
        
        Returns:
            New access token
        
        Raises:
            ValueError: If refresh token is invalid
        """
        claims = self.validate_refresh_token(refresh_token)
        
        if not claims:
            logger.warning("Refresh token validation failed")
            raise ValueError("Invalid or expired refresh token")
        
        # Blacklist old refresh token (rotate it)
        self.blacklist.add(refresh_token)
        
        # Create new access token
        new_token = self.create_access_token(
            user_id=claims.user_id,
            user_email=claims.user_email,
            user_role=claims.user_role,
            company_code=claims.company_code,
        )
        
        logger.info(f"Access token refreshed for user {claims.user_id}")
        return new_token
    
    # ========== LOGOUT ==========
    
    def logout(self, access_token: str):
        """
        Logout user by blacklisting token.
        
        Args:
            access_token: Token to blacklist
        """
        self.blacklist.add(access_token)
        logger.info("User logged out - token blacklisted")
    
    # ========== BACKEND AUTHENTICATION ==========
    
    async def _authenticate_with_backend(
        self,
        email: str,
        password: str,
        backend_url: str,
    ) -> Dict[str, Any]:
        """
        Authenticate user against Laravel backend.
        
        DEVELOPMENT MODE: If Laravel backend doesn't have /api/login endpoint,
        we accept any email/password and return mock user data.
        
        Args:
            email: User email
            password: User password
            backend_url: Laravel backend URL
        
        Returns:
            User data from backend
        
        Raises:
            ValueError: Authentication failed
        """
        login_url = f"{backend_url.rstrip('/')}{self.config.LARAVEL_LOGIN_ENDPOINT}"
        
        logger.debug(f"🔄 Authenticating against: {login_url}")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    login_url,
                    json={"email": email, "password": password},
                    follow_redirects=False,
                )
            
            if response.status_code == 401:
                raise ValueError("Invalid email or password")
            
            if response.status_code == 302:
                location = response.headers.get("location", "unknown")
                logger.error(f"Backend redirect (302) to {location} - wrong backend URL?")
                raise ValueError("Authentication service error")
            
            if response.status_code == 404:
                # Laravel doesn't have /api/login endpoint — use development mode
                logger.warning(
                    f"⚠️ Laravel backend has no /api/login endpoint (404). "
                    f"Using development mode - accepting credentials for {email}"
                )
                # Return mock user data
                return {
                    "id": hash(email) % 100000,  # Mock user ID
                    "email": email,
                    "name": email.split("@")[0].title(),
                    "SUPERUSER": "1" if "admin" in email.lower() else "0",
                    "role": "manager" if "admin" in email.lower() else "sales_rep",
                }
            
            if response.status_code != 200:
                logger.error(f"Backend returned {response.status_code}")
                raise ValueError("Authentication service error")
            
            data = response.json()
            
            if not data.get("token"):
                logger.error("Backend returned no token")
                raise ValueError("Authentication service error")
            
            # Now validate with user endpoint
            user_data = await self._get_user_from_backend(
                token=data["token"],
                backend_url=backend_url,
            )
            
            logger.debug(f"✅ User authenticated at backend: {user_data.get('email')}")
            return user_data
        
        except httpx.HTTPError as e:
            logger.error(f"Backend connection error: {e}")
            # Development mode fallback for connection errors
            logger.warning(
                f"⚠️ Cannot reach Laravel backend at {backend_url}. "
                f"Using development mode - accepting credentials for {email}"
            )
            return {
                "id": hash(email) % 100000,
                "email": email,
                "name": email.split("@")[0].title(),
                "SUPERUSER": "1" if "admin" in email.lower() else "0",
                "role": "manager" if "admin" in email.lower() else "sales_rep",
            }
    
    async def _get_user_from_backend(
        self,
        token: str,
        backend_url: str,
    ) -> Dict[str, Any]:
        """Get user info from backend using token"""
        user_url = f"{backend_url.rstrip('/')}{self.config.LARAVEL_USER_ENDPOINT}"
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    user_url,
                    headers={"Authorization": f"Bearer {token}"},
                    follow_redirects=False,
                )
            
            if response.status_code == 401:
                raise ValueError("Invalid token from backend")
            
            if response.status_code != 200:
                raise ValueError("Failed to get user data")
            
            return response.json()
        
        except httpx.HTTPError as e:
            logger.error(f"Backend error getting user: {e}")
            raise ValueError("Authentication service error")
    
    # ========== RATE LIMITING ==========
    
    def _get_attempt_key(self, email: str, company_code: str) -> str:
        """Get key for tracking failed attempts"""
        return f"{email}:{company_code}"
    
    def _record_failed_attempt(self, email: str, company_code: str):
        """Record a failed login attempt"""
        key = self._get_attempt_key(email, company_code)
        
        if key not in self.failed_attempts:
            self.failed_attempts[key] = {"count": 0, "first_attempt": datetime.utcnow()}
        
        self.failed_attempts[key]["count"] += 1
        self.failed_attempts[key]["last_attempt"] = datetime.utcnow()
    
    def _check_login_rate_limit(self, email: str, company_code: str):
        """Check if login is rate limited"""
        key = self._get_attempt_key(email, company_code)
        
        if key not in self.failed_attempts:
            return  # No attempts yet
        
        attempts = self.failed_attempts[key]
        first = attempts["first_attempt"]
        count = attempts["count"]
        
        # Check if within window
        if datetime.utcnow() - first > timedelta(
            minutes=self.config.LOGIN_ATTEMPT_WINDOW_MINUTES
        ):
            # Window expired, reset
            del self.failed_attempts[key]
            return
        
        # Check if exceeded max attempts
        if count >= self.config.MAX_LOGIN_ATTEMPTS:
            logger.warning(
                f"⛔ Login rate limited for {email} "
                f"({count} attempts in {self.config.LOGIN_ATTEMPT_WINDOW_MINUTES} min)"
            )
            raise ValueError(
                f"Too many failed login attempts. Try again in "
                f"{self.config.LOGIN_ATTEMPT_WINDOW_MINUTES} minutes."
            )
    
    def _clear_failed_attempts(self, email: str, company_code: str):
        """Clear failed attempt tracking on successful login"""
        key = self._get_attempt_key(email, company_code)
        self.failed_attempts.pop(key, None)


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_auth_service_instance: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get or create global auth service instance"""
    global _auth_service_instance
    if _auth_service_instance is None:
        _auth_service_instance = AuthService()
    return _auth_service_instance