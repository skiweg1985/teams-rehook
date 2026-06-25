from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Cookie, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import get_db
from app.models import AuditEvent, Session as SessionModel, User
from app.security import dumps_json, hash_secret, issue_plain_secret, lookup_secret_hash, utcnow, verify_secret


def _ensure_live(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_current_session(
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=get_settings().session_cookie_name),
) -> SessionModel:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing session")

    token_hash = lookup_secret_hash(session_token)
    current_session = db.scalar(select(SessionModel).where(SessionModel.session_token_hash == token_hash))
    if not current_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    if current_session.revoked_at is not None or _ensure_live(current_session.expires_at) <= utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired session")
    return current_session


def get_current_user(
    current_session: SessionModel = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, current_session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_csrf(
    current_session: SessionModel = Depends(get_current_session),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> str:
    if not x_csrf_token or not verify_secret(x_csrf_token, current_session.csrf_token_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
    return x_csrf_token


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, httponly=True, samesite="strict", path="/")


def set_session_cookie(response: Response, session_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        httponly=True,
        secure=settings.session_secure_cookie,
        samesite="strict",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


def refresh_csrf_token(db: Session, current_session: SessionModel) -> str:
    csrf_token = issue_plain_secret(16)
    current_session.csrf_token_hash = hash_secret(csrf_token)
    db.add(current_session)
    return csrf_token


def record_audit(
    db: Session,
    *,
    action: str,
    actor_type: str,
    actor_id: str | None,
    organization_id: str | None,
    metadata: dict,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        metadata_json=dumps_json(metadata),
    )
    db.add(event)
    db.flush()
    return event
