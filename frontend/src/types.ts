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

export type SessionState =
  | { status: "booting"; user: null; csrfToken: "" }
  | { status: "anonymous"; user: null; csrfToken: "" }
  | { status: "authenticated"; user: UserOut; csrfToken: string };

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
  created_at: string;
};

export type WebhookTargetType = "bot_conversation";
export type GraphTargetKind = "user" | "team" | "channel";

export type WebhookRouteOut = {
  id: string;
  organization_id: string;
  name: string;
  source_system: string;
  is_active: boolean;
  target_type: WebhookTargetType;
  target_name: string;
  bot_service_url: string;
  bot_conversation_id: string;
  graph_target_kind: GraphTargetKind | "";
  graph_target_id: string;
  graph_team_id: string;
  graph_team_name: string;
  graph_channel_id: string;
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
  source_system: string;
  is_active: boolean;
  target_type: WebhookTargetType;
  target_name: string;
  bot_service_url: string;
  bot_conversation_id: string;
  graph_target_kind?: GraphTargetKind | null;
  graph_target_id?: string;
  graph_team_id?: string;
  graph_team_name?: string;
  graph_channel_id?: string;
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

export type WebhookDeliveryStatus = "delivered" | "failed" | "rejected";

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
  source_system: string;
  target_name: string;
  status: WebhookDeliveryStatus;
  title: string;
  payload_type: string;
  delivery_mode: string;
  status_code: number | null;
  error: string;
  created_at: string;
};

export type WebhookDeliveryEventDetailOut = WebhookDeliveryEventOut & {
  route_name: string;
  source_system: string;
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
  retention_days: number;
  cutoff: string;
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
  raw_activity_type: string;
  last_seen_at: string;
  created_at: string;
  updated_at: string;
};
