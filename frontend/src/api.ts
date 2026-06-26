import type {
  ApiError,
  AuditEventOut,
  BotConversationReferenceOut,
  SessionResponse,
  TeamsTargetSearchResult,
  UserOut,
  WebhookDeliveryEventOut,
  WebhookDeliveryOut,
  WebhookDeliveryStatus,
  WebhookRouteCreate,
  WebhookRouteDefaultsOut,
  WebhookRouteOut,
  WebhookRouteTestRequest,
  WebhookRouteUpdate,
} from "./types";

type HttpMethod = "GET" | "POST" | "PATCH" | "DELETE";

type RequestOptions = {
  method?: HttpMethod;
  body?: unknown;
  csrfToken?: string;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.csrfToken) headers["X-CSRF-Token"] = options.csrfToken;

  const response = await fetch(path, {
    method,
    credentials: "include",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    const text = await response.text();
    let detail: unknown;
    let message = `Request failed with status ${response.status}`;
    if (text) {
      try {
        const body = JSON.parse(text) as { detail?: unknown };
        detail = body.detail ?? body;
        if (typeof detail === "string") message = detail;
      } catch {
        message = text;
      }
    }
    throw { status: response.status, message, detail } satisfies ApiError;
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  login(email: string, password: string) {
    return request<SessionResponse>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
    });
  },
  me() {
    return request<SessionResponse>("/api/v1/sessions/me");
  },
  logout(csrfToken: string) {
    return request<{ ok: boolean }>("/api/v1/auth/logout", {
      method: "POST",
      csrfToken,
    });
  },
  adminUsers(csrfToken: string) {
    return request<UserOut[]>("/api/v1/admin/users", { csrfToken });
  },
  adminLogs(csrfToken: string) {
    return request<AuditEventOut[]>("/api/v1/admin/logs", { csrfToken });
  },
  webhookRoutes() {
    return request<WebhookRouteOut[]>("/api/v1/webhook-routes");
  },
  webhookRouteDefaults() {
    return request<WebhookRouteDefaultsOut>("/api/v1/webhook-routes/defaults");
  },
  botConversationReferences() {
    return request<BotConversationReferenceOut[]>("/api/v1/bot/conversation-references");
  },
  createWebhookRoute(csrfToken: string, body: WebhookRouteCreate) {
    return request<WebhookRouteOut>("/api/v1/webhook-routes", {
      method: "POST",
      csrfToken,
      body,
    });
  },
  updateWebhookRoute(csrfToken: string, id: string, body: WebhookRouteUpdate) {
    return request<WebhookRouteOut>(`/api/v1/webhook-routes/${encodeURIComponent(id)}`, {
      method: "PATCH",
      csrfToken,
      body,
    });
  },
  deleteWebhookRoute(csrfToken: string, id: string) {
    return request<void>(`/api/v1/webhook-routes/${encodeURIComponent(id)}`, {
      method: "DELETE",
      csrfToken,
    });
  },
  regenerateWebhookRouteUrl(csrfToken: string, id: string) {
    return request<WebhookRouteOut>(`/api/v1/webhook-routes/${encodeURIComponent(id)}/regenerate-url`, {
      method: "POST",
      csrfToken,
    });
  },
  webhookRouteDeliveries(id: string, status?: WebhookDeliveryStatus) {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    const query = params.toString();
    return request<WebhookDeliveryEventOut[]>(
      `/api/v1/webhook-routes/${encodeURIComponent(id)}/deliveries${query ? `?${query}` : ""}`,
    );
  },
  testWebhookRoute(csrfToken: string, id: string, body: WebhookRouteTestRequest) {
    return request<WebhookDeliveryOut>(`/api/v1/webhook-routes/${encodeURIComponent(id)}/test`, {
      method: "POST",
      csrfToken,
      body,
    });
  },
  searchTeamsTargets(kind: "user" | "team", query: string) {
    const params = new URLSearchParams({ kind, q: query });
    return request<TeamsTargetSearchResult[]>(`/api/v1/teams-targets/search?${params.toString()}`);
  },
  teamChannels(teamId: string, query: string) {
    const params = new URLSearchParams({ q: query });
    return request<TeamsTargetSearchResult[]>(
      `/api/v1/teams-targets/teams/${encodeURIComponent(teamId)}/channels?${params.toString()}`,
    );
  },
};
