from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuthDiagnosticSnapshot
from app.schemas import OAuthDiagnosticsOut
from app.security import dumps_json, ensure_utc, loads_json, utcnow

AUTH_COMPONENT_BOT_DELIVERY = "bot_delivery"
AUTH_COMPONENT_GRAPH_LOOKUP = "graph_lookup"


def credential_signature(*values: str) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update((value or "").encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def app_only_credential_signature(*, tenant_id: str, client_id: str, client_secret: str, scope: str) -> str:
    return credential_signature(tenant_id, client_id, client_secret, scope)


def get_oauth_snapshot(
    db: Session,
    *,
    organization_id: str,
    component: str,
    credential_signature_value: str,
) -> AuthDiagnosticSnapshot | None:
    snapshot = db.scalar(
        select(AuthDiagnosticSnapshot).where(
            AuthDiagnosticSnapshot.organization_id == organization_id,
            AuthDiagnosticSnapshot.component == component,
        )
    )
    if snapshot is None or snapshot.credential_signature != credential_signature_value:
        return None
    return snapshot


def store_oauth_snapshot(
    db: Session,
    *,
    organization_id: str,
    component: str,
    credential_signature_value: str,
    status: str,
    message: str,
    oauth: OAuthDiagnosticsOut,
) -> AuthDiagnosticSnapshot:
    snapshot = db.scalar(
        select(AuthDiagnosticSnapshot).where(
            AuthDiagnosticSnapshot.organization_id == organization_id,
            AuthDiagnosticSnapshot.component == component,
        )
    )
    if snapshot is None:
        snapshot = AuthDiagnosticSnapshot(organization_id=organization_id, component=component)
    token = oauth.token
    snapshot.credential_signature = credential_signature_value
    snapshot.status = status
    snapshot.message = message
    snapshot.token_checked = token.checked
    snapshot.token_request_succeeded = token.succeeded
    snapshot.diagnostics_json = dumps_json(oauth.model_dump(mode="json"))
    snapshot.checked_at = token.checked_at or utcnow()
    snapshot.expires_at = token.expires_at
    db.add(snapshot)
    db.flush()
    return snapshot


def oauth_from_snapshot(snapshot: AuthDiagnosticSnapshot) -> OAuthDiagnosticsOut:
    payload = loads_json(snapshot.diagnostics_json, {})
    if not isinstance(payload, dict):
        payload = {}
    return OAuthDiagnosticsOut(**payload)


def snapshot_checked_at(snapshot: AuthDiagnosticSnapshot | None):
    return ensure_utc(snapshot.checked_at) if snapshot is not None else None
