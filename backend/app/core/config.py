from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    app_name: str = "Teams Rehook"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./app.db"
    cors_origins: str = "http://localhost:5173,http://localhost"
    app_public_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"

    session_cookie_name: str = "teams_rehook_session"
    session_ttl_hours: int = 8
    session_secure_cookie: bool = False
    session_secret: str = "change-me-session-secret"

    default_org_slug: str = "default"
    default_org_name: str = "Default Organization"
    ms_app_tenant_id: str = ""
    ms_app_client_id: str = ""
    ms_app_client_secret: str = ""
    botframework_scope: str = "https://api.botframework.com/.default"
    graph_scope: str = "https://graph.microsoft.com/.default"
    bot_framework_enabled: bool = True
    graph_lookup_enabled: bool = True
    graph_delivery_enabled: bool = True
    bot_delivery_mode: str = "real"
    bot_default_service_url: str = ""
    webhook_max_payload_bytes: int = 64_000
    webhook_abuse_blocking_enabled: bool = True
    webhook_abuse_failure_limit: int = 10
    webhook_abuse_window_minutes: int = 10
    webhook_abuse_initial_block_minutes: int = 10
    webhook_abuse_max_block_minutes: int = 1440
    webhook_abuse_cleanup_days: int = 30
    log_retention_days: int = 7
    log_cleanup_interval_minutes: int = 60
    trust_x_forwarded_for: bool = False
    trusted_proxy_ips: str = ""
    settings_enc_key: str = ""
    monitoring_api_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def bot_delivery_mode_normalized(self) -> str:
        mode = self.bot_delivery_mode.strip().lower()
        return mode if mode in {"mock", "real"} else "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
