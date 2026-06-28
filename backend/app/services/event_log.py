from __future__ import annotations

import logging
import re
import time
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.settings_overrides import get_effective_settings
from app.database import SessionLocal
from app.models import EventLogEntry
from app.security import dumps_json

logger = logging.getLogger("teams_rehook.event_log")

_request_id: ContextVar[str] = ContextVar("request_id", default="")
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")

SENSITIVE_KEY_RE = re.compile(
    r"(authorization|cookie|token|secret|password|csrf|session|key|code|refresh_token|access_token|client_secret)",
    re.IGNORECASE,
)
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,80}$")
MAX_SAFE_PREVIEW = 1200


def current_request_id() -> str:
    return _request_id.get()


def current_correlation_id() -> str:
    return _correlation_id.get() or _request_id.get()


def set_event_context(*, request_id: str, correlation_id: str) -> None:
    _request_id.set(request_id)
    _correlation_id.set(correlation_id or request_id)


def issue_request_id(value: str | None = None) -> str:
    candidate = (value or "").strip()
    if candidate and SAFE_ID_RE.match(candidate):
        return candidate[:80]
    return uuid4().hex


def emit_event(
    db: Session | None = None,
    *,
    level: str = "info",
    category: str,
    event_type: str,
    message: str,
    user_message: str = "",
    correlation_id: str | None = None,
    request_id: str | None = None,
    actor: dict[str, Any] | None = None,
    target: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
    http: dict[str, Any] | None = None,
    security: dict[str, Any] | None = None,
    raw: dict[str, Any] | None = None,
    domain: str = "",
    domain_event_id: str | None = None,
    commit: bool | None = None,
) -> EventLogEntry | None:
    """Persist and print a structured event without allowing logging failures to affect callers."""
    entry = EventLogEntry(
        level=_clip(level or "info", 20),
        category=_clip(category, 40),
        event_type=_clip(event_type, 120),
        message=_clip(message, 2000),
        user_message=_clip(user_message, 1000),
        correlation_id=_clip(correlation_id or current_correlation_id(), 80),
        request_id=_clip(request_id or current_request_id(), 80),
        actor_json=dumps_json(redact(actor or {})),
        target_json=dumps_json(redact(target or {})),
        source_json=dumps_json(redact(source or {}, preserve_raw_source=True)),
        http_json=dumps_json(redact(http or {})),
        security_json=dumps_json(redact(security or {})),
        raw_json=dumps_json(safe_raw(raw or {})),
        domain=_clip(domain, 40),
        domain_event_id=domain_event_id,
    )
    _log_to_console(entry)
    if db is not None:
        try:
            with db.begin_nested():
                db.add(entry)
                db.flush()
            if commit:
                db.commit()
            return entry
        except Exception:
            logger.exception("Event log persistence failed")
            return None

    try:
        with SessionLocal() as own_db:
            own_db.add(entry)
            own_db.commit()
            return entry
    except Exception:
        logger.exception("Event log persistence failed")
        return None


def event_from_entry(entry: EventLogEntry) -> dict[str, Any]:
    from app.security import loads_json

    return {
        "id": entry.id,
        "level": entry.level,
        "category": entry.category,
        "event_type": entry.event_type,
        "message": entry.message,
        "user_message": entry.user_message,
        "correlation_id": entry.correlation_id,
        "request_id": entry.request_id,
        "actor": loads_json(entry.actor_json, {}),
        "target": loads_json(entry.target_json, {}),
        "source": loads_json(entry.source_json, {}),
        "http": loads_json(entry.http_json, {}),
        "security": loads_json(entry.security_json, {}),
        "raw": loads_json(entry.raw_json, {}),
        "domain": entry.domain,
        "domain_event_id": entry.domain_event_id,
        "created_at": entry.created_at,
    }


def request_source(request: Request) -> dict[str, str]:
    return {
        "ip": request.client.host if request.client else "",
        "user_agent": _clip(request.headers.get("user-agent", ""), 500),
        "x_forwarded_for": _clip(request.headers.get("x-forwarded-for", ""), 500),
    }


def request_http(request: Request, *, status_code: int, duration_ms: int) -> dict[str, Any]:
    return {
        "method": request.method,
        "path": sanitize_path(request.url.path),
        "status_code": status_code,
        "duration_ms": duration_ms,
        "content_type": _clip(request.headers.get("content-type", ""), 200),
        "content_length": _clip(request.headers.get("content-length", ""), 40),
    }


def sanitize_path(path: str) -> str:
    value = path.split("?", 1)[0]
    value = re.sub(r"(/api/v1/webhooks/)[^/]+", r"\1{token}", value)
    value = re.sub(r"(/api/v1/admin/webhook-abuse-buckets/)[^/]+", r"\1{id}", value)
    value = re.sub(r"(/api/v1/webhook-delivery-events/)[^/]+", r"\1{id}", value)
    value = re.sub(r"(/api/v1/webhook-routes/)[^/]+", r"\1{id}", value)
    value = re.sub(r"(/api/v1/admin/users/)[^/]+", r"\1{id}", value)
    value = re.sub(r"(/api/v1/admin/settings/)[^/]+", r"\1{key}", value)
    return _clip(value, 600)


async def log_api_request(request: Request, call_next):
    if not request.url.path.startswith("/api/v1/"):
        return await call_next(request)

    request_id = issue_request_id(request.headers.get("x-request-id"))
    correlation_id = issue_request_id(request.headers.get("x-correlation-id") or request_id)
    set_event_context(request_id=request_id, correlation_id=correlation_id)
    request.state.request_id = request_id
    request.state.correlation_id = correlation_id
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        return response
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        emit_event(
            level="error",
            category="system",
            event_type="system.unhandled_exception",
            message=f"Unhandled exception while handling {request.method} {sanitize_path(request.url.path)}",
            correlation_id=correlation_id,
            request_id=request_id,
            source=request_source(request),
            http=request_http(request, status_code=500, duration_ms=duration_ms),
            raw={"exception_type": exc.__class__.__name__, "exception": str(exc)},
            domain="system",
        )
        raise
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        emit_event(
            level=_level_for_status(status_code),
            category="request",
            event_type="request.completed",
            message=f"{request.method} {sanitize_path(request.url.path)} completed with HTTP {status_code}",
            correlation_id=correlation_id,
            request_id=request_id,
            source=request_source(request),
            http=request_http(request, status_code=status_code, duration_ms=duration_ms),
            domain="request",
        )


def redact(value: Any, *, preserve_raw_source: bool = False) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if SENSITIVE_KEY_RE.search(key_str) and not (preserve_raw_source and key_str in {"ip", "user_agent", "x_forwarded_for"}):
                redacted[key_str] = "[redacted]"
            else:
                redacted[key_str] = redact(item, preserve_raw_source=preserve_raw_source)
        return redacted
    if isinstance(value, list):
        return [redact(item, preserve_raw_source=preserve_raw_source) for item in value[:50]]
    if isinstance(value, str):
        return _clip(value, 2000)
    return value


def safe_raw(value: dict[str, Any]) -> dict[str, Any]:
    settings = get_effective_settings()
    if not getattr(settings, "event_debug_previews_enabled", False):
        return {}
    return _clip_nested(redact(value), MAX_SAFE_PREVIEW)


def _clip_nested(value: Any, limit: int) -> Any:
    if isinstance(value, dict):
        return {str(key): _clip_nested(item, limit) for key, item in list(value.items())[:50]}
    if isinstance(value, list):
        return [_clip_nested(item, limit) for item in value[:50]]
    if isinstance(value, str):
        return _clip(value, limit)
    return value


def _level_for_status(status_code: int) -> str:
    if status_code >= 500:
        return "error"
    if status_code in {401, 403, 429}:
        return "warning"
    if status_code >= 400:
        return "warning"
    return "info"


def _log_to_console(entry: EventLogEntry) -> None:
    level = logging.ERROR if entry.level in {"error", "critical"} else logging.WARNING if entry.level == "warning" else logging.INFO
    logger.log(
        level,
        "%s %s %s request_id=%s correlation_id=%s",
        entry.category,
        entry.event_type,
        entry.message,
        entry.request_id,
        entry.correlation_id,
    )


def _clip(value: str, limit: int) -> str:
    return str(value or "")[:limit]
