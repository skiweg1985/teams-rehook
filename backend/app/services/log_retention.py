from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.settings_overrides import get_effective_settings
from app.models import AuditEvent, BotActivityEvent, EventLogEntry, WebhookDeliveryEvent
from app.security import utcnow

_last_log_cleanup_at: datetime | None = None


@dataclass(frozen=True)
class CleanupResult:
    deleted_webhook_delivery_events: int
    deleted_audit_events: int
    deleted_bot_activity_events: int
    deleted_event_log_entries: int
    retention_days: int
    cutoff: datetime
    skipped: bool = False

    @property
    def deleted(self) -> int:
        return (
            self.deleted_webhook_delivery_events
            + self.deleted_audit_events
            + self.deleted_bot_activity_events
            + self.deleted_event_log_entries
        )


def cleanup_log_events(db: Session, *, force: bool = False) -> CleanupResult:
    global _last_log_cleanup_at

    settings = get_effective_settings()
    retention_days = max(0, settings.log_retention_days)
    interval_minutes = max(1, settings.log_cleanup_interval_minutes)
    now = utcnow()
    cutoff = now - timedelta(days=retention_days)

    if not force and _last_log_cleanup_at is not None:
        next_allowed = _last_log_cleanup_at + timedelta(minutes=interval_minutes)
        if next_allowed > now:
            return CleanupResult(
                deleted_webhook_delivery_events=0,
                deleted_audit_events=0,
                deleted_bot_activity_events=0,
                deleted_event_log_entries=0,
                retention_days=retention_days,
                cutoff=cutoff,
                skipped=True,
            )

    delivery_result = db.execute(delete(WebhookDeliveryEvent).where(WebhookDeliveryEvent.created_at < cutoff))
    audit_result = db.execute(delete(AuditEvent).where(AuditEvent.created_at < cutoff))
    bot_activity_result = db.execute(delete(BotActivityEvent).where(BotActivityEvent.created_at < cutoff))
    event_log_result = db.execute(delete(EventLogEntry).where(EventLogEntry.created_at < cutoff))
    _last_log_cleanup_at = now
    return CleanupResult(
        deleted_webhook_delivery_events=delivery_result.rowcount or 0,
        deleted_audit_events=audit_result.rowcount or 0,
        deleted_bot_activity_events=bot_activity_result.rowcount or 0,
        deleted_event_log_entries=event_log_result.rowcount or 0,
        retention_days=retention_days,
        cutoff=cutoff,
    )
