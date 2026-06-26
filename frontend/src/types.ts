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

export type DemoItemStatus = "todo" | "in_progress" | "done";

export type DemoItemOut = {
  id: string;
  organization_id: string;
  owner_id: string | null;
  title: string;
  status: DemoItemStatus;
  summary: string;
  created_at: string;
  updated_at: string;
};

export type DemoItemCreate = {
  title: string;
  status: DemoItemStatus;
  summary: string;
};

export type DemoItemUpdate = Partial<DemoItemCreate>;

export type AuditEventOut = {
  id: string;
  actor_type: string;
  actor_id: string | null;
  action: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type WebhookTargetType = "bot_conversation";

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

export type WebhookDeliveryEventOut = {
  id: string;
  route_id: string | null;
  status: "delivered" | "failed" | "rejected";
  request_metadata: Record<string, unknown>;
  normalized_message: Record<string, unknown>;
  delivery_result: Record<string, unknown>;
  error: string;
  created_at: string;
};
