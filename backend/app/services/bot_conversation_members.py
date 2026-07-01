from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.settings_overrides import get_effective_settings
from app.services.teams_bot import BotTokenManager, get_token_manager


class BotConversationMembersError(RuntimeError):
    pass


@dataclass(frozen=True)
class BotConversationMember:
    id: str = ""
    name: str = ""
    aad_object_id: str = ""
    email: str = ""
    user_principal_name: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "aad_object_id": self.aad_object_id,
            "email": self.email,
            "user_principal_name": self.user_principal_name,
        }


@dataclass(frozen=True)
class BotConversationMembersResult:
    members: list[BotConversationMember]
    member_summary: str
    member_count: int


def fetch_bot_conversation_members(
    *,
    service_url: str,
    conversation_id: str,
    settings: Settings | None = None,
    token_manager: BotTokenManager | None = None,
) -> BotConversationMembersResult:
    settings = settings or get_effective_settings()
    _ = settings
    service_url = service_url.strip().rstrip("/")
    conversation_id = conversation_id.strip()
    if not service_url or not conversation_id:
        raise BotConversationMembersError("Bot service URL and conversation ID are required for member lookup")

    token = (token_manager or get_token_manager()).get_token()
    encoded_conversation_id = urllib.parse.quote(conversation_id, safe="")
    url = f"{service_url}/v3/conversations/{encoded_conversation_id}/members"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8") or "[]")
    except urllib.error.HTTPError as exc:
        safe_body = exc.read().decode("utf-8", errors="replace")[:300]
        raise BotConversationMembersError(f"Bot Framework member lookup failed with HTTP {exc.code}: {safe_body}") from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise BotConversationMembersError("Bot Framework member lookup failed") from exc
    if not isinstance(body, list):
        raise BotConversationMembersError("Bot Framework member lookup returned an invalid response")

    members = [_member_from_raw(item) for item in body if isinstance(item, dict)]
    members = [member for member in members if member.id or member.name or member.email or member.user_principal_name]
    return BotConversationMembersResult(
        members=members,
        member_summary=summarize_members(members),
        member_count=len(members),
    )


def summarize_members(members: list[BotConversationMember], *, visible_count: int = 3) -> str:
    labels: list[str] = []
    seen: set[str] = set()
    for member in members:
        label = _member_label(member)
        if not label:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)
    if not labels:
        return ""
    visible = labels[: max(1, visible_count)]
    remaining = len(labels) - len(visible)
    summary = ", ".join(visible)
    if remaining > 0:
        summary = f"{summary} + {remaining}"
    return summary[:500]


def serialize_members(members: list[BotConversationMember]) -> str:
    return json.dumps([member.to_dict() for member in members[:50]], ensure_ascii=False)


def _member_from_raw(raw: dict[str, Any]) -> BotConversationMember:
    return BotConversationMember(
        id=_string(raw.get("id")),
        name=_string(raw.get("name")),
        aad_object_id=_string(raw.get("aadObjectId")) or _string(raw.get("objectId")),
        email=_string(raw.get("email")),
        user_principal_name=_string(raw.get("userPrincipalName")),
    )


def _member_label(member: BotConversationMember) -> str:
    return member.name or member.user_principal_name or member.email or member.id


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
