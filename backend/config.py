from pydantic_settings import BaseSettings
from typing import List
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # Groq LLM (OpenAI-compatible)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Task queue
    REDIS_URL: str = "redis://redis:6379/0"

    # App
    IFC_OUTPUT_DIR: str = "./generated"
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def get_supabase():
    """Returns a Supabase client. Call per-request, client is lightweight."""
    from supabase import create_client
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
