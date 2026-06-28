from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_users_org_email"),)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    session_token_hash: Mapped[str] = mapped_column(Text, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class WebhookRoute(Base):
    __tablename__ = "webhook_routes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    route_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    route_token: Mapped[str] = mapped_column(Text, default="")
    delivery_backend: Mapped[str] = mapped_column(String(32), default="bot_framework")
    client_ip_access_mode: Mapped[str] = mapped_column(String(32), default="public")
    client_ip_allowlist: Mapped[str] = mapped_column(Text, default="")
    target_type: Mapped[str] = mapped_column(String(32), default="bot_conversation")
    target_name: Mapped[str] = mapped_column(String(200))
    bot_service_url: Mapped[str] = mapped_column(Text, default="")
    bot_conversation_id: Mapped[str] = mapped_column(Text, default="")
    graph_target_kind: Mapped[str] = mapped_column(String(32), default="")
    graph_target_id: Mapped[str] = mapped_column(Text, default="")
    graph_team_id: Mapped[str] = mapped_column(Text, default="")
    graph_team_name: Mapped[str] = mapped_column(String(200), default="")
    graph_channel_id: Mapped[str] = mapped_column(Text, default="")
    graph_user_id: Mapped[str] = mapped_column(Text, default="")
    graph_user_display_name: Mapped[str] = mapped_column(String(255), default="")
    graph_user_principal_name: Mapped[str] = mapped_column(String(255), default="")
    bot_target_source: Mapped[str] = mapped_column(String(40), default="")
    bot_registered_by_id: Mapped[str] = mapped_column(Text, default="")
    bot_registered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_delivery_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("organization_id", "name", "delivery_backend", name="uq_webhook_routes_org_name_backend"),
    )


class WebhookDeliveryEvent(Base):
    __tablename__ = "webhook_delivery_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    route_id: Mapped[str | None] = mapped_column(ForeignKey("webhook_routes.id"), nullable=True, index=True)
    route_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    request_metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    normalized_message_json: Mapped[str] = mapped_column(Text, default="{}")
    delivery_result_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class WebhookAbuseBucket(Base):
    __tablename__ = "webhook_abuse_buckets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    bucket_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)
    client_hash: Mapped[str] = mapped_column(String(64), index=True)
    last_client_host: Mapped[str] = mapped_column(Text, default="")
    route_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    failure_count: Mapped[int] = mapped_column(default=0)
    block_count: Mapped[int] = mapped_column(default=0)
    window_started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_reason: Mapped[str] = mapped_column(String(120), default="")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class BotActivityEvent(Base):
    __tablename__ = "bot_activity_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    activity_type: Mapped[str] = mapped_column(String(80), default="", index=True)
    service_url: Mapped[str] = mapped_column(Text, default="")
    conversation_id: Mapped[str] = mapped_column(Text, default="", index=True)
    tenant_id: Mapped[str] = mapped_column(Text, default="", index=True)
    team_id: Mapped[str] = mapped_column(Text, default="", index=True)
    graph_team_id: Mapped[str] = mapped_column(Text, default="", index=True)
    channel_id: Mapped[str] = mapped_column(Text, default="", index=True)
    conversation_type: Mapped[str] = mapped_column(String(40), default="")
    team_name: Mapped[str] = mapped_column(String(200), default="")
    channel_name: Mapped[str] = mapped_column(String(200), default="")
    from_id: Mapped[str] = mapped_column(Text, default="")
    user_name: Mapped[str] = mapped_column(String(200), default="")
    graph_user_id: Mapped[str] = mapped_column(Text, default="", index=True)
    recipient_id: Mapped[str] = mapped_column(Text, default="")
    raw_activity_json: Mapped[str] = mapped_column(Text, default="{}")
    auth_status: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    auth_issuer: Mapped[str] = mapped_column(Text, default="")
    auth_audience: Mapped[str] = mapped_column(Text, default="")
    auth_service_url: Mapped[str] = mapped_column(Text, default="")
    auth_service_url_matched: Mapped[bool] = mapped_column(Boolean, default=False)
    auth_validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class BotConversationReference(Base):
    __tablename__ = "bot_conversation_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(32), default="", index=True)
    service_url: Mapped[str] = mapped_column(Text, default="")
    conversation_id: Mapped[str] = mapped_column(Text, default="", index=True)
    tenant_id: Mapped[str] = mapped_column(Text, default="", index=True)
    team_id: Mapped[str] = mapped_column(Text, default="", index=True)
    graph_team_id: Mapped[str] = mapped_column(Text, default="", index=True)
    channel_id: Mapped[str] = mapped_column(Text, default="", index=True)
    conversation_type: Mapped[str] = mapped_column(String(40), default="")
    team_name: Mapped[str] = mapped_column(String(200), default="")
    channel_name: Mapped[str] = mapped_column(String(200), default="")
    user_id: Mapped[str] = mapped_column(Text, default="", index=True)
    user_name: Mapped[str] = mapped_column(String(200), default="")
    graph_user_id: Mapped[str] = mapped_column(Text, default="", index=True)
    raw_activity_type: Mapped[str] = mapped_column(String(80), default="")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("conversation_id", name="uq_bot_conversation_references_conversation_id"),
    )


class GraphDelegatedCredential(Base):
    __tablename__ = "graph_delegated_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(Text, default="")
    client_id: Mapped[str] = mapped_column(Text, default="")
    scopes: Mapped[str] = mapped_column(Text, default="")
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, default="")
    service_user_id: Mapped[str] = mapped_column(Text, default="")
    service_user_display_name: Mapped[str] = mapped_column(String(255), default="")
    service_user_principal_name: Mapped[str] = mapped_column(String(255), default="")
    last_status: Mapped[str] = mapped_column(String(40), default="missing", index=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    refresh_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (UniqueConstraint("organization_id", name="uq_graph_delegated_credentials_org"),)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(255), index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    updated_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
