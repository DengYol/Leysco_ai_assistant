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

    # Groq (active LLM)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # Ollama (backup — not used)
    OLLAMA_URL: str = "http://localhost:11434/api/generate"
    OLLAMA_MODEL: str = "llama-3.1-8b-instant"
    OLLAMA_TIMEOUT: int = 120

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

    # General
    APP_NAME: str = "Leysco AI Sales Assistant"
    DEBUG: bool = True


settings = Settings()