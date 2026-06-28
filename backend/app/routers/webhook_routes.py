from __future__ import annotations

import ipaddress
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.settings_overrides import get_effective_settings
from app.database import get_db
from app.deps import record_audit, require_admin, require_csrf
from app.models import User, WebhookDeliveryEvent, WebhookRoute
from app.schemas import (
    WebhookDeliveryOut,
    WebhookDeliveryEventOut,
    WebhookDeliveryEventDetailOut,
    WebhookDeliveryEventPageOut,
    WebhookDeliveryEventSummaryOut,
    LogCleanupOut,
    WebhookRouteDefaultsOut,
    WebhookRouteCreate,
    WebhookRouteCreatedOut,
    WebhookRouteNameRefreshOut,
    WebhookRouteOut,
    WebhookRouteTestRequest,
    WebhookRouteUpdate,
)
from app.security import dumps_json, issue_plain_secret, loads_json, lookup_secret_hash, utcnow
from app.services.graph_delegated_lookup import GraphDelegatedLookupError, create_or_get_one_on_one_chat
from app.services.graph_name_resolution import refresh_graph_names, resolve_route_graph_names, try_resolve_route_graph_names
from app.services.graph_targets import GraphConfigError, GraphRequestError
from app.services.log_retention import cleanup_log_events
from app.services.teams_bot import BotDeliveryError, send_bot_activity
from app.services.teams_graph_delivery import GraphDeliveryError, send_graph_message
from app.services.client_ip_allowlist import (
    CLIENT_IP_ACCESS_PUBLIC,
    CLIENT_IP_ACCESS_RESTRICTED,
    client_ip_allowed,
    normalize_client_ip_access_mode,
    normalize_client_ip_allowlist,
)
from app.services.webhook_abuse import BLOCKED_WEBHOOK_DETAIL, check_block, record_failure, record_success
from app.services.webhook_payloads import NormalizedMessage, WebhookPayloadError, normalize_webhook_payload, payload_preview

router = APIRouter(tags=["webhook-routes"])

DeliveryStatusFilter = Literal["delivered", "failed", "rejected"]
DELIVERY_BACKEND_BOT = "bot_framework"
DELIVERY_BACKEND_GRAPH = "graph"
ABUSE_REASON_BACKEND_DISABLED = "delivery_backend_disabled"
ABUSE_REASON_INVALID_PAYLOAD = "invalid_payload"
ABUSE_REASON_CLIENT_IP_NOT_ALLOWED = "client_ip_not_allowed"
ABUSE_REASON_PAYLOAD_TOO_LARGE = "payload_too_large"
ABUSE_REASON_ROUTE_DISABLED = "route_disabled"
ABUSE_REASON_UNKNOWN_ROUTE = "unknown_route"


@router.get("/webhook-routes", response_model=list[WebhookRouteOut])
def list_webhook_routes(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    routes = db.scalars(
        select(WebhookRoute)
        .where(WebhookRoute.organization_id == admin.organization_id)
        .order_by(WebhookRoute.updated_at.desc())
    ).all()
    return [_route_out(route) for route in routes]


@router.get("/webhook-routes/defaults", response_model=WebhookRouteDefaultsOut)
def webhook_route_defaults(admin: User = Depends(require_admin)):
    _ = admin
    settings = get_effective_settings()
    return WebhookRouteDefaultsOut(bot_default_service_url=settings.bot_default_service_url.strip())


@router.post(
    "/webhook-routes",
    response_model=WebhookRouteCreatedOut,
    dependencies=[Depends(require_csrf)],
)
def create_webhook_route(
    payload: WebhookRouteCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    settings = get_effective_settings()
    route_token = issue_plain_secret(24)
    route = WebhookRoute(
        organization_id=admin.organization_id,
        created_by_id=admin.id,
        name=payload.name.strip(),
        is_active=payload.is_active,
        route_token_hash=lookup_secret_hash(route_token),
        route_token=route_token,
        delivery_backend=payload.delivery_backend,
        client_ip_access_mode=payload.client_ip_access_mode,
        client_ip_allowlist=payload.client_ip_allowlist,
        target_type=payload.target_type,
        target_name=payload.target_name.strip(),
        bot_service_url=payload.bot_service_url.strip(),
        bot_conversation_id=payload.bot_conversation_id.strip(),
        graph_target_kind=payload.graph_target_kind or "",
        graph_target_id=payload.graph_target_id.strip(),
        graph_team_id=payload.graph_team_id.strip(),
        graph_team_name=payload.graph_team_name.strip(),
        graph_channel_id=payload.graph_channel_id.strip(),
        graph_user_id=payload.graph_user_id.strip(),
        graph_user_display_name=payload.graph_user_display_name.strip(),
        graph_user_principal_name=payload.graph_user_principal_name.strip(),
        bot_target_source=payload.bot_target_source.strip(),
    )
    _ensure_route_feature_enabled(route, settings)
    _validate_client_ip_access(route)
    _materialize_graph_user_target(db, admin.organization_id, route)
    if settings.graph_lookup_enabled:
        try_resolve_route_graph_names(route)
    _validate_target(route)
    _ensure_route_name_available(db, admin.organization_id, route.name, _route_delivery_backend(route))
    db.add(route)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Webhook route name already exists") from exc
    record_audit(
        db,
        action="webhook_route.created",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"webhook_route_id": route.id, "name": route.name},
    )
    db.commit()
    db.refresh(route)
    return _route_out(route, created=True)


@router.patch("/webhook-routes/{route_id}", response_model=WebhookRouteOut, dependencies=[Depends(require_csrf)])
def update_webhook_route(
    route_id: str,
    payload: WebhookRouteUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    settings = get_effective_settings()
    route = _get_org_route(db, admin.organization_id, route_id)
    _ensure_delivery_backend_feature_enabled(payload.delivery_backend or _route_delivery_backend(route), settings)
    if payload.name is not None:
        route.name = payload.name.strip()
    if payload.is_active is not None:
        route.is_active = payload.is_active
    if payload.delivery_backend is not None:
        route.delivery_backend = payload.delivery_backend
    if payload.client_ip_access_mode is not None:
        route.client_ip_access_mode = payload.client_ip_access_mode
        if payload.client_ip_access_mode == CLIENT_IP_ACCESS_PUBLIC:
            route.client_ip_allowlist = ""
    if payload.client_ip_allowlist is not None:
        route.client_ip_allowlist = payload.client_ip_allowlist
    if payload.target_type is not None:
        route.target_type = payload.target_type
    if payload.target_name is not None:
        route.target_name = payload.target_name.strip()
    if payload.bot_service_url is not None:
        route.bot_service_url = payload.bot_service_url.strip()
    if payload.bot_conversation_id is not None:
        route.bot_conversation_id = payload.bot_conversation_id.strip()
    if payload.graph_target_kind is not None:
        route.graph_target_kind = payload.graph_target_kind
    if payload.graph_target_id is not None:
        route.graph_target_id = payload.graph_target_id.strip()
    if payload.graph_team_id is not None:
        route.graph_team_id = payload.graph_team_id.strip()
    if payload.graph_team_name is not None:
        route.graph_team_name = payload.graph_team_name.strip()
    if payload.graph_channel_id is not None:
        route.graph_channel_id = payload.graph_channel_id.strip()
    if payload.graph_user_id is not None:
        route.graph_user_id = payload.graph_user_id.strip()
    if payload.graph_user_display_name is not None:
        route.graph_user_display_name = payload.graph_user_display_name.strip()
    if payload.graph_user_principal_name is not None:
        route.graph_user_principal_name = payload.graph_user_principal_name.strip()
    if payload.bot_target_source is not None:
        route.bot_target_source = payload.bot_target_source.strip()
    _ensure_route_feature_enabled(route, settings)
    _validate_client_ip_access(route)
    _materialize_graph_user_target(db, admin.organization_id, route)
    if settings.graph_lookup_enabled:
        try_resolve_route_graph_names(route)
    _validate_target(route)
    _ensure_route_name_available(db, admin.organization_id, route.name, _route_delivery_backend(route), route_id=route.id)
    record_audit(
        db,
        action="webhook_route.updated",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"webhook_route_id": route.id},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Webhook route name already exists") from exc
    db.refresh(route)
    return _route_out(route)


@router.post("/webhook-routes/refresh-graph-names", response_model=WebhookRouteNameRefreshOut, dependencies=[Depends(require_csrf)])
def refresh_webhook_route_graph_names(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ensure_graph_lookup_enabled()
    result = refresh_graph_names(db, organization_id=admin.organization_id)
    if result.error:
        db.rollback()
        return WebhookRouteNameRefreshOut(
            ok=False,
            routes_checked=result.routes_checked,
            routes_updated=result.routes_updated,
            references_checked=result.references_checked,
            references_updated=result.references_updated,
            error=result.error,
        )
    record_audit(
        db,
        action="webhook_route.graph_names_refreshed",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={
            "routes_checked": result.routes_checked,
            "routes_updated": result.routes_updated,
            "references_checked": result.references_checked,
            "references_updated": result.references_updated,
        },
    )
    db.commit()
    return WebhookRouteNameRefreshOut(
        routes_checked=result.routes_checked,
        routes_updated=result.routes_updated,
        references_checked=result.references_checked,
        references_updated=result.references_updated,
    )


@router.post("/webhook-routes/{route_id}/refresh-graph-names", response_model=WebhookRouteNameRefreshOut, dependencies=[Depends(require_csrf)])
def refresh_single_webhook_route_graph_names(
    route_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    route = _get_org_route(db, admin.organization_id, route_id)
    _ensure_graph_lookup_enabled()
    try:
        updated = resolve_route_graph_names(route, force=True)
    except (GraphConfigError, GraphRequestError) as exc:
        db.rollback()
        return WebhookRouteNameRefreshOut(ok=False, routes_checked=1, error=str(exc))
    record_audit(
        db,
        action="webhook_route.graph_names_refreshed",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"webhook_route_id": route.id, "name": route.name, "routes_updated": 1 if updated else 0},
    )
    db.commit()
    return WebhookRouteNameRefreshOut(routes_checked=1, routes_updated=1 if updated else 0)


@router.delete("/webhook-routes/{route_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
def delete_webhook_route(
    route_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    route = _get_org_route(db, admin.organization_id, route_id)
    db.execute(update(WebhookDeliveryEvent).where(WebhookDeliveryEvent.route_id == route.id).values(route_id=None))
    record_audit(
        db,
        action="webhook_route.deleted",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"webhook_route_id": route.id, "name": route.name},
    )
    db.delete(route)
    db.commit()
    return None


@router.post("/webhook-routes/{route_id}/regenerate-url", response_model=WebhookRouteCreatedOut, dependencies=[Depends(require_csrf)])
def regenerate_webhook_route_url(
    route_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    route = _get_org_route(db, admin.organization_id, route_id)
    route_token = issue_plain_secret(24)
    route.route_token = route_token
    route.route_token_hash = lookup_secret_hash(route_token)
    record_audit(
        db,
        action="webhook_route.url_regenerated",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"webhook_route_id": route.id, "name": route.name},
    )
    db.commit()
    db.refresh(route)
    return _route_out(route, created=True)


@router.get("/webhook-routes/{route_id}/deliveries", response_model=list[WebhookDeliveryEventOut])
def list_webhook_route_deliveries(
    route_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    status_filter: DeliveryStatusFilter | None = Query(default=None, alias="status"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    route = _get_org_route(db, admin.organization_id, route_id)
    query = select(WebhookDeliveryEvent).where(WebhookDeliveryEvent.route_id == route.id)
    if status_filter:
        query = query.where(WebhookDeliveryEvent.status == status_filter)
    events = db.scalars(query.order_by(WebhookDeliveryEvent.created_at.desc()).limit(limit)).all()
    return [_delivery_event_out(event) for event in events]


@router.get("/webhook-delivery-events", response_model=WebhookDeliveryEventPageOut)
def list_webhook_delivery_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    status_filter: DeliveryStatusFilter | None = Query(default=None, alias="status"),
    route_id: str | None = Query(default=None),
    q: str = Query(default="", max_length=200),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cleanup_result = cleanup_log_events(db)
    if not cleanup_result.skipped:
        db.commit()

    filters = [WebhookDeliveryEvent.organization_id == admin.organization_id]
    if route_id:
        route = _get_org_route(db, admin.organization_id, route_id)
        filters.append(WebhookDeliveryEvent.route_id == route.id)
    if status_filter:
        filters.append(WebhookDeliveryEvent.status == status_filter)
    search = q.strip()
    if search:
        pattern = f"%{search}%"
        filters.append(
            or_(
                WebhookDeliveryEvent.error.ilike(pattern),
                WebhookDeliveryEvent.request_metadata_json.ilike(pattern),
                WebhookDeliveryEvent.normalized_message_json.ilike(pattern),
                WebhookDeliveryEvent.delivery_result_json.ilike(pattern),
                WebhookRoute.name.ilike(pattern),
                WebhookRoute.target_name.ilike(pattern),
            )
        )

    total = (
        db.scalar(
            select(func.count())
            .select_from(WebhookDeliveryEvent)
            .outerjoin(WebhookRoute, WebhookDeliveryEvent.route_id == WebhookRoute.id)
            .where(*filters)
        )
        or 0
    )
    offset = (page - 1) * page_size
    rows = db.execute(
        select(WebhookDeliveryEvent, WebhookRoute)
        .outerjoin(WebhookRoute, WebhookDeliveryEvent.route_id == WebhookRoute.id)
        .where(*filters)
        .order_by(WebhookDeliveryEvent.created_at.desc())
        .offset(offset)
        .limit(page_size)
    ).all()
    return WebhookDeliveryEventPageOut(
        items=[_delivery_event_summary_out(event, route) for event, route in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
        retention_days=cleanup_result.retention_days,
    )


@router.get("/webhook-delivery-events/{event_id}", response_model=WebhookDeliveryEventDetailOut)
def get_webhook_delivery_event(
    event_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(WebhookDeliveryEvent, WebhookRoute)
        .outerjoin(WebhookRoute, WebhookDeliveryEvent.route_id == WebhookRoute.id)
        .where(WebhookDeliveryEvent.id == event_id, WebhookDeliveryEvent.organization_id == admin.organization_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery event not found")
    event, route = row
    return _delivery_event_detail_out(event, route)


@router.post(
    "/webhook-delivery-events/cleanup",
    response_model=LogCleanupOut,
    dependencies=[Depends(require_csrf)],
)
def cleanup_log_event_retention(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
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


@router.post("/webhook-routes/{route_id}/test", response_model=WebhookDeliveryOut, dependencies=[Depends(require_csrf)])
def test_webhook_route(
    route_id: str,
    payload: WebhookRouteTestRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    route = _get_org_route(db, admin.organization_id, route_id)
    _ensure_route_feature_enabled(route, get_effective_settings())
    message = NormalizedMessage(
        title=payload.title.strip(),
        text=payload.text.strip(),
        severity=payload.severity.strip().lower() or "info",
        raw_type="test",
    )
    delivery = _deliver_to_route(db, route, message, request_metadata=_manual_test_metadata(route))
    record_audit(
        db,
        action="webhook_route.tested",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"webhook_route_id": route.id, "status": delivery.status},
    )
    db.commit()
    if delivery.status == "failed":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=delivery.error)
    return WebhookDeliveryOut(
        ok=True,
        status="delivered",
        route_id=route.id,
        delivery_event_id=delivery.id,
        message="Test message delivered",
    )


@router.post("/webhooks/{route_token}", response_model=WebhookDeliveryOut)
async def receive_webhook(route_token: str, request: Request, db: Session = Depends(get_db)):
    settings = get_effective_settings()
    token_hash = lookup_secret_hash(route_token)
    client_host, _, _, _ = _resolve_client_host(request)
    block = check_block(db, client_host=client_host, route_token_hash=token_hash)
    if block is not None:
        db.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=BLOCKED_WEBHOOK_DETAIL)

    body = await request.body()
    if len(body) > settings.webhook_max_payload_bytes:
        record_failure(db, client_host=client_host, route_token_hash=token_hash, reason=ABUSE_REASON_PAYLOAD_TOO_LARGE)
        event = _record_event(
            db,
            route=None,
            route_token_hash=token_hash,
            status_value="rejected",
            request_metadata=_request_metadata(request, body),
            error=f"Payload exceeds {settings.webhook_max_payload_bytes} bytes",
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=event.error)

    route = db.scalar(select(WebhookRoute).where(WebhookRoute.route_token_hash == token_hash))
    if not route:
        record_failure(db, client_host=client_host, route_token_hash=None, reason=ABUSE_REASON_UNKNOWN_ROUTE)
        _record_event(
            db,
            route=None,
            route_token_hash=token_hash,
            status_value="rejected",
            request_metadata=_request_metadata(request, body),
            error="Unknown webhook route",
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook route not found")
    if not route.is_active:
        record_failure(db, client_host=client_host, route_token_hash=token_hash, reason=ABUSE_REASON_ROUTE_DISABLED)
        event = _record_event(
            db,
            route=route,
            route_token_hash=token_hash,
            status_value="rejected",
            request_metadata=_request_metadata(request, body),
            error="Webhook route is disabled",
        )
        route.last_delivery_status = "rejected"
        route.last_delivery_at = utcnow()
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=event.error)
    disabled_message = _route_feature_disabled_message(route, settings)
    if disabled_message:
        record_failure(db, client_host=client_host, route_token_hash=token_hash, reason=ABUSE_REASON_BACKEND_DISABLED)
        event = _record_event(
            db,
            route=route,
            route_token_hash=token_hash,
            status_value="rejected",
            request_metadata=_request_metadata(request, body),
            error=disabled_message,
        )
        route.last_delivery_status = "rejected"
        route.last_delivery_at = utcnow()
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=event.error)
    if not _route_allows_client_ip(route, client_host):
        record_failure(db, client_host=client_host, route_token_hash=token_hash, reason=ABUSE_REASON_CLIENT_IP_NOT_ALLOWED)
        event = _record_event(
            db,
            route=route,
            route_token_hash=token_hash,
            status_value="rejected",
            request_metadata=_request_metadata(request, body),
            error="Client IP is not allowed for this webhook route",
        )
        route.last_delivery_status = "rejected"
        route.last_delivery_at = utcnow()
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=event.error)

    try:
        message = normalize_webhook_payload(body, request.headers.get("content-type"))
    except WebhookPayloadError as exc:
        record_failure(db, client_host=client_host, route_token_hash=token_hash, reason=ABUSE_REASON_INVALID_PAYLOAD)
        event = _record_event(
            db,
            route=route,
            route_token_hash=token_hash,
            status_value="rejected",
            request_metadata=_request_metadata(request, body),
            error=str(exc),
        )
        route.last_delivery_status = "rejected"
        route.last_delivery_at = utcnow()
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=event.error) from exc

    record_success(db, client_host=client_host, route_token_hash=token_hash)
    delivery = _deliver_to_route(db, route, message, request_metadata=_request_metadata(request, body))
    db.commit()
    if delivery.status == "failed":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=delivery.error)
    return WebhookDeliveryOut(
        ok=True,
        status="delivered",
        route_id=route.id,
        delivery_event_id=delivery.id,
        message="Webhook delivered",
    )


def _get_org_route(db: Session, organization_id: str, route_id: str) -> WebhookRoute:
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.id == route_id, WebhookRoute.organization_id == organization_id))
    if not route:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook route not found")
    return route


def _materialize_graph_user_target(db: Session, organization_id: str, route: WebhookRoute) -> None:
    if _route_delivery_backend(route) != DELIVERY_BACKEND_GRAPH or (route.graph_target_kind or "").strip() != "user":
        return
    user_id = route.graph_user_id.strip() or route.graph_target_id.strip()
    if not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Graph one-on-one routes require a user ID")
    try:
        chat = create_or_get_one_on_one_chat(
            db,
            organization_id=organization_id,
            user_id=user_id,
            user_display_name=route.graph_user_display_name or route.target_name,
            user_principal_name=route.graph_user_principal_name,
        )
    except GraphDelegatedLookupError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    route.graph_target_kind = "chat"
    route.graph_target_id = chat.id
    route.graph_user_id = chat.user_id
    route.graph_user_display_name = chat.user_display_name
    route.graph_user_principal_name = chat.user_principal_name
    route.graph_team_id = ""
    route.graph_team_name = ""
    route.graph_channel_id = ""
    route.bot_service_url = ""
    route.bot_conversation_id = ""
    if not route.bot_target_source.strip():
        route.bot_target_source = "graph_user_lookup"


def _ensure_graph_lookup_enabled() -> None:
    if not get_effective_settings().graph_lookup_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Microsoft Graph lookup is disabled")


def _ensure_route_feature_enabled(route: WebhookRoute, settings) -> None:
    message = _delivery_backend_disabled_message(_route_delivery_backend(route), settings)
    if message:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _route_feature_disabled_message(route: WebhookRoute, settings) -> str:
    return _delivery_backend_disabled_message(_route_delivery_backend(route), settings)


def _ensure_delivery_backend_feature_enabled(backend: str, settings) -> None:
    message = _delivery_backend_disabled_message(backend, settings)
    if message:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _delivery_backend_disabled_message(backend: str, settings) -> str:
    if backend == DELIVERY_BACKEND_BOT and not settings.bot_framework_enabled:
        return "Bot Framework delivery is disabled"
    if backend == DELIVERY_BACKEND_GRAPH:
        if not settings.graph_lookup_enabled:
            return "Microsoft Graph delivery requires Graph lookup to be enabled"
        if not settings.graph_delivery_enabled:
            return "Microsoft Graph delivery is disabled"
    return ""


def _validate_target(route: WebhookRoute) -> None:
    backend = _route_delivery_backend(route)
    if backend not in {DELIVERY_BACKEND_BOT, DELIVERY_BACKEND_GRAPH}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported delivery backend")
    if route.target_type != "bot_conversation":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported target type")
    if not route.target_name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target name is required")
    if backend == DELIVERY_BACKEND_BOT and (not route.bot_service_url.strip() or not route.bot_conversation_id.strip()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bot service URL and conversation ID are required")
    if backend == DELIVERY_BACKEND_GRAPH:
        kind = (route.graph_target_kind or "").strip()
        if kind == "channel" and (not route.graph_team_id.strip() or not route.graph_channel_id.strip()):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Graph channel routes require a team ID and channel ID")
        if kind == "chat" and not route.graph_target_id.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Graph chat routes require an existing chat ID")
        if kind not in {"channel", "chat"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Graph delivery supports channel and existing chat targets in V1")


def _validate_client_ip_access(route: WebhookRoute) -> None:
    try:
        route.client_ip_access_mode = normalize_client_ip_access_mode(route.client_ip_access_mode)
        route.client_ip_allowlist = normalize_client_ip_allowlist(route.client_ip_allowlist or "")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if route.client_ip_access_mode == CLIENT_IP_ACCESS_PUBLIC:
        route.client_ip_allowlist = ""
        return
    if route.client_ip_access_mode == CLIENT_IP_ACCESS_RESTRICTED and not route.client_ip_allowlist:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Restricted routes require at least one client IP or CIDR range")


def _route_allows_client_ip(route: WebhookRoute, client_host: str) -> bool:
    try:
        mode = normalize_client_ip_access_mode(route.client_ip_access_mode)
    except ValueError:
        mode = CLIENT_IP_ACCESS_PUBLIC
    if mode == CLIENT_IP_ACCESS_PUBLIC:
        return True
    return client_ip_allowed(client_host, route.client_ip_allowlist or "")


def _ensure_route_name_available(
    db: Session,
    organization_id: str,
    name: str,
    delivery_backend: str,
    *,
    route_id: str | None = None,
) -> None:
    statement = select(WebhookRoute.id).where(
        WebhookRoute.organization_id == organization_id,
        WebhookRoute.name == name,
        WebhookRoute.delivery_backend == delivery_backend,
    )
    if route_id:
        statement = statement.where(WebhookRoute.id != route_id)
    if db.scalar(statement):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Webhook route name already exists for this delivery backend",
        )


def _deliver_to_route(
    db: Session,
    route: WebhookRoute,
    message: NormalizedMessage,
    *,
    request_metadata: dict,
) -> WebhookDeliveryEvent:
    backend = _route_delivery_backend(route)
    if backend == DELIVERY_BACKEND_GRAPH:
        try:
            result = send_graph_message(db, organization_id=route.organization_id, route=route, message=message)
            route.last_delivery_status = "delivered"
            route.last_delivery_at = utcnow()
            return _record_event(
                db,
                route=route,
                route_token_hash=route.route_token_hash,
                status_value="delivered",
                request_metadata=request_metadata,
                normalized_message=message.to_dict(),
                delivery_result=result.to_dict(),
            )
        except GraphDeliveryError as exc:
            return _record_failed_delivery(
                db,
                route,
                message,
                request_metadata,
                str(exc),
                delivery_result=exc.result or {"backend": DELIVERY_BACKEND_GRAPH, "error_type": exc.error_type},
            )
    if backend != DELIVERY_BACKEND_BOT:
        return _record_failed_delivery(
            db,
            route,
            message,
            request_metadata,
            f"Unsupported delivery backend: {backend}",
            delivery_result={"backend": backend},
        )
    try:
        result = send_bot_activity(
            service_url=route.bot_service_url,
            conversation_id=route.bot_conversation_id,
            message=message,
        )
        delivery_result = result.to_dict()
        delivery_result["backend"] = DELIVERY_BACKEND_BOT
        route.last_delivery_status = "delivered"
        route.last_delivery_at = utcnow()
        return _record_event(
            db,
            route=route,
            route_token_hash=route.route_token_hash,
            status_value="delivered",
            request_metadata=request_metadata,
            normalized_message=message.to_dict(),
            delivery_result=delivery_result,
        )
    except BotDeliveryError as exc:
        return _record_failed_delivery(
            db,
            route,
            message,
            request_metadata,
            str(exc),
            delivery_result={"backend": DELIVERY_BACKEND_BOT},
        )


def _record_failed_delivery(
    db: Session,
    route: WebhookRoute,
    message: NormalizedMessage,
    request_metadata: dict,
    error: str,
    *,
    delivery_result: dict,
) -> WebhookDeliveryEvent:
    route.last_delivery_status = "failed"
    route.last_delivery_at = utcnow()
    return _record_event(
        db,
        route=route,
        route_token_hash=route.route_token_hash,
        status_value="failed",
        request_metadata=request_metadata,
        normalized_message=message.to_dict(),
        delivery_result=delivery_result,
        error=error,
    )


def _record_event(
    db: Session,
    *,
    route: WebhookRoute | None,
    route_token_hash: str | None,
    status_value: str,
    request_metadata: dict,
    normalized_message: dict | None = None,
    delivery_result: dict | None = None,
    error: str = "",
) -> WebhookDeliveryEvent:
    event = WebhookDeliveryEvent(
        organization_id=route.organization_id if route else None,
        route_id=route.id if route else None,
        route_token_hash=route_token_hash,
        status=status_value,
        request_metadata_json=dumps_json(request_metadata),
        normalized_message_json=dumps_json(normalized_message or {}),
        delivery_result_json=dumps_json(delivery_result or {}),
        error=error[:1000],
    )
    db.add(event)
    db.flush()
    return event


def _request_metadata(request: Request, body: bytes) -> dict:
    client_host, direct_client_host, x_forwarded_for, client_host_source = _resolve_client_host(request)
    return {
        "trigger": "external_webhook",
        "method": request.method,
        "path": request.url.path,
        "content_type": request.headers.get("content-type", ""),
        "content_length": request.headers.get("content-length", str(len(body))),
        "client_host": client_host,
        "direct_client_host": direct_client_host,
        "x_forwarded_for": x_forwarded_for,
        "client_host_source": client_host_source,
        "user_agent": request.headers.get("user-agent", ""),
        "payload_preview": payload_preview(body),
    }


def _resolve_client_host(request: Request) -> tuple[str, str, str, str]:
    direct_client_host = request.client.host if request.client else ""
    x_forwarded_for = request.headers.get("x-forwarded-for", "")
    settings = get_effective_settings()
    trusted_proxy_networks = _trusted_proxy_networks(settings.trusted_proxy_ips)
    if (
        not settings.trust_x_forwarded_for
        or not x_forwarded_for.strip()
        or not _host_in_networks(direct_client_host, trusted_proxy_networks)
    ):
        return direct_client_host, direct_client_host, x_forwarded_for, "direct"

    forwarded_hosts = _forwarded_host_chain(x_forwarded_for)
    if not forwarded_hosts:
        return direct_client_host, direct_client_host, x_forwarded_for, "direct"

    for forwarded_host in reversed(forwarded_hosts):
        if not _ip_in_networks(forwarded_host, trusted_proxy_networks):
            return str(forwarded_host), direct_client_host, x_forwarded_for, "x_forwarded_for"
    return str(forwarded_hosts[0]), direct_client_host, x_forwarded_for, "x_forwarded_for"


def _trusted_proxy_networks(value: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for part in value.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        try:
            networks.append(ipaddress.ip_network(candidate, strict=False))
        except ValueError:
            return []
    return networks


def _forwarded_host_chain(value: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    hosts: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for part in value.split(","):
        candidate = part.strip()
        if not candidate:
            return []
        try:
            hosts.append(ipaddress.ip_address(candidate))
        except ValueError:
            return []
    return hosts


def _host_in_networks(host: str, networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network]) -> bool:
    if not host or not networks:
        return False
    try:
        return _ip_in_networks(ipaddress.ip_address(host), networks)
    except ValueError:
        return False


def _ip_in_networks(
    host: ipaddress.IPv4Address | ipaddress.IPv6Address,
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> bool:
    return any(host in network for network in networks)


def _manual_test_metadata(route: WebhookRoute) -> dict:
    return {
        "trigger": "manual_test",
        "graph_target": {
            "kind": route.graph_target_kind,
            "target_name": route.target_name,
            "target_id": route.graph_target_id,
            "team_id": route.graph_team_id,
            "team_name": route.graph_team_name,
            "channel_id": route.graph_channel_id,
            "user_id": route.graph_user_id,
            "user_display_name": route.graph_user_display_name,
            "user_principal_name": route.graph_user_principal_name,
        },
        "bot_target": {
            "service_url": route.bot_service_url,
            "conversation_id": route.bot_conversation_id,
        },
    }


def _route_out(
    route: WebhookRoute,
    *,
    created: bool = False,
) -> WebhookRouteOut | WebhookRouteCreatedOut:
    webhook_url = _build_webhook_url(route.route_token) if route.route_token else None
    payload = {
        "id": route.id,
        "organization_id": route.organization_id,
        "name": route.name,
        "is_active": route.is_active,
        "delivery_backend": _route_delivery_backend(route),
        "client_ip_access_mode": normalize_client_ip_access_mode(route.client_ip_access_mode),
        "client_ip_allowlist": normalize_client_ip_allowlist(route.client_ip_allowlist or ""),
        "target_type": route.target_type,
        "target_name": route.target_name,
        "bot_service_url": route.bot_service_url,
        "bot_conversation_id": route.bot_conversation_id,
        "graph_target_kind": route.graph_target_kind,
        "graph_target_id": route.graph_target_id,
        "graph_team_id": route.graph_team_id,
        "graph_team_name": route.graph_team_name,
        "graph_channel_id": route.graph_channel_id,
        "graph_user_id": route.graph_user_id,
        "graph_user_display_name": route.graph_user_display_name,
        "graph_user_principal_name": route.graph_user_principal_name,
        "bot_target_source": route.bot_target_source,
        "bot_registered_by_id": route.bot_registered_by_id,
        "bot_registered_at": route.bot_registered_at,
        "webhook_url": webhook_url,
        "webhook_url_available": webhook_url is not None,
        "last_delivery_status": route.last_delivery_status,
        "last_delivery_at": route.last_delivery_at,
        "created_at": route.created_at,
        "updated_at": route.updated_at,
    }
    if created and webhook_url:
        return WebhookRouteCreatedOut(**payload)
    return WebhookRouteOut(**payload)


def _delivery_event_out(event: WebhookDeliveryEvent) -> WebhookDeliveryEventOut:
    return WebhookDeliveryEventOut(
        id=event.id,
        route_id=event.route_id,
        status=event.status,
        request_metadata=loads_json(event.request_metadata_json, {}),
        normalized_message=loads_json(event.normalized_message_json, {}),
        delivery_result=loads_json(event.delivery_result_json, {}),
        error=event.error,
        created_at=event.created_at,
    )


def _delivery_event_summary_out(event: WebhookDeliveryEvent, route: WebhookRoute | None) -> WebhookDeliveryEventSummaryOut:
    normalized_message = loads_json(event.normalized_message_json, {})
    delivery_result = loads_json(event.delivery_result_json, {})
    return WebhookDeliveryEventSummaryOut(
        id=event.id,
        route_id=event.route_id,
        route_name=route.name if route else "",
        target_name=route.target_name if route else "",
        status=event.status,
        title=_string_value(normalized_message, "title"),
        payload_type=_string_value(normalized_message, "raw_type"),
        delivery_backend=_string_value(delivery_result, "backend") or (_route_delivery_backend(route) if route else ""),
        delivery_mode=_string_value(delivery_result, "mode"),
        status_code=_int_value(delivery_result, "status_code"),
        error=event.error,
        created_at=event.created_at,
    )


def _delivery_event_detail_out(event: WebhookDeliveryEvent, route: WebhookRoute | None) -> WebhookDeliveryEventDetailOut:
    base = _delivery_event_out(event)
    return WebhookDeliveryEventDetailOut(
        **base.model_dump(),
        route_name=route.name if route else "",
        target_name=route.target_name if route else "",
    )


def _string_value(record: dict, key: str) -> str:
    value = record.get(key)
    return value.strip() if isinstance(value, str) else ""


def _int_value(record: dict, key: str) -> int | None:
    value = record.get(key)
    return value if isinstance(value, int) else None


def _route_delivery_backend(route: WebhookRoute) -> str:
    value = route.delivery_backend.strip() if isinstance(route.delivery_backend, str) else ""
    return value or DELIVERY_BACKEND_BOT


def _build_webhook_url(route_token: str) -> str:
    settings = get_effective_settings()
    base_url = settings.app_public_base_url.rstrip("/")
    prefix = settings.api_v1_prefix.rstrip("/")
    return f"{base_url}{prefix}/webhooks/{route_token}"
