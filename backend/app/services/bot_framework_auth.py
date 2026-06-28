from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import jwt

from app.core.config import Settings
from app.core.settings_overrides import get_effective_settings
from app.security import utcnow


BOT_FRAMEWORK_ISSUER = "https://api.botframework.com"
OPENID_METADATA_URL = "https://login.botframework.com/v1/.well-known/openidconfiguration"
ALLOWED_ALGORITHMS = {"RS256", "RS384", "RS512"}
CLOCK_SKEW_SECONDS = 300
JWKS_CACHE_SECONDS = 24 * 60 * 60


class BotFrameworkAuthError(RuntimeError):
    pass


class BotFrameworkAuthConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class BotFrameworkClaims:
    issuer: str
    audience: str
    service_url: str
    service_url_matched: bool
    validated_at: datetime


@dataclass
class _JwksCache:
    metadata_url: str
    jwks_uri: str
    keys: list[dict[str, Any]]
    expires_at: datetime


_jwks_cache: _JwksCache | None = None
_jwks_lock = threading.Lock()


def reset_bot_framework_auth_cache() -> None:
    global _jwks_cache
    with _jwks_lock:
        _jwks_cache = None


def validate_bot_framework_activity(
    authorization: str | None,
    activity: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> BotFrameworkClaims:
    settings = settings or get_effective_settings()
    app_id = settings.ms_app_client_id.strip()
    if not app_id:
        raise BotFrameworkAuthConfigError("Bot Framework inbound authentication is not configured")

    token = _extract_bearer_token(authorization)
    header = _decode_header(token)
    alg = str(header.get("alg") or "")
    if alg not in ALLOWED_ALGORITHMS:
        raise BotFrameworkAuthError("Invalid Bot Framework token algorithm")
    kid = str(header.get("kid") or "")
    if not kid:
        raise BotFrameworkAuthError("Bot Framework token is missing a key ID")

    key_data = _get_signing_key(kid)
    try:
        key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))
    except (jwt.InvalidKeyError, ValueError) as exc:
        raise BotFrameworkAuthError("Invalid Bot Framework signing key") from exc
    try:
        claims = jwt.decode(
            token,
            key=key,
            algorithms=[alg],
            audience=app_id,
            issuer=BOT_FRAMEWORK_ISSUER,
            leeway=CLOCK_SKEW_SECONDS,
            options={"require": ["aud", "exp", "iss", "nbf"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise BotFrameworkAuthError("Expired Bot Framework token") from exc
    except jwt.ImmatureSignatureError as exc:
        raise BotFrameworkAuthError("Bot Framework token is not active yet") from exc
    except jwt.InvalidAudienceError as exc:
        raise BotFrameworkAuthError("Invalid Bot Framework token audience") from exc
    except jwt.InvalidIssuerError as exc:
        raise BotFrameworkAuthError("Invalid Bot Framework token issuer") from exc
    except jwt.InvalidTokenError as exc:
        raise BotFrameworkAuthError("Invalid Bot Framework token") from exc

    service_url = _claim_string(claims, "serviceurl") or _claim_string(claims, "serviceUrl")
    activity_service_url = _activity_service_url(activity)
    if not service_url or not activity_service_url or service_url != activity_service_url:
        raise BotFrameworkAuthError("Bot Framework serviceUrl claim mismatch")

    return BotFrameworkClaims(
        issuer=str(claims.get("iss") or ""),
        audience=str(claims.get("aud") or ""),
        service_url=service_url,
        service_url_matched=True,
        validated_at=utcnow(),
    )


def fetch_bot_framework_openid_metadata(url: str = OPENID_METADATA_URL) -> dict[str, Any]:
    return _fetch_json(url)


def fetch_bot_framework_jwks(url: str) -> dict[str, Any]:
    return _fetch_json(url)


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise BotFrameworkAuthError("Missing Bot Framework authorization")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise BotFrameworkAuthError("Invalid Bot Framework authorization header")
    return token.strip()


def _decode_header(token: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise BotFrameworkAuthError("Invalid Bot Framework token") from exc
    if not isinstance(header, dict):
        raise BotFrameworkAuthError("Invalid Bot Framework token")
    return header


def _get_signing_key(kid: str) -> dict[str, Any]:
    keys = _get_jwks_keys()
    key = _find_key(keys, kid)
    if key is None:
        keys = _get_jwks_keys(force_refresh=True)
        key = _find_key(keys, kid)
    if key is None:
        raise BotFrameworkAuthError("Unknown Bot Framework signing key")
    return key


def _get_jwks_keys(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    global _jwks_cache
    now = utcnow()
    with _jwks_lock:
        if not force_refresh and _jwks_cache and _jwks_cache.expires_at > now:
            return _jwks_cache.keys
        try:
            metadata = fetch_bot_framework_openid_metadata(OPENID_METADATA_URL)
            jwks_uri = str(metadata.get("jwks_uri") or "")
            if not jwks_uri:
                raise BotFrameworkAuthError("Bot Framework OpenID metadata is missing jwks_uri")
            jwks = fetch_bot_framework_jwks(jwks_uri)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise BotFrameworkAuthError("Unable to refresh Bot Framework signing keys") from exc
        keys = jwks.get("keys")
        if not isinstance(keys, list):
            raise BotFrameworkAuthError("Bot Framework JWKS response is invalid")
        normalized_keys = [key for key in keys if isinstance(key, dict)]
        _jwks_cache = _JwksCache(
            metadata_url=OPENID_METADATA_URL,
            jwks_uri=jwks_uri,
            keys=normalized_keys,
            expires_at=now + timedelta(seconds=JWKS_CACHE_SECONDS),
        )
        return normalized_keys


def _find_key(keys: list[dict[str, Any]], kid: str) -> dict[str, Any] | None:
    for key in keys:
        if str(key.get("kid") or "") == kid:
            return key
    return None


def _fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise BotFrameworkAuthError("Bot Framework metadata response is invalid")
    return parsed


def _claim_string(claims: dict[str, Any], key: str) -> str:
    value = claims.get(key)
    return value.strip() if isinstance(value, str) else ""


def _activity_service_url(activity: dict[str, Any]) -> str:
    value = activity.get("serviceUrl")
    return value.strip() if isinstance(value, str) else ""
