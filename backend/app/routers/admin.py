from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import get_db
from app.deps import require_admin, require_csrf
from app.models import AuditEvent, BotActivityEvent, User
from app.schemas import (
    AdminReadinessOut,
    AuditEventOut,
    BotReadinessOut,
    GraphReadinessOut,
    LogCleanupOut,
    RuntimeReadinessOut,
    SystemLogEventOut,
    UserOut,
)
from app.security import loads_json
from app.services.log_retention import cleanup_log_events

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_csrf)])
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(
        select(User)
        .where(User.organization_id == admin.organization_id)
        .order_by(User.created_at.desc())
    ).all()


@router.get("/readiness", response_model=AdminReadinessOut, dependencies=[Depends(require_csrf)])
def readiness(admin: User = Depends(require_admin)):
    _ = admin
    settings = get_settings()
    delivery_mode = settings.bot_delivery_mode_normalized
    bot_credentials_configured = all(
        value.strip()
        for value in [settings.bot_tenant_id, settings.bot_client_id, settings.bot_client_secret]
    )
    bot_ready = delivery_mode == "mock" or bot_credentials_configured
    if delivery_mode == "mock":
        bot_message = "Mock delivery is active. Teams messages are simulated."
    elif bot_ready:
        bot_message = "Bot Framework credentials are configured for real Teams delivery."
    else:
        bot_message = "Real delivery requires BOT_TENANT_ID, BOT_CLIENT_ID and BOT_CLIENT_SECRET."

    graph_credentials_configured = all(
        value.strip()
        for value in [settings.graph_tenant_id, settings.graph_client_id, settings.graph_client_secret]
    )
    if graph_credentials_configured:
        graph_source = "graph"
        graph_message = "Microsoft Graph credentials are configured for target search and name resolution."
    elif bot_credentials_configured:
        graph_source = "bot"
        graph_message = "Microsoft Graph will reuse the Bot app registration credentials."
    else:
        graph_source = "missing"
        graph_message = "Graph target search requires Graph credentials or reusable Bot credentials."

    return AdminReadinessOut(
        app_name=settings.app_name,
        app_version=settings.app_version,
        delivery_mode=delivery_mode,
        bot=BotReadinessOut(
            ready=bot_ready,
            mode=delivery_mode,
            credentials_configured=bot_credentials_configured,
            default_service_url_configured=bool(settings.bot_default_service_url.strip()),
            message=bot_message,
        ),
        graph=GraphReadinessOut(
            ready=graph_credentials_configured or bot_credentials_configured,
            configured=graph_credentials_configured or bot_credentials_configured,
            credential_source=graph_source,
            message=graph_message,
        ),
        runtime=RuntimeReadinessOut(
            app_public_base_url=settings.app_public_base_url,
            frontend_base_url=settings.frontend_base_url,
            cors_origins=settings.cors_origin_list,
            webhook_max_payload_bytes=settings.webhook_max_payload_bytes,
            log_retention_days=settings.log_retention_days,
            log_cleanup_interval_minutes=settings.log_cleanup_interval_minutes,
            session_secure_cookie=settings.session_secure_cookie,
        ),
    )


@router.get("/logs", response_model=list[AuditEventOut], dependencies=[Depends(require_csrf)])
def list_logs(
    limit: int = Query(default=100, ge=1, le=250),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cleanup_result = cleanup_log_events(db)
    if not cleanup_result.skipped:
        db.commit()
    rows = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.organization_id == admin.organization_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    ).all()
    return [
        AuditEventOut(
            id=row.id,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            action=row.action,
            metadata=loads_json(row.metadata_json, {}),
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/system-logs", response_model=list[SystemLogEventOut], dependencies=[Depends(require_csrf)])
def list_system_logs(
    limit: int = Query(default=100, ge=1, le=250),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    cleanup_result = cleanup_log_events(db)
    if not cleanup_result.skipped:
        db.commit()
    rows = db.scalars(select(BotActivityEvent).order_by(BotActivityEvent.created_at.desc()).limit(limit)).all()
    return [
        SystemLogEventOut(
            id=row.id,
            activity_type=row.activity_type,
            conversation_type=row.conversation_type,
            scope=_system_scope(row),
            team_name=row.team_name,
            channel_name=row.channel_name,
            user_name=row.user_name,
            service_url=row.service_url,
            conversation_id=row.conversation_id,
            tenant_id=row.tenant_id,
            team_id=row.team_id,
            graph_team_id=row.graph_team_id,
            channel_id=row.channel_id,
            graph_user_id=row.graph_user_id,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/logs/cleanup", response_model=LogCleanupOut, dependencies=[Depends(require_csrf)])
def cleanup_logs(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = admin
    cleanup_result = cleanup_log_events(db, force=True)
    db.commit()
    return LogCleanupOut(
        deleted=cleanup_result.deleted,
        deleted_webhook_delivery_events=cleanup_result.deleted_webhook_delivery_events,
        deleted_audit_events=cleanup_result.deleted_audit_events,
        deleted_bot_activity_events=cleanup_result.deleted_bot_activity_events,
        retention_days=cleanup_result.retention_days,
        cutoff=cleanup_result.cutoff,
    )


def _system_scope(event: BotActivityEvent) -> str:
    if event.conversation_type == "personal":
        return "user"
    if event.team_id and event.channel_id:
        return "channel"
    if event.team_id:
        return "team"
    return event.conversation_type or "unknown"
