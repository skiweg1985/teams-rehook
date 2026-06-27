from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.settings_overrides import get_effective_settings
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
    params = _chat_list_params(normalized_limit, include_ordering=True)
    try:
        data = _graph_get("/me/chats", token.access_token, params)
    except GraphDelegatedLookupError as exc:
        if not _is_orderby_rejection(exc):
            raise
        data = _graph_get("/me/chats", token.access_token, _chat_list_params(normalized_limit, include_ordering=False))

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
        display_name = topic or _chat_type_label(chat_type)
        subtitle = chat_type or "chat"
        haystack = " ".join([chat_id, display_name, subtitle]).lower()
        if needle and needle not in haystack:
            continue
        chats.append(DelegatedGraphChat(id=chat_id, display_name=display_name, subtitle=subtitle))
        if len(chats) >= normalized_limit:
            break
    return chats


def _chat_list_params(limit: int, *, include_ordering: bool) -> dict[str, str]:
    params = {
        "$top": str(limit),
        "$select": "id,topic,chatType",
    }
    if include_ordering:
        params["$orderby"] = CHAT_LIST_ORDER_BY
    return params


def _graph_get(path: str, access_token: str, params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"https://graph.microsoft.com/v1.0{path}?{query}",
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


def _is_orderby_rejection(exc: GraphDelegatedLookupError) -> bool:
    if exc.status_code != 400:
        return False
    message = str(exc).lower()
    return "order by" in message or "orderby" in message


def _chat_type_label(chat_type: str) -> str:
    if chat_type == "oneOnOne":
        return "1:1 chat"
    if chat_type == "meeting":
        return "Meeting chat"
    return "Group chat"


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
