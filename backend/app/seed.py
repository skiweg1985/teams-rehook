from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.settings_overrides import load_overrides
from app.database import Base, engine
from app.models import BotActivityEvent, BotConversationReference, Organization, User, WebhookRoute
from app.security import hash_secret
from app.services.log_retention import cleanup_log_events


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_additive_schema()
    settings = get_settings()
    with Session(engine) as db:
        _backfill_bot_reference_metadata(db)
        _backfill_webhook_route_targets(db)
        cleanup_log_events(db, force=True)
        load_overrides(db)

        org = db.scalar(select(Organization).where(Organization.slug == settings.default_org_slug))
        if not org:
            org = Organization(slug=settings.default_org_slug, name=settings.default_org_name)
            db.add(org)
            db.flush()

        bootstrap_email = str(settings.bootstrap_admin_email or "").strip().lower()
        admin = db.scalar(select(User).where(User.organization_id == org.id, User.email == bootstrap_email))
        if not admin:
            admin = User(
                organization_id=org.id,
                email=bootstrap_email,
                display_name=settings.bootstrap_admin_display_name,
                password_hash=hash_secret(settings.bootstrap_admin_password),
                is_admin=True,
                is_active=True,
            )
            db.add(admin)
            db.flush()

        db.commit()


def _backfill_bot_reference_metadata(db: Session) -> None:
    events = db.scalars(select(BotActivityEvent).order_by(BotActivityEvent.created_at.asc())).all()
    changed = False
    for event in events:
        raw = _loads_json(event.raw_activity_json)
        captured = _extract_bot_activity(event, raw)
        if not captured["conversation_id"] or not captured["service_url"]:
            continue
        reference = db.scalar(
            select(BotConversationReference).where(
                BotConversationReference.conversation_id == captured["conversation_id"]
            )
        )
        raw_reference = None
        if captured["raw_conversation_id"] and captured["raw_conversation_id"] != captured["conversation_id"]:
            raw_reference = db.scalar(
                select(BotConversationReference).where(
                    BotConversationReference.conversation_id == captured["raw_conversation_id"]
                )
            )
        if reference is None and raw_reference is not None:
            raw_reference.conversation_id = captured["conversation_id"]
            reference = raw_reference
        elif reference is not None and raw_reference is not None and raw_reference.id != reference.id:
            db.delete(raw_reference)
        if reference is None:
            continue
        _apply_reference_metadata(reference, captured, event.activity_type)
        changed = True
    if changed:
        db.commit()


def _backfill_webhook_route_targets(db: Session) -> None:
    references = {
        reference.conversation_id: reference
        for reference in db.scalars(select(BotConversationReference)).all()
    }
    changed = False
    routes = db.scalars(
        select(WebhookRoute).where(WebhookRoute.bot_target_source.in_(["bot_command", "conversation_reference"]))
    ).all()
    for route in routes:
        reference = references.get(route.bot_conversation_id)
        if reference is None:
            continue
        route.target_name = _reference_target_name(reference)
        route.graph_target_kind = _reference_graph_kind(reference)
        route.graph_target_id = _reference_graph_target_id(reference)
        route.graph_team_id = reference.graph_team_id
        route.graph_team_name = reference.team_name
        route.graph_channel_id = reference.channel_id if route.graph_target_kind == "channel" else ""
        if not route.bot_registered_by_id:
            route.bot_registered_by_id = reference.graph_user_id or reference.user_id
        changed = True
    if changed:
        db.commit()


def _apply_reference_metadata(
    reference: BotConversationReference,
    captured: dict[str, str],
    activity_type: str,
) -> None:
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
    reference.raw_activity_type = activity_type


def _reference_target_name(reference: BotConversationReference) -> str:
    if reference.team_name and reference.channel_name:
        return _clip(f"{reference.team_name} / {reference.channel_name}", 200)
    if reference.channel_name:
        return _clip(reference.channel_name, 200)
    if reference.team_name:
        return _clip(reference.team_name, 200)
    return _clip(reference.user_name or reference.graph_user_id or reference.user_id or reference.conversation_id, 200)


def _reference_graph_kind(reference: BotConversationReference) -> str:
    if reference.scope == "channel" or reference.channel_id:
        return "channel"
    if reference.scope == "team" or reference.graph_team_id:
        return "team"
    return "user"


def _reference_graph_target_id(reference: BotConversationReference) -> str:
    kind = _reference_graph_kind(reference)
    if kind == "channel":
        return reference.channel_id
    if kind == "team":
        return reference.graph_team_id
    return reference.graph_user_id or reference.user_id


def _extract_bot_activity(event: BotActivityEvent, raw: dict[str, Any]) -> dict[str, str]:
    channel_data = _dict(raw.get("channelData"))
    conversation = _dict(raw.get("conversation"))
    sender = _dict(raw.get("from"))
    tenant = _dict(channel_data.get("tenant"))
    team = _dict(channel_data.get("team"))
    channel = _dict(channel_data.get("channel"))
    settings = _dict(channel_data.get("settings"))
    selected_channel = _dict(settings.get("selectedChannel"))
    raw_conversation_id = _string(conversation.get("id")) or event.conversation_id
    conversation_id = _normalize_conversation_id(raw_conversation_id)
    conversation_type = _string(conversation.get("conversationType")).lower()
    channel_id = (
        _string(channel.get("id"))
        or _string(channel_data.get("teamsChannelId"))
        or _string(selected_channel.get("id"))
        or (conversation_id if conversation_type == "channel" else "")
    )
    return {
        "service_url": _string(raw.get("serviceUrl")) or event.service_url,
        "conversation_id": conversation_id,
        "raw_conversation_id": raw_conversation_id,
        "tenant_id": _string(tenant.get("id")) or _string(conversation.get("tenantId")) or event.tenant_id,
        "team_id": _string(team.get("id")) or _string(channel_data.get("teamsTeamId")) or event.team_id,
        "graph_team_id": _string(team.get("aadGroupId")) or event.graph_team_id,
        "channel_id": channel_id or event.channel_id,
        "conversation_type": _clip(conversation_type or event.conversation_type, 40),
        "team_name": _clip(_string(team.get("name")) or event.team_name, 200),
        "channel_name": _clip(
            _string(channel.get("name"))
            or _string(selected_channel.get("name"))
            or _string(conversation.get("name"))
            or event.channel_name,
            200,
        ),
        "from_id": _string(sender.get("id")) or event.from_id,
        "user_name": _clip(_string(sender.get("name")) or event.user_name, 200),
        "graph_user_id": _string(sender.get("aadObjectId")) or event.graph_user_id,
    }


def _scope_for(captured: dict[str, str]) -> str:
    if captured["conversation_type"] == "personal":
        return "user"
    if captured["team_id"] and captured["channel_id"]:
        return "channel"
    if captured["team_id"]:
        return "team"
    return "user"


def _loads_json(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_conversation_id(value: str) -> str:
    return value.split(";messageid=", 1)[0] if ";messageid=" in value else value


def _clip(value: str, limit: int) -> str:
    return value[:limit]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _ensure_additive_schema() -> None:
    table_columns = {
        "webhook_routes": {
            "route_token": "TEXT DEFAULT '' NOT NULL",
            "delivery_backend": "VARCHAR(32) DEFAULT 'bot_framework' NOT NULL",
            "graph_target_kind": "VARCHAR(32) DEFAULT '' NOT NULL",
            "graph_target_id": "TEXT DEFAULT '' NOT NULL",
            "graph_team_id": "TEXT DEFAULT '' NOT NULL",
            "graph_team_name": "VARCHAR(200) DEFAULT '' NOT NULL",
            "graph_channel_id": "TEXT DEFAULT '' NOT NULL",
            "bot_target_source": "VARCHAR(40) DEFAULT '' NOT NULL",
            "bot_registered_by_id": "TEXT DEFAULT '' NOT NULL",
            "bot_registered_at": "TIMESTAMP NULL",
        },
        "bot_activity_events": {
            "graph_team_id": "TEXT DEFAULT '' NOT NULL",
            "conversation_type": "VARCHAR(40) DEFAULT '' NOT NULL",
            "team_name": "VARCHAR(200) DEFAULT '' NOT NULL",
            "channel_name": "VARCHAR(200) DEFAULT '' NOT NULL",
            "user_name": "VARCHAR(200) DEFAULT '' NOT NULL",
            "graph_user_id": "TEXT DEFAULT '' NOT NULL",
        },
        "bot_conversation_references": {
            "graph_team_id": "TEXT DEFAULT '' NOT NULL",
            "conversation_type": "VARCHAR(40) DEFAULT '' NOT NULL",
            "team_name": "VARCHAR(200) DEFAULT '' NOT NULL",
            "channel_name": "VARCHAR(200) DEFAULT '' NOT NULL",
            "user_name": "VARCHAR(200) DEFAULT '' NOT NULL",
            "graph_user_id": "TEXT DEFAULT '' NOT NULL",
        },
    }
    with engine.begin() as connection:
        dialect = engine.dialect.name
        for table_name, columns_to_add in table_columns.items():
            if dialect == "sqlite":
                existing_columns = {
                    row[1] for row in connection.execute(text(f"PRAGMA table_info({table_name})")).all()
                }
            else:
                existing_columns = {
                    row[0]
                    for row in connection.execute(
                        text(
                            """
                            SELECT column_name
                            FROM information_schema.columns
                            WHERE table_name = :table_name
                            """
                        ),
                        {"table_name": table_name},
                    ).all()
                }
            for column_name, column_type in columns_to_add.items():
                if column_name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
