from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from app.core.settings_overrides import load_overrides, reset_override_state
from app.database import Base, get_db
from app.main import create_app
from app.models import Organization, Session as UserSession, User
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


def test_create_user_and_login(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login(client)
        response = client.post(
            "/api/v1/admin/users",
            headers={"X-CSRF-Token": csrf},
            json={
                "email": "Ops.User@Example.COM",
                "display_name": "Ops User",
                "password": "new-user-password",
                "is_admin": False,
                "is_active": True,
            },
        )
        assert response.status_code == 201
        assert response.json()["email"] == "ops.user@example.com"
        assert response.json()["is_admin"] is False

        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "ops.user@example.com", "password": "new-user-password"},
        )
        assert login_response.status_code == 200


def test_create_user_rejects_duplicate_email(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login(client)
        response = client.post(
            "/api/v1/admin/users",
            headers={"X-CSRF-Token": csrf},
            json={
                "email": "ADMIN@example.com",
                "display_name": "Duplicate",
                "password": "duplicate-password",
                "is_admin": True,
                "is_active": True,
            },
        )
        assert response.status_code == 409


def test_update_user_fields_and_reject_self_lockout(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login(client)
        created = client.post(
            "/api/v1/admin/users",
            headers={"X-CSRF-Token": csrf},
            json={
                "email": "member@example.com",
                "display_name": "Member",
                "password": "member-password",
                "is_admin": False,
                "is_active": True,
            },
        )
        user_id = created.json()["id"]

        updated = client.patch(
            f"/api/v1/admin/users/{user_id}",
            headers={"X-CSRF-Token": csrf},
            json={"email": "renamed@example.com", "display_name": "Renamed Member", "is_admin": True},
        )
        assert updated.status_code == 200
        assert updated.json()["email"] == "renamed@example.com"
        assert updated.json()["display_name"] == "Renamed Member"
        assert updated.json()["is_admin"] is True

        admin_id = db_session.scalar(select(User.id).where(User.email == "admin@example.com"))
        demote_self = client.patch(
            f"/api/v1/admin/users/{admin_id}",
            headers={"X-CSRF-Token": csrf},
            json={"is_admin": False},
        )
        assert demote_self.status_code == 400
        assert demote_self.json()["detail"] == "You cannot remove your own admin access"

        deactivate_self = client.patch(
            f"/api/v1/admin/users/{admin_id}",
            headers={"X-CSRF-Token": csrf},
            json={"is_active": False},
        )
        assert deactivate_self.status_code == 400
        assert deactivate_self.json()["detail"] == "You cannot deactivate your own user"


def test_password_reset_and_deactivation_revoke_sessions(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login(client)
        created = client.post(
            "/api/v1/admin/users",
            headers={"X-CSRF-Token": csrf},
            json={
                "email": "target@example.com",
                "display_name": "Target",
                "password": "target-password",
                "is_admin": False,
                "is_active": True,
            },
        )
        user_id = created.json()["id"]
        login(client, "target@example.com", "target-password")

        csrf = login(client)
        reset = client.put(
            f"/api/v1/admin/users/{user_id}/password",
            headers={"X-CSRF-Token": csrf},
            json={"password": "changed-password"},
        )
        assert reset.status_code == 200
        assert db_session.scalar(select(UserSession).where(UserSession.user_id == user_id)).revoked_at is not None
        assert client.post("/api/v1/auth/login", json={"email": "target@example.com", "password": "target-password"}).status_code == 401
        assert client.post("/api/v1/auth/login", json={"email": "target@example.com", "password": "changed-password"}).status_code == 200

        csrf = login(client)
        deactivate = client.patch(
            f"/api/v1/admin/users/{user_id}",
            headers={"X-CSRF-Token": csrf},
            json={"is_active": False},
        )
        assert deactivate.status_code == 200
        assert client.post("/api/v1/auth/login", json={"email": "target@example.com", "password": "changed-password"}).status_code == 401


def test_user_writes_require_csrf_and_admin(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login(client)
        rejected = client.post(
            "/api/v1/admin/users",
            json={
                "email": "missing-csrf@example.com",
                "display_name": "Missing CSRF",
                "password": "missing-csrf-password",
            },
        )
        assert rejected.status_code == 403

        created = client.post(
            "/api/v1/admin/users",
            headers={"X-CSRF-Token": csrf},
            json={
                "email": "member@example.com",
                "display_name": "Member",
                "password": "member-password",
                "is_admin": False,
                "is_active": True,
            },
        )
        assert created.status_code == 201

        member_csrf = login(client, "member@example.com", "member-password")
        forbidden = client.get("/api/v1/admin/users", headers={"X-CSRF-Token": member_csrf})
        assert forbidden.status_code == 403
