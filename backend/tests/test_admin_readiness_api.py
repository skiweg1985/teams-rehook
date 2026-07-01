from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, urlparse
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings_overrides import load_overrides, reset_override_state
from app.core.encrypted_secrets import decrypt_secret, encrypt_secret
from app.database import Base, get_db
from app.main import create_app
from app.models import AuditEvent, GraphDelegatedCredential, GraphDelegatedOAuthPendingCredential, Organization, User
from app.security import hash_secret
from app.schemas import OAuthAppDiagnosticsOut, OAuthTenantDiagnosticsOut
from app.services import graph_delegated_auth
from app.services.graph_delegated_auth import GraphDelegatedAuthError
from app.services.graph_targets import GraphRequestError
from app.services.teams_bot import BotDeliveryError


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


@pytest.fixture(autouse=True)
def settings_enc_key_env(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings

    monkeypatch.setenv("SETTINGS_ENC_KEY", "test-settings-encryption-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@contextmanager
def make_client(db_session: Session, monkeypatch: pytest.MonkeyPatch, **env: str) -> Iterator[TestClient]:
    from app.core.config import get_settings

    defaults = {
        "BOT_DELIVERY_MODE": "mock",
        "MS_APP_TENANT_ID": "",
        "MS_APP_CLIENT_ID": "",
        "MS_APP_CLIENT_SECRET": "",
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


def fake_jwt(**claims) -> str:
    header = _jwt_part({"alg": "none", "typ": "JWT"})
    payload = _jwt_part(claims)
    return f"{header}.{payload}.signature"


def _jwt_part(value: dict) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).decode("utf-8")
    return encoded.rstrip("=")


def fake_token_response(audience: str = "https://graph.microsoft.com"):
    from app.routers.admin import OAuthTokenResponse

    token = fake_jwt(
        aud=audience,
        iss="https://login.microsoftonline.com/tenant/v2.0",
        roles=["User.Read.All", "Team.ReadBasic.All"],
    )
    return OAuthTokenResponse(access_token=token, expires_in_seconds=3600, claims={
        "aud": audience,
        "iss": "https://login.microsoftonline.com/tenant/v2.0",
        "roles": ["User.Read.All", "Team.ReadBasic.All"],
    })


def metadata_pair():
    return (
        OAuthAppDiagnosticsOut(
            metadata_checked=True,
            available=True,
            display_name="Teams Rehook App",
            app_id="client",
            service_principal_id="sp-id",
            account_enabled=True,
            service_principal_type="Application",
        ),
        OAuthTenantDiagnosticsOut(
            metadata_checked=True,
            available=True,
            display_name="Example Tenant",
            primary_domain="example.com",
        ),
    )


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
    assert body["bot"]["auth_status"] == "mock"
    assert body["bot"]["token_checked"] is False
    assert body["bot"]["credentials_configured"] is False
    assert body["bot"]["credential_fields"]["tenant_id"] == "missing"
    assert "graph" not in body
    assert body["graph_lookup"]["ready"] is False
    assert body["graph_lookup"]["auth_status"] == "incomplete"
    assert body["graph_delivery"]["ready"] is False
    assert body["graph_delivery"]["auth_status"] == "missing"
    assert body["runtime"]["settings_encryption_key_source"] == "configured"
    assert body["runtime"]["settings_encryption_ready"] is True


def test_readiness_marks_disabled_application_features_without_token_checks(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    with make_client(db_session, monkeypatch) as client:
        csrf_token = login_admin(client)
        assert client.put(
            "/api/v1/admin/settings/graph_delivery_enabled",
            headers={"X-CSRF-Token": csrf_token},
            json={"value": "false"},
        ).status_code == 200
        assert client.put(
            "/api/v1/admin/settings/graph_lookup_enabled",
            headers={"X-CSRF-Token": csrf_token},
            json={"value": "false"},
        ).status_code == 200
        assert client.put(
            "/api/v1/admin/settings/bot_framework_enabled",
            headers={"X-CSRF-Token": csrf_token},
            json={"value": "false"},
        ).status_code == 200
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["bot"]["enabled"] is False
    assert body["bot"]["auth_status"] == "disabled"
    assert body["bot"]["token_checked"] is False
    assert body["graph_lookup"]["enabled"] is False
    assert body["graph_lookup"]["auth_status"] == "disabled"
    assert body["graph_delivery"]["enabled"] is False
    assert body["graph_delivery"]["auth_status"] == "disabled"


def test_readiness_reports_real_delivery_missing_bot_credentials(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    with make_client(db_session, monkeypatch, BOT_DELIVERY_MODE="real") as client:
        csrf_token = login_admin(client)
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["delivery_mode"] == "real"
    assert body["bot"]["ready"] is False
    assert body["bot"]["auth_status"] == "incomplete"
    assert body["bot"]["token_checked"] is False
    assert "MS_APP_TENANT_ID" in body["bot"]["message"]


def test_readiness_checks_bot_token_for_real_delivery(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.routers.admin._fetch_oauth_token",
        lambda **kwargs: fake_token_response(kwargs["scope"]),
    )
    monkeypatch.setattr("app.routers.admin._metadata_for_credentials", lambda **kwargs: metadata_pair())
    with make_client(
        db_session,
        monkeypatch,
        BOT_DELIVERY_MODE="real",
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
    ) as client:
        csrf_token = login_admin(client)
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["bot"]["ready"] is True
    assert body["bot"]["auth_status"] == "ready"
    assert body["bot"]["token_checked"] is True
    assert body["bot"]["token_request_succeeded"] is True
    assert body["bot"]["credential_fields"] == {
        "tenant_id": "configured",
        "client_id": "configured",
        "client_secret": "configured",
    }
    assert body["bot"]["oauth"]["tenant_id"] == "tenant"
    assert body["bot"]["oauth"]["client_id"] == "client"
    assert body["bot"]["oauth"]["scope"] == "https://api.botframework.com/.default"
    assert body["bot"]["oauth"]["token"]["succeeded"] is True
    assert body["bot"]["oauth"]["token"]["expires_in_seconds"] == 3600
    assert body["bot"]["oauth"]["token"]["audience"] == "https://api.botframework.com/.default"
    assert body["bot"]["oauth"]["token"]["roles"] == ["User.Read.All", "Team.ReadBasic.All"]
    assert body["bot"]["oauth"]["app"]["display_name"] == "Teams Rehook App"
    assert body["bot"]["oauth"]["app"]["service_principal_id"] == "sp-id"
    assert body["bot"]["oauth"]["tenant"]["display_name"] == "Example Tenant"


def test_readiness_reports_bot_token_error_without_leaking_details(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    def fail_token(**kwargs):
        if kwargs["request_error"] is BotDeliveryError:
            raise BotDeliveryError("raw provider detail that should not leak")
        raise GraphRequestError("raw graph detail that should not leak")

    monkeypatch.setattr("app.routers.admin._fetch_oauth_token", fail_token)
    with make_client(
        db_session,
        monkeypatch,
        BOT_DELIVERY_MODE="real",
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
    ) as client:
        csrf_token = login_admin(client)
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["bot"]["ready"] is False
    assert body["bot"]["auth_status"] == "token_error"
    assert body["bot"]["token_checked"] is True
    assert body["bot"]["token_request_succeeded"] is False
    assert body["bot"]["oauth"]["token"]["checked"] is True
    assert body["bot"]["oauth"]["token"]["succeeded"] is False
    assert "raw provider detail" not in body["bot"]["message"]


def test_readiness_reports_shared_ms_app_credentials(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.routers.admin._fetch_oauth_token",
        lambda **kwargs: fake_token_response(kwargs["scope"]),
    )
    monkeypatch.setattr("app.routers.admin._metadata_for_credentials", lambda **kwargs: metadata_pair())
    monkeypatch.setattr("app.routers.admin._metadata_from_graph_token", lambda access_token, client_id: metadata_pair())
    with make_client(
        db_session,
        monkeypatch,
        BOT_DELIVERY_MODE="real",
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
    ) as client:
        csrf_token = login_admin(client)
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["bot"]["ready"] is True
    assert body["graph_lookup"]["ready"] is True
    assert body["graph_lookup"]["credential_source"] == "ms_app"
    assert body["graph_lookup"]["auth_status"] == "ready"
    assert body["graph_lookup"]["token_checked"] is True
    assert body["graph_lookup"]["credential_fields"] == {
        "tenant_id": "configured",
        "client_id": "configured",
        "client_secret": "configured",
    }
    assert body["graph_lookup"]["oauth"]["credential_source"] == "ms_app"
    assert body["graph_lookup"]["oauth"]["token"]["expires_in_seconds"] == 3600
    assert body["graph_lookup"]["oauth"]["app"]["available"] is True
    assert body["graph_lookup"]["oauth"]["tenant"]["primary_domain"] == "example.com"
    assert body["bot"]["oauth"]["credential_source"] == "ms_app"


def test_readiness_keeps_graph_ready_when_metadata_is_unavailable(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.routers.admin._fetch_oauth_token",
        lambda **kwargs: fake_token_response(kwargs["scope"]),
    )
    monkeypatch.setattr(
        "app.routers.admin._metadata_from_graph_token",
        lambda access_token, client_id: (
            OAuthAppDiagnosticsOut(
                metadata_checked=True,
                available=False,
                message="App metadata is not available with the current Graph permissions.",
            ),
            OAuthTenantDiagnosticsOut(
                metadata_checked=True,
                available=False,
                message="Tenant metadata is not available with the current Graph permissions.",
            ),
        ),
    )
    with make_client(
        db_session,
        monkeypatch,
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
    ) as client:
        csrf_token = login_admin(client)
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["graph_lookup"]["ready"] is True
    assert body["graph_lookup"]["auth_status"] == "permission_warning"
    assert body["graph_lookup"]["token_request_succeeded"] is True
    assert body["graph_lookup"]["oauth"]["app"]["metadata_checked"] is True
    assert body["graph_lookup"]["oauth"]["app"]["available"] is False
    assert body["graph_lookup"]["oauth"]["tenant"]["metadata_checked"] is True
    assert body["graph_lookup"]["oauth"]["tenant"]["available"] is False
    assert "raw" not in body["graph_lookup"]["oauth"]["app"]["message"]


def test_readiness_reports_graph_token_error_without_leaking_details(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    def fail_token(**kwargs):
        raise GraphRequestError("raw graph response that should not leak")

    monkeypatch.setattr("app.routers.admin._fetch_oauth_token", fail_token)
    with make_client(
        db_session,
        monkeypatch,
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
    ) as client:
        csrf_token = login_admin(client)
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["graph_lookup"]["ready"] is False
    assert body["graph_lookup"]["auth_status"] == "token_error"
    assert body["graph_lookup"]["token_checked"] is True
    assert body["graph_lookup"]["token_request_succeeded"] is False
    assert body["graph_lookup"]["oauth"]["token"]["checked"] is True
    assert body["graph_lookup"]["oauth"]["token"]["succeeded"] is False
    assert "raw graph response" not in body["graph_lookup"]["message"]


def add_delegated_credential(
    db_session: Session,
    *,
    scopes: str = "offline_access ChannelMessage.Send ChatMessage.Send Chat.ReadBasic Chat.Create User.Read",
) -> GraphDelegatedCredential:
    organization_id = db_session.query(Organization.id).filter_by(slug="default").scalar()
    credential = GraphDelegatedCredential(
        organization_id=organization_id,
        tenant_id="tenant",
        client_id="client",
        scopes=scopes,
        encrypted_refresh_token=encrypt_secret("refresh-token"),
        service_user_id="old-user-id",
        service_user_display_name="Old Service User",
        service_user_principal_name="old-service@example.com",
        last_status="ready",
    )
    db_session.add(credential)
    db_session.commit()
    return credential


def delegated_token_response(scope: str = "offline_access ChannelMessage.Send ChatMessage.Send Chat.ReadBasic Chat.Create User.Read"):
    return {
        "access_token": fake_jwt(
            oid="service-user-id",
            name="Graph Service User",
            preferred_username="graph-service@example.com",
        ),
        "expires_in": 3600,
        "scope": scope,
    }


def test_readiness_reports_missing_graph_delivery_credential(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    with make_client(
        db_session,
        monkeypatch,
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
    ) as client:
        csrf_token = login_admin(client)
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["graph_delivery"]["ready"] is False
    assert body["graph_delivery"]["auth_status"] == "missing"
    assert body["graph_delivery"]["token_checked"] is False
    assert body["graph_delivery"]["credential_source"] == "missing"
    assert body["graph_delivery"]["tenant_id"] == "tenant"
    assert body["graph_delivery"]["client_id"] == "client"
    assert body["graph_delivery"]["required_scopes"] == [
        "offline_access",
        "ChannelMessage.Send",
        "ChatMessage.Send",
        "Chat.ReadBasic",
        "Chat.Create",
        "User.Read",
    ]
    assert "refresh-token" not in json.dumps(body["graph_delivery"])


def test_readiness_reports_ready_graph_delivery_credential(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    add_delegated_credential(db_session)
    monkeypatch.setattr("app.routers.admin._fetch_oauth_token", lambda **kwargs: fake_token_response(kwargs["scope"]))
    monkeypatch.setattr("app.routers.admin._metadata_from_graph_token", lambda access_token, client_id: metadata_pair())
    monkeypatch.setattr(graph_delegated_auth, "_request_token", lambda **kwargs: delegated_token_response())
    with make_client(
        db_session,
        monkeypatch,
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
    ) as client:
        csrf_token = login_admin(client)
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["graph_delivery"]["ready"] is True
    assert body["graph_delivery"]["auth_status"] == "ready"
    assert body["graph_delivery"]["token_checked"] is True
    assert body["graph_delivery"]["token_request_succeeded"] is True
    assert body["graph_delivery"]["credential_source"] == "delegated_service_user"
    assert body["graph_delivery"]["service_user_id"] == "service-user-id"
    assert body["graph_delivery"]["service_user_display_name"] == "Graph Service User"
    assert body["graph_delivery"]["service_user_principal_name"] == "graph-service@example.com"
    assert body["graph_delivery"]["missing_scopes"] == []
    assert "refresh-token" not in json.dumps(body["graph_delivery"])


def test_readiness_reports_graph_delivery_expired_without_raw_details(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    add_delegated_credential(db_session)

    def expired_token(**kwargs):
        raise graph_delegated_auth._ExpiredRefreshTokenError("raw invalid_grant body")

    monkeypatch.setattr(graph_delegated_auth, "_request_token", expired_token)
    with make_client(
        db_session,
        monkeypatch,
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
    ) as client:
        csrf_token = login_admin(client)
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["graph_delivery"]["ready"] is False
    assert body["graph_delivery"]["auth_status"] == "expired"
    assert body["graph_delivery"]["token_checked"] is True
    assert body["graph_delivery"]["token_request_succeeded"] is False
    assert "raw invalid_grant body" not in json.dumps(body["graph_delivery"])


def test_readiness_reports_graph_delivery_token_error_without_raw_details(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    add_delegated_credential(db_session)

    def token_error(**kwargs):
        raise GraphDelegatedAuthError("raw provider body")

    monkeypatch.setattr(graph_delegated_auth, "_request_token", token_error)
    with make_client(
        db_session,
        monkeypatch,
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
    ) as client:
        csrf_token = login_admin(client)
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["graph_delivery"]["ready"] is False
    assert body["graph_delivery"]["auth_status"] == "token_error"
    assert body["graph_delivery"]["token_checked"] is True
    assert body["graph_delivery"]["token_request_succeeded"] is False
    assert "raw provider body" not in json.dumps(body["graph_delivery"])


def test_readiness_reports_graph_delivery_settings_key_error(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    add_delegated_credential(db_session)

    with make_client(
        db_session,
        monkeypatch,
        SETTINGS_ENC_KEY="wrong-settings-encryption-key",
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
    ) as client:
        csrf_token = login_admin(client)
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["graph_delivery"]["ready"] is False
    assert body["graph_delivery"]["auth_status"] == "configuration_error"
    assert body["graph_delivery"]["token_checked"] is False
    assert "SETTINGS_ENC_KEY" in body["graph_delivery"]["message"]
    assert "refresh-token" not in json.dumps(body["graph_delivery"])


def test_readiness_reports_graph_delivery_missing_required_scopes(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    add_delegated_credential(db_session, scopes="offline_access User.Read")
    monkeypatch.setattr(graph_delegated_auth, "_request_token", lambda **kwargs: delegated_token_response("offline_access User.Read"))
    with make_client(
        db_session,
        monkeypatch,
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
    ) as client:
        csrf_token = login_admin(client)
        response = client.get("/api/v1/admin/readiness", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["graph_delivery"]["ready"] is False
    assert body["graph_delivery"]["auth_status"] == "permission_warning"
    assert body["graph_delivery"]["token_request_succeeded"] is True
    assert body["graph_delivery"]["missing_scopes"] == ["ChannelMessage.Send", "ChatMessage.Send", "Chat.ReadBasic", "Chat.Create"]


def test_graph_delivery_oauth_start_returns_authorization_url(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    with make_client(
        db_session,
        monkeypatch,
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
        APP_PUBLIC_BASE_URL="https://app.example.com",
    ) as client:
        csrf_token = login_admin(client)
        response = client.post("/api/v1/admin/graph-delivery/oauth/start", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    parsed = urlparse(body["authorization_url"])
    query = parse_qs(parsed.query)
    assert parsed.path == "/tenant/oauth2/v2.0/authorize"
    assert query["redirect_uri"] == ["https://app.example.com/api/v1/admin/graph-delivery/oauth/callback"]
    scopes = query["scope"][0].split()
    assert "Chat.ReadBasic" in scopes
    assert "refresh-token" not in json.dumps(body)
    assert query["state"][0]


def test_graph_delivery_oauth_callback_creates_pending_credential_and_redirects(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, str] = {}
    active = add_delegated_credential(db_session)

    def fake_exchange(db, **kwargs):
        captured.update(kwargs)
        pending = GraphDelegatedOAuthPendingCredential(
            organization_id=kwargs["organization_id"],
            created_by_id=kwargs["created_by_id"],
            tenant_id="tenant",
            client_id="client",
            scopes="offline_access User.Read",
            encrypted_refresh_token=encrypt_secret("pending-refresh-token"),
            service_user_id="pending-user-id",
            service_user_display_name="Pending User",
            service_user_principal_name="pending@example.com",
            expires_at=graph_delegated_auth.utcnow() + graph_delegated_auth.PENDING_CREDENTIAL_TTL,
        )
        db.add(pending)
        db.flush()
        return pending

    monkeypatch.setattr("app.routers.admin.exchange_authorization_code_to_pending", fake_exchange)
    with make_client(
        db_session,
        monkeypatch,
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
        APP_PUBLIC_BASE_URL="https://app.example.com",
        FRONTEND_BASE_URL="https://ui.example.com",
    ) as client:
        csrf_token = login_admin(client)
        start = client.post("/api/v1/admin/graph-delivery/oauth/start", headers={"X-CSRF-Token": csrf_token})
        state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
        response = client.get(
            "/api/v1/admin/graph-delivery/oauth/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 303
    pending = db_session.query(GraphDelegatedOAuthPendingCredential).one()
    assert response.headers["location"] == f"https://ui.example.com/settings/graph-delivery/confirm?pending_id={pending.id}"
    assert captured["code"] == "auth-code"
    assert captured["redirect_uri"] == "https://app.example.com/api/v1/admin/graph-delivery/oauth/callback"
    assert captured["scopes"] == graph_delegated_auth.DEFAULT_DELEGATED_GRAPH_SCOPES
    assert captured["created_by_id"]
    row = db_session.query(GraphDelegatedCredential).one()
    assert row.id == active.id
    assert row.service_user_display_name == "Old Service User"
    assert "pending-refresh-token" not in json.dumps(dict(response.headers))


def test_graph_delivery_oauth_pending_get_returns_safe_metadata(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    org = db_session.query(Organization).one()
    pending = GraphDelegatedOAuthPendingCredential(
        organization_id=org.id,
        tenant_id="tenant",
        client_id="client",
        scopes="offline_access User.Read",
        encrypted_refresh_token=encrypt_secret("pending-refresh-token"),
        service_user_id="pending-user-id",
        service_user_display_name="Pending User",
        service_user_principal_name="pending@example.com",
        expires_at=graph_delegated_auth.utcnow() + graph_delegated_auth.PENDING_CREDENTIAL_TTL,
    )
    db_session.add(pending)
    db_session.commit()

    with make_client(db_session, monkeypatch) as client:
        csrf_token = login_admin(client)
        response = client.get(f"/api/v1/admin/graph-delivery/oauth/pending/{pending.id}", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["service_user_display_name"] == "Pending User"
    assert body["service_user_principal_name"] == "pending@example.com"
    assert body["tenant_id"] == "tenant"
    assert body["client_id"] == "client"
    assert "User.Read" in body["scopes"]
    assert "pending-refresh-token" not in json.dumps(body)


def test_graph_delivery_oauth_pending_confirm_promotes_credential(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    active = add_delegated_credential(db_session)
    pending = GraphDelegatedOAuthPendingCredential(
        organization_id=active.organization_id,
        tenant_id="tenant",
        client_id="client",
        scopes="offline_access User.Read ChannelMessage.Send ChatMessage.Send Chat.ReadBasic Chat.Create",
        encrypted_refresh_token=encrypt_secret("pending-refresh-token"),
        service_user_id="pending-user-id",
        service_user_display_name="Pending User",
        service_user_principal_name="pending@example.com",
        expires_at=graph_delegated_auth.utcnow() + graph_delegated_auth.PENDING_CREDENTIAL_TTL,
    )
    db_session.add(pending)
    db_session.commit()
    monkeypatch.setattr(
        graph_delegated_auth,
        "_request_token",
        lambda **kwargs: {
            "access_token": fake_jwt(
                oid="pending-user-id",
                name="Pending User",
                preferred_username="pending@example.com",
            ),
            "expires_in": 3600,
            "scope": "offline_access User.Read ChannelMessage.Send ChatMessage.Send Chat.ReadBasic Chat.Create",
        },
    )

    with make_client(db_session, monkeypatch, MS_APP_TENANT_ID="tenant", MS_APP_CLIENT_ID="client", MS_APP_CLIENT_SECRET="secret") as client:
        csrf_token = login_admin(client)
        response = client.post(
            f"/api/v1/admin/graph-delivery/oauth/pending/{pending.id}/confirm",
            headers={"X-CSRF-Token": csrf_token},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["graph_delivery"]["service_user_display_name"] == "Pending User"
    assert body["runtime"]["app_public_base_url"] == "http://localhost:5173"
    row = db_session.query(GraphDelegatedCredential).one()
    assert row.id == active.id
    assert row.service_user_display_name == "Pending User"
    assert decrypt_secret(row.encrypted_refresh_token) == "pending-refresh-token"
    assert db_session.query(GraphDelegatedOAuthPendingCredential).count() == 0
    audit = db_session.query(AuditEvent).filter_by(action="graph_delivery.oauth.confirmed").one()
    assert audit.organization_id == active.organization_id


def test_graph_delivery_oauth_pending_cancel_keeps_active_credential(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    active = add_delegated_credential(db_session)
    pending = GraphDelegatedOAuthPendingCredential(
        organization_id=active.organization_id,
        encrypted_refresh_token=encrypt_secret("pending-refresh-token"),
        service_user_display_name="Pending User",
        expires_at=graph_delegated_auth.utcnow() + graph_delegated_auth.PENDING_CREDENTIAL_TTL,
    )
    db_session.add(pending)
    db_session.commit()

    with make_client(db_session, monkeypatch) as client:
        csrf_token = login_admin(client)
        response = client.delete(f"/api/v1/admin/graph-delivery/oauth/pending/{pending.id}", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 204
    row = db_session.query(GraphDelegatedCredential).one()
    assert row.id == active.id
    assert row.service_user_display_name == "Old Service User"
    assert db_session.query(GraphDelegatedOAuthPendingCredential).count() == 0


def test_graph_delivery_oauth_pending_expired_is_rejected(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    org = db_session.query(Organization).one()
    pending = GraphDelegatedOAuthPendingCredential(
        organization_id=org.id,
        encrypted_refresh_token=encrypt_secret("pending-refresh-token"),
        expires_at=graph_delegated_auth.utcnow() - graph_delegated_auth.PENDING_CREDENTIAL_TTL,
    )
    db_session.add(pending)
    db_session.commit()

    with make_client(db_session, monkeypatch) as client:
        csrf_token = login_admin(client)
        response = client.post(
            f"/api/v1/admin/graph-delivery/oauth/pending/{pending.id}/confirm",
            headers={"X-CSRF-Token": csrf_token},
        )

    assert response.status_code == 404
    assert db_session.query(GraphDelegatedOAuthPendingCredential).count() == 0


def test_graph_delivery_oauth_callback_rejects_invalid_state(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    with make_client(
        db_session,
        monkeypatch,
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
    ) as client:
        login_admin(client)
        response = client.get(
            "/api/v1/admin/graph-delivery/oauth/callback",
            params={"code": "auth-code", "state": "bad-state"},
        )

    assert response.status_code == 400
    assert "state" in response.json()["detail"]


def test_graph_delivery_oauth_disconnect_removes_credential(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    add_delegated_credential(db_session)

    with make_client(db_session, monkeypatch) as client:
        csrf_token = login_admin(client)
        response = client.delete("/api/v1/admin/graph-delivery/oauth", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 204
    assert db_session.query(GraphDelegatedCredential).count() == 0


def test_delivery_auth_refresh_requires_csrf(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    with make_client(db_session, monkeypatch) as client:
        login_admin(client)
        response = client.post("/api/v1/admin/delivery-auth/refresh")

    assert response.status_code == 403


def test_delivery_auth_refresh_resets_enabled_token_managers_and_returns_readiness(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    add_delegated_credential(db_session)
    calls = {"bot": 0, "graph": 0, "delegated": 0}

    def bot_token(settings):
        calls["bot"] += 1
        return "bot-token", 3600

    def graph_token(settings):
        calls["graph"] += 1
        return "graph-token", 3600

    def delegated_token(**kwargs):
        calls["delegated"] += 1
        return delegated_token_response()

    monkeypatch.setattr("app.services.teams_bot.fetch_botframework_token", bot_token)
    monkeypatch.setattr("app.services.graph_targets.fetch_graph_token", graph_token)
    monkeypatch.setattr(graph_delegated_auth, "_request_token", delegated_token)
    monkeypatch.setattr("app.routers.admin._fetch_oauth_token", lambda **kwargs: fake_token_response(kwargs["scope"]))
    monkeypatch.setattr("app.routers.admin._metadata_from_graph_token", lambda access_token, client_id: metadata_pair())

    with make_client(
        db_session,
        monkeypatch,
        BOT_DELIVERY_MODE="real",
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
    ) as client:
        csrf_token = login_admin(client)
        response = client.post("/api/v1/admin/delivery-auth/refresh", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["bot_delivery"]["status"] == "refreshed"
    assert body["graph_lookup"]["status"] == "refreshed"
    assert body["graph_delivery"]["status"] == "refreshed"
    assert body["bot_inbound_auth"]["status"] == "cleared"
    assert body["readiness"]["bot"]["ready"] is True
    assert body["readiness"]["graph_lookup"]["ready"] is True
    assert body["readiness"]["graph_delivery"]["ready"] is True
    assert calls["bot"] == 1
    assert calls["graph"] == 1
    assert calls["delegated"] >= 1
    assert "bot-token" not in json.dumps(body)
    assert "graph-token" not in json.dumps(body)
    assert "refresh-token" not in json.dumps(body)
    audit = db_session.query(AuditEvent).filter_by(action="delivery_auth.tokens_refreshed").one()
    assert json.loads(audit.metadata_json)["components"] == {
        "bot_delivery": "refreshed",
        "graph_lookup": "refreshed",
        "graph_delivery": "refreshed",
        "bot_inbound_auth": "cleared",
    }


def test_delivery_auth_refresh_skips_mock_and_unconfigured_components(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    with make_client(
        db_session,
        monkeypatch,
        BOT_DELIVERY_MODE="mock",
    ) as client:
        csrf_token = login_admin(client)
        assert client.put(
            "/api/v1/admin/settings/graph_delivery_enabled",
            headers={"X-CSRF-Token": csrf_token},
            json={"value": "false"},
        ).status_code == 200
        assert client.put(
            "/api/v1/admin/settings/graph_lookup_enabled",
            headers={"X-CSRF-Token": csrf_token},
            json={"value": "false"},
        ).status_code == 200
        response = client.post("/api/v1/admin/delivery-auth/refresh", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["bot_delivery"]["status"] == "skipped"
    assert body["graph_lookup"]["status"] == "skipped"
    assert body["graph_delivery"]["status"] == "skipped"
    assert body["bot_inbound_auth"]["status"] == "cleared"
    assert body["readiness"]["bot"]["auth_status"] == "mock"
    assert body["readiness"]["graph_lookup"]["auth_status"] == "disabled"
    assert body["readiness"]["graph_delivery"]["auth_status"] == "disabled"


def test_delivery_auth_refresh_reports_sanitized_failures(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    add_delegated_credential(db_session)

    def bot_token(settings):
        raise BotDeliveryError("raw bot provider body with bot-secret")

    def graph_token(settings):
        raise GraphRequestError("raw graph provider body with graph-secret")

    def delegated_token(**kwargs):
        raise GraphDelegatedAuthError("raw delegated provider body with delegated-secret")

    monkeypatch.setattr("app.services.teams_bot.fetch_botframework_token", bot_token)
    monkeypatch.setattr("app.services.graph_targets.fetch_graph_token", graph_token)
    monkeypatch.setattr(graph_delegated_auth, "_request_token", delegated_token)
    monkeypatch.setattr("app.routers.admin._fetch_oauth_token", lambda **kwargs: fake_token_response(kwargs["scope"]))
    monkeypatch.setattr("app.routers.admin._metadata_from_graph_token", lambda access_token, client_id: metadata_pair())

    with make_client(
        db_session,
        monkeypatch,
        BOT_DELIVERY_MODE="real",
        MS_APP_TENANT_ID="tenant",
        MS_APP_CLIENT_ID="client",
        MS_APP_CLIENT_SECRET="secret",
    ) as client:
        csrf_token = login_admin(client)
        response = client.post("/api/v1/admin/delivery-auth/refresh", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["bot_delivery"]["status"] == "failed"
    assert body["graph_lookup"]["status"] == "failed"
    assert body["graph_delivery"]["status"] == "failed"
    encoded = json.dumps(body)
    assert "bot-secret" not in encoded
    assert "graph-secret" not in encoded
    assert "delegated-secret" not in encoded
