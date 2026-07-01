from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session, object_session

from app.core.proxy_trust import combined_trusted_proxy_ips
from app.core.settings_overrides import (
    clear_override,
    get_effective_settings,
    is_environment_override,
    list_setting_items,
    set_override,
)
from app.database import get_db
from app.deps import get_current_session, record_audit, require_admin, require_csrf
from app.models import (
    AuditEvent,
    BotActivityEvent,
    BotAccessRole,
    BotAuthorizedGroup,
    BotAuthorizedUser,
    EventLogEntry,
    GraphDelegatedCredential,
    Session as UserSession,
    User,
    WebhookAbuseBucket,
)
from app.schemas import (
    AdminReadinessOut,
    AuditEventOut,
    BotAccessRoleCreateIn,
    BotAccessRoleOut,
    BotAccessRoleUpdateIn,
    BotAuthorizedGroupCreateIn,
    BotAuthorizedGroupOut,
    BotAuthorizedGroupUpdateIn,
    BotAuthorizedUserCreateIn,
    BotAuthorizedUserOut,
    BotAuthorizedUserUpdateIn,
    BotReadinessOut,
    ClientEventIn,
    DeliveryAuthRefreshComponentOut,
    DeliveryAuthRefreshOut,
    EventLogEntryOut,
    EventLogEntryPageOut,
    GraphDeliveryOAuthStartOut,
    GraphDeliveryOAuthPendingOut,
    GraphDeliveryReadinessOut,
    GraphReadinessOut,
    LogCleanupOut,
    OAuthAppDiagnosticsOut,
    OAuthDiagnosticsOut,
    OAuthTenantDiagnosticsOut,
    OAuthTokenDiagnosticsOut,
    RuntimeReadinessOut,
    SettingItemOut,
    SettingUpdateIn,
    SystemLogEventOut,
    UserCreateIn,
    UserOut,
    UserPasswordUpdateIn,
    UserUpdateIn,
    WebhookAbuseBucketOut,
    WebhookAbuseCleanupOut,
)
from app.security import dumps_json, ensure_utc, hash_secret, loads_json, utcnow
from app.services.bot_framework_auth import reset_bot_framework_auth_cache
from app.services.bot_access_roles import (
    BOT_PERMISSION_FIELDS,
    ROUTE_OPERATOR_SYSTEM_KEY,
    ROUTE_VIEWER_SYSTEM_KEY,
    ensure_bot_access_system_roles,
    role_permissions,
)
from app.services.event_log import emit_event, event_from_entry
from app.services.graph_delegated_auth import (
    DEFAULT_DELEGATED_GRAPH_SCOPES,
    GraphDelegatedAuthError,
    GraphDelegatedConfigError,
    build_authorization_url,
    diagnostics_for_organization,
    diagnostics_for_pending_credential,
    exchange_authorization_code_to_pending,
    get_pending_delegated_credential_by_id,
    pending_credential_is_expired,
    promote_pending_delegated_credential,
    refresh_delegated_access_token,
)
from app.services.graph_targets import GraphConfigError, GraphRequestError, get_graph_token_manager, reset_graph_token_manager
from app.services.log_retention import cleanup_log_events
from app.services.teams_bot import BotDeliveryError, get_token_manager, reset_bot_token_manager
from app.services.webhook_abuse import cleanup_buckets, unblock_bucket

router = APIRouter(prefix="/admin", tags=["admin"])
GRAPH_OAUTH_STATE_TTL_SECONDS = 600
GRAPH_GROUP_MEMBERSHIP_REQUIRED_ROLES = ("GroupMember.Read.All",)
GRAPH_GROUP_MEMBERSHIP_ALTERNATIVE_ROLES = ("Directory.Read.All",)


@dataclass(frozen=True)
class OAuthTokenResponse:
    access_token: str
    expires_in_seconds: int
    claims: dict


@router.get("/settings", response_model=list[SettingItemOut], dependencies=[Depends(require_csrf)])
def list_settings(admin: User = Depends(require_admin)):
    _ = admin
    return [SettingItemOut(**item) for item in list_setting_items()]


@router.put(
    "/settings/{key}",
    response_model=SettingItemOut,
    dependencies=[Depends(require_csrf)],
)
def update_setting(
    key: str,
    payload: SettingUpdateIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    set_override(db, key=key, value=payload.value, updated_by_id=admin.id)
    record_audit(
        db,
        action="settings.override.set" if is_environment_override(key) else "settings.application.set",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"key": key},
    )
    db.commit()
    item = next((entry for entry in list_setting_items() if entry["key"] == key), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown setting")
    return SettingItemOut(**item)


@router.delete(
    "/settings/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def reset_setting(
    key: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    clear_override(db, key=key)
    record_audit(
        db,
        action="settings.override.reset" if is_environment_override(key) else "settings.application.reset",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"key": key},
    )
    db.commit()
    return None


@router.post(
    "/graph-delivery/oauth/start",
    response_model=GraphDeliveryOAuthStartOut,
    dependencies=[Depends(require_csrf)],
)
def start_graph_delivery_oauth(admin: User = Depends(require_admin)):
    settings = get_effective_settings()
    redirect_uri = _graph_delivery_redirect_uri(settings)
    state = _issue_graph_oauth_state(admin, settings)
    try:
        authorization_url = build_authorization_url(
            redirect_uri=redirect_uri,
            state=state,
            settings=settings,
            scopes=DEFAULT_DELEGATED_GRAPH_SCOPES,
        )
    except GraphDelegatedConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return GraphDeliveryOAuthStartOut(authorization_url=authorization_url)


@router.get("/graph-delivery/oauth/callback")
def graph_delivery_oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    settings = get_effective_settings()
    _verify_graph_oauth_state(state, admin, settings)
    if error:
        return _graph_delivery_settings_redirect(settings, "error")
    if not code.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Microsoft Graph authorization code")
    try:
        pending = exchange_authorization_code_to_pending(
            db,
            organization_id=admin.organization_id,
            created_by_id=admin.id,
            code=code,
            redirect_uri=_graph_delivery_redirect_uri(settings),
            settings=settings,
            scopes=DEFAULT_DELEGATED_GRAPH_SCOPES,
        )
    except (GraphDelegatedConfigError, GraphDelegatedAuthError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    record_audit(
        db,
        action="graph_delivery.oauth.connected",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"credential": "delegated_service_user", "pending_id": pending.id},
    )
    db.commit()
    return _graph_delivery_pending_redirect(settings, pending.id)


@router.get(
    "/graph-delivery/oauth/pending/{pending_id}",
    response_model=GraphDeliveryOAuthPendingOut,
    dependencies=[Depends(require_csrf)],
)
def get_graph_delivery_oauth_pending(
    pending_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    pending = _get_live_graph_delivery_pending(db, admin.organization_id, pending_id)
    return _graph_delivery_pending_out(pending)


@router.post(
    "/graph-delivery/oauth/pending/{pending_id}/confirm",
    response_model=AdminReadinessOut,
    dependencies=[Depends(require_csrf)],
)
def confirm_graph_delivery_oauth_pending(
    pending_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _get_live_graph_delivery_pending(db, admin.organization_id, pending_id)
    try:
        credential = promote_pending_delegated_credential(db, organization_id=admin.organization_id, pending_id=pending_id)
    except GraphDelegatedAuthError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    record_audit(
        db,
        action="graph_delivery.oauth.confirmed",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={
            "credential": "delegated_service_user",
            "pending_id": pending_id,
            "service_user_id": credential.service_user_id,
        },
    )
    db.commit()
    readiness = _admin_readiness(db, admin, settings=get_effective_settings())
    if readiness.graph_delivery.token_checked:
        db.commit()
    return readiness


@router.delete(
    "/graph-delivery/oauth/pending/{pending_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def cancel_graph_delivery_oauth_pending(
    pending_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    pending = get_pending_delegated_credential_by_id(db, organization_id=admin.organization_id, pending_id=pending_id)
    if pending is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending delegated Graph connection was not found.")
    db.delete(pending)
    record_audit(
        db,
        action="graph_delivery.oauth.pending_canceled",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"credential": "delegated_service_user", "pending_id": pending_id},
    )
    db.commit()
    return None


@router.delete("/graph-delivery/oauth", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
def disconnect_graph_delivery_oauth(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    db.execute(delete(GraphDelegatedCredential).where(GraphDelegatedCredential.organization_id == admin.organization_id))
    record_audit(
        db,
        action="graph_delivery.oauth.disconnected",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"credential": "delegated_service_user"},
    )
    db.commit()
    return None


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_csrf)])
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(
        select(User)
        .where(User.organization_id == admin.organization_id)
        .order_by(User.created_at.desc())
    ).all()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
def create_user(payload: UserCreateIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    email = _normalize_user_email(payload.email)
    _ensure_user_email_available(db, admin.organization_id, email)
    user = User(
        organization_id=admin.organization_id,
        email=email,
        display_name=payload.display_name.strip(),
        password_hash=hash_secret(payload.password),
        is_admin=payload.is_admin,
        is_active=payload.is_active,
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        action="admin.user.created",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={
            "user_id": user.id,
            "email": user.email,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
        },
    )
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut, dependencies=[Depends(require_csrf)])
def update_user(
    user_id: str,
    payload: UserUpdateIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = _get_org_user(db, admin.organization_id, user_id)
    next_email = _normalize_user_email(payload.email) if payload.email is not None else user.email
    next_display_name = payload.display_name.strip() if payload.display_name is not None else user.display_name
    next_is_admin = payload.is_admin if payload.is_admin is not None else user.is_admin
    next_is_active = payload.is_active if payload.is_active is not None else user.is_active

    if next_email != user.email:
        _ensure_user_email_available(db, admin.organization_id, next_email, user_id=user.id)
    _ensure_user_update_allowed(db, actor=admin, user=user, next_is_admin=next_is_admin, next_is_active=next_is_active)

    before = {
        "email": user.email,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
    }
    user.email = next_email
    user.display_name = next_display_name
    user.is_admin = next_is_admin
    user.is_active = next_is_active
    revoked_sessions = 0
    if not user.is_active:
        revoked_sessions = _revoke_user_sessions(db, user.id)
    record_audit(
        db,
        action="admin.user.updated",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={
            "user_id": user.id,
            "before": before,
            "after": {
                "email": user.email,
                "display_name": user.display_name,
                "is_admin": user.is_admin,
                "is_active": user.is_active,
            },
        },
    )
    if revoked_sessions:
        _record_session_revocation(db, admin, user, revoked_sessions, "user_deactivated")
    db.commit()
    return user


@router.put("/users/{user_id}/password", response_model=UserOut, dependencies=[Depends(require_csrf)])
def update_user_password(
    user_id: str,
    payload: UserPasswordUpdateIn,
    admin: User = Depends(require_admin),
    current_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    user = _get_org_user(db, admin.organization_id, user_id)
    user.password_hash = hash_secret(payload.password)
    revoked_sessions = _revoke_user_sessions(db, user.id, exclude_session_id=current_session.id if user.id == admin.id else None)
    record_audit(
        db,
        action="admin.user.password_changed",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"user_id": user.id, "email": user.email},
    )
    if revoked_sessions:
        _record_session_revocation(db, admin, user, revoked_sessions, "password_changed")
    db.commit()
    return user


@router.get("/bot-roles", response_model=list[BotAccessRoleOut], dependencies=[Depends(require_csrf)])
def list_bot_access_roles(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    ensure_bot_access_system_roles(db, admin.organization_id, actor_id=admin.id)
    db.commit()
    return db.scalars(
        select(BotAccessRole)
        .where(BotAccessRole.organization_id == admin.organization_id)
        .order_by(BotAccessRole.is_system.desc(), BotAccessRole.name.asc())
    ).all()


@router.post(
    "/bot-roles",
    response_model=BotAccessRoleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_bot_access_role(
    payload: BotAccessRoleCreateIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ensure_bot_role_name_available(db, admin.organization_id, payload.name)
    role = BotAccessRole(
        organization_id=admin.organization_id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        is_system=False,
        system_key=None,
        created_by_id=admin.id,
        updated_by_id=admin.id,
        **{field: bool(getattr(payload, field)) for field in BOT_PERMISSION_FIELDS},
    )
    db.add(role)
    db.flush()
    record_audit(
        db,
        action="admin.bot_role.created",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata=_bot_role_audit_metadata(role),
    )
    db.commit()
    return role


@router.patch("/bot-roles/{bot_role_id}", response_model=BotAccessRoleOut, dependencies=[Depends(require_csrf)])
def update_bot_access_role(
    bot_role_id: str,
    payload: BotAccessRoleUpdateIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    role = _get_org_bot_role(db, admin.organization_id, bot_role_id)
    before = _bot_role_audit_metadata(role)
    if payload.name is not None:
        _ensure_bot_role_name_available(db, admin.organization_id, payload.name, existing_role_id=role.id)
        role.name = payload.name.strip()
    if payload.description is not None:
        role.description = payload.description.strip()
    for field in BOT_PERMISSION_FIELDS:
        value = getattr(payload, field)
        if value is not None:
            setattr(role, field, value)
    role.updated_by_id = admin.id
    role.updated_at = utcnow()
    _sync_linked_bot_role_grants(db, role)
    record_audit(
        db,
        action="admin.bot_role.updated",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"before": before, "after": _bot_role_audit_metadata(role)},
    )
    db.commit()
    return role


@router.delete("/bot-roles/{bot_role_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
def delete_bot_access_role(
    bot_role_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    role = _get_org_bot_role(db, admin.organization_id, bot_role_id)
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="System bot access roles cannot be deleted")
    linked_user_count = db.scalar(select(func.count()).select_from(BotAuthorizedUser).where(BotAuthorizedUser.role_id == role.id)) or 0
    linked_group_count = db.scalar(select(func.count()).select_from(BotAuthorizedGroup).where(BotAuthorizedGroup.role_id == role.id)) or 0
    if linked_user_count or linked_group_count:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bot access role is still assigned")
    metadata = _bot_role_audit_metadata(role)
    db.delete(role)
    record_audit(
        db,
        action="admin.bot_role.deleted",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata=metadata,
    )
    db.commit()
    return None


@router.get("/bot-users", response_model=list[BotAuthorizedUserOut], dependencies=[Depends(require_csrf)])
def list_bot_authorized_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    ensure_bot_access_system_roles(db, admin.organization_id, actor_id=admin.id)
    _backfill_bot_access_role_assignments(db, admin.organization_id)
    db.commit()
    return db.scalars(
        select(BotAuthorizedUser)
        .where(BotAuthorizedUser.organization_id == admin.organization_id)
        .order_by(BotAuthorizedUser.display_name.asc(), BotAuthorizedUser.created_at.desc())
    ).all()


@router.post(
    "/bot-users",
    response_model=BotAuthorizedUserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_bot_authorized_user(
    payload: BotAuthorizedUserCreateIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    aad_object_id = _normalize_aad_object_id(payload.aad_object_id)
    _ensure_bot_user_available(db, admin.organization_id, aad_object_id)
    access_role = _resolve_payload_bot_role(db, admin.organization_id, payload.role_id, payload.role)
    permissions = role_permissions(access_role) if access_role is not None else _bot_permissions_from_payload(payload)
    bot_user = BotAuthorizedUser(
        organization_id=admin.organization_id,
        aad_object_id=aad_object_id,
        display_name=payload.display_name.strip(),
        user_principal_name=payload.user_principal_name.strip(),
        role_id=access_role.id if access_role else None,
        role=_role_label_for_grant(access_role, payload.role),
        is_active=payload.is_active,
        created_by_id=admin.id,
        updated_by_id=admin.id,
        **permissions,
    )
    db.add(bot_user)
    db.flush()
    record_audit(
        db,
        action="admin.bot_user.created",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata=_bot_user_audit_metadata(bot_user),
    )
    db.commit()
    return bot_user


@router.patch("/bot-users/{bot_user_id}", response_model=BotAuthorizedUserOut, dependencies=[Depends(require_csrf)])
def update_bot_authorized_user(
    bot_user_id: str,
    payload: BotAuthorizedUserUpdateIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    bot_user = _get_org_bot_user(db, admin.organization_id, bot_user_id)
    before = _bot_user_audit_metadata(bot_user)
    if payload.display_name is not None:
        bot_user.display_name = payload.display_name.strip()
    if payload.user_principal_name is not None:
        bot_user.user_principal_name = payload.user_principal_name.strip()
    if payload.is_active is not None:
        bot_user.is_active = payload.is_active

    payload_data = payload.model_dump(exclude_unset=True)
    permission_patch = {
        field: value
        for field, value in payload_data.items()
        if field in BOT_PERMISSION_FIELDS and value is not None
    }
    if "role_id" in payload_data or payload.role is not None:
        access_role = _resolve_payload_bot_role(db, admin.organization_id, payload.role_id, payload.role)
        bot_user.role_id = access_role.id if access_role else None
        bot_user.role = _role_label_for_grant(access_role, payload.role)
        if access_role is not None:
            for field, value in role_permissions(access_role).items():
                setattr(bot_user, field, value)
            permission_patch = {}
    for field, value in permission_patch.items():
        setattr(bot_user, field, value)
    if permission_patch and bot_user.role_id is None:
        bot_user.role = _infer_bot_role(bot_user)
    bot_user.updated_by_id = admin.id
    bot_user.updated_at = utcnow()
    record_audit(
        db,
        action="admin.bot_user.updated",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"before": before, "after": _bot_user_audit_metadata(bot_user)},
    )
    db.commit()
    return bot_user


@router.delete("/bot-users/{bot_user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
def delete_bot_authorized_user(
    bot_user_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    bot_user = _get_org_bot_user(db, admin.organization_id, bot_user_id)
    metadata = _bot_user_audit_metadata(bot_user)
    db.delete(bot_user)
    record_audit(
        db,
        action="admin.bot_user.deleted",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata=metadata,
    )
    db.commit()
    return None


@router.get("/bot-groups", response_model=list[BotAuthorizedGroupOut], dependencies=[Depends(require_csrf)])
def list_bot_authorized_groups(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    ensure_bot_access_system_roles(db, admin.organization_id, actor_id=admin.id)
    _backfill_bot_access_role_assignments(db, admin.organization_id)
    db.commit()
    return db.scalars(
        select(BotAuthorizedGroup)
        .where(BotAuthorizedGroup.organization_id == admin.organization_id)
        .order_by(BotAuthorizedGroup.display_name.asc(), BotAuthorizedGroup.created_at.desc())
    ).all()


@router.post(
    "/bot-groups",
    response_model=BotAuthorizedGroupOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_bot_authorized_group(
    payload: BotAuthorizedGroupCreateIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    group_object_id = _normalize_aad_object_id(payload.group_object_id)
    _ensure_bot_group_available(db, admin.organization_id, group_object_id)
    access_role = _resolve_payload_bot_role(db, admin.organization_id, payload.role_id, payload.role)
    permissions = role_permissions(access_role) if access_role is not None else _bot_permissions_from_payload(payload)
    bot_group = BotAuthorizedGroup(
        organization_id=admin.organization_id,
        group_object_id=group_object_id,
        display_name=payload.display_name.strip(),
        mail=payload.mail.strip(),
        security_enabled=payload.security_enabled,
        group_types_json=_serialize_group_types(payload.group_types),
        role_id=access_role.id if access_role else None,
        role=_role_label_for_grant(access_role, payload.role),
        is_active=payload.is_active,
        created_by_id=admin.id,
        updated_by_id=admin.id,
        **permissions,
    )
    db.add(bot_group)
    db.flush()
    record_audit(
        db,
        action="admin.bot_group.created",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata=_bot_group_audit_metadata(bot_group),
    )
    db.commit()
    return bot_group


@router.patch("/bot-groups/{bot_group_id}", response_model=BotAuthorizedGroupOut, dependencies=[Depends(require_csrf)])
def update_bot_authorized_group(
    bot_group_id: str,
    payload: BotAuthorizedGroupUpdateIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    bot_group = _get_org_bot_group(db, admin.organization_id, bot_group_id)
    before = _bot_group_audit_metadata(bot_group)
    if payload.display_name is not None:
        bot_group.display_name = payload.display_name.strip()
    if payload.mail is not None:
        bot_group.mail = payload.mail.strip()
    if payload.security_enabled is not None:
        bot_group.security_enabled = payload.security_enabled
    if payload.group_types is not None:
        bot_group.group_types_json = _serialize_group_types(payload.group_types)
    if payload.is_active is not None:
        bot_group.is_active = payload.is_active

    payload_data = payload.model_dump(exclude_unset=True)
    permission_patch = {
        field: value
        for field, value in payload_data.items()
        if field in BOT_PERMISSION_FIELDS and value is not None
    }
    if "role_id" in payload_data or payload.role is not None:
        access_role = _resolve_payload_bot_role(db, admin.organization_id, payload.role_id, payload.role)
        bot_group.role_id = access_role.id if access_role else None
        bot_group.role = _role_label_for_grant(access_role, payload.role)
        if access_role is not None:
            for field, value in role_permissions(access_role).items():
                setattr(bot_group, field, value)
            permission_patch = {}
    for field, value in permission_patch.items():
        setattr(bot_group, field, value)
    if permission_patch and bot_group.role_id is None:
        bot_group.role = _infer_bot_role(bot_group)
    bot_group.updated_by_id = admin.id
    bot_group.updated_at = utcnow()
    record_audit(
        db,
        action="admin.bot_group.updated",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"before": before, "after": _bot_group_audit_metadata(bot_group)},
    )
    db.commit()
    return bot_group


@router.delete("/bot-groups/{bot_group_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
def delete_bot_authorized_group(
    bot_group_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    bot_group = _get_org_bot_group(db, admin.organization_id, bot_group_id)
    metadata = _bot_group_audit_metadata(bot_group)
    db.delete(bot_group)
    record_audit(
        db,
        action="admin.bot_group.deleted",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata=metadata,
    )
    db.commit()
    return None


def _normalize_aad_object_id(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AAD object ID is required")
    return normalized


def _ensure_bot_user_available(db: Session, organization_id: str, aad_object_id: str) -> None:
    existing = db.scalar(
        select(BotAuthorizedUser).where(
            BotAuthorizedUser.organization_id == organization_id,
            BotAuthorizedUser.aad_object_id == aad_object_id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A bot access user with this AAD object ID already exists")


def _ensure_bot_group_available(db: Session, organization_id: str, group_object_id: str) -> None:
    existing = db.scalar(
        select(BotAuthorizedGroup).where(
            BotAuthorizedGroup.organization_id == organization_id,
            BotAuthorizedGroup.group_object_id == group_object_id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A bot access group with this object ID already exists")


def _get_org_bot_user(db: Session, organization_id: str, bot_user_id: str) -> BotAuthorizedUser:
    bot_user = db.scalar(select(BotAuthorizedUser).where(BotAuthorizedUser.id == bot_user_id, BotAuthorizedUser.organization_id == organization_id))
    if bot_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot access user not found")
    return bot_user


def _get_org_bot_group(db: Session, organization_id: str, bot_group_id: str) -> BotAuthorizedGroup:
    bot_group = db.scalar(
        select(BotAuthorizedGroup).where(
            BotAuthorizedGroup.id == bot_group_id,
            BotAuthorizedGroup.organization_id == organization_id,
        )
    )
    if bot_group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot access group not found")
    return bot_group


def _get_org_bot_role(db: Session, organization_id: str, bot_role_id: str) -> BotAccessRole:
    role = db.scalar(
        select(BotAccessRole).where(
            BotAccessRole.id == bot_role_id,
            BotAccessRole.organization_id == organization_id,
        )
    )
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot access role not found")
    return role


def _ensure_bot_role_name_available(
    db: Session,
    organization_id: str,
    name: str,
    *,
    existing_role_id: str | None = None,
) -> None:
    normalized = name.strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bot access role name is required")
    existing = db.scalar(
        select(BotAccessRole).where(
            BotAccessRole.organization_id == organization_id,
            func.lower(BotAccessRole.name) == normalized.lower(),
        )
    )
    if existing is not None and existing.id != existing_role_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A bot access role with this name already exists")


def _resolve_payload_bot_role(
    db: Session,
    organization_id: str,
    role_id: str | None,
    role: str | None,
) -> BotAccessRole | None:
    if role_id:
        return _get_org_bot_role(db, organization_id, role_id)
    if role in {"route_viewer", "viewer"}:
        return _get_system_bot_role(db, organization_id, ROUTE_VIEWER_SYSTEM_KEY)
    if role in {"route_operator", "operator", "route_manager"}:
        return _get_system_bot_role(db, organization_id, ROUTE_OPERATOR_SYSTEM_KEY)
    return None


def _get_system_bot_role(db: Session, organization_id: str, system_key: str) -> BotAccessRole:
    roles = ensure_bot_access_system_roles(db, organization_id)
    return roles[system_key]


def _role_label_for_grant(access_role: BotAccessRole | None, requested_role: str | None) -> str:
    if access_role is None:
        return requested_role or "custom"
    return access_role.system_key or "role"


def _bot_permissions_from_payload(payload: BotAuthorizedUserCreateIn | BotAuthorizedGroupCreateIn) -> dict[str, bool]:
    return {field: bool(getattr(payload, field)) for field in BOT_PERMISSION_FIELDS}


def _infer_bot_role(grant) -> str:
    permissions = {field: bool(getattr(grant, field)) for field in BOT_PERMISSION_FIELDS}
    if permissions == role_permissions(_get_cached_role_for_infer(grant, ROUTE_VIEWER_SYSTEM_KEY)):
        return "route_viewer"
    if permissions == role_permissions(_get_cached_role_for_infer(grant, ROUTE_OPERATOR_SYSTEM_KEY)):
        return "route_operator"
    return "custom"


def _get_cached_role_for_infer(grant, system_key: str) -> BotAccessRole | None:
    session = object_session(grant)
    if session is None:
        return None
    return session.scalar(
        select(BotAccessRole).where(
            BotAccessRole.organization_id == grant.organization_id,
            BotAccessRole.system_key == system_key,
        )
    )


def _backfill_bot_access_role_assignments(db: Session, organization_id: str) -> None:
    roles = ensure_bot_access_system_roles(db, organization_id)
    viewer = roles[ROUTE_VIEWER_SYSTEM_KEY]
    operator = roles[ROUTE_OPERATOR_SYSTEM_KEY]
    for grant in [
        *db.scalars(select(BotAuthorizedUser).where(BotAuthorizedUser.organization_id == organization_id, BotAuthorizedUser.role_id.is_(None))).all(),
        *db.scalars(select(BotAuthorizedGroup).where(BotAuthorizedGroup.organization_id == organization_id, BotAuthorizedGroup.role_id.is_(None))).all(),
    ]:
        if grant.role == "custom":
            continue
        permissions = {field: bool(getattr(grant, field)) for field in BOT_PERMISSION_FIELDS}
        if grant.role in {"viewer", "route_viewer"} and permissions == role_permissions(viewer):
            grant.role_id = viewer.id
            grant.role = viewer.system_key or "route_viewer"
        elif grant.role in {"operator", "route_operator", "route_manager"} and permissions == role_permissions(operator):
            grant.role_id = operator.id
            grant.role = operator.system_key or "route_operator"
        elif grant.role in {"viewer", "operator", "route_manager"}:
            grant.role = "custom"


def _sync_linked_bot_role_grants(db: Session, role: BotAccessRole) -> None:
    permissions = role_permissions(role)
    role_label = _role_label_for_grant(role, None)
    for grant in [
        *db.scalars(select(BotAuthorizedUser).where(BotAuthorizedUser.role_id == role.id)).all(),
        *db.scalars(select(BotAuthorizedGroup).where(BotAuthorizedGroup.role_id == role.id)).all(),
    ]:
        for field, value in permissions.items():
            setattr(grant, field, value)
        grant.role = role_label
        grant.updated_at = utcnow()


def _bot_user_audit_metadata(bot_user: BotAuthorizedUser) -> dict:
    return {
        "bot_user_id": bot_user.id,
        "aad_object_id": bot_user.aad_object_id,
        "display_name": bot_user.display_name,
        "user_principal_name": bot_user.user_principal_name,
        "role_id": bot_user.role_id,
        "role": bot_user.role,
        "is_active": bot_user.is_active,
        "permissions": {field: bool(getattr(bot_user, field)) for field in BOT_PERMISSION_FIELDS},
    }


def _bot_group_audit_metadata(bot_group: BotAuthorizedGroup) -> dict:
    return {
        "bot_group_id": bot_group.id,
        "group_object_id": bot_group.group_object_id,
        "display_name": bot_group.display_name,
        "mail": bot_group.mail,
        "security_enabled": bot_group.security_enabled,
        "group_types": bot_group.group_types,
        "role_id": bot_group.role_id,
        "role": bot_group.role,
        "is_active": bot_group.is_active,
        "permissions": {field: bool(getattr(bot_group, field)) for field in BOT_PERMISSION_FIELDS},
    }


def _bot_role_audit_metadata(role: BotAccessRole) -> dict:
    return {
        "bot_role_id": role.id,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "system_key": role.system_key,
        "permissions": {field: bool(getattr(role, field)) for field in BOT_PERMISSION_FIELDS},
    }


def _serialize_group_types(values: list[str]) -> str:
    return dumps_json([str(value).strip() for value in values if str(value).strip()])


def _normalize_user_email(email: str) -> str:
    value = str(email or "").strip().lower()
    if "@" not in value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A valid email address is required")
    return value


def _get_org_user(db: Session, organization_id: str, user_id: str) -> User:
    user = db.scalar(select(User).where(User.id == user_id, User.organization_id == organization_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _ensure_user_email_available(db: Session, organization_id: str, email: str, user_id: str | None = None) -> None:
    existing = db.scalar(select(User).where(User.organization_id == organization_id, User.email == email))
    if existing is not None and existing.id != user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists")


def _ensure_user_update_allowed(
    db: Session,
    *,
    actor: User,
    user: User,
    next_is_admin: bool,
    next_is_active: bool,
) -> None:
    if user.id == actor.id and not next_is_admin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot remove your own admin access")
    if user.id == actor.id and not next_is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate your own user")
    if user.is_admin and user.is_active and (not next_is_admin or not next_is_active):
        active_admins = db.scalars(
            select(User.id).where(
                User.organization_id == actor.organization_id,
                User.is_admin.is_(True),
                User.is_active.is_(True),
            )
        ).all()
        if len(active_admins) <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one active admin is required")


def _revoke_user_sessions(db: Session, user_id: str, exclude_session_id: str | None = None) -> int:
    filters = [UserSession.user_id == user_id, UserSession.revoked_at.is_(None)]
    if exclude_session_id:
        filters.append(UserSession.id != exclude_session_id)
    sessions = db.scalars(select(UserSession).where(*filters)).all()
    revoked_at = utcnow()
    for session in sessions:
        session.revoked_at = revoked_at
    return len(sessions)


def _record_session_revocation(db: Session, admin: User, user: User, revoked_sessions: int, reason: str) -> None:
    record_audit(
        db,
        action="admin.user.sessions_revoked",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"user_id": user.id, "email": user.email, "count": revoked_sessions, "reason": reason},
    )


@router.get("/readiness", response_model=AdminReadinessOut, dependencies=[Depends(require_csrf)])
def readiness(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _admin_readiness(db, admin)


@router.post("/delivery-auth/refresh", response_model=DeliveryAuthRefreshOut, dependencies=[Depends(require_csrf)])
def refresh_delivery_auth(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    settings = get_effective_settings()
    refreshed_at = utcnow()
    bot_delivery = _refresh_bot_delivery_token(settings)
    graph_lookup = _refresh_graph_lookup_token(settings)
    graph_delivery = _refresh_graph_delivery_token(db, admin.organization_id, settings)
    bot_inbound_auth = _refresh_bot_inbound_auth_cache()
    components = {
        "bot_delivery": bot_delivery,
        "graph_lookup": graph_lookup,
        "graph_delivery": graph_delivery,
        "bot_inbound_auth": bot_inbound_auth,
    }
    record_audit(
        db,
        action="delivery_auth.tokens_refreshed",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={
            "components": {key: value.status for key, value in components.items()},
        },
    )
    readiness_out = _admin_readiness(db, admin, settings=settings)
    db.commit()
    return DeliveryAuthRefreshOut(
        ok=not any(component.status == "failed" for component in components.values()),
        refreshed_at=refreshed_at,
        bot_delivery=bot_delivery,
        graph_lookup=graph_lookup,
        graph_delivery=graph_delivery,
        bot_inbound_auth=bot_inbound_auth,
        readiness=readiness_out,
    )


def _admin_readiness(db: Session, admin: User, settings=None) -> AdminReadinessOut:
    settings = settings or get_effective_settings()
    delivery_mode = settings.bot_delivery_mode_normalized
    bot = _bot_readiness(settings, delivery_mode) if settings.bot_framework_enabled else _disabled_bot_readiness(settings, delivery_mode)
    graph_lookup = _graph_lookup_readiness(settings) if settings.graph_lookup_enabled else _disabled_graph_lookup_readiness(settings)
    graph_delivery_enabled = settings.graph_delivery_enabled and settings.graph_lookup_enabled
    graph_delivery = (
        _graph_delivery_readiness(db, admin.organization_id, settings)
        if graph_delivery_enabled
        else _disabled_graph_delivery_readiness(settings, graph_lookup_enabled=settings.graph_lookup_enabled)
    )
    if graph_delivery.token_checked:
        db.commit()

    return AdminReadinessOut(
        app_name=settings.app_name,
        app_version=settings.app_version,
        delivery_mode=delivery_mode,
        bot=bot,
        graph_lookup=graph_lookup,
        graph_delivery=graph_delivery,
        runtime=RuntimeReadinessOut(
            app_public_base_url=settings.app_public_base_url,
            frontend_base_url=settings.frontend_base_url,
            cors_origins=settings.cors_origin_list,
            compose_app_subnet=settings.compose_app_subnet,
            trusted_proxy_ips=settings.trusted_proxy_ips,
            trusted_proxy_chain=combined_trusted_proxy_ips(settings.compose_app_subnet, settings.trusted_proxy_ips),
            webhook_max_payload_bytes=settings.webhook_max_payload_bytes,
            webhook_url_reveal_ttl_hours=settings.webhook_url_reveal_ttl_hours,
            log_retention_days=settings.log_retention_days,
            log_cleanup_interval_minutes=settings.log_cleanup_interval_minutes,
            event_debug_previews_enabled=settings.event_debug_previews_enabled,
            session_secure_cookie=settings.session_secure_cookie,
            settings_encryption_key_source=settings.settings_enc_key_source,
            settings_encryption_ready=bool(settings.settings_enc_key.strip()),
        ),
    )


def _refresh_bot_delivery_token(settings) -> DeliveryAuthRefreshComponentOut:
    reset_bot_token_manager()
    if not settings.bot_framework_enabled:
        return DeliveryAuthRefreshComponentOut(status="skipped", message="Bot Framework delivery is disabled by feature policy.")
    if settings.bot_delivery_mode_normalized != "real":
        return DeliveryAuthRefreshComponentOut(status="skipped", message="Bot Framework delivery is in mock mode; no delivery token is requested.")
    try:
        get_token_manager().get_token()
    except BotDeliveryError:
        return DeliveryAuthRefreshComponentOut(
            status="failed",
            message="Bot Framework delivery token refresh failed. Check tenant ID, client ID, client secret and app permissions.",
        )
    return DeliveryAuthRefreshComponentOut(status="refreshed", message="Bot Framework delivery token was refreshed.")


def _refresh_graph_lookup_token(settings) -> DeliveryAuthRefreshComponentOut:
    reset_graph_token_manager()
    if not settings.graph_lookup_enabled:
        return DeliveryAuthRefreshComponentOut(status="skipped", message="Microsoft Graph lookup is disabled by feature policy.")
    try:
        get_graph_token_manager().get_token()
    except GraphConfigError:
        return DeliveryAuthRefreshComponentOut(
            status="failed",
            message="Microsoft Graph lookup token refresh failed because app credentials are incomplete.",
        )
    except GraphRequestError:
        return DeliveryAuthRefreshComponentOut(
            status="failed",
            message="Microsoft Graph lookup token refresh failed. Check credentials, tenant and app permissions.",
        )
    return DeliveryAuthRefreshComponentOut(status="refreshed", message="Microsoft Graph lookup token was refreshed.")


def _refresh_graph_delivery_token(db: Session, organization_id: str, settings) -> DeliveryAuthRefreshComponentOut:
    if not settings.graph_delivery_enabled:
        return DeliveryAuthRefreshComponentOut(status="skipped", message="Delegated Graph delivery is disabled by feature policy.")
    if not settings.graph_lookup_enabled:
        return DeliveryAuthRefreshComponentOut(status="skipped", message="Delegated Graph delivery is disabled because Graph lookup is disabled.")
    diagnostics = diagnostics_for_organization(db, organization_id)
    if not diagnostics.configured:
        return DeliveryAuthRefreshComponentOut(status="skipped", message="Delegated Graph delivery has no connected service user.")
    try:
        refresh_delegated_access_token(
            db,
            organization_id=organization_id,
            settings=settings,
            scopes=DEFAULT_DELEGATED_GRAPH_SCOPES,
        )
    except GraphDelegatedConfigError:
        return DeliveryAuthRefreshComponentOut(
            status="failed",
            message="Delegated Graph delivery token refresh failed because app registration settings are incomplete.",
        )
    except HTTPException as exc:
        detail = str(exc.detail)
        if "SETTINGS_ENC_KEY" in detail:
            return DeliveryAuthRefreshComponentOut(status="failed", message=detail)
        raise
    except GraphDelegatedAuthError:
        return DeliveryAuthRefreshComponentOut(
            status="failed",
            message="Delegated Graph delivery token refresh failed. Reconnect the service user if the token is expired or revoked.",
        )
    return DeliveryAuthRefreshComponentOut(status="refreshed", message="Delegated Graph delivery token was refreshed.")


def _refresh_bot_inbound_auth_cache() -> DeliveryAuthRefreshComponentOut:
    reset_bot_framework_auth_cache()
    return DeliveryAuthRefreshComponentOut(status="cleared", message="Bot Framework inbound authentication signing-key cache was cleared.")


def _graph_delivery_redirect_uri(settings) -> str:
    return f"{settings.app_public_base_url.rstrip('/')}{settings.api_v1_prefix.rstrip('/')}/admin/graph-delivery/oauth/callback"


def _graph_delivery_settings_redirect(settings, result: str) -> RedirectResponse:
    base = settings.frontend_base_url.rstrip("/")
    return RedirectResponse(f"{base}/settings?graph_delivery={urllib.parse.quote(result)}", status_code=status.HTTP_303_SEE_OTHER)


def _graph_delivery_pending_redirect(settings, pending_id: str) -> RedirectResponse:
    base = settings.frontend_base_url.rstrip("/")
    return RedirectResponse(
        f"{base}/settings/graph-delivery/confirm?pending_id={urllib.parse.quote(pending_id)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _get_live_graph_delivery_pending(db: Session, organization_id: str, pending_id: str):
    pending = get_pending_delegated_credential_by_id(db, organization_id=organization_id, pending_id=pending_id)
    if pending is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending delegated Graph connection was not found.")
    if pending_credential_is_expired(pending):
        db.delete(pending)
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending delegated Graph connection expired.")
    return pending


def _graph_delivery_pending_out(pending) -> GraphDeliveryOAuthPendingOut:
    diagnostics = diagnostics_for_pending_credential(pending)
    return GraphDeliveryOAuthPendingOut(
        id=pending.id,
        tenant_id=diagnostics.tenant_id,
        client_id=diagnostics.client_id,
        scopes=diagnostics.scopes or [],
        service_user_id=diagnostics.service_user_id,
        service_user_display_name=diagnostics.service_user_display_name,
        service_user_principal_name=diagnostics.service_user_principal_name,
        access_token_expires_at=diagnostics.access_token_expires_at,
        refresh_checked_at=diagnostics.refresh_checked_at,
        expires_at=ensure_utc(pending.expires_at) or pending.expires_at,
    )


def _issue_graph_oauth_state(admin: User, settings) -> str:
    payload = {
        "user_id": admin.id,
        "organization_id": admin.organization_id,
        "nonce": secrets.token_urlsafe(12),
        "expires_at": int(time.time()) + GRAPH_OAUTH_STATE_TTL_SECONDS,
    }
    encoded = _b64url_json(payload)
    signature = hmac.new(settings.session_secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _verify_graph_oauth_state(state: str, admin: User, settings) -> None:
    try:
        encoded, signature = state.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Microsoft Graph OAuth state") from exc
    expected = hmac.new(settings.session_secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Microsoft Graph OAuth state")
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Microsoft Graph OAuth state") from exc
    if payload.get("user_id") != admin.id or payload.get("organization_id") != admin.organization_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Microsoft Graph OAuth state does not match the current admin")
    if int(payload.get("expires_at") or 0) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Microsoft Graph OAuth state expired")


def _b64url_json(payload: dict) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).decode("utf-8")
    return encoded.rstrip("=")


def _bot_readiness(settings, delivery_mode: str) -> BotReadinessOut:
    credential_fields = {
        "tenant_id": _configured_status(settings.ms_app_tenant_id),
        "client_id": _configured_status(settings.ms_app_client_id),
        "client_secret": _configured_status(settings.ms_app_client_secret),
        "default_service_url": _configured_status(settings.bot_default_service_url),
    }
    credentials_configured = all(
        credential_fields[field] == "configured"
        for field in ["tenant_id", "client_id", "client_secret"]
    )
    oauth = _oauth_diagnostics(
        credential_source="ms_app",
        tenant_id=settings.ms_app_tenant_id,
        client_id=settings.ms_app_client_id,
        scope=settings.botframework_scope,
    )
    if delivery_mode == "mock":
        return BotReadinessOut(
            ready=True,
            auth_status="mock",
            token_checked=False,
            token_request_succeeded=False,
            mode=delivery_mode,
            credentials_configured=credentials_configured,
            default_service_url_configured=credential_fields["default_service_url"] == "configured",
            credential_fields=credential_fields,
            oauth=oauth,
            message="Mock delivery is active. Token checks are skipped and Teams messages are simulated.",
        )
    if not credentials_configured:
        return BotReadinessOut(
            ready=False,
            auth_status="incomplete",
            token_checked=False,
            token_request_succeeded=False,
            mode=delivery_mode,
            credentials_configured=False,
            default_service_url_configured=credential_fields["default_service_url"] == "configured",
            credential_fields=credential_fields,
            oauth=oauth,
            message="Real delivery requires MS_APP_TENANT_ID, MS_APP_CLIENT_ID and MS_APP_CLIENT_SECRET.",
        )
    try:
        token_response = _fetch_oauth_token(
            tenant_id=settings.ms_app_tenant_id,
            client_id=settings.ms_app_client_id,
            client_secret=settings.ms_app_client_secret,
            scope=settings.botframework_scope,
            config_error=BotDeliveryError,
            request_error=BotDeliveryError,
            missing_labels={
                "tenant_id": "MS_APP_TENANT_ID",
                "client_id": "MS_APP_CLIENT_ID",
                "client_secret": "MS_APP_CLIENT_SECRET",
            },
        )
    except BotDeliveryError:
        return BotReadinessOut(
            ready=False,
            auth_status="token_error",
            token_checked=True,
            token_request_succeeded=False,
            mode=delivery_mode,
            credentials_configured=True,
            default_service_url_configured=credential_fields["default_service_url"] == "configured",
            credential_fields=credential_fields,
            oauth=_oauth_diagnostics(
                credential_source="ms_app",
                tenant_id=settings.ms_app_tenant_id,
                client_id=settings.ms_app_client_id,
                scope=settings.botframework_scope,
                token=OAuthTokenDiagnosticsOut(checked=True, succeeded=False),
            ),
            message="Bot Framework token request failed. Check tenant ID, client ID, client secret and app permissions.",
        )
    oauth = _oauth_diagnostics(
        credential_source="ms_app",
        tenant_id=settings.ms_app_tenant_id,
        client_id=settings.ms_app_client_id,
        scope=settings.botframework_scope,
        token=_token_diagnostics(token_response),
        metadata=_metadata_for_credentials(
            tenant_id=settings.ms_app_tenant_id,
            client_id=settings.ms_app_client_id,
            client_secret=settings.ms_app_client_secret,
            scope=settings.graph_scope,
        ),
    )
    return BotReadinessOut(
        ready=True,
        auth_status="ready",
        token_checked=True,
        token_request_succeeded=True,
        mode=delivery_mode,
        credentials_configured=True,
        default_service_url_configured=credential_fields["default_service_url"] == "configured",
        credential_fields=credential_fields,
        oauth=oauth,
        message="Bot Framework token request succeeded. Delivery still requires a valid Teams conversation reference and bot permissions.",
    )


def _disabled_bot_readiness(settings, delivery_mode: str) -> BotReadinessOut:
    credential_fields = {
        "tenant_id": _configured_status(settings.ms_app_tenant_id),
        "client_id": _configured_status(settings.ms_app_client_id),
        "client_secret": _configured_status(settings.ms_app_client_secret),
        "default_service_url": _configured_status(settings.bot_default_service_url),
    }
    return BotReadinessOut(
        enabled=False,
        ready=True,
        auth_status="disabled",
        token_checked=False,
        token_request_succeeded=False,
        mode=delivery_mode,
        credentials_configured=all(
            credential_fields[field] == "configured"
            for field in ["tenant_id", "client_id", "client_secret"]
        ),
        default_service_url_configured=credential_fields["default_service_url"] == "configured",
        credential_fields=credential_fields,
        oauth=_oauth_diagnostics(
            credential_source="disabled",
            tenant_id=settings.ms_app_tenant_id,
            client_id=settings.ms_app_client_id,
            scope=settings.botframework_scope,
        ),
        message="Bot Framework delivery is disabled by feature policy.",
    )


def _graph_lookup_readiness(settings) -> GraphReadinessOut:
    credential_fields = {
        "tenant_id": _configured_status(settings.ms_app_tenant_id),
        "client_id": _configured_status(settings.ms_app_client_id),
        "client_secret": _configured_status(settings.ms_app_client_secret),
    }
    credentials_configured = all(status == "configured" for status in credential_fields.values())
    credential_source = "ms_app" if credentials_configured else "missing"
    oauth = _oauth_diagnostics(
        credential_source=credential_source,
        tenant_id=settings.ms_app_tenant_id,
        client_id=settings.ms_app_client_id,
        scope=settings.graph_scope,
    )

    if not credentials_configured:
        return GraphReadinessOut(
            ready=False,
            auth_status="incomplete",
            token_checked=False,
            token_request_succeeded=False,
            configured=False,
            credential_source=credential_source,
            credential_fields=credential_fields,
            oauth=oauth,
            message="Graph lookup requires MS_APP_TENANT_ID, MS_APP_CLIENT_ID and MS_APP_CLIENT_SECRET.",
        )
    try:
        token_response = _fetch_oauth_token(
            tenant_id=settings.ms_app_tenant_id,
            client_id=settings.ms_app_client_id,
            client_secret=settings.ms_app_client_secret,
            scope=settings.graph_scope,
            config_error=GraphConfigError,
            request_error=GraphRequestError,
            missing_labels={
                "tenant_id": "MS_APP_TENANT_ID",
                "client_id": "MS_APP_CLIENT_ID",
                "client_secret": "MS_APP_CLIENT_SECRET",
            },
        )
    except GraphConfigError:
        return GraphReadinessOut(
            ready=False,
            auth_status="incomplete",
            token_checked=False,
            token_request_succeeded=False,
            configured=False,
            credential_source="missing",
            credential_fields=credential_fields,
            oauth=oauth,
            message="Graph lookup credentials are incomplete.",
        )
    except GraphRequestError:
        return GraphReadinessOut(
            ready=False,
            auth_status="token_error",
            token_checked=True,
            token_request_succeeded=False,
            configured=True,
            credential_source=credential_source,
            credential_fields=credential_fields,
            oauth=_oauth_diagnostics(
                credential_source=credential_source,
                tenant_id=settings.ms_app_tenant_id,
                client_id=settings.ms_app_client_id,
                scope=settings.graph_scope,
                token=OAuthTokenDiagnosticsOut(checked=True, succeeded=False),
            ),
            message="Microsoft Graph token request failed. Check credentials, tenant and app permissions.",
        )
    oauth = _oauth_diagnostics(
        credential_source=credential_source,
        tenant_id=settings.ms_app_tenant_id,
        client_id=settings.ms_app_client_id,
        scope=settings.graph_scope,
        token=_token_diagnostics(token_response),
        metadata=_metadata_from_graph_token(token_response.access_token, settings.ms_app_client_id),
    )
    metadata_available = oauth.app.available and oauth.tenant.available
    group_membership = _graph_group_membership_readiness(oauth.token.roles)
    return GraphReadinessOut(
        ready=True,
        auth_status="ready" if metadata_available else "permission_warning",
        token_checked=True,
        token_request_succeeded=True,
        configured=True,
        credential_source=credential_source,
        credential_fields=credential_fields,
        oauth=oauth,
        group_membership_lookup_ready=group_membership["ready"],
        group_membership_required_roles=list(GRAPH_GROUP_MEMBERSHIP_REQUIRED_ROLES),
        group_membership_alternative_roles=list(GRAPH_GROUP_MEMBERSHIP_ALTERNATIVE_ROLES),
        group_membership_missing_roles=group_membership["missing_roles"],
        group_membership_message=group_membership["message"],
        message=(
            "Microsoft Graph token request succeeded. Lookup and readiness diagnostics are available."
            if metadata_available
            else "Microsoft Graph token request succeeded. Lookup can still work, but optional directory metadata is limited by tenant permissions."
        ),
    )


def _graph_group_membership_readiness(roles: list[str]) -> dict:
    granted = {role.lower() for role in roles}
    has_required = any(role.lower() in granted for role in GRAPH_GROUP_MEMBERSHIP_REQUIRED_ROLES)
    has_alternative = any(role.lower() in granted for role in GRAPH_GROUP_MEMBERSHIP_ALTERNATIVE_ROLES)
    ready = has_required or has_alternative
    missing_roles = [] if ready else list(GRAPH_GROUP_MEMBERSHIP_REQUIRED_ROLES)
    return {
        "ready": ready,
        "missing_roles": missing_roles,
        "message": (
            "Bot Access group search and membership checks have a suitable Microsoft Graph app role."
            if ready
            else "Bot Access groups require GroupMember.Read.All or a broader directory-read app role such as Directory.Read.All."
        ),
    }


def _disabled_graph_lookup_readiness(settings) -> GraphReadinessOut:
    credential_fields = {
        "tenant_id": _configured_status(settings.ms_app_tenant_id),
        "client_id": _configured_status(settings.ms_app_client_id),
        "client_secret": _configured_status(settings.ms_app_client_secret),
    }
    return GraphReadinessOut(
        enabled=False,
        ready=True,
        auth_status="disabled",
        token_checked=False,
        token_request_succeeded=False,
        configured=all(status == "configured" for status in credential_fields.values()),
        credential_source="disabled",
        credential_fields=credential_fields,
        oauth=_oauth_diagnostics(
            credential_source="disabled",
            tenant_id=settings.ms_app_tenant_id,
            client_id=settings.ms_app_client_id,
            scope=settings.graph_scope,
        ),
        group_membership_required_roles=list(GRAPH_GROUP_MEMBERSHIP_REQUIRED_ROLES),
        group_membership_alternative_roles=list(GRAPH_GROUP_MEMBERSHIP_ALTERNATIVE_ROLES),
        group_membership_missing_roles=list(GRAPH_GROUP_MEMBERSHIP_REQUIRED_ROLES),
        group_membership_message="Graph lookup is disabled, so Bot Access group membership cannot be checked.",
        message="Microsoft Graph lookup is disabled by feature policy.",
    )


def _graph_delivery_readiness(db: Session, organization_id: str, settings) -> GraphDeliveryReadinessOut:
    diagnostics = diagnostics_for_organization(db, organization_id)
    required_scopes = list(DEFAULT_DELEGATED_GRAPH_SCOPES)
    credential_source = "delegated_service_user" if diagnostics.configured else "missing"

    if not diagnostics.configured:
        return _graph_delivery_readiness_out(
            diagnostics=diagnostics,
            settings=settings,
            required_scopes=required_scopes,
            credential_source=credential_source,
            ready=False,
            auth_status="missing",
            token_checked=False,
            token_request_succeeded=False,
            message="Delegated Graph delivery has not been configured.",
        )

    try:
        access_token = refresh_delegated_access_token(
            db,
            organization_id=organization_id,
            settings=settings,
            scopes=DEFAULT_DELEGATED_GRAPH_SCOPES,
        )
        diagnostics = access_token.diagnostics
    except GraphDelegatedConfigError:
        diagnostics = diagnostics_for_organization(db, organization_id)
        return _graph_delivery_readiness_out(
            diagnostics=diagnostics,
            settings=settings,
            required_scopes=required_scopes,
            credential_source=credential_source,
            ready=False,
            auth_status="incomplete",
            token_checked=False,
            token_request_succeeded=False,
            message="Delegated Graph delivery requires MS_APP_TENANT_ID, MS_APP_CLIENT_ID and MS_APP_CLIENT_SECRET.",
        )
    except HTTPException as exc:
        detail = str(exc.detail)
        if "SETTINGS_ENC_KEY" not in detail:
            raise
        diagnostics = diagnostics_for_organization(db, organization_id)
        return _graph_delivery_readiness_out(
            diagnostics=diagnostics,
            settings=settings,
            required_scopes=required_scopes,
            credential_source=credential_source,
            ready=False,
            auth_status="configuration_error",
            token_checked=False,
            token_request_succeeded=False,
            message=detail,
        )
    except GraphDelegatedAuthError:
        diagnostics = diagnostics_for_organization(db, organization_id)
        auth_status = diagnostics.status if diagnostics.status in {"expired", "token_error"} else "token_error"
        message = (
            "Delegated Graph refresh token is expired or revoked. Reconnect the service user."
            if auth_status == "expired"
            else "Delegated Graph token refresh failed. Check the service-user connection and Microsoft tenant access."
        )
        return _graph_delivery_readiness_out(
            diagnostics=diagnostics,
            settings=settings,
            required_scopes=required_scopes,
            credential_source=credential_source,
            ready=False,
            auth_status=auth_status,
            token_checked=True,
            token_request_succeeded=False,
            message=message,
        )

    missing_scopes = _missing_required_scopes(diagnostics.scopes or [], required_scopes)
    if missing_scopes:
        return _graph_delivery_readiness_out(
            diagnostics=diagnostics,
            settings=settings,
            required_scopes=required_scopes,
            credential_source=credential_source,
            ready=False,
            auth_status="permission_warning",
            token_checked=True,
            token_request_succeeded=True,
            missing_scopes=missing_scopes,
            message=f"Delegated Graph token refresh succeeded, but required scopes are missing: {', '.join(missing_scopes)}.",
        )

    return _graph_delivery_readiness_out(
        diagnostics=diagnostics,
        settings=settings,
        required_scopes=required_scopes,
        credential_source=credential_source,
        ready=True,
        auth_status="ready",
        token_checked=True,
        token_request_succeeded=True,
        message="Delegated Graph token refresh succeeded. Graph delivery prerequisites are usable.",
    )


def _disabled_graph_delivery_readiness(settings, *, graph_lookup_enabled: bool) -> GraphDeliveryReadinessOut:
    message = (
        "Delegated Graph delivery is disabled because Graph lookup is disabled."
        if not graph_lookup_enabled
        else "Delegated Graph delivery is disabled by feature policy."
    )
    return GraphDeliveryReadinessOut(
        enabled=False,
        ready=True,
        auth_status="disabled",
        token_checked=False,
        token_request_succeeded=False,
        configured=False,
        credential_source="disabled",
        tenant_id=settings.ms_app_tenant_id,
        client_id=settings.ms_app_client_id,
        scopes=[],
        required_scopes=list(DEFAULT_DELEGATED_GRAPH_SCOPES),
        missing_scopes=[],
        service_user_id="",
        service_user_display_name="",
        service_user_principal_name="",
        access_token_expires_at=None,
        refresh_checked_at=None,
        message=message,
    )


def _graph_delivery_readiness_out(
    *,
    diagnostics,
    settings,
    required_scopes: list[str],
    credential_source: str,
    ready: bool,
    auth_status: str,
    token_checked: bool,
    token_request_succeeded: bool,
    message: str,
    missing_scopes: list[str] | None = None,
) -> GraphDeliveryReadinessOut:
    granted_scopes = diagnostics.scopes or []
    return GraphDeliveryReadinessOut(
        ready=ready,
        auth_status=auth_status,
        token_checked=token_checked,
        token_request_succeeded=token_request_succeeded,
        configured=diagnostics.configured,
        credential_source=credential_source,
        tenant_id=diagnostics.tenant_id or settings.ms_app_tenant_id,
        client_id=diagnostics.client_id or settings.ms_app_client_id,
        scopes=granted_scopes,
        required_scopes=required_scopes,
        missing_scopes=missing_scopes if missing_scopes is not None else _missing_required_scopes(granted_scopes, required_scopes),
        service_user_id=diagnostics.service_user_id,
        service_user_display_name=diagnostics.service_user_display_name,
        service_user_principal_name=diagnostics.service_user_principal_name,
        access_token_expires_at=diagnostics.access_token_expires_at,
        refresh_checked_at=diagnostics.refresh_checked_at,
        message=message,
    )


def _missing_required_scopes(granted_scopes: list[str], required_scopes: list[str]) -> list[str]:
    granted = {scope.lower() for scope in granted_scopes}
    return [scope for scope in required_scopes if scope.lower() not in granted]


def _fetch_oauth_token(
    *,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    scope: str,
    config_error,
    request_error,
    missing_labels: dict[str, str],
) -> OAuthTokenResponse:
    missing = [
        missing_labels[name]
        for name, value in {
            "tenant_id": tenant_id,
            "client_id": client_id,
            "client_secret": client_secret,
        }.items()
        if not value
    ]
    if missing:
        raise config_error(f"Missing OAuth credentials: {', '.join(missing)}")

    form = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise request_error("Failed to fetch OAuth access token") from exc

    access_token = str(body.get("access_token") or "")
    if not access_token:
        raise request_error("OAuth token response did not include an access token")
    return OAuthTokenResponse(
        access_token=access_token,
        expires_in_seconds=int(body.get("expires_in") or 3600),
        claims=_decode_jwt_claims(access_token),
    )


def _oauth_diagnostics(
    *,
    credential_source: str,
    tenant_id: str,
    client_id: str,
    scope: str,
    token: OAuthTokenDiagnosticsOut | None = None,
    metadata: tuple[OAuthAppDiagnosticsOut, OAuthTenantDiagnosticsOut] | None = None,
) -> OAuthDiagnosticsOut:
    app, tenant = metadata or (OAuthAppDiagnosticsOut(), OAuthTenantDiagnosticsOut())
    return OAuthDiagnosticsOut(
        credential_source=credential_source,
        tenant_id=tenant_id,
        client_id=client_id,
        scope=scope,
        token=token or OAuthTokenDiagnosticsOut(),
        app=app,
        tenant=tenant,
    )


def _token_diagnostics(response: OAuthTokenResponse) -> OAuthTokenDiagnosticsOut:
    claims = response.claims
    roles = claims.get("roles") if isinstance(claims.get("roles"), list) else []
    return OAuthTokenDiagnosticsOut(
        checked=True,
        succeeded=True,
        expires_in_seconds=response.expires_in_seconds,
        expires_at=utcnow() + timedelta(seconds=max(response.expires_in_seconds, 1)),
        audience=str(claims.get("aud") or ""),
        issuer=str(claims.get("iss") or ""),
        roles=[str(role) for role in roles],
    )


def _metadata_for_credentials(
    *,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    scope: str,
) -> tuple[OAuthAppDiagnosticsOut, OAuthTenantDiagnosticsOut]:
    try:
        token_response = _fetch_oauth_token(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            scope=scope,
            config_error=GraphConfigError,
            request_error=GraphRequestError,
            missing_labels={
                "tenant_id": "MS_APP_TENANT_ID",
                "client_id": "MS_APP_CLIENT_ID",
                "client_secret": "MS_APP_CLIENT_SECRET",
            },
        )
    except (GraphConfigError, GraphRequestError):
        return (
            OAuthAppDiagnosticsOut(
                metadata_checked=True,
                available=False,
                message="App metadata is not available with the current Graph permissions.",
            ),
            OAuthTenantDiagnosticsOut(
                metadata_checked=True,
                available=False,
                message="Tenant metadata is not available with the current Graph permissions.",
            ),
        )
    return _metadata_from_graph_token(token_response.access_token, client_id)


def _metadata_from_graph_token(access_token: str, client_id: str) -> tuple[OAuthAppDiagnosticsOut, OAuthTenantDiagnosticsOut]:
    return (
        _service_principal_metadata(access_token, client_id),
        _tenant_metadata(access_token),
    )


def _service_principal_metadata(access_token: str, client_id: str) -> OAuthAppDiagnosticsOut:
    try:
        data = _graph_get_with_token(
            access_token,
            "/servicePrincipals",
            {
                "$filter": f"appId eq '{_odata_string(client_id)}'",
                "$select": "id,appId,displayName,servicePrincipalType,accountEnabled,appOwnerOrganizationId",
            },
        )
    except GraphRequestError:
        return OAuthAppDiagnosticsOut(
            metadata_checked=True,
            available=False,
            message="App metadata is not available with the current Graph permissions.",
        )
    values = data.get("value") if isinstance(data.get("value"), list) else []
    app = values[0] if values and isinstance(values[0], dict) else {}
    if not app:
        return OAuthAppDiagnosticsOut(
            metadata_checked=True,
            available=False,
            message="No service principal was found for this client ID.",
        )
    return OAuthAppDiagnosticsOut(
        metadata_checked=True,
        available=True,
        display_name=str(app.get("displayName") or ""),
        app_id=str(app.get("appId") or ""),
        service_principal_id=str(app.get("id") or ""),
        account_enabled=app.get("accountEnabled") if isinstance(app.get("accountEnabled"), bool) else None,
        service_principal_type=str(app.get("servicePrincipalType") or ""),
    )


def _tenant_metadata(access_token: str) -> OAuthTenantDiagnosticsOut:
    try:
        data = _graph_get_with_token(
            access_token,
            "/organization",
            {"$select": "id,displayName,verifiedDomains"},
        )
    except GraphRequestError:
        return OAuthTenantDiagnosticsOut(
            metadata_checked=True,
            available=False,
            message="Tenant metadata is not available with the current Graph permissions.",
        )
    values = data.get("value") if isinstance(data.get("value"), list) else []
    tenant = values[0] if values and isinstance(values[0], dict) else {}
    if not tenant:
        return OAuthTenantDiagnosticsOut(
            metadata_checked=True,
            available=False,
            message="No tenant metadata was returned.",
        )
    domains = tenant.get("verifiedDomains") if isinstance(tenant.get("verifiedDomains"), list) else []
    primary_domain = ""
    for domain in domains:
        if isinstance(domain, dict) and domain.get("isDefault"):
            primary_domain = str(domain.get("name") or "")
            break
    if not primary_domain and domains and isinstance(domains[0], dict):
        primary_domain = str(domains[0].get("name") or "")
    return OAuthTenantDiagnosticsOut(
        metadata_checked=True,
        available=True,
        display_name=str(tenant.get("displayName") or ""),
        primary_domain=primary_domain,
    )


def _graph_get_with_token(access_token: str, path: str, params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"https://graph.microsoft.com/v1.0{path}?{query}",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        _ = exc.read()
        raise GraphRequestError("Microsoft Graph metadata request failed") from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GraphRequestError("Microsoft Graph metadata request failed") from exc


def _decode_jwt_claims(token: str) -> dict:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
        value = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _configured_status(value: str) -> str:
    return "configured" if value.strip() else "missing"


def _odata_string(value: str) -> str:
    return value.replace("'", "''")


@router.get("/webhook-abuse-buckets", response_model=list[WebhookAbuseBucketOut], dependencies=[Depends(require_csrf)])
def list_webhook_abuse_buckets(
    limit: int = Query(default=100, ge=1, le=250),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    settings = get_effective_settings()
    now = utcnow()
    observed_cutoff = now - timedelta(minutes=settings.webhook_abuse_window_minutes)
    rows = db.scalars(
        select(WebhookAbuseBucket)
        .where(
            or_(
                WebhookAbuseBucket.blocked_until > now,
                and_(
                    WebhookAbuseBucket.failure_count > 0,
                    WebhookAbuseBucket.window_started_at >= observed_cutoff,
                ),
            )
        )
        .order_by(WebhookAbuseBucket.last_seen_at.desc())
        .limit(limit)
    ).all()
    return [_webhook_abuse_bucket_out(row) for row in rows]


@router.delete(
    "/webhook-abuse-buckets/{bucket_id}",
    response_model=WebhookAbuseBucketOut,
    dependencies=[Depends(require_csrf)],
)
def reset_webhook_abuse_bucket(
    bucket_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    bucket = unblock_bucket(db, bucket_id)
    if bucket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook abuse bucket not found")
    record_audit(
        db,
        action="webhook_abuse_bucket.reset",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"bucket_id": bucket.id, "scope": bucket.scope},
    )
    db.commit()
    db.refresh(bucket)
    return _webhook_abuse_bucket_out(bucket)


@router.post(
    "/webhook-abuse-buckets/cleanup",
    response_model=WebhookAbuseCleanupOut,
    dependencies=[Depends(require_csrf)],
)
def cleanup_webhook_abuse_buckets(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    settings = get_effective_settings()
    result = cleanup_buckets(db)
    record_audit(
        db,
        action="webhook_abuse_bucket.cleanup",
        actor_type="user",
        actor_id=admin.id,
        organization_id=admin.organization_id,
        metadata={"deleted": result.deleted, "cleanup_days": settings.webhook_abuse_cleanup_days},
    )
    db.commit()
    return WebhookAbuseCleanupOut(
        deleted=result.deleted,
        cleanup_days=settings.webhook_abuse_cleanup_days,
        cutoff=result.cutoff,
    )


@router.get("/logs", response_model=list[AuditEventOut], dependencies=[Depends(require_csrf)])
def list_logs(
    limit: int = Query(default=100, ge=1, le=250),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cleanup_result = cleanup_log_events(db)
    if not cleanup_result.skipped:
        db.commit()
    rows = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.organization_id == admin.organization_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    ).all()
    return [
        AuditEventOut(
            id=row.id,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            action=row.action,
            metadata=loads_json(row.metadata_json, {}),
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/event-logs", response_model=EventLogEntryPageOut, dependencies=[Depends(require_csrf)])
def list_event_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=250),
    level: str = Query(default=""),
    category: str = Query(default=""),
    event_type: str = Query(default=""),
    correlation_id: str = Query(default=""),
    request_id: str = Query(default=""),
    q: str = Query(default=""),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    cleanup_result = cleanup_log_events(db)
    if not cleanup_result.skipped:
        db.commit()

    filters = []
    if level.strip():
        filters.append(EventLogEntry.level == level.strip())
    if category.strip():
        filters.append(EventLogEntry.category == category.strip())
    if event_type.strip():
        filters.append(EventLogEntry.event_type == event_type.strip())
    if correlation_id.strip():
        filters.append(EventLogEntry.correlation_id == correlation_id.strip())
    if request_id.strip():
        filters.append(EventLogEntry.request_id == request_id.strip())
    if q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                EventLogEntry.message.ilike(pattern),
                EventLogEntry.event_type.ilike(pattern),
                EventLogEntry.category.ilike(pattern),
                EventLogEntry.actor_json.ilike(pattern),
                EventLogEntry.target_json.ilike(pattern),
                EventLogEntry.source_json.ilike(pattern),
                EventLogEntry.http_json.ilike(pattern),
                EventLogEntry.security_json.ilike(pattern),
            )
        )

    total_query = select(func.count()).select_from(EventLogEntry)
    rows_query = select(EventLogEntry).order_by(EventLogEntry.created_at.desc())
    if filters:
        total_query = total_query.where(*filters)
        rows_query = rows_query.where(*filters)
    total = db.scalar(total_query) or 0
    rows = db.scalars(rows_query.offset((page - 1) * page_size).limit(page_size)).all()
    total_pages = max(1, (total + page_size - 1) // page_size)
    settings = get_effective_settings()
    return EventLogEntryPageOut(
        items=[EventLogEntryOut(**event_from_entry(row)) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        retention_days=max(0, settings.log_retention_days),
    )


@router.post("/client-events", response_model=EventLogEntryOut, dependencies=[Depends(require_csrf)])
def create_client_event(
    payload: ClientEventIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    event = emit_event(
        db,
        level=payload.level,
        category="frontend",
        event_type=payload.event_type,
        message=payload.message,
        correlation_id=payload.correlation_id or payload.request_id,
        request_id=payload.request_id,
        actor={"type": "admin", "id": admin.id, "displayName": admin.display_name},
        target={"type": "admin_ui", "path": payload.path, "action": payload.action},
        raw={"detail": payload.detail},
        domain="frontend",
    )
    db.commit()
    if event is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Client event could not be recorded")
    return EventLogEntryOut(**event_from_entry(event))


@router.get("/system-logs", response_model=list[SystemLogEventOut], dependencies=[Depends(require_csrf)])
def list_system_logs(
    limit: int = Query(default=100, ge=1, le=250),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    cleanup_result = cleanup_log_events(db)
    if not cleanup_result.skipped:
        db.commit()
    rows = db.scalars(select(BotActivityEvent).order_by(BotActivityEvent.created_at.desc()).limit(limit)).all()
    return [
        SystemLogEventOut(
            id=row.id,
            activity_type=row.activity_type,
            conversation_type=row.conversation_type,
            scope=_system_scope(row),
            team_name=row.team_name,
            channel_name=row.channel_name,
            user_name=row.user_name,
            service_url=row.service_url,
            conversation_id=row.conversation_id,
            tenant_id=row.tenant_id,
            team_id=row.team_id,
            graph_team_id=row.graph_team_id,
            channel_id=row.channel_id,
            graph_user_id=row.graph_user_id,
            auth_status=row.auth_status,
            auth_issuer=row.auth_issuer,
            auth_audience=row.auth_audience,
            auth_service_url=row.auth_service_url,
            auth_service_url_matched=row.auth_service_url_matched,
            auth_validated_at=row.auth_validated_at,
            bot_authorization_status=row.bot_authorization_status,
            bot_authorized_user_id=row.bot_authorized_user_id,
            bot_authorization_reason=row.bot_authorization_reason,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/logs/cleanup", response_model=LogCleanupOut, dependencies=[Depends(require_csrf)])
def cleanup_logs(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = admin
    cleanup_result = cleanup_log_events(db, force=True)
    db.commit()
    return LogCleanupOut(
        deleted=cleanup_result.deleted,
        deleted_webhook_delivery_events=cleanup_result.deleted_webhook_delivery_events,
        deleted_audit_events=cleanup_result.deleted_audit_events,
        deleted_bot_activity_events=cleanup_result.deleted_bot_activity_events,
        deleted_event_log_entries=cleanup_result.deleted_event_log_entries,
        retention_days=cleanup_result.retention_days,
        cutoff=cleanup_result.cutoff,
    )


def _system_scope(event: BotActivityEvent) -> str:
    if event.conversation_type == "personal":
        return "user"
    if event.team_id and event.channel_id:
        return "channel"
    if event.team_id:
        return "team"
    return event.conversation_type or "unknown"


def _webhook_abuse_bucket_out(bucket: WebhookAbuseBucket) -> WebhookAbuseBucketOut:
    blocked_until = ensure_utc(bucket.blocked_until)
    return WebhookAbuseBucketOut(
        id=bucket.id,
        scope=bucket.scope if bucket.scope in {"ip", "ip_route"} else "ip",
        status="blocked" if blocked_until and blocked_until > utcnow() else "watching",
        client_host=bucket.last_client_host,
        client_fingerprint=bucket.client_hash[:12],
        route_token_fingerprint=(bucket.route_token_hash or "")[:12],
        failure_count=bucket.failure_count,
        block_count=bucket.block_count,
        window_started_at=bucket.window_started_at,
        blocked_until=bucket.blocked_until,
        last_reason=bucket.last_reason,
        last_seen_at=bucket.last_seen_at,
        created_at=bucket.created_at,
    )
