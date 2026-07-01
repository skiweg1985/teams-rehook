from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.settings_overrides import get_effective_settings
from app.database import get_db
from app.deps import require_admin
from app.models import User
from app.schemas import TeamsGroupMemberCountOut, TeamsGroupMemberOut, TeamsGroupMemberPageOut, TeamsTargetSearchOut
from app.services.graph_delegated_lookup import GraphDelegatedLookupError, list_service_user_chats
from app.services.graph_targets import GraphConfigError, GraphGroupMember, GraphRequestError, GraphTarget, count_group_transitive_user_members, list_group_transitive_members, list_team_channels, search_targets

router = APIRouter(tags=["teams-targets"])


@router.get("/teams-targets/search", response_model=list[TeamsTargetSearchOut])
def search_teams_targets(
    kind: Literal["user", "team", "group"] = Query(...),
    q: str = Query(default="", min_length=0, max_length=120),
    admin: User = Depends(require_admin),
):
    _ = admin
    _ensure_graph_lookup_enabled()
    return [_target_out(target) for target in _run_graph_search(lambda: search_targets(kind, q))]


@router.get("/teams-targets/teams/{team_id}/channels", response_model=list[TeamsTargetSearchOut])
def search_team_channels(
    team_id: str,
    q: str = Query(default="", max_length=120),
    admin: User = Depends(require_admin),
):
    _ = admin
    _ensure_graph_lookup_enabled()
    return [_target_out(target) for target in _run_graph_search(lambda: list_team_channels(team_id, q))]


@router.get("/teams-targets/groups/{group_id}/members", response_model=TeamsGroupMemberPageOut)
def list_group_members(
    group_id: str,
    q: str = Query(default="", max_length=120),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    admin: User = Depends(require_admin),
):
    _ = admin
    _ensure_graph_lookup_enabled()
    page = _run_graph_search(lambda: list_group_transitive_members(group_id, q, offset=offset, limit=limit))
    return TeamsGroupMemberPageOut(
        items=[_group_member_out(member) for member in page.items],
        offset=page.offset,
        limit=page.limit,
        has_more=page.has_more,
    )


@router.get("/teams-targets/groups/{group_id}/members/count", response_model=TeamsGroupMemberCountOut)
def count_group_members(
    group_id: str,
    admin: User = Depends(require_admin),
):
    _ = admin
    _ensure_graph_lookup_enabled()
    return TeamsGroupMemberCountOut(count=_run_graph_search(lambda: count_group_transitive_user_members(group_id)))


@router.get("/teams-targets/chats", response_model=list[TeamsTargetSearchOut])
def search_service_user_chats(
    q: str = Query(default="", max_length=120),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ensure_graph_lookup_enabled()
    try:
        chats = list_service_user_chats(db, organization_id=admin.organization_id, query=q)
    except GraphDelegatedLookupError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [
        TeamsTargetSearchOut(
            kind="chat",
            id=chat.id,
            display_name=chat.display_name,
            subtitle=chat.subtitle,
        )
        for chat in chats
    ]


def _ensure_graph_lookup_enabled() -> None:
    if not get_effective_settings().graph_lookup_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Microsoft Graph lookup is disabled")


def _run_graph_search(search):
    try:
        return search()
    except GraphConfigError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except GraphRequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


def _target_out(target: GraphTarget) -> TeamsTargetSearchOut:
    return TeamsTargetSearchOut(
        kind=target.kind,
        id=target.id,
        display_name=target.display_name,
        subtitle=target.subtitle,
        team_id=target.team_id,
        team_name=target.team_name,
        channel_id=target.channel_id,
        mail=target.mail,
        security_enabled=target.security_enabled,
        group_types=list(target.group_types),
    )


def _group_member_out(member: GraphGroupMember) -> TeamsGroupMemberOut:
    return TeamsGroupMemberOut(
        id=member.id,
        display_name=member.display_name,
        user_principal_name=member.user_principal_name,
        mail=member.mail,
    )
