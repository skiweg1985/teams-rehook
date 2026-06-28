from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings_overrides import load_overrides, reset_override_state
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
        load_overrides(db)
        yield db


@contextmanager
def make_client(db_session: Session, monkeypatch: pytest.MonkeyPatch, **env: str) -> Iterator[TestClient]:
    from app.core.config import get_settings

    defaults = {
        "BOT_DELIVERY_MODE": "mock",
        "LOG_RETENTION_DAYS": "7",
        "WEBHOOK_MAX_PAYLOAD_BYTES": "64000",
        "SETTINGS_ENC_KEY": "test-settings-encryption-key",
    }
    defaults.update(env)
    for key, value in defaults.items():
        monkeypatch.setenv(key, value)
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


def login_admin(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "change-me-admin-password"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_list_settings_returns_env_defaults(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login_admin(client)
        response = client.get("/api/v1/admin/settings", headers={"X-CSRF-Token": csrf})
        assert response.status_code == 200
        payload = response.json()
        delivery = next(item for item in payload if item["key"] == "bot_delivery_mode")
        assert delivery["env_default"] == "mock"
        assert delivery["effective_value"] == "mock"
        assert delivery["is_overridden"] is False
        bot_enabled = next(item for item in payload if item["key"] == "bot_framework_enabled")
        assert bot_enabled["type"] == "bool"
        assert bot_enabled["env_default"] == "true"
        assert bot_enabled["effective_value"] == "true"
        trust_xff = next(item for item in payload if item["key"] == "trust_x_forwarded_for")
        assert trust_xff["type"] == "bool"
        assert trust_xff["env_default"] == "false"
        assert trust_xff["effective_value"] == "false"
        trusted_proxies = next(item for item in payload if item["key"] == "trusted_proxy_ips")
        assert trusted_proxies["type"] == "string"
        assert trusted_proxies["effective_value"] == ""


def test_override_and_reset_setting(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch, LOG_RETENTION_DAYS="7") as client:
        csrf = login_admin(client)
        put = client.put(
            "/api/v1/admin/settings/log_retention_days",
            headers={"X-CSRF-Token": csrf},
            json={"value": "14"},
        )
        assert put.status_code == 200
        updated = put.json()
        assert updated["effective_value"] == "14"
        assert updated["is_overridden"] is True
        assert updated["env_default"] == "7"

        delete = client.delete(
            "/api/v1/admin/settings/log_retention_days",
            headers={"X-CSRF-Token": csrf},
        )
        assert delete.status_code == 204

        get = client.get("/api/v1/admin/settings", headers={"X-CSRF-Token": csrf})
        retention = next(item for item in get.json() if item["key"] == "log_retention_days")
        assert retention["effective_value"] == "7"
        assert retention["is_overridden"] is False


def test_secret_override_is_masked(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login_admin(client)
        put = client.put(
            "/api/v1/admin/settings/ms_app_client_secret",
            headers={"X-CSRF-Token": csrf},
            json={"value": "example-secret-value"},
        )
        assert put.status_code == 200
        updated = put.json()
        assert updated["effective_value"] == "configured"
        assert "example-secret-value" not in str(updated)


def test_trusted_proxy_settings_can_be_overridden_and_validated(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login_admin(client)
        enabled = client.put(
            "/api/v1/admin/settings/trust_x_forwarded_for",
            headers={"X-CSRF-Token": csrf},
            json={"value": "true"},
        )
        assert enabled.status_code == 200
        assert enabled.json()["effective_value"] == "true"

        proxies = client.put(
            "/api/v1/admin/settings/trusted_proxy_ips",
            headers={"X-CSRF-Token": csrf},
            json={"value": "127.0.0.1, 10.0.0.0/24"},
        )
        assert proxies.status_code == 200
        assert proxies.json()["effective_value"] == "127.0.0.1/32,10.0.0.0/24"

        rejected = client.put(
            "/api/v1/admin/settings/trusted_proxy_ips",
            headers={"X-CSRF-Token": csrf},
            json={"value": "127.0.0.1, not-an-ip"},
        )
        assert rejected.status_code == 400
        assert rejected.json()["detail"] == "Trusted proxy IPs must be comma-separated IP addresses or CIDR ranges"


def test_graph_delivery_requires_graph_lookup_enabled(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login_admin(client)
        rejected = client.put(
            "/api/v1/admin/settings/graph_lookup_enabled",
            headers={"X-CSRF-Token": csrf},
            json={"value": "false"},
        )
        assert rejected.status_code == 400
        assert rejected.json()["detail"] == "Graph delivery requires Graph lookup to be enabled"

        delivery = client.put(
            "/api/v1/admin/settings/graph_delivery_enabled",
            headers={"X-CSRF-Token": csrf},
            json={"value": "false"},
        )
        assert delivery.status_code == 200

        lookup = client.put(
            "/api/v1/admin/settings/graph_lookup_enabled",
            headers={"X-CSRF-Token": csrf},
            json={"value": "false"},
        )
        assert lookup.status_code == 200
        assert lookup.json()["effective_value"] == "false"
