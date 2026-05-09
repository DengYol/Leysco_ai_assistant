"""
app/api/dependencies.py
========================
FastAPI dependencies for token extraction, validation, and session management.

FIXED: Correctly extracts manager role from Laravel SUPERUSER field
FIXED: Proper role detection for both SUPERUSER flag and role field
FIXED: Stable session ID derived from user identity to prevent new session
       on every notification poll (was calling uuid.uuid4() as fallback)
"""

from fastapi import Header, HTTPException, status, Request, Depends
from typing import Optional, Dict, List, Any
import re
import logging
import os
import hashlib
import uuid
from datetime import datetime, timedelta

from app.core.config import settings
from app.services.conversation_memory import get_conversation_memory

logger = logging.getLogger(__name__)

# In-memory user session cache (replace with Redis in production)
_user_session_cache: Dict[str, Dict] = {}


# =========================================================
# TOKEN EXTRACTION
# =========================================================

async def get_token_from_header(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> str:
    """Extract Bearer token from Authorization header."""
    token = authorization

    if not token:
        for key, value in request.headers.items():
            if key.lower() == "authorization":
                token = value
                break

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = token.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Use 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_value = parts[1].strip()
    if not token_value or len(token_value) < 10:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or empty token.",
        )

    return token_value


async def get_optional_token(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Optional[str]:
    """Extract Bearer token if present (optional)."""
    try:
        return await get_token_from_header(request, authorization)
    except HTTPException:
        return None


# =========================================================
# COMPANY CODE
# =========================================================

async def get_company_code_header(request: Request) -> Optional[str]:
    """Extract and validate X-Company-Code header."""
    for key, value in request.headers.items():
        if key.lower() == "x-company-code":
            if re.match(r'^[A-Za-z0-9_-]{3,50}$', value):
                return value.upper()
            else:
                logger.warning(f"Invalid company code format received")
                return None
    return None


async def get_company_code(
    request: Request,
    token: str = Depends(get_token_from_header),
) -> str:
    """
    Resolve company code:
      1. X-Company-Code header  (preferred for opaque tokens)
      2. Token validation response from Laravel backend
    """
    code = await get_company_code_header(request)
    if code:
        logger.info(f"✅ Company code from header: {code}")
        return code

    validation = await validate_token_with_backend(token)
    if validation and validation.get("company_code"):
        return validation["company_code"]

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Company code not found. Provide X-Company-Code header.",
    )


# =========================================================
# SESSION CACHE MANAGER
# =========================================================

class UserSessionManager:
    """In-memory user session cache keyed by token hash."""

    @staticmethod
    def get(token: str) -> Optional[Dict]:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        entry = _user_session_cache.get(token_hash)
        if entry:
            if datetime.now() < entry["expires_at"]:
                return entry["user"]
            del _user_session_cache[token_hash]
        return None

    @staticmethod
    def store(token: str, user_info: Dict, ttl_seconds: int = 3600) -> None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        _user_session_cache[token_hash] = {
            "user":       user_info,
            "expires_at": datetime.now() + timedelta(seconds=ttl_seconds),
        }

    @staticmethod
    def clear(token: str) -> None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        _user_session_cache.pop(token_hash, None)

    # Backward-compatible aliases
    @staticmethod
    def get_user_from_token(token: str) -> Optional[Dict]:
        return UserSessionManager.get(token)

    @staticmethod
    def store_user_session(token: str, user_info: Dict, ttl_seconds: int = 3600) -> None:
        UserSessionManager.store(token, user_info, ttl_seconds)

    @staticmethod
    def clear_user_session(token: str) -> None:
        UserSessionManager.clear(token)


# =========================================================
# TOKEN VALIDATION WITH LARAVEL BACKEND
# =========================================================

async def validate_token_with_backend(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate opaque Sanctum token against the Laravel backend.

    Returns canonical user_info dict with keys:
        user_id, user_role, user_email, company_code,
        assigned_customers, is_manager

    Results are cached for ttl_seconds so subsequent calls are free.
    
    FIXED: Properly detects manager role from Laravel response:
        - SUPERUSER == "1" → manager
        - role in ["manager", "admin", "supervisor", "director"] → manager
        - is_manager == True → manager
    """
    # Cache hit — skip network call
    cached = UserSessionManager.get(token)
    if cached:
        logger.info("✅ Using cached user session")
        return cached

    backend_url = getattr(settings, "LARAVEL_BACKEND_URL", None)

    if not backend_url:
        logger.error("LARAVEL_BACKEND_URL is not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not configured.",
        )

    validate_url = f"{backend_url.rstrip('/')}/api/user"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                validate_url,
                headers={"Authorization": f"Bearer {token}"},
            )

        if response.status_code == 200:
            data = response.json()
            
            # FIXED: Proper manager detection from Laravel response
            # Check for SUPERUSER field (string "1" or "0")
            is_superuser = data.get("SUPERUSER") == "1"
            
            # Check role field
            role = data.get("role", "sales_rep")
            is_manager_role = role.lower() in ("manager", "admin", "supervisor", "director")
            
            # Check is_manager flag
            is_manager_flag = data.get("is_manager", False)
            
            # Combined manager flag
            is_manager = is_superuser or is_manager_role or is_manager_flag
            
            # Determine user role string
            user_role = "manager" if is_manager else "sales_rep"
            
            # Extract company code from various possible fields
            company_code = (
                data.get("company_code") or 
                data.get("tenant_code") or 
                data.get("CompanyID") or 
                data.get("company_id")
            )
            
            # If company code is numeric (like CompanyID), add "C" prefix
            if company_code and str(company_code).isdigit():
                company_code = f"C{company_code}"
            
            user_info: Dict[str, Any] = {
                "user_id":            data.get("id"),
                "user_role":          user_role,
                "user_email":         data.get("email"),
                "company_code":       company_code,
                "assigned_customers": data.get("assigned_customers", []),
                "is_manager":         is_manager,
                "raw_user_data": {    # Keep for debugging
                    "name": data.get("name"),
                    "SUPERUSER": data.get("SUPERUSER"),
                    "type": data.get("type"),
                }
            }
            
            logger.info(f"✅ Token validated - User: {data.get('name')}, Role: {user_role}, SUPERUSER: {data.get('SUPERUSER')}")
            UserSessionManager.store(token, user_info)
            return user_info

        elif response.status_code == 401:
            logger.warning("Token invalid or expired")
            return None

        else:
            logger.error(f"Token validation failed: HTTP {response.status_code}")
            return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        return None


# =========================================================
# USER INFO HELPERS
# =========================================================

async def extract_user_info_from_token(
    token: str,
    request: Request = None,
) -> Dict[str, Any]:
    """Return full user_info dict for a token."""
    info = await validate_token_with_backend(token)
    if info:
        return info

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unable to authenticate. Please log in again.",
    )


async def extract_user_id_from_token(token: str) -> Optional[int]:
    info = await validate_token_with_backend(token)
    return info.get("user_id") if info else None


async def extract_user_role_from_token(token: str) -> str:
    info = await validate_token_with_backend(token)
    return info.get("user_role", "sales_rep") if info else "sales_rep"


async def extract_user_email_from_token(token: str) -> Optional[str]:
    info = await validate_token_with_backend(token)
    return info.get("user_email") if info else None


async def extract_assigned_customers_from_token(token: str) -> List[str]:
    info = await validate_token_with_backend(token)
    if not info:
        return []
    customers = info.get("assigned_customers", [])
    if isinstance(customers, list):
        return [str(c) for c in customers if c]
    if isinstance(customers, str):
        return [c.strip() for c in customers.split(",") if c.strip()]
    return []


async def is_manager_from_token(token: str) -> bool:
    info = await validate_token_with_backend(token)
    return info.get("is_manager", False) if info else False


# =========================================================
# SESSION ID RESOLUTION
# =========================================================

def _make_stable_session_id(user_id: Any, tenant_code: str) -> str:
    """
    Derive a deterministic session ID from user identity.

    This ensures that stateless polling endpoints (notifications, unread-count)
    always resolve to the SAME session rather than spawning a fresh uuid4 on
    every request — which was the root cause of notifications never persisting.

    The result is a 36-character hex string (no dashes) so it looks like a
    normal session ID in logs.
    """
    stable_key = f"{tenant_code}:{user_id}"
    return hashlib.sha256(stable_key.encode()).hexdigest()[:36]


async def get_session_id_from_request(
    request: Request,
    session_id: Optional[str] = None,
    user_id: Optional[Any] = None,
    tenant_code: Optional[str] = None,
) -> str:
    """
    Resolve session ID with the following priority:

    1. Explicit session_id argument
    2. ?session_id= query param
    3. X-Session-ID request header
    4. session_id field in POST body
    5. Stable deterministic ID derived from user_id + tenant_code  ← FIXED
    6. Random uuid4 (last resort — only when no user identity available)

    Previously the fallback was always uuid4(), which meant every notification
    poll created a brand-new session and notifications never accumulated.
    """
    if session_id:
        return session_id
    if request.query_params.get("session_id"):
        return request.query_params["session_id"]
    if request.headers.get("X-Session-ID"):
        return request.headers["X-Session-ID"]
    if request.method == "POST":
        try:
            body = await request.json()
            if body.get("session_id"):
                return body["session_id"]
        except Exception:
            pass

    # FIXED: derive a stable, repeatable session ID from user identity so that
    # polling endpoints (GET /notifications, GET /notifications/unread-count)
    # always land on the same session instead of creating a new one each time.
    if user_id is not None and tenant_code:
        stable_id = _make_stable_session_id(user_id, tenant_code)
        logger.debug(f"🔑 Using stable session ID for user {user_id} / {tenant_code}: {stable_id[:8]}...")
        return stable_id

    # True last resort — anonymous or unauthenticated requests
    return str(uuid.uuid4())


# =========================================================
# CONVERSATION CONTEXT  ← MAIN DEPENDENCY
# =========================================================

async def get_conversation_context(
    request: Request,
    token:        str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code),
) -> Dict[str, Any]:
    """
    Build full conversation context for the current request.
    validate_token_with_backend is called ONCE; all fields come from
    that single cached dict.

    FIXED: user_id and tenant_code are resolved BEFORE get_session_id_from_request
    so the stable-session-ID fallback has the information it needs. Previously
    the call order meant user_id was never passed in, so uuid4() was always used.
    """
    user_info = await extract_user_info_from_token(token, request)

    user_id            = user_info.get("user_id")
    user_role          = user_info.get("user_role", "sales_rep")
    user_email         = user_info.get("user_email")
    assigned_customers = user_info.get("assigned_customers", [])
    is_manager         = user_info.get("is_manager", user_role == "manager")
    tenant_code        = company_code

    # Pass user identity so polling endpoints get a stable session ID
    effective_session_id = await get_session_id_from_request(
        request,
        user_id=user_id,
        tenant_code=tenant_code,
    )

    logger.info(
        f"📝 Session: {effective_session_id[:8]}... | "
        f"User: {user_id} | Role: {user_role} | Company: {tenant_code} | "
        f"is_manager: {is_manager}"
    )

    memory  = get_conversation_memory()
    session = memory.get_or_create_session(
        session_id=effective_session_id,
        user_id=str(user_id) if user_id else None,
        tenant_code=tenant_code,
    )
    context = memory.get_context(effective_session_id)
    history = memory.get_conversation_history(effective_session_id, limit=10)

    return {
        "session_id":         effective_session_id,
        "user_id":            user_id,
        "user_role":          user_role,
        "user_email":         user_email,
        "tenant_code":        tenant_code,
        "assigned_customers": assigned_customers,
        "is_manager":         is_manager,
        "context":            context,
        "history":            history,
        "message_count":      session.get("message_count", 0),
        "_token":             token,
    }


async def require_manager_role(
    context: Dict = Depends(get_conversation_context),
) -> Dict:
    """Ensure the current user has manager role."""
    if not context.get("is_manager"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature is only available for managers.",
        )
    return context


# =========================================================
# LIFECYCLE HELPERS
# =========================================================

async def sync_user_session(token: str, user_data: Dict) -> None:
    """Sync user session from Laravel after login."""
    UserSessionManager.store(token, user_data)
    logger.info(f"User session synced: {user_data.get('user_email')}")


async def logout_user(token: str) -> None:
    """Clear user session on logout."""
    UserSessionManager.clear(token)


# =========================================================
# DEBUG HELPER
# =========================================================

async def debug_token_info(request: Request) -> Dict:
    """Debug helper to inspect token and user info."""
    try:
        token = await get_token_from_header(request)
        user_info = await extract_user_info_from_token(token, request)
        
        return {
            "authenticated": True,
            "user_id": user_info.get("user_id"),
            "user_role": user_info.get("user_role"),
            "user_email": user_info.get("user_email"),
            "company_code": user_info.get("company_code"),
            "is_manager": user_info.get("is_manager"),
            "raw_user_data": user_info.get("raw_user_data"),
            "token_preview": f"{token[:20]}...{token[-10:]}" if len(token) > 30 else token,
        }
    except HTTPException as e:
        return {
            "authenticated": False,
            "error": e.detail,
        }
    except Exception as e:
        return {
            "authenticated": False,
            "error": str(e),
        }


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "get_token_from_header",
    "get_optional_token",
    "get_company_code",
    "get_company_code_header",
    "extract_user_id_from_token",
    "extract_user_role_from_token",
    "extract_user_email_from_token",
    "extract_assigned_customers_from_token",
    "extract_user_info_from_token",
    "is_manager_from_token",
    "get_conversation_context",
    "require_manager_role",
    "validate_token_with_backend",
    "sync_user_session",
    "logout_user",
    "UserSessionManager",
    "debug_token_info",
]