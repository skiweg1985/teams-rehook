from __future__ import annotations

from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import create_app
from app.models import BotActivityEvent, BotConversationReference, WebhookRoute
from app.security import loads_json


def make_client() -> tuple[TestClient, Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    db = SessionLocal()
    app = create_app()
    app.router.on_startup.clear()

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), db


def test_bot_message_endpoint_captures_conversation_reference():
    client, db = make_client()
    activity = {
        "type": "conversationUpdate",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
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

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["captured_reference"] is True
    event = db.scalar(select(BotActivityEvent))
    reference = db.scalar(select(BotConversationReference))
    assert event is not None
    assert event.activity_type == "conversationUpdate"
    assert event.conversation_id == "conversation-id"
    assert event.team_id == "team-id"
    assert event.channel_id == "channel-id"
    assert reference is not None
    assert reference.scope == "channel"
    assert reference.service_url == "https://smba.trafficmanager.net/emea/"
    assert reference.conversation_id == "conversation-id"
    assert reference.team_id == "team-id"
    assert reference.channel_id == "channel-id"
    assert loads_json(event.raw_activity_json, {})["type"] == "conversationUpdate"
    db.close()


def test_bot_message_endpoint_updates_existing_reference():
    client, db = make_client()
    first = {
        "type": "message",
        "serviceUrl": "https://old.example/",
        "conversation": {"id": "conversation-id"},
        "from": {"id": "user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }
    second = {
        "type": "message",
        "serviceUrl": "https://new.example/",
        "conversation": {"id": "conversation-id"},
        "from": {"id": "user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}, "team": {"id": "team-id"}},
    }

    assert client.post("/api/v1/bot/messages", json=first).status_code == 200
    assert client.post("/api/v1/bot/messages", json=second).status_code == 200

    references = db.scalars(select(BotConversationReference)).all()
    assert len(references) == 1
    assert references[0].scope == "team"
    assert references[0].service_url == "https://new.example/"
    assert references[0].team_id == "team-id"
    db.close()


def test_bot_message_endpoint_normalizes_channel_message_conversation_id():
    client, db = make_client()
    activity = {
        "type": "message",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "19:channel@thread.tacv2;messageid=1782480239835", "conversationType": "channel"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {
            "tenant": {"id": "tenant-id"},
            "team": {"id": "19:team@thread.tacv2", "aadGroupId": "graph-team-id", "name": "Infrastruktur"},
            "channel": {"id": "19:channel@thread.tacv2", "name": "Jira"},
        },
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    event = db.scalar(select(BotActivityEvent))
    reference = db.scalar(select(BotConversationReference))
    assert event is not None
    assert event.conversation_id == "19:channel@thread.tacv2"
    assert event.graph_team_id == "graph-team-id"
    assert event.graph_user_id == "aad-user-id"
    assert event.team_name == "Infrastruktur"
    assert event.channel_name == "Jira"
    assert reference is not None
    assert reference.conversation_id == "19:channel@thread.tacv2"
    assert reference.scope == "channel"
    assert reference.graph_team_id == "graph-team-id"
    db.close()


def test_register_command_creates_webhook_route_from_current_conversation(monkeypatch):
    sent_replies: list[dict] = []

    def fake_send_bot_activity(**kwargs):
        sent_replies.append(kwargs)

    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", fake_send_bot_activity)
    client, db = make_client()
    activity = {
        "type": "message",
        "text": "<at>Relay Bot</at> /register Jira Alerts",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "19:channel@thread.tacv2;messageid=1782480239835", "conversationType": "channel"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "recipient": {"id": "28:bot"},
        "channelData": {
            "tenant": {"id": "tenant-id"},
            "team": {"id": "19:team@thread.tacv2", "aadGroupId": "graph-team-id", "name": "Infrastruktur"},
            "channel": {"id": "19:channel@thread.tacv2", "name": "Jira"},
        },
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    body = response.json()
    assert body["handled_command"] is True
    assert body["command"] == "register"
    assert body["reply_sent"] is True
    assert "/webhooks/" in body["reply_text"]
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Jira Alerts"))
    assert route is not None
    assert route.bot_conversation_id == "19:channel@thread.tacv2"
    assert route.bot_service_url == "https://smba.trafficmanager.net/emea/"
    assert route.target_name == "Infrastruktur / Jira"
    assert route.graph_target_kind == "channel"
    assert route.graph_target_id == "19:channel@thread.tacv2"
    assert route.graph_team_id == "graph-team-id"
    assert route.graph_channel_id == "19:channel@thread.tacv2"
    assert route.bot_target_source == "bot_command"
    assert route.bot_registered_by_id == "aad-user-id"
    assert sent_replies[0]["conversation_id"] == "19:channel@thread.tacv2"
    db.close()


def test_register_command_uses_existing_reference_names_when_message_omits_them(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    conversation_update = {
        "type": "conversationUpdate",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "19:channel@thread.tacv2", "conversationType": "channel", "name": "Jira"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {
            "tenant": {"id": "tenant-id"},
            "team": {"id": "19:team@thread.tacv2", "aadGroupId": "graph-team-id", "name": "Infrastruktur"},
            "settings": {"selectedChannel": {"id": "19:channel@thread.tacv2"}},
        },
    }
    message = {
        "type": "message",
        "text": "/register Jira Alerts",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "19:channel@thread.tacv2;messageid=123", "conversationType": "channel"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {
            "tenant": {"id": "tenant-id"},
            "team": {"id": "19:team@thread.tacv2", "aadGroupId": "graph-team-id"},
            "teamsChannelId": "19:channel@thread.tacv2",
        },
    }

    assert client.post("/api/v1/bot/messages", json=conversation_update).status_code == 200
    response = client.post("/api/v1/bot/messages", json=message)

    assert response.status_code == 200
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Jira Alerts"))
    assert route is not None
    assert route.target_name == "Infrastruktur / Jira"
    assert route.graph_team_name == "Infrastruktur"
    assert route.graph_channel_id == "19:channel@thread.tacv2"
    db.close()


def test_register_command_updates_existing_route_without_regenerating_url(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    first = {
        "type": "message",
        "text": "/register Jira Alerts",
        "serviceUrl": "https://old.example/",
        "conversation": {"id": "conversation-one", "conversationType": "personal"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }
    second = {
        "type": "message",
        "text": "/register Jira Alerts",
        "serviceUrl": "https://new.example/",
        "conversation": {"id": "conversation-two", "conversationType": "personal"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    assert client.post("/api/v1/bot/messages", json=first).status_code == 200
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Jira Alerts"))
    assert route is not None
    first_token = route.route_token
    response = client.post("/api/v1/bot/messages", json=second)

    assert response.status_code == 200
    assert response.json()["reply_text"].startswith("Route `Jira Alerts` updated")
    routes = db.scalars(select(WebhookRoute).where(WebhookRoute.name == "Jira Alerts")).all()
    assert len(routes) == 1
    assert routes[0].route_token == first_token
    assert routes[0].bot_service_url == "https://new.example/"
    assert routes[0].bot_conversation_id == "conversation-two"
    db.close()


def test_register_command_rejects_too_long_route_name(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    activity = {
        "type": "message",
        "text": f"/register {'x' * 201}",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    assert response.json()["handled_command"] is True
    assert "limited to 200 characters" in response.json()["reply_text"]
    assert db.scalar(select(WebhookRoute)) is None
    db.close()


def test_webhook_and_info_commands_reply_with_route_and_reference_details(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    base_activity = {
        "type": "message",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "/register Personal Alerts"}).status_code == 200

    webhook_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "/webhook Personal Alerts"})
    info_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "/info"})

    assert webhook_response.status_code == 200
    assert "Webhook URL for `Personal Alerts`" in webhook_response.json()["reply_text"]
    assert info_response.status_code == 200
    reply_text = info_response.json()["reply_text"]
    assert "AAD user ID: `aad-user-id`" in reply_text
    assert "Conversation ID: `conversation-id`" in reply_text
    assert "Linked route: `Personal Alerts`" in reply_text
    db.close()


def test_bot_message_endpoint_ignores_empty_probe():
    client, db = make_client()

    response = client.post("/api/v1/bot/messages", content=b"")

    assert response.status_code == 200
    assert response.json()["captured_reference"] is False
    assert db.scalar(select(BotActivityEvent)) is None
    assert db.scalar(select(BotConversationReference)) is None
    db.close()
