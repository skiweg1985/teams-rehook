from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings_overrides import reset_override_state
from app.database import Base, get_db
from app.main import create_app
from app.models import AuditEvent, BotActivityEvent, Organization, User, WebhookAbuseBucket, WebhookDeliveryEvent, WebhookRoute
from app.security import dumps_json, hash_secret, lookup_secret_hash
from app.security import ensure_utc, utcnow
from app.routers.webhook_routes import _resolve_client_host


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
        admin = User(
            organization_id=org.id,
            email="admin@example.com",
            display_name="Admin",
            password_hash=hash_secret("change-me-admin-password"),
            is_admin=True,
            is_active=True,
        )
        db.add(org)
        db.flush()
        admin.organization_id = org.id
        db.add(admin)
        db.commit()
        yield db


@pytest.fixture()
def client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from app.core.config import get_settings

    monkeypatch.setenv("BOT_DELIVERY_MODE", "mock")
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
        reset_override_state()


def add_route(
    db: Session,
    *,
    token: str = "route-token",
    active: bool = True,
    client_ip_access_mode: str = "public",
    client_ip_allowlist: str = "",
) -> WebhookRoute:
    org = db.scalar(select(Organization).where(Organization.slug == "default"))
    assert org is not None
    route = WebhookRoute(
        organization_id=org.id,
        name=f"Route {token}",
        is_active=active,
        route_token_hash=lookup_secret_hash(token),
        route_token=token,
        client_ip_access_mode=client_ip_access_mode,
        client_ip_allowlist=client_ip_allowlist,
        target_type="bot_conversation",
        target_name="Monitoring",
        bot_service_url="https://smba.trafficmanager.net/emea/example",
        bot_conversation_id="conversation-id",
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    return route


def login_admin(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "change-me-admin-password"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def set_admin_setting(client: TestClient, csrf_token: str, key: str, value: str) -> None:
    response = client.put(
        f"/api/v1/admin/settings/{key}",
        headers={"X-CSRF-Token": csrf_token},
        json={"value": value},
    )
    assert response.status_code == 200


def test_admin_route_api_requires_session_and_csrf(client: TestClient):
    response = client.get("/api/v1/webhook-routes")

    assert response.status_code == 401


def test_public_webhook_delivers_known_active_route(client: TestClient, db_session: Session):
    route = add_route(db_session)

    response = client.post(
        "/api/v1/webhooks/route-token",
        json={"title": "PRTG alert", "text": "Sensor down", "severity": "warning"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "delivered"
    assert body["route_id"] == route.id
    db_session.refresh(route)
    assert route.last_delivery_status == "delivered"
    events = db_session.scalars(select(WebhookDeliveryEvent).where(WebhookDeliveryEvent.route_id == route.id)).all()
    assert len(events) == 1
    assert events[0].status == "delivered"
    request_metadata = json.loads(events[0].request_metadata_json)
    assert request_metadata["client_host"]
    assert request_metadata["direct_client_host"] == request_metadata["client_host"]
    assert request_metadata["client_host_source"] == "direct"
    assert json.loads(events[0].delivery_result_json)["backend"] == "bot_framework"


def test_create_route_stores_restricted_client_ip_allowlist(client: TestClient):
    csrf_token = login_admin(client)

    response = client.post(
        "/api/v1/webhook-routes",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "name": "Restricted route",
            "is_active": True,
            "client_ip_access_mode": "restricted",
            "client_ip_allowlist": "203.0.113.10, 10.0.0.0/24\n203.0.113.10",
            "target_type": "bot_conversation",
            "target_name": "Monitoring",
            "bot_service_url": "https://smba.trafficmanager.net/emea/example",
            "bot_conversation_id": "conversation-id",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["client_ip_access_mode"] == "restricted"
    assert body["client_ip_allowlist"] == "203.0.113.10\n10.0.0.0/24"


def test_create_restricted_route_rejects_invalid_or_empty_allowlist(client: TestClient):
    csrf_token = login_admin(client)
    base_payload = {
        "name": "Restricted route",
        "is_active": True,
        "client_ip_access_mode": "restricted",
        "target_type": "bot_conversation",
        "target_name": "Monitoring",
        "bot_service_url": "https://smba.trafficmanager.net/emea/example",
        "bot_conversation_id": "conversation-id",
    }

    empty_response = client.post(
        "/api/v1/webhook-routes",
        headers={"X-CSRF-Token": csrf_token},
        json={**base_payload, "client_ip_allowlist": ""},
    )
    invalid_response = client.post(
        "/api/v1/webhook-routes",
        headers={"X-CSRF-Token": csrf_token},
        json={**base_payload, "name": "Invalid route", "client_ip_allowlist": "not-an-ip"},
    )

    assert empty_response.status_code == 422
    assert invalid_response.status_code == 422


def test_restricted_webhook_delivers_allowed_client_ip(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    route = add_route(
        db_session,
        token="restricted-token",
        client_ip_access_mode="restricted",
        client_ip_allowlist="203.0.113.10\n10.0.0.0/24",
    )
    monkeypatch.setattr(
        "app.routers.webhook_routes._resolve_client_host",
        lambda request: ("10.0.0.42", "10.0.0.42", "", "direct"),
    )

    response = client.post("/api/v1/webhooks/restricted-token", json={"text": "allowed"})

    assert response.status_code == 200
    db_session.refresh(route)
    assert route.last_delivery_status == "delivered"


def test_restricted_webhook_rejects_unlisted_client_ip(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    route = add_route(
        db_session,
        token="restricted-token",
        client_ip_access_mode="restricted",
        client_ip_allowlist="203.0.113.10",
    )
    monkeypatch.setattr(
        "app.routers.webhook_routes._resolve_client_host",
        lambda request: ("198.51.100.20", "198.51.100.20", "", "direct"),
    )

    response = client.post("/api/v1/webhooks/restricted-token", json={"text": "blocked"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Client IP is not allowed for this webhook route"
    db_session.refresh(route)
    assert route.last_delivery_status == "rejected"
    event = db_session.scalar(select(WebhookDeliveryEvent).where(WebhookDeliveryEvent.route_id == route.id))
    assert event is not None
    assert event.status == "rejected"
    assert event.error == "Client IP is not allowed for this webhook route"


def test_client_host_ignores_x_forwarded_for_by_default(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings

    monkeypatch.setenv("TRUST_X_FORWARDED_FOR", "false")
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/24")
    get_settings.cache_clear()
    request = SimpleNamespace(
        client=SimpleNamespace(host="10.0.0.10"),
        headers={"x-forwarded-for": "203.0.113.42, 10.0.0.10"},
    )

    try:
        assert _resolve_client_host(request) == (
            "10.0.0.10",
            "10.0.0.10",
            "203.0.113.42, 10.0.0.10",
            "direct",
        )
    finally:
        get_settings.cache_clear()


def test_client_host_uses_x_forwarded_for_from_trusted_proxy(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings

    monkeypatch.setenv("TRUST_X_FORWARDED_FOR", "true")
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/24")
    get_settings.cache_clear()
    request = SimpleNamespace(
        client=SimpleNamespace(host="10.0.0.10"),
        headers={"x-forwarded-for": "203.0.113.42, 10.0.0.9"},
    )

    try:
        assert _resolve_client_host(request) == (
            "203.0.113.42",
            "10.0.0.10",
            "203.0.113.42, 10.0.0.9",
            "x_forwarded_for",
        )
    finally:
        get_settings.cache_clear()


def test_client_host_uses_compose_haproxy_forwarded_client(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings

    monkeypatch.setenv("TRUST_X_FORWARDED_FOR", "true")
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    monkeypatch.setenv("COMPOSE_APP_SUBNET", "172.30.0.0/24")
    get_settings.cache_clear()
    request = SimpleNamespace(
        client=SimpleNamespace(host="172.30.0.10"),
        headers={"x-forwarded-for": "203.0.113.42"},
    )

    try:
        assert _resolve_client_host(request) == (
            "203.0.113.42",
            "172.30.0.10",
            "203.0.113.42",
            "x_forwarded_for",
        )
    finally:
        get_settings.cache_clear()


def test_client_host_uses_trusted_upstream_proxy_chain(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings

    monkeypatch.setenv("TRUST_X_FORWARDED_FOR", "true")
    monkeypatch.setenv("COMPOSE_APP_SUBNET", "172.30.0.0/24")
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.9/32")
    get_settings.cache_clear()
    request = SimpleNamespace(
        client=SimpleNamespace(host="172.30.0.10"),
        headers={"x-forwarded-for": "203.0.113.42, 10.0.0.9"},
    )

    try:
        assert _resolve_client_host(request) == (
            "203.0.113.42",
            "172.30.0.10",
            "203.0.113.42, 10.0.0.9",
            "x_forwarded_for",
        )
    finally:
        get_settings.cache_clear()


def test_client_host_ignores_x_forwarded_for_from_untrusted_proxy(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings

    monkeypatch.setenv("TRUST_X_FORWARDED_FOR", "true")
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/24")
    get_settings.cache_clear()
    request = SimpleNamespace(
        client=SimpleNamespace(host="198.51.100.10"),
        headers={"x-forwarded-for": "203.0.113.42"},
    )

    try:
        assert _resolve_client_host(request) == (
            "198.51.100.10",
            "198.51.100.10",
            "203.0.113.42",
            "direct",
        )
    finally:
        get_settings.cache_clear()


def test_client_host_falls_back_when_x_forwarded_for_is_malformed(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings

    monkeypatch.setenv("TRUST_X_FORWARDED_FOR", "true")
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/24")
    get_settings.cache_clear()
    request = SimpleNamespace(
        client=SimpleNamespace(host="10.0.0.10"),
        headers={"x-forwarded-for": "203.0.113.42, not-an-ip"},
    )

    try:
        assert _resolve_client_host(request) == (
            "10.0.0.10",
            "10.0.0.10",
            "203.0.113.42, not-an-ip",
            "direct",
        )
    finally:
        get_settings.cache_clear()


def test_public_webhook_rejects_unknown_token(client: TestClient, db_session: Session):
    response = client.post("/api/v1/webhooks/missing-token", json={"text": "hello"})

    assert response.status_code == 404
    events = db_session.scalars(select(WebhookDeliveryEvent)).all()
    assert len(events) == 1
    assert events[0].route_id is None
    assert events[0].status == "rejected"


def test_public_webhook_rejects_oversized_payload_before_delivery(client: TestClient, db_session: Session):
    csrf_token = login_admin(client)
    set_admin_setting(client, csrf_token, "webhook_max_payload_bytes", "1024")

    response = client.post(
        "/api/v1/webhooks/missing-token",
        content=b"x" * 1025,
        headers={"Content-Type": "text/plain"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Payload exceeds 1024 bytes"
    event = db_session.scalar(select(WebhookDeliveryEvent))
    assert event is not None
    assert event.status == "rejected"
    assert event.error == "Payload exceeds 1024 bytes"


def test_public_webhook_idempotency_key_prevents_duplicate_delivery(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    route = add_route(db_session, token="idempotent-token")
    deliveries = 0

    class FakeBotResult:
        def to_dict(self):
            return {"mode": "mock", "activity_id": "activity-id", "status_code": 202, "activity": {"type": "message"}}

    def fake_send_bot_activity(**kwargs):
        nonlocal deliveries
        deliveries += 1
        return FakeBotResult()

    monkeypatch.setattr("app.routers.webhook_routes.send_bot_activity", fake_send_bot_activity)

    first = client.post(
        "/api/v1/webhooks/idempotent-token",
        json={"text": "hello"},
        headers={"Idempotency-Key": "retry-key-123"},
    )
    second = client.post(
        "/api/v1/webhooks/idempotent-token",
        json={"text": "hello again"},
        headers={"Idempotency-Key": "retry-key-123"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["delivery_event_id"] == first.json()["delivery_event_id"]
    assert deliveries == 1
    events = db_session.scalars(select(WebhookDeliveryEvent).where(WebhookDeliveryEvent.route_id == route.id)).all()
    assert len(events) == 1


def test_public_webhook_persists_pending_event_before_provider_delivery(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    route = add_route(db_session, token="pending-token")
    observed_statuses: list[str] = []

    class FakeBotResult:
        def to_dict(self):
            return {"mode": "mock", "activity_id": "activity-id", "status_code": 202, "activity": {"type": "message"}}

    def fake_send_bot_activity(**kwargs):
        events = db_session.scalars(select(WebhookDeliveryEvent).where(WebhookDeliveryEvent.route_id == route.id)).all()
        observed_statuses.extend(event.status for event in events)
        return FakeBotResult()

    monkeypatch.setattr("app.routers.webhook_routes.send_bot_activity", fake_send_bot_activity)

    response = client.post("/api/v1/webhooks/pending-token", json={"text": "hello"})

    assert response.status_code == 200
    assert observed_statuses == ["pending"]
    final_event = db_session.scalar(select(WebhookDeliveryEvent).where(WebhookDeliveryEvent.route_id == route.id))
    assert final_event is not None
    assert final_event.status == "delivered"


def test_unknown_webhook_route_blocks_after_failure_limit(client: TestClient, db_session: Session):
    csrf_token = login_admin(client)
    set_admin_setting(client, csrf_token, "webhook_abuse_failure_limit", "2")

    first = client.post("/api/v1/webhooks/missing-token", json={"text": "hello"})
    second = client.post("/api/v1/webhooks/missing-token", json={"text": "hello"})
    blocked = client.post("/api/v1/webhooks/missing-token", json={"text": "hello"})

    assert first.status_code == 404
    assert second.status_code == 404
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Too many failed webhook attempts"
    buckets = db_session.scalars(select(WebhookAbuseBucket)).all()
    assert len(buckets) == 1
    assert buckets[0].scope == "ip"
    assert buckets[0].route_token_hash is None
    assert all(bucket.blocked_until is not None for bucket in buckets)
    assert {bucket.last_reason for bucket in buckets} == {"unknown_route"}
    assert {bucket.last_client_host for bucket in buckets} == {"testclient"}


def test_invalid_payload_counts_route_bucket_and_success_resets_it(client: TestClient, db_session: Session):
    add_route(db_session, token="reset-token")
    csrf_token = login_admin(client)
    set_admin_setting(client, csrf_token, "webhook_abuse_failure_limit", "3")

    invalid = client.post("/api/v1/webhooks/reset-token", data=b"   ", headers={"Content-Type": "text/plain"})
    assert invalid.status_code == 400
    route_bucket = db_session.scalar(select(WebhookAbuseBucket).where(WebhookAbuseBucket.scope == "ip_route"))
    assert route_bucket is not None
    assert route_bucket.failure_count == 1
    assert route_bucket.last_reason == "invalid_payload"

    delivered = client.post("/api/v1/webhooks/reset-token", json={"text": "valid"})
    assert delivered.status_code == 200
    db_session.refresh(route_bucket)
    assert route_bucket.failure_count == 0
    assert route_bucket.blocked_until is None


def test_webhook_abuse_block_expires_and_escalates(client: TestClient, db_session: Session):
    csrf_token = login_admin(client)
    set_admin_setting(client, csrf_token, "webhook_abuse_failure_limit", "1")

    first = client.post("/api/v1/webhooks/escalate-token", json={"text": "hello"})
    assert first.status_code == 404
    first_bucket = db_session.scalar(select(WebhookAbuseBucket).where(WebhookAbuseBucket.scope == "ip"))
    assert first_bucket is not None
    assert first_bucket.block_count == 1
    first_blocked_until = ensure_utc(first_bucket.blocked_until)
    assert first_blocked_until is not None

    for bucket in db_session.scalars(select(WebhookAbuseBucket)).all():
        bucket.blocked_until = utcnow() - timedelta(minutes=1)
    db_session.commit()

    second = client.post("/api/v1/webhooks/escalate-token", json={"text": "hello"})
    assert second.status_code == 404
    db_session.refresh(first_bucket)
    assert first_bucket.block_count == 2
    second_blocked_until = ensure_utc(first_bucket.blocked_until)
    assert second_blocked_until is not None
    assert first_blocked_until is not None
    assert second_blocked_until > first_blocked_until


def test_webhook_abuse_uses_resolved_forwarded_client(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    csrf_token = login_admin(client)
    set_admin_setting(client, csrf_token, "webhook_abuse_failure_limit", "1")

    def fake_resolve_client_host(request):
        forwarded = request.headers.get("x-forwarded-for", "")
        return forwarded, "10.0.0.10", forwarded, "x_forwarded_for"

    monkeypatch.setattr("app.routers.webhook_routes._resolve_client_host", fake_resolve_client_host)

    proxied = client.post(
        "/api/v1/webhooks/forwarded-token",
        headers={"X-Forwarded-For": "203.0.113.10"},
        json={"text": "hello"},
    )
    same_forwarded_blocked = client.post(
        "/api/v1/webhooks/forwarded-token",
        headers={"X-Forwarded-For": "203.0.113.10"},
        json={"text": "hello"},
    )
    different_forwarded = client.post(
        "/api/v1/webhooks/forwarded-token",
        headers={"X-Forwarded-For": "203.0.113.11"},
        json={"text": "hello"},
    )

    assert proxied.status_code == 404
    assert same_forwarded_blocked.status_code == 429
    assert different_forwarded.status_code == 404
    assert {bucket.last_client_host for bucket in db_session.scalars(select(WebhookAbuseBucket)).all()} == {
        "203.0.113.10",
        "203.0.113.11",
    }


def test_admin_webhook_abuse_list_hides_expired_observed_clients(client: TestClient, db_session: Session):
    csrf_token = login_admin(client)
    set_admin_setting(client, csrf_token, "webhook_abuse_failure_limit", "10")
    set_admin_setting(client, csrf_token, "webhook_abuse_window_minutes", "10")

    rejected = client.post("/api/v1/webhooks/observed-token", json={"text": "hello"})
    assert rejected.status_code == 404

    recent_response = client.get("/api/v1/admin/webhook-abuse-buckets", headers={"X-CSRF-Token": csrf_token})
    assert recent_response.status_code == 200
    assert len(recent_response.json()) == 1
    assert recent_response.json()[0]["status"] == "watching"

    bucket = db_session.scalar(select(WebhookAbuseBucket))
    assert bucket is not None
    bucket.window_started_at = utcnow() - timedelta(minutes=11)
    bucket.last_seen_at = utcnow() - timedelta(minutes=11)
    db_session.commit()

    expired_response = client.get("/api/v1/admin/webhook-abuse-buckets", headers={"X-CSRF-Token": csrf_token})
    assert expired_response.status_code == 200
    assert expired_response.json() == []


def test_admin_can_list_unblock_and_cleanup_webhook_abuse_buckets(client: TestClient, db_session: Session):
    csrf_token = login_admin(client)
    set_admin_setting(client, csrf_token, "webhook_abuse_failure_limit", "1")

    rejected = client.post("/api/v1/webhooks/admin-abuse-token", json={"text": "hello"})
    assert rejected.status_code == 404

    missing_csrf = client.get("/api/v1/admin/webhook-abuse-buckets")
    assert missing_csrf.status_code == 403

    list_response = client.get("/api/v1/admin/webhook-abuse-buckets", headers={"X-CSRF-Token": csrf_token})
    assert list_response.status_code == 200
    buckets = list_response.json()
    assert buckets
    assert buckets[0]["status"] == "blocked"
    assert buckets[0]["client_host"] == "testclient"
    assert buckets[0]["client_fingerprint"]
    assert buckets[0]["block_count"] == 1

    reset_without_csrf = client.delete(f"/api/v1/admin/webhook-abuse-buckets/{buckets[0]['id']}")
    assert reset_without_csrf.status_code == 403

    reset_response = client.delete(
        f"/api/v1/admin/webhook-abuse-buckets/{buckets[0]['id']}",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["status"] == "watching"
    assert reset_response.json()["failure_count"] == 0
    assert reset_response.json()["block_count"] == 1
    assert reset_response.json()["blocked_until"] is None

    add_route(db_session, token="after-unblock-token")
    delivered = client.post("/api/v1/webhooks/after-unblock-token", json={"text": "valid after unblock"})
    assert delivered.status_code == 200

    old_bucket = WebhookAbuseBucket(
        bucket_key="old-cleanup-bucket",
        scope="ip",
        client_hash="abc123",
        failure_count=0,
        block_count=0,
        window_started_at=utcnow() - timedelta(days=40),
        last_seen_at=utcnow() - timedelta(days=40),
    )
    db_session.add(old_bucket)
    db_session.commit()

    cleanup_response = client.post(
        "/api/v1/admin/webhook-abuse-buckets/cleanup",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert cleanup_response.status_code == 200
    assert cleanup_response.json()["deleted"] >= 1
    assert db_session.get(WebhookAbuseBucket, old_bucket.id) is None


def test_public_webhook_rejects_disabled_route(client: TestClient, db_session: Session):
    route = add_route(db_session, token="disabled-token", active=False)

    response = client.post("/api/v1/webhooks/disabled-token", json={"text": "hello"})

    assert response.status_code == 409
    db_session.refresh(route)
    assert route.last_delivery_status == "rejected"


def test_route_token_hash_is_stored_for_lookup(db_session: Session):
    route = add_route(db_session, token="secret-route-token")

    assert route.route_token == "secret-route-token"
    assert route.route_token_hash == lookup_secret_hash("secret-route-token")


def test_regenerate_url_replaces_route_token(client: TestClient, db_session: Session):
    route = add_route(db_session, token="old-token")
    csrf_token = login_admin(client)

    response = client.post(
        f"/api/v1/webhook-routes/{route.id}/regenerate-url",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["webhook_url_available"] is True
    assert "old-token" not in body["webhook_url"]
    db_session.refresh(route)
    assert route.route_token != "old-token"
    assert route.route_token_hash == lookup_secret_hash(route.route_token)

    old_response = client.post("/api/v1/webhooks/old-token", json={"text": "old URL"})
    assert old_response.status_code == 404

    new_response = client.post(f"/api/v1/webhooks/{route.route_token}", json={"text": "new URL"})
    assert new_response.status_code == 200


def test_create_route_stores_graph_target_metadata(client: TestClient):
    csrf_token = login_admin(client)

    response = client.post(
        "/api/v1/webhook-routes",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "name": "Graph target route",
            "is_active": True,
            "target_type": "bot_conversation",
            "target_name": "Monitoring / Alerts",
            "bot_service_url": "https://smba.trafficmanager.net/emea/example",
            "bot_conversation_id": "conversation-id",
            "graph_target_kind": "channel",
            "graph_target_id": "channel-id",
            "graph_team_id": "team-id",
            "graph_team_name": "Monitoring",
            "graph_channel_id": "channel-id",
            "bot_target_source": "conversation_reference",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["delivery_backend"] == "bot_framework"
    assert body["graph_target_kind"] == "channel"
    assert body["graph_target_id"] == "channel-id"
    assert body["graph_team_id"] == "team-id"
    assert body["graph_team_name"] == "Monitoring"
    assert body["graph_channel_id"] == "channel-id"
    assert body["bot_target_source"] == "conversation_reference"


def test_create_route_can_store_graph_delivery_backend(client: TestClient):
    csrf_token = login_admin(client)

    response = client.post(
        "/api/v1/webhook-routes",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "name": "Graph delivery route",
            "is_active": True,
            "delivery_backend": "graph",
            "target_type": "bot_conversation",
            "target_name": "Monitoring / Alerts",
            "graph_target_kind": "channel",
            "graph_target_id": "channel-id",
            "graph_team_id": "team-id",
            "graph_team_name": "Monitoring",
            "graph_channel_id": "channel-id",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["delivery_backend"] == "graph"
    assert body["bot_service_url"] == ""
    assert body["bot_conversation_id"] == ""


def test_create_graph_route_rejects_disabled_graph_delivery(client: TestClient):
    csrf_token = login_admin(client)
    settings_response = client.put(
        "/api/v1/admin/settings/graph_delivery_enabled",
        headers={"X-CSRF-Token": csrf_token},
        json={"value": "false"},
    )
    assert settings_response.status_code == 200

    response = client.post(
        "/api/v1/webhook-routes",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "name": "Disabled Graph route",
            "is_active": True,
            "delivery_backend": "graph",
            "target_type": "bot_conversation",
            "target_name": "Monitoring / Alerts",
            "graph_target_kind": "channel",
            "graph_target_id": "channel-id",
            "graph_team_id": "team-id",
            "graph_channel_id": "channel-id",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Microsoft Graph delivery is disabled"


def test_create_route_allows_same_name_across_delivery_backends(client: TestClient):
    csrf_token = login_admin(client)
    name = "Shared alert route"

    bot_response = client.post(
        "/api/v1/webhook-routes",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "name": name,
            "is_active": True,
            "delivery_backend": "bot_framework",
            "target_type": "bot_conversation",
            "target_name": "Monitoring / Alerts",
            "bot_service_url": "https://smba.trafficmanager.net/emea/example",
            "bot_conversation_id": "conversation-id",
        },
    )
    graph_response = client.post(
        "/api/v1/webhook-routes",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "name": name,
            "is_active": True,
            "delivery_backend": "graph",
            "target_type": "bot_conversation",
            "target_name": "Monitoring / Alerts",
            "graph_target_kind": "channel",
            "graph_target_id": "channel-id",
            "graph_team_id": "team-id",
            "graph_team_name": "Monitoring",
            "graph_channel_id": "channel-id",
        },
    )

    assert bot_response.status_code == 200
    assert graph_response.status_code == 200
    assert bot_response.json()["name"] == graph_response.json()["name"] == name
    assert bot_response.json()["delivery_backend"] == "bot_framework"
    assert graph_response.json()["delivery_backend"] == "graph"


def test_create_route_rejects_same_name_with_same_delivery_backend(client: TestClient):
    csrf_token = login_admin(client)
    payload = {
        "name": "Duplicate Graph route",
        "is_active": True,
        "delivery_backend": "graph",
        "target_type": "bot_conversation",
        "target_name": "Monitoring / Alerts",
        "graph_target_kind": "channel",
        "graph_target_id": "channel-id",
        "graph_team_id": "team-id",
        "graph_team_name": "Monitoring",
        "graph_channel_id": "channel-id",
    }

    first_response = client.post("/api/v1/webhook-routes", headers={"X-CSRF-Token": csrf_token}, json=payload)
    second_response = client.post("/api/v1/webhook-routes", headers={"X-CSRF-Token": csrf_token}, json=payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Webhook route name already exists for this delivery backend"


def test_update_route_delivery_backend(client: TestClient, db_session: Session):
    route = add_route(db_session)
    csrf_token = login_admin(client)

    response = client.patch(
        f"/api/v1/webhook-routes/{route.id}",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "delivery_backend": "graph",
            "bot_service_url": "",
            "bot_conversation_id": "",
            "graph_target_kind": "channel",
            "graph_target_id": "channel-id",
            "graph_team_id": "team-id",
            "graph_channel_id": "channel-id",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["delivery_backend"] == "graph"
    db_session.refresh(route)
    assert route.delivery_backend == "graph"


def test_create_graph_chat_route_uses_graph_target_id_as_chat_id(client: TestClient):
    csrf_token = login_admin(client)

    response = client.post(
        "/api/v1/webhook-routes",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "name": "Graph chat route",
            "is_active": True,
            "delivery_backend": "graph",
            "target_type": "bot_conversation",
            "target_name": "Ops chat",
            "graph_target_kind": "chat",
            "graph_target_id": "chat-id",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["delivery_backend"] == "graph"
    assert body["graph_target_kind"] == "chat"
    assert body["graph_target_id"] == "chat-id"


def test_create_graph_user_route_materializes_one_on_one_chat(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    csrf_token = login_admin(client)

    def fake_one_on_one_chat(db, *, organization_id: str, user_id: str, user_display_name: str, user_principal_name: str):
        assert user_id == "user-id"
        assert user_display_name == "Ada Admin"
        assert user_principal_name == "ada@example.com"
        return type(
            "Chat",
            (),
            {
                "id": "chat-id",
                "user_id": user_id,
                "user_display_name": user_display_name,
                "user_principal_name": user_principal_name,
            },
        )()

    monkeypatch.setattr("app.routers.webhook_routes.create_or_get_one_on_one_chat", fake_one_on_one_chat)

    response = client.post(
        "/api/v1/webhook-routes",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "name": "Graph user route",
            "is_active": True,
            "delivery_backend": "graph",
            "target_type": "bot_conversation",
            "target_name": "Ada Admin",
            "graph_target_kind": "user",
            "graph_target_id": "user-id",
            "graph_user_id": "user-id",
            "graph_user_display_name": "Ada Admin",
            "graph_user_principal_name": "ada@example.com",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["graph_target_kind"] == "chat"
    assert body["graph_target_id"] == "chat-id"
    assert body["graph_user_id"] == "user-id"
    assert body["graph_user_display_name"] == "Ada Admin"
    assert body["graph_user_principal_name"] == "ada@example.com"
    route = db_session.scalar(select(WebhookRoute).where(WebhookRoute.name == "Graph user route"))
    assert route is not None
    assert route.graph_target_kind == "chat"
    assert route.graph_target_id == "chat-id"


def test_create_graph_user_route_reports_graph_lookup_error(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    csrf_token = login_admin(client)

    def fail_one_on_one_chat(*args, **kwargs):
        from app.services.graph_delegated_lookup import GraphDelegatedLookupError

        raise GraphDelegatedLookupError("Microsoft Graph one-on-one chat creation failed with HTTP 403: Forbidden")

    monkeypatch.setattr("app.routers.webhook_routes.create_or_get_one_on_one_chat", fail_one_on_one_chat)

    response = client.post(
        "/api/v1/webhook-routes",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "name": "Graph user route",
            "is_active": True,
            "delivery_backend": "graph",
            "target_type": "bot_conversation",
            "target_name": "Ada Admin",
            "graph_target_kind": "user",
            "graph_target_id": "user-id",
        },
    )

    assert response.status_code == 502
    assert "HTTP 403" in response.json()["detail"]


def test_update_graph_user_route_materializes_one_on_one_chat(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    route = add_route(db_session)
    csrf_token = login_admin(client)

    def fake_one_on_one_chat(db, *, organization_id: str, user_id: str, user_display_name: str, user_principal_name: str):
        return type(
            "Chat",
            (),
            {
                "id": "updated-chat-id",
                "user_id": user_id,
                "user_display_name": user_display_name,
                "user_principal_name": user_principal_name,
            },
        )()

    monkeypatch.setattr("app.routers.webhook_routes.create_or_get_one_on_one_chat", fake_one_on_one_chat)

    response = client.patch(
        f"/api/v1/webhook-routes/{route.id}",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "delivery_backend": "graph",
            "target_name": "Ada Admin",
            "graph_target_kind": "user",
            "graph_target_id": "user-id",
            "graph_user_id": "user-id",
            "graph_user_display_name": "Ada Admin",
            "graph_user_principal_name": "ada@example.com",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["delivery_backend"] == "graph"
    assert body["graph_target_kind"] == "chat"
    assert body["graph_target_id"] == "updated-chat-id"
    assert body["bot_service_url"] == ""
    assert body["bot_conversation_id"] == ""
    db_session.refresh(route)
    assert route.graph_user_id == "user-id"


def test_create_graph_channel_route_requires_channel_metadata(client: TestClient):
    csrf_token = login_admin(client)

    response = client.post(
        "/api/v1/webhook-routes",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "name": "Incomplete Graph channel",
            "is_active": True,
            "delivery_backend": "graph",
            "target_type": "bot_conversation",
            "target_name": "Ops / Alerts",
            "graph_target_kind": "channel",
            "graph_target_id": "channel-id",
            "graph_team_id": "team-id",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Graph channel routes require a team ID and channel ID"


def test_create_route_rejects_invalid_delivery_backend(client: TestClient):
    csrf_token = login_admin(client)

    response = client.post(
        "/api/v1/webhook-routes",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "name": "Invalid backend route",
            "is_active": True,
            "delivery_backend": "email",
            "target_type": "bot_conversation",
            "target_name": "Monitoring",
        },
    )

    assert response.status_code == 422


def test_refresh_graph_names_updates_route_target_names(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch):
    route = add_route(db_session)
    route.graph_target_kind = "channel"
    route.graph_target_id = "channel-id"
    route.graph_team_id = "team-id"
    route.graph_team_name = ""
    route.graph_channel_id = "channel-id"
    route.target_name = "Ada Admin"
    db_session.commit()
    csrf_token = login_admin(client)

    def fake_team(team_id: str):
        assert team_id == "team-id"
        return type("Target", (), {"display_name": "Infrastruktur"})()

    def fake_channel(team_id: str, channel_id: str):
        assert team_id == "team-id"
        assert channel_id == "channel-id"
        return type("Target", (), {"display_name": "Jira"})()

    monkeypatch.setattr("app.services.graph_name_resolution.get_team_target", fake_team)
    monkeypatch.setattr("app.services.graph_name_resolution.get_channel_target", fake_channel)

    response = client.post("/api/v1/webhook-routes/refresh-graph-names", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["routes_updated"] == 1
    db_session.refresh(route)
    assert route.graph_team_name == "Infrastruktur"
    assert route.target_name == "Infrastruktur / Jira"


def test_refresh_single_route_graph_names_updates_only_that_route(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch):
    route = add_route(db_session, token="one")
    other = add_route(db_session, token="two")
    route.graph_target_kind = "channel"
    route.graph_target_id = "channel-id"
    route.graph_team_id = "team-id"
    route.graph_channel_id = "channel-id"
    route.target_name = "Ada Admin"
    other.target_name = "Leave Me"
    db_session.commit()
    csrf_token = login_admin(client)

    monkeypatch.setattr("app.services.graph_name_resolution.get_team_target", lambda team_id: type("Target", (), {"display_name": "Ops"})())
    monkeypatch.setattr("app.services.graph_name_resolution.get_channel_target", lambda team_id, channel_id: type("Target", (), {"display_name": "Alerts"})())

    response = client.post(f"/api/v1/webhook-routes/{route.id}/refresh-graph-names", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    assert response.json()["routes_updated"] == 1
    db_session.refresh(route)
    db_session.refresh(other)
    assert route.target_name == "Ops / Alerts"
    assert other.target_name == "Leave Me"


def test_delivery_events_endpoint_returns_parsed_logs(client: TestClient, db_session: Session):
    route = add_route(db_session)
    csrf_token = login_admin(client)
    delivery = client.post(
        f"/api/v1/webhook-routes/{route.id}/test",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "Test", "text": "Hello", "severity": "info"},
    )
    assert delivery.status_code == 200

    response = client.get(f"/api/v1/webhook-routes/{route.id}/deliveries")

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "delivered"
    assert rows[0]["request_metadata"]["trigger"] == "manual_test"
    assert rows[0]["request_metadata"]["bot_target"]["conversation_id"] == "conversation-id"
    assert rows[0]["normalized_message"]["title"] == "Test"
    assert rows[0]["delivery_result"]["backend"] == "bot_framework"
    assert rows[0]["delivery_result"]["mode"] == "mock"


def test_manual_test_logs_graph_target_metadata(client: TestClient, db_session: Session):
    route = add_route(db_session)
    route.target_name = "Monitoring / Alerts"
    route.graph_target_kind = "channel"
    route.graph_target_id = "channel-id"
    route.graph_team_id = "team-id"
    route.graph_team_name = "Monitoring"
    route.graph_channel_id = "channel-id"
    db_session.commit()
    csrf_token = login_admin(client)

    delivery = client.post(
        f"/api/v1/webhook-routes/{route.id}/test",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "Test", "text": "Hello", "severity": "info"},
    )
    assert delivery.status_code == 200

    response = client.get(f"/api/v1/webhook-routes/{route.id}/deliveries")

    assert response.status_code == 200
    graph_target = response.json()[0]["request_metadata"]["graph_target"]
    assert graph_target["kind"] == "channel"
    assert graph_target["target_name"] == "Monitoring / Alerts"
    assert graph_target["team_id"] == "team-id"
    assert graph_target["team_name"] == "Monitoring"
    assert graph_target["channel_id"] == "channel-id"


def test_graph_delivery_backend_calls_graph_service(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch):
    route = add_route(db_session)
    route.delivery_backend = "graph"
    route.bot_service_url = ""
    route.bot_conversation_id = ""
    route.graph_target_kind = "channel"
    route.graph_target_id = "channel-id"
    route.graph_team_id = "team-id"
    route.graph_channel_id = "channel-id"
    db_session.commit()
    csrf_token = login_admin(client)
    calls = []

    class FakeGraphResult:
        def to_dict(self):
            return {
                "backend": "graph",
                "mode": "real",
                "status_code": 201,
                "message_id": "graph-message-id",
                "target": {"kind": "channel", "team_id": "team-id", "channel_id": "channel-id"},
            }

    def fake_send_graph_message(*args, **kwargs):
        calls.append({"args": args, **kwargs})
        return FakeGraphResult()

    monkeypatch.setattr("app.routers.webhook_routes.send_graph_message", fake_send_graph_message)

    response = client.post(
        f"/api/v1/webhook-routes/{route.id}/test",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "Test", "text": "Hello", "severity": "info"},
    )

    assert response.status_code == 200
    assert calls
    assert calls[0]["route"].id == route.id
    db_session.refresh(route)
    assert route.last_delivery_status == "delivered"
    event = db_session.scalar(select(WebhookDeliveryEvent).where(WebhookDeliveryEvent.route_id == route.id))
    assert event is not None
    assert event.status == "delivered"
    result = json.loads(event.delivery_result_json)
    assert result["backend"] == "graph"
    assert result["message_id"] == "graph-message-id"


def test_graph_delivery_backend_records_safe_service_failure(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch):
    from app.services.teams_graph_delivery import GraphDeliveryError

    route = add_route(db_session)
    route.delivery_backend = "graph"
    route.bot_service_url = ""
    route.bot_conversation_id = ""
    route.graph_target_kind = "chat"
    route.graph_target_id = "chat-id"
    db_session.commit()
    csrf_token = login_admin(client)

    def fail_graph_delivery(*args, **kwargs):
        raise GraphDeliveryError(
            "Delegated Graph delivery is not ready. Reconnect the service user in Settings.",
            error_type="auth_error",
            result={"backend": "graph", "error_type": "auth_error"},
        )

    monkeypatch.setattr("app.routers.webhook_routes.send_graph_message", fail_graph_delivery)

    response = client.post(
        f"/api/v1/webhook-routes/{route.id}/test",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "Test", "text": "Hello", "severity": "info"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Delegated Graph delivery is not ready. Reconnect the service user in Settings."
    event = db_session.scalar(select(WebhookDeliveryEvent).where(WebhookDeliveryEvent.route_id == route.id))
    assert event is not None
    assert event.status == "failed"
    assert json.loads(event.delivery_result_json) == {"backend": "graph", "error_type": "auth_error"}


def test_mixed_mode_delivery_summaries_keep_backend_separate_from_mode(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    bot_route = add_route(db_session, token="bot-token")
    graph_route = add_route(db_session, token="graph-token")
    graph_route.name = "Graph route"
    graph_route.delivery_backend = "graph"
    graph_route.bot_service_url = ""
    graph_route.bot_conversation_id = ""
    graph_route.graph_target_kind = "chat"
    graph_route.graph_target_id = "chat-id"
    db_session.commit()
    csrf_token = login_admin(client)

    class FakeGraphResult:
        def to_dict(self):
            return {
                "backend": "graph",
                "mode": "real",
                "status_code": 201,
                "message_id": "graph-message-id",
                "target": {"kind": "chat", "chat_id": "chat-id"},
            }

    monkeypatch.setattr("app.routers.webhook_routes.send_graph_message", lambda *args, **kwargs: FakeGraphResult())

    bot_response = client.post(
        f"/api/v1/webhook-routes/{bot_route.id}/test",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "Bot", "text": "Hello", "severity": "info"},
    )
    graph_response = client.post(
        f"/api/v1/webhook-routes/{graph_route.id}/test",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "Graph", "text": "Hello", "severity": "info"},
    )

    assert bot_response.status_code == 200
    assert graph_response.status_code == 200
    response = client.get("/api/v1/webhook-delivery-events?page_size=10")

    assert response.status_code == 200
    rows_by_title = {row["title"]: row for row in response.json()["items"]}
    assert rows_by_title["Bot"]["delivery_backend"] == "bot_framework"
    assert rows_by_title["Bot"]["delivery_mode"] == "mock"
    assert rows_by_title["Graph"]["delivery_backend"] == "graph"
    assert rows_by_title["Graph"]["delivery_mode"] == "real"
    assert rows_by_title["Graph"]["status_code"] == 201


def test_delivery_events_endpoint_filters_by_status(client: TestClient, db_session: Session):
    route = add_route(db_session)
    login_admin(client)
    for status_value in ("delivered", "failed", "rejected"):
        db_session.add(
            WebhookDeliveryEvent(
                organization_id=route.organization_id,
                route_id=route.id,
                route_token_hash=route.route_token_hash,
                status=status_value,
                request_metadata_json=dumps_json({"payload_preview": status_value}),
                normalized_message_json=dumps_json({"title": status_value}),
                delivery_result_json=dumps_json({"backend": "bot_framework", "mode": "mock"}),
            )
        )
    db_session.commit()

    for status_value in ("delivered", "failed", "rejected"):
        response = client.get(f"/api/v1/webhook-routes/{route.id}/deliveries?status={status_value}")

        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["status"] == status_value


def test_delivery_events_endpoint_rejects_invalid_status_filter(client: TestClient, db_session: Session):
    route = add_route(db_session)
    login_admin(client)

    response = client.get(f"/api/v1/webhook-routes/{route.id}/deliveries?status=unknown")

    assert response.status_code == 422


def test_delivery_events_endpoint_uses_stable_order_for_equal_timestamps(client: TestClient, db_session: Session):
    route = add_route(db_session)
    login_admin(client)
    created_at = utcnow()
    db_session.add_all(
        [
            WebhookDeliveryEvent(
                id="00000000-0000-0000-0000-000000000001",
                organization_id=route.organization_id,
                route_id=route.id,
                route_token_hash=route.route_token_hash,
                status="delivered",
                normalized_message_json=dumps_json({"title": "First"}),
                created_at=created_at,
            ),
            WebhookDeliveryEvent(
                id="00000000-0000-0000-0000-000000000002",
                organization_id=route.organization_id,
                route_id=route.id,
                route_token_hash=route.route_token_hash,
                status="delivered",
                normalized_message_json=dumps_json({"title": "Second"}),
                created_at=created_at,
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/v1/webhook-delivery-events?page=1&page_size=2")

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == ["Second", "First"]


def test_global_delivery_events_endpoint_paginates_summaries(client: TestClient, db_session: Session):
    route = add_route(db_session)
    login_admin(client)
    for index in range(3):
        db_session.add(
            WebhookDeliveryEvent(
                organization_id=route.organization_id,
                route_id=route.id,
                route_token_hash=route.route_token_hash,
                status="delivered" if index != 1 else "failed",
                request_metadata_json=dumps_json({"payload_preview": f"payload-{index}"}),
                normalized_message_json=dumps_json({"title": f"Message {index}", "raw_type": "json_object"}),
                delivery_result_json=dumps_json({"backend": "bot_framework", "mode": "mock", "status_code": 202}),
                error="failed send" if index == 1 else "",
                created_at=utcnow() + timedelta(minutes=index),
            )
        )
    db_session.commit()

    response = client.get("/api/v1/webhook-delivery-events?page=1&page_size=2")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total_pages"] == 2
    assert body["retention_days"] == 7
    assert len(body["items"]) == 2
    assert body["items"][0]["route_name"] == route.name
    assert body["items"][0]["title"] == "Message 2"
    assert body["items"][0]["delivery_backend"] == "bot_framework"
    assert body["items"][0]["delivery_mode"] == "mock"
    assert body["items"][0]["status_code"] == 202


def test_global_delivery_events_endpoint_searches_message_and_route_fields(client: TestClient, db_session: Session):
    route = add_route(db_session, token="search-one")
    other_route = add_route(db_session, token="search-two")
    login_admin(client)
    db_session.add_all(
        [
            WebhookDeliveryEvent(
                organization_id=route.organization_id,
                route_id=route.id,
                route_token_hash=route.route_token_hash,
                status="delivered",
                normalized_message_json=dumps_json({"title": "Power supply alert", "raw_type": "json_object"}),
                request_metadata_json=dumps_json({"payload_preview": "rack psu failure"}),
            ),
            WebhookDeliveryEvent(
                organization_id=other_route.organization_id,
                route_id=other_route.id,
                route_token_hash=other_route.route_token_hash,
                status="failed",
                normalized_message_json=dumps_json({"title": "Unrelated message", "raw_type": "json_object"}),
                error="No match here",
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/v1/webhook-delivery-events?q=power")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["route_id"] == route.id
    assert body["items"][0]["title"] == "Power supply alert"


def test_global_delivery_events_endpoint_filters_by_route(client: TestClient, db_session: Session):
    route = add_route(db_session, token="filter-one")
    other_route = add_route(db_session, token="filter-two")
    login_admin(client)
    for current_route in (route, other_route):
        db_session.add(
            WebhookDeliveryEvent(
                organization_id=current_route.organization_id,
                route_id=current_route.id,
                route_token_hash=current_route.route_token_hash,
                status="delivered",
                normalized_message_json=dumps_json({"title": current_route.name}),
            )
        )
    db_session.commit()

    response = client.get(f"/api/v1/webhook-delivery-events?route_id={route.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["route_id"] == route.id


def test_global_delivery_event_detail_returns_json_payloads(client: TestClient, db_session: Session):
    route = add_route(db_session)
    login_admin(client)
    event = WebhookDeliveryEvent(
        organization_id=route.organization_id,
        route_id=route.id,
        route_token_hash=route.route_token_hash,
        status="failed",
        request_metadata_json=dumps_json({"payload_preview": "payload"}),
        normalized_message_json=dumps_json({"title": "Failure"}),
        delivery_result_json=dumps_json({"backend": "bot_framework", "mode": "mock"}),
        error="send failed",
    )
    db_session.add(event)
    db_session.commit()

    response = client.get(f"/api/v1/webhook-delivery-events/{event.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["route_name"] == route.name
    assert body["target_name"] == "Monitoring"
    assert body["request_metadata"]["payload_preview"] == "payload"
    assert body["normalized_message"]["title"] == "Failure"
    assert body["delivery_result"]["backend"] == "bot_framework"
    assert body["delivery_result"]["mode"] == "mock"
    assert body["error"] == "send failed"


def test_log_cleanup_uses_retention_days_from_env(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings
    from app.core.settings_overrides import reset_override_state
    from app.services import log_retention

    monkeypatch.setenv("LOG_RETENTION_DAYS", "2")
    get_settings.cache_clear()
    reset_override_state()
    log_retention._last_log_cleanup_at = None
    route = add_route(db_session)
    old_event = WebhookDeliveryEvent(
        organization_id=route.organization_id,
        route_id=route.id,
        status="delivered",
        created_at=utcnow() - timedelta(days=3),
    )
    fresh_event = WebhookDeliveryEvent(
        organization_id=route.organization_id,
        route_id=route.id,
        status="delivered",
        created_at=utcnow() - timedelta(days=1),
    )
    old_audit = AuditEvent(
        organization_id=route.organization_id,
        actor_type="user",
        action="old.audit",
        created_at=utcnow() - timedelta(days=3),
    )
    fresh_audit = AuditEvent(
        organization_id=route.organization_id,
        actor_type="user",
        action="fresh.audit",
        created_at=utcnow() - timedelta(days=1),
    )
    old_activity = BotActivityEvent(activity_type="message", created_at=utcnow() - timedelta(days=3))
    fresh_activity = BotActivityEvent(activity_type="message", created_at=utcnow() - timedelta(days=1))
    db_session.add_all([old_event, fresh_event, old_audit, fresh_audit, old_activity, fresh_activity])
    db_session.commit()

    result = log_retention.cleanup_log_events(db_session, force=True)
    db_session.commit()

    remaining_deliveries = db_session.scalars(select(WebhookDeliveryEvent)).all()
    remaining_audits = db_session.scalars(select(AuditEvent).where(AuditEvent.action.like("%.audit"))).all()
    remaining_activities = db_session.scalars(select(BotActivityEvent)).all()
    assert result.deleted == 3
    assert result.deleted_webhook_delivery_events == 1
    assert result.deleted_audit_events == 1
    assert result.deleted_bot_activity_events == 1
    assert result.retention_days == 2
    assert [event.id for event in remaining_deliveries] == [fresh_event.id]
    assert [event.id for event in remaining_audits] == [fresh_audit.id]
    assert [event.id for event in remaining_activities] == [fresh_activity.id]
    get_settings.cache_clear()


def test_admin_cleanup_endpoint_cleans_all_log_tables(client: TestClient, db_session: Session):
    from app.services import log_retention

    log_retention._last_log_cleanup_at = None
    route = add_route(db_session)
    db_session.add_all(
        [
            WebhookDeliveryEvent(
                organization_id=route.organization_id,
                route_id=route.id,
                status="delivered",
                created_at=utcnow() - timedelta(days=8),
            ),
            AuditEvent(
                organization_id=route.organization_id,
                actor_type="user",
                action="old.audit",
                created_at=utcnow() - timedelta(days=8),
            ),
            BotActivityEvent(activity_type="message", created_at=utcnow() - timedelta(days=8)),
        ]
    )
    db_session.commit()
    csrf_token = login_admin(client)

    response = client.post("/api/v1/admin/logs/cleanup", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] == 3
    assert body["deleted_webhook_delivery_events"] == 1
    assert body["deleted_audit_events"] == 1
    assert body["deleted_bot_activity_events"] == 1


def test_delivery_log_cleanup_endpoint_returns_complete_cleanup_shape(client: TestClient, db_session: Session):
    from app.services import log_retention

    log_retention._last_log_cleanup_at = None
    route = add_route(db_session)
    db_session.add(
        WebhookDeliveryEvent(
            organization_id=route.organization_id,
            route_id=route.id,
            status="delivered",
            created_at=utcnow() - timedelta(days=8),
        )
    )
    db_session.commit()
    csrf_token = login_admin(client)

    response = client.post("/api/v1/webhook-delivery-events/cleanup", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    body = response.json()
    assert body["deleted_webhook_delivery_events"] == 1
    assert body["deleted_event_log_entries"] >= 0


def test_admin_system_logs_endpoint_returns_bot_activity_events(client: TestClient, db_session: Session):
    csrf_token = login_admin(client)
    event = BotActivityEvent(
        activity_type="message",
        conversation_type="channel",
        team_name="Operations",
        channel_name="Alerts",
        user_name="Ada Admin",
        conversation_id="conversation-id",
        team_id="team-id",
        channel_id="channel-id",
        graph_user_id="graph-user-id",
    )
    db_session.add(event)
    db_session.commit()

    response = client.get("/api/v1/admin/system-logs", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["activity_type"] == "message"
    assert rows[0]["scope"] == "channel"
    assert rows[0]["team_name"] == "Operations"
    assert rows[0]["channel_name"] == "Alerts"
    assert rows[0]["auth_status"] == "unknown"
    assert rows[0]["auth_service_url_matched"] is False
