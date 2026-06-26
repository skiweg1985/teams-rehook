from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import timedelta

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
    OAuthAppDiagnosticsOut,
    OAuthDiagnosticsOut,
    OAuthTenantDiagnosticsOut,
    OAuthTokenDiagnosticsOut,
    RuntimeReadinessOut,
    SystemLogEventOut,
    UserOut,
)
from app.security import loads_json, utcnow
from app.services.graph_targets import GraphConfigError, GraphRequestError
from app.services.log_retention import cleanup_log_events
from app.services.teams_bot import BotDeliveryError

router = APIRouter(prefix="/admin", tags=["admin"])


@dataclass(frozen=True)
class OAuthTokenResponse:
    access_token: str
    expires_in_seconds: int
    claims: dict


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
    oauth = _oauth_diagnostics(
        credential_source="bot",
        tenant_id=settings.bot_tenant_id,
        client_id=settings.bot_client_id,
        scope=settings.botframework_scope,
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
            oauth=oauth,
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
            oauth=oauth,
            message="Real delivery requires BOT_TENANT_ID, BOT_CLIENT_ID and BOT_CLIENT_SECRET.",
        )
    try:
        token_response = _fetch_oauth_token(
            tenant_id=settings.bot_tenant_id,
            client_id=settings.bot_client_id,
            client_secret=settings.bot_client_secret,
            scope=settings.botframework_scope,
            config_error=BotDeliveryError,
            request_error=BotDeliveryError,
            missing_labels={
                "tenant_id": "BOT_TENANT_ID",
                "client_id": "BOT_CLIENT_ID",
                "client_secret": "BOT_CLIENT_SECRET",
            },
        )
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
            oauth=_oauth_diagnostics(
                credential_source="bot",
                tenant_id=settings.bot_tenant_id,
                client_id=settings.bot_client_id,
                scope=settings.botframework_scope,
                token=OAuthTokenDiagnosticsOut(checked=True, succeeded=False),
            ),
            message="Bot Framework token request failed. Check tenant ID, client ID, client secret and app permissions.",
        )
    oauth = _oauth_diagnostics(
        credential_source="bot",
        tenant_id=settings.bot_tenant_id,
        client_id=settings.bot_client_id,
        scope=settings.botframework_scope,
        token=_token_diagnostics(token_response),
        metadata=_metadata_for_credentials(
            tenant_id=settings.bot_tenant_id,
            client_id=settings.bot_client_id,
            client_secret=settings.bot_client_secret,
            scope=settings.graph_scope,
        ),
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
        oauth=oauth,
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
    tenant_id, client_id, client_secret = _graph_credentials(settings)
    oauth = _oauth_diagnostics(
        credential_source=credential_source,
        tenant_id=tenant_id,
        client_id=client_id,
        scope=settings.graph_scope,
    )

    if credential_source == "missing":
        return GraphReadinessOut(
            ready=False,
            auth_status="incomplete",
            token_checked=False,
            token_request_succeeded=False,
            configured=False,
            credential_source=credential_source,
            credential_fields=credential_fields,
            oauth=oauth,
            message="Graph lookup requires dedicated Graph credentials or reusable Bot app credentials.",
        )
    try:
        token_response = _fetch_oauth_token(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            scope=settings.graph_scope,
            config_error=GraphConfigError,
            request_error=GraphRequestError,
            missing_labels={
                "tenant_id": "GRAPH_TENANT_ID or BOT_TENANT_ID",
                "client_id": "GRAPH_CLIENT_ID or BOT_CLIENT_ID",
                "client_secret": "GRAPH_CLIENT_SECRET or BOT_CLIENT_SECRET",
            },
        )
    except GraphConfigError:
        return GraphReadinessOut(
            ready=False,
            auth_status="incomplete",
            token_checked=False,
            token_request_succeeded=False,
            configured=False,
            credential_source="missing",
            credential_fields=credential_fields,
            oauth=oauth,
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
            oauth=_oauth_diagnostics(
                credential_source=credential_source,
                tenant_id=tenant_id,
                client_id=client_id,
                scope=settings.graph_scope,
                token=OAuthTokenDiagnosticsOut(checked=True, succeeded=False),
            ),
            message="Microsoft Graph token request failed. Check credentials, tenant and app permissions.",
        )
    oauth = _oauth_diagnostics(
        credential_source=credential_source,
        tenant_id=tenant_id,
        client_id=client_id,
        scope=settings.graph_scope,
        token=_token_diagnostics(token_response),
        metadata=_metadata_from_graph_token(token_response.access_token, client_id),
    )
    metadata_available = oauth.app.available and oauth.tenant.available
    return GraphReadinessOut(
        ready=True,
        auth_status="ready" if metadata_available else "permission_warning",
        token_checked=True,
        token_request_succeeded=True,
        configured=True,
        credential_source=credential_source,
        credential_fields=credential_fields,
        oauth=oauth,
        message=(
            "Microsoft Graph token request succeeded. Lookup and readiness diagnostics are available."
            if metadata_available
            else "Microsoft Graph token request succeeded. Lookup can still work, but optional directory metadata is limited by tenant permissions."
        ),
    )


def _fetch_oauth_token(
    *,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    scope: str,
    config_error,
    request_error,
    missing_labels: dict[str, str],
) -> OAuthTokenResponse:
    missing = [
        missing_labels[name]
        for name, value in {
            "tenant_id": tenant_id,
            "client_id": client_id,
            "client_secret": client_secret,
        }.items()
        if not value
    ]
    if missing:
        raise config_error(f"Missing OAuth credentials: {', '.join(missing)}")

    form = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise request_error("Failed to fetch OAuth access token") from exc

    access_token = str(body.get("access_token") or "")
    if not access_token:
        raise request_error("OAuth token response did not include an access token")
    return OAuthTokenResponse(
        access_token=access_token,
        expires_in_seconds=int(body.get("expires_in") or 3600),
        claims=_decode_jwt_claims(access_token),
    )


def _oauth_diagnostics(
    *,
    credential_source: str,
    tenant_id: str,
    client_id: str,
    scope: str,
    token: OAuthTokenDiagnosticsOut | None = None,
    metadata: tuple[OAuthAppDiagnosticsOut, OAuthTenantDiagnosticsOut] | None = None,
) -> OAuthDiagnosticsOut:
    app, tenant = metadata or (OAuthAppDiagnosticsOut(), OAuthTenantDiagnosticsOut())
    return OAuthDiagnosticsOut(
        credential_source=credential_source,
        tenant_id=tenant_id,
        client_id=client_id,
        scope=scope,
        token=token or OAuthTokenDiagnosticsOut(),
        app=app,
        tenant=tenant,
    )


def _token_diagnostics(response: OAuthTokenResponse) -> OAuthTokenDiagnosticsOut:
    claims = response.claims
    roles = claims.get("roles") if isinstance(claims.get("roles"), list) else []
    return OAuthTokenDiagnosticsOut(
        checked=True,
        succeeded=True,
        expires_in_seconds=response.expires_in_seconds,
        expires_at=utcnow() + timedelta(seconds=max(response.expires_in_seconds, 1)),
        audience=str(claims.get("aud") or ""),
        issuer=str(claims.get("iss") or ""),
        roles=[str(role) for role in roles],
    )


def _metadata_for_credentials(
    *,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    scope: str,
) -> tuple[OAuthAppDiagnosticsOut, OAuthTenantDiagnosticsOut]:
    try:
        token_response = _fetch_oauth_token(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            scope=scope,
            config_error=GraphConfigError,
            request_error=GraphRequestError,
            missing_labels={
                "tenant_id": "BOT_TENANT_ID",
                "client_id": "BOT_CLIENT_ID",
                "client_secret": "BOT_CLIENT_SECRET",
            },
        )
    except (GraphConfigError, GraphRequestError):
        return (
            OAuthAppDiagnosticsOut(
                metadata_checked=True,
                available=False,
                message="App metadata is not available with the current Graph permissions.",
            ),
            OAuthTenantDiagnosticsOut(
                metadata_checked=True,
                available=False,
                message="Tenant metadata is not available with the current Graph permissions.",
            ),
        )
    return _metadata_from_graph_token(token_response.access_token, client_id)


def _metadata_from_graph_token(access_token: str, client_id: str) -> tuple[OAuthAppDiagnosticsOut, OAuthTenantDiagnosticsOut]:
    return (
        _service_principal_metadata(access_token, client_id),
        _tenant_metadata(access_token),
    )


def _service_principal_metadata(access_token: str, client_id: str) -> OAuthAppDiagnosticsOut:
    try:
        data = _graph_get_with_token(
            access_token,
            "/servicePrincipals",
            {
                "$filter": f"appId eq '{_odata_string(client_id)}'",
                "$select": "id,appId,displayName,servicePrincipalType,accountEnabled,appOwnerOrganizationId",
            },
        )
    except GraphRequestError:
        return OAuthAppDiagnosticsOut(
            metadata_checked=True,
            available=False,
            message="App metadata is not available with the current Graph permissions.",
        )
    values = data.get("value") if isinstance(data.get("value"), list) else []
    app = values[0] if values and isinstance(values[0], dict) else {}
    if not app:
        return OAuthAppDiagnosticsOut(
            metadata_checked=True,
            available=False,
            message="No service principal was found for this client ID.",
        )
    return OAuthAppDiagnosticsOut(
        metadata_checked=True,
        available=True,
        display_name=str(app.get("displayName") or ""),
        app_id=str(app.get("appId") or ""),
        service_principal_id=str(app.get("id") or ""),
        account_enabled=app.get("accountEnabled") if isinstance(app.get("accountEnabled"), bool) else None,
        service_principal_type=str(app.get("servicePrincipalType") or ""),
    )


def _tenant_metadata(access_token: str) -> OAuthTenantDiagnosticsOut:
    try:
        data = _graph_get_with_token(
            access_token,
            "/organization",
            {"$select": "id,displayName,verifiedDomains"},
        )
    except GraphRequestError:
        return OAuthTenantDiagnosticsOut(
            metadata_checked=True,
            available=False,
            message="Tenant metadata is not available with the current Graph permissions.",
        )
    values = data.get("value") if isinstance(data.get("value"), list) else []
    tenant = values[0] if values and isinstance(values[0], dict) else {}
    if not tenant:
        return OAuthTenantDiagnosticsOut(
            metadata_checked=True,
            available=False,
            message="No tenant metadata was returned.",
        )
    domains = tenant.get("verifiedDomains") if isinstance(tenant.get("verifiedDomains"), list) else []
    primary_domain = ""
    for domain in domains:
        if isinstance(domain, dict) and domain.get("isDefault"):
            primary_domain = str(domain.get("name") or "")
            break
    if not primary_domain and domains and isinstance(domains[0], dict):
        primary_domain = str(domains[0].get("name") or "")
    return OAuthTenantDiagnosticsOut(
        metadata_checked=True,
        available=True,
        display_name=str(tenant.get("displayName") or ""),
        primary_domain=primary_domain,
    )


def _graph_get_with_token(access_token: str, path: str, params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"https://graph.microsoft.com/v1.0{path}?{query}",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        _ = exc.read()
        raise GraphRequestError("Microsoft Graph metadata request failed") from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GraphRequestError("Microsoft Graph metadata request failed") from exc


def _decode_jwt_claims(token: str) -> dict:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
        value = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _graph_credentials(settings) -> tuple[str, str, str]:
    return (
        settings.graph_tenant_id or settings.bot_tenant_id,
        settings.graph_client_id or settings.bot_client_id,
        settings.graph_client_secret or settings.bot_client_secret,
    )


def _odata_string(value: str) -> str:
    return value.replace("'", "''")


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
