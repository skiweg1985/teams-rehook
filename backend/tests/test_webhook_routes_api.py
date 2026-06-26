from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import create_app
from app.models import Organization, User, WebhookDeliveryEvent, WebhookRoute
from app.security import hash_secret, lookup_secret_hash


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
        admin = User(
            organization_id=org.id,
            email="admin@example.com",
            display_name="Admin",
            password_hash=hash_secret("change-me-admin-password"),
            is_admin=True,
            is_active=True,
        )
        db.add(org)
        db.flush()
        admin.organization_id = org.id
        db.add(admin)
        db.commit()
        yield db


@pytest.fixture()
def client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from app.core.config import get_settings

    monkeypatch.setenv("BOT_DELIVERY_MODE", "mock")
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


def add_route(db: Session, *, token: str = "route-token", active: bool = True) -> WebhookRoute:
    org = db.scalar(select(Organization).where(Organization.slug == "default"))
    assert org is not None
    route = WebhookRoute(
        organization_id=org.id,
        name=f"Route {token}",
        source_system="PRTG",
        is_active=active,
        route_token_hash=lookup_secret_hash(token),
        route_token=token,
        target_type="bot_conversation",
        target_name="Monitoring",
        bot_service_url="https://smba.trafficmanager.net/emea/example",
        bot_conversation_id="conversation-id",
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    return route


def login_admin(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "change-me-admin-password"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_admin_route_api_requires_session_and_csrf(client: TestClient):
    response = client.get("/api/v1/webhook-routes")

    assert response.status_code == 401


def test_public_webhook_delivers_known_active_route(client: TestClient, db_session: Session):
    route = add_route(db_session)

    response = client.post(
        "/api/v1/webhooks/route-token",
        json={"title": "PRTG alert", "text": "Sensor down", "severity": "warning"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "delivered"
    assert body["route_id"] == route.id
    db_session.refresh(route)
    assert route.last_delivery_status == "delivered"
    events = db_session.scalars(select(WebhookDeliveryEvent).where(WebhookDeliveryEvent.route_id == route.id)).all()
    assert len(events) == 1
    assert events[0].status == "delivered"


def test_public_webhook_rejects_unknown_token(client: TestClient, db_session: Session):
    response = client.post("/api/v1/webhooks/missing-token", json={"text": "hello"})

    assert response.status_code == 404
    events = db_session.scalars(select(WebhookDeliveryEvent)).all()
    assert len(events) == 1
    assert events[0].route_id is None
    assert events[0].status == "rejected"


def test_public_webhook_rejects_disabled_route(client: TestClient, db_session: Session):
    route = add_route(db_session, token="disabled-token", active=False)

    response = client.post("/api/v1/webhooks/disabled-token", json={"text": "hello"})

    assert response.status_code == 409
    db_session.refresh(route)
    assert route.last_delivery_status == "rejected"


def test_route_token_hash_is_stored_for_lookup(db_session: Session):
    route = add_route(db_session, token="secret-route-token")

    assert route.route_token == "secret-route-token"
    assert route.route_token_hash == lookup_secret_hash("secret-route-token")


def test_regenerate_url_replaces_route_token(client: TestClient, db_session: Session):
    route = add_route(db_session, token="old-token")
    csrf_token = login_admin(client)

    response = client.post(
        f"/api/v1/webhook-routes/{route.id}/regenerate-url",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["webhook_url_available"] is True
    assert "old-token" not in body["webhook_url"]
    db_session.refresh(route)
    assert route.route_token != "old-token"
    assert route.route_token_hash == lookup_secret_hash(route.route_token)


def test_delivery_events_endpoint_returns_parsed_logs(client: TestClient, db_session: Session):
    route = add_route(db_session)
    csrf_token = login_admin(client)
    delivery = client.post(
        f"/api/v1/webhook-routes/{route.id}/test",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "Test", "text": "Hello", "severity": "info"},
    )
    assert delivery.status_code == 200

    response = client.get(f"/api/v1/webhook-routes/{route.id}/deliveries")

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "delivered"
    assert rows[0]["request_metadata"]["trigger"] == "manual_test"
    assert rows[0]["normalized_message"]["title"] == "Test"
    assert rows[0]["delivery_result"]["mode"] == "mock"
