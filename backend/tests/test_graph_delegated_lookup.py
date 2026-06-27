from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.graph_delegated_lookup import (
    CHAT_LIST_ORDER_BY,
    DelegatedGraphChat,
    DelegatedGraphOneOnOneChat,
    GraphDelegatedLookupError,
    create_or_get_one_on_one_chat,
    list_service_user_chats,
)


def test_list_service_user_chats_uses_supported_graph_ordering(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, str, dict[str, str]]] = []

    def fake_refresh(db, *, organization_id: str, settings):
        assert organization_id == "org-id"
        return SimpleNamespace(
            access_token="delegated-token",
            diagnostics=SimpleNamespace(service_user_id="service-user-id", service_user_principal_name="service@example.com"),
        )

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
                "$expand": "members",
                "$orderby": CHAT_LIST_ORDER_BY,
            },
        )
    ]
    assert "lastUpdatedDateTime" not in calls[0][2].get("$orderby", "")


def test_list_service_user_chats_retries_without_ordering_when_graph_rejects_orderby(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, str]] = []

    def fake_refresh(db, *, organization_id: str, settings):
        return SimpleNamespace(
            access_token="delegated-token",
            diagnostics=SimpleNamespace(service_user_id="service-user-id", service_user_principal_name="service@example.com"),
        )

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
            "$expand": "members",
            "$orderby": CHAT_LIST_ORDER_BY,
        },
        {
            "$top": "25",
            "$select": "id,topic,chatType",
            "$expand": "members",
        },
    ]


def test_list_service_user_chats_uses_other_one_on_one_member_name(monkeypatch: pytest.MonkeyPatch):
    def fake_refresh(db, *, organization_id: str, settings):
        return SimpleNamespace(
            access_token="delegated-token",
            diagnostics=SimpleNamespace(service_user_id="service-user-id", service_user_principal_name="service@example.com"),
        )

    def fake_graph_get(path: str, access_token: str, params: dict[str, str]):
        return {
            "value": [
                {
                    "id": "chat-1",
                    "topic": "",
                    "chatType": "oneOnOne",
                    "members": [
                        {"userId": "service-user-id", "displayName": "Relay User", "email": "service@example.com"},
                        {"userId": "target-user-id", "displayName": "Ada Admin", "email": "ada@example.com"},
                    ],
                }
            ]
        }

    monkeypatch.setattr("app.services.graph_delegated_lookup.refresh_delegated_access_token", fake_refresh)
    monkeypatch.setattr("app.services.graph_delegated_lookup._graph_get", fake_graph_get)

    chats = list_service_user_chats(SimpleNamespace(), organization_id="org-id")

    assert chats == [DelegatedGraphChat(id="chat-1", display_name="Ada Admin", subtitle="1:1 chat - ada@example.com")]


def test_list_service_user_chats_uses_group_members_when_topic_is_empty(monkeypatch: pytest.MonkeyPatch):
    def fake_refresh(db, *, organization_id: str, settings):
        return SimpleNamespace(
            access_token="delegated-token",
            diagnostics=SimpleNamespace(service_user_id="service-user-id", service_user_principal_name="service@example.com"),
        )

    def fake_graph_get(path: str, access_token: str, params: dict[str, str]):
        return {
            "value": [
                {
                    "id": "chat-1",
                    "topic": "",
                    "chatType": "group",
                    "members": [
                        {"userId": "service-user-id", "displayName": "Relay User", "email": "service@example.com"},
                        {"userId": "user-1", "displayName": "Ada Admin", "email": "ada@example.com"},
                        {"userId": "user-2", "displayName": "Grace Ops", "email": "grace@example.com"},
                        {"userId": "user-3", "displayName": "Linus Lead", "email": "linus@example.com"},
                        {"userId": "user-4", "displayName": "Katherine Key", "email": "katherine@example.com"},
                    ],
                }
            ]
        }

    monkeypatch.setattr("app.services.graph_delegated_lookup.refresh_delegated_access_token", fake_refresh)
    monkeypatch.setattr("app.services.graph_delegated_lookup._graph_get", fake_graph_get)

    chats = list_service_user_chats(SimpleNamespace(), organization_id="org-id")

    assert chats == [
        DelegatedGraphChat(
            id="chat-1",
            display_name="Ada Admin, Grace Ops, Linus Lead + 1",
            subtitle="Group chat - 5 members",
        )
    ]


def test_list_service_user_chats_query_matches_member_fields(monkeypatch: pytest.MonkeyPatch):
    def fake_refresh(db, *, organization_id: str, settings):
        return SimpleNamespace(
            access_token="delegated-token",
            diagnostics=SimpleNamespace(service_user_id="service-user-id", service_user_principal_name="service@example.com"),
        )

    def fake_graph_get(path: str, access_token: str, params: dict[str, str]):
        return {
            "value": [
                {
                    "id": "chat-1",
                    "topic": "",
                    "chatType": "oneOnOne",
                    "members": [
                        {"userId": "service-user-id", "displayName": "Relay User", "email": "service@example.com"},
                        {"userId": "target-user-id", "displayName": "Ada Admin", "email": "ada@example.com"},
                    ],
                }
            ]
        }

    monkeypatch.setattr("app.services.graph_delegated_lookup.refresh_delegated_access_token", fake_refresh)
    monkeypatch.setattr("app.services.graph_delegated_lookup._graph_get", fake_graph_get)

    chats = list_service_user_chats(SimpleNamespace(), organization_id="org-id", query="ada@example.com")

    assert chats == [DelegatedGraphChat(id="chat-1", display_name="Ada Admin", subtitle="1:1 chat - ada@example.com")]


def test_list_service_user_chats_retries_without_members_when_graph_rejects_expand(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, str]] = []

    def fake_refresh(db, *, organization_id: str, settings):
        return SimpleNamespace(
            access_token="delegated-token",
            diagnostics=SimpleNamespace(service_user_id="service-user-id", service_user_principal_name="service@example.com"),
        )

    def fake_graph_get(path: str, access_token: str, params: dict[str, str]):
        calls.append(params)
        if "$expand" in params:
            raise GraphDelegatedLookupError(
                "Microsoft Graph chat lookup failed with HTTP 403: Forbidden: members are not available.",
                status_code=403,
            )
        return {"value": [{"id": "chat-1", "topic": "", "chatType": "oneOnOne"}]}

    monkeypatch.setattr("app.services.graph_delegated_lookup.refresh_delegated_access_token", fake_refresh)
    monkeypatch.setattr("app.services.graph_delegated_lookup._graph_get", fake_graph_get)

    chats = list_service_user_chats(SimpleNamespace(), organization_id="org-id")

    assert chats == [DelegatedGraphChat(id="chat-1", display_name="1:1 chat", subtitle="oneOnOne")]
    assert calls == [
        {
            "$top": "25",
            "$select": "id,topic,chatType",
            "$expand": "members",
            "$orderby": CHAT_LIST_ORDER_BY,
        },
        {
            "$top": "25",
            "$select": "id,topic,chatType",
            "$orderby": CHAT_LIST_ORDER_BY,
        },
    ]


def test_list_service_user_chats_does_not_retry_unrelated_graph_errors(monkeypatch: pytest.MonkeyPatch):
    calls = 0

    def fake_refresh(db, *, organization_id: str, settings):
        return SimpleNamespace(
            access_token="delegated-token",
            diagnostics=SimpleNamespace(service_user_id="service-user-id", service_user_principal_name="service@example.com"),
        )

    def fake_graph_get(path: str, access_token: str, params: dict[str, str]):
        nonlocal calls
        calls += 1
        raise GraphDelegatedLookupError("Microsoft Graph chat lookup failed with HTTP 403: Forbidden", status_code=403)

    monkeypatch.setattr("app.services.graph_delegated_lookup.refresh_delegated_access_token", fake_refresh)
    monkeypatch.setattr("app.services.graph_delegated_lookup._graph_get", fake_graph_get)

    with pytest.raises(GraphDelegatedLookupError, match="HTTP 403"):
        list_service_user_chats(SimpleNamespace(), organization_id="org-id")

    assert calls == 1


def test_create_or_get_one_on_one_chat_posts_service_user_and_target(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, str, dict]] = []

    def fake_refresh(db, *, organization_id: str, settings):
        assert organization_id == "org-id"
        return SimpleNamespace(
            access_token="delegated-token",
            diagnostics=SimpleNamespace(service_user_id="service-user-id", service_user_principal_name="service@example.com"),
        )

    def fake_graph_post(path: str, access_token: str, payload: dict):
        calls.append((path, access_token, payload))
        return {"status_code": 201, "body": {"id": "chat-id"}}

    monkeypatch.setattr("app.services.graph_delegated_lookup.refresh_delegated_access_token", fake_refresh)
    monkeypatch.setattr("app.services.graph_delegated_lookup._graph_post_json", fake_graph_post)

    chat = create_or_get_one_on_one_chat(
        SimpleNamespace(),
        organization_id="org-id",
        user_id="target-user-id",
        user_display_name="Ada Admin",
        user_principal_name="ada@example.com",
    )

    assert chat == DelegatedGraphOneOnOneChat(
        id="chat-id",
        user_id="target-user-id",
        user_display_name="Ada Admin",
        user_principal_name="ada@example.com",
    )
    assert calls == [
        (
            "/chats",
            "delegated-token",
            {
                "chatType": "oneOnOne",
                "members": [
                    {
                        "@odata.type": "#microsoft.graph.aadUserConversationMember",
                        "roles": ["owner"],
                        "user@odata.bind": "https://graph.microsoft.com/v1.0/users('service-user-id')",
                    },
                    {
                        "@odata.type": "#microsoft.graph.aadUserConversationMember",
                        "roles": ["owner"],
                        "user@odata.bind": "https://graph.microsoft.com/v1.0/users('target-user-id')",
                    },
                ],
            },
        )
    ]


def test_create_or_get_one_on_one_chat_rejects_existing_chat_id(monkeypatch: pytest.MonkeyPatch):
    def fail_refresh(*args, **kwargs):
        raise AssertionError("delegated token should not be refreshed for invalid input")

    monkeypatch.setattr("app.services.graph_delegated_lookup.refresh_delegated_access_token", fail_refresh)

    with pytest.raises(GraphDelegatedLookupError, match="not an existing Teams chat ID"):
        create_or_get_one_on_one_chat(SimpleNamespace(), organization_id="org-id", user_id="19:001dc@example-thread.v2")


def test_create_or_get_one_on_one_chat_reports_missing_chat_id(monkeypatch: pytest.MonkeyPatch):
    def fake_refresh(db, *, organization_id: str, settings):
        return SimpleNamespace(
            access_token="delegated-token",
            diagnostics=SimpleNamespace(service_user_id="service-user-id", service_user_principal_name="service@example.com"),
        )

    monkeypatch.setattr("app.services.graph_delegated_lookup.refresh_delegated_access_token", fake_refresh)
    monkeypatch.setattr(
        "app.services.graph_delegated_lookup._graph_post_json",
        lambda path, access_token, payload: {"status_code": 201, "body": {}},
    )

    with pytest.raises(GraphDelegatedLookupError, match="chat ID"):
        create_or_get_one_on_one_chat(SimpleNamespace(), organization_id="org-id", user_id="target-user-id")
