from __future__ import annotations

import urllib.parse
from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.database import Base, get_db
from app.main import create_app
from app.models import AuditEvent, BotActivityEvent, BotConversationReference, WebhookDeliveryEvent, WebhookRoute
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


def card_from_sent_reply(reply: dict) -> dict:
    sent_message = reply["message"]
    assert sent_message.activity is not None
    return sent_message.activity["attachments"][0]["content"]


def assert_copy_webhook_action(card: dict, webhook_url: str) -> None:
    action = next(action for action in card["actions"] if action["title"] == "Copy webhook URL")
    assert action["type"] == "Action.OpenUrl"
    parsed = urllib.parse.urlparse(action["url"])
    assert parsed.path == "/copy-webhook"
    assert "/api/v1/webhooks/" not in parsed.path
    assert urllib.parse.parse_qs(parsed.query) == {"url": [webhook_url]}


def expected_webhook_url(route_token: str) -> str:
    settings = get_settings()
    return f"{settings.app_public_base_url.rstrip('/')}{settings.api_v1_prefix.rstrip('/')}/webhooks/{route_token}"


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
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
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
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
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
    sent_message = sent_replies[0]["message"]
    assert sent_message.activity is not None
    attachment = sent_message.activity["attachments"][0]
    assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"
    card = attachment["content"]
    assert card["msteams"] == {"width": "Full"}
    assert route.route_token
    assert_copy_webhook_action(card, expected_webhook_url(route.route_token))
    assert any(action["type"] == "Action.ToggleVisibility" for action in card["actions"])
    assert any(item.get("id") == "technicalDetails" and item.get("isVisible") is False for item in card["body"])
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
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
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


def test_register_command_resolves_missing_channel_names_from_graph(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)

    def fake_team(team_id: str):
        assert team_id == "graph-team-id"
        return type("Target", (), {"display_name": "Infrastruktur"})()

    def fake_channel(team_id: str, channel_id: str):
        assert team_id == "graph-team-id"
        assert channel_id == "19:channel@thread.tacv2"
        return type("Target", (), {"display_name": "Jira"})()

    monkeypatch.setattr("app.services.graph_name_resolution.get_team_target", fake_team)
    monkeypatch.setattr("app.services.graph_name_resolution.get_channel_target", fake_channel)
    client, db = make_client()
    activity = {
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

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Jira Alerts"))
    reference = db.scalar(select(BotConversationReference))
    assert route is not None
    assert route.target_name == "Infrastruktur / Jira"
    assert route.graph_team_name == "Infrastruktur"
    assert reference is not None
    assert reference.team_name == "Infrastruktur"
    assert reference.channel_name == "Jira"
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
    sent_replies: list[dict] = []
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: sent_replies.append(kwargs))
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
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Personal Alerts"))
    assert route is not None
    assert route.route_token
    webhook_url = expected_webhook_url(route.route_token)
    webhook_card = card_from_sent_reply(sent_replies[1])
    info_card = card_from_sent_reply(sent_replies[2])
    assert_copy_webhook_action(webhook_card, webhook_url)
    assert_copy_webhook_action(info_card, webhook_url)
    db.close()


def test_info_command_lists_all_linked_routes_with_core_details(monkeypatch):
    sent_replies: list[dict] = []
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: sent_replies.append(kwargs))
    client, db = make_client()
    base_activity = {
        "type": "message",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "channel", "name": "Ops Alerts"},
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "channelData": {
            "tenant": {"id": "tenant-id"},
            "team": {"id": "team-id", "aadGroupId": "graph-team-id", "name": "Operations"},
            "channel": {"id": "channel-id", "name": "Ops Alerts"},
        },
    }
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "/register Primary Alerts"}).status_code == 200
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "/register Secondary Alerts"}).status_code == 200
    primary = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Primary Alerts"))
    secondary = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Secondary Alerts"))
    assert primary is not None
    assert secondary is not None

    response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "/info"})

    assert response.status_code == 200
    reply_text = response.json()["reply_text"]
    assert "Linked routes: `2`" in reply_text
    assert "`Primary Alerts`" in reply_text
    assert "`Secondary Alerts`" in reply_text
    assert expected_webhook_url(primary.route_token) in reply_text
    assert expected_webhook_url(secondary.route_token) in reply_text
    assert "Team: Operations" in reply_text
    assert "Channel: Ops Alerts" in reply_text
    assert "User: Ada Admin" in reply_text
    assert "Details: /info Primary Alerts" in reply_text
    assert "Details: /info Secondary Alerts" in reply_text
    info_card = card_from_sent_reply(sent_replies[2])
    card_text = repr(info_card)
    primary_url = expected_webhook_url(primary.route_token)
    secondary_url = expected_webhook_url(secondary.route_token)
    assert f"URL: [{primary_url}](" in card_text
    assert f"URL: [{secondary_url}](" in card_text
    assert f"/copy-webhook?url={urllib.parse.quote_plus(primary_url)}" in card_text
    assert f"/copy-webhook?url={urllib.parse.quote_plus(secondary_url)}" in card_text
    db.close()


def test_info_command_omits_missing_user_team_and_channel_fields_from_card(monkeypatch):
    sent_replies: list[dict] = []
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: sent_replies.append(kwargs))
    client, db = make_client()
    base_activity = {
        "type": "message",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "/register Personal Alerts"}).status_code == 200
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "/register Secondary Alerts"}).status_code == 200

    response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "/info"})

    assert response.status_code == 200
    info_card = card_from_sent_reply(sent_replies[2])
    card_text = repr(info_card)
    assert "Personal Alerts" in card_text
    assert "Secondary Alerts" in card_text
    assert "URL:" in card_text
    assert "Details: /info Personal Alerts" in card_text
    assert "User:" not in card_text
    assert "Team:" not in card_text
    assert "Channel:" not in card_text
    db.close()


def test_info_command_omits_id_only_user_team_and_channel_from_visible_card(monkeypatch):
    sent_replies: list[dict] = []
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: sent_replies.append(kwargs))
    client, db = make_client()
    base_activity = {
        "type": "message",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "channel"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {
            "tenant": {"id": "tenant-id"},
            "team": {"id": "team-id", "aadGroupId": "graph-team-id"},
            "channel": {"id": "channel-id"},
        },
    }
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "/register Primary Alerts"}).status_code == 200
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "/register Secondary Alerts"}).status_code == 200

    response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "/info"})

    assert response.status_code == 200
    info_card = card_from_sent_reply(sent_replies[2])
    visible_facts = info_card["body"][2]["facts"]
    visible_fact_titles = {fact["title"] for fact in visible_facts}
    assert "User:" not in visible_fact_titles
    assert "Team:" not in visible_fact_titles
    assert "Channel:" not in visible_fact_titles
    route_blocks = [item["text"] for item in info_card["body"][3]["items"] if item["type"] == "TextBlock"]
    assert not any(text.startswith("User:") for text in route_blocks)
    assert not any(text.startswith("Team:") for text in route_blocks)
    assert not any(text.startswith("Channel:") for text in route_blocks)
    assert "graph-team-id" in repr(info_card)
    assert "channel-id" in repr(info_card)
    assert "aad-user-id" in repr(info_card)
    db.close()


def test_info_command_uses_stored_route_target_names_when_current_activity_only_has_ids(monkeypatch):
    sent_replies: list[dict] = []
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: sent_replies.append(kwargs))
    client, db = make_client()
    register_activity = {
        "type": "message",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "channel", "name": "Ops Alerts"},
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "channelData": {
            "tenant": {"id": "tenant-id"},
            "team": {"id": "team-id", "aadGroupId": "graph-team-id", "name": "Operations"},
            "channel": {"id": "channel-id", "name": "Ops Alerts"},
        },
    }
    info_activity = {
        "type": "message",
        "text": "/info",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "channel"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {
            "tenant": {"id": "tenant-id"},
            "team": {"id": "team-id", "aadGroupId": "graph-team-id"},
            "channel": {"id": "channel-id"},
        },
    }
    assert client.post("/api/v1/bot/messages", json={**register_activity, "text": "/register Jira Infra"}).status_code == 200

    response = client.post("/api/v1/bot/messages", json=info_activity)

    assert response.status_code == 200
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Jira Infra"))
    assert route is not None
    assert route.target_name == "Operations / Ops Alerts"
    info_card = card_from_sent_reply(sent_replies[1])
    visible_facts = info_card["body"][2]["facts"]
    assert {"title": "Team:", "value": "Operations"} in visible_facts
    assert {"title": "Channel:", "value": "Ops Alerts"} in visible_facts
    assert "graph-team-id" in repr(info_card)
    assert "channel-id" in repr(info_card)
    db.close()


def test_disable_and_enable_commands_update_single_linked_route_without_name(monkeypatch):
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
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Personal Alerts"))
    assert route is not None

    disable_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "/disable"})
    db.refresh(route)

    assert disable_response.status_code == 200
    assert disable_response.json()["command"] == "disable"
    assert "disabled" in disable_response.json()["reply_text"]
    assert route.is_active is False

    enable_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "/enable"})
    db.refresh(route)

    assert enable_response.status_code == 200
    assert enable_response.json()["command"] == "enable"
    assert "enabled" in enable_response.json()["reply_text"]
    assert route.is_active is True
    audit_actions = [event.action for event in db.scalars(select(AuditEvent).order_by(AuditEvent.created_at)).all()]
    assert "webhook_route.disabled" in audit_actions
    assert "webhook_route.enabled" in audit_actions
    db.close()


def test_disable_command_requires_name_when_multiple_routes_are_linked(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    base_activity = {
        "type": "message",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "/register Primary Alerts"}).status_code == 200
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "/register Secondary Alerts"}).status_code == 200

    response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "/disable"})

    assert response.status_code == 200
    body = response.json()
    assert body["command"] == "disable"
    assert "Multiple routes are linked" in body["reply_text"]
    routes = db.scalars(select(WebhookRoute)).all()
    assert {route.name: route.is_active for route in routes} == {
        "Primary Alerts": True,
        "Secondary Alerts": True,
    }
    db.close()


def test_enable_and_disable_commands_target_named_route_when_multiple_are_linked(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    base_activity = {
        "type": "message",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "/register Primary Alerts"}).status_code == 200
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "/register Secondary Alerts"}).status_code == 200

    disable_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "/disable Secondary Alerts"})
    primary = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Primary Alerts"))
    secondary = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Secondary Alerts"))
    assert primary is not None
    assert secondary is not None

    assert disable_response.status_code == 200
    assert primary.is_active is True
    assert secondary.is_active is False

    enable_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "/enable Secondary Alerts"})
    db.refresh(secondary)

    assert enable_response.status_code == 200
    assert secondary.is_active is True
    db.close()


def test_delete_command_removes_named_linked_route_and_detaches_delivery_events(monkeypatch):
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
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Personal Alerts"))
    assert route is not None
    delivery = WebhookDeliveryEvent(
        organization_id=route.organization_id,
        route_id=route.id,
        route_token_hash=route.route_token_hash,
        status="delivered",
    )
    db.add(delivery)
    db.commit()

    response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "/delete Personal Alerts"})

    assert response.status_code == 200
    assert response.json()["command"] == "delete"
    assert "deleted" in response.json()["reply_text"]
    assert db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Personal Alerts")) is None
    db.refresh(delivery)
    assert delivery.route_id is None
    audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "webhook_route.deleted"))
    assert audit is not None
    assert audit.actor_type == "bot_command"
    db.close()


def test_route_mutation_commands_reject_too_long_or_unlinked_names(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    linked_activity = {
        "type": "message",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "linked-conversation", "conversationType": "personal"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }
    other_activity = {
        **linked_activity,
        "conversation": {"id": "other-conversation", "conversationType": "personal"},
    }
    assert client.post("/api/v1/bot/messages", json={**linked_activity, "text": "/register Personal Alerts"}).status_code == 200
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Personal Alerts"))
    assert route is not None

    long_name_response = client.post("/api/v1/bot/messages", json={**linked_activity, "text": f"/disable {'x' * 201}"})
    unlinked_response = client.post("/api/v1/bot/messages", json={**other_activity, "text": "/disable Personal Alerts"})
    db.refresh(route)

    assert long_name_response.status_code == 200
    assert "limited to 200 characters" in long_name_response.json()["reply_text"]
    assert unlinked_response.status_code == 200
    assert "No route named `Personal Alerts` is linked" in unlinked_response.json()["reply_text"]
    assert route.is_active is True
    db.close()


def test_help_command_lists_available_commands_as_card(monkeypatch):
    sent_replies: list[dict] = []
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: sent_replies.append(kwargs))
    client, db = make_client()
    activity = {
        "type": "message",
        "text": "/help",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    body = response.json()
    assert body["handled_command"] is True
    assert body["command"] == "help"
    assert "/register <route name>" in body["reply_text"]
    assert "/webhook <route name>" in body["reply_text"]
    assert "/disable [route name]" in body["reply_text"]
    assert "/enable [route name]" in body["reply_text"]
    assert "/delete <route name>" in body["reply_text"]
    assert "/info [route name]" in body["reply_text"]
    assert "/help" in body["reply_text"]
    sent_message = sent_replies[0]["message"]
    assert sent_message.activity is not None
    card = sent_message.activity["attachments"][0]["content"]
    assert card["body"][0]["text"] == "Available commands"
    command_facts = card["body"][2]["facts"]
    assert {
        "/register <route name>:",
        "/webhook <route name>:",
        "/disable [route name]:",
        "/enable [route name]:",
        "/delete <route name>:",
        "/info [route name]:",
        "/help:",
    }.issubset({fact["title"] for fact in command_facts})
    db.close()


def test_bot_message_endpoint_ignores_empty_probe():
    client, db = make_client()

    response = client.post("/api/v1/bot/messages", content=b"")

    assert response.status_code == 200
    assert response.json()["captured_reference"] is False
    assert db.scalar(select(BotActivityEvent)) is None
    assert db.scalar(select(BotConversationReference)) is None
    db.close()
