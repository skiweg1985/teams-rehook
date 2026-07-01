from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.settings_overrides import get_effective_settings
from app.database import get_db
from app.models import Organization, WebhookDeliveryEvent, WebhookRoute
from app.routers.admin import _bot_readiness, _graph_lookup_readiness
from app.schemas import (
    MonitoringDatabaseOut,
    MonitoringDeliveriesOut,
    MonitoringGraphReadinessOut,
    MonitoringProblemRouteOut,
    MonitoringReadinessComponentOut,
    MonitoringReadinessOut,
    MonitoringRollingWindowOut,
    MonitoringRoutesOut,
    MonitoringStatusOut,
)
from app.security import utcnow
from app.services.graph_delegated_auth import DEFAULT_DELEGATED_GRAPH_SCOPES, diagnostics_for_organization

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

WINDOWS: dict[str, timedelta] = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
}
PROBLEM_ROUTE_LIMIT = 25
PRTG_SERVICE_STATE_LOOKUP = "prtg.standardlookups.wmi.diskhealth.health"
PRTG_BOOLEAN_TRUE_OK_LOOKUP = "prtg.standardlookups.boolean.statetrueok"


def require_monitoring_api_key(authorization: str | None = Header(default=None, alias="Authorization")) -> None:
    expected = get_settings().monitoring_api_key.strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Monitoring API key is not configured",
        )
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid monitoring API key")


@router.get("/status", response_model=MonitoringStatusOut, dependencies=[Depends(require_monitoring_api_key)])
def monitoring_status(db: Session = Depends(get_db)):
    return _build_monitoring_status(db)


@router.get("/prtg", dependencies=[Depends(require_monitoring_api_key)])
def monitoring_prtg(db: Session = Depends(get_db)):
    status_out = _build_monitoring_status(db)
    return {"prtg": {"result": _prtg_channels(status_out), "text": _prtg_text(status_out)}}


def _build_monitoring_status(db: Session) -> MonitoringStatusOut:
    settings = get_effective_settings()
    generated_at = utcnow()
    delivery_mode = settings.bot_delivery_mode_normalized
    enabled_backends = _enabled_delivery_backends(settings)
    bot_readiness = (
        _bot_readiness(settings, delivery_mode)
        if settings.bot_framework_enabled
        else MonitoringReadinessComponentOut(enabled=False, ready=True, auth_status="disabled")
    )
    graph_lookup_readiness = (
        _graph_lookup_readiness(settings)
        if settings.graph_lookup_enabled
        else MonitoringGraphReadinessOut(
            enabled=False,
            ready=True,
            auth_status="disabled",
            credential_source="disabled",
        )
    )
    graph_delivery_readiness = MonitoringGraphReadinessOut(
        enabled=settings.graph_delivery_enabled and settings.graph_lookup_enabled,
        ready=False,
        auth_status="unknown",
        credential_source="missing",
    )

    try:
        db.execute(text("SELECT 1"))
        database = MonitoringDatabaseOut(ok=True)
        if settings.graph_delivery_enabled and settings.graph_lookup_enabled:
            graph_delivery_readiness = _graph_delivery_readiness(db)
        else:
            graph_delivery_readiness = MonitoringGraphReadinessOut(
                enabled=False,
                ready=True,
                auth_status="disabled",
                credential_source="disabled",
            )
        routes = _route_counts(db)
        rollup_routes = _route_counts(db, delivery_backends=enabled_backends)
        deliveries = _delivery_summary(db)
        rolling_windows = {label: _rolling_window(db, generated_at - window) for label, window in WINDOWS.items()}
        rollup_short_window = _rolling_window(db, generated_at - WINDOWS["5m"], delivery_backends=enabled_backends)
        problem_routes = _problem_routes(db)
    except Exception:
        database = MonitoringDatabaseOut(ok=False, message="Database check failed")
        routes = MonitoringRoutesOut()
        rollup_routes = MonitoringRoutesOut()
        deliveries = MonitoringDeliveriesOut()
        rolling_windows = {label: MonitoringRollingWindowOut() for label in WINDOWS}
        rollup_short_window = MonitoringRollingWindowOut()
        problem_routes = []

    status_value = _rollup_status(
        database_ok=database.ok,
        delivery_mode=delivery_mode,
        bot_enabled=settings.bot_framework_enabled,
        bot_ready=bot_readiness.ready,
        graph_lookup_enabled=settings.graph_lookup_enabled,
        graph_lookup_ready=graph_lookup_readiness.ready,
        graph_delivery_enabled=settings.graph_delivery_enabled and settings.graph_lookup_enabled,
        graph_delivery_ready=graph_delivery_readiness.ready,
        routes=rollup_routes,
        short_window=rollup_short_window,
    )
    return MonitoringStatusOut(
        ok=status_value == "ok",
        status=status_value,
        service=settings.app_name,
        version=settings.app_version,
        generated_at=generated_at,
        database=database,
        delivery_mode=delivery_mode,
        readiness=MonitoringReadinessOut(
            bot=MonitoringReadinessComponentOut(
                enabled=settings.bot_framework_enabled,
                ready=bot_readiness.ready,
                auth_status=bot_readiness.auth_status,
            ),
            graph_lookup=MonitoringGraphReadinessOut(
                enabled=settings.graph_lookup_enabled,
                ready=graph_lookup_readiness.ready,
                auth_status=graph_lookup_readiness.auth_status,
                credential_source=graph_lookup_readiness.credential_source,
            ),
            graph_delivery=graph_delivery_readiness,
        ),
        routes=routes,
        deliveries=deliveries,
        rolling_windows=rolling_windows,
        problem_routes=problem_routes,
    )


def _prtg_channels(status_out: MonitoringStatusOut) -> list[dict[str, object]]:
    channels: list[dict[str, object]] = [
        {
            "channel": "Service State",
            "value": _prtg_service_state(status_out.status),
            "unit": "Custom",
            "customunit": "state",
            "valuelookup": PRTG_SERVICE_STATE_LOOKUP,
        },
        _prtg_boolean_channel("Database OK", status_out.database.ok),
        _prtg_boolean_channel("Bot Ready", status_out.readiness.bot.ready),
        _prtg_boolean_channel("Graph Lookup Ready", status_out.readiness.graph_lookup.ready),
        _prtg_boolean_channel("Graph Delivery Ready", status_out.readiness.graph_delivery.ready),
        _prtg_count_channel("Routes Total", status_out.routes.total),
        _prtg_count_channel("Routes Active", status_out.routes.active),
        _prtg_count_channel("Routes Inactive", status_out.routes.inactive),
        _prtg_count_channel("Routes Last Failed", status_out.routes.with_last_failure),
        _prtg_count_channel("Routes Last Rejected", status_out.routes.with_last_rejection),
        _prtg_count_channel("Routes Untested Active", status_out.routes.untested_active),
    ]
    for label in WINDOWS:
        window = status_out.rolling_windows.get(label, MonitoringRollingWindowOut())
        channels.extend(
            [
                _prtg_count_channel(f"Deliveries {label} Success", window.delivery_success_count),
                _prtg_count_channel(f"Deliveries {label} Failed", window.delivery_failure_count),
                _prtg_count_channel(f"Deliveries {label} Rejected", window.delivery_rejection_count),
                _prtg_percent_channel(f"Success Rate {label}", window.success_rate),
            ]
        )
    return channels


def _prtg_count_channel(channel: str, value: int) -> dict[str, object]:
    return {"channel": channel, "value": value, "unit": "Count"}


def _prtg_boolean_channel(channel: str, value: bool) -> dict[str, object]:
    return {
        "channel": channel,
        "value": int(value),
        "unit": "Custom",
        "customunit": "state",
        "valuelookup": PRTG_BOOLEAN_TRUE_OK_LOOKUP,
    }


def _prtg_percent_channel(channel: str, success_rate: float | None) -> dict[str, object]:
    value = 100.0 if success_rate is None else round(success_rate * 100, 1)
    return {"channel": channel, "value": value, "unit": "Percent", "float": 1, "decimalmode": "All"}


def _prtg_service_state(status_value: str) -> int:
    return {"ok": 0, "warn": 1, "crit": 2}.get(status_value, 2)


def _prtg_text(status_out: MonitoringStatusOut) -> str:
    routes = status_out.routes
    short_window = status_out.rolling_windows.get("5m", MonitoringRollingWindowOut())
    database = "ok" if status_out.database.ok else "failed"
    recent_issues = short_window.delivery_failure_count + short_window.delivery_rejection_count
    return (
        f"{status_out.service} {status_out.status}; database {database}; "
        f"routes active={routes.active}/{routes.total}, {_prtg_route_issues_text(routes)}; "
        f"5m delivered={short_window.delivery_success_count}, issues={recent_issues}"
    )


def _prtg_route_issues_text(routes: MonitoringRoutesOut) -> str:
    route_issues = routes.inactive + routes.with_last_failure + routes.with_last_rejection + routes.untested_active
    if not route_issues:
        return "issues=0"
    return (
        f"issues={route_issues} "
        f"(inactive={routes.inactive}, failed={routes.with_last_failure}, "
        f"rejected={routes.with_last_rejection}, untested_active={routes.untested_active})"
    )


def _route_counts(db: Session, *, delivery_backends: set[str] | None = None) -> MonitoringRoutesOut:
    filters = []
    if delivery_backends is not None:
        filters.append(WebhookRoute.delivery_backend.in_(delivery_backends))
    total = db.scalar(select(func.count()).select_from(WebhookRoute).where(*filters)) or 0
    active = db.scalar(select(func.count()).select_from(WebhookRoute).where(*filters, WebhookRoute.is_active.is_(True))) or 0
    inactive = db.scalar(select(func.count()).select_from(WebhookRoute).where(*filters, WebhookRoute.is_active.is_(False))) or 0
    with_last_failure = (
        db.scalar(select(func.count()).select_from(WebhookRoute).where(*filters, WebhookRoute.last_delivery_status == "failed")) or 0
    )
    with_last_rejection = (
        db.scalar(select(func.count()).select_from(WebhookRoute).where(*filters, WebhookRoute.last_delivery_status == "rejected")) or 0
    )
    untested_active = (
        db.scalar(
            select(func.count())
            .select_from(WebhookRoute)
            .where(*filters, WebhookRoute.is_active.is_(True), WebhookRoute.last_delivery_status.is_(None))
        )
        or 0
    )
    return MonitoringRoutesOut(
        total=total,
        active=active,
        inactive=inactive,
        with_last_failure=with_last_failure,
        with_last_rejection=with_last_rejection,
        untested_active=untested_active,
    )


def _delivery_summary(db: Session) -> MonitoringDeliveriesOut:
    return MonitoringDeliveriesOut(
        last_success_at=_last_delivery_at(db, "delivered"),
        last_failure_at=_last_delivery_at(db, "failed"),
        last_rejection_at=_last_delivery_at(db, "rejected"),
    )


def _graph_delivery_readiness(db: Session) -> MonitoringGraphReadinessOut:
    organization_id = db.scalar(select(Organization.id).order_by(Organization.created_at.asc()))
    if not organization_id:
        return MonitoringGraphReadinessOut(
            ready=False,
            auth_status="missing",
            credential_source="missing",
        )
    diagnostics = diagnostics_for_organization(db, organization_id)
    credential_source = "delegated_service_user" if diagnostics.configured else "missing"
    missing_scopes = _missing_required_scopes(diagnostics.scopes or [])
    auth_status = diagnostics.status or "missing"
    if diagnostics.configured and auth_status == "ready" and missing_scopes:
        auth_status = "permission_warning"
    return MonitoringGraphReadinessOut(
        ready=diagnostics.configured and auth_status == "ready",
        auth_status=auth_status,
        credential_source=credential_source,
    )


def _missing_required_scopes(granted_scopes: list[str]) -> list[str]:
    granted = {scope.lower() for scope in granted_scopes}
    return [scope for scope in DEFAULT_DELEGATED_GRAPH_SCOPES if scope.lower() not in granted]


def _last_delivery_at(db: Session, status_value: str):
    return db.scalar(
        select(func.max(WebhookDeliveryEvent.created_at)).where(WebhookDeliveryEvent.status == status_value)
    )


def _rolling_window(db: Session, since, *, delivery_backends: set[str] | None = None) -> MonitoringRollingWindowOut:
    statement = (
        select(WebhookDeliveryEvent.status, func.count())
        .select_from(WebhookDeliveryEvent)
        .where(WebhookDeliveryEvent.created_at >= since)
    )
    if delivery_backends is not None:
        statement = statement.outerjoin(WebhookRoute, WebhookDeliveryEvent.route_id == WebhookRoute.id).where(
            or_(WebhookDeliveryEvent.route_id.is_(None), WebhookRoute.delivery_backend.in_(delivery_backends))
        )
    rows = db.execute(statement.group_by(WebhookDeliveryEvent.status)).all()
    counts = {str(status_value): int(count) for status_value, count in rows}
    delivered = counts.get("delivered", 0)
    failed = counts.get("failed", 0)
    rejected = counts.get("rejected", 0)
    total = delivered + failed + rejected
    return MonitoringRollingWindowOut(
        delivery_success_count=delivered,
        delivery_failure_count=failed,
        delivery_rejection_count=rejected,
        success_rate=round(delivered / total, 3) if total else None,
    )


def _problem_routes(db: Session) -> list[MonitoringProblemRouteOut]:
    routes = db.scalars(
        select(WebhookRoute)
        .where(
            (WebhookRoute.is_active.is_(False))
            | (WebhookRoute.last_delivery_status.in_(["failed", "rejected"]))
            | ((WebhookRoute.is_active.is_(True)) & (WebhookRoute.last_delivery_status.is_(None)))
        )
        .order_by(WebhookRoute.updated_at.desc())
        .limit(PROBLEM_ROUTE_LIMIT)
    ).all()
    return [
        MonitoringProblemRouteOut(
            id=route.id,
            name=route.name,
            delivery_backend=route.delivery_backend,
            is_active=route.is_active,
            last_delivery_status=route.last_delivery_status,
            last_delivery_at=route.last_delivery_at,
        )
        for route in routes
    ]


def _rollup_status(
    *,
    database_ok: bool,
    delivery_mode: str,
    bot_enabled: bool,
    bot_ready: bool,
    graph_lookup_enabled: bool,
    graph_lookup_ready: bool,
    graph_delivery_enabled: bool,
    graph_delivery_ready: bool,
    routes: MonitoringRoutesOut,
    short_window: MonitoringRollingWindowOut,
) -> str:
    if not database_ok or (bot_enabled and delivery_mode == "real" and not bot_ready):
        return "crit"
    if (
        (graph_lookup_enabled and not graph_lookup_ready)
        or (graph_delivery_enabled and not graph_delivery_ready)
        or routes.inactive
        or routes.with_last_failure
        or routes.with_last_rejection
        or routes.untested_active
        or short_window.delivery_failure_count
        or short_window.delivery_rejection_count
    ):
        return "warn"
    return "ok"


def _enabled_delivery_backends(settings) -> set[str]:
    backends: set[str] = set()
    if settings.bot_framework_enabled:
        backends.add("bot_framework")
    if settings.graph_delivery_enabled and settings.graph_lookup_enabled:
        backends.add("graph")
    return backends
