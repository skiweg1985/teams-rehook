from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import create_app
from app.models import Organization, User
from app.security import hash_secret
from app.services.graph_targets import GraphConfigError, GraphTarget


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


@pytest.fixture()
def client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from app.core.config import get_settings

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


def test_target_search_requires_admin(client: TestClient):
    response = client.get("/api/v1/teams-targets/search?kind=user&q=ann")

    assert response.status_code == 401


def test_target_search_returns_graph_results(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    login_admin(client)

    def fake_search(kind: str, query: str):
        assert kind == "user"
        assert query == "ann"
        return [GraphTarget(kind="user", id="user-id", display_name="Ann Admin", subtitle="ann@example.com")]

    monkeypatch.setattr("app.routers.teams_targets.search_targets", fake_search)

    response = client.get("/api/v1/teams-targets/search?kind=user&q=ann")

    assert response.status_code == 200
    assert response.json() == [
        {
            "kind": "user",
            "id": "user-id",
            "display_name": "Ann Admin",
            "subtitle": "ann@example.com",
            "team_id": None,
            "team_name": None,
            "channel_id": None,
        }
    ]


def test_target_search_reports_missing_graph_config(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    login_admin(client)

    def fake_search(kind: str, query: str):
        raise GraphConfigError("Missing Microsoft Graph app-only credentials: MS_APP_TENANT_ID")

    monkeypatch.setattr("app.routers.teams_targets.search_targets", fake_search)

    response = client.get("/api/v1/teams-targets/search?kind=team&q=ops")

    assert response.status_code == 503
    assert "MS_APP_TENANT_ID" in response.json()["detail"]


def test_team_channels_returns_channel_results(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    login_admin(client)

    def fake_channels(team_id: str, query: str):
        assert team_id == "team-id"
        assert query == "alerts"
        return [
            GraphTarget(
                kind="channel",
                id="channel-id",
                display_name="Alerts",
                subtitle="standard",
                team_id="team-id",
                team_name="Operations",
                channel_id="channel-id",
            )
        ]

    monkeypatch.setattr("app.routers.teams_targets.list_team_channels", fake_channels)

    response = client.get("/api/v1/teams-targets/teams/team-id/channels?q=alerts")

    assert response.status_code == 200
    assert response.json()[0]["kind"] == "channel"
    assert response.json()[0]["channel_id"] == "channel-id"
