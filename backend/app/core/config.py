from __future__ import annotations

from functools import lru_cache
import secrets

from pydantic import PrivateAttr
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SESSION_SECRETS = {"change-me-session-secret", "change-me", "changeme", "secret", "default"}
PLACEHOLDER_SETTINGS_ENC_KEYS = {
    "change-me-settings-enc-key",
    "change-me-settings-key",
    "change-me",
    "changeme",
    "secret",
    "default",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")
    _session_secret_generated: bool = PrivateAttr(default=False)
    _settings_enc_key_generated: bool = PrivateAttr(default=False)
    _bot_framework_enabled: bool = PrivateAttr(default=True)
    _graph_lookup_enabled: bool = PrivateAttr(default=True)
    _graph_delivery_enabled: bool = PrivateAttr(default=True)
    _webhook_url_reveal_ttl_hours: int = PrivateAttr(default=24)

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
    session_secret: str = ""

    default_org_slug: str = "default"
    default_org_name: str = "Default Organization"
    ms_app_tenant_id: str = ""
    ms_app_client_id: str = ""
    ms_app_client_secret: str = ""
    botframework_scope: str = "https://api.botframework.com/.default"
    graph_scope: str = "https://graph.microsoft.com/.default"
    bot_delivery_mode: str = "real"
    webhook_max_payload_bytes: int = 64_000
    webhook_abuse_blocking_enabled: bool = True
    webhook_abuse_failure_limit: int = 10
    webhook_abuse_window_minutes: int = 10
    webhook_abuse_initial_block_minutes: int = 10
    webhook_abuse_max_block_minutes: int = 1440
    webhook_abuse_cleanup_days: int = 30
    log_retention_days: int = 7
    log_cleanup_interval_minutes: int = 60
    event_debug_previews_enabled: bool = False
    compose_app_subnet: str = "172.30.0.0/24"
    trust_x_forwarded_for: bool = False
    trusted_proxy_ips: str = ""
    settings_enc_key: str = ""
    monitoring_api_key: str = ""

    @property
    def bot_framework_enabled(self) -> bool:
        return self._bot_framework_enabled

    @property
    def graph_lookup_enabled(self) -> bool:
        return self._graph_lookup_enabled

    @property
    def graph_delivery_enabled(self) -> bool:
        return self._graph_delivery_enabled

    @property
    def webhook_url_reveal_ttl_hours(self) -> int:
        return self._webhook_url_reveal_ttl_hours

    def use_delivery_feature_settings(
        self,
        *,
        bot_framework_enabled: bool | None = None,
        graph_lookup_enabled: bool | None = None,
        graph_delivery_enabled: bool | None = None,
        webhook_url_reveal_ttl_hours: int | None = None,
    ) -> None:
        if bot_framework_enabled is not None:
            self._bot_framework_enabled = bot_framework_enabled
        if graph_lookup_enabled is not None:
            self._graph_lookup_enabled = graph_lookup_enabled
        if graph_delivery_enabled is not None:
            self._graph_delivery_enabled = graph_delivery_enabled
        if webhook_url_reveal_ttl_hours is not None:
            self._webhook_url_reveal_ttl_hours = webhook_url_reveal_ttl_hours

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def bot_delivery_mode_normalized(self) -> str:
        mode = self.bot_delivery_mode.strip().lower()
        return mode if mode in {"mock", "real"} else "mock"

    def has_configured_session_secret(self) -> bool:
        return bool(self.session_secret.strip()) and not self._session_secret_generated

    def ensure_session_secret(self) -> str:
        if not self.session_secret.strip():
            self.session_secret = secrets.token_urlsafe(48)
            self._session_secret_generated = True
        return self.session_secret

    def use_generated_session_secret(self, value: str) -> None:
        self.session_secret = value
        self._session_secret_generated = True

    def has_configured_settings_enc_key(self) -> bool:
        return bool(self.settings_enc_key.strip()) and not self._settings_enc_key_generated

    def use_generated_settings_enc_key(self, value: str) -> None:
        self.settings_enc_key = value
        self._settings_enc_key_generated = True

    @property
    def settings_enc_key_source(self) -> str:
        if self.has_configured_settings_enc_key():
            return "configured"
        if self.settings_enc_key.strip() and self._settings_enc_key_generated:
            return "generated"
        return "missing"


def is_placeholder_session_secret(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or normalized in PLACEHOLDER_SESSION_SECRETS or normalized.startswith("change-me")


def is_placeholder_settings_enc_key(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or normalized in PLACEHOLDER_SETTINGS_ENC_KEYS or normalized.startswith("change-me")


@lru_cache
def get_settings() -> Settings:
    return Settings()
