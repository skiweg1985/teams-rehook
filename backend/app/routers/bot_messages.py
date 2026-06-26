from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass
from html import unescape
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import get_db
from app.deps import record_audit, require_admin
from app.models import BotActivityEvent, BotConversationReference, Organization, User, WebhookDeliveryEvent, WebhookRoute
from app.schemas import BotActivityIngestOut, BotConversationReferenceOut
from app.security import dumps_json, issue_plain_secret, lookup_secret_hash, utcnow
from app.services.graph_name_resolution import try_resolve_reference_graph_names, try_resolve_route_graph_names
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
                    activity=command_result.activity,
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
    activity: dict[str, Any] | None = None


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
    try_resolve_reference_graph_names(reference)
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
    if command == "disable":
        return _set_route_active_command(db, captured, argument, is_active=False)
    if command == "enable":
        return _set_route_active_command(db, captured, argument, is_active=True)
    if command == "delete":
        return _delete_linked_route_command(db, captured, argument)
    if command == "info":
        return _info_command(db, captured, reference, argument)
    if command == "help":
        return _help_command()
    return CommandResult(
        handled=True,
        command=command,
        reply_text=(
            "Unknown command. Available commands: `/register <route name>`, `/webhook <route name>`, "
            "`/disable [route name]`, `/enable [route name]`, `/delete <route name>`, `/info [route name]`, `/help`."
        ),
        severity="warn",
        activity=_command_activity(
            "Unknown command",
            (
                "Available commands are /register <route name>, /webhook <route name>, /disable [route name], "
                "/enable [route name], /delete <route name>, /info [route name] and /help."
            ),
        ),
    )


def _parse_command(text: str) -> tuple[str, str] | None:
    cleaned = unescape(re.sub(r"<at>.*?</at>", "", text, flags=re.IGNORECASE | re.DOTALL)).strip()
    if not cleaned.startswith("/"):
        return None
    match = re.match(r"^/([A-Za-z][A-Za-z0-9_-]*)(?:\s+(.+))?$", cleaned, flags=re.DOTALL)
    if not match:
        return ("invalid", "")
    return match.group(1).lower(), " ".join((match.group(2) or "").strip().split())


def _command_activity(
    title: str,
    message: str = "",
    *,
    facts: list[tuple[str, str]] | None = None,
    long_fields: list[tuple[str, str]] | None = None,
    technical_fields: list[tuple[str, str]] | None = None,
    actions: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": title,
            "weight": "Bolder",
            "size": "Medium",
            "wrap": True,
        }
    ]
    if message:
        body.append({"type": "TextBlock", "text": message, "wrap": True, "spacing": "Small"})
    if facts:
        body.append(
            {
                "type": "FactSet",
                "spacing": "Medium",
                "facts": [{"title": f"{label}:", "value": _card_value(value)} for label, value in facts],
            }
        )
    if long_fields:
        body.append({"type": "Container", "spacing": "Medium", "items": _long_field_items(long_fields)})
    card_actions = list(actions or [])
    if technical_fields:
        body.append(
            {
                "type": "Container",
                "id": "technicalDetails",
                "isVisible": False,
                "separator": True,
                "spacing": "Medium",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "Technical details",
                        "weight": "Bolder",
                        "size": "Small",
                        "wrap": True,
                    },
                    *_long_field_items(technical_fields),
                ],
            }
        )
        card_actions.append(
            {
                "type": "Action.ToggleVisibility",
                "title": "Show technical details",
                "targetElements": ["technicalDetails"],
            }
        )
    card: dict[str, Any] = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "msteams": {"width": "Full"},
        "body": body,
    }
    if card_actions:
        card["actions"] = card_actions
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }
        ],
    }


def _long_field_items(fields: list[tuple[str, str]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for label, value in fields:
        items.extend(
            [
                {
                    "type": "TextBlock",
                    "text": label,
                    "weight": "Bolder",
                    "size": "Small",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": _card_value(value),
                    "fontType": "Monospace",
                    "wrap": True,
                    "spacing": "None",
                },
            ]
        )
    return items


def _card_value(value: str) -> str:
    return value.strip() if value.strip() else "-"


def _open_url_action(title: str, url: str) -> dict[str, str]:
    return {"type": "Action.OpenUrl", "title": title, "url": url}


def _copy_webhook_url_action(webhook_url: str) -> dict[str, str]:
    return _open_url_action("Copy webhook URL", _build_webhook_copy_url(webhook_url))


def _technical_fields(captured: dict[str, str]) -> list[tuple[str, str]]:
    return [
        ("Conversation ID", captured["conversation_id"]),
        ("Service URL", captured["service_url"]),
        ("Tenant ID", captured["tenant_id"]),
        ("Teams user ID", captured["from_id"]),
        ("AAD user ID", captured["graph_user_id"]),
        ("Teams team ID", captured["team_id"]),
        ("Graph team ID", captured["graph_team_id"]),
        ("Channel ID", captured["channel_id"]),
    ]


def _route_command_activity(route: WebhookRoute, verb: str, webhook_url: str, captured: dict[str, str]) -> dict[str, Any]:
    target_name = _target_name(captured)
    return _command_activity(
        f"Route {verb}",
        f"{route.name} is ready for this Teams conversation.",
        facts=[
            ("Route", route.name),
            ("Target", target_name),
            ("Scope", _scope_for(captured)),
        ],
        long_fields=[("Webhook URL", webhook_url)],
        technical_fields=_technical_fields(captured),
        actions=[_copy_webhook_url_action(webhook_url)],
    )


def _webhook_command_activity(route: WebhookRoute, webhook_url: str) -> dict[str, Any]:
    return _command_activity(
        "Webhook URL",
        "Use this stable URL for incoming webhook requests.",
        facts=[
            ("Route", route.name),
            ("Target", route.target_name),
            ("Status", "active" if route.is_active else "inactive"),
        ],
        long_fields=[("Webhook URL", webhook_url)],
        actions=[_copy_webhook_url_action(webhook_url)],
    )


def _info_detail_command_activity(
    captured: dict[str, str],
    reference: BotConversationReference | None,
    linked_route: WebhookRoute | None,
) -> dict[str, Any]:
    webhook_url = _build_webhook_url(linked_route.route_token) if linked_route and linked_route.route_token else ""
    long_fields = [("Webhook URL", webhook_url)] if webhook_url else []
    actions = [_copy_webhook_url_action(webhook_url)] if webhook_url else []
    return _command_activity(
        "Teams conversation captured",
        "This is the Teams context currently available to the relay bot.",
        facts=[
            *_visible_context_facts(captured, linked_route),
            ("Reference saved", "yes" if reference else "no"),
            ("Linked route", linked_route.name if linked_route else "none"),
        ],
        long_fields=long_fields,
        technical_fields=_technical_fields(captured),
        actions=actions,
    )


def _info_overview_command_activity(
    captured: dict[str, str],
    reference: BotConversationReference | None,
    routes: list[WebhookRoute],
) -> dict[str, Any]:
    route_fields = [(route.name, _route_overview_text(route, captured, link_webhook_url=True)) for route in routes]
    if not route_fields:
        route_fields = [("Routes", "none")]
    return _command_activity(
        "Teams conversation captured",
        "This is the Teams context currently available to the relay bot.",
        facts=[
            *_visible_context_facts(captured),
            ("Reference saved", "yes" if reference else "no"),
            ("Linked routes", str(len(routes))),
        ],
        long_fields=route_fields,
        technical_fields=_technical_fields(captured),
    )


def _route_overview_text(route: WebhookRoute, captured: dict[str, str], *, link_webhook_url: bool = False) -> str:
    webhook_url = _build_webhook_url(route.route_token) if route.route_token else "-"
    webhook_label = webhook_url
    if link_webhook_url and route.route_token:
        webhook_label = f"[{webhook_url}]({_build_webhook_copy_url(webhook_url)})"
    lines = [
        f"Status: {'active' if route.is_active else 'inactive'}",
        f"URL: {webhook_label}",
    ]
    names = _route_display_names(route, captured)
    team = names["team"]
    channel = names["channel"]
    user = names["user"]
    if team:
        lines.append(f"Team: {team}")
    if channel:
        lines.append(f"Channel: {channel}")
    if user:
        lines.append(f"User: {user}")
    lines.append(f"Details: /info {route.name}")
    return "\n".join(lines)


def _visible_context_facts(captured: dict[str, str], route: WebhookRoute | None = None) -> list[tuple[str, str]]:
    facts = [("Scope", _scope_for(captured))]
    names = _route_display_names(route, captured) if route else {
        "user": captured["user_name"],
        "team": captured["team_name"],
        "channel": captured["channel_name"],
    }
    user = names["user"]
    team = names["team"]
    channel = names["channel"]
    if user:
        facts.append(("User", user))
    if team:
        facts.append(("Team", team))
    if channel:
        facts.append(("Channel", channel))
    return facts


def _route_display_names(route: WebhookRoute | None, captured: dict[str, str]) -> dict[str, str]:
    names = {
        "user": captured["user_name"],
        "team": captured["team_name"],
        "channel": captured["channel_name"],
    }
    if route is None:
        return names
    if route.graph_team_name and not names["team"]:
        names["team"] = route.graph_team_name
    target_name = route.target_name.strip()
    if route.graph_target_kind == "channel" and target_name and _looks_like_display_label(target_name, route, captured):
        if " / " in target_name:
            team_name, channel_name = target_name.split(" / ", 1)
            names["team"] = names["team"] or team_name.strip()
            names["channel"] = names["channel"] or channel_name.strip()
        else:
            names["channel"] = names["channel"] or target_name
    elif route.graph_target_kind == "team" and target_name and _looks_like_display_label(target_name, route, captured):
        names["team"] = names["team"] or target_name
    elif route.graph_target_kind == "user" and target_name and _looks_like_display_label(target_name, route, captured):
        names["user"] = names["user"] or target_name
    return names


def _looks_like_display_label(value: str, route: WebhookRoute, captured: dict[str, str]) -> bool:
    cleaned = value.strip()
    if not cleaned:
        return False
    known_ids = {
        route.graph_target_id,
        route.graph_team_id,
        route.graph_channel_id,
        route.bot_registered_by_id,
        route.bot_conversation_id,
        captured["conversation_id"],
        captured["graph_team_id"],
        captured["team_id"],
        captured["channel_id"],
        captured["graph_user_id"],
        captured["from_id"],
    }
    if cleaned in known_ids:
        return False
    if re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", cleaned):
        return False
    if cleaned.startswith(("19:", "29:")):
        return False
    return True


def _help_command() -> CommandResult:
    reply_text = "\n".join(
        [
            "Available commands:",
            "`/register <route name>` - create or update a route for this Teams conversation.",
            "`/webhook <route name>` - show the webhook URL for an existing route.",
            "`/disable [route name]` - disable a route linked to this Teams conversation.",
            "`/enable [route name]` - enable a route linked to this Teams conversation.",
            "`/delete <route name>` - delete a route linked to this Teams conversation.",
            "`/info [route name]` - show linked routes or details for one route.",
            "`/help` - show this command list.",
        ]
    )
    return CommandResult(
        handled=True,
        command="help",
        reply_text=reply_text,
        activity=_command_activity(
            "Available commands",
            "Use these slash commands in a chat or channel where the relay bot is installed.",
            facts=[
                ("/register <route name>", "Create or update a route for this Teams conversation."),
                ("/webhook <route name>", "Show the webhook URL for an existing route."),
                ("/disable [route name]", "Disable a route linked to this Teams conversation."),
                ("/enable [route name]", "Enable a route linked to this Teams conversation."),
                ("/delete <route name>", "Delete a route linked to this Teams conversation."),
                ("/info [route name]", "Show linked routes or details for one route."),
                ("/help", "Show this command list."),
            ],
        ),
    )


def _register_route_from_command(
    db: Session,
    captured: dict[str, str],
    route_name: str,
    reference: BotConversationReference | None,
) -> CommandResult:
    if not route_name:
        reply_text = "Please include a route name, for example `/register Jira Alerts`."
        return CommandResult(
            handled=True,
            command="register",
            reply_text=reply_text,
            severity="warn",
            activity=_command_activity("Route name required", "Please include a route name before registering.", facts=[("Example", "/register Jira Alerts")]),
        )
    if len(route_name) > 200:
        reply_text = "Route names are limited to 200 characters. Please choose a shorter name."
        return CommandResult(
            handled=True,
            command="register",
            reply_text=reply_text,
            severity="warn",
            activity=_command_activity("Route name too long", "Route names are limited to 200 characters. Please choose a shorter name."),
        )
    if not captured["service_url"] or not captured["conversation_id"] or reference is None:
        reply_text = "I could not capture a complete Bot Framework conversation reference yet. Please send the command again from Teams."
        return CommandResult(
            handled=True,
            command="register",
            reply_text=reply_text,
            severity="warn",
            activity=_command_activity(
                "Conversation reference missing",
                "I could not capture a complete Bot Framework conversation reference yet. Please send the command again from Teams.",
            ),
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
    try_resolve_route_graph_names(route)
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
        activity=_route_command_activity(route, verb, webhook_url, effective),
    )


def _webhook_url_command(db: Session, route_name: str) -> CommandResult:
    if not route_name:
        reply_text = "Please include a route name, for example `/webhook Jira Alerts`."
        return CommandResult(
            handled=True,
            command="webhook",
            reply_text=reply_text,
            severity="warn",
            activity=_command_activity("Route name required", "Please include a route name to look up.", facts=[("Example", "/webhook Jira Alerts")]),
        )
    if len(route_name) > 200:
        reply_text = "Route names are limited to 200 characters. Please choose a shorter name."
        return CommandResult(
            handled=True,
            command="webhook",
            reply_text=reply_text,
            severity="warn",
            activity=_command_activity("Route name too long", "Route names are limited to 200 characters. Please choose a shorter name."),
        )
    organization = _default_organization(db)
    route = db.scalar(
        select(WebhookRoute).where(
            WebhookRoute.organization_id == organization.id,
            WebhookRoute.name == route_name,
        )
    )
    if route is None or not route.route_token:
        reply_text = f"No route named `{route_name}` exists yet. Use `/register {route_name}` from the target conversation first."
        return CommandResult(
            handled=True,
            command="webhook",
            reply_text=reply_text,
            severity="warn",
            activity=_command_activity(
                "Route not found",
                f"No route named {route_name} exists yet.",
                facts=[("Create it with", f"/register {route_name}")],
            ),
        )
    webhook_url = _build_webhook_url(route.route_token)
    return CommandResult(
        handled=True,
        command="webhook",
        reply_text=f"Webhook URL for `{route.name}`:\n{webhook_url}",
        activity=_webhook_command_activity(route, webhook_url),
    )


def _set_route_active_command(db: Session, captured: dict[str, str], route_name: str, *, is_active: bool) -> CommandResult:
    command = "enable" if is_active else "disable"
    verb = "enabled" if is_active else "disabled"
    if len(route_name) > 200:
        return _route_name_too_long_command(command)
    route, error = _resolve_linked_route(db, captured, route_name, command)
    if error:
        return error
    assert route is not None
    was_active = route.is_active
    route.is_active = is_active
    db.flush()
    _record_bot_route_audit(db, f"webhook_route.{verb}", route, captured, previous_is_active=was_active)
    state_text = "already " if was_active == is_active else ""
    reply_text = f"Route `{route.name}` is {state_text}{verb} for this Teams conversation."
    return CommandResult(
        handled=True,
        command=command,
        reply_text=reply_text,
        activity=_route_status_command_activity(route, verb, captured),
    )


def _delete_linked_route_command(db: Session, captured: dict[str, str], route_name: str) -> CommandResult:
    if not route_name:
        reply_text = "Please include a route name, for example `/delete Jira Alerts`."
        return CommandResult(
            handled=True,
            command="delete",
            reply_text=reply_text,
            severity="warn",
            activity=_command_activity(
                "Route name required",
                "Please include the route name before deleting.",
                facts=[("Example", "/delete Jira Alerts")],
            ),
        )
    if len(route_name) > 200:
        return _route_name_too_long_command("delete")
    route, error = _resolve_linked_route(db, captured, route_name, "delete")
    if error:
        return error
    assert route is not None
    route_id = route.id
    route_name = route.name
    target_name = route.target_name
    db.execute(update(WebhookDeliveryEvent).where(WebhookDeliveryEvent.route_id == route_id).values(route_id=None))
    _record_bot_route_audit(db, "webhook_route.deleted", route, captured)
    db.delete(route)
    db.flush()
    return CommandResult(
        handled=True,
        command="delete",
        reply_text=f"Route `{route_name}` deleted for this Teams conversation.",
        activity=_command_activity(
            "Route deleted",
            "The route has been deleted and its webhook URL will no longer accept messages.",
            facts=[
                ("Route", route_name),
                ("Target", target_name),
            ],
        ),
    )


def _info_command(
    db: Session,
    captured: dict[str, str],
    reference: BotConversationReference | None,
    route_name: str,
) -> CommandResult:
    if len(route_name) > 200:
        return _route_name_too_long_command("info")
    routes = _find_routes_for_reference(db, captured)
    linked_route = None
    if route_name:
        linked_route = next((route for route in routes if route.name == route_name), None)
        if linked_route is None:
            return CommandResult(
                handled=True,
                command="info",
                reply_text=f"No route named `{route_name}` is linked to this Teams conversation.",
                severity="warn",
                activity=_command_activity(
                    "Linked route not found",
                    f"No route named {route_name} is linked to this Teams conversation.",
                    facts=[("Linked routes", ", ".join(route.name for route in routes) if routes else "none")],
                ),
            )
    elif len(routes) == 1:
        linked_route = routes[0]
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
    if not route_name and linked_route is None:
        if routes:
            lines.append(f"Linked routes: `{len(routes)}`")
            for route in routes:
                lines.append(f"- `{route.name}`")
                lines.extend(f"  {line}" for line in _route_overview_text(route, captured).splitlines())
        else:
            lines.append("Linked routes: `none`")
            lines.append("Use `/register <route name>` to link a route to this Teams conversation.")
        return CommandResult(
            handled=True,
            command="info",
            reply_text="\n".join(lines),
            activity=_info_overview_command_activity(captured, reference, routes),
        )
    if linked_route and linked_route.route_token:
        lines.append(f"Linked route: `{linked_route.name}`")
        lines.append(f"Route status: `{'active' if linked_route.is_active else 'inactive'}`")
        lines.append(f"Target: `{linked_route.target_name or '-'}`")
        lines.append(f"Webhook URL: {_build_webhook_url(linked_route.route_token)}")
    else:
        lines.append("Linked route: `none`")
    return CommandResult(
        handled=True,
        command="info",
        reply_text="\n".join(lines),
        activity=_info_detail_command_activity(captured, reference, linked_route),
    )


def _resolve_linked_route(
    db: Session,
    captured: dict[str, str],
    route_name: str,
    command: str,
) -> tuple[WebhookRoute | None, CommandResult | None]:
    routes = _find_routes_for_reference(db, captured)
    if route_name:
        routes = [route for route in routes if route.name == route_name]
    if not routes:
        if route_name:
            reply_text = f"No route named `{route_name}` is linked to this Teams conversation."
            title = "Linked route not found"
            message = f"No route named {route_name} is linked to this Teams conversation."
        else:
            reply_text = "No webhook route is linked to this Teams conversation yet. Use `/register <route name>` first."
            title = "No linked route"
            message = "No webhook route is linked to this Teams conversation yet."
        return None, CommandResult(
            handled=True,
            command=command,
            reply_text=reply_text,
            severity="warn",
            activity=_command_activity(title, message, facts=[("Create it with", "/register <route name>")]),
        )
    if route_name:
        return routes[0], None
    if len(routes) == 1:
        return routes[0], None
    names = ", ".join(f"`{route.name}`" for route in routes)
    example = f"/{command} {routes[0].name}"
    return None, CommandResult(
        handled=True,
        command=command,
        reply_text=f"Multiple routes are linked to this Teams conversation: {names}. Please include a route name, for example `{example}`.",
        severity="warn",
        activity=_command_activity(
            "Route name required",
            "Multiple routes are linked to this Teams conversation. Please include the route name.",
            facts=[("Linked routes", ", ".join(route.name for route in routes)), ("Example", example)],
        ),
    )


def _find_routes_for_reference(db: Session, captured: dict[str, str]) -> list[WebhookRoute]:
    organization = _default_organization(db)
    routes_by_id: dict[str, WebhookRoute] = {}
    if captured["conversation_id"]:
        for route in db.scalars(
            select(WebhookRoute)
            .where(
                WebhookRoute.organization_id == organization.id,
                WebhookRoute.bot_conversation_id == captured["conversation_id"],
            )
            .order_by(WebhookRoute.updated_at.desc())
        ).all():
            routes_by_id.setdefault(route.id, route)
    if captured["graph_team_id"] and captured["channel_id"]:
        for route in db.scalars(
            select(WebhookRoute)
            .where(
                WebhookRoute.organization_id == organization.id,
                WebhookRoute.graph_team_id == captured["graph_team_id"],
                WebhookRoute.graph_channel_id == captured["channel_id"],
            )
            .order_by(WebhookRoute.updated_at.desc())
        ).all():
            routes_by_id.setdefault(route.id, route)
    return list(routes_by_id.values())


def _route_name_too_long_command(command: str) -> CommandResult:
    return CommandResult(
        handled=True,
        command=command,
        reply_text="Route names are limited to 200 characters. Please choose a shorter name.",
        severity="warn",
        activity=_command_activity("Route name too long", "Route names are limited to 200 characters. Please choose a shorter name."),
    )


def _route_status_command_activity(route: WebhookRoute, verb: str, captured: dict[str, str]) -> dict[str, Any]:
    return _command_activity(
        f"Route {verb}",
        f"{route.name} is {verb} for this Teams conversation.",
        facts=[
            ("Route", route.name),
            ("Target", route.target_name),
            ("Scope", _scope_for(captured)),
            ("Status", "active" if route.is_active else "inactive"),
        ],
    )


def _record_bot_route_audit(
    db: Session,
    action: str,
    route: WebhookRoute,
    captured: dict[str, str],
    **extra_metadata: Any,
) -> None:
    metadata = {
        "webhook_route_id": route.id,
        "name": route.name,
        "conversation_id": captured["conversation_id"],
        "graph_team_id": captured["graph_team_id"],
        "channel_id": captured["channel_id"],
        "teams_user_id": captured["from_id"],
        "aad_user_id": captured["graph_user_id"],
    }
    metadata.update(extra_metadata)
    record_audit(
        db,
        action=action,
        actor_type="bot_command",
        actor_id=None,
        organization_id=route.organization_id,
        metadata=metadata,
    )


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


def _build_webhook_copy_url(webhook_url: str) -> str:
    settings = get_settings()
    query = urllib.parse.urlencode({"url": webhook_url})
    return f"{settings.frontend_base_url.rstrip('/')}/copy-webhook?{query}"


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
