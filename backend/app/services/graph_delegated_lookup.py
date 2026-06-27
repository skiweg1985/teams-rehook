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
    pass


@dataclass(frozen=True)
class DelegatedGraphChat:
    id: str
    display_name: str
    subtitle: str = ""


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

    data = _graph_get(
        "/me/chats",
        token.access_token,
        {
            "$top": str(max(1, min(limit, 50))),
            "$select": "id,topic,chatType,lastUpdatedDateTime",
            "$orderby": "lastUpdatedDateTime desc",
        },
    )
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
        if len(chats) >= limit:
            break
    return chats


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
        raise GraphDelegatedLookupError(f"Microsoft Graph chat lookup failed with HTTP {exc.code}: {safe_message}") from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GraphDelegatedLookupError("Microsoft Graph chat lookup failed.") from exc


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
