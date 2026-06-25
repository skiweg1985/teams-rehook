from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    app_name: str = "codex-app-skeleton"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./app.db"
    cors_origins: str = "http://localhost:5173,http://localhost"
    app_public_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"

    session_cookie_name: str = "codex_app_session"
    session_ttl_hours: int = 8
    session_secure_cookie: bool = False
    session_secret: str = "change-me-session-secret"

    default_org_slug: str = "default"
    default_org_name: str = "Default Organization"
    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: str = "change-me-admin-password"
    bootstrap_admin_display_name: str = "App Admin"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
