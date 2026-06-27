import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GITHUB_TOKEN: Optional[str] = None
    STACKOVERFLOW_KEY: Optional[str] = None
    SUPABASE_URL: Optional[str] = None
    SUPABASE_SERVICE_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    ENVIRONMENT: str = "development"

    @property
    def github_token(self) -> Optional[str]:
        return self.GITHUB_TOKEN

    @property
    def stackoverflow_key(self) -> Optional[str]:
        return self.STACKOVERFLOW_KEY

    @property
    def supabase_url(self) -> Optional[str]:
        return self.SUPABASE_URL

    @property
    def supabase_service_key(self) -> Optional[str]:
        return self.SUPABASE_SERVICE_KEY

    @property
    def gemini_api_key(self) -> Optional[str]:
        return self.GEMINI_API_KEY

    @property
    def environment(self) -> str:
        return self.ENVIRONMENT

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
