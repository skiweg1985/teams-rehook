from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BotConversationReference, WebhookRoute
from app.services.graph_targets import (
    GraphConfigError,
    GraphRequestError,
    get_channel_target,
    get_team_target,
    get_user_target,
)


@dataclass(frozen=True)
class GraphNameRefreshResult:
    routes_checked: int = 0
    routes_updated: int = 0
    references_checked: int = 0
    references_updated: int = 0
    error: str = ""


def resolve_reference_graph_names(reference: BotConversationReference, *, force: bool = False) -> bool:
    changed = False
    if reference.graph_team_id and (force or not reference.team_name):
        team_name = _safe_team_name(reference.graph_team_id)
        if team_name and reference.team_name != team_name:
            reference.team_name = team_name
            changed = True
    if reference.graph_team_id and reference.channel_id and (force or not reference.channel_name):
        channel_name = _safe_channel_name(reference.graph_team_id, reference.channel_id)
        if channel_name and reference.channel_name != channel_name:
            reference.channel_name = channel_name
            changed = True
    if reference.graph_user_id and (force or not reference.user_name):
        user_name = _safe_user_name(reference.graph_user_id)
        if user_name and reference.user_name != user_name:
            reference.user_name = user_name
            changed = True
    return changed


def try_resolve_reference_graph_names(reference: BotConversationReference, *, force: bool = False) -> bool:
    try:
        return resolve_reference_graph_names(reference, force=force)
    except (GraphConfigError, GraphRequestError):
        return False


def resolve_route_graph_names(route: WebhookRoute, *, force: bool = False) -> bool:
    changed = False
    target_name = route.target_name.strip()
    if route.graph_team_id and (force or not route.graph_team_name):
        team_name = _safe_team_name(route.graph_team_id)
        if team_name and route.graph_team_name != team_name:
            route.graph_team_name = team_name
            changed = True
    channel_name = ""
    should_resolve_channel = force or (route.graph_target_kind == "channel" and (not route.graph_team_name or " / " not in target_name))
    if route.graph_team_id and route.graph_channel_id and should_resolve_channel:
        channel_name = _safe_channel_name(route.graph_team_id, route.graph_channel_id)
    if route.graph_target_kind == "channel" and route.graph_team_name and channel_name:
        target_name = f"{route.graph_team_name} / {channel_name}"
        if route.target_name != target_name:
            route.target_name = target_name
            changed = True
    elif route.graph_target_kind == "team" and route.graph_team_name and route.target_name != route.graph_team_name:
        route.target_name = route.graph_team_name
        changed = True
    elif route.graph_target_kind == "user" and route.graph_target_id and (force or not route.target_name):
        user_name = _safe_user_name(route.graph_target_id)
        if user_name and route.target_name != user_name:
            route.target_name = user_name
            changed = True
    return changed


def try_resolve_route_graph_names(route: WebhookRoute, *, force: bool = False) -> bool:
    try:
        return resolve_route_graph_names(route, force=force)
    except (GraphConfigError, GraphRequestError):
        return False


def refresh_graph_names(db: Session, *, organization_id: str | None = None) -> GraphNameRefreshResult:
    route_statement = select(WebhookRoute)
    if organization_id:
        route_statement = route_statement.where(WebhookRoute.organization_id == organization_id)
    routes = db.scalars(route_statement).all()
    references = db.scalars(select(BotConversationReference)).all()
    routes_updated = 0
    references_updated = 0
    try:
        for reference in references:
            if resolve_reference_graph_names(reference, force=True):
                references_updated += 1
        for route in routes:
            if resolve_route_graph_names(route, force=True):
                routes_updated += 1
    except (GraphConfigError, GraphRequestError) as exc:
        return GraphNameRefreshResult(
            routes_checked=len(routes),
            routes_updated=routes_updated,
            references_checked=len(references),
            references_updated=references_updated,
            error=str(exc),
        )
    if routes_updated or references_updated:
        db.flush()
    return GraphNameRefreshResult(
        routes_checked=len(routes),
        routes_updated=routes_updated,
        references_checked=len(references),
        references_updated=references_updated,
    )


def _safe_team_name(team_id: str) -> str:
    target = get_team_target(team_id)
    return target.display_name if target else ""


def _safe_channel_name(team_id: str, channel_id: str) -> str:
    target = get_channel_target(team_id, channel_id)
    return target.display_name if target else ""


def _safe_user_name(user_id: str) -> str:
    target = get_user_target(user_id)
    return target.display_name if target else ""
