from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": stray keys in an operator's .env (e.g. from an older
    # version) must not crash startup.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Groq LLM (OpenAI-compatible)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # App
    IFC_OUTPUT_DIR: str = "./generated"
    # Stored results/IFC older than this are deleted daily; <= 0 disables cleanup.
    RESULT_TTL_DAYS: int = 30
    # Abuse guard on the paid-LLM generate endpoint, per client IP; 0 disables.
    RATE_LIMIT_PER_MINUTE: int = 5
    RATE_LIMIT_PER_DAY: int = 30
    # Overall Groq time budget per generation; past it the layout falls back to
    # the rule engine instead of racing the frontend's 120 s request timeout.
    LLM_TIME_BUDGET_S: float = 90.0
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
