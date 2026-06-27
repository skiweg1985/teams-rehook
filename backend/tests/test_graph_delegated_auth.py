from __future__ import annotations

import base64
import io
import json
from collections.abc import Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.core.encrypted_secrets import decrypt_secret, encrypt_secret
from app.database import Base
from app.models import GraphDelegatedCredential, Organization
from app.services.graph_delegated_auth import (
    DEFAULT_DELEGATED_GRAPH_SCOPES,
    GraphDelegatedAuthError,
    build_authorization_url,
    diagnostics_for_organization,
    exchange_authorization_code,
    refresh_delegated_access_token,
)


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
        db.commit()
        db.refresh(org)
        yield db


@pytest.fixture()
def org_id(db_session: Session) -> str:
    org = db_session.query(Organization).filter_by(slug="default").one()
    return org.id


def test_encrypted_secret_round_trip_and_invalid_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "first-key")
    get_settings.cache_clear()
    encrypted = encrypt_secret("refresh-token")

    assert encrypted != "refresh-token"
    assert decrypt_secret(encrypted) == "refresh-token"

    monkeypatch.setenv("SESSION_SECRET", "second-key")
    get_settings.cache_clear()
    with pytest.raises(HTTPException):
        decrypt_secret(encrypted)


def test_build_authorization_url_uses_existing_app_registration():
    settings = Settings(ms_app_tenant_id="tenant", ms_app_client_id="client", ms_app_client_secret="secret")

    url = build_authorization_url(
        redirect_uri="https://app.example.com/callback",
        state="state-token",
        settings=settings,
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "login.microsoftonline.com"
    assert parsed.path == "/tenant/oauth2/v2.0/authorize"
    assert query["client_id"] == ["client"]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == ["https://app.example.com/callback"]
    assert query["response_mode"] == ["query"]
    assert query["state"] == ["state-token"]
    assert query["scope"] == [" ".join(DEFAULT_DELEGATED_GRAPH_SCOPES)]


def test_exchange_authorization_code_stores_encrypted_refresh_token_and_safe_metadata(
    db_session: Session,
    org_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    settings = Settings(ms_app_tenant_id="tenant", ms_app_client_id="client", ms_app_client_secret="secret")
    captured: dict[str, str] = {}

    def fake_urlopen(request, timeout=10):
        captured.update({key: values[0] for key, values in parse_qs(request.data.decode("utf-8")).items()})
        return _json_response(
            {
                "access_token": _jwt(
                    {
                        "oid": "user-id",
                        "name": "Teams Sender",
                        "preferred_username": "sender@example.com",
                    }
                ),
                "refresh_token": "refresh-token",
                "expires_in": 1800,
                "scope": "offline_access ChannelMessage.Send ChatMessage.Send Chat.ReadBasic User.Read",
            }
        )

    monkeypatch.setattr("app.services.graph_delegated_auth.urllib.request.urlopen", fake_urlopen)

    diagnostics = exchange_authorization_code(
        db_session,
        organization_id=org_id,
        code="auth-code",
        redirect_uri="https://app.example.com/callback",
        settings=settings,
    )

    row = db_session.query(GraphDelegatedCredential).filter_by(organization_id=org_id).one()
    assert captured["grant_type"] == "authorization_code"
    assert captured["code"] == "auth-code"
    assert captured["client_secret"] == "secret"
    assert row.encrypted_refresh_token != "refresh-token"
    assert decrypt_secret(row.encrypted_refresh_token) == "refresh-token"
    assert diagnostics.status == "ready"
    assert diagnostics.service_user_id == "user-id"
    assert diagnostics.service_user_display_name == "Teams Sender"
    assert diagnostics.service_user_principal_name == "sender@example.com"
    assert "refresh-token" not in str(diagnostics.to_dict())
    assert "secret" not in str(diagnostics.to_dict())


def test_refresh_delegated_access_token_rotates_refresh_token(
    db_session: Session,
    org_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    settings = Settings(ms_app_tenant_id="tenant", ms_app_client_id="client", ms_app_client_secret="secret")
    db_session.add(
        GraphDelegatedCredential(
            organization_id=org_id,
            tenant_id="tenant",
            client_id="client",
            scopes="offline_access ChannelMessage.Send",
            encrypted_refresh_token=encrypt_secret("old-refresh"),
            last_status="ready",
        )
    )
    db_session.commit()
    captured: dict[str, str] = {}

    def fake_urlopen(request, timeout=10):
        captured.update({key: values[0] for key, values in parse_qs(request.data.decode("utf-8")).items()})
        return _json_response(
            {
                "access_token": _jwt({"oid": "user-id", "name": "Teams Sender"}),
                "refresh_token": "new-refresh",
                "expires_in": 3600,
                "scope": "offline_access ChannelMessage.Send ChatMessage.Send Chat.ReadBasic User.Read",
            }
        )

    monkeypatch.setattr("app.services.graph_delegated_auth.urllib.request.urlopen", fake_urlopen)

    token = refresh_delegated_access_token(db_session, organization_id=org_id, settings=settings)

    row = db_session.query(GraphDelegatedCredential).filter_by(organization_id=org_id).one()
    assert captured["grant_type"] == "refresh_token"
    assert captured["refresh_token"] == "old-refresh"
    assert token.access_token
    assert token.diagnostics.status == "ready"
    assert decrypt_secret(row.encrypted_refresh_token) == "new-refresh"
    assert "new-refresh" not in str(token.diagnostics.to_dict())


def test_refresh_delegated_access_token_retains_offline_access_when_token_response_omits_it(
    db_session: Session,
    org_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    settings = Settings(ms_app_tenant_id="tenant", ms_app_client_id="client", ms_app_client_secret="secret")
    db_session.add(
        GraphDelegatedCredential(
            organization_id=org_id,
            tenant_id="tenant",
            client_id="client",
            scopes="offline_access ChannelMessage.Send ChatMessage.Send Chat.ReadBasic User.Read",
            encrypted_refresh_token=encrypt_secret("refresh-token"),
            last_status="ready",
        )
    )
    db_session.commit()

    def fake_urlopen(request, timeout=10):
        return _json_response(
            {
                "access_token": _jwt({"oid": "user-id", "name": "Teams Sender"}),
                "expires_in": 3600,
                "scope": "ChannelMessage.Send ChatMessage.Send Chat.ReadBasic User.Read",
            }
        )

    monkeypatch.setattr("app.services.graph_delegated_auth.urllib.request.urlopen", fake_urlopen)

    token = refresh_delegated_access_token(db_session, organization_id=org_id, settings=settings)

    assert "offline_access" in token.scopes
    diagnostics = diagnostics_for_organization(db_session, org_id)
    assert "offline_access" in diagnostics.scopes


def test_missing_delegated_credential_returns_missing_diagnostics(db_session: Session, org_id: str):
    diagnostics = diagnostics_for_organization(db_session, org_id)

    assert diagnostics.status == "missing"
    assert diagnostics.configured is False
    assert diagnostics.message == "Delegated Graph delivery has not been configured."


def test_invalid_refresh_token_marks_credential_expired_without_raw_provider_body(
    db_session: Session,
    org_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    settings = Settings(ms_app_tenant_id="tenant", ms_app_client_id="client", ms_app_client_secret="secret")
    db_session.add(
        GraphDelegatedCredential(
            organization_id=org_id,
            encrypted_refresh_token=encrypt_secret("expired-refresh"),
            last_status="ready",
        )
    )
    db_session.commit()

    def fake_urlopen(request, timeout=10):
        raise _http_error({"error": "invalid_grant", "error_description": "raw provider detail"})

    monkeypatch.setattr("app.services.graph_delegated_auth.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(GraphDelegatedAuthError):
        refresh_delegated_access_token(db_session, organization_id=org_id, settings=settings)

    diagnostics = diagnostics_for_organization(db_session, org_id)
    assert diagnostics.status == "expired"
    assert diagnostics.message == "Delegated Graph refresh token is expired or revoked."
    assert "raw provider detail" not in str(diagnostics.to_dict())


def test_transient_refresh_failure_marks_token_error_without_raw_provider_body(
    db_session: Session,
    org_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    settings = Settings(ms_app_tenant_id="tenant", ms_app_client_id="client", ms_app_client_secret="secret")
    db_session.add(
        GraphDelegatedCredential(
            organization_id=org_id,
            encrypted_refresh_token=encrypt_secret("refresh-token"),
            last_status="ready",
        )
    )
    db_session.commit()

    def fake_urlopen(request, timeout=10):
        raise URLError("raw provider network detail")

    monkeypatch.setattr("app.services.graph_delegated_auth.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(GraphDelegatedAuthError):
        refresh_delegated_access_token(db_session, organization_id=org_id, settings=settings)

    diagnostics = diagnostics_for_organization(db_session, org_id)
    assert diagnostics.status == "token_error"
    assert diagnostics.message == "Delegated Graph token refresh failed."
    assert "raw provider network detail" not in str(diagnostics.to_dict())


class _JsonResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _json_response(payload: dict) -> _JsonResponse:
    return _JsonResponse(payload)


def _jwt(claims: dict) -> str:
    header = _b64({"alg": "none", "typ": "JWT"})
    payload = _b64(claims)
    return f"{header}.{payload}."


def _b64(payload: dict) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    return encoded.rstrip("=")


def _http_error(payload: dict) -> HTTPError:
    body = json.dumps(payload).encode("utf-8")
    return HTTPError(
        url="https://login.microsoftonline.com/tenant/oauth2/v2.0/token",
        code=400,
        msg="Bad Request",
        hdrs={},
        fp=io.BytesIO(body),
    )
