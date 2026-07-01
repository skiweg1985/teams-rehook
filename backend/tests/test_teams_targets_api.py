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
from app.services.graph_delegated_lookup import DelegatedGraphChat, GraphDelegatedLookupError
from app.services.graph_targets import GraphConfigError, GraphGroupMember, GraphGroupMemberPage, GraphTarget


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
            "mail": "",
            "security_enabled": None,
            "group_types": [],
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
    assert response.json()[0]["group_types"] == []


def test_group_target_search_returns_group_metadata(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    login_admin(client)

    def fake_search(kind: str, query: str):
        assert kind == "group"
        assert query == "ops"
        return [
            GraphTarget(
                kind="group",
                id="group-id",
                display_name="Ops Owners",
                subtitle="ops@example.com · Microsoft 365 group",
                mail="ops@example.com",
                security_enabled=True,
                group_types=("Unified",),
            )
        ]

    monkeypatch.setattr("app.routers.teams_targets.search_targets", fake_search)

    response = client.get("/api/v1/teams-targets/search?kind=group&q=ops")

    assert response.status_code == 200
    assert response.json() == [
        {
            "kind": "group",
            "id": "group-id",
            "display_name": "Ops Owners",
            "subtitle": "ops@example.com · Microsoft 365 group",
            "team_id": None,
            "team_name": None,
            "channel_id": None,
            "mail": "ops@example.com",
            "security_enabled": True,
            "group_types": ["Unified"],
        }
    ]


def test_group_members_returns_transitive_user_members(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    login_admin(client)

    def fake_members(group_id: str, query: str, *, offset: int, limit: int):
        assert group_id == "group-id"
        assert query == "ada"
        assert offset == 25
        assert limit == 50
        return GraphGroupMemberPage(
            items=[
                GraphGroupMember(
                    id="user-id",
                    display_name="Ada Admin",
                    user_principal_name="ada@example.com",
                    mail="ada@example.com",
                )
            ],
            offset=offset,
            limit=limit,
            has_more=True,
        )

    monkeypatch.setattr("app.routers.teams_targets.list_group_transitive_members", fake_members)

    response = client.get("/api/v1/teams-targets/groups/group-id/members?q=ada&offset=25&limit=50")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": "user-id",
                "display_name": "Ada Admin",
                "user_principal_name": "ada@example.com",
                "mail": "ada@example.com",
            }
        ],
        "offset": 25,
        "limit": 50,
        "has_more": True,
    }


def test_group_member_count_returns_graph_count(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    login_admin(client)

    def fake_count(group_id: str):
        assert group_id == "group-id"
        return 123

    monkeypatch.setattr("app.routers.teams_targets.count_group_transitive_user_members", fake_count)

    response = client.get("/api/v1/teams-targets/groups/group-id/members/count")

    assert response.status_code == 200
    assert response.json() == {"count": 123}


def test_service_user_chats_returns_delegated_chat_results(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    login_admin(client)

    def fake_chats(db, *, organization_id: str, query: str):
        assert query == "ops"
        return [DelegatedGraphChat(id="chat-id", display_name="Ops chat", subtitle="group")]

    monkeypatch.setattr("app.routers.teams_targets.list_service_user_chats", fake_chats)

    response = client.get("/api/v1/teams-targets/chats?q=ops")

    assert response.status_code == 200
    assert response.json() == [
        {
            "kind": "chat",
            "id": "chat-id",
            "display_name": "Ops chat",
            "subtitle": "group",
            "team_id": None,
            "team_name": None,
            "channel_id": None,
            "mail": "",
            "security_enabled": None,
            "group_types": [],
        }
    ]


def test_service_user_chats_reports_delegated_lookup_error(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    login_admin(client)

    def fail_chats(db, *, organization_id: str, query: str):
        raise GraphDelegatedLookupError("Delegated Graph delivery is not connected")

    monkeypatch.setattr("app.routers.teams_targets.list_service_user_chats", fail_chats)

    response = client.get("/api/v1/teams-targets/chats")

    assert response.status_code == 502
    assert response.json()["detail"] == "Delegated Graph delivery is not connected"
