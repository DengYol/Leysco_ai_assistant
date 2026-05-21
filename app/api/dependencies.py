"""
app/api/dependencies.py
========================
FastAPI dependencies for token extraction, validation, and session management.

FIXED: Dynamic per-tenant backend URL resolution so any leysco100 tenant works.
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
# TENANT → BACKEND URL RESOLUTION   ← NEW
# =========================================================

def resolve_backend_url(company_code: Optional[str] = None, request: Optional[Request] = None) -> str:
    """
    Dynamically resolve the Laravel backend URL for a given tenant.

    Resolution order:
      1. Per-tenant env var  e.g. LARAVEL_BACKEND_URL_TEST001=https://dev100-be.leysco100.com
      2. Origin-header sniffing  (dev100.leysco100.com  → dev100-be.leysco100.com)
      3. X-Tenant-Env header     (explicit override for testing)
      4. LARAVEL_BACKEND_URL     (global default / single-tenant fallback)
      5. Hard error              (nothing configured)

    Examples
    --------
    Company TEST001 on dev100:
        env  LARAVEL_BACKEND_URL_TEST001=https://dev100-be.leysco100.com
        → https://dev100-be.leysco100.com

    Any request from https://dev109.leysco100.com (no per-tenant env var):
        origin sniff → https://dev109-be.leysco100.com
    """

    # 1. Per-tenant env var  (LARAVEL_BACKEND_URL_<COMPANY_CODE>)
    if company_code:
        env_key = f"LARAVEL_BACKEND_URL_{company_code.upper()}"
        per_tenant = os.getenv(env_key)
        if per_tenant:
            logger.debug(f"🔀 Backend URL from env {env_key}: {per_tenant}")
            return per_tenant.rstrip("/")

    # 2. Derive from the Origin / Referer header
    #    dev100.leysco100.com  → dev100-be.leysco100.com
    #    dev109.leysco100.com  → dev109-be.leysco100.com
    if request:
        origin = request.headers.get("origin") or request.headers.get("referer", "")
        match = re.search(r"https?://(dev\d+)\.leysco100\.com", origin)
        if match:
            env_slug = match.group(1)           # e.g. "dev100"
            derived = f"https://{env_slug}-be.leysco100.com"
            logger.debug(f"🔀 Backend URL derived from origin '{origin}': {derived}")
            return derived

    # 3. Explicit X-Tenant-Env header  (useful for Postman / integration tests)
    if request:
        tenant_env = request.headers.get("x-tenant-env")  # e.g. "dev100"
        if tenant_env and re.fullmatch(r"[a-zA-Z0-9_-]{3,30}", tenant_env):
            derived = f"https://{tenant_env}-be.leysco100.com"
            logger.debug(f"🔀 Backend URL from X-Tenant-Env header: {derived}")
            return derived

    # 4. Global fallback env var
    global_url = getattr(settings, "LARAVEL_BACKEND_URL", None) or os.getenv("LARAVEL_BACKEND_URL")
    if global_url:
        logger.debug(f"🔀 Backend URL from global setting: {global_url}")
        return global_url.rstrip("/")

    # 5. Nothing configured — fail loudly
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

    validation = await validate_token_with_backend(token, request=request)
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

async def validate_token_with_backend(
    token: str,
    company_code: Optional[str] = None,
    request: Optional[Request] = None,
) -> Optional[Dict[str, Any]]:
    """
    Validate opaque Sanctum token against the correct Laravel backend
    for this tenant.

    Backend URL is resolved dynamically via resolve_backend_url() so
    tokens from dev100.leysco100.com validate against dev100-be, tokens
    from dev109.leysco100.com validate against dev109-be, etc.

    Returns canonical user_info dict with keys:
        user_id, user_role, user_email, company_code,
        assigned_customers, is_manager, backend_url (for debugging)
    """
    # Cache hit — skip network call
    cached = UserSessionManager.get(token)
    if cached:
        logger.info("✅ Using cached user session")
        return cached

    # ← CHANGED: resolve dynamically instead of reading a single setting
    backend_url = resolve_backend_url(company_code=company_code, request=request)
    validate_url = f"{backend_url}/api/user"

    logger.info(f"🔍 Validating token against: {validate_url}")

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                validate_url,
                headers={"Authorization": f"Bearer {token}"},
                follow_redirects=False,   # surface mis-routed requests immediately
            )

        if response.status_code == 302:
            location = response.headers.get("location", "unknown")
            logger.error(
                f"Token validation redirected (302) to '{location}'. "
                f"Likely wrong backend URL '{backend_url}' for this token. "
                f"Check resolve_backend_url() or per-tenant env vars."
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
                data.get("company_code") or
                data.get("tenant_code") or
                data.get("CompanyID") or
                data.get("company_id")
            )
            if company_code_val and str(company_code_val).isdigit():
                company_code_val = f"C{company_code_val}"

            user_info: Dict[str, Any] = {
                "user_id":            data.get("id"),
                "user_role":          user_role,
                "user_email":         data.get("email"),
                "company_code":       company_code_val,
                "assigned_customers": data.get("assigned_customers", []),
                "is_manager":         is_manager,
                "backend_url":        backend_url,   # useful for debugging
                "raw_user_data": {
                    "name":      data.get("name"),
                    "SUPERUSER": data.get("SUPERUSER"),
                    "type":      data.get("type"),
                },
            }

            logger.info(
                f"✅ Token validated — User: {data.get('name')}, "
                f"Role: {user_role}, SUPERUSER: {data.get('SUPERUSER')}, "
                f"Backend: {backend_url}"
            )
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
# CONVERSATION CONTEXT  ← MAIN DEPENDENCY
# =========================================================

async def get_conversation_context(
    request: Request,
    token:        str = Depends(get_token_from_header),
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
    tenant_code        = company_code

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