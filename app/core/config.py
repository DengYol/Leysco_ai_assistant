from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Leysco API
    LEYSCO_API_BASE_URL: str
    LEYSCO_API_TOKEN: str
    LEYSCO_USERNAME: str = ""  # Added for authentication
    LEYSCO_PASSWORD: str = ""  # Added for authentication

    # LLM Provider Configuration (New)
    LLM_PROVIDER: str = "auto"  # auto, groq, gemini

    # Groq (active LLM)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # Gemini API (Google AI Studio) - Added
    GEMINI_API_KEY: str = ""  # Get from https://aistudio.google.com/
    GEMINI_MODEL: str = "gemini-1.5-flash"  # or gemini-2.0-flash-exp

    # Ollama (backup — not used)
    OLLAMA_URL: str = "http://localhost:11434/api/generate"
    OLLAMA_MODEL: str = "llama-3.1-8b-instant"
    OLLAMA_TIMEOUT: int = 120

    # Cache Configuration (New)
    CACHE_BACKEND: str = "memory"  # memory, redis
    CACHE_TTL_SECONDS: int = 300
    CACHE_MAX_ENTRIES: int = 1000

    # Redis Configuration (New - optional)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    # Security (New)
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    
    # Tenant encryption (New)
    TENANT_CONFIG_ENCRYPTION_KEY: str = "your-encryption-key-32-bytes-here"

    # Competitor API Keys
    TWIGA_API_KEY: str = ""
    SOKOPEPPER_API_KEY: str = ""
    FARMCROWDY_API_KEY: str = ""
    
    # Competitor API URLs
    TWIGA_API_URL: str = "https://api.twiga.com/v1/prices"
    SOKOPEPPER_API_URL: str = "https://api.sokopepper.co.ke/v2/prices"
    FARMCROWDY_API_URL: str = "https://api.farmcrowdy.com/prices"
    
    # World Bank API (free)
    WORLD_BANK_ENABLED: bool = True
    WORLD_BANK_API_URL: str = "https://api.worldbank.org/v2"
    
    # Which competitors are enabled
    ENABLED_COMPETITORS: str = "market,worldbank"  # Add worldbank
    
    # Cache settings
    COMPETITOR_CACHE_TTL_HOURS: int = 6
    COMPETITOR_API_TIMEOUT_SECONDS: int = 10

    # Rate Limiting (New)
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 30

    # Logging (New)
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = ""

    # General
    APP_NAME: str = "Leysco AI Sales Assistant"
    DEBUG: bool = True


settings = Settings()


# Helper function to validate required settings
def validate_settings():
    """Validate that required settings are present."""
    missing = []
    
    if not settings.LEYSCO_API_TOKEN:
        missing.append("LEYSCO_API_TOKEN")
    if not settings.LEYSCO_API_BASE_URL:
        missing.append("LEYSCO_API_BASE_URL")
    
    if missing:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Missing required settings: {', '.join(missing)}")
        logger.warning("Please set these in your .env file or environment variables")
        return False
    
    return True