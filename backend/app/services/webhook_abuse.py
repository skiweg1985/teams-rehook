from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.settings_overrides import get_effective_settings
from app.models import WebhookAbuseBucket
from app.security import ensure_utc, utcnow
from app.services.event_log import emit_event

BLOCKED_WEBHOOK_DETAIL = "Too many failed webhook attempts"
SCOPE_IP = "ip"
SCOPE_IP_ROUTE = "ip_route"


@dataclass(frozen=True)
class WebhookBlockDecision:
    bucket: WebhookAbuseBucket

    @property
    def blocked_until(self):
        return ensure_utc(self.bucket.blocked_until)


@dataclass(frozen=True)
class WebhookAbuseCleanupResult:
    deleted: int
    cutoff: datetime


def check_block(db: Session, *, client_host: str, route_token_hash: str | None) -> WebhookBlockDecision | None:
    settings = get_effective_settings()
    if not settings.webhook_abuse_blocking_enabled:
        return None

    now = utcnow()
    blocked_bucket: WebhookAbuseBucket | None = None
    expired: list[WebhookAbuseBucket] = []
    for bucket in _load_buckets(db, client_host=client_host, route_token_hash=route_token_hash):
        bucket.last_client_host = _stored_client_host(client_host)
        bucket.last_seen_at = now
        blocked_until = ensure_utc(bucket.blocked_until)
        if blocked_until is None:
            continue
        if blocked_until > now:
            if blocked_bucket is None or blocked_until > (ensure_utc(blocked_bucket.blocked_until) or now):
                blocked_bucket = bucket
        else:
            expired.append(bucket)

    for bucket in expired:
        bucket.blocked_until = None
        bucket.failure_count = 0
        bucket.window_started_at = now
        bucket.last_seen_at = now

    if blocked_bucket is None:
        return None
    return WebhookBlockDecision(bucket=blocked_bucket)


def record_failure(db: Session, *, client_host: str, route_token_hash: str | None, reason: str) -> list[WebhookAbuseBucket]:
    settings = get_effective_settings()
    if not settings.webhook_abuse_blocking_enabled:
        return []

    now = utcnow()
    window = timedelta(minutes=settings.webhook_abuse_window_minutes)
    buckets: list[WebhookAbuseBucket] = []
    for scope, scoped_route_token_hash in _bucket_scopes(route_token_hash):
        bucket = _get_or_create_bucket(
            db,
            client_host=client_host,
            scope=scope,
            route_token_hash=scoped_route_token_hash,
            now=now,
        )
        window_started_at = ensure_utc(bucket.window_started_at) or now
        if now - window_started_at > window:
            bucket.failure_count = 0
            bucket.window_started_at = now

        bucket.failure_count += 1
        bucket.last_reason = reason[:120]
        bucket.last_client_host = _stored_client_host(client_host)
        bucket.last_seen_at = now
        if bucket.failure_count >= settings.webhook_abuse_failure_limit:
            bucket.block_count += 1
            bucket.blocked_until = now + _block_duration(bucket.block_count)
            emit_event(
                db,
                level="warning",
                category="security",
                event_type="webhook_abuse.client_blocked",
                message="Webhook client was blocked after repeated failed attempts.",
                source={"ip": client_host},
                security={"severity": "medium", "reason": reason},
                target={"type": "webhook", "scope": scope, "route_fingerprint": (route_token_hash or "")[:12]},
                raw={"failure_count": bucket.failure_count, "block_count": bucket.block_count},
                domain="abuse",
                domain_event_id=bucket.id,
            )
        else:
            emit_event(
                db,
                level="warning",
                category="security",
                event_type="webhook_abuse.failure_recorded",
                message="Failed webhook attempt was recorded for abuse tracking.",
                source={"ip": client_host},
                security={"severity": "low", "reason": reason},
                target={"type": "webhook", "scope": scope, "route_fingerprint": (route_token_hash or "")[:12]},
                domain="abuse",
                domain_event_id=bucket.id,
            )
        buckets.append(bucket)

    db.flush()
    return buckets


def record_success(db: Session, *, client_host: str, route_token_hash: str | None) -> None:
    if not route_token_hash:
        return
    settings = get_effective_settings()
    if not settings.webhook_abuse_blocking_enabled:
        return

    now = utcnow()
    bucket = _find_bucket(db, client_host=client_host, scope=SCOPE_IP_ROUTE, route_token_hash=route_token_hash)
    if bucket is None:
        return
    bucket.failure_count = 0
    bucket.window_started_at = now
    bucket.blocked_until = None
    bucket.last_client_host = _stored_client_host(client_host)
    bucket.last_seen_at = now
    db.flush()


def unblock_bucket(db: Session, bucket_id: str) -> WebhookAbuseBucket | None:
    bucket = db.get(WebhookAbuseBucket, bucket_id)
    if bucket is None:
        return None
    now = utcnow()
    bucket.failure_count = 0
    bucket.blocked_until = None
    bucket.window_started_at = now
    bucket.last_seen_at = now
    db.flush()
    emit_event(
        db,
        level="info",
        category="security",
        event_type="webhook_abuse.client_unblocked",
        message="Webhook abuse bucket was manually unblocked.",
        source={"ip": bucket.last_client_host},
        target={"type": "webhook", "scope": bucket.scope, "route_fingerprint": (bucket.route_token_hash or "")[:12]},
        security={"severity": "low", "reason": "manual_unblock"},
        domain="abuse",
        domain_event_id=bucket.id,
    )
    return bucket


def cleanup_buckets(db: Session) -> WebhookAbuseCleanupResult:
    settings = get_effective_settings()
    cutoff = utcnow() - timedelta(days=settings.webhook_abuse_cleanup_days)
    result = db.execute(
        delete(WebhookAbuseBucket).where(
            WebhookAbuseBucket.last_seen_at < cutoff,
            WebhookAbuseBucket.blocked_until.is_(None),
        )
    )
    deleted = result.rowcount or 0
    if deleted:
        emit_event(
            db,
            level="info",
            category="security",
            event_type="webhook_abuse.cleanup",
            message="Inactive webhook abuse buckets were cleaned up.",
            raw={"deleted": deleted, "cutoff": cutoff.isoformat()},
            domain="abuse",
        )
    return WebhookAbuseCleanupResult(deleted=deleted, cutoff=cutoff)


def _load_buckets(db: Session, *, client_host: str, route_token_hash: str | None) -> list[WebhookAbuseBucket]:
    client_hash = _client_hash(client_host)
    keys = [_bucket_key(scope, client_hash, scoped_route_token_hash) for scope, scoped_route_token_hash in _bucket_scopes(route_token_hash)]
    return db.scalars(select(WebhookAbuseBucket).where(WebhookAbuseBucket.bucket_key.in_(keys))).all()


def _get_or_create_bucket(
    db: Session,
    *,
    client_host: str,
    scope: str,
    route_token_hash: str | None,
    now,
) -> WebhookAbuseBucket:
    bucket = _find_bucket(db, client_host=client_host, scope=scope, route_token_hash=route_token_hash)
    if bucket is not None:
        return bucket

    client_hash = _client_hash(client_host)
    bucket = WebhookAbuseBucket(
        bucket_key=_bucket_key(scope, client_hash, route_token_hash),
        scope=scope,
        client_hash=client_hash,
        last_client_host=_stored_client_host(client_host),
        route_token_hash=route_token_hash,
        window_started_at=now,
        last_seen_at=now,
    )
    db.add(bucket)
    db.flush()
    return bucket


def _find_bucket(
    db: Session,
    *,
    client_host: str,
    scope: str,
    route_token_hash: str | None,
) -> WebhookAbuseBucket | None:
    client_hash = _client_hash(client_host)
    key = _bucket_key(scope, client_hash, route_token_hash)
    return db.scalar(select(WebhookAbuseBucket).where(WebhookAbuseBucket.bucket_key == key))


def _bucket_scopes(route_token_hash: str | None) -> list[tuple[str, str | None]]:
    scopes = [(SCOPE_IP, None)]
    if route_token_hash:
        scopes.append((SCOPE_IP_ROUTE, route_token_hash))
    return scopes


def _client_hash(client_host: str) -> str:
    settings = get_effective_settings()
    secret = settings.ensure_session_secret()
    return hmac.new(secret.encode("utf-8"), client_host.encode("utf-8"), hashlib.sha256).hexdigest()


def _bucket_key(scope: str, client_hash: str, route_token_hash: str | None) -> str:
    return hashlib.sha256(f"{scope}:{client_hash}:{route_token_hash or ''}".encode("utf-8")).hexdigest()


def _stored_client_host(client_host: str) -> str:
    return client_host.strip()[:255]


def _block_duration(block_count: int) -> timedelta:
    settings = get_effective_settings()
    if block_count <= 1:
        minutes = settings.webhook_abuse_initial_block_minutes
    elif block_count == 2:
        minutes = 60
    else:
        minutes = min(settings.webhook_abuse_max_block_minutes, 60 * (2 ** (block_count - 2)))
    return timedelta(minutes=min(minutes, settings.webhook_abuse_max_block_minutes))
