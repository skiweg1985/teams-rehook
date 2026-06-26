from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import create_app
from app.models import Organization, User
from app.security import hash_secret


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
        yield db


@contextmanager
def make_client(db_session: Session, monkeypatch: pytest.MonkeyPatch, **env: str) -> Iterator[TestClient]:
    from app.core.config import get_settings

    defaults = {
        "BOT_DELIVERY_MODE": "mock",
        "BOT_TENANT_ID": "",
        "BOT_CLIENT_ID": "",
        "BOT_CLIENT_SECRET": "",
        "BOT_DEFAULT_SERVICE_URL": "",
        "GRAPH_TENANT_ID": "",
        "GRAPH_CLIENT_ID": "",
        "GRAPH_CLIENT_SECRET": "",
    }
    defaults.update(env)
    for key, value in defaults.items():
        monkeypatch.setenv(key, value)
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


def login_admin(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "change-me-admin-password"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_readiness_requires_admin_session(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    with make_client(db_session, monkeypatch, BOT_DELIVERY_MODE="mock") as client:
        response = client.get("/api/v1/admin/readiness")

    assert response.status_code == 401


def test_readiness_reports_mock_delivery_ready_without_bot_credentials(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    with make_client(db_session, monkeypatch, BOT_DELIVERY_MODE="mock") as client:
        csrf_token = login_admin(client)
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["app_name"] == "Teams Rehook"
    assert body["delivery_mode"] == "mock"
    assert body["bot"]["ready"] is True
    assert body["bot"]["credentials_configured"] is False
    assert body["graph"]["ready"] is False


def test_readiness_reports_real_delivery_missing_bot_credentials(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    with make_client(db_session, monkeypatch, BOT_DELIVERY_MODE="real") as client:
        csrf_token = login_admin(client)
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["delivery_mode"] == "real"
    assert body["bot"]["ready"] is False
    assert "BOT_TENANT_ID" in body["bot"]["message"]


def test_readiness_reports_graph_credentials_and_bot_fallback(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    with make_client(
        db_session,
        monkeypatch,
        BOT_DELIVERY_MODE="real",
        BOT_TENANT_ID="tenant",
        BOT_CLIENT_ID="client",
        BOT_CLIENT_SECRET="secret",
    ) as client:
        csrf_token = login_admin(client)
        fallback_response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert fallback_response.status_code == 200
    fallback_body = fallback_response.json()
    assert fallback_body["bot"]["ready"] is True
    assert fallback_body["graph"]["ready"] is True
    assert fallback_body["graph"]["credential_source"] == "bot"

    with make_client(
        db_session,
        monkeypatch,
        BOT_DELIVERY_MODE="mock",
        GRAPH_TENANT_ID="tenant",
        GRAPH_CLIENT_ID="client",
        GRAPH_CLIENT_SECRET="secret",
    ) as client:
        csrf_token = login_admin(client)
        graph_response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert graph_response.status_code == 200
    graph_body = graph_response.json()
    assert graph_body["graph"]["ready"] is True
    assert graph_body["graph"]["credential_source"] == "graph"
