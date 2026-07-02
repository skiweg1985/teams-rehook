import type {
  AdminReadinessOut,
  ApiError,
  AuditEventOut,
  BotAccessRoleCreate,
  BotAccessRoleOut,
  BotAccessRoleUpdate,
  BotAuthorizedGroupCreate,
  BotAuthorizedGroupOut,
  BotAuthorizedGroupUpdate,
  BotAuthorizedUserCreate,
  BotAuthorizedUserOut,
  BotAuthorizedUserUpdate,
  BotConversationReferenceDetailOut,
  BotConversationReferenceOut,
  DeliveryAuthRefreshJobOut,
  EventLogEntryPageOut,
  FirstAdminCreate,
  GraphDeliveryOAuthPendingOut,
  GraphDeliveryOAuthStartOut,
  LogCleanupOut,
  SessionResponse,
  SettingItemOut,
  SetupStatusOut,
  SystemLogEventOut,
  TeamsGroupMemberCount,
  TeamsGroupMemberPage,
  TeamsTargetSearchResult,
  UserCreate,
  UserOut,
  UserPasswordUpdate,
  UserUpdate,
  WebhookAbuseBucketOut,
  WebhookAbuseCleanupOut,
  WebhookDeliveryEventDetailOut,
  WebhookDeliveryEventOut,
  WebhookDeliveryEventPageOut,
  WebhookDeliveryOut,
  WebhookDeliveryStatus,
  WebhookRouteCreate,
  WebhookRouteNameRefreshOut,
  WebhookRouteOut,
  WebhookRouteTestRequest,
  WebhookRouteUpdate,
  WebhookUrlRevealOut,
} from "./types";

type HttpMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

type RequestOptions = {
  method?: HttpMethod;
  body?: unknown;
  csrfToken?: string;
};

type EventLogFilters = {
  page?: number;
  pageSize?: number;
  level?: string;
  category?: string;
  eventType?: string;
  correlationId?: string;
  requestId?: string;
  query?: string;
};

let activeSessionRequest: Promise<SessionResponse> | null = null;

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
  setupStatus() {
    return request<SetupStatusOut>("/api/v1/setup/status");
  },
  createFirstAdmin(body: FirstAdminCreate) {
    return request<SessionResponse>("/api/v1/setup/admin", {
      method: "POST",
      body,
    });
  },
  login(email: string, password: string) {
    return request<SessionResponse>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
    });
  },
  me() {
    activeSessionRequest ??= request<SessionResponse>("/api/v1/sessions/me").finally(() => {
      activeSessionRequest = null;
    });
    return activeSessionRequest;
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
  createAdminUser(csrfToken: string, body: UserCreate) {
    return request<UserOut>("/api/v1/admin/users", {
      method: "POST",
      csrfToken,
      body,
    });
  },
  updateAdminUser(csrfToken: string, id: string, body: UserUpdate) {
    return request<UserOut>(`/api/v1/admin/users/${encodeURIComponent(id)}`, {
      method: "PATCH",
      csrfToken,
      body,
    });
  },
  updateAdminUserPassword(csrfToken: string, id: string, body: UserPasswordUpdate) {
    return request<UserOut>(`/api/v1/admin/users/${encodeURIComponent(id)}/password`, {
      method: "PUT",
      csrfToken,
      body,
    });
  },
  adminBotRoles(csrfToken: string) {
    return request<BotAccessRoleOut[]>("/api/v1/admin/bot-roles", { csrfToken });
  },
  createAdminBotRole(csrfToken: string, body: BotAccessRoleCreate) {
    return request<BotAccessRoleOut>("/api/v1/admin/bot-roles", {
      method: "POST",
      csrfToken,
      body,
    });
  },
  updateAdminBotRole(csrfToken: string, id: string, body: BotAccessRoleUpdate) {
    return request<BotAccessRoleOut>(`/api/v1/admin/bot-roles/${encodeURIComponent(id)}`, {
      method: "PATCH",
      csrfToken,
      body,
    });
  },
  deleteAdminBotRole(csrfToken: string, id: string) {
    return request<void>(`/api/v1/admin/bot-roles/${encodeURIComponent(id)}`, {
      method: "DELETE",
      csrfToken,
    });
  },
  adminBotUsers(csrfToken: string) {
    return request<BotAuthorizedUserOut[]>("/api/v1/admin/bot-users", { csrfToken });
  },
  createAdminBotUser(csrfToken: string, body: BotAuthorizedUserCreate) {
    return request<BotAuthorizedUserOut>("/api/v1/admin/bot-users", {
      method: "POST",
      csrfToken,
      body,
    });
  },
  updateAdminBotUser(csrfToken: string, id: string, body: BotAuthorizedUserUpdate) {
    return request<BotAuthorizedUserOut>(`/api/v1/admin/bot-users/${encodeURIComponent(id)}`, {
      method: "PATCH",
      csrfToken,
      body,
    });
  },
  deleteAdminBotUser(csrfToken: string, id: string) {
    return request<void>(`/api/v1/admin/bot-users/${encodeURIComponent(id)}`, {
      method: "DELETE",
      csrfToken,
    });
  },
  adminBotGroups(csrfToken: string) {
    return request<BotAuthorizedGroupOut[]>("/api/v1/admin/bot-groups", { csrfToken });
  },
  createAdminBotGroup(csrfToken: string, body: BotAuthorizedGroupCreate) {
    return request<BotAuthorizedGroupOut>("/api/v1/admin/bot-groups", {
      method: "POST",
      csrfToken,
      body,
    });
  },
  updateAdminBotGroup(csrfToken: string, id: string, body: BotAuthorizedGroupUpdate) {
    return request<BotAuthorizedGroupOut>(`/api/v1/admin/bot-groups/${encodeURIComponent(id)}`, {
      method: "PATCH",
      csrfToken,
      body,
    });
  },
  deleteAdminBotGroup(csrfToken: string, id: string) {
    return request<void>(`/api/v1/admin/bot-groups/${encodeURIComponent(id)}`, {
      method: "DELETE",
      csrfToken,
    });
  },
  adminLogs(csrfToken: string) {
    return request<AuditEventOut[]>("/api/v1/admin/logs", { csrfToken });
  },
  adminSystemLogs(csrfToken: string) {
    return request<SystemLogEventOut[]>("/api/v1/admin/system-logs", { csrfToken });
  },
  adminEventLogs(csrfToken: string, filters: EventLogFilters = {}) {
    const params = new URLSearchParams();
    if (filters.page) params.set("page", String(filters.page));
    if (filters.pageSize) params.set("page_size", String(filters.pageSize));
    if (filters.level) params.set("level", filters.level);
    if (filters.category) params.set("category", filters.category);
    if (filters.eventType) params.set("event_type", filters.eventType);
    if (filters.correlationId) params.set("correlation_id", filters.correlationId);
    if (filters.requestId) params.set("request_id", filters.requestId);
    if (filters.query) params.set("q", filters.query);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request<EventLogEntryPageOut>(`/api/v1/admin/event-logs${suffix}`, { csrfToken });
  },
  adminWebhookAbuseBuckets(csrfToken: string) {
    return request<WebhookAbuseBucketOut[]>("/api/v1/admin/webhook-abuse-buckets", { csrfToken });
  },
  unblockWebhookAbuseBucket(csrfToken: string, id: string) {
    return request<WebhookAbuseBucketOut>(`/api/v1/admin/webhook-abuse-buckets/${encodeURIComponent(id)}`, {
      method: "DELETE",
      csrfToken,
    });
  },
  cleanupWebhookAbuseBuckets(csrfToken: string) {
    return request<WebhookAbuseCleanupOut>("/api/v1/admin/webhook-abuse-buckets/cleanup", {
      method: "POST",
      csrfToken,
    });
  },
  adminReadiness(csrfToken: string) {
    return request<AdminReadinessOut>("/api/v1/admin/readiness", { csrfToken });
  },
  refreshDeliveryAuth(csrfToken: string) {
    return request<DeliveryAuthRefreshJobOut>("/api/v1/admin/delivery-auth/refresh", {
      method: "POST",
      csrfToken,
    });
  },
  deliveryAuthRefreshJob(csrfToken: string, jobId: string) {
    return request<DeliveryAuthRefreshJobOut>(`/api/v1/admin/delivery-auth/refresh/${encodeURIComponent(jobId)}`, { csrfToken });
  },
  adminSettings(csrfToken: string) {
    return request<SettingItemOut[]>("/api/v1/admin/settings", { csrfToken });
  },
  startGraphDeliveryOAuth(csrfToken: string) {
    return request<GraphDeliveryOAuthStartOut>("/api/v1/admin/graph-delivery/oauth/start", {
      method: "POST",
      csrfToken,
    });
  },
  disconnectGraphDeliveryOAuth(csrfToken: string) {
    return request<void>("/api/v1/admin/graph-delivery/oauth", {
      method: "DELETE",
      csrfToken,
    });
  },
  graphDeliveryOAuthPending(csrfToken: string, id: string) {
    return request<GraphDeliveryOAuthPendingOut>(`/api/v1/admin/graph-delivery/oauth/pending/${encodeURIComponent(id)}`, { csrfToken });
  },
  confirmGraphDeliveryOAuthPending(csrfToken: string, id: string) {
    return request<AdminReadinessOut>(`/api/v1/admin/graph-delivery/oauth/pending/${encodeURIComponent(id)}/confirm`, {
      method: "POST",
      csrfToken,
    });
  },
  cancelGraphDeliveryOAuthPending(csrfToken: string, id: string) {
    return request<void>(`/api/v1/admin/graph-delivery/oauth/pending/${encodeURIComponent(id)}`, {
      method: "DELETE",
      csrfToken,
    });
  },
  updateSetting(csrfToken: string, key: string, value: string) {
    return request<SettingItemOut>(`/api/v1/admin/settings/${encodeURIComponent(key)}`, {
      method: "PUT",
      csrfToken,
      body: { value },
    });
  },
  resetSetting(csrfToken: string, key: string) {
    return request<void>(`/api/v1/admin/settings/${encodeURIComponent(key)}`, {
      method: "DELETE",
      csrfToken,
    });
  },
  cleanupLogs(csrfToken: string) {
    return request<LogCleanupOut>("/api/v1/admin/logs/cleanup", {
      method: "POST",
      csrfToken,
    });
  },
  webhookUrlReveal(token: string) {
    return request<WebhookUrlRevealOut>(`/api/v1/webhook-url-reveals/${encodeURIComponent(token)}`);
  },
  webhookRoutes() {
    return request<WebhookRouteOut[]>("/api/v1/webhook-routes");
  },
  botConversationReferences() {
    return request<BotConversationReferenceOut[]>("/api/v1/bot/conversation-references");
  },
  botConversationReference(id: string) {
    return request<BotConversationReferenceDetailOut>(`/api/v1/bot/conversation-references/${encodeURIComponent(id)}`);
  },
  refreshBotConversationReferenceMembers(csrfToken: string, id: string) {
    return request<BotConversationReferenceDetailOut>(`/api/v1/bot/conversation-references/${encodeURIComponent(id)}/refresh-members`, {
      method: "POST",
      csrfToken,
    });
  },
  deleteBotConversationReference(csrfToken: string, id: string, deleteLinkedRoutes: boolean) {
    return request<void>(`/api/v1/bot/conversation-references/${encodeURIComponent(id)}?delete_linked_routes=${deleteLinkedRoutes ? "true" : "false"}`, {
      method: "DELETE",
      csrfToken,
    });
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
  refreshWebhookRouteGraphNames(csrfToken: string) {
    return request<WebhookRouteNameRefreshOut>("/api/v1/webhook-routes/refresh-graph-names", {
      method: "POST",
      csrfToken,
    });
  },
  refreshSingleWebhookRouteGraphNames(csrfToken: string, id: string) {
    return request<WebhookRouteNameRefreshOut>(`/api/v1/webhook-routes/${encodeURIComponent(id)}/refresh-graph-names`, {
      method: "POST",
      csrfToken,
    });
  },
  refreshWebhookRouteMembers(csrfToken: string, id: string) {
    return request<WebhookRouteOut>(`/api/v1/webhook-routes/${encodeURIComponent(id)}/refresh-members`, {
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
  webhookDeliveryEvents({
    page,
    pageSize,
    status,
    routeId,
    query,
  }: {
    page: number;
    pageSize: number;
    status?: WebhookDeliveryStatus;
    routeId?: string;
    query?: string;
  }) {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status) params.set("status", status);
    if (routeId) params.set("route_id", routeId);
    if (query?.trim()) params.set("q", query.trim());
    return request<WebhookDeliveryEventPageOut>(`/api/v1/webhook-delivery-events?${params.toString()}`);
  },
  webhookDeliveryEvent(id: string) {
    return request<WebhookDeliveryEventDetailOut>(`/api/v1/webhook-delivery-events/${encodeURIComponent(id)}`);
  },
  testWebhookRoute(csrfToken: string, id: string, body: WebhookRouteTestRequest) {
    return request<WebhookDeliveryOut>(`/api/v1/webhook-routes/${encodeURIComponent(id)}/test`, {
      method: "POST",
      csrfToken,
      body,
    });
  },
  searchTeamsTargets(kind: "user" | "team" | "group", query: string) {
    const params = new URLSearchParams({ kind, q: query });
    return request<TeamsTargetSearchResult[]>(`/api/v1/teams-targets/search?${params.toString()}`);
  },
  teamChannels(teamId: string, query: string) {
    const params = new URLSearchParams({ q: query });
    return request<TeamsTargetSearchResult[]>(
      `/api/v1/teams-targets/teams/${encodeURIComponent(teamId)}/channels?${params.toString()}`,
    );
  },
  serviceUserChats(query: string) {
    const params = new URLSearchParams({ q: query });
    return request<TeamsTargetSearchResult[]>(`/api/v1/teams-targets/chats?${params.toString()}`);
  },
  groupMembers(groupId: string, query = "", offset = 0, limit = 100) {
    const params = new URLSearchParams({ q: query, offset: String(offset), limit: String(limit) });
    return request<TeamsGroupMemberPage>(`/api/v1/teams-targets/groups/${encodeURIComponent(groupId)}/members?${params.toString()}`);
  },
  groupMemberCount(groupId: string) {
    return request<TeamsGroupMemberCount>(`/api/v1/teams-targets/groups/${encodeURIComponent(groupId)}/members/count`);
  },
};
