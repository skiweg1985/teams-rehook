from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from app.core.config import Settings
from app.core.settings_overrides import get_effective_settings
from app.security import utcnow
from app.services.webhook_payloads import NormalizedMessage


class BotDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class BotDeliveryResult:
    mode: str
    activity_id: str | None
    status_code: int
    activity: dict

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "activity_id": self.activity_id,
            "status_code": self.status_code,
            "activity": self.activity,
        }


TokenFetcher = Callable[[Settings], tuple[str, int]]
NowProvider = Callable[[], datetime]


class BotTokenManager:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        fetcher: TokenFetcher | None = None,
        now: NowProvider = utcnow,
        refresh_window_seconds: int = 60,
    ):
        self.settings = settings or get_effective_settings()
        self.fetcher = fetcher or fetch_botframework_token
        self.now = now
        self.refresh_window = timedelta(seconds=refresh_window_seconds)
        self._access_token: str | None = None
        self._expires_at: datetime | None = None
        self._lock = threading.Lock()

    def get_token(self) -> str:
        with self._lock:
            if self._access_token and self._expires_at and self._expires_at - self.now() > self.refresh_window:
                return self._access_token
            token, expires_in = self.fetcher(self.settings)
            if not token:
                raise BotDeliveryError("Bot Framework token response did not include an access token")
            self._access_token = token
            self._expires_at = self.now() + timedelta(seconds=max(expires_in, 1))
            return self._access_token


_token_manager: BotTokenManager | None = None


def get_token_manager() -> BotTokenManager:
    global _token_manager
    if _token_manager is None:
        _token_manager = BotTokenManager()
    return _token_manager


def reset_bot_token_manager() -> None:
    global _token_manager
    _token_manager = None


def fetch_botframework_token(settings: Settings) -> tuple[str, int]:
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
        raise BotDeliveryError(f"Missing Bot Framework credentials: {', '.join(missing)}")

    form = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": settings.ms_app_client_id,
            "client_secret": settings.ms_app_client_secret,
            "scope": settings.botframework_scope,
        }
    ).encode("utf-8")
    url = f"https://login.microsoftonline.com/{settings.ms_app_tenant_id}/oauth2/v2.0/token"
    request = urllib.request.Request(
        url,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise BotDeliveryError("Failed to fetch Bot Framework access token") from exc
    return str(body.get("access_token") or ""), int(body.get("expires_in") or 3600)


def build_activity(message: NormalizedMessage) -> dict:
    if message.activity:
        activity = dict(message.activity)
        activity.setdefault("type", "message")
        return activity
    lines = [f"**{message.title}**", message.text]
    return {"type": "message", "text": "\n\n".join([line for line in lines if line])}


def send_bot_activity(
    *,
    service_url: str,
    conversation_id: str,
    message: NormalizedMessage,
    settings: Settings | None = None,
    token_manager: BotTokenManager | None = None,
) -> BotDeliveryResult:
    settings = settings or get_effective_settings()
    mode = settings.bot_delivery_mode_normalized
    activity = build_activity(message)
    if mode == "mock":
        return BotDeliveryResult(mode="mock", activity_id="mock-activity", status_code=202, activity=activity)

    service_url = service_url.strip().rstrip("/")
    conversation_id = conversation_id.strip()
    if not service_url or not conversation_id:
        raise BotDeliveryError("Bot service URL and conversation ID are required for real delivery")

    token = (token_manager or get_token_manager()).get_token()
    encoded_conversation_id = urllib.parse.quote(conversation_id, safe="")
    url = f"{service_url}/v3/conversations/{encoded_conversation_id}/activities"
    body = json.dumps(activity).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response_body = response.read().decode("utf-8")
            parsed = json.loads(response_body) if response_body else {}
            activity_id = parsed.get("id") if isinstance(parsed, dict) else None
            return BotDeliveryResult(
                mode="real",
                activity_id=str(activity_id) if activity_id else None,
                status_code=response.status,
                activity=activity,
            )
    except urllib.error.HTTPError as exc:
        safe_body = exc.read().decode("utf-8", errors="replace")[:500]
        raise BotDeliveryError(f"Bot Framework delivery failed with HTTP {exc.code}: {safe_body}") from exc
    except urllib.error.URLError as exc:
        raise BotDeliveryError("Bot Framework delivery failed") from exc
