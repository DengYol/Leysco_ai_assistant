"""
app/api/auth_routes.py
======================

Authentication API endpoints.

Endpoints:
  POST   /api/auth/login      - Login with email/password, get tokens
  POST   /api/auth/logout     - Logout and blacklist token
  POST   /api/auth/refresh    - Refresh access token
  POST   /api/auth/verify     - Verify token validity
"""

from fastapi import APIRouter, Request, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any
import logging

from app.core.auth_service import get_auth_service
from app.api.dependencies import (
    get_token_from_header,
    resolve_backend_url,
    get_company_code_header,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================

class LoginRequest(BaseModel):
    """Login request"""
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=8, description="User password")
    company_code: Optional[str] = Field(None, description="Company code (optional, from header if not provided)")


class LoginResponse(BaseModel):
    """Login response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: Dict[str, Any]


class RefreshRequest(BaseModel):
    """Token refresh request"""
    refresh_token: str = Field(..., description="Refresh token")


class RefreshResponse(BaseModel):
    """Token refresh response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class VerifyResponse(BaseModel):
    """Token verification response"""
    valid: bool
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    user_role: Optional[str] = None
    company_code: Optional[str] = None
    expires_in: Optional[int] = None  # seconds until expiration


class LogoutResponse(BaseModel):
    """Logout response"""
    message: str


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/login", response_model=LoginResponse, status_code=200)
async def login(
    request: Request,
    credentials: LoginRequest,
) -> LoginResponse:
    """
    Authenticate user and return tokens.
    
    **Flow:**
    1. Get company code from body or X-Company-Code header
    2. Resolve backend URL for that company
    3. Authenticate against Laravel backend
    4. Generate JWT tokens (access + refresh)
    5. Return tokens + user info
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8000/api/auth/login \\
      -H "Content-Type: application/json" \\
      -d {
        "email": "user@example.com",
        "password": "SecurePassword123",
        "company_code": "TEST001"
      }
    ```
    
    **Response:**
    ```json
    {
      "access_token": "eyJhbGciOiJIUzI1NiI...",
      "refresh_token": "eyJhbGciOiJIUzI1NiI...",
      "token_type": "bearer",
      "expires_in": 86400,
      "user": {
        "user_id": 123,
        "user_email": "user@example.com",
        "user_name": "John Doe",
        "user_role": "sales_rep",
        "company_code": "TEST001"
      }
    }
    ```
    """
    
    try:
        # Get company code
        company_code = (
            credentials.company_code or
            await get_company_code_header(request)
        )
        
        if not company_code:
            logger.warning(f"Login attempt without company code: {credentials.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="company_code is required (provide as parameter or X-Company-Code header)"
            )
        
        logger.info(f"🔐 Login request: {credentials.email} for {company_code}")
        
        # Resolve backend URL for this company
        try:
            backend_url = resolve_backend_url(company_code=company_code, request=request)
        except HTTPException as e:
            logger.error(f"Cannot resolve backend for {company_code}: {e.detail}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service not configured for this company"
            )
        
        # Authenticate
        auth_service = get_auth_service()
        result = await auth_service.login(
            email=credentials.email,
            password=credentials.password,
            company_code=company_code,
            backend_url=backend_url,
        )
        
        logger.info(f"✅ Login successful: {credentials.email} ({company_code})")
        
        return LoginResponse(**result)
    
    except ValueError as e:
        logger.warning(f"❌ Login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"❌ Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed. Please try again."
        )


@router.post("/refresh", response_model=RefreshResponse, status_code=200)
async def refresh_token(
    request: Request,
    body: RefreshRequest,
) -> RefreshResponse:
    """
    Get a new access token using a refresh token.
    
    **Flow:**
    1. Validate refresh token signature and expiration
    2. Generate new access token
    3. Blacklist old refresh token (rotation)
    4. Return new access token
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8000/api/auth/refresh \\
      -H "Content-Type: application/json" \\
      -d {
        "refresh_token": "eyJhbGciOiJIUzI1NiI..."
      }
    ```
    
    **Response:**
    ```json
    {
      "access_token": "eyJhbGciOiJIUzI1NiI...",
      "token_type": "bearer",
      "expires_in": 86400
    }
    ```
    """
    
    try:
        auth_service = get_auth_service()
        
        # Validate refresh token
        new_token = await auth_service.refresh_access_token(body.refresh_token)
        
        logger.info("✅ Token refreshed successfully")
        
        return RefreshResponse(
            access_token=new_token,
            token_type="bearer",
            expires_in=auth_service.config.JWT_ACCESS_TOKEN_EXPIRE_HOURS * 3600
        )
    
    except ValueError as e:
        logger.warning(f"❌ Token refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    except Exception as e:
        logger.error(f"❌ Refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )


@router.post("/verify", response_model=VerifyResponse, status_code=200)
async def verify_token(
    request: Request,
    token: str = Depends(get_token_from_header),
) -> VerifyResponse:
    """
    Verify that an access token is valid.
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8000/api/auth/verify \\
      -H "Authorization: Bearer <access_token>"
    ```
    
    **Response (valid):**
    ```json
    {
      "valid": true,
      "user_id": 123,
      "user_email": "user@example.com",
      "user_role": "sales_rep",
      "company_code": "TEST001",
      "expires_in": 3600
    }
    ```
    
    **Response (invalid):**
    ```json
    {
      "valid": false,
      "reason": "Token expired"
    }
    ```
    """
    
    try:
        auth_service = get_auth_service()
        
        claims = auth_service.validate_access_token(token)
        
        if not claims:
            return VerifyResponse(valid=False)
        
        return VerifyResponse(
            valid=True,
            user_id=claims.user_id,
            user_email=claims.user_email,
            user_role=claims.user_role,
            company_code=claims.company_code,
            expires_in=claims.get_ttl_seconds()
        )
    
    except Exception as e:
        logger.error(f"Verification error: {e}")
        return VerifyResponse(valid=False)


@router.post("/logout", response_model=LogoutResponse, status_code=200)
async def logout(
    request: Request,
    token: str = Depends(get_token_from_header),
) -> LogoutResponse:
    """
    Logout user by blacklisting token.
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8000/api/auth/logout \\
      -H "Authorization: Bearer <access_token>"
    ```
    
    **Response:**
    ```json
    {
      "message": "Successfully logged out"
    }
    ```
    """
    
    try:
        auth_service = get_auth_service()
        
        # Validate token first
        claims = auth_service.validate_access_token(token)
        if not claims:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        # Blacklist token
        auth_service.logout(token)
        
        logger.info(f"✅ User {claims.user_id} logged out")
        
        return LogoutResponse(message="Successfully logged out")
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )