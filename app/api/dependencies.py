"""
app/api/dependencies.py
========================
FastAPI dependencies for token extraction, validation, and session management.

FIXED: Dynamic per-tenant backend URL resolution so any leysco100 tenant works.
FIXED: Correctly extracts manager role from Laravel SUPERUSER field
FIXED: Proper role detection for both SUPERUSER flag and role field
FIXED: Stable session ID derived from user identity to prevent new session
       on every notification poll (was calling uuid.uuid4() as fallback)
FIXED: Token validation now correctly uses company_code from header AND from token
FIXED: Multi-tenant session isolation - different companies have separate sessions
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
# TENANT → BACKEND URL RESOLUTION
# =========================================================

def resolve_backend_url(company_code: Optional[str] = None, request: Optional[Request] = None) -> str:
    """
    Dynamically resolve the Laravel backend URL for a given tenant.

    Resolution order:
      1. Per-tenant env var  e.g. LARAVEL_BACKEND_URL_TEST001=https://dev100-be.leysco100.com
      2. X-Tenant-Env header     (explicit override for testing)
      3. Origin-header sniffing  (dev100.leysco100.com  → dev100-be.leysco100.com)
      4. Company code mapping
      5. LARAVEL_BACKEND_URL     (global default / single-tenant fallback)
      6. Hard error              (nothing configured)
    """
    
    # 1. Per-tenant env var (LARAVEL_BACKEND_URL_<COMPANY_CODE>)
    if company_code:
        env_key = f"LARAVEL_BACKEND_URL_{company_code.upper()}"
        per_tenant = os.getenv(env_key)
        if per_tenant:
            logger.debug(f"🔀 Backend URL from env {env_key}: {per_tenant}")
            return per_tenant.rstrip("/")
    
    # 2. Explicit X-Tenant-Env header (useful for Postman / integration tests)
    if request:
        tenant_env = request.headers.get("x-tenant-env") or request.headers.get("X-Tenant-Env")
        if tenant_env and re.fullmatch(r"[a-zA-Z0-9_-]{3,30}", tenant_env):
            derived = f"https://{tenant_env}-be.leysco100.com"
            logger.debug(f"🔀 Backend URL from X-Tenant-Env header: {derived}")
            return derived
    
    # 3. Derive from the Origin / Referer header
    if request:
        origin = request.headers.get("origin") or request.headers.get("referer", "")
        match = re.search(r"https?://(dev\d+)\.leysco100\.com", origin)
        if match:
            env_slug = match.group(1)
            derived = f"https://{env_slug}-be.leysco100.com"
            logger.debug(f"🔀 Backend URL derived from origin '{origin}': {derived}")
            return derived
    
    # 4. Company code to backend mapping (fallback)
    if company_code:
        backend_map = {
            "TEST001": os.getenv("LARAVEL_BACKEND_URL_TEST001", "https://dev100-be.leysco100.com"),
            "TEST002": os.getenv("LARAVEL_BACKEND_URL_TEST002", "https://dev109-be.leysco100.com"),
        }
        mapped = backend_map.get(company_code.upper())
        if mapped:
            logger.debug(f"🔀 Backend URL from company code mapping: {mapped}")
            return mapped

    # 5. Global fallback env var
    global_url = getattr(settings, "LARAVEL_BACKEND_URL", None) or os.getenv("LARAVEL_BACKEND_URL")
    if global_url:
        logger.debug(f"🔀 Backend URL from global setting: {global_url}")
        return global_url.rstrip("/")

    # 6. Nothing configured — fail loudly
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication service is not configured for this tenant.",
    )


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
                logger.warning(f"Invalid company code format received: {value}")
                return None
    return None


async def get_company_code(
    request: Request,
    token: str = Depends(get_token_from_header),
) -> str:
    """
    Resolve company code:
      1. X-Company-Code header (preferred)
      2. From cached session
      3. Token validation response from Laravel backend
    """
    # Priority 1: Header
    code = await get_company_code_header(request)
    if code:
        logger.info(f"✅ Company code from header: {code}")
        return code
    
    # Priority 2: From cached session
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    cached = _user_session_cache.get(token_hash)
    if cached and cached.get("user", {}).get("company_code"):
        cached_code = cached["user"]["company_code"]
        logger.info(f"✅ Company code from cached session: {cached_code}")
        return cached_code
    
    # Priority 3: Validate token with backend (without company code to detect)
    # Try to detect from origin first
    backend_url = resolve_backend_url(request=request)
    
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{backend_url}/api/user",
                headers={"Authorization": f"Bearer {token}"}
            )
        
        if response.status_code == 200:
            data = response.json()
            company_code_val = (
                data.get("company_code") or
                data.get("tenant_code") or
                data.get("CompanyID") or
                data.get("company_id")
            )
            if company_code_val:
                if str(company_code_val).isdigit():
                    company_code_val = f"C{company_code_val}"
                logger.info(f"✅ Company code from token validation: {company_code_val}")
                return company_code_val
    except Exception as e:
        logger.error(f"Error extracting company code from token: {e}")

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Company code not found. Provide X-Company-Code header.",
    )


# =========================================================
# SESSION CACHE MANAGER (Multi-tenant aware)
# =========================================================

class UserSessionManager:
    """In-memory user session cache keyed by (token_hash, company_code)."""

    @staticmethod
    def _get_cache_key(token: str, company_code: str = None) -> str:
        """Create cache key with optional company code for isolation."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        if company_code:
            return f"{token_hash}:{company_code}"
        return token_hash

    @staticmethod
    def get(token: str, company_code: str = None) -> Optional[Dict]:
        cache_key = UserSessionManager._get_cache_key(token, company_code)
        entry = _user_session_cache.get(cache_key)
        if entry:
            if datetime.now() < entry["expires_at"]:
                return entry["user"]
            del _user_session_cache[cache_key]
        return None

    @staticmethod
    def store(token: str, user_info: Dict, ttl_seconds: int = 3600) -> None:
        company_code = user_info.get("company_code")
        cache_key = UserSessionManager._get_cache_key(token, company_code)
        _user_session_cache[cache_key] = {
            "user":       user_info,
            "expires_at": datetime.now() + timedelta(seconds=ttl_seconds),
        }
        logger.debug(f"Session stored for company: {company_code}")

    @staticmethod
    def clear(token: str, company_code: str = None) -> None:
        cache_key = UserSessionManager._get_cache_key(token, company_code)
        _user_session_cache.pop(cache_key, None)

    # Backward-compatible aliases
    @staticmethod
    def get_user_from_token(token: str, company_code: str = None) -> Optional[Dict]:
        return UserSessionManager.get(token, company_code)

    @staticmethod
    def store_user_session(token: str, user_info: Dict, ttl_seconds: int = 3600) -> None:
        UserSessionManager.store(token, user_info, ttl_seconds)

    @staticmethod
    def clear_user_session(token: str, company_code: str = None) -> None:
        UserSessionManager.clear(token, company_code)


# =========================================================
# TOKEN VALIDATION WITH LARAVEL BACKEND (Multi-tenant)
# =========================================================

async def validate_token_with_backend(
    token: str,
    company_code: Optional[str] = None,
    request: Optional[Request] = None,
) -> Optional[Dict[str, Any]]:
    """
    Validate opaque Sanctum token against the correct Laravel backend
    for this tenant.

    CRITICAL FIX: Uses company_code AND request to resolve the correct backend.
    Tokens from TEST001 validate against dev100-be, TEST002 against dev109-be.
    """
    # Get company code from various sources
    resolved_company_code = company_code
    
    # If no company code provided, try to get from request header
    if not resolved_company_code and request:
        resolved_company_code = await get_company_code_header(request)
    
    # Cache hit with company code - use it
    cached = UserSessionManager.get(token, resolved_company_code)
    if cached:
        logger.info(f"✅ Using cached user session for company: {resolved_company_code}")
        return cached
    
    # CRITICAL FIX: Resolve backend URL using both company code and request
    backend_url = resolve_backend_url(company_code=resolved_company_code, request=request)
    validate_url = f"{backend_url}/api/user"

    logger.info(f"🔍 Validating token against: {validate_url} (company: {resolved_company_code})")

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                validate_url,
                headers={"Authorization": f"Bearer {token}"},
                follow_redirects=False,
            )

        if response.status_code == 302:
            location = response.headers.get("location", "unknown")
            logger.error(
                f"Token validation redirected (302) to '{location}'. "
                f"Likely wrong backend URL '{backend_url}' for this token. "
                f"Company code: {resolved_company_code}"
            )
            return None

        if response.status_code == 200:
            data = response.json()

            # Manager detection from Laravel response
            is_superuser     = data.get("SUPERUSER") == "1"
            role             = data.get("role", "sales_rep")
            is_manager_role  = role.lower() in ("manager", "admin", "supervisor", "director")
            is_manager_flag  = data.get("is_manager", False)
            is_manager       = is_superuser or is_manager_role or is_manager_flag
            user_role        = "manager" if is_manager else "sales_rep"

            # Company code extraction
            company_code_val = (
                resolved_company_code or
                data.get("company_code") or
                data.get("tenant_code") or
                data.get("CompanyID") or
                data.get("company_id")
            )
            
            # If company code is numeric, prefix with 'C'
            if company_code_val and str(company_code_val).isdigit():
                company_code_val = f"C{company_code_val}"

            user_info: Dict[str, Any] = {
                "user_id":            data.get("id"),
                "user_role":          user_role,
                "user_email":         data.get("email"),
                "user_name":          data.get("name"),
                "company_code":       company_code_val,
                "assigned_customers": data.get("assigned_customers", []),
                "is_manager":         is_manager,
                "backend_url":        backend_url,
                "raw_user_data": {
                    "name":      data.get("name"),
                    "SUPERUSER": data.get("SUPERUSER"),
                    "type":      data.get("type"),
                },
            }

            logger.info(
                f"✅ Token validated — User: {data.get('name')}, "
                f"Role: {user_role}, Company: {company_code_val}, "
                f"Backend: {backend_url}"
            )
            
            # Store with company code for proper isolation
            UserSessionManager.store(token, user_info)
            return user_info

        elif response.status_code == 401:
            logger.warning(f"Token invalid or expired (401) from {backend_url}")
            return None

        else:
            logger.error(f"Token validation failed: HTTP {response.status_code} from {backend_url}")
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
    # Get company code from request if available
    company_code = None
    if request:
        company_code = await get_company_code_header(request)

    info = await validate_token_with_backend(token, company_code=company_code, request=request)
    if info:
        return info

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unable to authenticate. Please log in again.",
    )


async def extract_user_id_from_token(token: str, request: Request = None) -> Optional[int]:
    info = await validate_token_with_backend(token, request=request)
    return info.get("user_id") if info else None


async def extract_user_role_from_token(token: str, request: Request = None) -> str:
    info = await validate_token_with_backend(token, request=request)
    return info.get("user_role", "sales_rep") if info else "sales_rep"


async def extract_user_email_from_token(token: str, request: Request = None) -> Optional[str]:
    info = await validate_token_with_backend(token, request=request)
    return info.get("user_email") if info else None


async def extract_assigned_customers_from_token(token: str, request: Request = None) -> List[str]:
    info = await validate_token_with_backend(token, request=request)
    if not info:
        return []
    customers = info.get("assigned_customers", [])
    if isinstance(customers, list):
        return [str(c) for c in customers if c]
    if isinstance(customers, str):
        return [c.strip() for c in customers.split(",") if c.strip()]
    return []


async def is_manager_from_token(token: str, request: Request = None) -> bool:
    info = await validate_token_with_backend(token, request=request)
    return info.get("is_manager", False) if info else False


# =========================================================
# SESSION ID RESOLUTION
# =========================================================

def _make_stable_session_id(user_id: Any, tenant_code: str) -> str:
    """
    Derive a deterministic session ID from user identity so polling
    endpoints always resolve to the same session.
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
    Resolve session ID with priority:
    1. Explicit session_id argument
    2. ?session_id= query param
    3. X-Session-ID request header
    4. session_id field in POST body
    5. Stable deterministic ID from user_id + tenant_code
    6. Random uuid4 (last resort)
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

    if user_id is not None and tenant_code:
        stable_id = _make_stable_session_id(user_id, tenant_code)
        logger.debug(f"🔑 Stable session ID for {user_id}/{tenant_code}: {stable_id[:8]}...")
        return stable_id

    return str(uuid.uuid4())


# =========================================================
# CONVERSATION CONTEXT (Main Dependency)
# =========================================================

async def get_conversation_context(
    request: Request,
    token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code),
) -> Dict[str, Any]:
    """
    Build full conversation context for the current request.
    Passes company_code + request to validate_token_with_backend so the
    correct tenant backend is always used.
    """
    user_info = await extract_user_info_from_token(token, request)

    user_id            = user_info.get("user_id")
    user_role          = user_info.get("user_role", "sales_rep")
    user_email         = user_info.get("user_email")
    assigned_customers = user_info.get("assigned_customers", [])
    is_manager         = user_info.get("is_manager", user_role == "manager")
    tenant_code        = company_code or user_info.get("company_code")

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


async def logout_user(token: str, company_code: str = None) -> None:
    """Clear user session on logout."""
    UserSessionManager.clear(token, company_code)


# =========================================================
# DEBUG HELPER
# =========================================================

async def debug_token_info(request: Request) -> Dict:
    """Debug helper to inspect token and user info."""
    try:
        token        = await get_token_from_header(request)
        company_code = await get_company_code_header(request)
        backend_url  = resolve_backend_url(company_code=company_code, request=request)
        user_info    = await extract_user_info_from_token(token, request)

        return {
            "authenticated":  True,
            "user_id":        user_info.get("user_id"),
            "user_role":      user_info.get("user_role"),
            "user_email":     user_info.get("user_email"),
            "company_code":   user_info.get("company_code"),
            "is_manager":     user_info.get("is_manager"),
            "raw_user_data":  user_info.get("raw_user_data"),
            "backend_url":    backend_url,
            "token_preview":  f"{token[:20]}...{token[-10:]}" if len(token) > 30 else token,
        }
    except HTTPException as e:
        return {"authenticated": False, "error": e.detail}
    except Exception as e:
        return {"authenticated": False, "error": str(e)}


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
    "resolve_backend_url",
    "UserSessionManager",
    "debug_token_info",
]