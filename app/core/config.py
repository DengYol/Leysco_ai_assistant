"""
app/core/config.py
==================
Centralised settings with per-tenant backend URL resolution.

Per-tenant overrides are read directly from os.environ so they don't need
to be declared as typed fields (there can be unlimited tenants).

    LARAVEL_BACKEND_URL_TEST001=https://dev100-be.leysco100.com
    LEYSCO_API_BASE_URL_TEST001=https://dev100-be.leysco100.com/api/v1
"""

import os
import re
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME:  str  = "Leysco AI Sales Assistant"
    APP_ENV:   str  = "development"   # development | staging | production
    DEBUG:     bool = False

    # ── Authentication ────────────────────────────────────────────────────────
    # Global fallback — used when no per-tenant override matches.
    # Per-tenant: LARAVEL_BACKEND_URL_<COMPANY_CODE>=https://...
    LARAVEL_BACKEND_URL: str = ""

    # ── Leysco ERP API ────────────────────────────────────────────────────────
    # Global fallback — per-tenant: LEYSCO_API_BASE_URL_<COMPANY_CODE>=https://...
    LEYSCO_API_BASE_URL: str = ""

    # Service-account credentials for background jobs only.
    # Regular user requests use their own Bearer token.
    LEYSCO_SERVICE_ACCOUNT_EMAIL:    str = ""
    LEYSCO_SERVICE_ACCOUNT_PASSWORD: str = ""

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins.
    # e.g. https://dev100.leysco100.com,https://dev109.leysco100.com
    CORS_ALLOWED_ORIGINS: str = ""

    # ── LLM Providers ─────────────────────────────────────────────────────────
    LLM_PROVIDER: str = "groq"   # groq | gemini | ollama

    GROQ_API_KEY: str = ""
    GROQ_MODEL:   str = "llama-3.1-8b-instant"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL:   str = "gemini-1.5-flash"

    OLLAMA_URL:     str = "http://localhost:11434/api/generate"
    OLLAMA_MODEL:   str = "llama-3.1-8b-instant"
    OLLAMA_TIMEOUT: int = 120

    # ── Cache ─────────────────────────────────────────────────────────────────
    CACHE_BACKEND:     str = "memory"   # memory | redis
    CACHE_TTL_SECONDS: int = 300
    CACHE_MAX_ENTRIES: int = 1000

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_HOST:     str  = "localhost"
    REDIS_PORT:     int  = 6379
    REDIS_PASSWORD: str  = ""
    REDIS_DB:       int  = 0
    REDIS_SSL:      bool = False

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY:                  str = ""
    JWT_SECRET_KEY:              str = ""
    JWT_ALGORITHM:               str = "HS256"
    JWT_EXPIRE_HOURS:            int = 8
    TENANT_CONFIG_ENCRYPTION_KEY: str = ""

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_ENABLED:    bool = True
    RATE_LIMIT_PER_MINUTE: int  = 60
    RATE_LIMIT_BURST:      int  = 20

    # ── Notifications ─────────────────────────────────────────────────────────
    USE_MOCK_NOTIFICATIONS:             bool = False
    NOTIFICATION_SCAN_INTERVAL_SECONDS: int  = 900

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL:  str = "INFO"
    LOG_FORMAT: str = "text"   # text | json
    LOG_FILE:   str = ""

    # ── Competitor Pricing ────────────────────────────────────────────────────
    TWIGA_API_KEY:      str = ""
    SOKOPEPPER_API_KEY: str = ""
    FARMCROWDY_API_KEY: str = ""

    TWIGA_API_URL:      str = "https://api.twiga.com/v1/prices"
    SOKOPEPPER_API_URL: str = "https://api.sokopepper.co.ke/v2/prices"
    FARMCROWDY_API_URL: str = "https://api.farmcrowdy.com/prices"

    WORLD_BANK_ENABLED: bool = True
    WORLD_BANK_API_URL: str  = "https://api.worldbank.org/v2"

    ENABLED_COMPETITORS:           str = "market,worldbank"
    COMPETITOR_CACHE_TTL_HOURS:    int = 6
    COMPETITOR_API_TIMEOUT_SECONDS: int = 10

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS_ALLOWED_ORIGINS as a clean list."""
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]


# ── Singleton ─────────────────────────────────────────────────────────────────
settings = Settings()


# ── Per-tenant URL helpers ────────────────────────────────────────────────────

def get_laravel_backend_url(company_code: str | None = None) -> str:
    """
    Return the Laravel backend URL for a given company code.

    Resolution order:
      1. LARAVEL_BACKEND_URL_<COMPANY_CODE>  env var  (per-tenant)
      2. Origin/Referer sniffing             (handled in dependencies.py)
      3. LARAVEL_BACKEND_URL                 settings fallback
      4. RuntimeError                        — nothing configured

    This function covers steps 1 and 3 only. The full chain including
    request-header sniffing lives in dependencies.resolve_backend_url().
    """
    if company_code:
        key = f"LARAVEL_BACKEND_URL_{company_code.upper()}"
        val = os.environ.get(key)
        if val:
            logger.debug(f"🔀 Laravel backend for {company_code}: {val} (from {key})")
            return val.rstrip("/")

    if settings.LARAVEL_BACKEND_URL:
        return settings.LARAVEL_BACKEND_URL.rstrip("/")

    raise RuntimeError(
        "Laravel backend URL is not configured. "
        f"Set LARAVEL_BACKEND_URL or LARAVEL_BACKEND_URL_<COMPANY_CODE> in .env."
    )


def get_leysco_api_base_url(company_code: str | None = None) -> str:
    """
    Return the ERP API base URL for a given company code.

    Resolution order:
      1. LEYSCO_API_BASE_URL_<COMPANY_CODE>  env var  (per-tenant)
      2. LEYSCO_API_BASE_URL                 settings fallback
      3. Derive from Laravel backend URL     (append /api/v1)
      4. RuntimeError
    """
    if company_code:
        key = f"LEYSCO_API_BASE_URL_{company_code.upper()}"
        val = os.environ.get(key)
        if val:
            logger.debug(f"🔀 ERP base URL for {company_code}: {val} (from {key})")
            return val.rstrip("/")

    if settings.LEYSCO_API_BASE_URL:
        return settings.LEYSCO_API_BASE_URL.rstrip("/")

    # Derive from Laravel backend URL as last resort
    try:
        backend = get_laravel_backend_url(company_code)
        derived = f"{backend}/api/v1"
        logger.warning(
            f"LEYSCO_API_BASE_URL not set — derived from Laravel backend: {derived}"
        )
        return derived
    except RuntimeError:
        pass

    raise RuntimeError(
        "ERP API base URL is not configured. "
        f"Set LEYSCO_API_BASE_URL or LEYSCO_API_BASE_URL_<COMPANY_CODE> in .env."
    )


def get_all_tenant_company_codes() -> list[str]:
    """
    Return all company codes that have explicit per-tenant backend URL overrides.
    Useful for the background scanner to know which tenants exist.

    Scans os.environ for keys matching LARAVEL_BACKEND_URL_<CODE>.
    """
    prefix = "LARAVEL_BACKEND_URL_"
    codes = []
    for key in os.environ:
        if key.startswith(prefix):
            code = key[len(prefix):]
            if re.fullmatch(r"[A-Z0-9_-]{2,50}", code):
                codes.append(code)
    return sorted(codes)


# ── Validation ────────────────────────────────────────────────────────────────

def validate_settings() -> dict:
    """
    Validate required settings at startup.
    Returns {"valid": bool, "missing": [...], "warnings": [...]}.
    """
    missing:  list[str] = []
    warnings: list[str] = []

    # ── Critical ──────────────────────────────────────────────────────────────
    if not settings.LARAVEL_BACKEND_URL and not get_all_tenant_company_codes():
        missing.append(
            "LARAVEL_BACKEND_URL (or at least one LARAVEL_BACKEND_URL_<CODE>)"
        )

    if not settings.LEYSCO_API_BASE_URL and not get_all_tenant_company_codes():
        missing.append(
            "LEYSCO_API_BASE_URL (or at least one LEYSCO_API_BASE_URL_<CODE>)"
        )

    if not settings.JWT_SECRET_KEY:
        missing.append("JWT_SECRET_KEY")

    if settings.JWT_SECRET_KEY in (
        "your-secret-key-change-in-production",
        "secret", "changeme", "password",
    ):
        missing.append("JWT_SECRET_KEY is set to a known weak default — change it")

    if not settings.TENANT_CONFIG_ENCRYPTION_KEY:
        missing.append("TENANT_CONFIG_ENCRYPTION_KEY")

    # ── Warnings ──────────────────────────────────────────────────────────────
    if not settings.GROQ_API_KEY and not settings.GEMINI_API_KEY:
        warnings.append("No LLM API keys configured — AI features will be unavailable")

    if not settings.LEYSCO_SERVICE_ACCOUNT_EMAIL:
        warnings.append(
            "LEYSCO_SERVICE_ACCOUNT_EMAIL not set — "
            "background scanner cannot authenticate without active user sessions"
        )

    if not settings.CORS_ALLOWED_ORIGINS:
        warnings.append(
            "CORS_ALLOWED_ORIGINS not set — "
            "main.py will default to localhost only"
        )

    if settings.DEBUG and settings.is_production:
        warnings.append("DEBUG=True in a production environment — disable immediately")

    if settings.USE_MOCK_NOTIFICATIONS and settings.is_production:
        warnings.append("USE_MOCK_NOTIFICATIONS=True in production — disable immediately")

    tenants = get_all_tenant_company_codes()
    if tenants:
        logger.info(f"🏢 Tenants configured: {', '.join(tenants)}")
    else:
        warnings.append(
            "No per-tenant LARAVEL_BACKEND_URL_<CODE> entries found — "
            "all tenants will use the global LARAVEL_BACKEND_URL fallback"
        )

    # ── Report ────────────────────────────────────────────────────────────────
    for w in warnings:
        logger.warning(f"⚠️  {w}")

    if missing:
        logger.error(f"❌ Missing or invalid settings: {', '.join(missing)}")
        return {"valid": False, "missing": missing, "warnings": warnings}

    logger.info("✅ Configuration validated successfully")
    return {"valid": True, "missing": [], "warnings": warnings}


# ── Safe logging ──────────────────────────────────────────────────────────────

def get_masked_config() -> dict:
    """Returns config values safe for logging — all secrets masked."""

    def mask(value: str) -> str:
        if not value:
            return "NOT_SET"
        if len(value) <= 8:
            return "***"
        return f"{value[:4]}...{value[-4:]}"

    tenant_backends = {
        f"LARAVEL_BACKEND_URL_{code}": os.environ.get(f"LARAVEL_BACKEND_URL_{code}", "")
        for code in get_all_tenant_company_codes()
    }

    return {
        "APP_ENV":               settings.APP_ENV,
        "DEBUG":                 settings.DEBUG,
        "LARAVEL_BACKEND_URL":   settings.LARAVEL_BACKEND_URL or "NOT_SET",
        "LEYSCO_API_BASE_URL":   settings.LEYSCO_API_BASE_URL or "NOT_SET",
        "CORS_ALLOWED_ORIGINS":  settings.CORS_ALLOWED_ORIGINS or "NOT_SET",
        **tenant_backends,                          # shows all per-tenant URLs (not secret)
        "LEYSCO_SERVICE_ACCOUNT_EMAIL": mask(settings.LEYSCO_SERVICE_ACCOUNT_EMAIL),
        "GROQ_API_KEY":          mask(settings.GROQ_API_KEY),
        "GEMINI_API_KEY":        mask(settings.GEMINI_API_KEY),
        "JWT_SECRET_KEY":        "SET" if settings.JWT_SECRET_KEY else "NOT_SET",
        "SECRET_KEY":            "SET" if settings.SECRET_KEY    else "NOT_SET",
        "TENANT_CONFIG_ENCRYPTION_KEY": "SET" if settings.TENANT_CONFIG_ENCRYPTION_KEY else "NOT_SET",
        "CACHE_BACKEND":         settings.CACHE_BACKEND,
        "REDIS_HOST":            settings.REDIS_HOST,
        "REDIS_SSL":             settings.REDIS_SSL,
        "LOG_LEVEL":             settings.LOG_LEVEL,
        "USE_MOCK_NOTIFICATIONS": settings.USE_MOCK_NOTIFICATIONS,
        "TENANTS_CONFIGURED":    get_all_tenant_company_codes(),
    }