from __future__ import annotations

import urllib.parse
import json
from collections.abc import Iterator
from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.database import Base, get_db
from app.main import create_app
from app.models import (
    AuditEvent,
    BotActivityEvent,
    BotAccessRole,
    BotAuthorizedGroup,
    BotAuthorizedUser,
    BotConversationReference,
    BotUserGroupMembershipCache,
    Organization,
    WebhookDeliveryEvent,
    WebhookRoute,
    WebhookUrlRevealToken,
)
from app.routers.bot_messages import _refresh_reference_chat_members, require_bot_framework_auth
from app.security import loads_json, utcnow
from app.services.bot_conversation_members import BotConversationMembersError
from app.services.bot_framework_auth import BotFrameworkClaims
from app.services.graph_targets import GraphRequestError


async def allow_bot_framework_auth():
    return BotFrameworkClaims(
        issuer="https://api.botframework.com",
        audience="test-bot-app-id",
        service_url="https://smba.trafficmanager.net/emea/",
        service_url_matched=True,
        validated_at=utcnow(),
    )


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
    org = Organization(slug="default", name="Default")
    db.add(org)
    db.flush()
    db.add(
        BotAuthorizedUser(
            organization_id=org.id,
            aad_object_id="aad-user-id",
            display_name="Ada Admin",
            user_principal_name="ada@example.com",
            role="route_manager",
            is_active=True,
            can_view_routes=True,
            can_reveal_webhook_urls=True,
            can_manage_route_status=True,
            can_delete_routes=True,
            can_manage_allowlist=True,
            can_create_private_chat_routes=True,
            can_create_channel_routes=True,
        )
    )
    db.commit()
    app = create_app()
    app.router.on_startup.clear()

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_bot_framework_auth] = allow_bot_framework_auth
    return TestClient(app), db


def card_from_sent_reply(reply: dict) -> dict:
    sent_message = reply["message"]
    assert sent_message.activity is not None
    return sent_message.activity["attachments"][0]["content"]


def collect_card_actions(value: object) -> list[dict]:
    actions: list[dict] = []
    if isinstance(value, dict):
        for action in value.get("actions") or []:
            if isinstance(action, dict):
                actions.append(action)
        for child in value.values():
            actions.extend(collect_card_actions(child))
    elif isinstance(value, list):
        for child in value:
            actions.extend(collect_card_actions(child))
    return actions


def collect_card_items(value: object, item_type: str) -> list[dict]:
    items: list[dict] = []
    if isinstance(value, dict):
        if value.get("type") == item_type:
            items.append(value)
        for child in value.values():
            items.extend(collect_card_items(child, item_type))
    elif isinstance(value, list):
        for child in value:
            items.extend(collect_card_items(child, item_type))
    return items


def assert_reveal_webhook_action(client: TestClient, db: Session, card: dict, route: WebhookRoute) -> None:
    for action in collect_card_actions(card):
        if action.get("title") != "Open webhook URL":
            continue
        assert action["type"] == "Action.OpenUrl"
        parsed = urllib.parse.urlparse(action["url"])
        assert parsed.path == "/copy-webhook"
        query = urllib.parse.parse_qs(parsed.query)
        assert set(query) == {"token"}
        token = query["token"][0]
        assert "/api/v1/webhooks/" not in action["url"]
        reveal = db.scalar(select(WebhookUrlRevealToken).where(WebhookUrlRevealToken.route_id == route.id))
        assert reveal is not None
        response = client.get(f"/api/v1/webhook-url-reveals/{token}")
        assert response.status_code == 200
        body = response.json()
        if body["route_name"] != route.name:
            continue
        assert body["webhook_url"] == expected_webhook_url(route.route_token)
        return
    raise AssertionError(f"Open webhook URL action for {route.name} not found")


def card_submit_actions(card: dict, command: str, route_name: str = "") -> list[dict]:
    matches = []
    for action in collect_card_actions(card):
        data = action.get("data")
        if action.get("type") != "Action.Submit" or not isinstance(data, dict):
            continue
        if data.get("command") != command:
            continue
        if route_name and data.get("route_name") != route_name:
            continue
        matches.append(action)
    return matches


def expected_webhook_url(route_token: str) -> str:
    settings = get_settings()
    return f"{settings.app_public_base_url.rstrip('/')}{settings.api_v1_prefix.rstrip('/')}/webhooks/{route_token}"


def update_default_bot_user(db: Session, **patch: bool | str) -> BotAuthorizedUser:
    bot_user = db.scalar(select(BotAuthorizedUser).where(BotAuthorizedUser.aad_object_id == "aad-user-id"))
    assert bot_user is not None
    for key, value in patch.items():
        setattr(bot_user, key, value)
    db.commit()
    db.refresh(bot_user)
    return bot_user


def create_bot_access_role(db: Session, **patch: bool | str) -> BotAccessRole:
    org = db.scalar(select(Organization))
    assert org is not None
    values = {
        "can_view_routes": True,
        "can_reveal_webhook_urls": True,
        "can_manage_route_status": False,
        "can_delete_routes": False,
        "can_manage_allowlist": False,
        "can_create_private_chat_routes": False,
        "can_create_channel_routes": False,
        **patch,
    }
    role = BotAccessRole(
        organization_id=org.id,
        name="Runtime Role",
        description="Runtime test role",
        is_system=False,
        **values,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def create_bot_group(
    db: Session,
    *,
    group_object_id: str = "group-id",
    is_active: bool = True,
    **patch: bool | str,
) -> BotAuthorizedGroup:
    org = db.scalar(select(Organization))
    assert org is not None
    values = {
        "can_view_routes": False,
        "can_reveal_webhook_urls": False,
        "can_manage_route_status": False,
        "can_delete_routes": False,
        "can_manage_allowlist": False,
        "can_create_private_chat_routes": False,
        "can_create_channel_routes": False,
        **patch,
    }
    group = BotAuthorizedGroup(
        organization_id=org.id,
        group_object_id=group_object_id,
        display_name="Bot Operators",
        mail="bot-operators@example.com",
        security_enabled=True,
        group_types_json="[]",
        role="custom",
        is_active=is_active,
        **values,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


def cache_group_membership(db: Session, group_ids: list[str], *, aad_object_id: str = "aad-user-id", expires_in_minutes: int = 10) -> None:
    org = db.scalar(select(Organization))
    assert org is not None
    now = utcnow()
    db.add(
        BotUserGroupMembershipCache(
            organization_id=org.id,
            aad_object_id=aad_object_id,
            group_ids_json=json.dumps(group_ids),
            checked_at=now,
            expires_at=now + timedelta(minutes=expires_in_minutes),
        )
    )
    db.commit()


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
    assert event.auth_status == "verified"
    assert event.auth_issuer == "https://api.botframework.com"
    assert event.auth_audience == "test-bot-app-id"
    assert event.auth_service_url == "https://smba.trafficmanager.net/emea/"
    assert event.auth_service_url_matched is True
    assert event.auth_validated_at is not None
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


def test_bot_message_endpoint_captures_group_chat_as_chat_reference():
    client, db = make_client()
    activity = {
        "type": "message",
        "serviceUrl": "https://smba.trafficmanager.net/emea/tenant-id/",
        "conversation": {
            "id": "19:group-chat@thread.v2",
            "conversationType": "groupChat",
            "isGroup": True,
            "tenantId": "tenant-id",
        },
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "recipient": {"id": "28:bot"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    event = db.scalar(select(BotActivityEvent))
    reference = db.scalar(select(BotConversationReference))
    assert event is not None
    assert event.conversation_type == "groupchat"
    assert event.conversation_id == "19:group-chat@thread.v2"
    assert event.team_id == ""
    assert event.channel_id == ""
    assert reference is not None
    assert reference.scope == "chat"
    assert reference.conversation_type == "groupchat"
    assert reference.conversation_id == "19:group-chat@thread.v2"
    assert reference.user_name == "Ada Admin"
    db.close()


def test_bot_message_endpoint_refreshes_group_chat_member_summary(monkeypatch):
    def fake_members(**kwargs):
        assert kwargs["conversation_id"] == "19:group-chat@thread.v2"
        return SimpleNamespace(
            member_summary="Ada Admin, Ben Builder",
            member_count=2,
            members=[
                SimpleNamespace(to_dict=lambda: {"id": "29:ada", "name": "Ada Admin", "aad_object_id": "", "email": "", "user_principal_name": ""}),
                SimpleNamespace(to_dict=lambda: {"id": "29:ben", "name": "Ben Builder", "aad_object_id": "", "email": "", "user_principal_name": ""}),
            ],
        )

    monkeypatch.setattr("app.routers.bot_messages.fetch_bot_conversation_members", fake_members)
    client, db = make_client()
    activity = {
        "type": "message",
        "serviceUrl": "https://smba.trafficmanager.net/emea/tenant-id/",
        "conversation": {"id": "19:group-chat@thread.v2", "conversationType": "groupChat", "isGroup": True},
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    reference = db.scalar(select(BotConversationReference))
    assert reference is not None
    assert reference.member_summary == "Ada Admin, Ben Builder"
    assert reference.member_count == 2
    assert reference.members_refreshed_at is not None
    assert reference.members_lookup_error == ""
    db.close()


def test_bot_message_endpoint_keeps_group_chat_when_member_lookup_fails(monkeypatch):
    def fail_members(**kwargs):
        raise BotConversationMembersError("member lookup unavailable")

    monkeypatch.setattr("app.routers.bot_messages.fetch_bot_conversation_members", fail_members)
    client, db = make_client()
    activity = {
        "type": "message",
        "serviceUrl": "https://smba.trafficmanager.net/emea/tenant-id/",
        "conversation": {"id": "19:group-chat@thread.v2", "conversationType": "groupChat", "isGroup": True},
        "from": {"id": "29:user", "name": "Ada Admin"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    reference = db.scalar(select(BotConversationReference))
    assert reference is not None
    assert reference.scope == "chat"
    assert reference.member_summary == ""
    assert reference.members_lookup_error == "member lookup unavailable"
    db.close()


def test_group_chat_member_refresh_tolerates_naive_database_timestamp(monkeypatch):
    def fail_if_called(**kwargs):
        raise AssertionError("fresh member lookup should be skipped")

    monkeypatch.setattr("app.routers.bot_messages.fetch_bot_conversation_members", fail_if_called)
    reference = BotConversationReference(
        scope="chat",
        conversation_type="groupChat",
        service_url="https://smba.trafficmanager.net/emea/tenant-id/",
        conversation_id="19:group-chat@thread.v2",
        members_refreshed_at=datetime.now() - timedelta(minutes=5),
    )

    changed = _refresh_reference_chat_members(reference)

    assert changed is False


def test_register_command_creates_webhook_route_from_current_conversation(monkeypatch):
    sent_replies: list[dict] = []

    def fake_send_bot_activity(**kwargs):
        sent_replies.append(kwargs)

    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", fake_send_bot_activity)
    client, db = make_client()
    activity = {
        "type": "message",
        "text": "<at>Relay Bot</at> register Jira Alerts",
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
    assert "/webhooks/" not in body["reply_text"]
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
    assert_reveal_webhook_action(client, db, card, route)
    assert any(action["type"] == "Action.ToggleVisibility" for action in card["actions"])
    assert any(item.get("id") == "technicalDetails" and item.get("isVisible") is False for item in card["body"])
    db.close()


def test_register_command_treats_group_chat_as_chat_target(monkeypatch):
    def fake_members(**kwargs):
        return SimpleNamespace(member_summary="Ada Admin, Ben Builder", member_count=2, members=[])

    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    monkeypatch.setattr("app.routers.bot_messages.fetch_bot_conversation_members", fake_members)
    client, db = make_client()
    activity = {
        "type": "message",
        "text": "<at>Relay Bot</at> register Ops Chat",
        "serviceUrl": "https://smba.trafficmanager.net/emea/tenant-id/",
        "conversation": {
            "id": "19:group-chat@thread.v2",
            "conversationType": "groupChat",
            "isGroup": True,
            "tenantId": "tenant-id",
        },
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "recipient": {"id": "28:bot"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Ops Chat"))
    reference = db.scalar(select(BotConversationReference))
    assert reference is not None
    assert reference.scope == "chat"
    assert route is not None
    assert route.target_name == "Ada Admin, Ben Builder"
    assert route.bot_conversation_id == "19:group-chat@thread.v2"
    assert route.graph_target_kind == "chat"
    assert route.graph_target_id == "19:group-chat@thread.v2"
    assert route.graph_channel_id == ""
    assert route.member_summary == "Ada Admin, Ben Builder"
    assert route.member_count == 2
    assert route.bot_registered_by_id == "aad-user-id"
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
        "text": "register Jira Alerts",
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
        "text": "register Jira Alerts",
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
        "text": "register Jira Alerts",
        "serviceUrl": "https://old.example/",
        "conversation": {"id": "conversation-one", "conversationType": "personal"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }
    second = {
        "type": "message",
        "text": "register Jira Alerts",
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
        "text": f"register {'x' * 201}",
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


def test_bot_command_denies_unknown_aad_user_and_keeps_reference(monkeypatch):
    sent_replies: list[dict] = []
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: sent_replies.append(kwargs))
    client, db = make_client()
    activity = {
        "type": "message",
        "text": "register Personal Alerts",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "name": "Mallory", "aadObjectId": "unknown-aad-user"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    body = response.json()
    assert body["handled_command"] is True
    assert body["command"] == "register"
    assert "not authorized" in body["reply_text"]
    assert db.scalar(select(WebhookRoute)) is None
    reference = db.scalar(select(BotConversationReference))
    assert reference is not None
    assert reference.conversation_id == "conversation-id"
    event = db.scalar(select(BotActivityEvent))
    assert event is not None
    assert event.bot_authorization_status == "denied"
    assert event.bot_authorization_reason == "bot_user_not_authorized"
    audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "bot_command.denied"))
    assert audit is not None
    assert sent_replies
    db.close()


def test_bot_command_denies_missing_aad_object_id(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    activity = {
        "type": "message",
        "text": "register Personal Alerts",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "name": "Legacy User"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    assert "not authorized" in response.json()["reply_text"]
    assert db.scalar(select(WebhookRoute)) is None
    event = db.scalar(select(BotActivityEvent))
    assert event is not None
    assert event.bot_authorization_reason == "missing_aad_object_id"
    db.close()


def test_bot_command_denies_missing_register_permission(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    update_default_bot_user(
        db,
        role="viewer",
        can_view_routes=True,
        can_reveal_webhook_urls=True,
        can_manage_route_status=False,
        can_delete_routes=False,
        can_manage_allowlist=False,
        can_create_private_chat_routes=False,
        can_create_channel_routes=False,
    )
    activity = {
        "type": "message",
        "text": "register Personal Alerts",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    assert "do not have permission" in response.json()["reply_text"]
    assert db.scalar(select(WebhookRoute)) is None
    event = db.scalar(select(BotActivityEvent))
    assert event is not None
    assert event.bot_authorization_status == "permission_denied"
    assert event.bot_authorization_reason == "missing_can_create_private_chat_routes"
    audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "bot_command.permission_denied"))
    assert audit is not None
    db.close()


def test_bot_command_uses_linked_role_permissions(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    role = create_bot_access_role(db, can_create_private_chat_routes=False)
    update_default_bot_user(
        db,
        role_id=role.id,
        role="role",
        can_view_routes=False,
        can_reveal_webhook_urls=False,
        can_manage_route_status=False,
        can_delete_routes=False,
        can_manage_allowlist=False,
        can_create_private_chat_routes=False,
        can_create_channel_routes=False,
    )
    activity = {
        "type": "message",
        "text": "register Role Alerts",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    denied = client.post("/api/v1/bot/messages", json=activity)
    assert denied.status_code == 200
    assert "do not have permission" in denied.json()["reply_text"]
    assert db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Role Alerts")) is None

    role.can_create_private_chat_routes = True
    db.commit()
    allowed = client.post("/api/v1/bot/messages", json=activity)
    assert allowed.status_code == 200
    assert allowed.json()["command"] == "register"
    assert db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Role Alerts")) is not None
    db.close()


def test_bot_command_allows_group_only_permission_from_cache(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    db.execute(delete(BotAuthorizedUser))
    create_bot_group(db, can_create_private_chat_routes=True)
    cache_group_membership(db, ["group-id"])
    activity = {
        "type": "message",
        "text": "register Group Alerts",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    assert response.json()["command"] == "register"
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Group Alerts"))
    assert route is not None
    audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "bot_command.authorized"))
    assert audit is not None
    metadata = loads_json(audit.metadata_json, {})
    assert metadata["authorization_sources"]["direct_user"] is None
    assert metadata["authorization_sources"]["groups"][0]["group_object_id"] == "group-id"
    assert metadata["authorization_sources"]["cache_status"] == "hit"
    db.close()


def test_bot_command_unions_direct_and_group_permissions(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    update_default_bot_user(
        db,
        role="viewer",
        can_view_routes=True,
        can_reveal_webhook_urls=True,
        can_manage_route_status=False,
        can_delete_routes=False,
        can_manage_allowlist=False,
        can_create_private_chat_routes=False,
        can_create_channel_routes=False,
    )
    create_bot_group(db, can_create_private_chat_routes=True)
    cache_group_membership(db, ["group-id"])
    activity = {
        "type": "message",
        "text": "register Union Alerts",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    assert db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Union Alerts")) is not None
    db.close()


def test_inactive_bot_group_does_not_grant_permission(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    db.execute(delete(BotAuthorizedUser))
    create_bot_group(db, is_active=False, can_create_private_chat_routes=True)
    activity = {
        "type": "message",
        "text": "register Inactive Group Alerts",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    assert "not authorized" in response.json()["reply_text"]
    assert db.scalar(select(WebhookRoute)) is None
    db.close()


def test_expired_group_membership_cache_refreshes_from_graph(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    monkeypatch.setattr("app.routers.bot_messages.list_user_transitive_group_ids", lambda user_id: ["group-id"])
    client, db = make_client()
    db.execute(delete(BotAuthorizedUser))
    create_bot_group(db, can_create_private_chat_routes=True)
    cache_group_membership(db, [], expires_in_minutes=-1)
    activity = {
        "type": "message",
        "text": "register Refreshed Alerts",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    assert db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Refreshed Alerts")) is not None
    audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "bot_command.authorized"))
    assert audit is not None
    assert loads_json(audit.metadata_json, {})["authorization_sources"]["cache_status"] == "miss"
    db.close()


def test_graph_failure_with_valid_cache_still_authorizes_group(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    monkeypatch.setattr("app.routers.bot_messages.list_user_transitive_group_ids", lambda user_id: (_ for _ in ()).throw(GraphRequestError("Graph down")))
    client, db = make_client()
    db.execute(delete(BotAuthorizedUser))
    create_bot_group(db, can_create_private_chat_routes=True)
    cache_group_membership(db, ["group-id"])
    activity = {
        "type": "message",
        "text": "register Cached Alerts",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    assert db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Cached Alerts")) is not None
    db.close()


def test_graph_failure_without_valid_cache_denies_safely(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    monkeypatch.setattr("app.routers.bot_messages.list_user_transitive_group_ids", lambda user_id: (_ for _ in ()).throw(GraphRequestError("Graph down")))
    client, db = make_client()
    db.execute(delete(BotAuthorizedUser))
    create_bot_group(db, can_create_private_chat_routes=True)
    activity = {
        "type": "message",
        "text": "register No Cache Alerts",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }

    response = client.post("/api/v1/bot/messages", json=activity)

    assert response.status_code == 200
    assert "cannot verify your authorization right now" in response.json()["reply_text"]
    assert db.scalar(select(WebhookRoute)) is None
    event = db.scalar(select(BotActivityEvent).where(BotActivityEvent.activity_type == "message"))
    assert event is not None
    assert event.bot_authorization_reason == "group_membership_lookup_unavailable"
    db.close()


def test_register_permissions_distinguish_private_chat_and_channel(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    update_default_bot_user(
        db,
        role="custom",
        can_view_routes=True,
        can_reveal_webhook_urls=False,
        can_manage_route_status=False,
        can_delete_routes=False,
        can_manage_allowlist=False,
        can_create_private_chat_routes=True,
        can_create_channel_routes=False,
    )
    personal_activity = {
        "type": "message",
        "text": "register Personal Alerts",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "personal-conversation", "conversationType": "personal"},
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }
    channel_activity = {
        "type": "message",
        "text": "register Channel Alerts",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "19:channel@thread.tacv2;messageid=123", "conversationType": "channel"},
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "channelData": {
            "tenant": {"id": "tenant-id"},
            "team": {"id": "team-id", "aadGroupId": "graph-team-id", "name": "Operations"},
            "channel": {"id": "19:channel@thread.tacv2", "name": "Alerts"},
        },
    }

    personal_response = client.post("/api/v1/bot/messages", json=personal_activity)
    channel_response = client.post("/api/v1/bot/messages", json=channel_activity)

    assert personal_response.status_code == 200
    assert personal_response.json()["reply_text"].startswith("Route `Personal Alerts` created")
    assert "do not have permission to reveal" in personal_response.json()["reply_text"]
    assert channel_response.status_code == 200
    assert "do not have permission" in channel_response.json()["reply_text"]
    assert db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Personal Alerts")) is not None
    assert db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Channel Alerts")) is None
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
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Personal Alerts"}).status_code == 200

    webhook_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "webhook Personal Alerts"})
    info_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "info"})

    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Personal Alerts"))
    assert route is not None
    assert webhook_response.status_code == 200
    assert "Webhook URL for `Personal Alerts` is available" in webhook_response.json()["reply_text"]
    assert expected_webhook_url(route.route_token) not in webhook_response.json()["reply_text"]
    assert info_response.status_code == 200
    reply_text = info_response.json()["reply_text"]
    assert "AAD user ID: `aad-user-id`" in reply_text
    assert "Conversation ID: `conversation-id`" in reply_text
    assert "Linked route: `Personal Alerts`" in reply_text
    assert route.route_token
    webhook_card = card_from_sent_reply(sent_replies[1])
    info_card = card_from_sent_reply(sent_replies[2])
    assert_reveal_webhook_action(client, db, webhook_card, route)
    assert_reveal_webhook_action(client, db, info_card, route)
    db.close()


def test_info_command_omits_webhook_reveal_without_reveal_permission(monkeypatch):
    sent_replies: list[dict] = []
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: sent_replies.append(kwargs))
    client, db = make_client()
    base_activity = {
        "type": "message",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "name": "Ada Admin", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Personal Alerts"}).status_code == 200
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Personal Alerts"))
    assert route is not None
    db.execute(delete(WebhookUrlRevealToken))
    update_default_bot_user(
        db,
        role="custom",
        can_view_routes=True,
        can_reveal_webhook_urls=False,
        can_manage_route_status=False,
        can_delete_routes=False,
        can_manage_allowlist=False,
        can_create_private_chat_routes=False,
        can_create_channel_routes=False,
    )

    info_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "info"})
    webhook_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "webhook Personal Alerts"})

    assert info_response.status_code == 200
    assert "Webhook URL: unavailable" in info_response.json()["reply_text"]
    info_card = card_from_sent_reply(sent_replies[-2])
    assert "/copy-webhook?token=" not in repr(info_card)
    assert not card_submit_actions(info_card, "disable", "Personal Alerts")
    assert db.scalar(select(WebhookUrlRevealToken)) is None
    assert webhook_response.status_code == 200
    assert "do not have permission" in webhook_response.json()["reply_text"]
    assert db.scalar(select(WebhookUrlRevealToken)) is None
    db.close()


def test_allowlist_command_shows_and_updates_single_linked_route(monkeypatch):
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
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Personal Alerts"}).status_code == 200

    restricted_response = client.post(
        "/api/v1/bot/messages",
        json={**base_activity, "text": "allowlist restricted 203.0.113.10, 10.0.0.0/24"},
    )
    show_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "allowlist"})
    public_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "allowlist public"})

    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Personal Alerts"))
    assert route is not None
    assert restricted_response.status_code == 200
    assert "restricted (2 allowed)" in restricted_response.json()["reply_text"]
    assert "203.0.113.10" in show_response.json()["reply_text"]
    assert "10.0.0.0/24" in show_response.json()["reply_text"]
    assert public_response.status_code == 200
    db.refresh(route)
    assert route.client_ip_access_mode == "public"
    assert route.client_ip_allowlist == ""
    assert "updated to `public`" in public_response.json()["reply_text"]
    assert "Client IP access updated" in repr(card_from_sent_reply(sent_replies[-1]))
    db.close()


def test_allowlist_command_targets_named_route_when_multiple_are_linked(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    base_activity = {
        "type": "message",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Primary Alerts"}).status_code == 200
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Secondary Alerts"}).status_code == 200

    unnamed_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "allowlist restricted 203.0.113.10"})
    named_response = client.post(
        "/api/v1/bot/messages",
        json={**base_activity, "text": "allowlist restricted Secondary Alerts: 203.0.113.10"},
    )

    primary = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Primary Alerts"))
    secondary = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Secondary Alerts"))
    assert primary is not None
    assert secondary is not None
    assert "Multiple routes are linked" in unnamed_response.json()["reply_text"]
    assert named_response.status_code == 200
    assert primary.client_ip_access_mode == "public"
    assert secondary.client_ip_access_mode == "restricted"
    assert secondary.client_ip_allowlist == "203.0.113.10"
    db.close()


def test_allowlist_command_rejects_invalid_entries(monkeypatch):
    monkeypatch.setattr("app.routers.bot_messages.send_bot_activity", lambda **kwargs: None)
    client, db = make_client()
    base_activity = {
        "type": "message",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "personal"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {"tenant": {"id": "tenant-id"}},
    }
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Personal Alerts"}).status_code == 200

    response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "allowlist restricted not-an-ip"})

    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Personal Alerts"))
    assert route is not None
    assert response.status_code == 200
    assert response.json()["command"] == "allowlist"
    assert "IP addresses or CIDR ranges" in response.json()["reply_text"]
    assert route.client_ip_access_mode == "public"
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
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Primary Alerts"}).status_code == 200
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Secondary Alerts"}).status_code == 200
    primary = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Primary Alerts"))
    secondary = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Secondary Alerts"))
    assert primary is not None
    assert secondary is not None

    response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "info"})

    assert response.status_code == 200
    reply_text = response.json()["reply_text"]
    assert "Linked routes: `2`" in reply_text
    assert "`Primary Alerts`" in reply_text
    assert "`Secondary Alerts`" in reply_text
    assert expected_webhook_url(primary.route_token) not in reply_text
    assert expected_webhook_url(secondary.route_token) not in reply_text
    assert "Team: Operations" in reply_text
    assert "Channel: Ops Alerts" in reply_text
    assert "User: Ada Admin" in reply_text
    assert "Details: info Primary Alerts" in reply_text
    assert "Details: info Secondary Alerts" in reply_text
    info_card = card_from_sent_reply(sent_replies[2])
    card_text = repr(info_card)
    assert expected_webhook_url(primary.route_token) not in card_text
    assert expected_webhook_url(secondary.route_token) not in card_text
    assert "/copy-webhook?token=" in card_text
    assert "/copy-webhook?url=" not in card_text
    assert_reveal_webhook_action(client, db, info_card, primary)
    assert_reveal_webhook_action(client, db, info_card, secondary)
    assert card_submit_actions(info_card, "info", "Primary Alerts")
    assert card_submit_actions(info_card, "disable", "Primary Alerts")
    db.close()


def test_info_command_omits_missing_user_team_and_channel_fields_from_card(monkeypatch):
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
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Personal Alerts"}).status_code == 200
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Secondary Alerts"}).status_code == 200

    response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "info"})

    assert response.status_code == 200
    info_card = card_from_sent_reply(sent_replies[2])
    card_text = repr(info_card)
    assert "Personal Alerts" in card_text
    assert "Secondary Alerts" in card_text
    assert "/copy-webhook?token=" in card_text
    assert card_submit_actions(info_card, "info", "Personal Alerts")
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
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Primary Alerts"}).status_code == 200
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Secondary Alerts"}).status_code == 200

    response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "info"})

    assert response.status_code == 200
    info_card = card_from_sent_reply(sent_replies[2])
    visible_facts = collect_card_items(info_card["body"], "FactSet")[0]["facts"]
    visible_fact_titles = {fact["title"] for fact in visible_facts}
    assert "User:" not in visible_fact_titles
    assert "Team:" not in visible_fact_titles
    assert "Channel:" not in visible_fact_titles
    route_blocks = [item["text"] for item in collect_card_items(info_card["body"], "TextBlock")]
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
        "text": "info",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "conversation": {"id": "conversation-id", "conversationType": "channel"},
        "from": {"id": "29:user", "aadObjectId": "aad-user-id"},
        "channelData": {
            "tenant": {"id": "tenant-id"},
            "team": {"id": "team-id", "aadGroupId": "graph-team-id"},
            "channel": {"id": "channel-id"},
        },
    }
    assert client.post("/api/v1/bot/messages", json={**register_activity, "text": "register Jira Infra"}).status_code == 200

    response = client.post("/api/v1/bot/messages", json=info_activity)

    assert response.status_code == 200
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Jira Infra"))
    assert route is not None
    assert route.target_name == "Operations / Ops Alerts"
    info_card = card_from_sent_reply(sent_replies[1])
    visible_facts = collect_card_items(info_card["body"], "FactSet")[0]["facts"]
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
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Personal Alerts"}).status_code == 200
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Personal Alerts"))
    assert route is not None

    disable_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "disable"})
    db.refresh(route)

    assert disable_response.status_code == 200
    assert disable_response.json()["command"] == "disable"
    assert "disabled" in disable_response.json()["reply_text"]
    assert route.is_active is False

    enable_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "enable"})
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
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Primary Alerts"}).status_code == 200
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Secondary Alerts"}).status_code == 200

    response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "disable"})

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
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Primary Alerts"}).status_code == 200
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Secondary Alerts"}).status_code == 200

    disable_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "disable Secondary Alerts"})
    primary = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Primary Alerts"))
    secondary = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Secondary Alerts"))
    assert primary is not None
    assert secondary is not None

    assert disable_response.status_code == 200
    assert primary.is_active is True
    assert secondary.is_active is False

    enable_response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "enable Secondary Alerts"})
    db.refresh(secondary)

    assert enable_response.status_code == 200
    assert secondary.is_active is True
    db.close()


def test_adaptive_card_submit_payloads_execute_safe_route_commands(monkeypatch):
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
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Personal Alerts"}).status_code == 200
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Personal Alerts"))
    assert route is not None

    disable_response = client.post(
        "/api/v1/bot/messages",
        json={**base_activity, "text": "", "value": {"command": "disable", "route_name": "Personal Alerts"}},
    )
    db.refresh(route)

    assert disable_response.status_code == 200
    assert disable_response.json()["command"] == "disable"
    assert route.is_active is False
    disable_card = card_from_sent_reply(sent_replies[-1])
    assert card_submit_actions(disable_card, "enable", "Personal Alerts")
    assert_reveal_webhook_action(client, db, disable_card, route)

    enable_response = client.post(
        "/api/v1/bot/messages",
        json={**base_activity, "text": "", "value": {"command": "enable Personal Alerts"}},
    )
    db.refresh(route)

    assert enable_response.status_code == 200
    assert enable_response.json()["command"] == "enable"
    assert route.is_active is True

    webhook_response = client.post(
        "/api/v1/bot/messages",
        json={**base_activity, "text": "", "value": {"command": "webhook", "route_name": "Personal Alerts"}},
    )

    assert webhook_response.status_code == 200
    assert webhook_response.json()["command"] == "webhook"
    assert "Webhook URL for `Personal Alerts` is available" in webhook_response.json()["reply_text"]
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
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Personal Alerts"}).status_code == 200
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

    response = client.post("/api/v1/bot/messages", json={**base_activity, "text": "delete Personal Alerts"})

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


def test_adaptive_card_submit_payload_cannot_delete_route(monkeypatch):
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
    assert client.post("/api/v1/bot/messages", json={**base_activity, "text": "register Personal Alerts"}).status_code == 200
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Personal Alerts"))
    assert route is not None
    sent_replies.clear()

    response = client.post(
        "/api/v1/bot/messages",
        json={**base_activity, "text": "", "value": {"command": "delete", "route_name": "Personal Alerts"}},
    )

    assert response.status_code == 200
    assert response.json()["handled_command"] is False
    assert response.json()["reply_sent"] is False
    assert sent_replies == []
    assert db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Personal Alerts")) is not None
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
    assert client.post("/api/v1/bot/messages", json={**linked_activity, "text": "register Personal Alerts"}).status_code == 200
    route = db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Personal Alerts"))
    assert route is not None

    long_name_response = client.post("/api/v1/bot/messages", json={**linked_activity, "text": f"disable {'x' * 201}"})
    unlinked_response = client.post("/api/v1/bot/messages", json={**other_activity, "text": "disable Personal Alerts"})
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
        "text": "help",
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
    assert "register <route name>" in body["reply_text"]
    assert "webhook <route name>" in body["reply_text"]
    assert "disable [route name]" in body["reply_text"]
    assert "enable [route name]" in body["reply_text"]
    assert "delete <route name>" in body["reply_text"]
    assert "info [route name]" in body["reply_text"]
    assert "allowlist [route name]" in body["reply_text"]
    assert "help" in body["reply_text"]
    assert "/register <route name>" not in body["reply_text"]
    sent_message = sent_replies[0]["message"]
    assert sent_message.activity is not None
    card = sent_message.activity["attachments"][0]["content"]
    assert card["body"][0]["text"] == "Available commands"
    command_rows = collect_card_items(card["body"], "ColumnSet")
    command_labels = [row["columns"][0]["items"][0] for row in command_rows]
    assert {
        "register <route name>:",
        "webhook <route name>:",
        "disable [route name]:",
        "enable [route name]:",
        "delete <route name>:",
        "info [route name]:",
        "allowlist [route name]:",
        "help:",
    }.issubset({label["text"] for label in command_labels})
    assert all(label["wrap"] is False for label in command_labels)
    assert card_submit_actions(card, "info")
    assert card_submit_actions(card, "help")
    db.close()


def test_slash_commands_and_unknown_text_are_ignored(monkeypatch):
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

    for text in ["/help", "/register Jira Alerts", "hello", "foo bar"]:
        response = client.post("/api/v1/bot/messages", json={**base_activity, "text": text})

        assert response.status_code == 200
        body = response.json()
        assert body["handled_command"] is False
        assert body["command"] is None
        assert body["reply_text"] is None
        assert body["reply_sent"] is False

    assert sent_replies == []
    assert db.scalar(select(WebhookRoute).where(WebhookRoute.name == "Jira Alerts")) is None
    db.close()


def test_bot_message_endpoint_ignores_empty_probe():
    client, db = make_client()

    response = client.post("/api/v1/bot/messages", content=b"")

    assert response.status_code == 200
    assert response.json()["captured_reference"] is False
    assert db.scalar(select(BotActivityEvent)) is None
    assert db.scalar(select(BotConversationReference)) is None
    db.close()
