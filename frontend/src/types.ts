export type ApiError = {
  status: number;
  message: string;
  detail?: unknown;
};

export type UserOut = {
  id: string;
  organization_id: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
};

export type SessionResponse = {
  ok: boolean;
  user: UserOut;
  csrf_token: string;
};

export type SetupStatusOut = {
  ok: boolean;
  needs_setup: boolean;
  admin_exists: boolean;
};

export type SessionState =
  | { status: "booting"; user: null; csrfToken: "" }
  | { status: "setup"; user: null; csrfToken: "" }
  | { status: "anonymous"; user: null; csrfToken: "" }
  | { status: "authenticated"; user: UserOut; csrfToken: string };

export type FirstAdminCreate = {
  email: string;
  display_name: string;
  password: string;
};

export type UserCreate = {
  email: string;
  display_name: string;
  password: string;
  is_admin: boolean;
  is_active: boolean;
};

export type UserUpdate = {
  email?: string;
  display_name?: string;
  is_admin?: boolean;
  is_active?: boolean;
};

export type UserPasswordUpdate = {
  password: string;
};

export type ToastTone = "success" | "error" | "info";

export type Toast = {
  id: number;
  tone: ToastTone;
  title: string;
  description?: string;
};

export type AuditEventOut = {
  id: string;
  actor_type: string;
  actor_id: string | null;
  action: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type SystemLogEventOut = {
  id: string;
  activity_type: string;
  conversation_type: string;
  scope: string;
  team_name: string;
  channel_name: string;
  user_name: string;
  service_url: string;
  conversation_id: string;
  tenant_id: string;
  team_id: string;
  graph_team_id: string;
  channel_id: string;
  graph_user_id: string;
  auth_status: string;
  auth_issuer: string;
  auth_audience: string;
  auth_service_url: string;
  auth_service_url_matched: boolean;
  auth_validated_at: string | null;
  created_at: string;
};

export type EventLogEntryOut = {
  id: string;
  level: string;
  category: string;
  event_type: string;
  message: string;
  user_message: string;
  correlation_id: string;
  request_id: string;
  actor: Record<string, unknown>;
  target: Record<string, unknown>;
  source: Record<string, unknown>;
  http: Record<string, unknown>;
  security: Record<string, unknown>;
  raw: Record<string, unknown>;
  domain: string;
  domain_event_id: string | null;
  created_at: string;
};

export type EventLogEntryPageOut = {
  items: EventLogEntryOut[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  retention_days: number;
};

export type WebhookAbuseBucketOut = {
  id: string;
  scope: "ip" | "ip_route";
  status: "watching" | "blocked";
  client_host: string;
  client_fingerprint: string;
  route_token_fingerprint: string;
  failure_count: number;
  block_count: number;
  window_started_at: string;
  blocked_until: string | null;
  last_reason: string;
  last_seen_at: string;
  created_at: string;
};

export type WebhookAbuseCleanupOut = {
  ok: boolean;
  deleted: number;
  cleanup_days: number;
  cutoff: string;
};

export type WebhookTargetType = "bot_conversation";
export type DeliveryBackend = "bot_framework" | "graph";
export type ClientIpAccessMode = "public" | "restricted";
export type GraphTargetKind = "user" | "team" | "channel" | "chat";

export type ConversationMemberOut = {
  id: string;
  name: string;
  aad_object_id: string;
  email: string;
  user_principal_name: string;
};

export type WebhookRouteOut = {
  id: string;
  organization_id: string;
  name: string;
  is_active: boolean;
  delivery_backend: DeliveryBackend;
  client_ip_access_mode: ClientIpAccessMode;
  client_ip_allowlist: string;
  target_type: WebhookTargetType;
  target_name: string;
  bot_service_url: string;
  bot_conversation_id: string;
  graph_target_kind: GraphTargetKind | "";
  graph_target_id: string;
  graph_team_id: string;
  graph_team_name: string;
  graph_channel_id: string;
  graph_user_id: string;
  graph_user_display_name: string;
  graph_user_principal_name: string;
  member_summary: string;
  member_count: number;
  members: ConversationMemberOut[];
  members_refreshed_at: string | null;
  members_lookup_error: string;
  bot_target_source: string;
  bot_registered_by_id: string;
  bot_registered_at: string | null;
  webhook_url: string | null;
  webhook_url_available: boolean;
  last_delivery_status: "delivered" | "failed" | "rejected" | null;
  last_delivery_at: string | null;
  created_at: string;
  updated_at: string;
};

export type WebhookRouteCreate = {
  name: string;
  is_active: boolean;
  delivery_backend?: DeliveryBackend;
  client_ip_access_mode?: ClientIpAccessMode;
  client_ip_allowlist?: string;
  target_type: WebhookTargetType;
  target_name: string;
  bot_service_url: string;
  bot_conversation_id: string;
  graph_target_kind?: GraphTargetKind | null;
  graph_target_id?: string;
  graph_team_id?: string;
  graph_team_name?: string;
  graph_channel_id?: string;
  graph_user_id?: string;
  graph_user_display_name?: string;
  graph_user_principal_name?: string;
  bot_target_source?: string;
};

export type WebhookRouteUpdate = Partial<WebhookRouteCreate>;

export type WebhookRouteTestRequest = {
  title: string;
  text: string;
  severity: string;
};

export type WebhookDeliveryOut = {
  ok: boolean;
  status: "delivered" | "failed" | "rejected";
  route_id: string;
  delivery_event_id: string;
  message: string;
};

export type WebhookRouteDefaultsOut = {
  bot_default_service_url: string;
};

export type WebhookRouteNameRefreshOut = {
  ok: boolean;
  routes_checked: number;
  routes_updated: number;
  references_checked: number;
  references_updated: number;
  error: string;
};

export type WebhookDeliveryStatus = "delivered" | "failed" | "rejected" | "pending";

export type WebhookDeliveryEventOut = {
  id: string;
  route_id: string | null;
  status: WebhookDeliveryStatus;
  request_metadata: Record<string, unknown>;
  normalized_message: Record<string, unknown>;
  delivery_result: Record<string, unknown>;
  error: string;
  created_at: string;
};

export type WebhookDeliveryEventSummaryOut = {
  id: string;
  route_id: string | null;
  route_name: string;
  target_name: string;
  status: WebhookDeliveryStatus;
  title: string;
  payload_type: string;
  delivery_backend: string;
  delivery_mode: string;
  status_code: number | null;
  error: string;
  created_at: string;
};

export type WebhookDeliveryEventDetailOut = WebhookDeliveryEventOut & {
  route_name: string;
  target_name: string;
};

export type WebhookDeliveryEventPageOut = {
  items: WebhookDeliveryEventSummaryOut[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  retention_days: number;
};

export type LogCleanupOut = {
  ok: boolean;
  deleted: number;
  deleted_webhook_delivery_events: number;
  deleted_audit_events: number;
  deleted_bot_activity_events: number;
  deleted_event_log_entries: number;
  retention_days: number;
  cutoff: string;
};

export type SettingItemOut = {
  key: string;
  label: string;
  type: "string" | "int" | "url" | "enum" | "secret" | "bool";
  enum_values: string[];
  env_default: string;
  effective_value: string;
  is_overridden: boolean;
  source: "environment" | "application";
};

export type GraphDeliveryOAuthStartOut = {
  authorization_url: string;
};

export type GraphDeliveryOAuthPendingOut = {
  id: string;
  tenant_id: string;
  client_id: string;
  scopes: string[];
  service_user_id: string;
  service_user_display_name: string;
  service_user_principal_name: string;
  access_token_expires_at: string | null;
  refresh_checked_at: string | null;
  expires_at: string;
};

export type AdminReadinessOut = {
  app_name: string;
  app_version: string;
  delivery_mode: "mock" | "real" | string;
  bot: {
    enabled: boolean;
    ready: boolean;
    auth_status: string;
    message: string;
    token_checked: boolean;
    token_request_succeeded: boolean;
    mode: string;
    credentials_configured: boolean;
    default_service_url_configured: boolean;
    credential_fields: Record<string, string>;
    oauth: OAuthDiagnosticsOut;
  };
  graph_lookup: {
    enabled: boolean;
    ready: boolean;
    auth_status: string;
    message: string;
    token_checked: boolean;
    token_request_succeeded: boolean;
    configured: boolean;
    credential_source: "ms_app" | "missing" | string;
    credential_fields: Record<string, string>;
    oauth: OAuthDiagnosticsOut;
  };
  graph_delivery: {
    enabled: boolean;
    ready: boolean;
    auth_status: string;
    message: string;
    token_checked: boolean;
    token_request_succeeded: boolean;
    configured: boolean;
    credential_source: "delegated_service_user" | "missing" | string;
    tenant_id: string;
    client_id: string;
    scopes: string[];
    required_scopes: string[];
    missing_scopes: string[];
    service_user_id: string;
    service_user_display_name: string;
    service_user_principal_name: string;
    access_token_expires_at: string | null;
    refresh_checked_at: string | null;
  };
  runtime: {
    app_public_base_url: string;
    frontend_base_url: string;
    cors_origins: string[];
    compose_app_subnet: string;
    trusted_proxy_ips: string;
    trusted_proxy_chain: string;
    webhook_max_payload_bytes: number;
    log_retention_days: number;
    log_cleanup_interval_minutes: number;
    event_debug_previews_enabled: boolean;
    session_secure_cookie: boolean;
    settings_encryption_key_source: "configured" | "generated" | "missing" | string;
    settings_encryption_ready: boolean;
  };
};

export type DeliveryAuthRefreshStatus = "refreshed" | "cleared" | "skipped" | "failed";

export type DeliveryAuthRefreshComponentOut = {
  status: DeliveryAuthRefreshStatus;
  message: string;
};

export type DeliveryAuthRefreshOut = {
  ok: boolean;
  refreshed_at: string;
  bot_delivery: DeliveryAuthRefreshComponentOut;
  graph_lookup: DeliveryAuthRefreshComponentOut;
  graph_delivery: DeliveryAuthRefreshComponentOut;
  bot_inbound_auth: DeliveryAuthRefreshComponentOut;
  readiness: AdminReadinessOut;
};

export type OAuthDiagnosticsOut = {
  credential_source: string;
  tenant_id: string;
  client_id: string;
  scope: string;
  token: {
    checked: boolean;
    succeeded: boolean;
    expires_in_seconds: number | null;
    expires_at: string | null;
    audience: string;
    issuer: string;
    roles: string[];
  };
  app: {
    metadata_checked: boolean;
    available: boolean;
    display_name: string;
    app_id: string;
    service_principal_id: string;
    account_enabled: boolean | null;
    service_principal_type: string;
    message: string;
  };
  tenant: {
    metadata_checked: boolean;
    available: boolean;
    display_name: string;
    primary_domain: string;
    message: string;
  };
};

export type TeamsTargetSearchResult = {
  kind: GraphTargetKind;
  id: string;
  display_name: string;
  subtitle: string;
  team_id: string | null;
  team_name: string | null;
  channel_id: string | null;
};

export type BotConversationReferenceOut = {
  id: string;
  scope: string;
  service_url: string;
  conversation_id: string;
  tenant_id: string;
  team_id: string;
  graph_team_id: string;
  channel_id: string;
  conversation_type: string;
  team_name: string;
  channel_name: string;
  user_id: string;
  user_name: string;
  graph_user_id: string;
  member_summary: string;
  member_count: number;
  members: ConversationMemberOut[];
  members_refreshed_at: string | null;
  members_lookup_error: string;
  raw_activity_type: string;
  last_seen_at: string;
  created_at: string;
  updated_at: string;
};
