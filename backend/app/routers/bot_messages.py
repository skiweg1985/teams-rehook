from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import timedelta
from html import unescape
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.core.settings_overrides import get_effective_settings
from app.database import get_db
from app.deps import record_audit, require_admin, require_csrf
from app.models import (
    BotActivityEvent,
    BotAuthorizedGroup,
    BotAuthorizedUser,
    BotConversationReference,
    BotUserGroupMembershipCache,
    Organization,
    User,
    WebhookDeliveryEvent,
    WebhookRoute,
    WebhookUrlRevealToken,
)
from app.schemas import (
    BotActivityIngestOut,
    BotConversationLinkedRouteOut,
    BotConversationReferenceDetailOut,
    BotConversationReferenceOut,
)
from app.security import dumps_json, ensure_utc, issue_plain_secret, lookup_secret_hash, utcnow
from app.services.client_ip_allowlist import (
    CLIENT_IP_ACCESS_PUBLIC,
    CLIENT_IP_ACCESS_RESTRICTED,
    normalize_client_ip_allowlist,
)
from app.services.bot_framework_auth import (
    BotFrameworkClaims,
    BotFrameworkAuthConfigError,
    BotFrameworkAuthError,
    validate_bot_framework_activity,
)
from app.services.bot_conversation_members import (
    BotConversationMembersError,
    fetch_bot_conversation_members,
    serialize_members,
)
from app.services.graph_name_resolution import try_resolve_reference_graph_names, try_resolve_route_graph_names
from app.services.graph_targets import GraphConfigError, GraphRequestError, list_user_transitive_group_ids
from app.services.event_log import emit_event
from app.services.bot_access_roles import BOT_PERMISSION_FIELDS, role_permissions
from app.services.teams_bot import BotDeliveryError, send_bot_activity
from app.services.webhook_payloads import NormalizedMessage

router = APIRouter(tags=["bot-messages"])
DELIVERY_BACKEND_BOT = "bot_framework"
CHAT_MEMBER_REFRESH_AFTER = timedelta(hours=6)
BOT_GROUP_MEMBERSHIP_CACHE_TTL = timedelta(minutes=10)
async def require_bot_framework_auth(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    body = await request.body()
    try:
        activity = json.loads(body) if body else {}
    except json.JSONDecodeError:
        activity = {}
    if not isinstance(activity, dict):
        activity = {}
    try:
        return validate_bot_framework_activity(authorization, activity)
    except BotFrameworkAuthConfigError as exc:
        emit_event(
            level="error",
            category="integration",
            event_type="bot.auth.configuration_error",
            message="Bot Framework authentication is not configured correctly.",
            source={"ip": request.client.host if request.client else "", "user_agent": request.headers.get("user-agent", "")},
            security={"severity": "high", "reason": "bot_auth_config_error"},
            raw={"exception_type": exc.__class__.__name__, "exception": str(exc)},
            domain="system",
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except BotFrameworkAuthError as exc:
        emit_event(
            level="warning",
            category="security",
            event_type="bot.auth.rejected",
            message="Bot Framework activity was rejected by authentication validation.",
            source={"ip": request.client.host if request.client else "", "user_agent": request.headers.get("user-agent", "")},
            security={"severity": "high", "reason": "bot_auth_rejected"},
            raw={"exception_type": exc.__class__.__name__, "exception": str(exc)},
            domain="system",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.post("/bot/messages", response_model=BotActivityIngestOut)
async def receive_bot_activity(
    request: Request,
    bot_auth: BotFrameworkClaims = Depends(require_bot_framework_auth),
    db: Session = Depends(get_db),
):
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
        auth_status="verified",
        auth_issuer=bot_auth.issuer,
        auth_audience=bot_auth.audience,
        auth_service_url=bot_auth.service_url,
        auth_service_url_matched=bot_auth.service_url_matched,
        auth_validated_at=bot_auth.validated_at,
    )
    db.add(event)
    db.flush()
    emit_event(
        db,
        level="info",
        category="integration",
        event_type="bot.activity.received",
        message=f"Teams bot activity received: {event.activity_type or 'activity'}",
        user_message="Teams activity received",
        actor={"type": "external", "id": event.graph_user_id or event.from_id, "displayName": event.user_name},
        target={
            "type": "team" if event.team_id else "message",
            "id": event.channel_id or event.conversation_id,
            "team_id": event.team_id,
            "channel_id": event.channel_id,
        },
        security={"severity": "low", "reason": event.auth_status},
        raw={"conversation_type": event.conversation_type, "service_url": event.service_url},
        domain="bot_activity",
        domain_event_id=event.id,
    )
    reference = _upsert_reference(db, captured)
    parsed_command = _parse_activity_command(activity) if captured["activity_type"] == "message" else None
    command_result = CommandResult()
    if parsed_command:
        authorization = _authorize_bot_command(db, captured, parsed_command)
        event.bot_authorization_status = authorization.status
        event.bot_authorized_user_id = authorization.bot_user.id if authorization.bot_user else ""
        event.bot_authorization_reason = authorization.reason
        _record_bot_command_authorization(db, authorization, captured, parsed_command)
        if authorization.allowed:
            command_result = _handle_command(db, activity, captured, reference, parsed=parsed_command, bot_user=authorization)
        else:
            command_result = _authorization_denied_command(parsed_command[0], authorization)
    else:
        event.bot_authorization_status = "not_applicable"
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
    changed = False
    for reference in references:
        changed = _refresh_reference_chat_members(reference) or changed
    if changed:
        db.commit()
    return references


@router.get("/bot/conversation-references/{reference_id}", response_model=BotConversationReferenceDetailOut)
def get_bot_conversation_reference(reference_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    reference = _get_conversation_reference(db, reference_id)
    linked_routes = _find_routes_for_conversation_reference(db, admin.organization_id, reference)
    return _reference_detail_out(reference, linked_routes)


@router.post(
    "/bot/conversation-references/{reference_id}/refresh-members",
    response_model=BotConversationReferenceDetailOut,
    dependencies=[Depends(require_csrf)],
)
def refresh_bot_conversation_reference_members(
    reference_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    reference = _get_conversation_reference(db, reference_id)
    _refresh_reference_chat_members(reference, force=True)
    linked_routes = _find_routes_for_conversation_reference(db, admin.organization_id, reference)
    record_audit(
        db,
        action="bot_conversation_reference.members_refreshed",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={
            "conversation_reference_id": reference.id,
            "conversation_id": reference.conversation_id,
            "member_count": reference.member_count,
            "lookup_error": bool(reference.members_lookup_error),
        },
    )
    db.commit()
    db.refresh(reference)
    linked_routes = _find_routes_for_conversation_reference(db, admin.organization_id, reference)
    return _reference_detail_out(reference, linked_routes)


@router.delete(
    "/bot/conversation-references/{reference_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def delete_bot_conversation_reference(
    reference_id: str,
    delete_linked_routes: bool = False,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    reference = _get_conversation_reference(db, reference_id)
    linked_routes = _find_routes_for_conversation_reference(db, admin.organization_id, reference)
    if linked_routes and not delete_linked_routes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation is still used by webhook routes. Confirm linked route deletion first.",
        )
    linked_route_ids = [route.id for route in linked_routes]
    for route in linked_routes:
        db.execute(update(WebhookDeliveryEvent).where(WebhookDeliveryEvent.route_id == route.id).values(route_id=None))
        db.execute(delete(WebhookUrlRevealToken).where(WebhookUrlRevealToken.route_id == route.id))
        record_audit(
            db,
            action="webhook_route.deleted",
            actor_type="user",
            actor_id=admin.id,
            organization_id=admin.organization_id,
            metadata={
                "webhook_route_id": route.id,
                "name": route.name,
                "deleted_with_conversation_reference_id": reference.id,
            },
        )
        db.delete(route)
    record_audit(
        db,
        action="bot_conversation_reference.deleted",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={
            "conversation_reference_id": reference.id,
            "conversation_id": reference.conversation_id,
            "linked_route_ids": linked_route_ids,
            "linked_route_count": len(linked_route_ids),
            "delete_linked_routes": delete_linked_routes,
        },
    )
    db.delete(reference)
    db.commit()
    return None


@dataclass(frozen=True)
class CommandResult:
    handled: bool = False
    command: str | None = None
    reply_text: str | None = None
    title: str = "Teams Rehook"
    severity: str = "info"
    activity: dict[str, Any] | None = None


@dataclass(frozen=True)
class BotCommandAuthorization:
    allowed: bool
    status: str
    reason: str
    command: str
    required_permission: str = ""
    bot_user: BotAuthorizedUser | None = None
    bot_groups: list[BotAuthorizedGroup] = field(default_factory=list)
    permissions: dict[str, bool] = field(default_factory=dict)
    cache_status: str = ""
    cache_error: str = ""

    def __getattr__(self, name: str) -> bool:
        if name in BOT_PERMISSION_FIELDS:
            return bool(self.permissions.get(name))
        raise AttributeError(name)


KNOWN_COMMANDS = {"register", "webhook", "disable", "enable", "delete", "info", "allowlist", "help"}
SAFE_SUBMIT_COMMANDS = {"webhook", "disable", "enable", "info", "help"}
UNAUTHORIZED_BOT_USER_REPLY = (
    "You are not authorized to use Teams Rehook. Please contact IT to request access."
)


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
    _refresh_reference_chat_members(reference)
    db.flush()
    return reference


def _refresh_reference_chat_members(reference: BotConversationReference, *, force: bool = False) -> bool:
    if reference.scope != "chat" and reference.conversation_type.lower() != "groupchat":
        return False
    if not reference.service_url or not reference.conversation_id:
        return False
    now = utcnow()
    members_refreshed_at = ensure_utc(reference.members_refreshed_at)
    if (
        not force
        and members_refreshed_at is not None
        and now - members_refreshed_at < CHAT_MEMBER_REFRESH_AFTER
    ):
        return False
    try:
        result = fetch_bot_conversation_members(
            service_url=reference.service_url,
            conversation_id=reference.conversation_id,
        )
    except (BotConversationMembersError, BotDeliveryError) as exc:
        reference.members_lookup_error = _clip(str(exc), 1000)
        reference.members_refreshed_at = now
        reference.updated_at = now
        return True
    reference.member_summary = result.member_summary
    reference.member_count = result.member_count
    reference.member_list_json = serialize_members(result.members)
    reference.members_lookup_error = ""
    reference.members_refreshed_at = now
    reference.updated_at = now
    return True


def _get_conversation_reference(db: Session, reference_id: str) -> BotConversationReference:
    reference = db.get(BotConversationReference, reference_id)
    if reference is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation reference not found")
    return reference


def _find_routes_for_conversation_reference(
    db: Session,
    organization_id: str,
    reference: BotConversationReference,
) -> list[WebhookRoute]:
    route_filters = []
    if reference.conversation_id:
        route_filters.append(WebhookRoute.bot_conversation_id == reference.conversation_id)
        route_filters.append(
            (WebhookRoute.graph_target_kind == "chat")
            & (WebhookRoute.graph_target_id == reference.conversation_id)
        )
    if reference.graph_team_id and reference.channel_id:
        route_filters.append(
            (WebhookRoute.graph_team_id == reference.graph_team_id)
            & (WebhookRoute.graph_channel_id == reference.channel_id)
        )
    if not route_filters:
        return []
    routes = db.scalars(
        select(WebhookRoute)
        .where(WebhookRoute.organization_id == organization_id, or_(*route_filters))
        .order_by(WebhookRoute.updated_at.desc())
    ).all()
    routes_by_id: dict[str, WebhookRoute] = {}
    for route in routes:
        routes_by_id.setdefault(route.id, route)
    return list(routes_by_id.values())


def _reference_detail_out(
    reference: BotConversationReference,
    linked_routes: list[WebhookRoute],
) -> BotConversationReferenceDetailOut:
    detail = BotConversationReferenceDetailOut.model_validate(reference)
    detail.linked_routes = [_linked_route_out(route) for route in linked_routes]
    detail.linked_route_count = len(linked_routes)
    return detail


def _linked_route_out(route: WebhookRoute) -> BotConversationLinkedRouteOut:
    return BotConversationLinkedRouteOut(
        id=route.id,
        name=route.name,
        is_active=route.is_active,
        delivery_backend=route.delivery_backend,
        target_name=route.target_name,
        last_delivery_status=route.last_delivery_status,
        last_delivery_at=route.last_delivery_at,
        updated_at=route.updated_at,
    )


def _scope_for(captured: dict[str, str]) -> str:
    if captured["conversation_type"] == "personal":
        return "user"
    if captured["team_id"] and captured["channel_id"]:
        return "channel"
    if captured["team_id"]:
        return "team"
    if _is_group_conversation(captured):
        return "chat"
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
        "is_group": _bool_string(conversation.get("isGroup")),
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


def _authorize_bot_command(
    db: Session,
    captured: dict[str, str],
    parsed: tuple[str, str],
) -> BotCommandAuthorization:
    command, argument = parsed
    aad_object_id = captured["graph_user_id"].strip().lower()
    if not aad_object_id:
        return BotCommandAuthorization(
            allowed=False,
            status="denied",
            reason="missing_aad_object_id",
            command=command,
        )
    organization = _default_organization(db)
    bot_user = db.scalar(
        select(BotAuthorizedUser).where(
            BotAuthorizedUser.organization_id == organization.id,
            BotAuthorizedUser.aad_object_id == aad_object_id,
        )
    )
    active_bot_user = bot_user if bot_user and bot_user.is_active else None
    group_ids, cache_status, cache_error = _bot_group_ids_for_sender(db, organization.id, aad_object_id)
    if cache_status == "error" and active_bot_user is None:
        return BotCommandAuthorization(
            allowed=False,
            status="denied",
            reason="group_membership_lookup_unavailable",
            command=command,
            bot_user=active_bot_user,
            cache_status=cache_status,
            cache_error=cache_error,
        )
    bot_groups = [] if cache_status == "error" else _matching_bot_groups(db, organization.id, group_ids)
    permissions = _union_bot_permissions([source for source in [active_bot_user, *bot_groups] if source is not None])
    if active_bot_user is None and not bot_groups:
        return BotCommandAuthorization(
            allowed=False,
            status="denied",
            reason="bot_user_not_authorized",
            command=command,
            bot_user=active_bot_user,
            bot_groups=bot_groups,
            permissions=permissions,
            cache_status=cache_status,
            cache_error=cache_error,
        )
    required_permission = _required_bot_permission(command, argument, captured)
    if required_permission and not bool(permissions.get(required_permission)):
        return BotCommandAuthorization(
            allowed=False,
            status="permission_denied",
            reason=f"missing_{required_permission}",
            command=command,
            required_permission=required_permission,
            bot_user=active_bot_user,
            bot_groups=bot_groups,
            permissions=permissions,
            cache_status=cache_status,
            cache_error=cache_error,
        )
    now = utcnow()
    if active_bot_user is not None:
        active_bot_user.last_seen_at = now
        active_bot_user.updated_at = now
    for bot_group in bot_groups:
        bot_group.last_matched_at = now
        bot_group.updated_at = now
    return BotCommandAuthorization(
        allowed=True,
        status="authorized",
        reason="authorized",
        command=command,
        required_permission=required_permission,
        bot_user=active_bot_user,
        bot_groups=bot_groups,
        permissions=permissions,
        cache_status=cache_status,
        cache_error=cache_error,
    )


def _required_bot_permission(command: str, argument: str, captured: dict[str, str]) -> str:
    if command == "help":
        return ""
    if command == "info":
        return "can_view_routes"
    if command == "webhook":
        return "can_reveal_webhook_urls"
    if command in {"enable", "disable"}:
        return "can_manage_route_status"
    if command == "delete":
        return "can_delete_routes"
    if command == "register":
        return "can_create_channel_routes" if _scope_for(captured) in {"team", "channel"} else "can_create_private_chat_routes"
    if command == "allowlist":
        return "can_manage_allowlist" if _allowlist_argument_is_write(argument) else "can_view_routes"
    return ""


def _allowlist_argument_is_write(argument: str) -> bool:
    lowered = argument.strip().lower()
    return lowered == CLIENT_IP_ACCESS_PUBLIC or lowered.startswith(f"{CLIENT_IP_ACCESS_PUBLIC} ") or lowered == CLIENT_IP_ACCESS_RESTRICTED or lowered.startswith(f"{CLIENT_IP_ACCESS_RESTRICTED} ")


def _bot_group_ids_for_sender(db: Session, organization_id: str, aad_object_id: str) -> tuple[list[str], str, str]:
    now = utcnow()
    has_group_grants = db.scalar(
        select(BotAuthorizedGroup.id)
        .where(BotAuthorizedGroup.organization_id == organization_id, BotAuthorizedGroup.is_active.is_(True))
        .limit(1)
    )
    if not has_group_grants:
        return [], "not_configured", ""
    cache = db.scalar(
        select(BotUserGroupMembershipCache).where(
            BotUserGroupMembershipCache.organization_id == organization_id,
            BotUserGroupMembershipCache.aad_object_id == aad_object_id,
        )
    )
    if cache and ensure_utc(cache.expires_at) and ensure_utc(cache.expires_at) > now:
        return cache.group_ids, "hit", cache.last_error or ""
    try:
        group_ids = list_user_transitive_group_ids(aad_object_id)
    except (GraphConfigError, GraphRequestError) as exc:
        error = _clip(str(exc), 1000)
        if cache is not None:
            cache.checked_at = now
            cache.last_error = error
            cache.updated_at = now
        return [], "error", error
    if cache is None:
        cache = BotUserGroupMembershipCache(organization_id=organization_id, aad_object_id=aad_object_id)
        db.add(cache)
    cache.group_ids_json = dumps_json(group_ids)
    cache.checked_at = now
    cache.expires_at = now + BOT_GROUP_MEMBERSHIP_CACHE_TTL
    cache.last_error = ""
    cache.updated_at = now
    return group_ids, "miss", ""


def _matching_bot_groups(db: Session, organization_id: str, group_ids: list[str]) -> list[BotAuthorizedGroup]:
    normalized_ids = [group_id.strip().lower() for group_id in group_ids if group_id.strip()]
    if not normalized_ids:
        return []
    return db.scalars(
        select(BotAuthorizedGroup)
        .where(
            BotAuthorizedGroup.organization_id == organization_id,
            BotAuthorizedGroup.is_active.is_(True),
            BotAuthorizedGroup.group_object_id.in_(normalized_ids),
        )
        .order_by(BotAuthorizedGroup.display_name.asc())
    ).all()


def _union_bot_permissions(sources: list[BotAuthorizedUser | BotAuthorizedGroup]) -> dict[str, bool]:
    return {
        field_name: any(_effective_bot_permissions(source).get(field_name, False) for source in sources)
        for field_name in BOT_PERMISSION_FIELDS
    }


def _effective_bot_permissions(source: BotAuthorizedUser | BotAuthorizedGroup) -> dict[str, bool]:
    access_role = getattr(source, "access_role", None)
    if getattr(source, "role_id", None) and access_role is not None:
        return role_permissions(access_role)
    return {field_name: bool(getattr(source, field_name)) for field_name in BOT_PERMISSION_FIELDS}


def _authorization_denied_command(command: str, authorization: BotCommandAuthorization) -> CommandResult:
    if authorization.status == "permission_denied":
        message = _permission_denied_message(authorization.required_permission)
        return CommandResult(
            handled=True,
            command=command,
            reply_text=message,
            severity="warn",
            activity=_command_activity(
                "Permission denied",
                message,
                status="warning",
            ),
        )
    if authorization.reason == "group_membership_lookup_unavailable":
        message = "Teams Rehook cannot verify your authorization right now. Please try again later or contact IT."
        return CommandResult(
            handled=True,
            command=command,
            reply_text=message,
            severity="warn",
            activity=_command_activity(
                "Authorization unavailable",
                message,
                status="warning",
            ),
        )
    return CommandResult(
        handled=True,
        command=command,
        reply_text=UNAUTHORIZED_BOT_USER_REPLY,
        severity="warn",
        activity=_command_activity(
            "Not authorized",
            UNAUTHORIZED_BOT_USER_REPLY,
            status="warning",
        ),
    )


def _permission_denied_message(required_permission: str) -> str:
    labels = {
        "can_view_routes": "view Teams conversations and webhook routes",
        "can_reveal_webhook_urls": "view webhook URLs",
        "can_manage_route_status": "enable or disable webhook routes",
        "can_delete_routes": "delete webhook routes",
        "can_manage_allowlist": "manage client IP allowlists",
        "can_create_private_chat_routes": "create webhook routes for private chats",
        "can_create_channel_routes": "create webhook routes for Teams channels",
    }
    action = labels.get(required_permission, "run this bot command")
    return f"You are signed in, but you do not have permission to {action}. Please contact IT if you need this access."


def _record_bot_command_authorization(
    db: Session,
    authorization: BotCommandAuthorization,
    captured: dict[str, str],
    parsed: tuple[str, str],
) -> None:
    command, argument = parsed
    action = {
        "authorized": "bot_command.authorized",
        "permission_denied": "bot_command.permission_denied",
    }.get(authorization.status, "bot_command.denied")
    record_audit(
        db,
        action=action,
        actor_type="bot_command",
        actor_id=captured["graph_user_id"] or captured["from_id"] or None,
        organization_id=_default_organization(db).id,
        metadata={
            "command": command,
            "argument": argument,
            "scope": _scope_for(captured),
            "reason": authorization.reason,
            "required_permission": authorization.required_permission,
            "bot_authorized_user_id": authorization.bot_user.id if authorization.bot_user else "",
            "authorization_sources": {
                "direct_user": (
                    {
                        "id": authorization.bot_user.id,
                        "aad_object_id": authorization.bot_user.aad_object_id,
                        "display_name": authorization.bot_user.display_name,
                        "role": authorization.bot_user.role,
                    }
                    if authorization.bot_user
                    else None
                ),
                "groups": [
                    {
                        "id": bot_group.id,
                        "group_object_id": bot_group.group_object_id,
                        "display_name": bot_group.display_name,
                        "mail": bot_group.mail,
                        "role": bot_group.role,
                    }
                    for bot_group in authorization.bot_groups
                ],
                "cache_status": authorization.cache_status,
                "cache_error": authorization.cache_error,
                "permissions": authorization.permissions,
                "allowed": authorization.allowed,
            },
            "aad_object_id": captured["graph_user_id"],
            "teams_user_id": captured["from_id"],
            "user_name": captured["user_name"],
            "conversation_id": captured["conversation_id"],
            "graph_team_id": captured["graph_team_id"],
            "channel_id": captured["channel_id"],
        },
    )


def _handle_command(
    db: Session,
    activity: dict[str, Any],
    captured: dict[str, str],
    reference: BotConversationReference | None,
    *,
    parsed: tuple[str, str] | None = None,
    bot_user: BotAuthorizedUser | None = None,
) -> CommandResult:
    if captured["activity_type"] != "message":
        return CommandResult()
    parsed = parsed or _parse_activity_command(activity)
    if not parsed:
        return CommandResult()
    command, argument = parsed
    if command == "register":
        return _register_route_from_command(db, captured, argument, reference, bot_user=bot_user)
    if command == "webhook":
        return _webhook_url_command(db, argument, bot_user=bot_user)
    if command == "disable":
        return _set_route_active_command(db, captured, argument, is_active=False, bot_user=bot_user)
    if command == "enable":
        return _set_route_active_command(db, captured, argument, is_active=True, bot_user=bot_user)
    if command == "delete":
        return _delete_linked_route_command(db, captured, argument)
    if command == "info":
        return _info_command(db, captured, reference, argument, bot_user=bot_user)
    if command == "allowlist":
        return _allowlist_command(db, captured, argument)
    if command == "help":
        return _help_command(bot_user=bot_user)
    return CommandResult()


def _parse_activity_command(activity: dict[str, Any]) -> tuple[str, str] | None:
    parsed = _parse_submit_command(_dict(activity.get("value")))
    if parsed:
        return parsed
    return _parse_command(_string(activity.get("text")))


def _parse_submit_command(value: dict[str, Any]) -> tuple[str, str] | None:
    command_value = _string(value.get("command")).strip()
    if not command_value:
        return None
    parsed = _parse_command(command_value)
    if parsed:
        command, embedded_argument = parsed
    else:
        command = command_value.lower()
        embedded_argument = ""
    if command not in SAFE_SUBMIT_COMMANDS:
        return None
    route_name = (
        _string(value.get("route_name"))
        or _string(value.get("routeName"))
        or _string(value.get("route"))
        or _string(value.get("argument"))
    )
    argument = " ".join((route_name or embedded_argument).strip().split())
    return command, argument


def _parse_command(text: str) -> tuple[str, str] | None:
    cleaned = unescape(re.sub(r"<at>.*?</at>", "", text, flags=re.IGNORECASE | re.DOTALL)).strip()
    if not cleaned or cleaned.startswith("/"):
        return None
    match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*)(?:\s+(.+))?$", cleaned, flags=re.DOTALL)
    if not match:
        return None
    command = match.group(1).lower()
    if command not in KNOWN_COMMANDS:
        return None
    return command, " ".join((match.group(2) or "").strip().split())


def _command_activity(
    title: str,
    message: str = "",
    *,
    status: str = "info",
    facts: list[tuple[str, str]] | None = None,
    long_fields: list[tuple[str, str]] | None = None,
    sections: list[dict[str, Any]] | None = None,
    technical_fields: list[tuple[str, str]] | None = None,
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": title,
            "weight": "Bolder",
            "size": "Medium",
            "color": _card_status_color(status),
            "wrap": True,
        }
    ]
    if message:
        body.append({"type": "TextBlock", "text": message, "wrap": True, "spacing": "Small"})
    status_text = _card_status_text(status)
    if status_text:
        body.append(
            {
                "type": "TextBlock",
                "text": status_text,
                "size": "Small",
                "color": _card_status_color(status),
                "weight": "Bolder",
                "spacing": "Small",
                "wrap": True,
            }
        )
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
    if sections:
        body.append({"type": "Container", "spacing": "Medium", "items": sections})
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


def _card_status_text(status: str) -> str:
    return {
        "success": "Status: ready",
        "warning": "Status: needs attention",
        "inactive": "Status: inactive",
    }.get(status, "")


def _card_status_color(status: str) -> str:
    return {
        "success": "Good",
        "warning": "Warning",
        "inactive": "Attention",
    }.get(status, "Accent")


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


def _open_url_action(title: str, url: str) -> dict[str, Any]:
    return {"type": "Action.OpenUrl", "title": title, "url": url}


def _copy_webhook_url_action(reveal_url: str) -> dict[str, Any]:
    return _open_url_action("Open webhook URL", reveal_url)


def _submit_command_action(title: str, command: str, route_name: str = "") -> dict[str, Any]:
    data: dict[str, str] = {"command": command}
    if route_name:
        data["route_name"] = route_name
    return {"type": "Action.Submit", "title": title, "data": data}


def _route_safe_actions(route: WebhookRoute, *, reveal_url: str = "", include_status_toggle: bool = True) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if reveal_url:
        actions.append(_copy_webhook_url_action(reveal_url))
    actions.append(_submit_command_action("Info", "info", route.name))
    if include_status_toggle:
        actions.append(
            _submit_command_action(
                "Disable" if route.is_active else "Enable",
                "disable" if route.is_active else "enable",
                route.name,
            )
        )
    return actions


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


def _route_command_activity(
    route: WebhookRoute,
    verb: str,
    reveal_url: str,
    captured: dict[str, str],
    *,
    bot_user: BotAuthorizedUser | None = None,
) -> dict[str, Any]:
    target_name = _target_name(captured)
    return _command_activity(
        f"Route {verb}",
        f"{route.name} is ready for this Teams conversation.",
        status="success",
        facts=[
            ("Route", route.name),
            ("Target", target_name),
            ("Scope", _scope_for(captured)),
            ("Route status", "active" if route.is_active else "inactive"),
            ("Client IP access", _client_ip_access_summary(route)),
        ],
        technical_fields=_technical_fields(captured),
        actions=_route_safe_actions(
            route,
            reveal_url=reveal_url,
            include_status_toggle=bool(bot_user and bot_user.can_manage_route_status),
        ),
    )


def _webhook_command_activity(route: WebhookRoute, reveal_url: str, *, bot_user: BotAuthorizedUser | None = None) -> dict[str, Any]:
    return _command_activity(
        "Webhook URL",
        "Open the button below to view and copy the stable incoming webhook URL.",
        status="success" if route.is_active else "inactive",
        facts=[
            ("Route", route.name),
            ("Target", route.target_name),
            ("Status", "active" if route.is_active else "inactive"),
            ("Client IP access", _client_ip_access_summary(route)),
        ],
        actions=_route_safe_actions(
            route,
            reveal_url=reveal_url,
            include_status_toggle=bool(bot_user and bot_user.can_manage_route_status),
        ),
    )


def _info_detail_command_activity(
    captured: dict[str, str],
    reference: BotConversationReference | None,
    linked_route: WebhookRoute | None,
    reveal_url: str = "",
    *,
    bot_user: BotAuthorizedUser | None = None,
) -> dict[str, Any]:
    actions = [_copy_webhook_url_action(reveal_url)] if reveal_url else []
    facts = [
        *_visible_context_facts(captured, linked_route),
        ("Reference saved", "yes" if reference else "no"),
        ("Linked route", linked_route.name if linked_route else "none"),
    ]
    if linked_route:
        facts.append(("Client IP access", _client_ip_access_summary(linked_route)))
    return _command_activity(
        "Teams conversation captured",
        "This is the Teams context currently available to the relay bot.",
        status="success" if linked_route and linked_route.is_active else "info",
        facts=facts,
        technical_fields=_technical_fields(captured),
        actions=[
            *actions,
            *(
                _route_safe_actions(
                    linked_route,
                    include_status_toggle=bool(bot_user and bot_user.can_manage_route_status),
                )
                if linked_route
                else []
            ),
        ],
    )


def _info_overview_command_activity(
    captured: dict[str, str],
    reference: BotConversationReference | None,
    routes: list[WebhookRoute],
    reveal_urls: dict[str, str],
    *,
    bot_user: BotAuthorizedUser | None = None,
) -> dict[str, Any]:
    route_sections = [
        _route_section_item(route, captured, reveal_url=reveal_urls.get(route.id, ""), bot_user=bot_user)
        for route in routes
    ]
    long_fields = [] if route_sections else [("Routes", "none")]
    return _command_activity(
        "Teams conversation captured",
        "This is the Teams context currently available to the relay bot.",
        facts=[
            *_visible_context_facts(captured),
            ("Reference saved", "yes" if reference else "no"),
            ("Linked routes", str(len(routes))),
        ],
        long_fields=long_fields,
        sections=route_sections,
        technical_fields=_technical_fields(captured),
        actions=[_submit_command_action("Refresh info", "info")],
    )


def _route_section_item(
    route: WebhookRoute,
    captured: dict[str, str],
    *,
    reveal_url: str = "",
    bot_user: BotAuthorizedUser | None = None,
) -> dict[str, Any]:
    facts = [
        ("Status", "active" if route.is_active else "inactive"),
        ("Target", route.target_name),
        ("Client IP access", _client_ip_access_summary(route)),
    ]
    names = _route_display_names(route, captured)
    for label, key in [("Team", "team"), ("Channel", "channel"), ("User", "user")]:
        if names[key]:
            facts.append((label, names[key]))
    return {
        "type": "Container",
        "style": "emphasis",
        "spacing": "Medium",
        "items": [
            {"type": "TextBlock", "text": route.name, "weight": "Bolder", "wrap": True},
            {
                "type": "FactSet",
                "spacing": "Small",
                "facts": [{"title": f"{label}:", "value": _card_value(value)} for label, value in facts],
            },
            {
                "type": "ActionSet",
                "spacing": "Small",
                "actions": _route_safe_actions(
                    route,
                    reveal_url=reveal_url,
                    include_status_toggle=bool(bot_user and bot_user.can_manage_route_status),
                ),
            },
        ],
    }


def _route_overview_text(route: WebhookRoute, captured: dict[str, str], *, reveal_url: str = "") -> str:
    webhook_label = f"[Open webhook URL]({reveal_url})" if reveal_url else "-"
    lines = [
        f"Status: {'active' if route.is_active else 'inactive'}",
        f"Client IP access: {_client_ip_access_summary(route)}",
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
    lines.append(f"Details: info {route.name}")
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


def _help_command(*, bot_user: BotAuthorizedUser | None = None) -> CommandResult:
    commands = _available_help_commands(bot_user)
    reply_text = "\n".join(
        [
            "Available commands:",
            *[f"`{command}` - {description[0].lower()}{description[1:]}" for command, description in commands],
        ]
    )
    return CommandResult(
        handled=True,
        command="help",
        reply_text=reply_text,
        activity=_help_command_activity(commands),
    )


def _available_help_commands(bot_user: BotAuthorizedUser | None) -> list[tuple[str, str]]:
    commands: list[tuple[str, str]] = []
    if bot_user and (bot_user.can_create_private_chat_routes or bot_user.can_create_channel_routes):
        commands.append(("register <route name>", "Create or update a route for this Teams conversation."))
    if bot_user and bot_user.can_reveal_webhook_urls:
        commands.append(("webhook <route name>", "Show the webhook URL for an existing route."))
    if bot_user and bot_user.can_manage_route_status:
        commands.extend(
            [
                ("disable [route name]", "Disable a route linked to this Teams conversation."),
                ("enable [route name]", "Enable a route linked to this Teams conversation."),
            ]
        )
    if bot_user and bot_user.can_delete_routes:
        commands.append(("delete <route name>", "Delete a route linked to this Teams conversation."))
    if bot_user and bot_user.can_view_routes:
        commands.append(("info [route name]", "Show linked routes or details for one route."))
    if bot_user and (bot_user.can_view_routes or bot_user.can_manage_allowlist):
        commands.append(("allowlist [route name]", "Show or change the route client IP allowlist."))
    commands.append(("help", "Show this command list."))
    return commands


def _help_command_activity(commands: list[tuple[str, str]]) -> dict[str, Any]:
    command_rows: list[dict[str, Any]] = []
    for command, description in commands:
        command_rows.append(
            {
                "type": "ColumnSet",
                "spacing": "Small",
                "columns": [
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"{command}:",
                                "weight": "Bolder",
                                "wrap": False,
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": description,
                                "wrap": True,
                            }
                        ],
                    },
                ],
            }
        )
    return _command_activity(
        "Available commands",
        "Use these commands in a chat or channel where the relay bot is installed.",
        facts=[
            ("Examples", "register Jira Alerts; info; webhook Jira Alerts"),
            ("Typed-only", "delete <route name>"),
        ],
        sections=[
            {
                "type": "Container",
                "spacing": "Medium",
                "items": command_rows,
            }
        ],
        actions=[
            _submit_command_action("Show conversation info", "info"),
            _submit_command_action("Show help", "help"),
        ],
    )


def _register_route_from_command(
    db: Session,
    captured: dict[str, str],
    route_name: str,
    reference: BotConversationReference | None,
    *,
    bot_user: BotAuthorizedUser | None = None,
) -> CommandResult:
    if not route_name:
        reply_text = "Please include a route name, for example `register Jira Alerts`."
        return CommandResult(
            handled=True,
            command="register",
            reply_text=reply_text,
            severity="warn",
            activity=_command_activity(
                "Route name required",
                "Please include a route name before registering.",
                status="warning",
                facts=[("Example", "register Jira Alerts")],
            ),
        )
    if len(route_name) > 200:
        reply_text = "Route names are limited to 200 characters. Please choose a shorter name."
        return CommandResult(
            handled=True,
            command="register",
            reply_text=reply_text,
            severity="warn",
            activity=_command_activity(
                "Route name too long",
                "Route names are limited to 200 characters. Please choose a shorter name.",
                status="warning",
            ),
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
                status="warning",
            ),
        )
    organization = _default_organization(db)
    effective = _captured_with_reference(captured, reference)
    route = db.scalar(
        select(WebhookRoute).where(
            WebhookRoute.organization_id == organization.id,
            WebhookRoute.name == route_name,
            WebhookRoute.delivery_backend == DELIVERY_BACKEND_BOT,
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
            route_token_hash=lookup_secret_hash(route_token),
            route_token=route_token,
            target_type="bot_conversation",
            target_name=_target_name(effective),
        )
        db.add(route)
    route.is_active = True
    route.delivery_backend = DELIVERY_BACKEND_BOT
    route.bot_service_url = effective["service_url"]
    route.bot_conversation_id = effective["conversation_id"]
    route.target_name = _target_name(effective)
    route.graph_target_kind = _graph_target_kind(effective)
    route.graph_target_id = _graph_target_id(effective)
    route.graph_team_id = effective["graph_team_id"]
    route.graph_team_name = _clip(effective["team_name"], 200)
    route.graph_channel_id = effective["channel_id"] if route.graph_target_kind == "channel" else ""
    if reference is not None:
        route.member_summary = reference.member_summary
        route.member_count = reference.member_count
        route.member_list_json = reference.member_list_json
        route.members_refreshed_at = reference.members_refreshed_at
        route.members_lookup_error = reference.members_lookup_error
    route.bot_target_source = "bot_command"
    route.bot_registered_by_id = effective["graph_user_id"] or effective["from_id"]
    route.bot_registered_at = utcnow()
    try_resolve_route_graph_names(route)
    db.flush()
    reveal_url = _issue_webhook_reveal_url(db, route) if bot_user and bot_user.can_reveal_webhook_urls else ""
    verb = "created" if created else "updated"
    reveal_instruction = (
        "Open the webhook URL button to view and copy the route URL.\n\n"
        if reveal_url
        else "You do not have permission to reveal the route URL from Teams.\n\n"
    )
    return CommandResult(
        handled=True,
        command="register",
        reply_text=(
            f"Route `{route.name}` {verb} for this conversation.\n\n"
            f"{reveal_instruction}"
            "Use `info` to inspect the captured Teams IDs."
        ),
        activity=_route_command_activity(route, verb, reveal_url, effective, bot_user=bot_user),
    )


def _webhook_url_command(db: Session, route_name: str, *, bot_user: BotAuthorizedUser | None = None) -> CommandResult:
    if not route_name:
        reply_text = "Please include a route name, for example `webhook Jira Alerts`."
        return CommandResult(
            handled=True,
            command="webhook",
            reply_text=reply_text,
            severity="warn",
            activity=_command_activity(
                "Route name required",
                "Please include a route name to look up.",
                status="warning",
                facts=[("Example", "webhook Jira Alerts")],
            ),
        )
    if len(route_name) > 200:
        reply_text = "Route names are limited to 200 characters. Please choose a shorter name."
        return CommandResult(
            handled=True,
            command="webhook",
            reply_text=reply_text,
            severity="warn",
            activity=_command_activity(
                "Route name too long",
                "Route names are limited to 200 characters. Please choose a shorter name.",
                status="warning",
            ),
        )
    organization = _default_organization(db)
    route = db.scalar(
        select(WebhookRoute).where(
            WebhookRoute.organization_id == organization.id,
            WebhookRoute.name == route_name,
        )
    )
    if route is None or not route.route_token:
        reply_text = f"No route named `{route_name}` exists yet. Use `register {route_name}` from the target conversation first."
        return CommandResult(
            handled=True,
            command="webhook",
            reply_text=reply_text,
            severity="warn",
            activity=_command_activity(
                "Route not found",
                f"No route named {route_name} exists yet.",
                status="warning",
                facts=[("Create it with", f"register {route_name}")],
            ),
        )
    reveal_url = _issue_webhook_reveal_url(db, route)
    return CommandResult(
        handled=True,
        command="webhook",
        reply_text=f"Webhook URL for `{route.name}` is available through the button in this reply.",
        activity=_webhook_command_activity(route, reveal_url, bot_user=bot_user),
    )


def _set_route_active_command(
    db: Session,
    captured: dict[str, str],
    route_name: str,
    *,
    is_active: bool,
    bot_user: BotAuthorizedUser | None = None,
) -> CommandResult:
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
    reveal_url = _issue_webhook_reveal_url(db, route) if route.route_token and bot_user and bot_user.can_reveal_webhook_urls else ""
    reply_text = f"Route `{route.name}` is {state_text}{verb} for this Teams conversation."
    return CommandResult(
        handled=True,
        command=command,
        reply_text=reply_text,
        activity=_route_status_command_activity(route, verb, captured, reveal_url, bot_user=bot_user),
    )


def _delete_linked_route_command(db: Session, captured: dict[str, str], route_name: str) -> CommandResult:
    if not route_name:
        reply_text = "Please include a route name, for example `delete Jira Alerts`."
        return CommandResult(
            handled=True,
            command="delete",
            reply_text=reply_text,
            severity="warn",
            activity=_command_activity(
                "Route name required",
                "Please include the route name before deleting.",
                status="warning",
                facts=[("Example", "delete Jira Alerts")],
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
    db.execute(delete(WebhookUrlRevealToken).where(WebhookUrlRevealToken.route_id == route_id))
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
            status="inactive",
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
    *,
    bot_user: BotAuthorizedUser | None = None,
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
                    status="warning",
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
        reveal_urls = {
            route.id: _issue_webhook_reveal_url(db, route)
            for route in routes
            if route.route_token and bot_user and bot_user.can_reveal_webhook_urls
        }
        if routes:
            lines.append(f"Linked routes: `{len(routes)}`")
            for route in routes:
                lines.append(f"- `{route.name}`")
                lines.extend(
                    f"  {line}"
                    for line in _route_overview_text(route, captured, reveal_url=reveal_urls.get(route.id, "")).splitlines()
                )
        else:
            lines.append("Linked routes: `none`")
            lines.append("Use `register <route name>` to link a route to this Teams conversation.")
        return CommandResult(
            handled=True,
            command="info",
            reply_text="\n".join(lines),
            activity=_info_overview_command_activity(captured, reference, routes, reveal_urls, bot_user=bot_user),
        )
    reveal_url = (
        _issue_webhook_reveal_url(db, linked_route)
        if linked_route and linked_route.route_token and bot_user and bot_user.can_reveal_webhook_urls
        else ""
    )
    if linked_route and linked_route.route_token:
        lines.append(f"Linked route: `{linked_route.name}`")
        lines.append(f"Route status: `{'active' if linked_route.is_active else 'inactive'}`")
        lines.append(f"Client IP access: `{_client_ip_access_summary(linked_route)}`")
        lines.append(f"Target: `{linked_route.target_name or '-'}`")
        if reveal_url:
            lines.append("Webhook URL: open the button in this reply to view and copy it.")
        else:
            lines.append("Webhook URL: unavailable with your current Teams bot permissions.")
    else:
        lines.append("Linked route: `none`")
    return CommandResult(
        handled=True,
        command="info",
        reply_text="\n".join(lines),
        activity=_info_detail_command_activity(captured, reference, linked_route, reveal_url, bot_user=bot_user),
    )


def _allowlist_command(db: Session, captured: dict[str, str], argument: str) -> CommandResult:
    if not argument:
        return _show_allowlist_command(db, captured, "")
    lowered = argument.lower()
    if lowered == "show":
        return _show_allowlist_command(db, captured, "")
    if lowered.startswith("show "):
        return _show_allowlist_command(db, captured, argument[5:].strip())
    if lowered == CLIENT_IP_ACCESS_PUBLIC or lowered.startswith(f"{CLIENT_IP_ACCESS_PUBLIC} "):
        route_name = argument[len(CLIENT_IP_ACCESS_PUBLIC) :].strip()
        return _set_allowlist_command(db, captured, route_name, CLIENT_IP_ACCESS_PUBLIC, "")
    if lowered == CLIENT_IP_ACCESS_RESTRICTED or lowered.startswith(f"{CLIENT_IP_ACCESS_RESTRICTED} "):
        route_name, allowlist = _parse_restricted_allowlist_argument(
            argument[len(CLIENT_IP_ACCESS_RESTRICTED) :].strip()
        )
        return _set_allowlist_command(db, captured, route_name, CLIENT_IP_ACCESS_RESTRICTED, allowlist)
    return _show_allowlist_command(db, captured, argument)


def _show_allowlist_command(db: Session, captured: dict[str, str], route_name: str) -> CommandResult:
    if len(route_name) > 200:
        return _route_name_too_long_command("allowlist")
    route, error = _resolve_linked_route(db, captured, route_name, "allowlist")
    if error:
        return error
    assert route is not None
    reply_text = "\n".join(
        [
            f"Route `{route.name}` client IP access: `{_client_ip_access_summary(route)}`",
            *_client_ip_allowlist_reply_lines(route),
            "",
            "Use `allowlist public` to make the linked route public.",
            "Use `allowlist restricted 203.0.113.10, 10.0.0.0/24` to restrict a single linked route.",
            "For multiple linked routes, use `allowlist restricted Route Name: 203.0.113.10`.",
        ]
    )
    return CommandResult(
        handled=True,
        command="allowlist",
        reply_text=reply_text,
        activity=_allowlist_command_activity(route, "Client IP allowlist"),
    )


def _set_allowlist_command(
    db: Session,
    captured: dict[str, str],
    route_name: str,
    mode: str,
    allowlist: str,
) -> CommandResult:
    if len(route_name) > 200:
        return _route_name_too_long_command("allowlist")
    route, error = _resolve_linked_route(db, captured, route_name, "allowlist")
    if error:
        return error
    assert route is not None
    previous_mode = route.client_ip_access_mode
    previous_allowlist = route.client_ip_allowlist
    try:
        normalized_allowlist = normalize_client_ip_allowlist(allowlist)
    except ValueError as exc:
        return CommandResult(
            handled=True,
            command="allowlist",
            reply_text=str(exc),
            severity="warn",
            activity=_command_activity(
                "Invalid allowlist",
                str(exc),
                status="warning",
                facts=[("Example", "allowlist restricted 203.0.113.10, 10.0.0.0/24")],
            ),
        )
    if mode == CLIENT_IP_ACCESS_RESTRICTED and not normalized_allowlist:
        return CommandResult(
            handled=True,
            command="allowlist",
            reply_text="Restricted routes require at least one client IP or CIDR range.",
            severity="warn",
            activity=_command_activity(
                "Allowlist required",
                "Restricted routes require at least one client IP or CIDR range.",
                status="warning",
                facts=[("Example", "allowlist restricted 203.0.113.10, 10.0.0.0/24")],
            ),
        )
    route.client_ip_access_mode = mode
    route.client_ip_allowlist = normalized_allowlist if mode == CLIENT_IP_ACCESS_RESTRICTED else ""
    db.flush()
    _record_bot_route_audit(
        db,
        "webhook_route.client_ip_access_updated",
        route,
        captured,
        previous_client_ip_access_mode=previous_mode,
        previous_client_ip_allowlist=previous_allowlist,
    )
    reply_text = "\n".join(
        [
            f"Route `{route.name}` client IP access updated to `{_client_ip_access_summary(route)}`.",
            *_client_ip_allowlist_reply_lines(route),
        ]
    )
    return CommandResult(
        handled=True,
        command="allowlist",
        reply_text=reply_text,
        activity=_allowlist_command_activity(route, "Client IP access updated"),
    )


def _parse_restricted_allowlist_argument(argument: str) -> tuple[str, str]:
    if ":" not in argument:
        return "", argument
    route_name, allowlist = argument.split(":", 1)
    return route_name.strip(), allowlist.strip()


def _allowlist_command_activity(route: WebhookRoute, title: str) -> dict[str, Any]:
    allowlist = route.client_ip_allowlist.strip()
    long_fields = [("Allowed clients", allowlist)] if allowlist else []
    return _command_activity(
        title,
        "Client IP access controls which source addresses may use this route URL.",
        status="success",
        facts=[
            ("Route", route.name),
            ("Mode", route.client_ip_access_mode or CLIENT_IP_ACCESS_PUBLIC),
            ("Allowed clients", str(len(allowlist.splitlines())) if allowlist else "all"),
        ],
        long_fields=long_fields,
    )


def _client_ip_access_summary(route: WebhookRoute) -> str:
    mode = route.client_ip_access_mode or CLIENT_IP_ACCESS_PUBLIC
    if mode == CLIENT_IP_ACCESS_RESTRICTED:
        count = len([entry for entry in route.client_ip_allowlist.splitlines() if entry.strip()])
        return f"restricted ({count} allowed)"
    return "public"


def _client_ip_allowlist_reply_lines(route: WebhookRoute) -> list[str]:
    if (route.client_ip_access_mode or CLIENT_IP_ACCESS_PUBLIC) != CLIENT_IP_ACCESS_RESTRICTED:
        return ["Allowed clients: `all`"]
    entries = [entry.strip() for entry in route.client_ip_allowlist.splitlines() if entry.strip()]
    if not entries:
        return ["Allowed clients: `none`"]
    return ["Allowed clients:", *[f"- `{entry}`" for entry in entries]]


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
            reply_text = "No webhook route is linked to this Teams conversation yet. Use `register <route name>` first."
            title = "No linked route"
            message = "No webhook route is linked to this Teams conversation yet."
        return None, CommandResult(
            handled=True,
            command=command,
            reply_text=reply_text,
            severity="warn",
            activity=_command_activity(
                title,
                message,
                status="warning",
                facts=[("Create it with", "register <route name>")],
            ),
        )
    if route_name:
        return routes[0], None
    if len(routes) == 1:
        return routes[0], None
    names = ", ".join(f"`{route.name}`" for route in routes)
    example = f"{command} {routes[0].name}"
    return None, CommandResult(
        handled=True,
        command=command,
        reply_text=f"Multiple routes are linked to this Teams conversation: {names}. Please include a route name, for example `{example}`.",
        severity="warn",
        activity=_command_activity(
            "Route name required",
            "Multiple routes are linked to this Teams conversation. Please include the route name.",
            status="warning",
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
        activity=_command_activity(
            "Route name too long",
            "Route names are limited to 200 characters. Please choose a shorter name.",
            status="warning",
        ),
    )


def _route_status_command_activity(
    route: WebhookRoute,
    verb: str,
    captured: dict[str, str],
    reveal_url: str,
    *,
    bot_user: BotAuthorizedUser | None = None,
) -> dict[str, Any]:
    return _command_activity(
        f"Route {verb}",
        f"{route.name} is {verb} for this Teams conversation.",
        status="success" if route.is_active else "inactive",
        facts=[
            ("Route", route.name),
            ("Target", route.target_name),
            ("Scope", _scope_for(captured)),
            ("Status", "active" if route.is_active else "inactive"),
        ],
        actions=_route_safe_actions(
            route,
            reveal_url=reveal_url,
            include_status_toggle=bool(bot_user and bot_user.can_manage_route_status),
        ),
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
        "is_group": "true" if reference.scope == "chat" else "",
        "member_summary": reference.member_summary,
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
    settings = get_effective_settings()
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
    if captured.get("member_summary"):
        return _clip(captured["member_summary"], 200)
    if _scope_for(captured) == "chat":
        return "Group chat"
    return _clip(
        captured["user_name"] or captured["graph_user_id"] or captured["from_id"] or captured["conversation_id"] or "Teams conversation",
        200,
    )


def _graph_target_kind(captured: dict[str, str]) -> str:
    if _scope_for(captured) == "chat":
        return "chat"
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
    if kind == "chat":
        return captured["conversation_id"]
    if kind == "user":
        return captured["graph_user_id"] or captured["from_id"]
    return ""


def _normalize_conversation_id(value: str) -> str:
    return value.split(";messageid=", 1)[0] if ";messageid=" in value else value


def _clip(value: str, limit: int) -> str:
    return value[:limit]


def _issue_webhook_reveal_url(db: Session, route: WebhookRoute) -> str:
    if not route.route_token:
        return ""
    settings = get_effective_settings()
    now = utcnow()
    db.execute(delete(WebhookUrlRevealToken).where(WebhookUrlRevealToken.expires_at <= now))
    token = issue_plain_secret(24)
    db.add(
        WebhookUrlRevealToken(
            organization_id=route.organization_id,
            route_id=route.id,
            token_hash=lookup_secret_hash(token),
            expires_at=now + timedelta(hours=settings.webhook_url_reveal_ttl_hours),
        )
    )
    query = urllib.parse.urlencode({"token": token})
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


def _bool_string(value: Any) -> str:
    return "true" if value is True else ""


def _is_group_conversation(captured: dict[str, str]) -> bool:
    return captured.get("is_group") == "true" or captured.get("conversation_type", "").lower() in {"groupchat", "group", "chat"}
