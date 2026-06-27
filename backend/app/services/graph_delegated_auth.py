from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.encrypted_secrets import decrypt_secret, encrypt_secret
from app.core.settings_overrides import get_effective_settings
from app.models import GraphDelegatedCredential
from app.security import ensure_utc, utcnow


DEFAULT_DELEGATED_GRAPH_SCOPES = ("offline_access", "ChannelMessage.Send", "ChatMessage.Send", "Chat.ReadBasic", "User.Read")
GRAPH_DELEGATED_STATUS_MISSING = "missing"
GRAPH_DELEGATED_STATUS_READY = "ready"
GRAPH_DELEGATED_STATUS_EXPIRED = "expired"
GRAPH_DELEGATED_STATUS_TOKEN_ERROR = "token_error"


class GraphDelegatedConfigError(RuntimeError):
    pass


class GraphDelegatedAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class GraphDelegatedDiagnostics:
    status: str
    configured: bool
    tenant_id: str = ""
    client_id: str = ""
    scopes: list[str] | None = None
    service_user_id: str = ""
    service_user_display_name: str = ""
    service_user_principal_name: str = ""
    access_token_expires_at: datetime | None = None
    refresh_checked_at: datetime | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "configured": self.configured,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "scopes": self.scopes or [],
            "service_user_id": self.service_user_id,
            "service_user_display_name": self.service_user_display_name,
            "service_user_principal_name": self.service_user_principal_name,
            "access_token_expires_at": self.access_token_expires_at,
            "refresh_checked_at": self.refresh_checked_at,
            "message": self.message,
        }


@dataclass(frozen=True)
class GraphDelegatedAccessToken:
    access_token: str
    expires_at: datetime
    scopes: list[str]
    diagnostics: GraphDelegatedDiagnostics


def build_authorization_url(
    *,
    redirect_uri: str,
    state: str,
    settings: Settings | None = None,
    scopes: tuple[str, ...] = DEFAULT_DELEGATED_GRAPH_SCOPES,
) -> str:
    settings = settings or get_effective_settings()
    _require_app_registration(settings)
    query = urllib.parse.urlencode(
        {
            "client_id": settings.ms_app_client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": " ".join(scopes),
            "state": state,
        }
    )
    tenant = urllib.parse.quote(settings.ms_app_tenant_id, safe="")
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{query}"


def exchange_authorization_code(
    db: Session,
    *,
    organization_id: str,
    code: str,
    redirect_uri: str,
    settings: Settings | None = None,
    scopes: tuple[str, ...] = DEFAULT_DELEGATED_GRAPH_SCOPES,
) -> GraphDelegatedDiagnostics:
    settings = settings or get_effective_settings()
    _require_app_registration(settings)
    response = _request_token(
        settings=settings,
        form={
            "grant_type": "authorization_code",
            "client_id": settings.ms_app_client_id,
            "client_secret": settings.ms_app_client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
        },
    )
    refresh_token = str(response.get("refresh_token") or "")
    access_token = str(response.get("access_token") or "")
    if not refresh_token or not access_token:
        raise GraphDelegatedAuthError("Delegated Graph authorization did not return usable token material")
    credential = _get_or_create_credential(db, organization_id)
    _apply_successful_token_response(
        credential,
        response,
        settings=settings,
        fallback_scopes=list(scopes),
        refresh_token=refresh_token,
    )
    db.add(credential)
    db.flush()
    return diagnostics_for_credential(credential)


def refresh_delegated_access_token(
    db: Session,
    *,
    organization_id: str,
    settings: Settings | None = None,
    scopes: tuple[str, ...] = DEFAULT_DELEGATED_GRAPH_SCOPES,
) -> GraphDelegatedAccessToken:
    settings = settings or get_effective_settings()
    _require_app_registration(settings)
    credential = get_delegated_credential(db, organization_id)
    if credential is None or not credential.encrypted_refresh_token:
        raise GraphDelegatedAuthError("Delegated Graph delivery is not configured")
    try:
        refresh_token = decrypt_secret(credential.encrypted_refresh_token)
        response = _request_token(
            settings=settings,
            form={
                "grant_type": "refresh_token",
                "client_id": settings.ms_app_client_id,
                "client_secret": settings.ms_app_client_secret,
                "refresh_token": refresh_token,
                "scope": " ".join(scopes),
            },
        )
    except _ExpiredRefreshTokenError as exc:
        _mark_credential_status(
            credential,
            GRAPH_DELEGATED_STATUS_EXPIRED,
            "Delegated Graph refresh token is expired or revoked.",
        )
        db.add(credential)
        db.flush()
        raise GraphDelegatedAuthError(credential.last_error) from exc
    except GraphDelegatedAuthError as exc:
        _mark_credential_status(
            credential,
            GRAPH_DELEGATED_STATUS_TOKEN_ERROR,
            "Delegated Graph token refresh failed.",
        )
        db.add(credential)
        db.flush()
        raise GraphDelegatedAuthError(credential.last_error) from exc

    access_token = str(response.get("access_token") or "")
    if not access_token:
        _mark_credential_status(
            credential,
            GRAPH_DELEGATED_STATUS_TOKEN_ERROR,
            "Delegated Graph token refresh did not return an access token.",
        )
        db.add(credential)
        db.flush()
        raise GraphDelegatedAuthError(credential.last_error)
    _apply_successful_token_response(
        credential,
        response,
        settings=settings,
        fallback_scopes=list(scopes),
        refresh_token=str(response.get("refresh_token") or "") or None,
    )
    db.add(credential)
    db.flush()
    return GraphDelegatedAccessToken(
        access_token=access_token,
        expires_at=ensure_utc(credential.access_token_expires_at) or utcnow(),
        scopes=_scope_list(credential.scopes),
        diagnostics=diagnostics_for_credential(credential),
    )


def get_delegated_credential(db: Session, organization_id: str) -> GraphDelegatedCredential | None:
    return db.scalar(
        select(GraphDelegatedCredential).where(GraphDelegatedCredential.organization_id == organization_id)
    )


def diagnostics_for_organization(db: Session, organization_id: str) -> GraphDelegatedDiagnostics:
    credential = get_delegated_credential(db, organization_id)
    if credential is None:
        return GraphDelegatedDiagnostics(
            status=GRAPH_DELEGATED_STATUS_MISSING,
            configured=False,
            message="Delegated Graph delivery has not been configured.",
        )
    return diagnostics_for_credential(credential)


def diagnostics_for_credential(credential: GraphDelegatedCredential) -> GraphDelegatedDiagnostics:
    return GraphDelegatedDiagnostics(
        status=credential.last_status or GRAPH_DELEGATED_STATUS_MISSING,
        configured=bool(credential.encrypted_refresh_token),
        tenant_id=credential.tenant_id,
        client_id=credential.client_id,
        scopes=_scope_list(credential.scopes),
        service_user_id=credential.service_user_id,
        service_user_display_name=credential.service_user_display_name,
        service_user_principal_name=credential.service_user_principal_name,
        access_token_expires_at=ensure_utc(credential.access_token_expires_at),
        refresh_checked_at=ensure_utc(credential.refresh_checked_at),
        message=credential.last_error,
    )


class _ExpiredRefreshTokenError(GraphDelegatedAuthError):
    pass


def _require_app_registration(settings: Settings) -> None:
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
        raise GraphDelegatedConfigError(f"Missing delegated Graph app registration settings: {', '.join(missing)}")


def _get_or_create_credential(db: Session, organization_id: str) -> GraphDelegatedCredential:
    credential = get_delegated_credential(db, organization_id)
    if credential is not None:
        return credential
    credential = GraphDelegatedCredential(organization_id=organization_id)
    db.add(credential)
    return credential


def _request_token(*, settings: Settings, form: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(form).encode("utf-8")
    request = urllib.request.Request(
        f"https://login.microsoftonline.com/{settings.ms_app_tenant_id}/oauth2/v2.0/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if _token_error_code(exc) == "invalid_grant":
            raise _ExpiredRefreshTokenError("Delegated Graph refresh token is expired or revoked") from exc
        raise GraphDelegatedAuthError("Delegated Graph token request failed") from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GraphDelegatedAuthError("Delegated Graph token request failed") from exc


def _token_error_code(exc: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(exc.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ""
    return str(body.get("error") or "")


def _apply_successful_token_response(
    credential: GraphDelegatedCredential,
    response: dict[str, Any],
    *,
    settings: Settings,
    fallback_scopes: list[str],
    refresh_token: str | None,
) -> None:
    access_token = str(response.get("access_token") or "")
    claims = _decode_jwt_claims(access_token)
    expires_in = int(response.get("expires_in") or 3600)
    scopes = _scope_list(str(response.get("scope") or "")) or fallback_scopes
    if refresh_token:
        credential.encrypted_refresh_token = encrypt_secret(refresh_token)
    credential.tenant_id = settings.ms_app_tenant_id
    credential.client_id = settings.ms_app_client_id
    credential.scopes = " ".join(scopes)
    service_user_id = _claim(claims, "oid") or _claim(claims, "sub")
    service_user_display_name = _claim(claims, "name")
    service_user_principal_name = _claim(claims, "preferred_username") or _claim(claims, "upn")
    if service_user_id:
        credential.service_user_id = service_user_id
    if service_user_display_name:
        credential.service_user_display_name = service_user_display_name
    if service_user_principal_name:
        credential.service_user_principal_name = service_user_principal_name
    credential.last_status = GRAPH_DELEGATED_STATUS_READY
    credential.last_error = ""
    credential.access_token_expires_at = utcnow() + timedelta(seconds=max(expires_in, 1))
    credential.refresh_checked_at = utcnow()


def _mark_credential_status(credential: GraphDelegatedCredential, status: str, message: str) -> None:
    credential.last_status = status
    credential.last_error = message
    credential.refresh_checked_at = utcnow()


def _decode_jwt_claims(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    padded = payload + "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        claims = json.loads(decoded)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return claims if isinstance(claims, dict) else {}


def _claim(claims: dict[str, Any], key: str) -> str:
    value = claims.get(key)
    return value.strip() if isinstance(value, str) else ""


def _scope_list(value: str) -> list[str]:
    return [scope for scope in value.split() if scope]
