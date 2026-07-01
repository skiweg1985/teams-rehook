from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.client_ip_allowlist import (
    CLIENT_IP_ACCESS_PUBLIC,
    CLIENT_IP_ACCESS_RESTRICTED,
    normalize_client_ip_access_mode,
    normalize_client_ip_allowlist,
)


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


class UserCreateIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=200)
    is_admin: bool = True
    is_active: bool = True


class FirstAdminCreateIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=200)


class UserUpdateIn(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=255)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    is_admin: bool | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_change(self):
        if self.email is None and self.display_name is None and self.is_admin is None and self.is_active is None:
            raise ValueError("At least one field must be provided")
        return self


class UserPasswordUpdateIn(BaseModel):
    password: str = Field(min_length=8, max_length=200)


BotUserRole = str


class BotUserPermissions(BaseModel):
    can_view_routes: bool = True
    can_reveal_webhook_urls: bool = True
    can_manage_route_status: bool = False
    can_delete_routes: bool = False
    can_manage_allowlist: bool = False
    can_create_private_chat_routes: bool = False
    can_create_channel_routes: bool = False


class BotAccessRoleOut(BotUserPermissions):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    name: str
    description: str = ""
    is_system: bool
    system_key: str | None = None
    created_at: datetime
    updated_at: datetime


class BotAccessRoleCreateIn(BotUserPermissions):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class BotAccessRoleUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    can_view_routes: bool | None = None
    can_reveal_webhook_urls: bool | None = None
    can_manage_route_status: bool | None = None
    can_delete_routes: bool | None = None
    can_manage_allowlist: bool | None = None
    can_create_private_chat_routes: bool | None = None
    can_create_channel_routes: bool | None = None

    @model_validator(mode="after")
    def require_change(self):
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("At least one field must be provided")
        return self


class BotAuthorizedUserOut(BotUserPermissions):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    aad_object_id: str
    display_name: str
    user_principal_name: str
    role_id: str | None = None
    role: BotUserRole
    is_active: bool
    last_seen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class BotAuthorizedUserCreateIn(BotUserPermissions):
    aad_object_id: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    user_principal_name: str = Field(default="", max_length=255)
    role_id: str | None = None
    role: BotUserRole = "custom"
    is_active: bool = True


class BotAuthorizedUserUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    user_principal_name: str | None = Field(default=None, max_length=255)
    role_id: str | None = None
    role: BotUserRole | None = None
    is_active: bool | None = None
    can_view_routes: bool | None = None
    can_reveal_webhook_urls: bool | None = None
    can_manage_route_status: bool | None = None
    can_delete_routes: bool | None = None
    can_manage_allowlist: bool | None = None
    can_create_private_chat_routes: bool | None = None
    can_create_channel_routes: bool | None = None

    @model_validator(mode="after")
    def require_change(self):
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("At least one field must be provided")
        return self


class BotAuthorizedGroupOut(BotUserPermissions):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    group_object_id: str
    display_name: str
    mail: str
    security_enabled: bool
    group_types: list[str] = Field(default_factory=list)
    role_id: str | None = None
    role: BotUserRole
    is_active: bool
    last_matched_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class BotAuthorizedGroupCreateIn(BotUserPermissions):
    group_object_id: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    mail: str = Field(default="", max_length=255)
    security_enabled: bool = False
    group_types: list[str] = Field(default_factory=list)
    role_id: str | None = None
    role: BotUserRole = "custom"
    is_active: bool = True


class BotAuthorizedGroupUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    mail: str | None = Field(default=None, max_length=255)
    security_enabled: bool | None = None
    group_types: list[str] | None = None
    role_id: str | None = None
    role: BotUserRole | None = None
    is_active: bool | None = None
    can_view_routes: bool | None = None
    can_reveal_webhook_urls: bool | None = None
    can_manage_route_status: bool | None = None
    can_delete_routes: bool | None = None
    can_manage_allowlist: bool | None = None
    can_create_private_chat_routes: bool | None = None
    can_create_channel_routes: bool | None = None

    @model_validator(mode="after")
    def require_change(self):
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("At least one field must be provided")
        return self


class SessionResponse(BaseModel):
    ok: bool = True
    user: UserOut
    csrf_token: str


class SetupStatusOut(BaseModel):
    ok: bool = True
    needs_setup: bool
    admin_exists: bool


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
    auth_status: str = "unknown"
    auth_issuer: str = ""
    auth_audience: str = ""
    auth_service_url: str = ""
    auth_service_url_matched: bool = False
    auth_validated_at: datetime | None = None
    bot_authorization_status: str = "not_applicable"
    bot_authorized_user_id: str = ""
    bot_authorization_reason: str = ""
    created_at: datetime


class EventLogEntryOut(BaseModel):
    id: str
    level: str
    category: str
    event_type: str
    message: str
    user_message: str = ""
    correlation_id: str = ""
    request_id: str = ""
    actor: dict[str, Any] = Field(default_factory=dict)
    target: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)
    http: dict[str, Any] = Field(default_factory=dict)
    security: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)
    domain: str = ""
    domain_event_id: str | None = None
    created_at: datetime


class EventLogEntryPageOut(BaseModel):
    items: list[EventLogEntryOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    retention_days: int


class ClientEventIn(BaseModel):
    level: Literal["warning", "error"] = "error"
    event_type: str = Field(default="frontend.admin_ui_error", min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=1000)
    path: str = Field(default="", max_length=600)
    action: str = Field(default="", max_length=200)
    request_id: str = Field(default="", max_length=80)
    correlation_id: str = Field(default="", max_length=80)
    detail: dict[str, Any] = Field(default_factory=dict)


class WebhookAbuseBucketOut(BaseModel):
    id: str
    scope: Literal["ip", "ip_route"]
    status: Literal["watching", "blocked"]
    client_host: str = ""
    client_fingerprint: str
    route_token_fingerprint: str = ""
    failure_count: int
    block_count: int
    window_started_at: datetime
    blocked_until: datetime | None = None
    last_reason: str = ""
    last_seen_at: datetime
    created_at: datetime


class WebhookAbuseCleanupOut(BaseModel):
    ok: bool = True
    deleted: int
    cleanup_days: int
    cutoff: datetime


GraphTargetKind = Literal["user", "team", "channel", "chat", "group"]
DeliveryBackend = Literal["bot_framework", "graph"]
ClientIpAccessMode = Literal["public", "restricted"]
WebhookTargetType = Literal["bot_conversation"]
WebhookRouteStatus = Literal["delivered", "failed", "rejected"]


class WebhookRouteBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    is_active: bool = True
    delivery_backend: DeliveryBackend = "bot_framework"
    client_ip_access_mode: ClientIpAccessMode = "public"
    client_ip_allowlist: str = Field(default="", max_length=4000)
    target_type: WebhookTargetType = "bot_conversation"
    target_name: str = Field(min_length=1, max_length=200)
    bot_service_url: str = Field(default="", max_length=2000)
    bot_conversation_id: str = Field(default="", max_length=2000)
    graph_target_kind: GraphTargetKind | None = None
    graph_target_id: str = Field(default="", max_length=2000)
    graph_team_id: str = Field(default="", max_length=2000)
    graph_team_name: str = Field(default="", max_length=200)
    graph_channel_id: str = Field(default="", max_length=2000)
    graph_user_id: str = Field(default="", max_length=2000)
    graph_user_display_name: str = Field(default="", max_length=255)
    graph_user_principal_name: str = Field(default="", max_length=255)
    bot_target_source: str = Field(default="", max_length=40)

    @model_validator(mode="after")
    def validate_client_ip_access(self):
        self.client_ip_access_mode = normalize_client_ip_access_mode(self.client_ip_access_mode)
        self.client_ip_allowlist = normalize_client_ip_allowlist(self.client_ip_allowlist)
        if self.client_ip_access_mode == CLIENT_IP_ACCESS_PUBLIC:
            self.client_ip_allowlist = ""
        if self.client_ip_access_mode == CLIENT_IP_ACCESS_RESTRICTED and not self.client_ip_allowlist:
            raise ValueError("Restricted routes require at least one client IP or CIDR range")
        return self


class WebhookRouteCreate(WebhookRouteBase):
    pass


class WebhookRouteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    delivery_backend: DeliveryBackend | None = None
    client_ip_access_mode: ClientIpAccessMode | None = None
    client_ip_allowlist: str | None = Field(default=None, max_length=4000)
    target_type: WebhookTargetType | None = None
    target_name: str | None = Field(default=None, min_length=1, max_length=200)
    bot_service_url: str | None = Field(default=None, max_length=2000)
    bot_conversation_id: str | None = Field(default=None, max_length=2000)
    graph_target_kind: GraphTargetKind | None = None
    graph_target_id: str | None = Field(default=None, max_length=2000)
    graph_team_id: str | None = Field(default=None, max_length=2000)
    graph_team_name: str | None = Field(default=None, max_length=200)
    graph_channel_id: str | None = Field(default=None, max_length=2000)
    graph_user_id: str | None = Field(default=None, max_length=2000)
    graph_user_display_name: str | None = Field(default=None, max_length=255)
    graph_user_principal_name: str | None = Field(default=None, max_length=255)
    bot_target_source: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def require_change(self):
        if (
            self.name is None
            and self.is_active is None
            and self.delivery_backend is None
            and self.client_ip_access_mode is None
            and self.client_ip_allowlist is None
            and self.target_type is None
            and self.target_name is None
            and self.bot_service_url is None
            and self.bot_conversation_id is None
            and self.graph_target_kind is None
            and self.graph_target_id is None
            and self.graph_team_id is None
            and self.graph_team_name is None
            and self.graph_channel_id is None
            and self.graph_user_id is None
            and self.graph_user_display_name is None
            and self.graph_user_principal_name is None
            and self.bot_target_source is None
        ):
            raise ValueError("At least one field must be provided")
        if self.client_ip_access_mode is not None:
            self.client_ip_access_mode = normalize_client_ip_access_mode(self.client_ip_access_mode)
        if self.client_ip_allowlist is not None:
            self.client_ip_allowlist = normalize_client_ip_allowlist(self.client_ip_allowlist)
        return self


class BotConversationMemberOut(BaseModel):
    id: str = ""
    name: str = ""
    aad_object_id: str = ""
    email: str = ""
    user_principal_name: str = ""


class WebhookRouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    name: str
    is_active: bool
    delivery_backend: str
    client_ip_access_mode: str
    client_ip_allowlist: str
    target_type: str
    target_name: str
    bot_service_url: str
    bot_conversation_id: str
    graph_target_kind: str
    graph_target_id: str
    graph_team_id: str
    graph_team_name: str
    graph_channel_id: str
    graph_user_id: str
    graph_user_display_name: str
    graph_user_principal_name: str
    member_summary: str = ""
    member_count: int = 0
    members: list[BotConversationMemberOut] = Field(default_factory=list)
    members_refreshed_at: datetime | None = None
    members_lookup_error: str = ""
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


class WebhookUrlRevealOut(BaseModel):
    webhook_url: str
    route_name: str
    expires_at: datetime


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
    target_name: str = ""
    status: str
    title: str = ""
    payload_type: str = ""
    delivery_backend: str = ""
    delivery_mode: str = ""
    status_code: int | None = None
    error: str = ""
    created_at: datetime


class WebhookDeliveryEventDetailOut(WebhookDeliveryEventOut):
    route_name: str = ""
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
    deleted_event_log_entries: int
    retention_days: int
    cutoff: datetime


class ReadinessComponentOut(BaseModel):
    enabled: bool = True
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
    credential_fields: dict[str, str]
    oauth: OAuthDiagnosticsOut


class GraphReadinessOut(ReadinessComponentOut):
    configured: bool
    credential_source: str
    credential_fields: dict[str, str]
    oauth: OAuthDiagnosticsOut
    group_membership_lookup_ready: bool = False
    group_membership_required_roles: list[str] = Field(default_factory=list)
    group_membership_alternative_roles: list[str] = Field(default_factory=list)
    group_membership_missing_roles: list[str] = Field(default_factory=list)
    group_membership_message: str = ""


class GraphDeliveryReadinessOut(ReadinessComponentOut):
    configured: bool
    credential_source: str
    tenant_id: str = ""
    client_id: str = ""
    scopes: list[str] = Field(default_factory=list)
    required_scopes: list[str] = Field(default_factory=list)
    missing_scopes: list[str] = Field(default_factory=list)
    service_user_id: str = ""
    service_user_display_name: str = ""
    service_user_principal_name: str = ""
    access_token_expires_at: datetime | None = None
    refresh_checked_at: datetime | None = None


class RuntimeReadinessOut(BaseModel):
    app_public_base_url: str
    frontend_base_url: str
    cors_origins: list[str]
    compose_app_subnet: str
    trusted_proxy_ips: str
    trusted_proxy_chain: str
    webhook_max_payload_bytes: int
    webhook_url_reveal_ttl_hours: int
    log_retention_days: int
    log_cleanup_interval_minutes: int
    event_debug_previews_enabled: bool
    session_secure_cookie: bool
    settings_encryption_key_source: str
    settings_encryption_ready: bool


class AdminReadinessOut(BaseModel):
    app_name: str
    app_version: str
    delivery_mode: str
    bot: BotReadinessOut
    graph_lookup: GraphReadinessOut
    graph_delivery: GraphDeliveryReadinessOut
    runtime: RuntimeReadinessOut


DeliveryAuthRefreshStatus = Literal["refreshed", "cleared", "skipped", "failed"]


class DeliveryAuthRefreshComponentOut(BaseModel):
    status: DeliveryAuthRefreshStatus
    message: str


class DeliveryAuthRefreshOut(BaseModel):
    ok: bool
    refreshed_at: datetime
    bot_delivery: DeliveryAuthRefreshComponentOut
    graph_lookup: DeliveryAuthRefreshComponentOut
    graph_delivery: DeliveryAuthRefreshComponentOut
    bot_inbound_auth: DeliveryAuthRefreshComponentOut
    readiness: AdminReadinessOut


class SettingItemOut(BaseModel):
    key: str
    label: str
    type: Literal["string", "int", "url", "enum", "secret", "bool"]
    enum_values: list[str] = Field(default_factory=list)
    env_default: str
    effective_value: str
    is_overridden: bool
    source: Literal["environment", "application"] = "environment"


class SettingUpdateIn(BaseModel):
    value: str = Field(max_length=4000)


class MonitoringDatabaseOut(BaseModel):
    ok: bool
    message: str = ""


class MonitoringReadinessComponentOut(BaseModel):
    enabled: bool = True
    ready: bool
    auth_status: str


class MonitoringGraphReadinessOut(MonitoringReadinessComponentOut):
    credential_source: str


class MonitoringReadinessOut(BaseModel):
    bot: MonitoringReadinessComponentOut
    graph_lookup: MonitoringGraphReadinessOut
    graph_delivery: MonitoringGraphReadinessOut


class MonitoringRoutesOut(BaseModel):
    total: int = 0
    active: int = 0
    inactive: int = 0
    with_last_failure: int = 0
    with_last_rejection: int = 0
    untested_active: int = 0


class MonitoringDeliveriesOut(BaseModel):
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_rejection_at: datetime | None = None


class MonitoringRollingWindowOut(BaseModel):
    delivery_success_count: int = 0
    delivery_failure_count: int = 0
    delivery_rejection_count: int = 0
    success_rate: float | None = None


class MonitoringProblemRouteOut(BaseModel):
    id: str
    name: str
    delivery_backend: str
    is_active: bool
    last_delivery_status: str | None = None
    last_delivery_at: datetime | None = None


class MonitoringStatusOut(BaseModel):
    ok: bool
    status: str
    service: str
    version: str
    generated_at: datetime
    database: MonitoringDatabaseOut
    delivery_mode: str
    readiness: MonitoringReadinessOut
    routes: MonitoringRoutesOut
    deliveries: MonitoringDeliveriesOut
    rolling_windows: dict[str, MonitoringRollingWindowOut]
    problem_routes: list[MonitoringProblemRouteOut]


class GraphDeliveryOAuthStartOut(BaseModel):
    authorization_url: str


class GraphDeliveryOAuthPendingOut(BaseModel):
    id: str
    tenant_id: str = ""
    client_id: str = ""
    scopes: list[str] = Field(default_factory=list)
    service_user_id: str = ""
    service_user_display_name: str = ""
    service_user_principal_name: str = ""
    access_token_expires_at: datetime | None = None
    refresh_checked_at: datetime | None = None
    expires_at: datetime


class TeamsTargetSearchOut(BaseModel):
    kind: GraphTargetKind
    id: str
    display_name: str
    subtitle: str = ""
    team_id: str | None = None
    team_name: str | None = None
    channel_id: str | None = None
    mail: str = ""
    security_enabled: bool | None = None
    group_types: list[str] = Field(default_factory=list)


class TeamsGroupMemberOut(BaseModel):
    id: str
    display_name: str
    user_principal_name: str = ""
    mail: str = ""


class TeamsGroupMemberPageOut(BaseModel):
    items: list[TeamsGroupMemberOut] = Field(default_factory=list)
    offset: int = 0
    limit: int = 100
    has_more: bool = False


class TeamsGroupMemberCountOut(BaseModel):
    count: int


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
    member_summary: str = ""
    member_count: int = 0
    members: list[BotConversationMemberOut] = Field(default_factory=list)
    members_refreshed_at: datetime | None = None
    members_lookup_error: str = ""
    raw_activity_type: str
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime


class BotConversationLinkedRouteOut(BaseModel):
    id: str
    name: str
    is_active: bool
    delivery_backend: str
    target_name: str
    last_delivery_status: str | None = None
    last_delivery_at: datetime | None = None
    updated_at: datetime


class BotConversationReferenceDetailOut(BotConversationReferenceOut):
    linked_routes: list[BotConversationLinkedRouteOut] = Field(default_factory=list)
    linked_route_count: int = 0
