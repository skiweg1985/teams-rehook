from __future__ import annotations

from app.core.config import Settings
from app.services.graph_targets import get_channel_target, get_team_target, get_user_target, _graph_credentials


def test_graph_credentials_fall_back_to_bot_credentials():
    settings = Settings(
        bot_tenant_id="bot-tenant",
        bot_client_id="bot-client",
        bot_client_secret="bot-secret",
    )

    assert _graph_credentials(settings) == ("bot-tenant", "bot-client", "bot-secret")


def test_graph_credentials_override_bot_credentials():
    settings = Settings(
        bot_tenant_id="bot-tenant",
        bot_client_id="bot-client",
        bot_client_secret="bot-secret",
        graph_tenant_id="graph-tenant",
        graph_client_id="graph-client",
        graph_client_secret="graph-secret",
    )

    assert _graph_credentials(settings) == ("graph-tenant", "graph-client", "graph-secret")


def test_graph_id_lookup_helpers(monkeypatch):
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_graph_get(path: str, params: dict[str, str]) -> dict:
        calls.append((path, params))
        if path == "/teams/team-id":
            return {"id": "team-id", "displayName": "Infrastruktur", "description": "Ops"}
        if path == "/teams/team-id/channels/channel-id":
            return {"id": "channel-id", "displayName": "Jira", "membershipType": "standard"}
        if path == "/users/user-id":
            return {"id": "user-id", "displayName": "Ada Admin", "mail": "ada@example.com"}
        raise AssertionError(path)

    monkeypatch.setattr("app.services.graph_targets._graph_get", fake_graph_get)

    team = get_team_target("team-id")
    channel = get_channel_target("team-id", "channel-id")
    user = get_user_target("user-id")

    assert team is not None
    assert team.display_name == "Infrastruktur"
    assert channel is not None
    assert channel.display_name == "Jira"
    assert user is not None
    assert user.display_name == "Ada Admin"
    assert calls == [
        ("/teams/team-id", {"$select": "id,displayName,description"}),
        ("/teams/team-id/channels/channel-id", {"$select": "id,displayName,description,membershipType"}),
        ("/users/user-id", {"$select": "id,displayName,userPrincipalName,mail"}),
    ]
