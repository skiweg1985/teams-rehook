from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.graph_targets import (
    GraphRequestError,
    fetch_graph_token,
    get_channel_target,
    get_team_target,
    get_user_target,
    list_group_transitive_members,
)


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


def test_group_member_page_stops_after_requested_window(monkeypatch):
    pages_read = 0

    def fake_pages(path: str, params: dict[str, str]):
        nonlocal pages_read
        for page_index in range(3):
            pages_read += 1
            yield {
                "value": [
                    {
                        "id": f"user-{page_index}-{member_index}",
                        "displayName": f"User {page_index}-{member_index}",
                        "userPrincipalName": f"user-{page_index}-{member_index}@example.com",
                        "mail": "",
                    }
                    for member_index in range(999)
                ]
            }

    monkeypatch.setattr("app.services.graph_targets._iter_graph_pages", fake_pages)

    page = list_group_transitive_members("group-id", limit=100, offset=0)

    assert len(page.items) == 100
    assert page.has_more is True
    assert pages_read == 1


def test_graph_page_iterator_has_safety_limit(monkeypatch):
    from app.services import graph_targets

    monkeypatch.setattr(
        "app.services.graph_targets.get_graph_token_manager",
        lambda: SimpleNamespace(get_token=lambda: "token"),
    )
    monkeypatch.setattr(
        "app.services.graph_targets._graph_get_url",
        lambda url, *, token: {"value": [], "@odata.nextLink": "https://graph.microsoft.com/v1.0/next"},
    )

    with pytest.raises(GraphRequestError, match="pagination exceeded"):
        list(graph_targets._iter_graph_pages("/groups/group-id/members", {}, max_pages=2))
