from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.encrypted_secrets import decrypt_secret, encrypt_secret
from app.models import AppSetting, utc_now

SettingType = Literal["string", "int", "url", "enum", "secret", "bool"]
SettingSource = Literal["environment", "application"]


@dataclass(frozen=True)
class SettingDefinition:
    key: str
    label: str
    type: SettingType
    is_secret: bool
    enum_values: tuple[str, ...] = ()
    source: SettingSource = "environment"


APPLICATION_SETTINGS: dict[str, SettingDefinition] = {
    "bot_framework_enabled": SettingDefinition(
        "bot_framework_enabled", "Bot Framework enabled", "bool", False, source="application"
    ),
    "graph_lookup_enabled": SettingDefinition(
        "graph_lookup_enabled", "Graph lookup enabled", "bool", False, source="application"
    ),
    "graph_delivery_enabled": SettingDefinition(
        "graph_delivery_enabled", "Graph delivery enabled", "bool", False, source="application"
    ),
    "webhook_url_reveal_ttl_hours": SettingDefinition(
        "webhook_url_reveal_ttl_hours", "Webhook URL reveal link lifetime", "int", False, source="application"
    ),
}

OVERRIDABLE_SETTINGS: dict[str, SettingDefinition] = {
    "bot_default_service_url": SettingDefinition(
        "bot_default_service_url", "Bot default service URL", "url", False
    ),
    "webhook_max_payload_bytes": SettingDefinition(
        "webhook_max_payload_bytes", "Webhook payload limit", "int", False
    ),
    "webhook_abuse_blocking_enabled": SettingDefinition(
        "webhook_abuse_blocking_enabled", "Webhook abuse blocking", "bool", False
    ),
    "webhook_abuse_failure_limit": SettingDefinition(
        "webhook_abuse_failure_limit", "Webhook abuse failure limit", "int", False
    ),
    "webhook_abuse_window_minutes": SettingDefinition(
        "webhook_abuse_window_minutes", "Webhook abuse window", "int", False
    ),
    "log_retention_days": SettingDefinition("log_retention_days", "Log retention", "int", False),
    "log_cleanup_interval_minutes": SettingDefinition(
        "log_cleanup_interval_minutes", "Log cleanup interval", "int", False
    ),
    "event_debug_previews_enabled": SettingDefinition(
        "event_debug_previews_enabled", "Event debug previews", "bool", False
    ),
    "trust_x_forwarded_for": SettingDefinition(
        "trust_x_forwarded_for", "Trust X-Forwarded-For", "bool", False
    ),
    "session_secure_cookie": SettingDefinition(
        "session_secure_cookie", "Secure session cookie", "bool", False
    ),
    "cors_origins": SettingDefinition("cors_origins", "CORS origins", "string", False),
    "app_public_base_url": SettingDefinition("app_public_base_url", "Public URL", "url", False),
    "frontend_base_url": SettingDefinition("frontend_base_url", "Frontend URL", "url", False),
    "ms_app_tenant_id": SettingDefinition("ms_app_tenant_id", "Microsoft tenant ID", "string", False),
    "ms_app_client_id": SettingDefinition("ms_app_client_id", "Microsoft client ID", "string", False),
    "ms_app_client_secret": SettingDefinition(
        "ms_app_client_secret", "Microsoft client secret", "secret", True
    ),
}

SETTING_DEFINITIONS: dict[str, SettingDefinition] = {
    **APPLICATION_SETTINGS,
    **OVERRIDABLE_SETTINGS,
}

_override_cache: dict[str, str] = {}
_cache_lock = threading.Lock()


def _encrypt_secret(value: str) -> str:
    return encrypt_secret(value)


def _decrypt_secret(value: str) -> str:
    try:
        return decrypt_secret(value)
    except HTTPException as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Stored secret override could not be decrypted with the current SETTINGS_ENC_KEY. "
                "Keep the previous key or re-enter the affected secret."
            ),
        ) from exc


def _stored_value(row: AppSetting) -> str:
    if row.is_secret:
        return _decrypt_secret(row.value)
    return row.value


def _serialize_for_storage(key: str, value: str) -> str:
    definition = SETTING_DEFINITIONS[key]
    normalized = _validate_and_normalize(key, value)
    if definition.is_secret:
        return _encrypt_secret(normalized)
    return normalized


def _validate_and_normalize(key: str, value: str) -> str:
    definition = SETTING_DEFINITIONS.get(key)
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown setting")

    raw = value.strip()
    if definition.type == "secret":
        if not raw:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Secret value is required")
        return raw

    if definition.type == "int":
        try:
            parsed = int(raw)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Value must be an integer") from exc
        if key == "webhook_max_payload_bytes" and parsed < 1024:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload limit must be at least 1024")
        if key == "webhook_abuse_failure_limit" and parsed < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failure limit must be at least 1")
        if key == "webhook_abuse_window_minutes" and parsed < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Value must be at least 1")
        if key == "webhook_url_reveal_ttl_hours" and not 1 <= parsed <= 168:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reveal link lifetime must be between 1 and 168 hours",
            )
        if key == "log_retention_days" and parsed < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Retention must be zero or greater")
        if key == "log_cleanup_interval_minutes" and parsed < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Cleanup interval must be at least 1"
            )
        return str(parsed)

    if definition.type == "bool":
        normalized = raw.lower()
        if normalized in {"true", "1", "yes", "on", "enabled"}:
            return "true"
        if normalized in {"false", "0", "no", "off", "disabled"}:
            return "false"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Value must be true or false")

    if definition.type == "enum":
        normalized = raw.lower()
        if normalized not in definition.enum_values:
            allowed = ", ".join(definition.enum_values)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Value must be one of: {allowed}",
            )
        return normalized

    if definition.type == "url":
        if not raw:
            return ""
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Value must be a valid HTTP URL")
        return raw.rstrip("/")

    if key == "cors_origins":
        return _normalize_cors_origins(raw)

    return raw


def _normalize_cors_origins(value: str) -> str:
    origins: list[str] = []
    for part in value.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CORS origins must be comma-separated HTTP or HTTPS origins",
            )
        if parsed.params or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CORS origins must contain scheme, host, and optional port only",
            )
        origin = f"{parsed.scheme.lower()}://{parsed.netloc}"
        if origin not in origins:
            origins.append(origin)
    if not origins:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CORS origins must list at least one HTTP or HTTPS origin",
        )
    return ",".join(origins)


def _coerce_for_settings(key: str, value: str) -> Any:
    definition = SETTING_DEFINITIONS[key]
    if definition.type == "int":
        return int(value)
    if definition.type == "bool":
        return value.strip().lower() == "true"
    if definition.type == "enum":
        return value
    return value


def _mask_secret(value: str) -> str:
    return "configured" if value.strip() else "missing"


def _display_value(key: str, value: str) -> str:
    definition = SETTING_DEFINITIONS[key]
    if definition.is_secret:
        return _mask_secret(value)
    if definition.type == "bool":
        return "true" if str(value).strip().lower() in {"true", "1", "yes", "on"} else "false"
    return value


def _env_value(settings: Settings, key: str) -> str:
    value = getattr(settings, key)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def load_overrides(db: Session) -> None:
    global _override_cache
    rows = db.scalars(select(AppSetting)).all()
    loaded: dict[str, str] = {}
    for row in rows:
        if row.key not in SETTING_DEFINITIONS:
            continue
        loaded[row.key] = _stored_value(row)
    with _cache_lock:
        _override_cache = loaded


def reset_override_state() -> None:
    global _override_cache
    with _cache_lock:
        _override_cache = {}


def get_effective_settings() -> Settings:
    base = get_settings()
    with _cache_lock:
        cached_settings = dict(_override_cache)
    if not cached_settings:
        return base
    env_updates = {
        key: _coerce_for_settings(key, value)
        for key, value in cached_settings.items()
        if key in OVERRIDABLE_SETTINGS
    }
    effective = base.model_copy(update=env_updates)
    effective.use_delivery_feature_settings(
        bot_framework_enabled=_coerce_for_settings("bot_framework_enabled", cached_settings["bot_framework_enabled"])
        if "bot_framework_enabled" in cached_settings
        else None,
        graph_lookup_enabled=_coerce_for_settings("graph_lookup_enabled", cached_settings["graph_lookup_enabled"])
        if "graph_lookup_enabled" in cached_settings
        else None,
        graph_delivery_enabled=_coerce_for_settings("graph_delivery_enabled", cached_settings["graph_delivery_enabled"])
        if "graph_delivery_enabled" in cached_settings
        else None,
        webhook_url_reveal_ttl_hours=_coerce_for_settings(
            "webhook_url_reveal_ttl_hours", cached_settings["webhook_url_reveal_ttl_hours"]
        )
        if "webhook_url_reveal_ttl_hours" in cached_settings
        else None,
    )
    return effective


def set_override(db: Session, *, key: str, value: str, updated_by_id: str | None) -> None:
    if key not in SETTING_DEFINITIONS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown setting")

    previous_frontend_url = get_effective_settings().frontend_base_url.rstrip("/") if key == "frontend_base_url" else ""
    definition = SETTING_DEFINITIONS[key]
    normalized = _validate_and_normalize(key, value)
    stored = _serialize_for_storage(key, normalized)
    _validate_feature_dependency(_hypothetical_settings(key, normalized))
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=stored, is_secret=definition.is_secret, updated_by_id=updated_by_id)
        db.add(row)
    else:
        row.value = stored
        row.is_secret = definition.is_secret
        row.updated_by_id = updated_by_id
        row.updated_at = utc_now()
        db.add(row)

    if key == "frontend_base_url":
        cors_row = db.get(AppSetting, "cors_origins")
        cors_stored = _stored_value(cors_row) if cors_row is not None else ""
        if cors_row is None:
            db.add(
                AppSetting(
                    key="cors_origins",
                    value=_serialize_for_storage("cors_origins", normalized),
                    is_secret=False,
                    updated_by_id=updated_by_id,
                )
            )
        elif cors_stored == previous_frontend_url:
            cors_row.value = _serialize_for_storage("cors_origins", normalized)
            cors_row.updated_by_id = updated_by_id
            cors_row.updated_at = utc_now()
            db.add(cors_row)

    db.flush()
    load_overrides(db)
    _on_change()


def clear_override(db: Session, *, key: str) -> None:
    if key not in SETTING_DEFINITIONS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown setting")

    _validate_feature_dependency(_hypothetical_settings(key, None))
    row = db.get(AppSetting, key)
    if row is not None:
        db.delete(row)
        db.flush()
    load_overrides(db)
    _on_change()


def is_overridden(key: str) -> bool:
    if key not in OVERRIDABLE_SETTINGS:
        return False
    return key in _override_cache


def is_environment_override(key: str) -> bool:
    return key in OVERRIDABLE_SETTINGS


def _hypothetical_settings(key: str, value: str | None) -> dict[str, str]:
    with _cache_lock:
        settings = dict(_override_cache)
    if value is None:
        settings.pop(key, None)
    else:
        settings[key] = value
    return settings


def _validate_feature_dependency(cached_settings: dict[str, str]) -> None:
    graph_lookup_enabled = (
        _coerce_for_settings("graph_lookup_enabled", cached_settings["graph_lookup_enabled"])
        if "graph_lookup_enabled" in cached_settings
        else True
    )
    graph_delivery_enabled = (
        _coerce_for_settings("graph_delivery_enabled", cached_settings["graph_delivery_enabled"])
        if "graph_delivery_enabled" in cached_settings
        else True
    )
    if graph_delivery_enabled and not graph_lookup_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Graph delivery requires Graph lookup to be enabled",
        )


def list_setting_items() -> list[dict[str, Any]]:
    env_settings = get_settings()
    effective = get_effective_settings()
    items: list[dict[str, Any]] = []
    for key, definition in SETTING_DEFINITIONS.items():
        env_raw = _env_value(env_settings, key)
        effective_raw = _env_value(effective, key)
        items.append(
            {
                "key": key,
                "label": definition.label,
                "type": definition.type,
                "enum_values": list(definition.enum_values),
                "env_default": _display_value(key, env_raw),
                "effective_value": _display_value(key, effective_raw),
                "is_overridden": is_overridden(key),
                "source": definition.source,
            }
        )
    return items


def _on_change() -> None:
    from app.services.graph_targets import reset_graph_token_manager
    from app.services.teams_bot import reset_bot_token_manager

    reset_bot_token_manager()
    reset_graph_token_manager()
