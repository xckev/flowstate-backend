"""Application configuration — reads values from .env via pydantic-settings."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Google OAuth
    google_client_id: str
    google_client_secret: str

    # Gemini
    gemini_api_key: str

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "flowstate"

    # CORS / frontend origin
    frontend_origin: str = "http://localhost:3000"

    # JWT signing key
    secret_key: str

    # OAuth callback URL — must match the redirect URI registered in Google Cloud Console
    oauth_redirect_uri: str = "http://localhost:8000/auth/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
