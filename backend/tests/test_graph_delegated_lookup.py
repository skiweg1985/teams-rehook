from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.graph_delegated_lookup import (
    CHAT_LIST_ORDER_BY,
    DelegatedGraphChat,
    GraphDelegatedLookupError,
    list_service_user_chats,
)


def test_list_service_user_chats_uses_supported_graph_ordering(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, str, dict[str, str]]] = []

    def fake_refresh(db, *, organization_id: str, settings):
        assert organization_id == "org-id"
        return SimpleNamespace(access_token="delegated-token")

    def fake_graph_get(path: str, access_token: str, params: dict[str, str]):
        calls.append((path, access_token, params))
        return {
            "value": [
                {"id": "chat-1", "topic": "Ops alerts", "chatType": "group"},
                {"id": "chat-2", "topic": "", "chatType": "oneOnOne"},
            ]
        }

    monkeypatch.setattr("app.services.graph_delegated_lookup.refresh_delegated_access_token", fake_refresh)
    monkeypatch.setattr("app.services.graph_delegated_lookup._graph_get", fake_graph_get)

    chats = list_service_user_chats(SimpleNamespace(), organization_id="org-id", query="ops", limit=10)

    assert chats == [DelegatedGraphChat(id="chat-1", display_name="Ops alerts", subtitle="group")]
    assert calls == [
        (
            "/me/chats",
            "delegated-token",
            {
                "$top": "10",
                "$select": "id,topic,chatType",
                "$orderby": CHAT_LIST_ORDER_BY,
            },
        )
    ]
    assert "lastUpdatedDateTime" not in calls[0][2].get("$orderby", "")


def test_list_service_user_chats_retries_without_ordering_when_graph_rejects_orderby(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, str]] = []

    def fake_refresh(db, *, organization_id: str, settings):
        return SimpleNamespace(access_token="delegated-token")

    def fake_graph_get(path: str, access_token: str, params: dict[str, str]):
        calls.append(params)
        if "$orderby" in params:
            raise GraphDelegatedLookupError(
                "Microsoft Graph chat lookup failed with HTTP 400: BadRequest: QueryOptions to order by field is not supported.",
                status_code=400,
            )
        return {"value": [{"id": "chat-1", "topic": "", "chatType": "meeting"}]}

    monkeypatch.setattr("app.services.graph_delegated_lookup.refresh_delegated_access_token", fake_refresh)
    monkeypatch.setattr("app.services.graph_delegated_lookup._graph_get", fake_graph_get)

    chats = list_service_user_chats(SimpleNamespace(), organization_id="org-id", limit=25)

    assert chats == [DelegatedGraphChat(id="chat-1", display_name="Meeting chat", subtitle="meeting")]
    assert calls == [
        {
            "$top": "25",
            "$select": "id,topic,chatType",
            "$orderby": CHAT_LIST_ORDER_BY,
        },
        {
            "$top": "25",
            "$select": "id,topic,chatType",
        },
    ]


def test_list_service_user_chats_does_not_retry_unrelated_graph_errors(monkeypatch: pytest.MonkeyPatch):
    calls = 0

    def fake_refresh(db, *, organization_id: str, settings):
        return SimpleNamespace(access_token="delegated-token")

    def fake_graph_get(path: str, access_token: str, params: dict[str, str]):
        nonlocal calls
        calls += 1
        raise GraphDelegatedLookupError("Microsoft Graph chat lookup failed with HTTP 403: Forbidden", status_code=403)

    monkeypatch.setattr("app.services.graph_delegated_lookup.refresh_delegated_access_token", fake_refresh)
    monkeypatch.setattr("app.services.graph_delegated_lookup._graph_get", fake_graph_get)

    with pytest.raises(GraphDelegatedLookupError, match="HTTP 403"):
        list_service_user_chats(SimpleNamespace(), organization_id="org-id")

    assert calls == 1
