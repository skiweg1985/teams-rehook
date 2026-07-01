from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings_overrides import load_overrides, reset_override_state, set_override
from app.database import Base, get_db
from app.main import create_app
from app.models import Organization, User, WebhookDeliveryEvent, WebhookRoute
from app.security import dumps_json, hash_secret, lookup_secret_hash, utcnow


@pytest.fixture()
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    with SessionLocal() as db:
        org = Organization(slug="default", name="Default")
        db.add(org)
        db.flush()
        db.add(
            User(
                organization_id=org.id,
                email="admin@example.com",
                display_name="Admin",
                password_hash=hash_secret("change-me-admin-password"),
                is_admin=True,
                is_active=True,
            )
        )
        db.commit()
        load_overrides(db)
        yield db
        reset_override_state()


@pytest.fixture()
def client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with app_client(db_session, monkeypatch) as test_client:
        yield test_client


@contextmanager
def app_client(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    *,
    monitoring_api_key: str = "monitoring-secret",
    bot_delivery_mode: str = "mock",
) -> Iterator[TestClient]:
    from app.core.config import get_settings

    monkeypatch.setenv("BOT_DELIVERY_MODE", bot_delivery_mode)
    monkeypatch.setenv("MS_APP_TENANT_ID", "")
    monkeypatch.setenv("MS_APP_CLIENT_ID", "")
    monkeypatch.setenv("MS_APP_CLIENT_SECRET", "")
    monkeypatch.setenv("MONITORING_API_KEY", monitoring_api_key)
    monkeypatch.setenv("APP_PUBLIC_BASE_URL", "http://localhost:5173")
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://localhost:5173")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173,http://localhost")
    monkeypatch.setenv("SESSION_SECURE_COOKIE", "false")
    get_settings.cache_clear()
    app = create_app()
    app.router.on_startup.clear()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()
        reset_override_state()


def auth_header(token: str = "monitoring-secret") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def channel_by_name(body: dict, name: str) -> dict:
    for channel in body["prtg"]["result"]:
        if channel["channel"] == name:
            return channel
    raise AssertionError(f"Missing PRTG channel {name}")


def add_route(
    db: Session,
    *,
    name: str,
    token: str,
    active: bool = True,
    last_status: str | None = None,
    last_at=None,
) -> WebhookRoute:
    org = db.scalar(select(Organization).where(Organization.slug == "default"))
    assert org is not None
    route = WebhookRoute(
        organization_id=org.id,
        name=name,
        is_active=active,
        route_token_hash=lookup_secret_hash(token),
        route_token=token,
        delivery_backend="bot_framework",
        target_type="bot_conversation",
        target_name="Monitoring",
        bot_service_url="https://smba.trafficmanager.net/emea/secret",
        bot_conversation_id="conversation-secret",
        last_delivery_status=last_status,
        last_delivery_at=last_at,
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    return route


def add_delivery(db: Session, route: WebhookRoute, *, status: str, created_at) -> WebhookDeliveryEvent:
    event = WebhookDeliveryEvent(
        organization_id=route.organization_id,
        route_id=route.id,
        route_token_hash=route.route_token_hash,
        status=status,
        normalized_message_json=dumps_json({"title": "Alert", "source": route.delivery_backend}),
        delivery_result_json=dumps_json({"mode": "mock", "status_code": 202}),
        created_at=created_at,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def test_monitoring_status_requires_configured_server_key(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    with app_client(db_session, monkeypatch, monitoring_api_key="") as test_client:
        response = test_client.get("/api/v1/monitoring/status", headers=auth_header())

    assert response.status_code == 503
    assert response.json()["detail"] == "Monitoring API key is not configured"


def test_monitoring_prtg_requires_configured_server_key(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    with app_client(db_session, monkeypatch, monitoring_api_key="") as test_client:
        response = test_client.get("/api/v1/monitoring/prtg", headers=auth_header())

    assert response.status_code == 503
    assert response.json()["detail"] == "Monitoring API key is not configured"


def test_monitoring_status_rejects_missing_or_wrong_bearer_token(client: TestClient):
    missing = client.get("/api/v1/monitoring/status")
    wrong = client.get("/api/v1/monitoring/status", headers=auth_header("wrong"))

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_monitoring_prtg_rejects_missing_or_wrong_bearer_token(client: TestClient):
    missing = client.get("/api/v1/monitoring/prtg")
    wrong = client.get("/api/v1/monitoring/prtg", headers=auth_header("wrong"))

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_monitoring_status_returns_route_counts_windows_and_problem_routes(client: TestClient, db_session: Session):
    now = utcnow()
    healthy = add_route(
        db_session,
        name="Healthy route",
        token="healthy-token-secret",
        last_status="delivered",
        last_at=now - timedelta(minutes=1),
    )
    failed = add_route(
        db_session,
        name="Failed route",
        token="failed-token-secret",
        last_status="failed",
        last_at=now - timedelta(minutes=2),
    )
    inactive = add_route(db_session, name="Inactive route", token="inactive-token-secret", active=False)
    add_route(db_session, name="Untested route", token="untested-token-secret", active=True)

    for minutes in [1, 2, 4, 10, 20]:
        add_delivery(db_session, healthy, status="delivered", created_at=now - timedelta(minutes=minutes))
    for minutes in [3, 12]:
        add_delivery(db_session, failed, status="failed", created_at=now - timedelta(minutes=minutes))
    add_delivery(db_session, failed, status="rejected", created_at=now - timedelta(minutes=50))

    response = client.get("/api/v1/monitoring/status", headers=auth_header())

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "Teams Rehook"
    assert body["database"] == {"ok": True, "message": ""}
    assert body["delivery_mode"] == "mock"
    assert body["routes"] == {
        "total": 4,
        "active": 3,
        "inactive": 1,
        "with_last_failure": 1,
        "with_last_rejection": 0,
        "untested_active": 1,
    }
    assert body["rolling_windows"]["5m"] == {
        "delivery_success_count": 3,
        "delivery_failure_count": 1,
        "delivery_rejection_count": 0,
        "success_rate": 0.75,
    }
    assert body["rolling_windows"]["15m"] == {
        "delivery_success_count": 4,
        "delivery_failure_count": 2,
        "delivery_rejection_count": 0,
        "success_rate": 0.667,
    }
    assert body["rolling_windows"]["1h"] == {
        "delivery_success_count": 5,
        "delivery_failure_count": 2,
        "delivery_rejection_count": 1,
        "success_rate": 0.625,
    }
    assert body["deliveries"]["last_success_at"] is not None
    assert body["deliveries"]["last_failure_at"] is not None
    assert body["deliveries"]["last_rejection_at"] is not None
    problem_names = {route["name"] for route in body["problem_routes"]}
    assert {"Failed route", "Inactive route", "Untested route"} <= problem_names
    serialized = response.text
    assert "healthy-token-secret" not in serialized
    assert "failed-token-secret" not in serialized
    assert "inactive-token-secret" not in serialized
    assert "conversation-secret" not in serialized
    assert "smba.trafficmanager" not in serialized


def test_monitoring_status_has_null_success_rate_without_delivery_events(client: TestClient):
    response = client.get("/api/v1/monitoring/status", headers=auth_header())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "warn"
    assert body["rolling_windows"]["5m"]["success_rate"] is None
    assert body["rolling_windows"]["15m"]["success_rate"] is None
    assert body["rolling_windows"]["1h"]["success_rate"] is None


def test_monitoring_prtg_returns_advanced_sensor_json_for_warning_status(
    client: TestClient, db_session: Session
):
    now = utcnow()
    healthy = add_route(
        db_session,
        name="Healthy route",
        token="healthy-token-secret",
        last_status="delivered",
        last_at=now - timedelta(minutes=1),
    )
    failed = add_route(
        db_session,
        name="Failed route",
        token="failed-token-secret",
        last_status="failed",
        last_at=now - timedelta(minutes=2),
    )
    add_route(db_session, name="Untested route", token="untested-token-secret", active=True)
    add_delivery(db_session, healthy, status="delivered", created_at=now - timedelta(minutes=1))
    add_delivery(db_session, failed, status="failed", created_at=now - timedelta(minutes=2))

    response = client.get("/api/v1/monitoring/prtg", headers=auth_header())

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"prtg"}
    assert isinstance(body["prtg"]["result"], list)
    assert body["prtg"]["text"].startswith("Teams Rehook warn;")
    assert "routes active=3/3, issues=2 (inactive=0, failed=1, rejected=0, untested_active=1)" in body["prtg"]["text"]
    assert channel_by_name(body, "Service State") == {
        "channel": "Service State",
        "value": 1,
        "unit": "Custom",
        "customunit": "state",
        "valuelookup": "prtg.standardlookups.wmi.diskhealth.health",
    }
    assert channel_by_name(body, "Database OK") == {
        "channel": "Database OK",
        "value": 1,
        "unit": "Custom",
        "customunit": "state",
        "valuelookup": "prtg.standardlookups.boolean.statetrueok",
    }
    assert channel_by_name(body, "Routes Total") == {"channel": "Routes Total", "value": 3, "unit": "Count"}
    assert channel_by_name(body, "Routes Last Failed") == {
        "channel": "Routes Last Failed",
        "value": 1,
        "unit": "Count",
    }
    assert channel_by_name(body, "Deliveries 5m Success") == {
        "channel": "Deliveries 5m Success",
        "value": 1,
        "unit": "Count",
    }
    assert channel_by_name(body, "Deliveries 5m Failed") == {
        "channel": "Deliveries 5m Failed",
        "value": 1,
        "unit": "Count",
    }
    assert channel_by_name(body, "Success Rate 5m") == {
        "channel": "Success Rate 5m",
        "value": 50.0,
        "unit": "Percent",
        "float": 1,
        "decimalmode": "All",
    }
    serialized = response.text
    assert "healthy-token-secret" not in serialized
    assert "failed-token-secret" not in serialized
    assert "untested-token-secret" not in serialized
    assert "conversation-secret" not in serialized
    assert "smba.trafficmanager" not in serialized


def test_monitoring_rollup_ignores_disabled_graph_features(client: TestClient, db_session: Session):
    admin = db_session.scalar(select(User).where(User.email == "admin@example.com"))
    assert admin is not None
    set_override(db_session, key="graph_delivery_enabled", value="false", updated_by_id=admin.id)
    set_override(db_session, key="graph_lookup_enabled", value="false", updated_by_id=admin.id)
    db_session.commit()
    now = utcnow()
    bot_route = add_route(
        db_session,
        name="Bot route",
        token="bot-route-token",
        last_status="delivered",
        last_at=now - timedelta(minutes=1),
    )
    graph_route = add_route(
        db_session,
        name="Graph route",
        token="graph-route-token",
        last_status="failed",
        last_at=now - timedelta(minutes=1),
    )
    graph_route.delivery_backend = "graph"
    db_session.add(graph_route)
    db_session.commit()
    add_delivery(db_session, bot_route, status="delivered", created_at=now - timedelta(minutes=1))
    add_delivery(db_session, graph_route, status="failed", created_at=now - timedelta(minutes=1))

    response = client.get("/api/v1/monitoring/status", headers=auth_header())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["readiness"]["graph_lookup"]["enabled"] is False
    assert body["readiness"]["graph_delivery"]["enabled"] is False
    assert body["routes"]["with_last_failure"] == 1
    assert body["rolling_windows"]["5m"]["delivery_failure_count"] == 1


def test_monitoring_prtg_maps_ok_status(client: TestClient, db_session: Session):
    admin = db_session.scalar(select(User).where(User.email == "admin@example.com"))
    assert admin is not None
    set_override(db_session, key="graph_delivery_enabled", value="false", updated_by_id=admin.id)
    set_override(db_session, key="graph_lookup_enabled", value="false", updated_by_id=admin.id)
    db_session.commit()
    now = utcnow()
    route = add_route(
        db_session,
        name="Healthy route",
        token="healthy-token-secret",
        last_status="delivered",
        last_at=now - timedelta(minutes=1),
    )
    add_delivery(db_session, route, status="delivered", created_at=now - timedelta(minutes=1))

    response = client.get("/api/v1/monitoring/prtg", headers=auth_header())

    assert response.status_code == 200
    body = response.json()
    assert channel_by_name(body, "Service State")["value"] == 0
    assert body["prtg"]["text"].startswith("Teams Rehook ok;")


def test_monitoring_prtg_maps_critical_status(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    with app_client(db_session, monkeypatch, bot_delivery_mode="real") as test_client:
        response = test_client.get("/api/v1/monitoring/prtg", headers=auth_header())

    assert response.status_code == 200
    body = response.json()
    assert channel_by_name(body, "Service State")["value"] == 2
    assert body["prtg"]["text"].startswith("Teams Rehook crit;")
