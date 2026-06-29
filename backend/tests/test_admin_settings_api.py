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
from app.models import AppSetting, Organization, User
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
        "APP_PUBLIC_BASE_URL": "http://localhost:5173",
        "FRONTEND_BASE_URL": "http://localhost:5173",
        "CORS_ORIGINS": "http://localhost:5173,http://localhost",
        "SESSION_SECURE_COOKIE": "false",
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
        bot_enabled = next(item for item in payload if item["key"] == "bot_framework_enabled")
        assert bot_enabled["type"] == "bool"
        assert bot_enabled["source"] == "application"
        assert bot_enabled["env_default"] == "true"
        assert bot_enabled["effective_value"] == "true"
        assert bot_enabled["is_overridden"] is False
        cors_origins = next(item for item in payload if item["key"] == "cors_origins")
        assert cors_origins["type"] == "string"
        assert cors_origins["source"] == "environment"
        assert cors_origins["env_default"] == "http://localhost:5173,http://localhost"
        assert cors_origins["effective_value"] == "http://localhost:5173,http://localhost"
        session_cookie = next(item for item in payload if item["key"] == "session_secure_cookie")
        assert session_cookie["type"] == "bool"
        assert session_cookie["env_default"] == "false"
        assert session_cookie["effective_value"] == "false"
        trust_xff = next(item for item in payload if item["key"] == "trust_x_forwarded_for")
        assert trust_xff["type"] == "bool"
        assert trust_xff["env_default"] == "false"
        assert trust_xff["effective_value"] == "false"
        assert all(item["key"] != "trusted_proxy_ips" for item in payload)


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


def test_token_scopes_are_env_only_settings(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    db_session.add(
        AppSetting(key="botframework_scope", value="https://wrong.example.com/.default", is_secret=False)
    )
    db_session.add(AppSetting(key="graph_scope", value="https://wrong.example.com/.default", is_secret=False))
    db_session.commit()

    with make_client(db_session, monkeypatch) as client:
        from app.core.settings_overrides import get_effective_settings

        csrf = login_admin(client)
        response = client.get("/api/v1/admin/settings", headers={"X-CSRF-Token": csrf})
        assert response.status_code == 200
        keys = {item["key"] for item in response.json()}
        assert "botframework_scope" not in keys
        assert "graph_scope" not in keys

        for key in ("botframework_scope", "graph_scope"):
            put = client.put(
                f"/api/v1/admin/settings/{key}",
                headers={"X-CSRF-Token": csrf},
                json={"value": "https://override.example.com/.default"},
            )
            assert put.status_code == 404
            assert put.json()["detail"] == "Unknown setting"

            delete = client.delete(f"/api/v1/admin/settings/{key}", headers={"X-CSRF-Token": csrf})
            assert delete.status_code == 404
            assert delete.json()["detail"] == "Unknown setting"

        effective = get_effective_settings()
        assert effective.botframework_scope == "https://api.botframework.com/.default"
        assert effective.graph_scope == "https://graph.microsoft.com/.default"


def test_trust_x_forwarded_for_can_be_overridden(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login_admin(client)
        enabled = client.put(
            "/api/v1/admin/settings/trust_x_forwarded_for",
            headers={"X-CSRF-Token": csrf},
            json={"value": "true"},
        )
        assert enabled.status_code == 200
        assert enabled.json()["effective_value"] == "true"

        rejected = client.put(
            "/api/v1/admin/settings/trusted_proxy_ips",
            headers={"X-CSRF-Token": csrf},
            json={"value": "127.0.0.1"},
        )
        assert rejected.status_code == 404
        assert rejected.json()["detail"] == "Unknown setting"


def test_readiness_reports_proxy_trust_chain(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(
        db_session,
        monkeypatch,
        COMPOSE_APP_SUBNET="172.30.0.0/24",
        TRUSTED_PROXY_IPS="10.0.0.10, 10.0.0.0/24",
    ) as client:
        csrf = login_admin(client)
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf})
        assert response.status_code == 200
        runtime = response.json()["runtime"]
        assert runtime["compose_app_subnet"] == "172.30.0.0/24"
        assert runtime["trusted_proxy_ips"] == "10.0.0.10, 10.0.0.0/24"
        assert runtime["trusted_proxy_chain"] == "172.30.0.0/24,10.0.0.10/32,10.0.0.0/24"


def test_browser_runtime_settings_can_be_overridden_and_validated(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login_admin(client)
        secure_cookie = client.put(
            "/api/v1/admin/settings/session_secure_cookie",
            headers={"X-CSRF-Token": csrf},
            json={"value": "true"},
        )
        assert secure_cookie.status_code == 200
        assert secure_cookie.json()["effective_value"] == "true"

        cors = client.put(
            "/api/v1/admin/settings/cors_origins",
            headers={"X-CSRF-Token": csrf},
            json={"value": "https://ops.example.com, http://localhost:8080/"},
        )
        assert cors.status_code == 200
        assert cors.json()["effective_value"] == "https://ops.example.com,http://localhost:8080"

        invalid_cors = client.put(
            "/api/v1/admin/settings/cors_origins",
            headers={"X-CSRF-Token": csrf},
            json={"value": "https://ops.example.com/app"},
        )
        assert invalid_cors.status_code == 400
        assert invalid_cors.json()["detail"] == "CORS origins must contain scheme, host, and optional port only"


def test_frontend_url_override_keeps_cors_origins_in_sync(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login_admin(client)
        first = client.put(
            "/api/v1/admin/settings/frontend_base_url",
            headers={"X-CSRF-Token": csrf},
            json={"value": "https://ops.example.com"},
        )
        assert first.status_code == 200

        second = client.put(
            "/api/v1/admin/settings/frontend_base_url",
            headers={"X-CSRF-Token": csrf},
            json={"value": "https://portal.example.com"},
        )
        assert second.status_code == 200

        settings = client.get("/api/v1/admin/settings", headers={"X-CSRF-Token": csrf})
        assert settings.status_code == 200
        items = {item["key"]: item for item in settings.json()}
        assert items["frontend_base_url"]["effective_value"] == "https://portal.example.com"
        assert items["cors_origins"]["effective_value"] == "https://portal.example.com"
        assert items["cors_origins"]["is_overridden"] is True


def test_overridden_cors_origins_drive_preflight_responses(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login_admin(client)
        updated = client.put(
            "/api/v1/admin/settings/cors_origins",
            headers={"X-CSRF-Token": csrf},
            json={"value": "https://ops.example.com"},
        )
        assert updated.status_code == 200

        preflight = client.options(
            "/api/v1/admin/settings",
            headers={
                "Origin": "https://ops.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-CSRF-Token",
            },
        )
        assert preflight.status_code == 204
        assert preflight.headers["access-control-allow-origin"] == "https://ops.example.com"
        assert preflight.headers["access-control-allow-credentials"] == "true"
        assert preflight.headers["access-control-allow-methods"] == "GET"
        assert preflight.headers["access-control-allow-headers"] == "X-CSRF-Token"


def test_session_cookie_uses_effective_secure_flag(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(db_session, monkeypatch) as client:
        csrf = login_admin(client)
        updated = client.put(
            "/api/v1/admin/settings/session_secure_cookie",
            headers={"X-CSRF-Token": csrf},
            json={"value": "true"},
        )
        assert updated.status_code == 200

        response = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "change-me-admin-password"},
        )
        assert response.status_code == 200
        assert "Secure" in response.headers["set-cookie"]


def test_delivery_feature_settings_are_application_managed(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
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
        assert delivery.json()["source"] == "application"
        assert delivery.json()["effective_value"] == "false"
        assert delivery.json()["is_overridden"] is False

        lookup = client.put(
            "/api/v1/admin/settings/graph_lookup_enabled",
            headers={"X-CSRF-Token": csrf},
            json={"value": "false"},
        )
        assert lookup.status_code == 200
        assert lookup.json()["effective_value"] == "false"
        assert lookup.json()["is_overridden"] is False
