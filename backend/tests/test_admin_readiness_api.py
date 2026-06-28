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
from app.core.encrypted_secrets import encrypt_secret
from app.database import Base, get_db
from app.main import create_app
from app.models import GraphDelegatedCredential, Organization, User
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
        "BOT_DEFAULT_SERVICE_URL": "",
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


def test_readiness_marks_disabled_features_without_token_checks(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    with make_client(
        db_session,
        monkeypatch,
        BOT_FRAMEWORK_ENABLED="false",
        GRAPH_LOOKUP_ENABLED="false",
        GRAPH_DELIVERY_ENABLED="false",
    ) as client:
        csrf_token = login_admin(client)
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
        "default_service_url": "missing",
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


def test_graph_delivery_oauth_callback_exchanges_code_and_redirects(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, str] = {}

    def fake_exchange(db, **kwargs):
        captured.update(kwargs)
        db.add(
            GraphDelegatedCredential(
                organization_id=kwargs["organization_id"],
                encrypted_refresh_token=encrypt_secret("refresh-token"),
                last_status="ready",
            )
        )
        db.flush()

    monkeypatch.setattr("app.routers.admin.exchange_authorization_code", fake_exchange)
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
    assert response.headers["location"] == "https://ui.example.com/settings?graph_delivery=connected"
    assert captured["code"] == "auth-code"
    assert captured["redirect_uri"] == "https://app.example.com/api/v1/admin/graph-delivery/oauth/callback"
    assert captured["scopes"] == graph_delegated_auth.DEFAULT_DELEGATED_GRAPH_SCOPES
    row = db_session.query(GraphDelegatedCredential).one()
    assert row.last_status == "ready"


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
