from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import get_db
from app.deps import (
    clear_session_cookie,
    get_current_session,
    get_current_user,
    record_audit,
    refresh_csrf_token,
    require_csrf,
    set_session_cookie,
)
from app.models import Organization, Session as SessionModel, User
from app.schemas import FirstAdminCreateIn, LoginRequest, SessionResponse, SetupStatusOut, UserOut
from app.security import hash_secret, issue_plain_secret, lookup_secret_hash, session_expiry, utcnow, verify_secret

router = APIRouter(tags=["auth"])


def _issue_session(db: Session, user: User) -> tuple[str, str]:
    settings = get_settings()
    session_token = issue_plain_secret()
    csrf_token = issue_plain_secret(16)
    db_session = SessionModel(
        user_id=user.id,
        session_token_hash=lookup_secret_hash(session_token),
        csrf_token_hash=hash_secret(csrf_token),
        expires_at=session_expiry(settings.session_ttl_hours),
    )
    db.add(db_session)
    return session_token, csrf_token


def _normalize_email(email: str) -> str:
    value = str(email or "").strip().lower()
    if "@" not in value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A valid email address is required")
    return value


def _default_organization(db: Session) -> Organization:
    settings = get_settings()
    org = db.scalar(select(Organization).where(Organization.slug == settings.default_org_slug))
    if org is None:
        org = Organization(slug=settings.default_org_slug, name=settings.default_org_name)
        db.add(org)
        db.flush()
    return org


def _admin_exists(db: Session, organization_id: str) -> bool:
    admin_id = db.scalar(
        select(User.id).where(
            User.organization_id == organization_id,
            User.is_admin.is_(True),
        )
    )
    return admin_id is not None


@router.get("/setup/status", response_model=SetupStatusOut)
def setup_status(db: Session = Depends(get_db)):
    org = _default_organization(db)
    admin_exists = _admin_exists(db, org.id)
    db.commit()
    return SetupStatusOut(needs_setup=not admin_exists, admin_exists=admin_exists)


@router.post("/setup/admin", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_first_admin(payload: FirstAdminCreateIn, response: Response, db: Session = Depends(get_db)):
    org = _default_organization(db)
    if _admin_exists(db, org.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Initial setup has already been completed")

    email = _normalize_email(payload.email)
    existing = db.scalar(select(User).where(User.organization_id == org.id, User.email == email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists")

    user = User(
        organization_id=org.id,
        email=email,
        display_name=payload.display_name.strip(),
        password_hash=hash_secret(payload.password),
        is_admin=True,
        is_active=True,
    )
    db.add(user)
    db.flush()
    session_token, csrf_token = _issue_session(db, user)
    set_session_cookie(response, session_token)
    record_audit(
        db,
        action="setup.first_admin.created",
        actor_type="user",
        actor_id=user.id,
        organization_id=org.id,
        metadata={"user_id": user.id, "email": user.email},
    )
    db.commit()
    return SessionResponse(user=UserOut.model_validate(user), csrf_token=csrf_token)


@router.post("/auth/login", response_model=SessionResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    email = str(payload.email or "").strip().lower()
    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if not user or not verify_secret(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    session_token, csrf_token = _issue_session(db, user)
    set_session_cookie(response, session_token)
    record_audit(
        db,
        action="auth.login.success",
        actor_type="user",
        actor_id=user.id,
        organization_id=user.organization_id,
        metadata={"email": user.email},
    )
    db.commit()
    return SessionResponse(user=UserOut.model_validate(user), csrf_token=csrf_token)


@router.post("/auth/logout", dependencies=[Depends(require_csrf)])
def logout(
    response: Response,
    current_session: SessionModel = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    current_session.revoked_at = utcnow()
    record_audit(
        db,
        action="auth.logout",
        actor_type="user",
        actor_id=current_session.user_id,
        organization_id=None,
        metadata={"session_id": current_session.id},
    )
    db.commit()
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/sessions/me", response_model=SessionResponse)
def me(
    current_user: User = Depends(get_current_user),
    current_session: SessionModel = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    csrf_token = refresh_csrf_token(db, current_session)
    db.commit()
    return SessionResponse(user=UserOut.model_validate(current_user), csrf_token=csrf_token)
