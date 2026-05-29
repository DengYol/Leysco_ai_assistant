# app/api/auth_routes.py
"""
Authentication routes - handles login and returns tokens
Solves multi-tenant token passing at the backend level
"""

import logging
from fastapi import APIRouter, Request, HTTPException, status
from typing import Dict, Any
import httpx

from app.api.dependencies import (
    resolve_backend_url,
    UserSessionManager,
    get_company_code_header,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


# =========================================================
# LOGIN ENDPOINT
# =========================================================

@router.post("/login")
async def login(
    request: Request,
    credentials: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Frontend login endpoint.
    
    Frontend sends email + password to THIS endpoint.
    Backend automatically:
    1. Determines which tenant backend to use
    2. Logs in to Laravel backend
    3. Gets token
    4. Caches token
    5. Returns token to frontend
    
    Frontend then uses this token for all AI API requests.
    
    Request body:
    {
        "email": "user@example.com",
        "password": "password123"
    }
    
    Response:
    {
        "token": "2555|Cl7tQFy6JkPej...",
        "user": {
            "id": 1,
            "name": "John Doe",
            "email": "user@example.com",
            "company_code": "TEST001",
            "is_manager": true
        },
        "backend_url": "https://dev100-be.leysco100.com"
    }
    """
    
    try:
        # Extract credentials
        email = credentials.get("email")
        password = credentials.get("password")
        
        if not email or not password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing email or password"
            )
        
        # Determine which tenant backend to use
        # Priority: 1) Header, 2) Origin sniffing, 3) Global fallback
        company_code = await get_company_code_header(request)
        backend_url = resolve_backend_url(company_code=company_code, request=request)
        
        logger.info(f"🔐 Login attempt for {email} on backend: {backend_url}")
        
        # Login to Laravel backend
        login_url = f"{backend_url}/api/v1/login"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                login_url,
                json={"email": email, "password": password},
                headers={"Content-Type": "application/json"}
            )
        
        if response.status_code != 200:
            logger.warning(f"❌ Login failed for {email}: HTTP {response.status_code}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        login_data = response.json()
        token = login_data.get("token")
        
        if not token:
            logger.error(f"❌ No token in login response from {backend_url}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Backend did not return token"
            )
        
        # Validate token against backend to get user info
        logger.info(f"✅ Token received, validating: {token[:20]}...")
        
        validate_url = f"{backend_url}/api/user"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            validate_response = await client.get(
                validate_url,
                headers={"Authorization": f"Bearer {token}"}
            )
        
        if validate_response.status_code != 200:
            logger.error(f"❌ Token validation failed: HTTP {validate_response.status_code}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token validation failed"
            )
        
        user_data = validate_response.json()
        
        # Build user info dict
        user_info = {
            "user_id": user_data.get("id"),
            "user_role": "manager" if user_data.get("SUPERUSER") == "1" else "sales_rep",
            "user_email": user_data.get("email"),
            "company_code": user_data.get("company_code") or company_code,
            "assigned_customers": user_data.get("assigned_customers", []),
            "is_manager": user_data.get("SUPERUSER") == "1",
            "backend_url": backend_url,  # ← Store backend URL for future requests
        }
        
        # Cache session so future requests don't validate again
        UserSessionManager.store(token, user_info, ttl_seconds=3600)
        logger.info(f"✅ User {user_data.get('email')} logged in successfully")
        
        # Return token + user info to frontend
        return {
            "token": token,
            "user": {
                "id": user_info["user_id"],
                "name": user_data.get("name"),
                "email": user_info["user_email"],
                "role": user_info["user_role"],
                "company_code": user_info["company_code"],
                "is_manager": user_info["is_manager"],
            },
            "backend_url": backend_url,  # For debugging
            "success": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


# =========================================================
# LOGOUT ENDPOINT
# =========================================================

@router.post("/logout")
async def logout(request: Request) -> Dict[str, Any]:
    """
    Logout endpoint - clears cached session.
    
    Frontend sends token, backend clears it from cache.
    """
    try:
        from app.api.dependencies import get_token_from_header
        
        token = await get_token_from_header(request)
        UserSessionManager.clear(token)
        
        logger.info(f"✅ User logged out")
        
        return {"success": True, "message": "Logged out successfully"}
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )


# =========================================================
# VERIFY TOKEN ENDPOINT
# =========================================================

@router.post("/verify")
async def verify_token(request: Request) -> Dict[str, Any]:
    """
    Verify that a token is still valid.
    
    Frontend can use this to check if token expired without
    making a full API call.
    """
    try:
        from app.api.dependencies import get_token_from_header, extract_user_info_from_token
        
        token = await get_token_from_header(request)
        user_info = await extract_user_info_from_token(token, request)
        
        return {
            "valid": True,
            "user_id": user_info.get("user_id"),
            "user_email": user_info.get("user_email"),
            "role": user_info.get("user_role"),
            "is_manager": user_info.get("is_manager"),
        }
        
    except HTTPException as e:
        if e.status_code == 401:
            return {"valid": False, "message": "Token expired or invalid"}
        raise
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verification failed"
        )