from __future__ import annotations

import urllib.error
from io import BytesIO
from types import SimpleNamespace

import pytest

from app.services.teams_graph_delivery import GraphDeliveryError, build_chat_message_payload, send_graph_message
from app.services.webhook_payloads import NormalizedMessage


def route(**overrides):
    defaults = {
        "graph_target_kind": "channel",
        "graph_target_id": "channel-id",
        "graph_team_id": "team-id",
        "graph_team_name": "Ops",
        "graph_channel_id": "channel-id",
        "target_name": "Ops / Alerts",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def fake_token():
    return SimpleNamespace(
        access_token="access-token",
        diagnostics=SimpleNamespace(
            service_user_display_name="Graph Sender",
            service_user_principal_name="sender@example.com",
        ),
    )


def test_build_chat_message_payload_escapes_html_text():
    payload = build_chat_message_payload(
        NormalizedMessage(title="<Alert>", text="Sensor <down>\nCheck & restart", severity="critical", status="down")
    )

    assert payload["body"]["contentType"] == "html"
    content = payload["body"]["content"]
    assert "&lt;Alert&gt;" in content
    assert "Sensor &lt;down&gt;<br>Check &amp; restart" in content
    assert "<strong>Status:</strong> down" in content
    assert "<strong>Severity:</strong> critical" in content


def test_build_chat_message_payload_preserves_adaptive_card_attachment():
    payload = build_chat_message_payload(
        NormalizedMessage(
            title="Card",
            text="Fallback",
            raw_type="adaptive_card_activity",
            activity={
                "type": "message",
                "attachments": [
                    {
                        "contentType": "application/vnd.microsoft.card.adaptive",
                        "content": {"type": "AdaptiveCard", "body": [{"type": "TextBlock", "text": "Hello"}]},
                    }
                ],
            },
        )
    )

    assert payload["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert "AdaptiveCard" in payload["attachments"][0]["content"]


def test_send_graph_message_posts_channel_target(monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.teams_graph_delivery.refresh_delegated_access_token", lambda *args, **kwargs: fake_token())
    monkeypatch.setattr(
        "app.services.teams_graph_delivery._graph_post_json",
        lambda path, token, payload: calls.append((path, token, payload)) or {"status_code": 201, "body": {"id": "message-id"}},
    )

    result = send_graph_message(
        SimpleNamespace(),
        organization_id="org-id",
        route=route(),
        message=NormalizedMessage(title="Alert", text="Hello"),
    )

    assert calls[0][0] == "/teams/team-id/channels/channel-id/messages"
    assert calls[0][1] == "access-token"
    assert result.to_dict()["backend"] == "graph"
    assert result.to_dict()["message_id"] == "message-id"
    assert result.to_dict()["target"]["kind"] == "channel"


def test_send_graph_message_posts_existing_chat_target(monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.teams_graph_delivery.refresh_delegated_access_token", lambda *args, **kwargs: fake_token())
    monkeypatch.setattr(
        "app.services.teams_graph_delivery._graph_post_json",
        lambda path, token, payload: calls.append(path) or {"status_code": 201, "body": {"id": "message-id"}},
    )

    result = send_graph_message(
        SimpleNamespace(),
        organization_id="org-id",
        route=route(graph_target_kind="chat", graph_target_id="chat-id"),
        message=NormalizedMessage(title="Alert", text="Hello"),
    )

    assert calls == ["/chats/chat-id/messages"]
    assert result.target["chat_id"] == "chat-id"


def test_send_graph_message_rejects_user_target_before_token(monkeypatch):
    refreshed = False

    def refresh(*args, **kwargs):
        nonlocal refreshed
        refreshed = True
        return fake_token()

    monkeypatch.setattr("app.services.teams_graph_delivery.refresh_delegated_access_token", refresh)

    with pytest.raises(GraphDeliveryError) as exc:
        send_graph_message(
            SimpleNamespace(),
            organization_id="org-id",
            route=route(graph_target_kind="user", graph_target_id="user-id"),
            message=NormalizedMessage(title="Alert", text="Hello"),
        )

    assert exc.value.error_type == "unsupported_target"
    assert refreshed is False


def test_send_graph_message_retries_adaptive_card_without_attachment_on_bad_request(monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.teams_graph_delivery.refresh_delegated_access_token", lambda *args, **kwargs: fake_token())

    def post(path, token, payload):
        calls.append(payload)
        if len(calls) == 1:
            raise GraphDeliveryError("Bad attachment", error_type="graph_http_error", status_code=400)
        return {"status_code": 201, "body": {"id": "fallback-id"}}

    monkeypatch.setattr("app.services.teams_graph_delivery._graph_post_json", post)

    result = send_graph_message(
        SimpleNamespace(),
        organization_id="org-id",
        route=route(),
        message=NormalizedMessage(
            title="Card",
            text="Fallback",
            activity={
                "type": "message",
                "attachments": [
                    {
                        "contentType": "application/vnd.microsoft.card.adaptive",
                        "content": {"type": "AdaptiveCard", "body": []},
                    }
                ],
            },
        ),
    )

    assert "attachments" in calls[0]
    assert "attachments" not in calls[1]
    assert result.message_id == "fallback-id"


def test_send_graph_message_adds_channel_membership_guidance_on_forbidden(monkeypatch):
    monkeypatch.setattr("app.services.teams_graph_delivery.refresh_delegated_access_token", lambda *args, **kwargs: fake_token())

    def post(path, token, payload):
        raise GraphDeliveryError(
            "Microsoft Graph delivery failed with HTTP 403: Forbidden: InsufficientPrivileges",
            error_type="graph_http_error",
            status_code=403,
            graph_error_code="Forbidden",
            graph_error_message="Forbidden: InsufficientPrivileges",
        )

    monkeypatch.setattr("app.services.teams_graph_delivery._graph_post_json", post)

    with pytest.raises(GraphDeliveryError) as exc:
        send_graph_message(
            SimpleNamespace(),
            organization_id="org-id",
            route=route(graph_team_name="Ops", target_name="Alerts"),
            message=NormalizedMessage(title="Alert", text="Hello"),
        )

    assert exc.value.error_type == "graph_channel_access_denied"
    assert "Add the connected Graph service user Graph Sender (sender@example.com)" in str(exc.value)
    assert "ChannelMessage.Send" in str(exc.value)
    assert exc.value.result["status_code"] == 403
    assert exc.value.result["graph_error_code"] == "Forbidden"
    assert exc.value.result["operator_message"] == str(exc.value)


def test_graph_post_json_preserves_safe_graph_error_details(monkeypatch):
    from app.services.teams_graph_delivery import _graph_post_json

    body = b'{"error":{"code":"Forbidden","message":"InsufficientPrivileges"}}'

    def fail(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            hdrs={},
            fp=BytesIO(body),
        )

    monkeypatch.setattr("urllib.request.urlopen", fail)

    with pytest.raises(GraphDeliveryError) as exc:
        _graph_post_json("/teams/team-id/channels/channel-id/messages", "access-token", {"body": {"content": "Hi"}})

    assert exc.value.status_code == 403
    assert exc.value.graph_error_code == "Forbidden"
    assert exc.value.graph_error_message == "Forbidden: InsufficientPrivileges"
