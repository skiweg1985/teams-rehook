from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.settings_overrides import get_effective_settings
from app.database import get_db
from app.deps import require_admin
from app.models import User
from app.schemas import TeamsTargetSearchOut
from app.services.graph_delegated_lookup import GraphDelegatedLookupError, list_service_user_chats
from app.services.graph_targets import GraphConfigError, GraphRequestError, GraphTarget, list_team_channels, search_targets

router = APIRouter(tags=["teams-targets"])


@router.get("/teams-targets/search", response_model=list[TeamsTargetSearchOut])
def search_teams_targets(
    kind: Literal["user", "team"] = Query(...),
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
    )
