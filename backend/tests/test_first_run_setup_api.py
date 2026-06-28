from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings_overrides import reset_override_state
from app.database import Base, get_db
from app.main import create_app
from app.models import Organization, User
from app.security import hash_secret, verify_secret


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
        yield db


@contextmanager
def make_client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from app.core.config import get_settings

    monkeypatch.setenv("SESSION_COOKIE_NAME", "teams_rehook_session")
    monkeypatch.setenv("SESSION_SECRET", "test-setup-session-secret")
    get_settings.cache_clear()
    reset_override_state()
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


def test_setup_status_reports_missing_admin_and_creates_default_org(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with make_client(db_session, monkeypatch) as client:
        response = client.get("/api/v1/setup/status")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "needs_setup": True, "admin_exists": False}
    assert db_session.scalar(select(Organization).where(Organization.slug == "default")) is not None


def test_create_first_admin_sets_session_and_blocks_second_setup(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with make_client(db_session, monkeypatch) as client:
        response = client.post(
            "/api/v1/setup/admin",
            json={
                "email": "Admin@Example.COM",
                "display_name": "Ops Admin",
                "password": "first-admin-password",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["user"]["email"] == "admin@example.com"
        assert body["user"]["display_name"] == "Ops Admin"
        assert body["user"]["is_admin"] is True
        assert body["csrf_token"]
        assert "teams_rehook_session=" in response.headers["set-cookie"]

        second = client.post(
            "/api/v1/setup/admin",
            json={
                "email": "second@example.com",
                "display_name": "Second Admin",
                "password": "second-admin-password",
            },
        )
        status_response = client.get("/api/v1/setup/status")
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "first-admin-password"},
        )

    user = db_session.scalar(select(User).where(User.email == "admin@example.com"))
    assert user is not None
    assert user.is_admin is True
    assert user.is_active is True
    assert verify_secret("first-admin-password", user.password_hash)
    assert second.status_code == 409
    assert status_response.json() == {"ok": True, "needs_setup": False, "admin_exists": True}
    assert login_response.status_code == 200


def test_create_first_admin_rejects_when_admin_already_exists(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org = Organization(slug="default", name="Default")
    db_session.add(org)
    db_session.flush()
    db_session.add(
        User(
            organization_id=org.id,
            email="existing@example.com",
            display_name="Existing Admin",
            password_hash=hash_secret("existing-password"),
            is_admin=True,
            is_active=True,
        )
    )
    db_session.commit()

    with make_client(db_session, monkeypatch) as client:
        response = client.post(
            "/api/v1/setup/admin",
            json={
                "email": "admin@example.com",
                "display_name": "Admin",
                "password": "first-admin-password",
            },
        )

    assert response.status_code == 409
