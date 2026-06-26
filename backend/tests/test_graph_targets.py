from __future__ import annotations

from app.core.config import Settings
from app.services.graph_targets import fetch_graph_token, get_channel_target, get_team_target, get_user_target


def test_fetch_graph_token_uses_ms_app_credentials(monkeypatch):
    settings = Settings(
        ms_app_tenant_id="ms-tenant",
        ms_app_client_id="ms-client",
        ms_app_client_secret="ms-secret",
    )
    captured: dict[str, str] = {}

    def fake_urlopen(request, timeout=10):
        from urllib.parse import parse_qs

        body = request.data.decode("utf-8")
        captured.update({key: values[0] for key, values in parse_qs(body).items()})
        captured["tenant_path"] = request.full_url

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"access_token":"token","expires_in":3600}'

        return FakeResponse()

    monkeypatch.setattr("app.services.graph_targets.urllib.request.urlopen", fake_urlopen)

    token, expires_in = fetch_graph_token(settings)

    assert token == "token"
    assert expires_in == 3600
    assert captured["client_id"] == "ms-client"
    assert captured["client_secret"] == "ms-secret"
    assert captured["tenant_path"].endswith("/ms-tenant/oauth2/v2.0/token")


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
