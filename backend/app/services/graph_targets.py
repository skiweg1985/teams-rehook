from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Literal

from app.core.config import Settings
from app.core.settings_overrides import get_effective_settings
from app.security import utcnow


GraphTargetKind = Literal["user", "team", "channel"]


class GraphConfigError(RuntimeError):
    pass


class GraphRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class GraphTarget:
    kind: GraphTargetKind
    id: str
    display_name: str
    subtitle: str = ""
    team_id: str | None = None
    team_name: str | None = None
    channel_id: str | None = None


TokenFetcher = Callable[[Settings], tuple[str, int]]


class GraphTokenManager:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        fetcher: TokenFetcher | None = None,
        refresh_window_seconds: int = 60,
    ):
        self.settings = settings or get_effective_settings()
        self.fetcher = fetch_graph_token if fetcher is None else fetcher
        self.refresh_window = timedelta(seconds=refresh_window_seconds)
        self._access_token: str | None = None
        self._expires_at: datetime | None = None
        self._lock = threading.Lock()

    def get_token(self) -> str:
        with self._lock:
            if self._access_token and self._expires_at and self._expires_at - utcnow() > self.refresh_window:
                return self._access_token
            token, expires_in = self.fetcher(self.settings)
            if not token:
                raise GraphRequestError("Microsoft Graph token response did not include an access token")
            self._access_token = token
            self._expires_at = utcnow() + timedelta(seconds=max(expires_in, 1))
            return self._access_token


_token_manager: GraphTokenManager | None = None


def get_graph_token_manager() -> GraphTokenManager:
    global _token_manager
    if _token_manager is None:
        _token_manager = GraphTokenManager()
    return _token_manager


def reset_graph_token_manager() -> None:
    global _token_manager
    _token_manager = None


def fetch_graph_token(settings: Settings) -> tuple[str, int]:
    missing = [
        name
        for name, value in {
            "MS_APP_TENANT_ID": settings.ms_app_tenant_id,
            "MS_APP_CLIENT_ID": settings.ms_app_client_id,
            "MS_APP_CLIENT_SECRET": settings.ms_app_client_secret,
        }.items()
        if not value
    ]
    if missing:
        raise GraphConfigError(f"Missing Microsoft Graph app-only credentials: {', '.join(missing)}")

    form = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": settings.ms_app_client_id,
            "client_secret": settings.ms_app_client_secret,
            "scope": settings.graph_scope,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://login.microsoftonline.com/{settings.ms_app_tenant_id}/oauth2/v2.0/token",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GraphRequestError("Failed to fetch Microsoft Graph access token") from exc
    return str(body.get("access_token") or ""), int(body.get("expires_in") or 3600)


def search_targets(kind: Literal["user", "team"], query: str, *, limit: int = 10) -> list[GraphTarget]:
    q = query.strip()
    if len(q) < 2:
        return []
    if kind == "user":
        return _search_users(q, limit=limit)
    return _search_teams(q, limit=limit)


def list_team_channels(team_id: str, query: str = "", *, limit: int = 25) -> list[GraphTarget]:
    team_id = team_id.strip()
    if not team_id:
        return []
    data = _graph_get(
        f"/teams/{urllib.parse.quote(team_id, safe='')}/channels",
        {"$select": "id,displayName,description,membershipType"},
    )
    needle = query.strip().lower()
    targets = []
    for channel in data.get("value", []):
        display_name = str(channel.get("displayName") or "").strip()
        if not display_name:
            continue
        if needle and needle not in display_name.lower() and needle not in str(channel.get("description") or "").lower():
            continue
        channel_id = str(channel.get("id") or "").strip()
        targets.append(
            GraphTarget(
                kind="channel",
                id=channel_id,
                display_name=display_name,
                subtitle=str(channel.get("description") or channel.get("membershipType") or "").strip(),
                team_id=team_id,
                channel_id=channel_id,
            )
        )
        if len(targets) >= limit:
            break
    return targets


def get_user_target(user_id: str) -> GraphTarget | None:
    user_id = user_id.strip()
    if not user_id:
        return None
    data = _graph_get(
        f"/users/{urllib.parse.quote(user_id, safe='')}",
        {"$select": "id,displayName,userPrincipalName,mail"},
    )
    display_name = str(data.get("displayName") or data.get("userPrincipalName") or "").strip()
    resolved_id = str(data.get("id") or user_id).strip()
    if not display_name:
        return None
    return GraphTarget(
        kind="user",
        id=resolved_id,
        display_name=display_name,
        subtitle=str(data.get("mail") or data.get("userPrincipalName") or "").strip(),
    )


def get_team_target(team_id: str) -> GraphTarget | None:
    team_id = team_id.strip()
    if not team_id:
        return None
    data = _graph_get(
        f"/teams/{urllib.parse.quote(team_id, safe='')}",
        {"$select": "id,displayName,description"},
    )
    display_name = str(data.get("displayName") or "").strip()
    resolved_id = str(data.get("id") or team_id).strip()
    if not display_name:
        return None
    return GraphTarget(
        kind="team",
        id=resolved_id,
        display_name=display_name,
        subtitle=str(data.get("description") or data.get("mailNickname") or "").strip(),
        team_id=resolved_id,
        team_name=display_name,
    )


def get_channel_target(team_id: str, channel_id: str) -> GraphTarget | None:
    team_id = team_id.strip()
    channel_id = channel_id.strip()
    if not team_id or not channel_id:
        return None
    data = _graph_get(
        f"/teams/{urllib.parse.quote(team_id, safe='')}/channels/{urllib.parse.quote(channel_id, safe='')}",
        {"$select": "id,displayName,description,membershipType"},
    )
    display_name = str(data.get("displayName") or "").strip()
    resolved_id = str(data.get("id") or channel_id).strip()
    if not display_name:
        return None
    return GraphTarget(
        kind="channel",
        id=resolved_id,
        display_name=display_name,
        subtitle=str(data.get("description") or data.get("membershipType") or "").strip(),
        team_id=team_id,
        channel_id=resolved_id,
    )


def _search_users(query: str, *, limit: int) -> list[GraphTarget]:
    escaped = _odata_string(query)
    data = _graph_get(
        "/users",
        {
            "$top": str(limit),
            "$select": "id,displayName,userPrincipalName,mail",
            "$filter": (
                f"startswith(displayName,'{escaped}') or "
                f"startswith(mail,'{escaped}') or "
                f"startswith(userPrincipalName,'{escaped}')"
            ),
        },
    )
    targets = []
    for user in data.get("value", []):
        display_name = str(user.get("displayName") or user.get("userPrincipalName") or "").strip()
        user_id = str(user.get("id") or "").strip()
        if display_name and user_id:
            targets.append(
                GraphTarget(
                    kind="user",
                    id=user_id,
                    display_name=display_name,
                    subtitle=str(user.get("mail") or user.get("userPrincipalName") or "").strip(),
                )
            )
    return targets


def _search_teams(query: str, *, limit: int) -> list[GraphTarget]:
    escaped = _odata_string(query)
    data = _graph_get(
        "/teams",
        {
            "$top": str(limit),
            "$select": "id,displayName,description",
            "$filter": f"startswith(displayName,'{escaped}')",
        },
    )
    targets = []
    for team in data.get("value", []):
        display_name = str(team.get("displayName") or "").strip()
        team_id = str(team.get("id") or "").strip()
        if display_name and team_id:
            targets.append(
                GraphTarget(
                    kind="team",
                    id=team_id,
                    display_name=display_name,
                    subtitle=str(team.get("description") or team.get("mailNickname") or "").strip(),
                    team_id=team_id,
                    team_name=display_name,
                )
            )
    return targets


def _graph_get(path: str, params: dict[str, str]) -> dict:
    token = get_graph_token_manager().get_token()
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"https://graph.microsoft.com/v1.0{path}?{query}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        safe_body = exc.read().decode("utf-8", errors="replace")[:500]
        raise GraphRequestError(f"Microsoft Graph request failed with HTTP {exc.code}: {safe_body}") from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GraphRequestError("Microsoft Graph request failed") from exc


def _odata_string(value: str) -> str:
    return value.replace("'", "''")
