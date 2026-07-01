from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BotAccessRole

BOT_PERMISSION_FIELDS = (
    "can_view_routes",
    "can_reveal_webhook_urls",
    "can_manage_route_status",
    "can_delete_routes",
    "can_manage_allowlist",
    "can_create_private_chat_routes",
    "can_create_channel_routes",
)

ROUTE_VIEWER_SYSTEM_KEY = "route_viewer"
ROUTE_OPERATOR_SYSTEM_KEY = "route_operator"

BOT_ACCESS_SYSTEM_ROLES = {
    ROUTE_VIEWER_SYSTEM_KEY: {
        "name": "Route Viewer",
        "description": "Can inspect routes and reveal webhook URLs.",
        "permissions": {
            "can_view_routes": True,
            "can_reveal_webhook_urls": True,
            "can_manage_route_status": False,
            "can_delete_routes": False,
            "can_manage_allowlist": False,
            "can_create_private_chat_routes": False,
            "can_create_channel_routes": False,
        },
    },
    ROUTE_OPERATOR_SYSTEM_KEY: {
        "name": "Route Operator",
        "description": "Can fully operate bot-managed webhook routes.",
        "permissions": {field: True for field in BOT_PERMISSION_FIELDS},
    },
}


def ensure_bot_access_system_roles(
    db: Session,
    organization_id: str,
    *,
    actor_id: str | None = None,
) -> dict[str, BotAccessRole]:
    existing = {
        role.system_key: role
        for role in db.scalars(
            select(BotAccessRole).where(
                BotAccessRole.organization_id == organization_id,
                BotAccessRole.system_key.in_(list(BOT_ACCESS_SYSTEM_ROLES)),
            )
        ).all()
        if role.system_key
    }
    changed = False
    for system_key, definition in BOT_ACCESS_SYSTEM_ROLES.items():
        role = existing.get(system_key)
        if role is None:
            role = BotAccessRole(
                organization_id=organization_id,
                name=str(definition["name"]),
                description=str(definition["description"]),
                is_system=True,
                system_key=system_key,
                created_by_id=actor_id,
                updated_by_id=actor_id,
                **definition["permissions"],
            )
            db.add(role)
            db.flush()
            existing[system_key] = role
            changed = True
        elif not role.is_system:
            role.is_system = True
            changed = True
    if changed:
        db.flush()
    return existing


def role_permissions(role: BotAccessRole | None) -> dict[str, bool]:
    if role is None:
        return {}
    return {field: bool(getattr(role, field)) for field in BOT_PERMISSION_FIELDS}

