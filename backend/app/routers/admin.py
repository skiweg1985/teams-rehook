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
from app.services.graph_targets import GraphConfigError, GraphRequestError, fetch_graph_token
from app.services.log_retention import cleanup_log_events
from app.services.teams_bot import BotDeliveryError, fetch_botframework_token

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
    bot = _bot_readiness(settings, delivery_mode)
    graph = _graph_readiness(settings)

    return AdminReadinessOut(
        app_name=settings.app_name,
        app_version=settings.app_version,
        delivery_mode=delivery_mode,
        bot=bot,
        graph=graph,
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


def _bot_readiness(settings, delivery_mode: str) -> BotReadinessOut:
    credential_fields = {
        "tenant_id": _configured_status(settings.bot_tenant_id),
        "client_id": _configured_status(settings.bot_client_id),
        "client_secret": _configured_status(settings.bot_client_secret),
        "default_service_url": _configured_status(settings.bot_default_service_url),
    }
    credentials_configured = all(
        credential_fields[field] == "configured"
        for field in ["tenant_id", "client_id", "client_secret"]
    )
    if delivery_mode == "mock":
        return BotReadinessOut(
            ready=True,
            auth_status="mock",
            token_checked=False,
            token_request_succeeded=False,
            mode=delivery_mode,
            credentials_configured=credentials_configured,
            default_service_url_configured=credential_fields["default_service_url"] == "configured",
            credential_fields=credential_fields,
            message="Mock delivery is active. Token checks are skipped and Teams messages are simulated.",
        )
    if not credentials_configured:
        return BotReadinessOut(
            ready=False,
            auth_status="incomplete",
            token_checked=False,
            token_request_succeeded=False,
            mode=delivery_mode,
            credentials_configured=False,
            default_service_url_configured=credential_fields["default_service_url"] == "configured",
            credential_fields=credential_fields,
            message="Real delivery requires BOT_TENANT_ID, BOT_CLIENT_ID and BOT_CLIENT_SECRET.",
        )
    try:
        fetch_botframework_token(settings)
    except BotDeliveryError:
        return BotReadinessOut(
            ready=False,
            auth_status="token_error",
            token_checked=True,
            token_request_succeeded=False,
            mode=delivery_mode,
            credentials_configured=True,
            default_service_url_configured=credential_fields["default_service_url"] == "configured",
            credential_fields=credential_fields,
            message="Bot Framework token request failed. Check tenant ID, client ID, client secret and app permissions.",
        )
    return BotReadinessOut(
        ready=True,
        auth_status="ready",
        token_checked=True,
        token_request_succeeded=True,
        mode=delivery_mode,
        credentials_configured=True,
        default_service_url_configured=credential_fields["default_service_url"] == "configured",
        credential_fields=credential_fields,
        message="Bot Framework token request succeeded. Delivery still requires a valid Teams conversation reference and bot permissions.",
    )


def _graph_readiness(settings) -> GraphReadinessOut:
    credential_fields = {
        "tenant_id": _graph_field_status(settings.graph_tenant_id, settings.bot_tenant_id),
        "client_id": _graph_field_status(settings.graph_client_id, settings.bot_client_id),
        "client_secret": _graph_field_status(settings.graph_client_secret, settings.bot_client_secret),
    }
    if all(status == "configured" for status in credential_fields.values()):
        credential_source = "graph"
    elif all(status in {"configured", "inherited"} for status in credential_fields.values()):
        credential_source = "bot"
    else:
        credential_source = "missing"

    if credential_source == "missing":
        return GraphReadinessOut(
            ready=False,
            auth_status="incomplete",
            token_checked=False,
            token_request_succeeded=False,
            configured=False,
            credential_source=credential_source,
            credential_fields=credential_fields,
            message="Graph lookup requires dedicated Graph credentials or reusable Bot app credentials.",
        )
    try:
        fetch_graph_token(settings)
    except GraphConfigError:
        return GraphReadinessOut(
            ready=False,
            auth_status="incomplete",
            token_checked=False,
            token_request_succeeded=False,
            configured=False,
            credential_source="missing",
            credential_fields=credential_fields,
            message="Graph lookup credentials are incomplete.",
        )
    except GraphRequestError:
        return GraphReadinessOut(
            ready=False,
            auth_status="token_error",
            token_checked=True,
            token_request_succeeded=False,
            configured=True,
            credential_source=credential_source,
            credential_fields=credential_fields,
            message="Microsoft Graph token request failed. Check credentials, tenant and app permissions.",
        )
    return GraphReadinessOut(
        ready=True,
        auth_status="permission_warning",
        token_checked=True,
        token_request_succeeded=True,
        configured=True,
        credential_source=credential_source,
        credential_fields=credential_fields,
        message="Microsoft Graph token request succeeded. Lookup can still require tenant permissions and admin consent.",
    )


def _configured_status(value: str) -> str:
    return "configured" if value.strip() else "missing"


def _graph_field_status(graph_value: str, bot_value: str) -> str:
    if graph_value.strip():
        return "configured"
    if bot_value.strip():
        return "inherited"
    return "missing"


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
