import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ClipboardCopy,
  FileClock,
  MessageSquareText,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcwKey,
  Send,
  Trash2,
  type LucideIcon,
} from "lucide-react";

import { api } from "./api";
import { AppProvider, useAppContext } from "./app-context";
import {
  Card,
  ConfirmModal,
  DataTable,
  EmptyState,
  Field,
  LoadingScreen,
  Modal,
  PageIntro,
  StatusBadge,
  ToastViewport,
} from "./components";
import { isApiError } from "./errors";
import { ThemeToggle } from "./theme-toggle";
import type {
  AdminReadinessOut,
  AuditEventOut,
  BotConversationReferenceOut,
  GraphTargetKind,
  SystemLogEventOut,
  UserOut,
  WebhookDeliveryEventDetailOut,
  WebhookDeliveryEventOut,
  WebhookDeliveryEventPageOut,
  WebhookDeliveryEventSummaryOut,
  WebhookDeliveryStatus,
  WebhookRouteOut,
} from "./types";
import { classNames, compactJson, formatDateTime, formatRelativeTime } from "./utils";

type RouteName = "dashboard" | "webhooks" | "users" | "settings" | "logs" | "system-logs";
type DeliveryStatusFilter = "all" | WebhookDeliveryStatus;

const NAV: Array<{ route: RouteName; label: string; path: string; icon: string }> = [
  { route: "dashboard", label: "Dashboard", path: "/dashboard", icon: "D" },
  { route: "webhooks", label: "Webhooks", path: "/webhooks", icon: "W" },
  { route: "users", label: "Users", path: "/users", icon: "U" },
  { route: "settings", label: "Settings", path: "/settings", icon: "S" },
  { route: "logs", label: "Messages", path: "/logs", icon: "M" },
  { route: "system-logs", label: "System logs", path: "/system-logs", icon: "L" },
];

const DELIVERY_STATUS_FILTERS: Array<{ value: DeliveryStatusFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "delivered", label: "Delivered" },
  { value: "failed", label: "Failed" },
  { value: "rejected", label: "Rejected" },
];

function IconButton({
  label,
  icon: Icon,
  onClick,
  disabled,
  tone = "secondary",
  spinning = false,
}: {
  label: string;
  icon: LucideIcon;
  onClick: () => void;
  disabled?: boolean;
  tone?: "secondary" | "danger";
  spinning?: boolean;
}) {
  return (
    <button
      aria-label={label}
      className={classNames("icon-button", tone === "danger" && "icon-button--danger")}
      disabled={disabled}
      title={label}
      type="button"
      onClick={onClick}
    >
      <Icon aria-hidden="true" className={classNames("button-icon", spinning && "button-icon--spin")} focusable="false" />
    </button>
  );
}

function EmptyGuidance({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-guidance">
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}

function routeFromPath(pathname: string): RouteName {
  if (pathname === "/" || pathname === "/dashboard") return "dashboard";
  if (pathname === "/webhooks") return "webhooks";
  if (pathname === "/users") return "users";
  if (pathname === "/settings") return "settings";
  if (pathname === "/system-logs") return "system-logs";
  if (pathname === "/logs") return "logs";
  return "dashboard";
}

function LoginScreen() {
  const { login } = useAppContext();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      window.history.replaceState(null, "", "/dashboard");
    } catch (err) {
      setError(isApiError(err) ? err.message : err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-screen">
      <section className="login-panel">
        <div className="login-panel-header">
          <div className="app-mark">T</div>
          <ThemeToggle />
        </div>
        <div>
          <p className="eyebrow">Teams Rehook Workspace</p>
          <h1>Teams Rehook</h1>
          <p className="lede">Manage stable webhook routes that forward operational messages into Microsoft Teams conversations.</p>
        </div>
        <form className="compact-form" onSubmit={submit}>
          <Field label="Email">
            <input
              value={email}
              autoComplete="email"
              placeholder="admin@example.com"
              required
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>
          <Field label="Password">
            <input
              value={password}
              type="password"
              autoComplete="current-password"
              placeholder="Enter your password"
              required
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          {error ? <p className="form-error">{error}</p> : null}
          <button className="primary-button" type="submit" disabled={busy}>
            {busy ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}

function WebhookCopyPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const webhookUrl = useMemo(() => new URLSearchParams(window.location.search).get("url") ?? "", []);
  const [status, setStatus] = useState("");

  async function copyWebhookUrl() {
    if (!webhookUrl) return;
    try {
      await navigator.clipboard.writeText(webhookUrl);
      setStatus("Webhook URL copied.");
    } catch {
      inputRef.current?.focus();
      inputRef.current?.select();
      setStatus("Automatic copy failed. The URL is selected for manual copy.");
    }
  }

  return (
    <main className="public-copy-screen">
      <section className="public-copy-panel">
        <div className="login-panel-header">
          <div className="app-mark">T</div>
          <ThemeToggle />
        </div>
        <div>
          <p className="eyebrow">Teams Rehook</p>
          <h1>Copy webhook URL</h1>
        </div>
        <div className="copy-url-field">
          <label htmlFor="webhook-copy-url">Webhook URL</label>
          <input
            id="webhook-copy-url"
            ref={inputRef}
            readOnly
            value={webhookUrl}
            placeholder="No webhook URL provided"
            onFocus={(event) => event.currentTarget.select()}
          />
        </div>
        <button
          className="primary-button button-with-icon"
          type="button"
          disabled={!webhookUrl}
          onClick={() => void copyWebhookUrl()}
        >
          <ClipboardCopy aria-hidden="true" className="button-icon" focusable="false" />
          Copy URL
        </button>
        {status ? (
          <p className="copy-status" role="status" aria-live="polite">
            {status}
          </p>
        ) : null}
      </section>
    </main>
  );
}

function AppShell() {
  const { session, logout } = useAppContext();
  const [route, setRoute] = useState<RouteName>(() => routeFromPath(window.location.pathname));

  useEffect(() => {
    const onPop = () => setRoute(routeFromPath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  function navigate(next: RouteName, path: string) {
    window.history.pushState(null, "", path);
    setRoute(next);
  }

  if (session.status !== "authenticated") return null;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-row">
          <div className="app-mark">T</div>
          <div>
            <strong>Teams Rehook</strong>
            <span>Webhook Relay</span>
          </div>
        </div>
        <nav className="nav-list" aria-label="Primary navigation">
          {NAV.map((item) => (
            <button
              key={item.route}
              type="button"
              className={classNames("nav-link", route === item.route && "nav-link--active")}
              onClick={() => navigate(item.route, item.path)}
            >
              <span aria-hidden="true">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div>
            <strong>{session.user.display_name}</strong>
            <span>{session.user.email}</span>
          </div>
          <button className="ghost-button" type="button" onClick={() => void logout()}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="main-content">
        <header className="topbar">
          <div />
          <ThemeToggle />
        </header>
        {route === "dashboard" ? <DashboardPage /> : null}
        {route === "webhooks" ? <WebhooksPage /> : null}
        {route === "users" ? <UsersPage /> : null}
        {route === "settings" ? <SettingsPage /> : null}
        {route === "logs" ? <MessageLogsPage /> : null}
        {route === "system-logs" ? <SystemLogsPage /> : null}
      </main>
    </div>
  );
}

function DashboardPage() {
  const [routes, setRoutes] = useState<WebhookRouteOut[]>([]);
  const [references, setReferences] = useState<BotConversationReferenceOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextRoutes, nextReferences] = await Promise.all([api.webhookRoutes(), api.botConversationReferences()]);
      setRoutes(nextRoutes);
      setReferences(nextReferences);
    } catch (err) {
      setError(isApiError(err) ? err.message : "Dashboard data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const counts = useMemo(
    () => ({
      routes: routes.length,
      active: routes.filter((route) => route.is_active).length,
      attention: routes.filter((route) => route.last_delivery_status === "failed" || route.last_delivery_status === "rejected").length,
      conversations: references.length,
    }),
    [routes, references],
  );
  const recentRoutes = useMemo(() => routes.slice(0, 5), [routes]);
  const attentionRoutes = useMemo(
    () => routes.filter((route) => route.last_delivery_status === "failed" || route.last_delivery_status === "rejected").slice(0, 5),
    [routes],
  );
  const inactiveRoutes = useMemo(() => routes.filter((route) => !route.is_active).slice(0, 5), [routes]);
  const untestedRoutes = useMemo(() => routes.filter((route) => route.is_active && !route.last_delivery_status).slice(0, 5), [routes]);
  const metricValue = (value: number) => (loading ? "..." : error ? "-" : value);

  return (
    <>
      <PageIntro
        eyebrow="Overview"
        title="Teams Rehook dashboard"
        description="Monitor relay routes, Teams conversations and recent delivery health from one operational view."
      />
      <div className="metric-grid">
        <Card className="metric-card">
          <span>Webhook routes</span>
          <strong>{metricValue(counts.routes)}</strong>
        </Card>
        <Card className="metric-card">
          <span>Active routes</span>
          <strong>{metricValue(counts.active)}</strong>
        </Card>
        <Card className="metric-card">
          <span>Needs attention</span>
          <strong>{metricValue(counts.attention)}</strong>
        </Card>
        <Card className="metric-card">
          <span>Known conversations</span>
          <strong>{metricValue(counts.conversations)}</strong>
        </Card>
      </div>
      <div className="attention-grid">
        <Card title="Needs attention" description="Routes with failed or rejected last delivery status.">
          {attentionRoutes.length ? (
            <ul className="compact-list">
              {attentionRoutes.map((route) => (
                <li key={route.id}>
                  <strong>{route.name}</strong>
                  <span>{route.last_delivery_status === "failed" ? "Last delivery failed" : "Last request was rejected"}</span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyGuidance
              title="No delivery problems"
              body="Failed or rejected route status will appear here after webhook requests or manual tests."
            />
          )}
        </Card>
        <Card title="Setup gaps" description="Routes and conversations that still need operator action.">
          <ul className="compact-list">
            {!references.length ? (
              <li>
                <strong>No known conversations</strong>
                <span>Add the bot to a Teams chat or channel, then send or mention the bot once.</span>
              </li>
            ) : null}
            {untestedRoutes.map((route) => (
              <li key={route.id}>
                <strong>{route.name}</strong>
                <span>Send a test message before giving the relay URL to a source system.</span>
              </li>
            ))}
            {inactiveRoutes.map((route) => (
              <li key={route.id}>
                <strong>{route.name}</strong>
                <span>Route is disabled and will reject incoming webhook requests.</span>
              </li>
            ))}
            {references.length && !untestedRoutes.length && !inactiveRoutes.length ? (
              <li>
                <strong>No setup gaps</strong>
                <span>Active routes have delivery history and known conversations are available.</span>
              </li>
            ) : null}
          </ul>
        </Card>
      </div>
      <Card title="Recent webhook routes" description="Latest relay routes and their current delivery status.">
        <DataTable
          columns={["Route", "Target", "Active", "Last delivery", "Updated"]}
          rows={recentRoutes.map((route) => [
            <strong>{route.name}</strong>,
            <div className="stacked-cell">
              <span>{route.target_name}</span>
              <span className="muted">{route.source_system || "No source system"}</span>
            </div>,
            route.is_active ? <StatusBadge label="Active" tone="success" /> : <StatusBadge label="Disabled" tone="warn" />,
            <DeliveryStatusBadge route={route} />,
            formatDateTime(route.updated_at),
          ])}
          emptyTitle="No webhook routes"
          emptyBody="Start by adding the bot to a Teams conversation, capture that conversation, create a route, then send a test message."
          loading={loading}
          loadingLabel="Loading recent webhook routes..."
          error={error}
          onRetry={() => void refresh()}
          rowKey={(index) => recentRoutes[index]?.id ?? index}
        />
      </Card>
    </>
  );
}

function WebhooksPage() {
  const { session, notify } = useAppContext();
  const [routes, setRoutes] = useState<WebhookRouteOut[]>([]);
  const [editing, setEditing] = useState<WebhookRouteOut | null>(null);
  const [viewingLogs, setViewingLogs] = useState<WebhookRouteOut | null>(null);
  const [confirmingRegeneration, setConfirmingRegeneration] = useState<WebhookRouteOut | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState<WebhookRouteOut | null>(null);
  const [regeneratedUrl, setRegeneratedUrl] = useState<{ routeName: string; url: string } | null>(null);
  const [testResult, setTestResult] = useState<WebhookRouteOut | null>(null);
  const [viewingBotReferences, setViewingBotReferences] = useState(false);
  const [botDefaultServiceUrl, setBotDefaultServiceUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [testingId, setTestingId] = useState("");
  const [regeneratingId, setRegeneratingId] = useState("");
  const [deletingId, setDeletingId] = useState("");
  const [refreshingNames, setRefreshingNames] = useState(false);
  const [refreshingRouteNameId, setRefreshingRouteNameId] = useState("");
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setRoutes(await api.webhookRoutes());
    } catch (err) {
      setError(isApiError(err) ? err.message : "Webhook routes could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [csrfToken, refresh]);

  useEffect(() => {
    void api.webhookRouteDefaults().then((defaults) => setBotDefaultServiceUrl(defaults.bot_default_service_url));
  }, []);

  async function deleteRoute(route: WebhookRouteOut) {
    setDeletingId(route.id);
    try {
      await api.deleteWebhookRoute(csrfToken, route.id);
      notify({ tone: "info", title: "Webhook route deleted", description: route.name });
      await refresh();
      setConfirmingDelete(null);
    } catch (err) {
      notify({
        tone: "error",
        title: "Delete failed",
        description: isApiError(err) ? err.message : "The route could not be deleted.",
      });
    } finally {
      setDeletingId("");
    }
  }

  async function testRoute(route: WebhookRouteOut) {
    setTestingId(route.id);
    try {
      await api.testWebhookRoute(csrfToken, route.id, {
        title: `Relay test: ${route.name}`,
        text: "This test message was sent from Teams Rehook.",
        severity: "info",
      });
      setTestResult(route);
      notify({ tone: "success", title: "Test delivered", description: graphTargetLabel(route) });
      await refresh();
    } catch (error) {
      notify({
        tone: "error",
        title: "Test failed",
        description: isApiError(error) ? error.message : "The route could not be tested.",
      });
      await refresh();
    } finally {
      setTestingId("");
    }
  }

  async function copyText(value: string, description: string) {
    await navigator.clipboard.writeText(value);
    notify({ tone: "success", title: "Webhook URL copied", description });
  }

  async function regenerateWebhookUrl(route: WebhookRouteOut) {
    setRegeneratingId(route.id);
    try {
      const updated = await api.regenerateWebhookRouteUrl(csrfToken, route.id);
      if (updated.webhook_url) void navigator.clipboard.writeText(updated.webhook_url).catch(() => undefined);
      if (updated.webhook_url) setRegeneratedUrl({ routeName: route.name, url: updated.webhook_url });
      notify({ tone: "success", title: "Webhook URL regenerated", description: "The new URL was copied to the clipboard." });
      await refresh();
    } catch (error) {
      notify({
        tone: "error",
        title: "Regeneration failed",
        description: isApiError(error) ? error.message : "The route URL could not be regenerated.",
      });
    } finally {
      setRegeneratingId("");
    }
  }

  async function refreshGraphNames() {
    setRefreshingNames(true);
    try {
      const result = await api.refreshWebhookRouteGraphNames(csrfToken);
      if (!result.ok) {
        notify({
          tone: "error",
          title: "Name refresh failed",
          description: result.error || "Microsoft Graph could not resolve the names.",
        });
        return;
      }
      const changed = result.routes_updated + result.references_updated;
      notify({
        tone: "success",
        title: "Names refreshed",
        description: changed ? `${changed} records updated from Microsoft Graph.` : "All known names are already current.",
      });
      await refresh();
    } catch (err) {
      notify({
        tone: "error",
        title: "Name refresh failed",
        description: isApiError(err) ? err.message : "Microsoft Graph could not resolve the names.",
      });
    } finally {
      setRefreshingNames(false);
    }
  }

  async function refreshRouteGraphNames(route: WebhookRouteOut) {
    setRefreshingRouteNameId(route.id);
    try {
      const result = await api.refreshSingleWebhookRouteGraphNames(csrfToken, route.id);
      if (!result.ok) {
        notify({
          tone: "error",
          title: "Name refresh failed",
          description: result.error || "Microsoft Graph could not resolve the route name.",
        });
        return;
      }
      notify({
        tone: "success",
        title: "Names refreshed",
        description: result.routes_updated ? route.name : "This route already has the current Graph names.",
      });
      await refresh();
    } catch (err) {
      notify({
        tone: "error",
        title: "Name refresh failed",
        description: isApiError(err) ? err.message : "Microsoft Graph could not resolve the route name.",
      });
    } finally {
      setRefreshingRouteNameId("");
    }
  }

  return (
    <>
      <PageIntro
        eyebrow="Teams Rehook"
        title="Webhook routes"
        description="Map stable relay webhook URLs to Teams bot targets and validate delivery with deterministic test sends."
        actions={
          <div className="row-actions">
            <button
              className="secondary-button button-with-icon"
              type="button"
              disabled={refreshingNames}
              onClick={() => void refreshGraphNames()}
            >
              <RefreshCw
                aria-hidden="true"
                className={classNames("button-icon", refreshingNames ? "button-icon--spin" : null)}
                focusable="false"
              />
              Refresh names
            </button>
            <button
              className="secondary-button button-with-icon"
              type="button"
              onClick={() => setViewingBotReferences(true)}
            >
              <MessageSquareText aria-hidden="true" className="button-icon" focusable="false" />
              Known conversations
            </button>
            <button
              className="primary-button button-with-icon"
              type="button"
              onClick={() => setEditing(emptyWebhookRoute(botDefaultServiceUrl))}
            >
              <Plus aria-hidden="true" className="button-icon" focusable="false" />
              New route
            </button>
          </div>
        }
      />
      <Card>
        <DataTable
          columns={["Route", "Target", "Health", "Relay URL", "Actions"]}
          rows={routes.map((route) => [
            <div className="stacked-cell">
              <strong>{route.name}</strong>
              <span className="muted">{route.source_system || "No source system"}</span>
              {route.bot_target_source === "bot_command" ? <StatusBadge label="Bot registered" tone="success" /> : null}
              {route.bot_target_source === "conversation_reference" ? <StatusBadge label="Conversation selected" tone="success" /> : null}
            </div>,
            <div className="stacked-cell">
              <strong>{route.target_name}</strong>
              <GraphTargetSummary
                kind={route.graph_target_kind}
                targetName={route.target_name}
                teamName={route.graph_team_name}
                teamId={route.graph_team_id}
                channelId={route.graph_channel_id}
              />
            </div>,
            <div className="stacked-cell">
              {route.is_active ? <StatusBadge label="Active" tone="success" /> : <StatusBadge label="Disabled" tone="warn" />}
              <DeliveryStatusBadge route={route} />
            </div>,
            route.webhook_url ? (
              <button
                className="secondary-button secondary-button--small button-with-icon"
                type="button"
                onClick={() => void copyText(route.webhook_url ?? "", route.name)}
              >
                <ClipboardCopy aria-hidden="true" className="button-icon" focusable="false" />
                Copy URL
              </button>
            ) : (
              <span className="muted">Unavailable for old route</span>
            ),
            <div className="row-actions">
              <IconButton
                label={testingId === route.id ? "Sending test" : "Send test"}
                icon={Send}
                disabled={testingId === route.id}
                onClick={() => void testRoute(route)}
              />
              <IconButton label="Edit route" icon={Pencil} onClick={() => setEditing(route)} />
              <IconButton label="View delivery logs" icon={FileClock} onClick={() => setViewingLogs(route)} />
              <IconButton
                label={refreshingRouteNameId === route.id ? "Refreshing Graph names" : "Refresh Graph names"}
                icon={RefreshCw}
                disabled={refreshingRouteNameId === route.id}
                spinning={refreshingRouteNameId === route.id}
                onClick={() => void refreshRouteGraphNames(route)}
              />
              <IconButton
                label={regeneratingId === route.id ? "Regenerating relay URL" : "Regenerate relay URL"}
                icon={RotateCcwKey}
                disabled={regeneratingId === route.id}
                spinning={regeneratingId === route.id}
                onClick={() => setConfirmingRegeneration(route)}
              />
              <IconButton label="Delete route" icon={Trash2} tone="danger" onClick={() => setConfirmingDelete(route)} />
            </div>,
          ])}
          emptyTitle="No webhook routes"
          emptyBody="Add the bot to a Teams chat or channel, open Known conversations to confirm capture, create a route, send a test, then copy the relay URL into the source system."
          loading={loading}
          loadingLabel="Loading webhook routes..."
          error={error}
          onRetry={() => void refresh()}
          rowKey={(index) => routes[index]?.id ?? index}
        />
      </Card>
      {editing ? (
        <WebhookRouteModal
          route={editing.id ? editing : null}
          initial={editing}
          onClose={() => setEditing(null)}
          onChanged={refresh}
        />
      ) : null}
      {viewingLogs ? <WebhookDeliveryLogsModal route={viewingLogs} onClose={() => setViewingLogs(null)} /> : null}
      {confirmingRegeneration ? (
        <RegenerateWebhookUrlModal
          route={confirmingRegeneration}
          busy={regeneratingId === confirmingRegeneration.id}
          onClose={() => setConfirmingRegeneration(null)}
          onCopyCurrent={() => void copyText(confirmingRegeneration.webhook_url ?? "", confirmingRegeneration.name)}
          onConfirm={async () => {
            await regenerateWebhookUrl(confirmingRegeneration);
            setConfirmingRegeneration(null);
          }}
        />
      ) : null}
      {confirmingDelete ? (
        <ConfirmModal
          title="Delete webhook route"
          description={`Delete ${confirmingDelete.name}?`}
          confirmLabel="Delete route"
          busyLabel="Deleting..."
          busy={deletingId === confirmingDelete.id}
          onClose={() => setConfirmingDelete(null)}
          onConfirm={() => deleteRoute(confirmingDelete)}
        >
          <div className="warning-box">
            <strong>This route will stop accepting webhook requests.</strong>
            <p>Source systems using this relay URL will fail until they are pointed to another active route.</p>
          </div>
        </ConfirmModal>
      ) : null}
      {regeneratedUrl ? (
        <WebhookUrlRevealModal
          title="Webhook URL regenerated"
          routeName={regeneratedUrl.routeName}
          note="The previous URL stopped working immediately. Update any source systems that still use it."
          onCopy={() => void copyText(regeneratedUrl.url, regeneratedUrl.routeName)}
          onClose={() => setRegeneratedUrl(null)}
        />
      ) : null}
      {testResult ? <TestDeliveryResultModal route={testResult} onClose={() => setTestResult(null)} /> : null}
      {viewingBotReferences ? (
        <BotConversationReferencesModal
          onClose={() => setViewingBotReferences(false)}
          onCreateRoute={(reference) => {
            setEditing(webhookRouteFromReference(reference));
            setViewingBotReferences(false);
          }}
        />
      ) : null}
    </>
  );
}

function RegenerateWebhookUrlModal({
  route,
  busy,
  onClose,
  onCopyCurrent,
  onConfirm,
}: {
  route: WebhookRouteOut;
  busy: boolean;
  onClose: () => void;
  onCopyCurrent: () => void;
  onConfirm: () => Promise<void>;
}) {
  return (
    <Modal title="Regenerate relay URL" description={`Generate a new relay URL for ${route.name}.`} onClose={onClose}>
      <div className="warning-box">
        <strong>Old URL becomes invalid immediately.</strong>
        <p>Any source system still using the current URL will receive a not found response as soon as the new URL is created.</p>
      </div>
      {route.webhook_url ? (
        <div className="webhook-url-box">
          <strong>Current relay webhook URL</strong>
          <small>The current URL is hidden. Copy it if you need to update another system before regenerating.</small>
          <button className="secondary-button secondary-button--small" type="button" onClick={onCopyCurrent}>
            Copy current URL
          </button>
        </div>
      ) : null}
      <div className="form-actions">
        <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button className="danger-button" type="button" onClick={() => void onConfirm()} disabled={busy}>
          {busy ? "Regenerating..." : "Regenerate URL"}
        </button>
      </div>
    </Modal>
  );
}

function WebhookUrlRevealModal({
  title,
  routeName,
  note,
  onCopy,
  onClose,
}: {
  title: string;
  routeName: string;
  note: string;
  onCopy: () => void;
  onClose: () => void;
}) {
  return (
    <Modal title={title} description={routeName} onClose={onClose}>
      <div className="webhook-url-box">
        <strong>Relay webhook URL</strong>
        <button className="secondary-button secondary-button--small" type="button" onClick={onCopy}>
          Copy URL
        </button>
        <small>{note}</small>
      </div>
      <div className="form-actions">
        <button className="primary-button" type="button" onClick={onClose}>
          Done
        </button>
      </div>
    </Modal>
  );
}

function TestDeliveryResultModal({ route, onClose }: { route: WebhookRouteOut; onClose: () => void }) {
  return (
    <Modal title="Test message delivered" description={route.name} onClose={onClose}>
      <div className="test-result-layout">
        <section className="test-result-section">
          <strong>Expected Graph target</strong>
          {route.graph_target_kind ? (
            <GraphTargetSummary
              kind={route.graph_target_kind}
              targetName={route.target_name}
              teamName={route.graph_team_name}
              teamId={route.graph_team_id}
              channelId={route.graph_channel_id}
            />
          ) : (
            <p className="muted">No Graph target selected.</p>
          )}
        </section>
        <section className="test-result-section">
          <strong>Bot delivery target</strong>
          <dl className="definition-list">
            <dt>Service URL</dt>
            <dd>{route.bot_service_url}</dd>
            <dt>Conversation ID</dt>
            <dd>{shortId(route.bot_conversation_id)}</dd>
            {route.bot_target_source === "bot_command" ? (
              <>
                <dt>Registered by</dt>
                <dd>{route.bot_registered_by_id ? shortId(route.bot_registered_by_id) : "Bot command"}</dd>
                <dt>Registered at</dt>
                <dd>{route.bot_registered_at ? formatDateTime(route.bot_registered_at) : "-"}</dd>
              </>
            ) : null}
          </dl>
        </section>
        <div className="warning-box">
          <strong>Manual verification point.</strong>
          <p>If the message did not appear in the expected Graph target, this Bot conversation ID belongs to a different Teams context.</p>
        </div>
      </div>
      <div className="form-actions">
        <button className="primary-button" type="button" onClick={onClose}>
          Done
        </button>
      </div>
    </Modal>
  );
}

function BotConversationReferencesModal({
  onClose,
  onCreateRoute,
}: {
  onClose: () => void;
  onCreateRoute: (reference: BotConversationReferenceOut) => void;
}) {
  const [references, setReferences] = useState<BotConversationReferenceOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError("");
    api
      .botConversationReferences()
      .then((rows) => {
        if (mounted) setReferences(rows);
      })
      .catch((err) => {
        if (mounted) setError(isApiError(err) ? err.message : "Bot conversations could not be loaded.");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <Modal
      title="Known Teams conversations"
      description="Conversations captured from inbound Teams bot activities. Graph-discovered targets are not sendable until the bot has a valid conversation reference."
      panelClassName="delivery-logs-modal"
      onClose={onClose}
    >
      {loading ? <p className="muted">Loading bot conversations...</p> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!loading && !error && references.length === 0 ? (
        <div className="guidance-box">
          <strong>No bot conversations captured yet.</strong>
          <p>Add Teams Rehook to a chat or channel, then send a message or mention the bot. The next inbound bot activity stores the service URL and conversation ID needed for delivery.</p>
          <p>After a conversation appears here, create a route from it and use Send test before sharing the relay URL with a source system.</p>
        </div>
      ) : null}
      {references.length ? (
        <div className="conversation-reference-list">
          {references.map((reference) => (
            <section className="test-result-section" key={reference.id}>
              <div className="delivery-event-detail-header">
                <div>
                  <h3>{referenceTitle(reference)}</h3>
                  <p>{formatDateTime(reference.last_seen_at)} · {reference.raw_activity_type || "activity"}</p>
                </div>
                <StatusBadge label={reference.scope || "unknown"} tone={reference.scope === "channel" ? "success" : "warn"} />
              </div>
              <dl className="definition-list">
                <dt>Conversation</dt>
                <dd>{reference.conversation_id}</dd>
                <dt>Service URL</dt>
                <dd>{reference.service_url}</dd>
                <dt>Team</dt>
                <dd>{identityLabel(reference.team_name, reference.graph_team_id || reference.team_id)}</dd>
                <dt>Channel</dt>
                <dd>{identityLabel(reference.channel_name, reference.channel_id)}</dd>
                <dt>User</dt>
                <dd>{identityLabel(reference.user_name, reference.graph_user_id || reference.user_id)}</dd>
              </dl>
              <div className="form-actions">
                <button className="secondary-button secondary-button--small" type="button" onClick={() => onCreateRoute(reference)}>
                  Create route
                </button>
              </div>
            </section>
          ))}
        </div>
      ) : null}
      <div className="form-actions">
        <button className="primary-button" type="button" onClick={onClose}>
          Done
        </button>
      </div>
    </Modal>
  );
}

function referenceTitle(reference: BotConversationReferenceOut): string {
  if (reference.team_name && reference.channel_name) return `${reference.team_name} / ${reference.channel_name}`;
  if (reference.channel_name) return reference.channel_name;
  if (reference.team_name) return reference.team_name;
  if (reference.user_name) return reference.user_name;
  return reference.conversation_type === "personal" ? "Personal chat" : "Teams conversation";
}

function referenceSubtitle(reference: BotConversationReferenceOut): string {
  const parts = [
    reference.scope || reference.conversation_type || "conversation",
    `seen ${formatRelativeTime(reference.last_seen_at)}`,
    reference.channel_id ? `channel ${shortId(reference.channel_id)}` : "",
    reference.graph_user_id || reference.user_id ? `user ${shortId(reference.graph_user_id || reference.user_id)}` : "",
  ].filter(Boolean);
  return parts.join(" · ");
}

function identityLabel(name: string, id: string): string {
  if (name && id) return `${name} (${shortId(id)})`;
  return name || id || "-";
}

function referenceGraphKind(reference: BotConversationReferenceOut): GraphTargetKind | "" {
  if (reference.scope === "channel" || reference.channel_id) return "channel";
  if (reference.scope === "team" || reference.graph_team_id) return "team";
  if (reference.scope === "user" || reference.graph_user_id || reference.user_id) return "user";
  return "";
}

function referenceGraphTargetId(reference: BotConversationReferenceOut): string {
  const kind = referenceGraphKind(reference);
  if (kind === "channel") return reference.channel_id;
  if (kind === "team") return reference.graph_team_id || reference.team_id;
  if (kind === "user") return reference.graph_user_id || reference.user_id;
  return "";
}

function referenceTargetName(reference: BotConversationReferenceOut): string {
  return referenceTitle(reference);
}

function GraphTargetSummary({
  kind,
  targetName,
  teamName,
  teamId,
  channelId,
}: {
  kind: GraphTargetKind | "";
  targetName: string;
  teamName: string;
  teamId: string;
  channelId: string;
}) {
  if (!kind) return null;
  const label = kind === "channel" ? "Graph channel" : kind === "team" ? "Graph team" : "Graph user";
  const title = kind === "channel" && teamName ? targetName || teamName : targetName || teamName || "Selected target";
  const technicalParts = [teamId ? `team ${shortId(teamId)}` : "", channelId ? `channel ${shortId(channelId)}` : ""].filter(Boolean);
  return (
    <span className="graph-target-summary">
      <span>{label}: {title}</span>
      {technicalParts.length ? <small>{technicalParts.join(" / ")}</small> : null}
    </span>
  );
}

function graphTargetLabel(route: WebhookRouteOut): string {
  if (!route.graph_target_kind) return route.target_name;
  if (route.graph_target_kind === "channel") return `Expected channel: ${route.target_name}`;
  if (route.graph_target_kind === "team") return `Expected team: ${route.target_name}`;
  return `Expected user: ${route.target_name}`;
}

function shortId(value: string): string {
  return value.length > 10 ? `${value.slice(0, 8)}...` : value;
}

function DeliveryStatusBadge({ route }: { route: WebhookRouteOut }) {
  if (!route.last_delivery_status) return <span className="muted">Not tested</span>;
  const statusLabel = route.last_delivery_status.charAt(0).toUpperCase() + route.last_delivery_status.slice(1);
  const label = formatRelativeTime(route.last_delivery_at);
  const detail = route.last_delivery_at ? `${statusLabel} · ${formatDateTime(route.last_delivery_at)}` : statusLabel;
  const ariaLabel = `${statusLabel} ${label}`;
  if (route.last_delivery_status === "delivered") {
    return <StatusBadge ariaLabel={ariaLabel} label={label} title={detail} tone="success" />;
  }
  if (route.last_delivery_status === "failed") {
    return <StatusBadge ariaLabel={ariaLabel} label={label} title={detail} tone="danger" />;
  }
  return <StatusBadge ariaLabel={ariaLabel} label={label} title={detail} tone="warn" />;
}

function emptyWebhookRoute(botDefaultServiceUrl = ""): WebhookRouteOut {
  return {
    id: "",
    organization_id: "",
    name: "",
    source_system: "",
    is_active: true,
    target_type: "bot_conversation",
    target_name: "",
    bot_service_url: botDefaultServiceUrl,
    bot_conversation_id: "",
    graph_target_kind: "",
    graph_target_id: "",
    graph_team_id: "",
    graph_team_name: "",
    graph_channel_id: "",
    bot_target_source: "",
    bot_registered_by_id: "",
    bot_registered_at: null,
    webhook_url: null,
    webhook_url_available: false,
    last_delivery_status: null,
    last_delivery_at: null,
    created_at: "",
    updated_at: "",
  };
}

function webhookRouteFromReference(reference: BotConversationReferenceOut): WebhookRouteOut {
  const kind = referenceGraphKind(reference);
  return {
    ...emptyWebhookRoute(reference.service_url),
    source_system: "teams",
    target_name: referenceTargetName(reference),
    bot_service_url: reference.service_url,
    bot_conversation_id: reference.conversation_id,
    graph_target_kind: kind,
    graph_target_id: referenceGraphTargetId(reference),
    graph_team_id: reference.graph_team_id,
    graph_team_name: reference.team_name,
    graph_channel_id: kind === "channel" ? reference.channel_id : "",
    bot_target_source: "conversation_reference",
    bot_registered_by_id: reference.graph_user_id || reference.user_id,
  };
}

function WebhookRouteModal({
  route,
  initial,
  onClose,
  onChanged,
}: {
  route: WebhookRouteOut | null;
  initial: WebhookRouteOut;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const { session, notify } = useAppContext();
  const [name, setName] = useState(initial.name);
  const [sourceSystem, setSourceSystem] = useState(initial.source_system);
  const [isActive, setIsActive] = useState(initial.is_active);
  const [targetName, setTargetName] = useState(initial.target_name);
  const [botServiceUrl, setBotServiceUrl] = useState(initial.bot_service_url);
  const [botConversationId, setBotConversationId] = useState(initial.bot_conversation_id);
  const [graphTargetKind, setGraphTargetKind] = useState<GraphTargetKind | "">(initial.graph_target_kind);
  const [graphTargetId, setGraphTargetId] = useState(initial.graph_target_id);
  const [graphTeamId, setGraphTeamId] = useState(initial.graph_team_id);
  const [graphTeamName, setGraphTeamName] = useState(initial.graph_team_name);
  const [graphChannelId, setGraphChannelId] = useState(initial.graph_channel_id);
  const [botTargetSource, setBotTargetSource] = useState(initial.bot_target_source);
  const [references, setReferences] = useState<BotConversationReferenceOut[]>([]);
  const [referencesLoading, setReferencesLoading] = useState(false);
  const [referencesError, setReferencesError] = useState("");
  const [conversationSearch, setConversationSearch] = useState("");
  const [showAdvancedTarget, setShowAdvancedTarget] = useState(false);
  const [createdWebhookUrl, setCreatedWebhookUrl] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";
  const selectedReference = useMemo(
    () => references.find((reference) => reference.conversation_id === botConversationId) ?? null,
    [botConversationId, references],
  );
  const filteredReferences = useMemo(() => {
    const query = conversationSearch.trim().toLowerCase();
    if (!query) return references;
    return references.filter((reference) =>
      [
        referenceTitle(reference),
        referenceSubtitle(reference),
        reference.conversation_id,
        reference.service_url,
        reference.team_name,
        reference.channel_name,
        reference.user_name,
      ]
        .filter(Boolean)
        .some((value) => value.toLowerCase().includes(query)),
    );
  }, [conversationSearch, references]);

  const loadReferences = useCallback(async () => {
    setReferencesLoading(true);
    setReferencesError("");
    try {
      setReferences(await api.botConversationReferences());
    } catch (err) {
      setReferencesError(isApiError(err) ? err.message : "Bot conversations could not be loaded.");
    } finally {
      setReferencesLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadReferences();
  }, [loadReferences]);

  function applyReference(reference: BotConversationReferenceOut) {
    const kind = referenceGraphKind(reference);
    setTargetName(referenceTargetName(reference));
    setBotServiceUrl(reference.service_url);
    setBotConversationId(reference.conversation_id);
    setGraphTargetKind(kind);
    setGraphTargetId(referenceGraphTargetId(reference));
    setGraphTeamId(reference.graph_team_id);
    setGraphTeamName(reference.team_name);
    setGraphChannelId(kind === "channel" ? reference.channel_id : "");
    setBotTargetSource("conversation_reference");
    setShowAdvancedTarget(false);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const body = {
      name: name.trim(),
      source_system: sourceSystem.trim(),
      is_active: isActive,
      target_type: "bot_conversation" as const,
      target_name: targetName.trim(),
      bot_service_url: botServiceUrl.trim(),
      bot_conversation_id: botConversationId.trim(),
      graph_target_kind: graphTargetKind || null,
      graph_target_id: graphTargetId.trim(),
      graph_team_id: graphTeamId.trim(),
      graph_team_name: graphTeamName.trim(),
      graph_channel_id: graphChannelId.trim(),
      bot_target_source: botTargetSource.trim(),
    };
    try {
      if (route) {
        await api.updateWebhookRoute(csrfToken, route.id, body);
        notify({ tone: "success", title: "Webhook route updated" });
        await onChanged();
        onClose();
      } else {
        const created = await api.createWebhookRoute(csrfToken, body);
        setCreatedWebhookUrl(created.webhook_url);
        if (created.webhook_url) void navigator.clipboard.writeText(created.webhook_url).catch(() => undefined);
        notify({ tone: "success", title: "Webhook route created", description: "The generated URL was copied to the clipboard." });
        await onChanged();
      }
    } catch (err) {
      setError(isApiError(err) ? err.message : "Saving the webhook route failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={route ? "Edit webhook route" : "New webhook route"}
      description="Create stable relay URLs from Teams conversations the bot has already captured."
      onClose={onClose}
    >
      <form className="compact-form" onSubmit={submit}>
        <Field label="Name">
          <input value={name} required maxLength={200} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label="Source system" hint="For example PRTG, macmon or firewall-events.">
          <input value={sourceSystem} maxLength={120} onChange={(event) => setSourceSystem(event.target.value)} />
        </Field>
        <label className="checkbox-field">
          <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />
          <span>Route is active</span>
        </label>
        <div className="graph-target-picker">
          <div className="graph-target-picker-header">
            <div>
              <strong>Teams conversation</strong>
              <p>Search known bot conversations and select one delivery target.</p>
            </div>
          </div>
          {targetName ? (
            <div className="selected-conversation-summary">
              <div className="selected-conversation-copy">
                <span>Current target</span>
                <strong>{selectedReference ? referenceTitle(selectedReference) : targetName}</strong>
              </div>
              <StatusBadge label="Selected" tone="success" />
            </div>
          ) : null}
          {referencesLoading ? <p className="muted">Loading known conversations...</p> : null}
          {referencesError ? (
            <div className="inline-error">
              <p className="form-error">{referencesError}</p>
              <button className="secondary-button secondary-button--small" type="button" onClick={() => void loadReferences()}>
                Retry
              </button>
            </div>
          ) : null}
          {!referencesLoading && !referencesError && references.length === 0 ? (
            <div className="guidance-box">
              <strong>No bot conversations captured yet.</strong>
              <p>Add the bot to a Teams chat or channel, then send or mention the bot once. Graph search can help identify Teams targets, but the bot still needs a captured conversation before Teams Rehook can send there.</p>
              <p>Use the manual delivery target only when you already have a valid Bot Framework service URL and conversation ID.</p>
            </div>
          ) : null}
          {references.length ? (
            <>
              <Field label="Find conversation">
                <input
                  value={conversationSearch}
                  placeholder="Search by team, channel, user or ID"
                  onChange={(event) => setConversationSearch(event.target.value)}
                />
              </Field>
              {filteredReferences.length ? (
                <div className="compact-conversation-list">
                  {filteredReferences.map((reference) => {
                    const selected = reference.conversation_id === botConversationId;
                    return (
                      <button
                        key={reference.id}
                        type="button"
                        className={selected ? "is-selected" : undefined}
                        aria-pressed={selected}
                        title={`${referenceTitle(reference)} - ${referenceSubtitle(reference)}`}
                        onClick={() => applyReference(reference)}
                      >
                        <span className="compact-conversation-list-copy">
                          <strong>{referenceTitle(reference)}</strong>
                          <small>{referenceSubtitle(reference)}</small>
                        </span>
                        {selected ? <StatusBadge label="Selected" tone="success" /> : null}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <p className="muted">No conversations match this search.</p>
              )}
            </>
          ) : null}
        </div>
        <button
          className="ghost-button ghost-button--small"
          type="button"
          onClick={() => setShowAdvancedTarget((current) => !current)}
        >
          {showAdvancedTarget ? "Hide advanced target fields" : "Show advanced target fields"}
        </button>
        {showAdvancedTarget ? (
          <div className="graph-target-picker">
            <div className="graph-target-picker-header">
              <div>
                <strong>Manual delivery target</strong>
                <p>Use this only when you already have a valid Bot Framework service URL and conversation ID for the target conversation.</p>
              </div>
              <StatusBadge label="Manual fallback" tone="warn" />
            </div>
            <Field label="Teams target name" hint="A human-readable label shown in the route table.">
              <input value={targetName} required maxLength={200} onChange={(event) => setTargetName(event.target.value)} />
            </Field>
            <Field label="Bot service URL" hint="Use the service URL from a known Bot Framework conversation reference.">
              <input
                value={botServiceUrl}
                required
                onChange={(event) => {
                  setBotServiceUrl(event.target.value);
                  setBotTargetSource("manual");
                }}
              />
            </Field>
            <Field label="Bot conversation ID" hint="Paste the full conversation ID. It is intentionally kept hidden in tables.">
              <textarea
                value={botConversationId}
                required
                onChange={(event) => {
                  setBotConversationId(event.target.value);
                  setBotTargetSource("manual");
                }}
              />
            </Field>
          </div>
        ) : null}
        {createdWebhookUrl ? (
          <div className="webhook-url-box">
            <strong>Relay webhook URL generated</strong>
            <small>The URL is hidden. It was copied automatically and remains available through the route table copy button.</small>
            <button
              className="secondary-button secondary-button--small"
              type="button"
              onClick={() => {
                void navigator.clipboard.writeText(createdWebhookUrl);
                notify({ tone: "success", title: "Webhook URL copied", description: name.trim() || "New route" });
              }}
            >
              Copy URL again
            </button>
          </div>
        ) : null}
        {error ? <p className="form-error">{error}</p> : null}
        <div className="form-actions">
          <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>
            {createdWebhookUrl ? "Done" : "Cancel"}
          </button>
          <button
            className="primary-button"
            type="submit"
            disabled={busy || Boolean(createdWebhookUrl) || !targetName.trim() || !botServiceUrl.trim() || !botConversationId.trim()}
          >
            {busy ? "Saving..." : route ? "Save" : "Create route"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function WebhookDeliveryLogsModal({ route, onClose }: { route: WebhookRouteOut; onClose: () => void }) {
  const [events, setEvents] = useState<WebhookDeliveryEventOut[]>([]);
  const [statusFilter, setStatusFilter] = useState<DeliveryStatusFilter>("all");
  const [selectedEventId, setSelectedEventId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const selectedEvent = useMemo(
    () => events.find((event) => event.id === selectedEventId) ?? events[0] ?? null,
    [events, selectedEventId],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const rows = await api.webhookRouteDeliveries(route.id, statusFilter === "all" ? undefined : statusFilter);
      setEvents(rows);
      setSelectedEventId(rows[0]?.id ?? "");
    } catch (err) {
      setError(isApiError(err) ? err.message : "Delivery logs could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [route.id, statusFilter]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <Modal
      title={`Delivery logs: ${route.name}`}
      description="Recent delivery attempts for this webhook route."
      panelClassName="delivery-logs-modal"
      onClose={onClose}
    >
      <div className="segmented-control" aria-label="Filter delivery logs by status">
        {DELIVERY_STATUS_FILTERS.map((filter) => (
          <button
            key={filter.value}
            type="button"
            className={classNames("segmented-control-button", statusFilter === filter.value && "is-active")}
            aria-pressed={statusFilter === filter.value}
            onClick={() => setStatusFilter(filter.value)}
          >
            {filter.label}
          </button>
        ))}
      </div>
      <div className="delivery-log-layout">
        <DataTable
          columns={["Status", "Time", "Message", "Payload", "Mode", "Error"]}
          rows={events.map((event) => [
            <DeliveryEventStatusBadge status={event.status} />,
            formatDateTime(event.created_at),
            <span>{eventTitle(event)}</span>,
            <span className="muted">{eventPayloadType(event)}</span>,
            <span className="muted">{eventDeliveryMode(event)}</span>,
            event.error ? <span className="form-error">{event.error}</span> : <span className="muted">-</span>,
          ])}
          emptyTitle="No delivery logs"
          emptyBody="Test sends and incoming webhooks will appear here."
          loading={loading}
          loadingLabel="Loading delivery logs..."
          error={error}
          onRetry={() => void refresh()}
          rowKey={(index) => events[index]?.id ?? index}
          rowClassName={(index) => (events[index]?.id === selectedEvent?.id ? "is-selected" : null)}
          onRowClick={(index) => setSelectedEventId(events[index]?.id ?? "")}
        />
        {!loading && !error && selectedEvent ? <DeliveryEventDetails event={selectedEvent} /> : null}
      </div>
    </Modal>
  );
}

function DeliveryEventStatusBadge({ status }: { status: WebhookDeliveryEventOut["status"] }) {
  if (status === "delivered") return <StatusBadge label="Delivered" tone="success" />;
  if (status === "failed") return <StatusBadge label="Failed" tone="danger" />;
  return <StatusBadge label="Rejected" tone="warn" />;
}

function DeliveryEventDetails({ event }: { event: WebhookDeliveryEventOut & Partial<WebhookDeliveryEventDetailOut> }) {
  const requestMetadata = event.request_metadata;
  const deliveryResult = event.delivery_result;
  return (
    <aside className="delivery-event-detail" aria-label="Delivery event details">
      <div className="delivery-event-detail-header">
        <div>
          <h3>{eventTitle(event)}</h3>
          <p>{formatDateTime(event.created_at)}</p>
        </div>
        <DeliveryEventStatusBadge status={event.status} />
      </div>

      <dl className="definition-list delivery-response-list">
        <dt>Route</dt>
        <dd>{event.route_name || (event.route_id ? shortId(event.route_id) : "-")}</dd>
        <dt>Target</dt>
        <dd>{event.target_name || "-"}</dd>
        <dt>Source</dt>
        <dd>{event.source_system || stringField(event.normalized_message, "source")}</dd>
        <dt>Mode</dt>
        <dd>{stringField(deliveryResult, "mode")}</dd>
        <dt>Status code</dt>
        <dd>{primitiveField(deliveryResult, "status_code")}</dd>
        <dt>Activity ID</dt>
        <dd>{stringField(deliveryResult, "activity_id")}</dd>
      </dl>

      {event.error ? (
        <section className="detail-section">
          <h4>Error</h4>
          <p className="form-error">{event.error}</p>
        </section>
      ) : null}

      <section className="detail-section">
        <h4>Request excerpt</h4>
        <pre className="json-block">{stringField(requestMetadata, "payload_preview")}</pre>
      </section>

      <section className="detail-section">
        <h4>Request metadata</h4>
        <dl className="definition-list">
          <dt>Content type</dt>
          <dd>{stringField(requestMetadata, "content_type")}</dd>
          <dt>Content length</dt>
          <dd>{primitiveField(requestMetadata, "content_length")}</dd>
          <dt>Client host</dt>
          <dd>{stringField(requestMetadata, "client_host")}</dd>
          <dt>Trigger</dt>
          <dd>{stringField(requestMetadata, "trigger")}</dd>
        </dl>
      </section>

      <section className="detail-section">
        <h4>Normalized message</h4>
        <JsonBlock value={event.normalized_message} />
      </section>

      <section className="detail-section">
        <h4>Sent activity</h4>
        <JsonBlock value={deliveryResult.activity} />
      </section>
    </aside>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="json-block">{formatJsonValue(value)}</pre>;
}

function formatJsonValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function stringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" && value.trim() ? value : "-";
}

function primitiveField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "-";
}

function eventTitle(event: WebhookDeliveryEventOut): string {
  const title = event.normalized_message.title;
  return typeof title === "string" && title.trim() ? title : "-";
}

function eventPayloadType(event: WebhookDeliveryEventOut): string {
  const rawType = event.normalized_message.raw_type;
  return typeof rawType === "string" && rawType.trim() ? rawType : "-";
}

function eventDeliveryMode(event: WebhookDeliveryEventOut): string {
  const mode = event.delivery_result.mode;
  const statusCode = event.delivery_result.status_code;
  const modeText = typeof mode === "string" && mode.trim() ? mode : "-";
  return typeof statusCode === "number" ? `${modeText} / ${statusCode}` : modeText;
}

function deliverySummaryMode(event: WebhookDeliveryEventSummaryOut): string {
  const mode = event.delivery_mode || "-";
  return typeof event.status_code === "number" ? `${mode} / ${event.status_code}` : mode;
}

function UsersPage() {
  const { session } = useAppContext();
  const [users, setUsers] = useState<UserOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setUsers(await api.adminUsers(csrfToken));
    } catch (err) {
      setError(isApiError(err) ? err.message : "Users could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [csrfToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <>
      <PageIntro
        eyebrow="Admin"
        title="Users"
        description="Manage administrator access for Teams Rehook operations."
      />
      <Card>
        <DataTable
          columns={["Name", "Email", "Role", "Status", "Created"]}
          rows={users.map((user) => [
            <strong>{user.display_name}</strong>,
            user.email,
            user.is_admin ? <StatusBadge label="Admin" tone="success" /> : <StatusBadge label="Member" />,
            user.is_active ? <StatusBadge label="Active" tone="success" /> : <StatusBadge label="Disabled" tone="danger" />,
            formatDateTime(user.created_at),
          ])}
          emptyTitle="No users"
          emptyBody="Users appear here after bootstrap or invitation flows."
          loading={loading}
          loadingLabel="Loading users..."
          error={error}
          onRetry={() => void refresh()}
          rowKey={(index) => users[index]?.id ?? index}
        />
      </Card>
    </>
  );
}

function SettingsPage() {
  const { session } = useAppContext();
  const [readiness, setReadiness] = useState<AdminReadinessOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setReadiness(await api.adminReadiness(csrfToken));
    } catch (err) {
      setError(isApiError(err) ? err.message : "Readiness data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [csrfToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <>
      <PageIntro
        eyebrow="Configuration"
        title="Readiness"
        description="Review delivery mode, integration readiness and runtime settings without exposing secrets."
      />
      {loading ? (
        <Card>
          <div className="table-state" role="status" aria-live="polite">
            <div className="spinner spinner--small" aria-hidden="true" />
            <p>Loading readiness...</p>
          </div>
        </Card>
      ) : error ? (
        <Card>
          <div className="table-state table-state--error" role="alert">
            <h3>Could not load readiness</h3>
            <p>{error}</p>
            <button className="secondary-button secondary-button--small" type="button" onClick={() => void refresh()}>
              Retry
            </button>
          </div>
        </Card>
      ) : readiness ? (
        <div className="settings-grid">
          <Card title="Delivery" description="Teams delivery mode and Bot Framework readiness.">
            <div className="readiness-header">
              <StatusBadge label={readiness.bot.ready ? "Ready" : "Action needed"} tone={readiness.bot.ready ? "success" : "warn"} />
              <StatusBadge label={readiness.delivery_mode} tone={readiness.delivery_mode === "real" ? "success" : "neutral"} />
            </div>
            <p className="muted">{readiness.bot.message}</p>
            <dl className="definition-list">
              <dt>Bot credentials</dt>
              <dd>{yesNo(readiness.bot.credentials_configured)}</dd>
              <dt>Default service URL</dt>
              <dd>{yesNo(readiness.bot.default_service_url_configured)}</dd>
            </dl>
          </Card>
          <Card title="Microsoft Graph" description="Target search and display-name resolution readiness.">
            <div className="readiness-header">
              <StatusBadge label={readiness.graph.ready ? "Ready" : "Not configured"} tone={readiness.graph.ready ? "success" : "warn"} />
              <StatusBadge label={graphCredentialLabel(readiness.graph.credential_source)} />
            </div>
            <p className="muted">{readiness.graph.message}</p>
            <p className="muted">Graph helps find Teams, channels and users. It does not prove that the bot can send there; validate each route with Send test.</p>
          </Card>
          <Card title="Runtime" description="Public URLs, limits and retention used by relay operations.">
            <dl className="definition-list">
              <dt>Application</dt>
              <dd>{readiness.app_name} {readiness.app_version}</dd>
              <dt>Public URL</dt>
              <dd>{readiness.runtime.app_public_base_url}</dd>
              <dt>Frontend URL</dt>
              <dd>{readiness.runtime.frontend_base_url}</dd>
              <dt>CORS origins</dt>
              <dd>{readiness.runtime.cors_origins.join(", ") || "-"}</dd>
              <dt>Payload limit</dt>
              <dd>{formatBytes(readiness.runtime.webhook_max_payload_bytes)}</dd>
              <dt>Log retention</dt>
              <dd>{readiness.runtime.log_retention_days} days</dd>
              <dt>Cleanup interval</dt>
              <dd>{readiness.runtime.log_cleanup_interval_minutes} minutes</dd>
              <dt>Secure session cookie</dt>
              <dd>{yesNo(readiness.runtime.session_secure_cookie)}</dd>
            </dl>
          </Card>
          <Card title="Operator checklist" description="Minimum path to a working relay route.">
            <ol className="check-list">
              <li>Add the bot to the target Teams chat or channel.</li>
              <li>Send or mention the bot once so Teams Rehook captures the conversation.</li>
              <li>Create a webhook route from that known conversation.</li>
              <li>Use Send test and confirm the message appears in Teams.</li>
              <li>Copy the relay URL into the source system and monitor Messages.</li>
            </ol>
          </Card>
        </div>
      ) : null}
    </>
  );
}

function yesNo(value: boolean): string {
  return value ? "Yes" : "No";
}

function graphCredentialLabel(source: string): string {
  if (source === "graph") return "Graph credentials";
  if (source === "bot") return "Bot fallback";
  return "Missing";
}

function formatBytes(value: number): string {
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  if (value >= 1024) return `${Math.round(value / 1024)} KB`;
  return `${value} B`;
}

function MessageLogsPage() {
  const [deliveryPage, setDeliveryPage] = useState<WebhookDeliveryEventPageOut | null>(null);
  const [routes, setRoutes] = useState<WebhookRouteOut[]>([]);
  const [statusFilter, setStatusFilter] = useState<DeliveryStatusFilter>("all");
  const [routeFilter, setRouteFilter] = useState("all");
  const [searchText, setSearchText] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selectedEventId, setSelectedEventId] = useState("");
  const [selectedEvent, setSelectedEvent] = useState<WebhookDeliveryEventDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [error, setError] = useState("");
  const pageSize = 25;
  const deliveryEvents = deliveryPage?.items ?? [];
  const total = deliveryPage?.total ?? 0;
  const totalPages = deliveryPage?.total_pages ?? 0;
  const firstVisible = total ? (page - 1) * pageSize + 1 : 0;
  const lastVisible = Math.min(page * pageSize, total);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setSearchQuery(searchText.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timeoutId);
  }, [searchText]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextDeliveryPage, nextRoutes] = await Promise.all([
        api.webhookDeliveryEvents({
          page,
          pageSize,
          status: statusFilter === "all" ? undefined : statusFilter,
          routeId: routeFilter === "all" ? undefined : routeFilter,
          query: searchQuery,
        }),
        api.webhookRoutes(),
      ]);
      setDeliveryPage(nextDeliveryPage);
      setRoutes(nextRoutes);
      setSelectedEventId((current) =>
        nextDeliveryPage.items.some((event) => event.id === current) ? current : nextDeliveryPage.items[0]?.id ?? "",
      );
    } catch (err) {
      setError(isApiError(err) ? err.message : "Logs could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [page, routeFilter, searchQuery, statusFilter]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selectedEventId) {
      setSelectedEvent(null);
      setDetailError("");
      return;
    }
    let mounted = true;
    setDetailLoading(true);
    setDetailError("");
    api
      .webhookDeliveryEvent(selectedEventId)
      .then((event) => {
        if (mounted) setSelectedEvent(event);
      })
      .catch((err) => {
        if (mounted) setDetailError(isApiError(err) ? err.message : "Delivery event details could not be loaded.");
      })
      .finally(() => {
        if (mounted) setDetailLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [selectedEventId]);

  return (
    <>
      <PageIntro
        eyebrow="Operations"
        title="Message logs"
        description={`Inspect webhook message events and Teams delivery outcomes. Logs are kept for ${deliveryPage?.retention_days ?? 7} days by default.`}
      />
      <Card
        title="Webhook message logs"
        description="Recent incoming webhook messages, manual tests and Teams delivery outcomes."
      >
        <div className="message-log-filters">
          <div className="segmented-control" aria-label="Filter webhook message logs by status">
            {DELIVERY_STATUS_FILTERS.map((filter) => (
              <button
                key={filter.value}
                type="button"
                className={classNames("segmented-control-button", statusFilter === filter.value && "is-active")}
                aria-pressed={statusFilter === filter.value}
                onClick={() => {
                  setStatusFilter(filter.value);
                  setPage(1);
                }}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <label className="compact-filter">
            <span>Route</span>
            <select
              value={routeFilter}
              onChange={(event) => {
                setRouteFilter(event.target.value);
                setPage(1);
              }}
            >
              <option value="all">All routes</option>
              {routes.map((route) => (
                <option key={route.id} value={route.id}>
                  {route.name}
                </option>
              ))}
            </select>
          </label>
          <label className="compact-filter compact-filter--search">
            <span>Search</span>
            <input
              type="search"
              value={searchText}
              placeholder="Route, source, message, error, payload"
              onChange={(event) => setSearchText(event.target.value)}
            />
          </label>
        </div>
        <div className="delivery-log-layout">
          <div className="logs-list-panel">
            <DataTable
              columns={["Status", "Time", "Route", "Message", "Mode", "Error"]}
              rows={deliveryEvents.map((event) => [
                <DeliveryEventStatusBadge status={event.status} />,
                formatDateTime(event.created_at),
                <div className="stacked-cell">
                  <strong>{event.route_name || "Deleted route"}</strong>
                  <span className="muted">{event.source_system || event.target_name || "No route metadata"}</span>
                </div>,
                <div className="stacked-cell">
                  <span>{event.title || "-"}</span>
                  <span className="muted">{event.payload_type || "-"}</span>
                </div>,
                <span className="muted">{deliverySummaryMode(event)}</span>,
                event.error ? <span className="form-error">{event.error}</span> : <span className="muted">-</span>,
              ])}
              emptyTitle="No webhook message logs"
              emptyBody="Send a route test or post to a relay URL. Delivered, failed and rejected attempts will appear here with payload and delivery details."
              loading={loading}
              loadingLabel="Loading webhook message logs..."
              error={error}
              onRetry={() => void refresh()}
              rowKey={(index) => deliveryEvents[index]?.id ?? index}
              rowClassName={(index) => (deliveryEvents[index]?.id === selectedEventId ? "is-selected" : null)}
              onRowClick={(index) => setSelectedEventId(deliveryEvents[index]?.id ?? "")}
            />
            {!loading && !error && totalPages > 1 ? (
              <div className="pagination-bar">
                <span>
                  {firstVisible}-{lastVisible} of {total}
                </span>
                <div className="row-actions">
                  <button className="secondary-button secondary-button--small button-with-icon" type="button" disabled={page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>
                    <ChevronLeft aria-hidden="true" className="button-icon" focusable="false" />
                    Previous
                  </button>
                  <button className="secondary-button secondary-button--small button-with-icon" type="button" disabled={page >= totalPages} onClick={() => setPage((current) => current + 1)}>
                    Next
                    <ChevronRight aria-hidden="true" className="button-icon" focusable="false" />
                  </button>
                </div>
              </div>
            ) : null}
          </div>
          {!loading && !error ? (
            detailLoading ? (
              <aside className="delivery-event-detail" role="status" aria-live="polite">
                <div className="spinner spinner--small" aria-hidden="true" />
                <p className="muted">Loading event details...</p>
              </aside>
            ) : detailError ? (
              <aside className="delivery-event-detail" role="alert">
                <p className="form-error">{detailError}</p>
              </aside>
            ) : selectedEvent ? (
              <DeliveryEventDetails event={selectedEvent} />
            ) : null
          ) : null}
        </div>
      </Card>
    </>
  );
}

function SystemLogsPage() {
  const { session, notify } = useAppContext();
  const [auditLogs, setAuditLogs] = useState<AuditEventOut[]>([]);
  const [systemLogs, setSystemLogs] = useState<SystemLogEventOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [cleanupBusy, setCleanupBusy] = useState(false);
  const [error, setError] = useState("");
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextAuditLogs, nextSystemLogs] = await Promise.all([
        api.adminLogs(csrfToken),
        api.adminSystemLogs(csrfToken),
      ]);
      setAuditLogs(nextAuditLogs);
      setSystemLogs(nextSystemLogs);
    } catch (err) {
      setError(isApiError(err) ? err.message : "System logs could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [csrfToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function cleanupLogs() {
    setCleanupBusy(true);
    try {
      const result = await api.cleanupLogs(csrfToken);
      notify({
        tone: "info",
        title: "Logs cleaned up",
        description: `${result.deleted} entries removed. Retention is ${result.retention_days} days.`,
      });
      await refresh();
    } catch (err) {
      notify({
        tone: "error",
        title: "Cleanup failed",
        description: isApiError(err) ? err.message : "Logs could not be cleaned up.",
      });
    } finally {
      setCleanupBusy(false);
    }
  }

  return (
    <>
      <PageIntro
        eyebrow="Administration"
        title="System logs"
        description="Review audit events and Teams bot activity separately from webhook message delivery."
        actions={
          <button className="secondary-button button-with-icon" type="button" disabled={cleanupBusy} onClick={() => void cleanupLogs()}>
            <Trash2 aria-hidden="true" className="button-icon" focusable="false" />
            {cleanupBusy ? "Cleaning..." : "Clean up"}
          </button>
        }
      />
      <Card title="Audit logs" description="Recent sign-ins, route changes and administration activity.">
        <DataTable
          columns={["Action", "Actor", "Metadata", "Time"]}
          rows={auditLogs.map((event) => [
            <strong>{event.action}</strong>,
            `${event.actor_type}${event.actor_id ? `:${event.actor_id.slice(0, 8)}` : ""}`,
            <span className="muted">{compactJson(event.metadata)}</span>,
            formatDateTime(event.created_at),
          ])}
          emptyTitle="No audit events"
          emptyBody="Log entries appear after sign-in or route administration changes."
          loading={loading}
          loadingLabel="Loading audit logs..."
          error={error}
          onRetry={() => void refresh()}
          rowKey={(index) => auditLogs[index]?.id ?? index}
        />
      </Card>
      <Card title="System events" description="Teams bot activities captured by the relay service.">
        <DataTable
          columns={["Activity", "Scope", "Conversation", "User", "Time"]}
          rows={systemLogs.map((event) => [
            <strong>{event.activity_type || "activity"}</strong>,
            <StatusBadge label={event.scope || "unknown"} tone={event.scope === "channel" ? "success" : "neutral"} />,
            <div className="stacked-cell">
              <span>{systemLogConversation(event)}</span>
              <span className="muted">{event.conversation_type || shortId(event.conversation_id)}</span>
            </div>,
            <div className="stacked-cell">
              <span>{event.user_name || "-"}</span>
              <span className="muted">{event.graph_user_id ? shortId(event.graph_user_id) : "-"}</span>
            </div>,
            formatDateTime(event.created_at),
          ])}
          emptyTitle="No system events"
          emptyBody="Bot activity events appear after Teams sends activities to the relay bot endpoint."
          loading={loading}
          loadingLabel="Loading system events..."
          error={error}
          onRetry={() => void refresh()}
          rowKey={(index) => systemLogs[index]?.id ?? index}
        />
      </Card>
    </>
  );
}

function systemLogConversation(event: SystemLogEventOut): string {
  if (event.team_name && event.channel_name) return `${event.team_name} / ${event.channel_name}`;
  return event.channel_name || event.team_name || shortId(event.conversation_id) || "-";
}

function InnerApp() {
  const { session } = useAppContext();
  if (session.status === "booting") return <LoadingScreen label="Loading workspace" />;
  if (session.status === "anonymous") return <LoginScreen />;
  return <AppShell />;
}

export default function App() {
  if (window.location.pathname === "/copy-webhook") return <WebhookCopyPage />;

  return (
    <AppProvider>
      <InnerApp />
      <ToastViewport />
    </AppProvider>
  );
}
