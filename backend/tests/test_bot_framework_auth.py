from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.settings_overrides import reset_override_state
from app.database import Base, get_db
from app.main import create_app
from app.models import BotActivityEvent, BotConversationReference
from app.security import utcnow
from app.services import bot_framework_auth


BOT_APP_ID = "bot-app-id"
SERVICE_URL = "https://smba.trafficmanager.net/emea/"
JWKS_URI = "https://example.test/botframework/keys"


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


@pytest.fixture()
def signing_key(monkeypatch: pytest.MonkeyPatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
    monkeypatch.setattr(
        bot_framework_auth,
        "fetch_bot_framework_openid_metadata",
        lambda url=bot_framework_auth.OPENID_METADATA_URL: {"jwks_uri": JWKS_URI},
    )
    monkeypatch.setattr(bot_framework_auth, "fetch_bot_framework_jwks", lambda url: {"keys": [jwk]})
    bot_framework_auth.reset_bot_framework_auth_cache()
    yield private_key
    bot_framework_auth.reset_bot_framework_auth_cache()


@pytest.fixture()
def client(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    signing_key,
) -> Iterator[TestClient]:
    monkeypatch.setenv("MS_APP_CLIENT_ID", BOT_APP_ID)
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


def test_valid_bot_framework_token_allows_activity_capture(client: TestClient, db_session: Session, signing_key):
    activity = _activity()
    response = client.post("/api/v1/bot/messages", json=activity, headers=_auth_headers(_token(signing_key)))

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["captured_reference"] is True
    event = db_session.scalar(select(BotActivityEvent))
    assert event is not None
    assert event.auth_status == "verified"
    assert event.auth_issuer == bot_framework_auth.BOT_FRAMEWORK_ISSUER
    assert event.auth_audience == BOT_APP_ID
    assert event.auth_service_url == SERVICE_URL
    assert event.auth_service_url_matched is True
    assert event.auth_validated_at is not None
    serialized_event = json.dumps(
        {
            "auth_status": event.auth_status,
            "auth_issuer": event.auth_issuer,
            "auth_audience": event.auth_audience,
            "auth_service_url": event.auth_service_url,
            "raw_activity_json": event.raw_activity_json,
        }
    )
    assert "Bearer" not in serialized_event
    assert ".ey" not in serialized_event
    assert db_session.scalar(select(BotConversationReference)) is not None


@pytest.mark.parametrize(
    ("headers", "detail"),
    [
        ({}, "Missing Bot Framework authorization"),
        ({"Authorization": "Basic abc"}, "Invalid Bot Framework authorization header"),
    ],
)
def test_bot_message_endpoint_rejects_missing_or_malformed_authorization(
    client: TestClient,
    db_session: Session,
    headers: dict[str, str],
    detail: str,
):
    response = client.post("/api/v1/bot/messages", json=_activity(), headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == detail
    assert response.headers["www-authenticate"] == "Bearer"
    assert db_session.scalar(select(BotActivityEvent)) is None
    assert db_session.scalar(select(BotConversationReference)) is None


@pytest.mark.parametrize(
    ("token_kwargs", "detail"),
    [
        ({"expires_delta": timedelta(minutes=-10)}, "Expired Bot Framework token"),
        ({"not_before_delta": timedelta(minutes=10)}, "Bot Framework token is not active yet"),
        ({"audience": "other-app-id"}, "Invalid Bot Framework token audience"),
        ({"issuer": "https://example.invalid"}, "Invalid Bot Framework token issuer"),
        ({"service_url": "https://smba.trafficmanager.net/us/"}, "Bot Framework serviceUrl claim mismatch"),
        ({"kid": "missing-key"}, "Unknown Bot Framework signing key"),
    ],
)
def test_bot_message_endpoint_rejects_invalid_bot_framework_tokens(
    client: TestClient,
    db_session: Session,
    signing_key,
    token_kwargs: dict,
    detail: str,
):
    response = client.post(
        "/api/v1/bot/messages",
        json=_activity(),
        headers=_auth_headers(_token(signing_key, **token_kwargs)),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == detail
    assert db_session.scalar(select(BotActivityEvent)) is None
    assert db_session.scalar(select(BotConversationReference)) is None


def test_bot_message_endpoint_rejects_bad_signature(client: TestClient, db_session: Session):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    response = client.post(
        "/api/v1/bot/messages",
        json=_activity(),
        headers=_auth_headers(_token(other_key)),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Bot Framework token"
    assert db_session.scalar(select(BotActivityEvent)) is None
    assert db_session.scalar(select(BotConversationReference)) is None


def test_bot_message_endpoint_rejects_unsigned_token(client: TestClient, db_session: Session):
    now = utcnow()
    token = jwt.encode(
        {
            "iss": bot_framework_auth.BOT_FRAMEWORK_ISSUER,
            "aud": BOT_APP_ID,
            "serviceurl": SERVICE_URL,
            "nbf": now - timedelta(minutes=1),
            "exp": now + timedelta(minutes=10),
        },
        key="",
        algorithm="none",
    )

    response = client.post("/api/v1/bot/messages", json=_activity(), headers=_auth_headers(token))

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Bot Framework token algorithm"
    assert db_session.scalar(select(BotActivityEvent)) is None
    assert db_session.scalar(select(BotConversationReference)) is None


def _activity() -> dict:
    return {
        "type": "conversationUpdate",
        "serviceUrl": SERVICE_URL,
        "conversation": {"id": "conversation-id"},
        "from": {"id": "user-id"},
        "recipient": {"id": "bot-id"},
        "channelData": {
            "tenant": {"id": "tenant-id"},
            "team": {"id": "team-id"},
            "channel": {"id": "channel-id"},
        },
        "membersAdded": [{"id": "bot-id"}],
    }


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token(
    private_key,
    *,
    issuer: str = bot_framework_auth.BOT_FRAMEWORK_ISSUER,
    audience: str = BOT_APP_ID,
    service_url: str = SERVICE_URL,
    kid: str = "test-key",
    expires_delta: timedelta = timedelta(minutes=10),
    not_before_delta: timedelta = timedelta(minutes=-1),
) -> str:
    now = utcnow()
    return jwt.encode(
        {
            "iss": issuer,
            "aud": audience,
            "serviceurl": service_url,
            "nbf": now + not_before_delta,
            "exp": now + expires_delta,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )
