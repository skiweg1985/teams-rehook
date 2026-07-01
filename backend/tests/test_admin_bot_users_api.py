from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings_overrides import load_overrides, reset_override_state
from app.database import Base, get_db
from app.main import create_app
from app.models import AuditEvent, BotAccessRole, BotAuthorizedGroup, BotAuthorizedUser, Organization, User
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
        db.add_all(
            [
                User(
                    organization_id=org.id,
                    email="admin@example.com",
                    display_name="Admin",
                    password_hash=hash_secret("change-me-admin-password"),
                    is_admin=True,
                    is_active=True,
                ),
                User(
                    organization_id=org.id,
                    email="member@example.com",
                    display_name="Member",
                    password_hash=hash_secret("member-password"),
                    is_admin=False,
                    is_active=True,
                ),
            ]
        )
        db.commit()
        load_overrides(db)
        yield db


@contextmanager
def make_client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from app.core.config import get_settings

    monkeypatch.setenv("BOT_DELIVERY_MODE", "mock")
    get_settings.cache_clear()
    reset_override_state()
    load_overrides(db_session)
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


def login(client: TestClient, email: str = "admin@example.com", password: str = "change-me-admin-password") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_create_update_list_and_delete_bot_access_user(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login(client)
        created = client.post(
            "/api/v1/admin/bot-users",
            headers={"X-CSRF-Token": csrf},
            json={
                "aad_object_id": "AAD-USER-ID",
                "display_name": "Ada Admin",
                "user_principal_name": "ada@example.com",
                "role": "operator",
                "is_active": True,
            },
        )

        assert created.status_code == 201
        body = created.json()
        assert body["aad_object_id"] == "aad-user-id"
        assert body["role"] == "route_operator"
        assert body["role_id"]
        assert body["can_view_routes"] is True
        assert body["can_reveal_webhook_urls"] is True
        assert body["can_manage_route_status"] is True
        assert body["can_delete_routes"] is True

        duplicate = client.post(
            "/api/v1/admin/bot-users",
            headers={"X-CSRF-Token": csrf},
            json={
                "aad_object_id": "aad-user-id",
                "display_name": "Duplicate",
                "role": "viewer",
            },
        )
        assert duplicate.status_code == 409

        updated = client.patch(
            f"/api/v1/admin/bot-users/{body['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "display_name": "Ada Lovelace",
                "role": "custom",
                "can_view_routes": True,
                "can_reveal_webhook_urls": False,
                "can_manage_route_status": False,
                "can_delete_routes": False,
                "can_manage_allowlist": False,
                "can_create_private_chat_routes": True,
                "can_create_channel_routes": False,
            },
        )

        assert updated.status_code == 200
        assert updated.json()["display_name"] == "Ada Lovelace"
        assert updated.json()["role"] == "custom"
        assert updated.json()["can_reveal_webhook_urls"] is False
        assert updated.json()["can_create_private_chat_routes"] is True

        listed = client.get("/api/v1/admin/bot-users", headers={"X-CSRF-Token": csrf})
        assert listed.status_code == 200
        assert [user["display_name"] for user in listed.json()] == ["Ada Lovelace"]

        deleted = client.delete(f"/api/v1/admin/bot-users/{body['id']}", headers={"X-CSRF-Token": csrf})
        assert deleted.status_code == 204
        assert db_session.scalar(select(BotAuthorizedUser)) is None
        audit_actions = [row.action for row in db_session.scalars(select(AuditEvent)).all()]
        assert "admin.bot_user.created" in audit_actions
        assert "admin.bot_user.updated" in audit_actions
        assert "admin.bot_user.deleted" in audit_actions


def test_create_update_list_and_delete_bot_access_group(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login(client)
        created = client.post(
            "/api/v1/admin/bot-groups",
            headers={"X-CSRF-Token": csrf},
            json={
                "group_object_id": "GROUP-ID",
                "display_name": "Teams Operators",
                "mail": "teams-operators@example.com",
                "security_enabled": True,
                "group_types": [],
                "role": "operator",
                "is_active": True,
            },
        )

        assert created.status_code == 201
        body = created.json()
        assert body["group_object_id"] == "group-id"
        assert body["role"] == "route_operator"
        assert body["role_id"]
        assert body["can_manage_route_status"] is True
        assert body["can_delete_routes"] is True

        duplicate = client.post(
            "/api/v1/admin/bot-groups",
            headers={"X-CSRF-Token": csrf},
            json={"group_object_id": "group-id", "display_name": "Duplicate", "role": "viewer"},
        )
        assert duplicate.status_code == 409

        updated = client.patch(
            f"/api/v1/admin/bot-groups/{body['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "display_name": "Teams Route Managers",
                "role": "route_manager",
            },
        )

        assert updated.status_code == 200
        assert updated.json()["display_name"] == "Teams Route Managers"
        assert updated.json()["can_delete_routes"] is True
        assert updated.json()["can_manage_allowlist"] is True

        listed = client.get("/api/v1/admin/bot-groups", headers={"X-CSRF-Token": csrf})
        assert listed.status_code == 200
        assert [group["display_name"] for group in listed.json()] == ["Teams Route Managers"]

        deleted = client.delete(f"/api/v1/admin/bot-groups/{body['id']}", headers={"X-CSRF-Token": csrf})
        assert deleted.status_code == 204
        assert db_session.scalar(select(BotAuthorizedGroup)) is None
        audit_actions = [row.action for row in db_session.scalars(select(AuditEvent)).all()]
        assert "admin.bot_group.created" in audit_actions
        assert "admin.bot_group.updated" in audit_actions
        assert "admin.bot_group.deleted" in audit_actions


def test_bot_access_roles_crud_and_delete_guards(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login(client)
        listed = client.get("/api/v1/admin/bot-roles", headers={"X-CSRF-Token": csrf})

        assert listed.status_code == 200
        role_names = {role["name"] for role in listed.json()}
        assert {"Route Viewer", "Route Operator"}.issubset(role_names)

        duplicate = client.post(
            "/api/v1/admin/bot-roles",
            headers={"X-CSRF-Token": csrf},
            json={
                "name": "Route Viewer",
                "description": "duplicate",
                "can_view_routes": True,
                "can_reveal_webhook_urls": False,
                "can_manage_route_status": False,
                "can_delete_routes": False,
                "can_manage_allowlist": False,
                "can_create_private_chat_routes": False,
                "can_create_channel_routes": False,
            },
        )
        assert duplicate.status_code == 409

        created = client.post(
            "/api/v1/admin/bot-roles",
            headers={"X-CSRF-Token": csrf},
            json={
                "name": "Channel Registrar",
                "description": "Can create channel routes only.",
                "can_view_routes": True,
                "can_reveal_webhook_urls": False,
                "can_manage_route_status": False,
                "can_delete_routes": False,
                "can_manage_allowlist": False,
                "can_create_private_chat_routes": False,
                "can_create_channel_routes": True,
            },
        )
        assert created.status_code == 201
        custom_role = created.json()
        assert custom_role["is_system"] is False
        assert custom_role["can_create_channel_routes"] is True

        patched = client.patch(
            f"/api/v1/admin/bot-roles/{custom_role['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"name": "Channel Route Registrar", "can_reveal_webhook_urls": True},
        )
        assert patched.status_code == 200
        assert patched.json()["name"] == "Channel Route Registrar"
        assert patched.json()["can_reveal_webhook_urls"] is True

        deleted = client.delete(f"/api/v1/admin/bot-roles/{custom_role['id']}", headers={"X-CSRF-Token": csrf})
        assert deleted.status_code == 204
        assert db_session.scalar(select(BotAccessRole).where(BotAccessRole.id == custom_role["id"])) is None

        system_role = next(role for role in listed.json() if role["name"] == "Route Viewer")
        delete_system = client.delete(f"/api/v1/admin/bot-roles/{system_role['id']}", headers={"X-CSRF-Token": csrf})
        assert delete_system.status_code == 409


def test_role_updates_sync_linked_bot_access_grants(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login(client)
        roles = client.get("/api/v1/admin/bot-roles", headers={"X-CSRF-Token": csrf}).json()
        viewer = next(role for role in roles if role["name"] == "Route Viewer")

        created_user = client.post(
            "/api/v1/admin/bot-users",
            headers={"X-CSRF-Token": csrf},
            json={
                "aad_object_id": "AAD-USER-ID",
                "display_name": "Ada Admin",
                "user_principal_name": "ada@example.com",
                "role_id": viewer["id"],
                "role": "route_viewer",
                "is_active": True,
            },
        )
        assert created_user.status_code == 201
        assert created_user.json()["can_delete_routes"] is False

        updated_role = client.patch(
            f"/api/v1/admin/bot-roles/{viewer['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"can_delete_routes": True},
        )
        assert updated_role.status_code == 200
        assert updated_role.json()["can_delete_routes"] is True

        listed_users = client.get("/api/v1/admin/bot-users", headers={"X-CSRF-Token": csrf})
        assert listed_users.status_code == 200
        assert listed_users.json()[0]["role_id"] == viewer["id"]
        assert listed_users.json()[0]["can_delete_routes"] is True

        delete_assigned_role = client.delete(f"/api/v1/admin/bot-roles/{viewer['id']}", headers={"X-CSRF-Token": csrf})
        assert delete_assigned_role.status_code == 409


def test_inline_custom_grants_are_not_backfilled_to_role_templates(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login(client)
        created = client.post(
            "/api/v1/admin/bot-users",
            headers={"X-CSRF-Token": csrf},
            json={
                "aad_object_id": "AAD-CUSTOM-ID",
                "display_name": "Custom Viewer",
                "user_principal_name": "custom@example.com",
                "role": "custom",
                "is_active": True,
                "can_view_routes": True,
                "can_reveal_webhook_urls": True,
                "can_manage_route_status": False,
                "can_delete_routes": False,
                "can_manage_allowlist": False,
                "can_create_private_chat_routes": False,
                "can_create_channel_routes": False,
            },
        )
        assert created.status_code == 201
        assert created.json()["role_id"] is None

        listed = client.get("/api/v1/admin/bot-users", headers={"X-CSRF-Token": csrf})
        assert listed.status_code == 200
        assert listed.json()[0]["role"] == "custom"
        assert listed.json()[0]["role_id"] is None


def test_bot_access_writes_require_csrf_and_admin(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login(client)
        missing_csrf = client.post(
            "/api/v1/admin/bot-users",
            json={"aad_object_id": "aad-user-id", "display_name": "Ada Admin", "role": "viewer"},
        )
        assert missing_csrf.status_code == 403
        missing_role_csrf = client.post(
            "/api/v1/admin/bot-roles",
            json={
                "name": "No CSRF",
                "description": "",
                "can_view_routes": True,
                "can_reveal_webhook_urls": False,
                "can_manage_route_status": False,
                "can_delete_routes": False,
                "can_manage_allowlist": False,
                "can_create_private_chat_routes": False,
                "can_create_channel_routes": False,
            },
        )
        assert missing_role_csrf.status_code == 403

        member_csrf = login(client, "member@example.com", "member-password")
        forbidden_role = client.get("/api/v1/admin/bot-roles", headers={"X-CSRF-Token": member_csrf})
        assert forbidden_role.status_code == 403
        forbidden = client.get("/api/v1/admin/bot-users", headers={"X-CSRF-Token": member_csrf})
        assert forbidden.status_code == 403
        forbidden_group = client.get("/api/v1/admin/bot-groups", headers={"X-CSRF-Token": member_csrf})
        assert forbidden_group.status_code == 403

        csrf = login(client)
        ok = client.post(
            "/api/v1/admin/bot-users",
            headers={"X-CSRF-Token": csrf},
            json={"aad_object_id": "aad-user-id", "display_name": "Ada Admin", "role": "route_manager"},
        )
        assert ok.status_code == 201
        missing_group_csrf = client.post(
            "/api/v1/admin/bot-groups",
            json={"group_object_id": "group-id", "display_name": "Operators", "role": "viewer"},
        )
        assert missing_group_csrf.status_code == 403
