from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HealthOut(BaseModel):
    ok: bool = True
    service: str
    version: str


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    email: str
    display_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime


class SessionResponse(BaseModel):
    ok: bool = True
    user: UserOut
    csrf_token: str


class AuditEventOut(BaseModel):
    id: str
    actor_type: str
    actor_id: str | None = None
    action: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SystemLogEventOut(BaseModel):
    id: str
    activity_type: str
    conversation_type: str = ""
    scope: str = ""
    team_name: str = ""
    channel_name: str = ""
    user_name: str = ""
    service_url: str = ""
    conversation_id: str = ""
    tenant_id: str = ""
    team_id: str = ""
    graph_team_id: str = ""
    channel_id: str = ""
    graph_user_id: str = ""
    created_at: datetime


GraphTargetKind = Literal["user", "team", "channel"]
WebhookTargetType = Literal["bot_conversation"]
WebhookRouteStatus = Literal["delivered", "failed", "rejected"]


class WebhookRouteBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_system: str = Field(default="", max_length=120)
    is_active: bool = True
    target_type: WebhookTargetType = "bot_conversation"
    target_name: str = Field(min_length=1, max_length=200)
    bot_service_url: str = Field(min_length=1, max_length=2000)
    bot_conversation_id: str = Field(min_length=1, max_length=2000)
    graph_target_kind: GraphTargetKind | None = None
    graph_target_id: str = Field(default="", max_length=2000)
    graph_team_id: str = Field(default="", max_length=2000)
    graph_team_name: str = Field(default="", max_length=200)
    graph_channel_id: str = Field(default="", max_length=2000)
    bot_target_source: str = Field(default="", max_length=40)


class WebhookRouteCreate(WebhookRouteBase):
    pass


class WebhookRouteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    source_system: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None
    target_type: WebhookTargetType | None = None
    target_name: str | None = Field(default=None, min_length=1, max_length=200)
    bot_service_url: str | None = Field(default=None, min_length=1, max_length=2000)
    bot_conversation_id: str | None = Field(default=None, min_length=1, max_length=2000)
    graph_target_kind: GraphTargetKind | None = None
    graph_target_id: str | None = Field(default=None, max_length=2000)
    graph_team_id: str | None = Field(default=None, max_length=2000)
    graph_team_name: str | None = Field(default=None, max_length=200)
    graph_channel_id: str | None = Field(default=None, max_length=2000)
    bot_target_source: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def require_change(self):
        if (
            self.name is None
            and self.source_system is None
            and self.is_active is None
            and self.target_type is None
            and self.target_name is None
            and self.bot_service_url is None
            and self.bot_conversation_id is None
            and self.graph_target_kind is None
            and self.graph_target_id is None
            and self.graph_team_id is None
            and self.graph_team_name is None
            and self.graph_channel_id is None
            and self.bot_target_source is None
        ):
            raise ValueError("At least one field must be provided")
        return self


class WebhookRouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    name: str
    source_system: str
    is_active: bool
    target_type: str
    target_name: str
    bot_service_url: str
    bot_conversation_id: str
    graph_target_kind: str
    graph_target_id: str
    graph_team_id: str
    graph_team_name: str
    graph_channel_id: str
    bot_target_source: str
    bot_registered_by_id: str
    bot_registered_at: datetime | None = None
    webhook_url: str | None = None
    webhook_url_available: bool = False
    last_delivery_status: str | None = None
    last_delivery_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WebhookRouteCreatedOut(WebhookRouteOut):
    webhook_url: str
    webhook_url_available: bool = True


class WebhookRouteTestRequest(BaseModel):
    title: str = Field(default="Teams Rehook test", min_length=1, max_length=255)
    text: str = Field(default="This is a test message from the relay service.", min_length=1, max_length=2000)
    severity: str = Field(default="info", max_length=40)


class WebhookDeliveryOut(BaseModel):
    ok: bool
    status: WebhookRouteStatus
    route_id: str
    delivery_event_id: str
    message: str


class WebhookRouteDefaultsOut(BaseModel):
    bot_default_service_url: str = ""


class WebhookRouteNameRefreshOut(BaseModel):
    ok: bool = True
    routes_checked: int = 0
    routes_updated: int = 0
    references_checked: int = 0
    references_updated: int = 0
    error: str = ""


class WebhookDeliveryEventOut(BaseModel):
    id: str
    route_id: str | None = None
    status: str
    request_metadata: dict[str, Any] = Field(default_factory=dict)
    normalized_message: dict[str, Any] = Field(default_factory=dict)
    delivery_result: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    created_at: datetime


class WebhookDeliveryEventSummaryOut(BaseModel):
    id: str
    route_id: str | None = None
    route_name: str = ""
    source_system: str = ""
    target_name: str = ""
    status: str
    title: str = ""
    payload_type: str = ""
    delivery_mode: str = ""
    status_code: int | None = None
    error: str = ""
    created_at: datetime


class WebhookDeliveryEventDetailOut(WebhookDeliveryEventOut):
    route_name: str = ""
    source_system: str = ""
    target_name: str = ""


class WebhookDeliveryEventPageOut(BaseModel):
    items: list[WebhookDeliveryEventSummaryOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    retention_days: int


class LogCleanupOut(BaseModel):
    ok: bool = True
    deleted: int
    deleted_webhook_delivery_events: int
    deleted_audit_events: int
    deleted_bot_activity_events: int
    retention_days: int
    cutoff: datetime


class ReadinessComponentOut(BaseModel):
    ready: bool
    auth_status: str
    message: str
    token_checked: bool
    token_request_succeeded: bool


class OAuthTokenDiagnosticsOut(BaseModel):
    checked: bool = False
    succeeded: bool = False
    expires_in_seconds: int | None = None
    expires_at: datetime | None = None
    audience: str = ""
    issuer: str = ""
    roles: list[str] = Field(default_factory=list)


class OAuthAppDiagnosticsOut(BaseModel):
    metadata_checked: bool = False
    available: bool = False
    display_name: str = ""
    app_id: str = ""
    service_principal_id: str = ""
    account_enabled: bool | None = None
    service_principal_type: str = ""
    message: str = ""


class OAuthTenantDiagnosticsOut(BaseModel):
    metadata_checked: bool = False
    available: bool = False
    display_name: str = ""
    primary_domain: str = ""
    message: str = ""


class OAuthDiagnosticsOut(BaseModel):
    credential_source: str = ""
    tenant_id: str = ""
    client_id: str = ""
    scope: str = ""
    token: OAuthTokenDiagnosticsOut = Field(default_factory=OAuthTokenDiagnosticsOut)
    app: OAuthAppDiagnosticsOut = Field(default_factory=OAuthAppDiagnosticsOut)
    tenant: OAuthTenantDiagnosticsOut = Field(default_factory=OAuthTenantDiagnosticsOut)


class BotReadinessOut(ReadinessComponentOut):
    mode: str
    credentials_configured: bool
    default_service_url_configured: bool
    credential_fields: dict[str, str]
    oauth: OAuthDiagnosticsOut


class GraphReadinessOut(ReadinessComponentOut):
    configured: bool
    credential_source: str
    credential_fields: dict[str, str]
    oauth: OAuthDiagnosticsOut


class RuntimeReadinessOut(BaseModel):
    app_public_base_url: str
    frontend_base_url: str
    cors_origins: list[str]
    webhook_max_payload_bytes: int
    log_retention_days: int
    log_cleanup_interval_minutes: int
    session_secure_cookie: bool


class AdminReadinessOut(BaseModel):
    app_name: str
    app_version: str
    delivery_mode: str
    bot: BotReadinessOut
    graph: GraphReadinessOut
    runtime: RuntimeReadinessOut


class SettingItemOut(BaseModel):
    key: str
    label: str
    type: Literal["string", "int", "url", "enum", "secret"]
    enum_values: list[str] = Field(default_factory=list)
    env_default: str
    effective_value: str
    is_overridden: bool


class SettingUpdateIn(BaseModel):
    value: str = Field(max_length=4000)


class TeamsTargetSearchOut(BaseModel):
    kind: GraphTargetKind
    id: str
    display_name: str
    subtitle: str = ""
    team_id: str | None = None
    team_name: str | None = None
    channel_id: str | None = None


class BotActivityIngestOut(BaseModel):
    ok: bool = True
    activity_event_id: str
    conversation_reference_id: str | None = None
    captured_reference: bool = False
    handled_command: bool = False
    command: str | None = None
    reply_sent: bool = False
    reply_error: str = ""
    reply_text: str | None = None


class BotConversationReferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scope: str
    service_url: str
    conversation_id: str
    tenant_id: str
    team_id: str
    graph_team_id: str
    channel_id: str
    conversation_type: str
    team_name: str
    channel_name: str
    user_id: str
    user_name: str
    graph_user_id: str
    raw_activity_type: str
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime
