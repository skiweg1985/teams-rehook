from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings, is_placeholder_session_secret, is_placeholder_settings_enc_key
from app.core.settings_overrides import load_overrides
from app.database import Base, engine
from app.models import AppSetting, BotActivityEvent, BotAuthorizedGroup, BotAuthorizedUser, BotConversationReference, Organization, User, WebhookRoute
from app.security import issue_plain_secret
from app.services.bot_access_roles import (
    ROUTE_OPERATOR_SYSTEM_KEY,
    ROUTE_VIEWER_SYSTEM_KEY,
    ensure_bot_access_system_roles,
    role_permissions,
)
from app.services.log_retention import cleanup_log_events

INSTANCE_SESSION_SECRET_KEY = "__instance_session_secret"
INSTANCE_SETTINGS_ENC_KEY = "__instance_settings_enc_key"


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_additive_schema()
    _ensure_obsolete_webhook_route_columns_removed()
    _ensure_webhook_route_name_backend_uniqueness()
    settings = get_settings()
    with Session(engine) as db:
        _ensure_instance_session_secret(db)
        _ensure_instance_settings_enc_key(db)
        _backfill_bot_reference_metadata(db)
        _backfill_webhook_route_targets(db)
        cleanup_log_events(db, force=True)
        load_overrides(db)

        org = db.scalar(select(Organization).where(Organization.slug == settings.default_org_slug))
        if not org:
            org = Organization(slug=settings.default_org_slug, name=settings.default_org_name)
            db.add(org)
            db.flush()

        _ensure_bot_access_roles_for_organizations(db)
        _backfill_bot_access_role_assignments(db)
        db.commit()


def _ensure_instance_session_secret(db: Session) -> str:
    settings = get_settings()
    if settings.has_configured_session_secret():
        if is_placeholder_session_secret(settings.session_secret):
            raise RuntimeError("SESSION_SECRET must not use a placeholder value")
        return settings.session_secret

    row = db.get(AppSetting, INSTANCE_SESSION_SECRET_KEY)
    if row is None:
        row = AppSetting(key=INSTANCE_SESSION_SECRET_KEY, value=issue_plain_secret(48), is_secret=True)
        db.add(row)
        db.flush()

    settings.use_generated_session_secret(row.value)
    return row.value


def _ensure_instance_settings_enc_key(db: Session) -> str:
    settings = get_settings()
    if settings.has_configured_settings_enc_key():
        if is_placeholder_settings_enc_key(settings.settings_enc_key):
            raise RuntimeError("SETTINGS_ENC_KEY must not use a placeholder value")
        return settings.settings_enc_key

    row = db.get(AppSetting, INSTANCE_SETTINGS_ENC_KEY)
    if row is None:
        row = AppSetting(key=INSTANCE_SETTINGS_ENC_KEY, value=issue_plain_secret(48), is_secret=True)
        db.add(row)
        db.flush()

    settings.use_generated_settings_enc_key(row.value)
    return row.value


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
        route.member_summary = reference.member_summary
        route.member_count = reference.member_count
        route.member_list_json = reference.member_list_json
        route.members_refreshed_at = reference.members_refreshed_at
        route.members_lookup_error = reference.members_lookup_error
        if not route.bot_registered_by_id:
            route.bot_registered_by_id = reference.graph_user_id or reference.user_id
        changed = True
    if changed:
        db.commit()


def _ensure_bot_access_roles_for_organizations(db: Session) -> None:
    for organization in db.scalars(select(Organization)).all():
        ensure_bot_access_system_roles(db, organization.id)


def _backfill_bot_access_role_assignments(db: Session) -> None:
    changed = False
    for organization in db.scalars(select(Organization)).all():
        roles = ensure_bot_access_system_roles(db, organization.id)
        viewer = roles[ROUTE_VIEWER_SYSTEM_KEY]
        operator = roles[ROUTE_OPERATOR_SYSTEM_KEY]
        grants = [
            *db.scalars(
                select(BotAuthorizedUser).where(
                    BotAuthorizedUser.organization_id == organization.id,
                    BotAuthorizedUser.role_id.is_(None),
                )
            ).all(),
            *db.scalars(
                select(BotAuthorizedGroup).where(
                    BotAuthorizedGroup.organization_id == organization.id,
                    BotAuthorizedGroup.role_id.is_(None),
                )
            ).all(),
        ]
        for grant in grants:
            if grant.role == "custom":
                continue
            permissions = {field: bool(getattr(grant, field)) for field in role_permissions(operator)}
            if grant.role in {"viewer", "route_viewer"} and permissions == role_permissions(viewer):
                grant.role_id = viewer.id
                grant.role = viewer.system_key or "route_viewer"
                changed = True
            elif grant.role in {"operator", "route_operator", "route_manager"} and permissions == role_permissions(operator):
                grant.role_id = operator.id
                grant.role = operator.system_key or "route_operator"
                changed = True
            elif grant.role in {"viewer", "operator", "route_manager"}:
                grant.role = "custom"
                changed = True
    if changed:
        db.flush()


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
    if reference.member_summary:
        return _clip(reference.member_summary, 200)
    if reference.scope == "chat" or reference.conversation_type.lower() == "groupchat":
        return "Group chat"
    return _clip(reference.user_name or reference.graph_user_id or reference.user_id or reference.conversation_id, 200)


def _reference_graph_kind(reference: BotConversationReference) -> str:
    if reference.scope == "chat" or reference.conversation_type.lower() == "groupchat":
        return "chat"
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
    if kind == "chat":
        return reference.conversation_id
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
        "is_group": _bool_string(conversation.get("isGroup")),
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
    if _is_group_conversation(captured):
        return "chat"
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


def _bool_string(value: Any) -> str:
    return "true" if value is True else ""


def _is_group_conversation(captured: dict[str, str]) -> bool:
    return captured.get("is_group") == "true" or captured.get("conversation_type", "").lower() in {"groupchat", "group", "chat"}


def _ensure_additive_schema() -> None:
    table_columns = {
        "webhook_routes": {
            "route_token": "TEXT DEFAULT '' NOT NULL",
            "delivery_backend": "VARCHAR(32) DEFAULT 'bot_framework' NOT NULL",
            "client_ip_access_mode": "VARCHAR(32) DEFAULT 'public' NOT NULL",
            "client_ip_allowlist": "TEXT DEFAULT '' NOT NULL",
            "graph_target_kind": "VARCHAR(32) DEFAULT '' NOT NULL",
            "graph_target_id": "TEXT DEFAULT '' NOT NULL",
            "graph_team_id": "TEXT DEFAULT '' NOT NULL",
            "graph_team_name": "VARCHAR(200) DEFAULT '' NOT NULL",
            "graph_channel_id": "TEXT DEFAULT '' NOT NULL",
            "graph_user_id": "TEXT DEFAULT '' NOT NULL",
            "graph_user_display_name": "VARCHAR(255) DEFAULT '' NOT NULL",
            "graph_user_principal_name": "VARCHAR(255) DEFAULT '' NOT NULL",
            "member_summary": "VARCHAR(500) DEFAULT '' NOT NULL",
            "member_count": "INTEGER DEFAULT 0 NOT NULL",
            "member_list_json": "TEXT DEFAULT '[]' NOT NULL",
            "members_refreshed_at": "TIMESTAMP NULL",
            "members_lookup_error": "TEXT DEFAULT '' NOT NULL",
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
            "auth_status": "VARCHAR(32) DEFAULT 'unknown' NOT NULL",
            "auth_issuer": "TEXT DEFAULT '' NOT NULL",
            "auth_audience": "TEXT DEFAULT '' NOT NULL",
            "auth_service_url": "TEXT DEFAULT '' NOT NULL",
            "auth_service_url_matched": "BOOLEAN DEFAULT FALSE NOT NULL",
            "auth_validated_at": "TIMESTAMP NULL",
            "bot_authorization_status": "VARCHAR(40) DEFAULT 'not_applicable' NOT NULL",
            "bot_authorized_user_id": "TEXT DEFAULT '' NOT NULL",
            "bot_authorization_reason": "TEXT DEFAULT '' NOT NULL",
        },
        "bot_conversation_references": {
            "graph_team_id": "TEXT DEFAULT '' NOT NULL",
            "conversation_type": "VARCHAR(40) DEFAULT '' NOT NULL",
            "team_name": "VARCHAR(200) DEFAULT '' NOT NULL",
            "channel_name": "VARCHAR(200) DEFAULT '' NOT NULL",
            "user_name": "VARCHAR(200) DEFAULT '' NOT NULL",
            "graph_user_id": "TEXT DEFAULT '' NOT NULL",
            "member_summary": "VARCHAR(500) DEFAULT '' NOT NULL",
            "member_count": "INTEGER DEFAULT 0 NOT NULL",
            "member_list_json": "TEXT DEFAULT '[]' NOT NULL",
            "members_refreshed_at": "TIMESTAMP NULL",
            "members_lookup_error": "TEXT DEFAULT '' NOT NULL",
        },
        "bot_authorized_users": {
            "role_id": "VARCHAR(36) NULL",
        },
        "bot_authorized_groups": {
            "role_id": "VARCHAR(36) NULL",
        },
        "webhook_delivery_events": {
            "idempotency_key": "VARCHAR(120) NULL",
        },
        "webhook_abuse_buckets": {
            "last_client_host": "TEXT DEFAULT '' NOT NULL",
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
        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ix_webhook_delivery_events_route_id_idempotency_key_unique
                ON webhook_delivery_events (route_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL
                """
            )
        )


def _ensure_obsolete_webhook_route_columns_removed() -> None:
    with engine.begin() as connection:
        dialect = engine.dialect.name
        if dialect == "postgresql":
            connection.execute(text("ALTER TABLE webhook_routes DROP COLUMN IF EXISTS source_system"))
        elif dialect == "sqlite":
            columns = {row[1] for row in connection.execute(text("PRAGMA table_info(webhook_routes)")).all()}
            if "source_system" in columns:
                connection.execute(text("ALTER TABLE webhook_routes DROP COLUMN source_system"))


def _ensure_webhook_route_name_backend_uniqueness() -> None:
    with engine.begin() as connection:
        dialect = engine.dialect.name
        connection.execute(
            text(
                """
                UPDATE webhook_routes
                SET delivery_backend = 'bot_framework'
                WHERE delivery_backend IS NULL OR trim(delivery_backend) = ''
                """
            )
        )
        if dialect == "postgresql":
            old_constraint = connection.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.table_constraints
                    WHERE table_name = 'webhook_routes'
                      AND constraint_name = 'uq_webhook_routes_org_name'
                    """
                )
            ).first()
            if old_constraint:
                connection.execute(text("ALTER TABLE webhook_routes DROP CONSTRAINT uq_webhook_routes_org_name"))
            new_constraint = connection.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.table_constraints
                    WHERE table_name = 'webhook_routes'
                      AND constraint_name = 'uq_webhook_routes_org_name_backend'
                    """
                )
            ).first()
            if not new_constraint:
                connection.execute(
                    text(
                        """
                        ALTER TABLE webhook_routes
                        ADD CONSTRAINT uq_webhook_routes_org_name_backend
                        UNIQUE (organization_id, name, delivery_backend)
                        """
                    )
                )
        elif dialect == "sqlite":
            if _sqlite_has_unique_webhook_route_index(connection, ["organization_id", "name"]):
                _sqlite_rebuild_webhook_routes_table(connection)
            _sqlite_ensure_webhook_route_indexes(connection)


def _sqlite_has_unique_webhook_route_index(connection, columns: list[str]) -> bool:
    for row in connection.execute(text("PRAGMA index_list(webhook_routes)")).all():
        index_name = row[1]
        is_unique = bool(row[2])
        if not is_unique:
            continue
        index_columns = [
            column_row[2]
            for column_row in connection.execute(
                text(f"PRAGMA index_info({_sqlite_quote_literal(index_name)})")
            ).all()
        ]
        if index_columns == columns:
            return True
    return False


def _sqlite_rebuild_webhook_routes_table(connection) -> None:
    existing_columns = {row[1] for row in connection.execute(text("PRAGMA table_info(webhook_routes)")).all()}
    columns = [
        "id",
        "organization_id",
        "created_by_id",
        "name",
        "is_active",
        "route_token_hash",
        "route_token",
        "delivery_backend",
        "client_ip_access_mode",
        "client_ip_allowlist",
        "target_type",
        "target_name",
        "bot_service_url",
        "bot_conversation_id",
        "graph_target_kind",
        "graph_target_id",
        "graph_team_id",
        "graph_team_name",
        "graph_channel_id",
        "graph_user_id",
        "graph_user_display_name",
        "graph_user_principal_name",
        "bot_target_source",
        "bot_registered_by_id",
        "bot_registered_at",
        "last_delivery_status",
        "last_delivery_at",
        "created_at",
        "updated_at",
    ]
    column_list = ", ".join(columns)
    select_expressions = ", ".join(_sqlite_rebuild_select_expression(column, existing_columns) for column in columns)
    connection.execute(text("DROP TABLE IF EXISTS webhook_routes_rebuild"))
    connection.execute(
        text(
            """
            CREATE TABLE webhook_routes_rebuild (
                id VARCHAR(36) NOT NULL,
                organization_id VARCHAR NOT NULL,
                created_by_id VARCHAR,
                name VARCHAR(200) NOT NULL,
                is_active BOOLEAN NOT NULL,
                route_token_hash VARCHAR(64) NOT NULL,
                route_token TEXT NOT NULL,
                delivery_backend VARCHAR(32) NOT NULL,
                client_ip_access_mode VARCHAR(32) DEFAULT 'public' NOT NULL,
                client_ip_allowlist TEXT DEFAULT '' NOT NULL,
                target_type VARCHAR(32) NOT NULL,
                target_name VARCHAR(200) NOT NULL,
                bot_service_url TEXT NOT NULL,
                bot_conversation_id TEXT NOT NULL,
                graph_target_kind VARCHAR(32) NOT NULL,
                graph_target_id TEXT NOT NULL,
                graph_team_id TEXT NOT NULL,
                graph_team_name VARCHAR(200) NOT NULL,
                graph_channel_id TEXT NOT NULL,
                graph_user_id TEXT NOT NULL,
                graph_user_display_name VARCHAR(255) NOT NULL,
                graph_user_principal_name VARCHAR(255) NOT NULL,
                bot_target_source VARCHAR(40) NOT NULL,
                bot_registered_by_id TEXT NOT NULL,
                bot_registered_at DATETIME,
                last_delivery_status VARCHAR(32),
                last_delivery_at DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                FOREIGN KEY(organization_id) REFERENCES organizations (id),
                FOREIGN KEY(created_by_id) REFERENCES users (id)
            )
            """
        )
    )
    connection.execute(
        text(
            f"""
            INSERT INTO webhook_routes_rebuild ({column_list})
            SELECT {select_expressions}
            FROM webhook_routes
            """
        )
    )
    connection.execute(text("DROP TABLE webhook_routes"))
    connection.execute(text("ALTER TABLE webhook_routes_rebuild RENAME TO webhook_routes"))


def _sqlite_rebuild_select_expression(column: str, existing_columns: set[str]) -> str:
    if column in existing_columns:
        return column
    if column == "client_ip_access_mode":
        return "'public' AS client_ip_access_mode"
    if column == "client_ip_allowlist":
        return "'' AS client_ip_allowlist"
    return f"NULL AS {column}"


def _sqlite_ensure_webhook_route_indexes(connection) -> None:
    connection.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_webhook_routes_org_name_backend
            ON webhook_routes (organization_id, name, delivery_backend)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ix_webhook_routes_route_token_hash
            ON webhook_routes (route_token_hash)
            """
        )
    )
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_webhook_routes_organization_id ON webhook_routes (organization_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_webhook_routes_created_by_id ON webhook_routes (created_by_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_webhook_routes_is_active ON webhook_routes (is_active)"))


def _sqlite_quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
