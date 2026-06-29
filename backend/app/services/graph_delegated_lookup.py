from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.settings_overrides import get_effective_settings
from app.services.bot_conversation_members import BotConversationMember, BotConversationMembersResult, summarize_members
from app.services.graph_delegated_auth import GraphDelegatedAuthError, refresh_delegated_access_token


class GraphDelegatedLookupError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class DelegatedGraphChat:
    id: str
    display_name: str
    subtitle: str = ""


@dataclass(frozen=True)
class DelegatedGraphChatMember:
    user_id: str = ""
    display_name: str = ""
    email: str = ""


@dataclass(frozen=True)
class DelegatedGraphOneOnOneChat:
    id: str
    user_id: str
    user_display_name: str = ""
    user_principal_name: str = ""


CHAT_LIST_ORDER_BY = "lastMessagePreview/createdDateTime desc"


def list_service_user_chats(
    db: Session,
    *,
    organization_id: str,
    query: str = "",
    limit: int = 25,
    settings: Settings | None = None,
) -> list[DelegatedGraphChat]:
    settings = settings or get_effective_settings()
    try:
        token = refresh_delegated_access_token(db, organization_id=organization_id, settings=settings)
    except GraphDelegatedAuthError as exc:
        raise GraphDelegatedLookupError("Delegated Graph delivery is not connected or the service-user token cannot be refreshed.") from exc

    normalized_limit = max(1, min(limit, 50))
    data = _list_chats_with_fallbacks(token.access_token, normalized_limit)
    service_user_id = _diagnostic_value(token, "service_user_id")
    service_user_principal_name = _diagnostic_value(token, "service_user_principal_name")
    if not service_user_id:
        try:
            service_user_id = _current_user_id(token.access_token)
        except GraphDelegatedLookupError:
            service_user_id = ""

    needle = query.strip().lower()
    chats: list[DelegatedGraphChat] = []
    for chat in data.get("value", []):
        if not isinstance(chat, dict):
            continue
        chat_id = str(chat.get("id") or "").strip()
        chat_type = str(chat.get("chatType") or "").strip()
        topic = str(chat.get("topic") or "").strip()
        if not chat_id:
            continue
        members = _chat_members(chat)
        display_name, subtitle = _chat_display(
            chat_type=chat_type,
            topic=topic,
            members=members,
            service_user_id=service_user_id,
            service_user_principal_name=service_user_principal_name,
        )
        haystack = " ".join(
            [
                chat_id,
                topic,
                chat_type,
                display_name,
                subtitle,
                *_member_search_terms(members),
            ]
        ).lower()
        if needle and needle not in haystack:
            continue
        chats.append(DelegatedGraphChat(id=chat_id, display_name=display_name, subtitle=subtitle))
        if len(chats) >= normalized_limit:
            break
    return chats


def create_or_get_one_on_one_chat(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    user_display_name: str = "",
    user_principal_name: str = "",
    settings: Settings | None = None,
) -> DelegatedGraphOneOnOneChat:
    user_id = user_id.strip()
    if not user_id:
        raise GraphDelegatedLookupError("A Microsoft Graph user ID or user principal name is required.")
    if _looks_like_graph_chat_id(user_id):
        raise GraphDelegatedLookupError("A one-on-one route requires a Microsoft 365 user ID or UPN, not an existing Teams chat ID.")
    settings = settings or get_effective_settings()
    try:
        token = refresh_delegated_access_token(db, organization_id=organization_id, settings=settings)
    except GraphDelegatedAuthError as exc:
        raise GraphDelegatedLookupError("Delegated Graph delivery is not connected or the service-user token cannot be refreshed.") from exc

    service_user_id = _diagnostic_value(token, "service_user_id")
    if not service_user_id:
        service_user_id = _current_user_id(token.access_token)
    if service_user_id and service_user_id.lower() == user_id.lower():
        raise GraphDelegatedLookupError("The Graph route target cannot be the connected service user.")

    payload = _one_on_one_chat_payload(service_user_id or _diagnostic_value(token, "service_user_principal_name"), user_id)
    response = _graph_post_json("/chats", token.access_token, payload)
    body = response.get("body") if isinstance(response, dict) else {}
    chat_id = str(body.get("id") or "").strip() if isinstance(body, dict) else ""
    if not chat_id:
        raise GraphDelegatedLookupError("Microsoft Graph did not return a chat ID for the one-on-one chat.")
    return DelegatedGraphOneOnOneChat(
        id=chat_id,
        user_id=user_id,
        user_display_name=user_display_name.strip(),
        user_principal_name=user_principal_name.strip(),
    )


def fetch_service_user_chat_members(
    db: Session,
    *,
    organization_id: str,
    chat_id: str,
    settings: Settings | None = None,
) -> BotConversationMembersResult:
    chat_id = chat_id.strip()
    if not chat_id:
        raise GraphDelegatedLookupError("A Microsoft Graph chat ID is required.")
    settings = settings or get_effective_settings()
    try:
        token = refresh_delegated_access_token(db, organization_id=organization_id, settings=settings)
    except GraphDelegatedAuthError as exc:
        raise GraphDelegatedLookupError("Delegated Graph delivery is not connected or the service-user token cannot be refreshed.") from exc
    data = _graph_get(f"/chats/{urllib.parse.quote(chat_id, safe='')}/members", token.access_token, {})
    raw_members = data.get("value")
    if not isinstance(raw_members, list):
        raise GraphDelegatedLookupError("Microsoft Graph chat members response was invalid.")
    members = [_bot_member_from_graph_member(member) for member in raw_members if isinstance(member, dict)]
    members = [member for member in members if member.id or member.name or member.email or member.user_principal_name]
    return BotConversationMembersResult(
        members=members,
        member_summary=summarize_members(members),
        member_count=len(members),
    )


def _list_chats_with_fallbacks(access_token: str, limit: int) -> dict:
    include_ordering = True
    include_members = True
    attempted: set[tuple[bool, bool]] = set()
    last_error: GraphDelegatedLookupError | None = None
    while (include_ordering, include_members) not in attempted:
        attempted.add((include_ordering, include_members))
        try:
            return _graph_get(
                "/me/chats",
                access_token,
                _chat_list_params(limit, include_ordering=include_ordering, include_members=include_members),
            )
        except GraphDelegatedLookupError as exc:
            last_error = exc
            if include_ordering and _is_orderby_rejection(exc):
                include_ordering = False
                continue
            if include_members and _is_member_expand_rejection(exc):
                include_members = False
                continue
            raise
    if last_error:
        raise last_error
    return {}


def _chat_list_params(limit: int, *, include_ordering: bool, include_members: bool) -> dict[str, str]:
    params = {
        "$top": str(limit),
        "$select": "id,topic,chatType",
    }
    if include_members:
        params["$expand"] = "members"
    if include_ordering:
        params["$orderby"] = CHAT_LIST_ORDER_BY
    return params


def _diagnostic_value(token, field: str) -> str:
    diagnostics = getattr(token, "diagnostics", None)
    return str(getattr(diagnostics, field, "") or "").strip()


def _current_user_id(access_token: str) -> str:
    data = _graph_get("/me", access_token, {"$select": "id"})
    return str(data.get("id") or "").strip()


def _one_on_one_chat_payload(service_user_id: str, target_user_id: str) -> dict:
    service_user_id = service_user_id.strip()
    target_user_id = target_user_id.strip()
    if not service_user_id:
        raise GraphDelegatedLookupError("Delegated Graph service-user metadata is incomplete. Reconnect the service user.")
    return {
        "chatType": "oneOnOne",
        "members": [
            _conversation_member(service_user_id),
            _conversation_member(target_user_id),
        ],
    }


def _conversation_member(user_id: str) -> dict:
    return {
        "@odata.type": "#microsoft.graph.aadUserConversationMember",
        "roles": ["owner"],
        "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{_odata_string(user_id)}')",
    }


def _looks_like_graph_chat_id(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("19:") or "@thread." in normalized


def _graph_get(path: str, access_token: str, params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode(params)
    separator = "?" if query else ""
    request = urllib.request.Request(
        f"https://graph.microsoft.com/v1.0{path}{separator}{query}",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
            return body if isinstance(body, dict) else {}
    except urllib.error.HTTPError as exc:
        safe_message = _safe_error_message(exc)
        raise GraphDelegatedLookupError(
            f"Microsoft Graph chat lookup failed with HTTP {exc.code}: {safe_message}",
            status_code=exc.code,
        ) from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GraphDelegatedLookupError("Microsoft Graph chat lookup failed.") from exc


def _graph_post_json(path: str, access_token: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"https://graph.microsoft.com/v1.0{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response_body = response.read().decode("utf-8")
            body = json.loads(response_body) if response_body else {}
            return {"status_code": response.status, "body": body if isinstance(body, dict) else {}}
    except urllib.error.HTTPError as exc:
        safe_message = _safe_error_message(exc)
        raise GraphDelegatedLookupError(
            f"Microsoft Graph one-on-one chat creation failed with HTTP {exc.code}: {safe_message}",
            status_code=exc.code,
        ) from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GraphDelegatedLookupError("Microsoft Graph one-on-one chat creation failed.") from exc


def _is_orderby_rejection(exc: GraphDelegatedLookupError) -> bool:
    if exc.status_code != 400:
        return False
    message = str(exc).lower()
    return "order by" in message or "orderby" in message


def _is_member_expand_rejection(exc: GraphDelegatedLookupError) -> bool:
    if exc.status_code not in {400, 403}:
        return False
    message = str(exc).lower()
    return "expand" in message or "member" in message


def _chat_members(chat: dict) -> list[DelegatedGraphChatMember]:
    raw_members = chat.get("members")
    if not isinstance(raw_members, list):
        return []
    members: list[DelegatedGraphChatMember] = []
    for raw_member in raw_members:
        if not isinstance(raw_member, dict):
            continue
        member = DelegatedGraphChatMember(
            user_id=str(raw_member.get("userId") or "").strip(),
            display_name=str(raw_member.get("displayName") or "").strip(),
            email=str(raw_member.get("email") or raw_member.get("userPrincipalName") or "").strip(),
        )
        if member.user_id or member.display_name or member.email:
            members.append(member)
    return members


def _bot_member_from_graph_member(raw_member: dict) -> BotConversationMember:
    return BotConversationMember(
        id=str(raw_member.get("id") or raw_member.get("userId") or "").strip(),
        name=str(raw_member.get("displayName") or "").strip(),
        aad_object_id=str(raw_member.get("userId") or "").strip(),
        email=str(raw_member.get("email") or "").strip(),
        user_principal_name=str(raw_member.get("userPrincipalName") or raw_member.get("email") or "").strip(),
    )


def _chat_display(
    *,
    chat_type: str,
    topic: str,
    members: list[DelegatedGraphChatMember],
    service_user_id: str,
    service_user_principal_name: str,
) -> tuple[str, str]:
    if chat_type == "oneOnOne":
        other_member = _other_one_on_one_member(members, service_user_id, service_user_principal_name)
        if other_member:
            subtitle = "1:1 chat"
            if other_member.email:
                subtitle = f"{subtitle} - {other_member.email}"
            return _member_label(other_member), subtitle
    if chat_type == "group" and not topic:
        summary = _member_summary(members, service_user_id, service_user_principal_name)
        if summary:
            return summary, _chat_subtitle(chat_type, members)
    return topic or _chat_type_label(chat_type), _chat_subtitle(chat_type, members)


def _chat_subtitle(chat_type: str, members: list[DelegatedGraphChatMember]) -> str:
    label = _chat_type_label(chat_type) if chat_type in {"group", "meeting", "oneOnOne"} else chat_type or "chat"
    if not members:
        return chat_type or "chat"
    member_label = "member" if len(members) == 1 else "members"
    return f"{label} - {len(members)} {member_label}"


def _other_one_on_one_member(
    members: list[DelegatedGraphChatMember],
    service_user_id: str,
    service_user_principal_name: str,
) -> DelegatedGraphChatMember | None:
    for member in members:
        if not _is_service_user_member(member, service_user_id, service_user_principal_name):
            return member
    return members[0] if len(members) == 1 else None


def _member_summary(
    members: list[DelegatedGraphChatMember],
    service_user_id: str,
    service_user_principal_name: str,
) -> str:
    display_members = [
        member for member in members if not _is_service_user_member(member, service_user_id, service_user_principal_name)
    ] or members
    labels = [_member_label(member) for member in display_members]
    labels = [label for label in labels if label]
    if not labels:
        return ""
    visible = labels[:3]
    hidden_count = len(labels) - len(visible)
    suffix = f" + {hidden_count}" if hidden_count > 0 else ""
    return f"{', '.join(visible)}{suffix}"


def _is_service_user_member(member: DelegatedGraphChatMember, service_user_id: str, service_user_principal_name: str) -> bool:
    service_user_id = service_user_id.lower()
    service_user_principal_name = service_user_principal_name.lower()
    return bool(
        (service_user_id and member.user_id.lower() == service_user_id)
        or (service_user_principal_name and member.email.lower() == service_user_principal_name)
    )


def _member_label(member: DelegatedGraphChatMember) -> str:
    return member.display_name or member.email or _short_id(member.user_id)


def _member_search_terms(members: list[DelegatedGraphChatMember]) -> list[str]:
    terms: list[str] = []
    for member in members:
        terms.extend([member.user_id, member.display_name, member.email])
    return terms


def _short_id(value: str) -> str:
    value = value.strip()
    return f"{value[:8]}..." if len(value) > 11 else value


def _chat_type_label(chat_type: str) -> str:
    if chat_type == "oneOnOne":
        return "1:1 chat"
    if chat_type == "meeting":
        return "Meeting chat"
    return "Group chat"


def _odata_string(value: str) -> str:
    return value.replace("'", "''")


def _safe_error_message(exc: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(exc.read().decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "The Graph response could not be parsed."
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        message = str(error.get("message") or "Microsoft Graph returned an error.").strip()
        code = str(error.get("code") or "").strip()
        return f"{code}: {message}" if code else message
    return "Microsoft Graph returned an error."
