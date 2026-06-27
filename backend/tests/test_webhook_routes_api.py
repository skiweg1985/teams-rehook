from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import create_app
from app.models import AuditEvent, BotActivityEvent, Organization, User, WebhookDeliveryEvent, WebhookRoute
from app.security import dumps_json, hash_secret, lookup_secret_hash
from app.security import utcnow


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


def add_route(db: Session, *, token: str = "route-token", active: bool = True) -> WebhookRoute:
    org = db.scalar(select(Organization).where(Organization.slug == "default"))
    assert org is not None
    route = WebhookRoute(
        organization_id=org.id,
        name=f"Route {token}",
        is_active=active,
        route_token_hash=lookup_secret_hash(token),
        route_token=token,
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
    assert json.loads(events[0].delivery_result_json)["backend"] == "bot_framework"


def test_public_webhook_rejects_unknown_token(client: TestClient, db_session: Session):
    response = client.post("/api/v1/webhooks/missing-token", json={"text": "hello"})

    assert response.status_code == 404
    events = db_session.scalars(select(WebhookDeliveryEvent)).all()
    assert len(events) == 1
    assert events[0].route_id is None
    assert events[0].status == "rejected"


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


def test_update_route_delivery_backend(client: TestClient, db_session: Session):
    route = add_route(db_session)
    csrf_token = login_admin(client)

    response = client.patch(
        f"/api/v1/webhook-routes/{route.id}",
        headers={"X-CSRF-Token": csrf_token},
        json={"delivery_backend": "graph", "bot_service_url": "", "bot_conversation_id": ""},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["delivery_backend"] == "graph"
    db_session.refresh(route)
    assert route.delivery_backend == "graph"


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


def test_graph_delivery_backend_records_clear_not_implemented_failure(client: TestClient, db_session: Session):
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

    response = client.post(
        f"/api/v1/webhook-routes/{route.id}/test",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "Test", "text": "Hello", "severity": "info"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Graph delivery is not implemented yet"
    db_session.refresh(route)
    assert route.last_delivery_status == "failed"
    event = db_session.scalar(select(WebhookDeliveryEvent).where(WebhookDeliveryEvent.route_id == route.id))
    assert event is not None
    assert event.status == "failed"
    assert event.error == "Graph delivery is not implemented yet"
    assert json.loads(event.delivery_result_json)["backend"] == "graph"


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
