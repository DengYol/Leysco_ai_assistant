from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Authentication ────────────────────────────────────────────────────────
    # Laravel backend used to validate user tokens on every request.
    LARAVEL_BACKEND_URL: str = ""

    # ── Leysco ERP API ────────────────────────────────────────────────────────
    LEYSCO_API_BASE_URL: str

    # System credentials — used only for ERP integration, never for data auth.
    LEYSCO_SYSTEM_USER:     str = ""
    LEYSCO_SYSTEM_PASSWORD: str = ""

    # ── LLM Providers ─────────────────────────────────────────────────────────
    LLM_PROVIDER: str = "auto"   # auto | groq | gemini

    GROQ_API_KEY: str = ""
    GROQ_MODEL:   str = "llama-3.1-8b-instant"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL:   str = "gemini-1.5-flash"

    OLLAMA_URL:     str = "http://localhost:11434/api/generate"
    OLLAMA_MODEL:   str = "llama-3.1-8b-instant"
    OLLAMA_TIMEOUT: int = 120

    # ── Cache ─────────────────────────────────────────────────────────────────
    CACHE_BACKEND:    str = "memory"   # memory | redis
    CACHE_TTL_SECONDS: int = 300
    CACHE_MAX_ENTRIES: int = 1000

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_HOST:     str = "localhost"
    REDIS_PORT:     int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB:       int = 0

    # ── Security ──────────────────────────────────────────────────────────────
    JWT_SECRET_KEY:              str = ""
    JWT_ALGORITHM:               str = "HS256"
    JWT_EXPIRE_HOURS:            int = 24
    TENANT_CONFIG_ENCRYPTION_KEY: str = ""

    # ── Competitor Pricing ────────────────────────────────────────────────────
    TWIGA_API_KEY:      str = ""
    SOKOPEPPER_API_KEY: str = ""
    FARMCROWDY_API_KEY: str = ""

    TWIGA_API_URL:      str = "https://api.twiga.com/v1/prices"
    SOKOPEPPER_API_URL: str = "https://api.sokopepper.co.ke/v2/prices"
    FARMCROWDY_API_URL: str = "https://api.farmcrowdy.com/prices"

    WORLD_BANK_ENABLED: bool = True
    WORLD_BANK_API_URL: str  = "https://api.worldbank.org/v2"

    ENABLED_COMPETITORS:          str = "market,worldbank"
    COMPETITOR_CACHE_TTL_HOURS:   int = 6
    COMPETITOR_API_TIMEOUT_SECONDS: int = 10

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_ENABLED:    bool = True
    RATE_LIMIT_PER_MINUTE: int  = 30

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FILE:  str = ""

    # ── General ───────────────────────────────────────────────────────────────
    APP_NAME: str  = "Leysco AI Sales Assistant"
    DEBUG:    bool = False

    USE_MOCK_NOTIFICATIONS: bool = False


settings = Settings()


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_settings() -> dict:
    """
    Validate required settings at startup.
    Logs errors for missing critical values and warnings for
    non-critical gaps. Returns a dict so callers can decide
    whether to abort.
    """
    import logging
    logger = logging.getLogger(__name__)

    missing:  list[str] = []
    warnings: list[str] = []

    # ── Critical — app cannot function without these ──────────────────────────
    if not settings.LARAVEL_BACKEND_URL:
        missing.append("LARAVEL_BACKEND_URL")

    if not settings.LEYSCO_API_BASE_URL:
        missing.append("LEYSCO_API_BASE_URL")

    if not settings.JWT_SECRET_KEY:
        missing.append("JWT_SECRET_KEY")

    if not settings.TENANT_CONFIG_ENCRYPTION_KEY:
        missing.append("TENANT_CONFIG_ENCRYPTION_KEY")

    # ── Warnings — degraded but operational ───────────────────────────────────
    if not settings.GROQ_API_KEY and not settings.GEMINI_API_KEY:
        warnings.append("No LLM API keys configured — AI features will be unavailable")

    if not settings.LEYSCO_SYSTEM_USER:
        warnings.append("LEYSCO_SYSTEM_USER not set — ERP integration may be limited")

    if settings.DEBUG:
        warnings.append("DEBUG mode is ON — disable before going live")

    if settings.USE_MOCK_NOTIFICATIONS:
        warnings.append("USE_MOCK_NOTIFICATIONS is ON — disable before going live")

    # ── Report ────────────────────────────────────────────────────────────────
    for w in warnings:
        logger.warning(f"⚠️  {w}")

    if missing:
        logger.error(f"❌ Missing required settings: {', '.join(missing)}")
        return {"valid": False, "missing": missing, "warnings": warnings}

    logger.info("✅ Configuration validated successfully")
    return {"valid": True, "missing": [], "warnings": warnings}


# ─── Masked config for safe logging ──────────────────────────────────────────

def get_masked_config() -> dict:
    """Returns config values safe for logging — all secrets are masked."""

    def mask(value: str) -> str:
        if not value:
            return "NOT_SET"
        if len(value) <= 8:
            return "***"
        return f"{value[:4]}...{value[-4:]}"

    return {
        "LARAVEL_BACKEND_URL":  settings.LARAVEL_BACKEND_URL or "NOT_SET",
        "LEYSCO_API_BASE_URL":  settings.LEYSCO_API_BASE_URL,
        "LEYSCO_SYSTEM_USER":   mask(settings.LEYSCO_SYSTEM_USER),
        "GROQ_API_KEY":         mask(settings.GROQ_API_KEY),
        "GEMINI_API_KEY":       mask(settings.GEMINI_API_KEY),
        "JWT_SECRET_KEY":       "SET" if settings.JWT_SECRET_KEY else "NOT_SET",
        "CACHE_BACKEND":        settings.CACHE_BACKEND,
        "REDIS_HOST":           settings.REDIS_HOST,
        "LOG_LEVEL":            settings.LOG_LEVEL,
        "DEBUG":                settings.DEBUG,
        "USE_MOCK_NOTIFICATIONS": settings.USE_MOCK_NOTIFICATIONS,
        "APP_NAME":             settings.APP_NAME,
    }