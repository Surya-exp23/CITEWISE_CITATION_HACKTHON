"""Runtime configuration — PRD section 18 (env vars)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "sqlite:///./citewise.db"
    OFFLINE_MODE: bool = True
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    PUBLIC_BASE_URL: str = "http://localhost:3000"
    ADMIN_TOKEN: str = ""
    ENABLE_LLM_ASSIST: bool = False
    GROQ_API_KEY: str = ""
    LLM_MODEL: str = "llama-3.3-70b-versatile"


settings = Settings()
