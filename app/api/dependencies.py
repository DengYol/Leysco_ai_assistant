"""
app/api/dependencies.py
========================
FastAPI dependencies for token extraction, validation, and session management.

All tenant-to-backend URL resolution is driven exclusively by environment
variables — there are NO hardcoded backend URLs in this file.

Per-tenant configuration in .env:
    LARAVEL_BACKEND_URL_TEST001=https://dev100-be.leysco100.com
    LARAVEL_BACKEND_URL_TEST002=https://dev109-be.leysco100.com
    LARAVEL_BACKEND_URL=https://fallback-be.leysco100.com   # global fallback
"""

from fastapi import Header, HTTPException, status, Request, Depends
from typing import Optional, Dict, List, Any
import re
import logging
import os
import hashlib
import uuid
from datetime import datetime, timedelta

from app.core.config import settings, get_laravel_backend_url
from app.services.conversation_memory import get_conversation_memory

logger = logging.getLogger(__name__)

# In-memory user session cache (replace with Redis in production)
_user_session_cache: Dict[str, Dict] = {}


# =========================================================
# TENANT → BACKEND URL RESOLUTION  (no hardcoded URLs)
# =========================================================

def resolve_backend_url(company_code: Optional[str] = None, request: Optional[Request] = None) -> str:
    """
    Dynamically resolve the Laravel backend URL for a given tenant.

    Resolution order:
      1. X-Backend-URL request header   (Flutter sends this — highest priority,
                                         enables fully automatic multi-tenant routing
                                         with zero .env mapping required)
      2. Per-tenant env var              LARAVEL_BACKEND_URL_<COMPANY_CODE>
      3. X-Tenant-Env request header    (Postman / integration tests)
      4. Origin/Referer header sniffing (dev100.leysco100.com → dev100-be.leysco100.com)
      5. LARAVEL_BACKEND_URL            (global fallback from settings / .env)
      6. Hard error — nothing configured
    """
    # 1. X-Backend-URL header — sent by Flutter with every request.
    #    Contains the exact Laravel backend URL that issued the token,
    #    e.g. "https://dev109-be.leysco100.com".
    #    This makes multi-tenant routing fully automatic: no .env entries needed.
    if request:
        backend_url_header = (
            request.headers.get("x-backend-url")
            or request.headers.get("X-Backend-URL")
        )
        if backend_url_header and backend_url_header.startswith("https://"):
            # Strip any trailing path suffixes the app may include in base_url.
            # Flutter saves base_url as "https://dev109-be.leysco100.com/api/v1"
            # but we need just "https://dev109-be.leysco100.com" so that
            # validate_token_with_backend can append /api/user without doubling.
            for suffix in ("/api/v1", "/api", "/v1"):
                if backend_url_header.rstrip("/").endswith(suffix):
                    backend_url_header = backend_url_header.rstrip("/")[:-len(suffix)]
                    break
            backend_url_header = backend_url_header.rstrip("/")
            logger.info(f"🔀 Backend URL from X-Backend-URL header: {backend_url_header}")
            return backend_url_header

    # 2. Per-tenant env var (useful for server-to-server or background jobs)
    if company_code:
        env_key = f"LARAVEL_BACKEND_URL_{company_code.upper()}"
        per_tenant = os.environ.get(env_key)
        if per_tenant:
            logger.debug(f"🔀 Backend URL from env {env_key}: {per_tenant}")
            return per_tenant.rstrip("/")

    # 2. Explicit X-Tenant-Env header (useful for Postman / integration tests)
    if request:
        tenant_env = (
            request.headers.get("x-tenant-env")
            or request.headers.get("X-Tenant-Env")
        )
        if tenant_env and re.fullmatch(r"[a-zA-Z0-9_-]{3,30}", tenant_env):
            # Derive backend URL from the slug: "dev100" → "dev100-be.leysco100.com"
            # The base domain is taken from LEYSCO_BASE_DOMAIN env (default: leysco100.com)
            base_domain = os.environ.get("LEYSCO_BASE_DOMAIN", "leysco100.com")
            derived = f"https://{tenant_env}-be.{base_domain}"
            logger.debug(f"🔀 Backend URL from X-Tenant-Env header: {derived}")
            return derived

    # 3. Derive from the Origin / Referer header
    if request:
        origin = request.headers.get("origin") or request.headers.get("referer", "")
        if origin:
            base_domain = os.environ.get("LEYSCO_BASE_DOMAIN", "leysco100.com")
            # Match pattern: https://dev<N>.leysco100.com  (or any slug)
            pattern = rf"https?://([a-zA-Z0-9_-]+)\.{re.escape(base_domain)}"
            match = re.search(pattern, origin)
            if match:
                env_slug = match.group(1)
                # Only derive if slug doesn't already end in -be (avoid double suffix)
                if not env_slug.endswith("-be"):
                    derived = f"https://{env_slug}-be.{base_domain}"
                    logger.debug(f"🔀 Backend URL derived from origin '{origin}': {derived}")
                    return derived

    # 4. Global fallback from settings / .env
    try:
        url = get_laravel_backend_url(company_code)
        logger.debug(f"🔀 Backend URL from global config: {url}")
        return url
    except RuntimeError:
        pass

    # 5. Nothing configured — fail loudly with a helpful message
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Authentication service is not configured for this tenant. "
            f"Set LARAVEL_BACKEND_URL_{(company_code or 'DEFAULT').upper()} in .env."
        ),
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

    # Priority 3: Validate token with backend to detect company code
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
                data.get("company_code")
                or data.get("tenant_code")
                or data.get("CompanyID")
                or data.get("company_id")
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

    Backend URL is resolved dynamically from env vars — no hardcoded URLs.
    """
    resolved_company_code = company_code

    if not resolved_company_code and request:
        resolved_company_code = await get_company_code_header(request)

    # Cache hit
    cached = UserSessionManager.get(token, resolved_company_code)
    if cached:
        logger.info(f"✅ Using cached user session for company: {resolved_company_code}")
        return cached

    # Resolve backend URL — env vars only, no hardcoded fallbacks
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
                f"Likely wrong backend URL '{backend_url}' for company '{resolved_company_code}'. "
                f"Check LARAVEL_BACKEND_URL_{(resolved_company_code or 'DEFAULT').upper()} in .env."
            )
            return None

        if response.status_code == 200:
            data = response.json()

            # Manager detection from Laravel response
            is_superuser    = data.get("SUPERUSER") == "1"
            role            = data.get("role", "sales_rep")
            is_manager_role = role.lower() in ("manager", "admin", "supervisor", "director")
            is_manager_flag = data.get("is_manager", False)
            is_manager      = is_superuser or is_manager_role or is_manager_flag
            user_role       = "manager" if is_manager else "sales_rep"

            # Company code extraction — prefer the one already known from header
            company_code_val = (
                resolved_company_code
                or data.get("company_code")
                or data.get("tenant_code")
                or data.get("CompanyID")
                or data.get("company_id")
            )
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