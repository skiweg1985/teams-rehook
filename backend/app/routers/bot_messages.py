from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import get_db
from app.deps import require_admin
from app.models import BotActivityEvent, BotConversationReference, Organization, User, WebhookRoute
from app.schemas import BotActivityIngestOut, BotConversationReferenceOut
from app.security import dumps_json, issue_plain_secret, lookup_secret_hash, utcnow
from app.services.teams_bot import BotDeliveryError, send_bot_activity
from app.services.webhook_payloads import NormalizedMessage

router = APIRouter(tags=["bot-messages"])


@router.post("/bot/messages", response_model=BotActivityIngestOut)
async def receive_bot_activity(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if not body:
        return BotActivityIngestOut(activity_event_id="", captured_reference=False)
    try:
        activity = json.loads(body)
    except json.JSONDecodeError:
        return BotActivityIngestOut(activity_event_id="", captured_reference=False)
    if not isinstance(activity, dict):
        return BotActivityIngestOut(activity_event_id="", captured_reference=False)
    captured = _extract_activity(activity)
    event = BotActivityEvent(
        activity_type=captured["activity_type"],
        service_url=captured["service_url"],
        conversation_id=captured["conversation_id"],
        tenant_id=captured["tenant_id"],
        team_id=captured["team_id"],
        graph_team_id=captured["graph_team_id"],
        channel_id=captured["channel_id"],
        conversation_type=captured["conversation_type"],
        team_name=captured["team_name"],
        channel_name=captured["channel_name"],
        from_id=captured["from_id"],
        user_name=captured["user_name"],
        graph_user_id=captured["graph_user_id"],
        recipient_id=captured["recipient_id"],
        raw_activity_json=dumps_json(_safe_activity(activity)),
    )
    db.add(event)
    db.flush()
    reference = _upsert_reference(db, captured)
    command_result = _handle_command(db, activity, captured, reference)
    db.commit()
    reply_sent = False
    reply_error = ""
    if command_result.reply_text and captured["service_url"] and captured["conversation_id"]:
        try:
            send_bot_activity(
                service_url=captured["service_url"],
                conversation_id=captured["conversation_id"],
                message=NormalizedMessage(
                    title=command_result.title,
                    text=command_result.reply_text,
                    severity=command_result.severity,
                    source="teams-relay-bot",
                    raw_type="bot-command-reply",
                ),
            )
            reply_sent = True
        except BotDeliveryError as exc:
            reply_error = str(exc)
    return BotActivityIngestOut(
        activity_event_id=event.id,
        conversation_reference_id=reference.id if reference else None,
        captured_reference=reference is not None,
        handled_command=command_result.handled,
        command=command_result.command,
        reply_sent=reply_sent,
        reply_error=reply_error,
        reply_text=command_result.reply_text,
    )


@router.get("/bot/conversation-references", response_model=list[BotConversationReferenceOut])
def list_bot_conversation_references(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = admin
    references = db.scalars(
        select(BotConversationReference).order_by(BotConversationReference.last_seen_at.desc()).limit(100)
    ).all()
    return references


@dataclass(frozen=True)
class CommandResult:
    handled: bool = False
    command: str | None = None
    reply_text: str | None = None
    title: str = "Teams Relay"
    severity: str = "info"


def _upsert_reference(db: Session, captured: dict[str, str]) -> BotConversationReference | None:
    if not captured["conversation_id"] or not captured["service_url"]:
        return None
    reference = db.scalar(
        select(BotConversationReference).where(BotConversationReference.conversation_id == captured["conversation_id"])
    )
    if reference is None:
        reference = BotConversationReference(conversation_id=captured["conversation_id"])
        db.add(reference)
    now = utcnow()
    reference.scope = _scope_for(captured)
    reference.service_url = captured["service_url"]
    reference.tenant_id = captured["tenant_id"]
    reference.team_id = captured["team_id"]
    reference.graph_team_id = captured["graph_team_id"] or reference.graph_team_id
    reference.channel_id = captured["channel_id"]
    reference.conversation_type = captured["conversation_type"]
    reference.team_name = captured["team_name"] or reference.team_name
    reference.channel_name = captured["channel_name"] or reference.channel_name
    reference.user_id = captured["from_id"]
    reference.user_name = captured["user_name"] or reference.user_name
    reference.graph_user_id = captured["graph_user_id"] or reference.graph_user_id
    reference.raw_activity_type = captured["activity_type"]
    reference.last_seen_at = now
    reference.updated_at = now
    db.flush()
    return reference


def _scope_for(captured: dict[str, str]) -> str:
    if captured["conversation_type"] == "personal":
        return "user"
    if captured["team_id"] and captured["channel_id"]:
        return "channel"
    if captured["team_id"]:
        return "team"
    return "user"


def _extract_activity(activity: dict[str, Any]) -> dict[str, str]:
    channel_data = _dict(activity.get("channelData"))
    conversation = _dict(activity.get("conversation"))
    sender = _dict(activity.get("from"))
    recipient = _dict(activity.get("recipient"))
    tenant = _dict(channel_data.get("tenant"))
    team = _dict(channel_data.get("team"))
    channel = _dict(channel_data.get("channel"))
    settings = _dict(channel_data.get("settings"))
    selected_channel = _dict(settings.get("selectedChannel"))
    conversation_id = _normalize_conversation_id(_string(conversation.get("id")))
    conversation_type = _string(conversation.get("conversationType")).lower()
    channel_id = (
        _string(channel.get("id"))
        or _string(channel_data.get("teamsChannelId"))
        or _string(selected_channel.get("id"))
        or (conversation_id if conversation_type == "channel" else "")
    )
    return {
        "activity_type": _string(activity.get("type")),
        "service_url": _string(activity.get("serviceUrl")),
        "conversation_id": conversation_id,
        "raw_conversation_id": _string(conversation.get("id")),
        "tenant_id": _string(tenant.get("id")) or _string(conversation.get("tenantId")),
        "team_id": _string(team.get("id")) or _string(channel_data.get("teamsTeamId")),
        "graph_team_id": _string(team.get("aadGroupId")),
        "channel_id": channel_id,
        "conversation_type": _clip(conversation_type, 40),
        "team_name": _clip(_string(team.get("name")), 200),
        "channel_name": _clip(
            _string(channel.get("name")) or _string(selected_channel.get("name")) or _string(conversation.get("name")),
            200,
        ),
        "from_id": _string(sender.get("id")),
        "user_name": _clip(_string(sender.get("name")), 200),
        "graph_user_id": _string(sender.get("aadObjectId")),
        "recipient_id": _string(recipient.get("id")),
    }


def _handle_command(
    db: Session,
    activity: dict[str, Any],
    captured: dict[str, str],
    reference: BotConversationReference | None,
) -> CommandResult:
    if captured["activity_type"] != "message":
        return CommandResult()
    parsed = _parse_command(_string(activity.get("text")))
    if not parsed:
        return CommandResult()
    command, argument = parsed
    if command == "register":
        return _register_route_from_command(db, captured, argument, reference)
    if command == "webhook":
        return _webhook_url_command(db, argument)
    if command == "info":
        return _info_command(db, captured, reference)
    return CommandResult(
        handled=True,
        command=command,
        reply_text="Unknown command. Available commands: `/register <route name>`, `/webhook <route name>`, `/info`.",
        severity="warn",
    )


def _parse_command(text: str) -> tuple[str, str] | None:
    cleaned = unescape(re.sub(r"<at>.*?</at>", "", text, flags=re.IGNORECASE | re.DOTALL)).strip()
    if not cleaned.startswith("/"):
        return None
    match = re.match(r"^/([A-Za-z][A-Za-z0-9_-]*)(?:\s+(.+))?$", cleaned, flags=re.DOTALL)
    if not match:
        return ("invalid", "")
    return match.group(1).lower(), " ".join((match.group(2) or "").strip().split())


def _register_route_from_command(
    db: Session,
    captured: dict[str, str],
    route_name: str,
    reference: BotConversationReference | None,
) -> CommandResult:
    if not route_name:
        return CommandResult(
            handled=True,
            command="register",
            reply_text="Please include a route name, for example `/register Jira Alerts`.",
            severity="warn",
        )
    if len(route_name) > 200:
        return CommandResult(
            handled=True,
            command="register",
            reply_text="Route names are limited to 200 characters. Please choose a shorter name.",
            severity="warn",
        )
    if not captured["service_url"] or not captured["conversation_id"] or reference is None:
        return CommandResult(
            handled=True,
            command="register",
            reply_text="I could not capture a complete Bot Framework conversation reference yet. Please send the command again from Teams.",
            severity="warn",
        )
    organization = _default_organization(db)
    effective = _captured_with_reference(captured, reference)
    route = db.scalar(
        select(WebhookRoute).where(
            WebhookRoute.organization_id == organization.id,
            WebhookRoute.name == route_name,
        )
    )
    created = route is None
    route_token = ""
    if route is None:
        route_token = issue_plain_secret(24)
        route = WebhookRoute(
            organization_id=organization.id,
            created_by_id=None,
            name=route_name,
            source_system="teams-command",
            route_token_hash=lookup_secret_hash(route_token),
            route_token=route_token,
            target_type="bot_conversation",
            target_name=_target_name(effective),
        )
        db.add(route)
    route.is_active = True
    route.bot_service_url = effective["service_url"]
    route.bot_conversation_id = effective["conversation_id"]
    route.target_name = _target_name(effective)
    route.graph_target_kind = _graph_target_kind(effective)
    route.graph_target_id = _graph_target_id(effective)
    route.graph_team_id = effective["graph_team_id"]
    route.graph_team_name = _clip(effective["team_name"], 200)
    route.graph_channel_id = effective["channel_id"] if route.graph_target_kind == "channel" else ""
    route.bot_target_source = "bot_command"
    route.bot_registered_by_id = effective["graph_user_id"] or effective["from_id"]
    route.bot_registered_at = utcnow()
    db.flush()
    webhook_url = _build_webhook_url(route.route_token)
    verb = "created" if created else "updated"
    return CommandResult(
        handled=True,
        command="register",
        reply_text=(
            f"Route `{route.name}` {verb} for this conversation.\n\n"
            f"Webhook URL:\n{webhook_url}\n\n"
            "Use `/info` to inspect the captured Teams IDs."
        ),
    )


def _webhook_url_command(db: Session, route_name: str) -> CommandResult:
    if not route_name:
        return CommandResult(
            handled=True,
            command="webhook",
            reply_text="Please include a route name, for example `/webhook Jira Alerts`.",
            severity="warn",
        )
    if len(route_name) > 200:
        return CommandResult(
            handled=True,
            command="webhook",
            reply_text="Route names are limited to 200 characters. Please choose a shorter name.",
            severity="warn",
        )
    organization = _default_organization(db)
    route = db.scalar(
        select(WebhookRoute).where(
            WebhookRoute.organization_id == organization.id,
            WebhookRoute.name == route_name,
        )
    )
    if route is None or not route.route_token:
        return CommandResult(
            handled=True,
            command="webhook",
            reply_text=f"No route named `{route_name}` exists yet. Use `/register {route_name}` from the target conversation first.",
            severity="warn",
        )
    return CommandResult(
        handled=True,
        command="webhook",
        reply_text=f"Webhook URL for `{route.name}`:\n{_build_webhook_url(route.route_token)}",
    )


def _info_command(
    db: Session,
    captured: dict[str, str],
    reference: BotConversationReference | None,
) -> CommandResult:
    linked_route = _find_route_for_reference(db, captured)
    lines = [
        f"Scope: `{_scope_for(captured)}`",
        f"Conversation ID: `{captured['conversation_id'] or '-'}`",
        f"Service URL: `{captured['service_url'] or '-'}`",
        f"Tenant ID: `{captured['tenant_id'] or '-'}`",
        f"Teams user ID: `{captured['from_id'] or '-'}`",
        f"User name: `{captured['user_name'] or '-'}`",
        f"AAD user ID: `{captured['graph_user_id'] or '-'}`",
        f"Teams team ID: `{captured['team_id'] or '-'}`",
        f"Graph team ID: `{captured['graph_team_id'] or '-'}`",
        f"Team name: `{captured['team_name'] or '-'}`",
        f"Channel ID: `{captured['channel_id'] or '-'}`",
        f"Channel name: `{captured['channel_name'] or '-'}`",
        f"Reference saved: `{'yes' if reference else 'no'}`",
    ]
    if linked_route and linked_route.route_token:
        lines.append(f"Linked route: `{linked_route.name}`")
        lines.append(f"Webhook URL: {_build_webhook_url(linked_route.route_token)}")
    else:
        lines.append("Linked route: `none`")
    return CommandResult(handled=True, command="info", reply_text="\n".join(lines))


def _find_route_for_reference(db: Session, captured: dict[str, str]) -> WebhookRoute | None:
    organization = _default_organization(db)
    route = db.scalar(
        select(WebhookRoute)
        .where(
            WebhookRoute.organization_id == organization.id,
            WebhookRoute.bot_conversation_id == captured["conversation_id"],
        )
        .order_by(WebhookRoute.updated_at.desc())
    )
    if route is not None:
        return route
    if captured["graph_team_id"] and captured["channel_id"]:
        return db.scalar(
            select(WebhookRoute)
            .where(
                WebhookRoute.organization_id == organization.id,
                WebhookRoute.graph_team_id == captured["graph_team_id"],
                WebhookRoute.graph_channel_id == captured["channel_id"],
            )
            .order_by(WebhookRoute.updated_at.desc())
        )
    return None


def _captured_with_reference(
    captured: dict[str, str],
    reference: BotConversationReference | None,
) -> dict[str, str]:
    if reference is None:
        return captured
    merged = dict(captured)
    reference_values = {
        "service_url": reference.service_url,
        "conversation_id": reference.conversation_id,
        "tenant_id": reference.tenant_id,
        "team_id": reference.team_id,
        "graph_team_id": reference.graph_team_id,
        "channel_id": reference.channel_id,
        "conversation_type": reference.conversation_type,
        "team_name": reference.team_name,
        "channel_name": reference.channel_name,
        "from_id": reference.user_id,
        "user_name": reference.user_name,
        "graph_user_id": reference.graph_user_id,
    }
    for key, value in reference_values.items():
        if value and not merged.get(key):
            merged[key] = value
    return merged


def _default_organization(db: Session) -> Organization:
    settings = get_settings()
    organization = db.scalar(select(Organization).where(Organization.slug == settings.default_org_slug))
    if organization is None:
        organization = Organization(slug=settings.default_org_slug, name=settings.default_org_name)
        db.add(organization)
        db.flush()
    return organization


def _target_name(captured: dict[str, str]) -> str:
    if captured["team_name"] and captured["channel_name"]:
        return _clip(f"{captured['team_name']} / {captured['channel_name']}", 200)
    if captured["channel_name"]:
        return _clip(captured["channel_name"], 200)
    if captured["team_name"]:
        return _clip(captured["team_name"], 200)
    return _clip(
        captured["user_name"] or captured["graph_user_id"] or captured["from_id"] or captured["conversation_id"] or "Teams conversation",
        200,
    )


def _graph_target_kind(captured: dict[str, str]) -> str:
    if captured["channel_id"]:
        return "channel"
    if captured["graph_team_id"]:
        return "team"
    if captured["graph_user_id"] or captured["from_id"]:
        return "user"
    return ""


def _graph_target_id(captured: dict[str, str]) -> str:
    kind = _graph_target_kind(captured)
    if kind == "channel":
        return captured["channel_id"]
    if kind == "team":
        return captured["graph_team_id"]
    if kind == "user":
        return captured["graph_user_id"] or captured["from_id"]
    return ""


def _normalize_conversation_id(value: str) -> str:
    return value.split(";messageid=", 1)[0] if ";messageid=" in value else value


def _clip(value: str, limit: int) -> str:
    return value[:limit]


def _build_webhook_url(route_token: str) -> str:
    settings = get_settings()
    return f"{settings.app_public_base_url.rstrip('/')}{settings.api_v1_prefix.rstrip('/')}/webhooks/{route_token}"


def _safe_activity(activity: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "type",
        "id",
        "timestamp",
        "serviceUrl",
        "channelId",
        "from",
        "conversation",
        "recipient",
        "channelData",
        "membersAdded",
        "membersRemoved",
        "name",
    }
    safe = {key: _truncate(value) for key, value in activity.items() if key in allowed_keys}
    text = activity.get("text")
    if isinstance(text, str) and text:
        safe["text_preview"] = text[:200]
    return safe


def _truncate(value: Any) -> Any:
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, dict):
        return {str(key): _truncate(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_truncate(child) for child in value[:25]]
    if isinstance(value, int | float | bool) or value is None:
        return value
    return str(value)[:2000]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
