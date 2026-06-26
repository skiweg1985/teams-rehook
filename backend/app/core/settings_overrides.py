from __future__ import annotations

import base64
import hashlib
import threading
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import AppSetting, utc_now

SettingType = Literal["string", "int", "url", "enum", "secret"]


@dataclass(frozen=True)
class SettingDefinition:
    key: str
    label: str
    type: SettingType
    is_secret: bool
    enum_values: tuple[str, ...] = ()


OVERRIDABLE_SETTINGS: dict[str, SettingDefinition] = {
    "bot_delivery_mode": SettingDefinition(
        "bot_delivery_mode", "Bot delivery mode", "enum", False, ("mock", "real")
    ),
    "bot_default_service_url": SettingDefinition(
        "bot_default_service_url", "Bot default service URL", "url", False
    ),
    "webhook_max_payload_bytes": SettingDefinition(
        "webhook_max_payload_bytes", "Webhook payload limit", "int", False
    ),
    "log_retention_days": SettingDefinition("log_retention_days", "Log retention", "int", False),
    "log_cleanup_interval_minutes": SettingDefinition(
        "log_cleanup_interval_minutes", "Log cleanup interval", "int", False
    ),
    "app_public_base_url": SettingDefinition("app_public_base_url", "Public URL", "url", False),
    "frontend_base_url": SettingDefinition("frontend_base_url", "Frontend URL", "url", False),
    "ms_app_tenant_id": SettingDefinition("ms_app_tenant_id", "Microsoft tenant ID", "string", False),
    "ms_app_client_id": SettingDefinition("ms_app_client_id", "Microsoft client ID", "string", False),
    "ms_app_client_secret": SettingDefinition(
        "ms_app_client_secret", "Microsoft client secret", "secret", True
    ),
    "botframework_scope": SettingDefinition("botframework_scope", "Bot Framework scope", "string", False),
    "graph_scope": SettingDefinition("graph_scope", "Microsoft Graph scope", "string", False),
}

_override_cache: dict[str, str] = {}
_cache_lock = threading.Lock()


def _fernet() -> Fernet:
    settings = get_settings()
    source = (settings.settings_enc_key or settings.session_secret or "change-me-session-secret").strip()
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def _decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored secret override could not be decrypted",
        ) from exc


def _stored_value(row: AppSetting) -> str:
    if row.is_secret:
        return _decrypt_secret(row.value)
    return row.value


def _serialize_for_storage(key: str, value: str) -> str:
    definition = OVERRIDABLE_SETTINGS[key]
    normalized = _validate_and_normalize(key, value)
    if definition.is_secret:
        return _encrypt_secret(normalized)
    return normalized


def _validate_and_normalize(key: str, value: str) -> str:
    definition = OVERRIDABLE_SETTINGS.get(key)
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
        if key == "log_retention_days" and parsed < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Retention must be zero or greater")
        if key == "log_cleanup_interval_minutes" and parsed < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Cleanup interval must be at least 1"
            )
        return str(parsed)

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

    return raw


def _coerce_for_settings(key: str, value: str) -> Any:
    definition = OVERRIDABLE_SETTINGS[key]
    if definition.type == "int":
        return int(value)
    if definition.type == "enum":
        return value
    return value


def _mask_secret(value: str) -> str:
    return "configured" if value.strip() else "missing"


def _display_value(key: str, value: str) -> str:
    definition = OVERRIDABLE_SETTINGS[key]
    if definition.is_secret:
        return _mask_secret(value)
    return value


def _env_value(settings: Settings, key: str) -> str:
    return str(getattr(settings, key))


def load_overrides(db: Session) -> None:
    global _override_cache
    rows = db.scalars(select(AppSetting)).all()
    loaded: dict[str, str] = {}
    for row in rows:
        if row.key not in OVERRIDABLE_SETTINGS:
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
        overrides = dict(_override_cache)
    if not overrides:
        return base
    updates = {key: _coerce_for_settings(key, value) for key, value in overrides.items()}
    return base.model_copy(update=updates)


def set_override(db: Session, *, key: str, value: str, updated_by_id: str | None) -> None:
    if key not in OVERRIDABLE_SETTINGS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown setting")

    definition = OVERRIDABLE_SETTINGS[key]
    stored = _serialize_for_storage(key, value)
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
    db.flush()
    load_overrides(db)
    _on_change()


def clear_override(db: Session, *, key: str) -> None:
    if key not in OVERRIDABLE_SETTINGS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown setting")

    row = db.get(AppSetting, key)
    if row is not None:
        db.delete(row)
        db.flush()
    load_overrides(db)
    _on_change()


def is_overridden(key: str) -> bool:
    return key in _override_cache


def list_setting_items() -> list[dict[str, Any]]:
    env_settings = get_settings()
    effective = get_effective_settings()
    items: list[dict[str, Any]] = []
    for key, definition in OVERRIDABLE_SETTINGS.items():
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
            }
        )
    return items


def _on_change() -> None:
    from app.services.graph_targets import reset_graph_token_manager
    from app.services.teams_bot import reset_bot_token_manager

    reset_bot_token_manager()
    reset_graph_token_manager()
