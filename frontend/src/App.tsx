import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ClipboardCopy, FileClock, MessageSquareText, Pencil, Plus, RefreshCw, Send, Trash2, type LucideIcon } from "lucide-react";

import { api } from "./api";
import { AppProvider, useAppContext } from "./app-context";
import { Card, DataTable, EmptyState, Field, LoadingScreen, Modal, PageIntro, StatusBadge, ToastViewport } from "./components";
import { isApiError } from "./errors";
import { ThemeToggle } from "./theme-toggle";
import type {
  AuditEventOut,
  BotConversationReferenceOut,
  GraphTargetKind,
  UserOut,
  WebhookDeliveryEventOut,
  WebhookDeliveryStatus,
  WebhookRouteOut,
} from "./types";
import { classNames, compactJson, formatDateTime, formatRelativeTime } from "./utils";

type RouteName = "dashboard" | "webhooks" | "users" | "settings" | "logs";
type DeliveryStatusFilter = "all" | WebhookDeliveryStatus;

const NAV: Array<{ route: RouteName; label: string; path: string; icon: string }> = [
  { route: "dashboard", label: "Dashboard", path: "/dashboard", icon: "D" },
  { route: "webhooks", label: "Webhooks", path: "/webhooks", icon: "W" },
  { route: "users", label: "Users", path: "/users", icon: "U" },
  { route: "settings", label: "Settings", path: "/settings", icon: "S" },
  { route: "logs", label: "Logs", path: "/logs", icon: "L" },
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

function routeFromPath(pathname: string): RouteName {
  if (pathname === "/" || pathname === "/dashboard") return "dashboard";
  if (pathname === "/webhooks") return "webhooks";
  if (pathname === "/users") return "users";
  if (pathname === "/settings") return "settings";
  if (pathname === "/logs") return "logs";
  return "dashboard";
}

function LoginScreen() {
  const { login } = useAppContext();
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("change-me-admin-password");
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
      setError(err instanceof Error ? err.message : "Sign in failed");
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
          <p className="eyebrow">Teams Relay Workspace</p>
          <h1>Teams Messenger</h1>
          <p className="lede">Manage stable webhook routes that forward operational messages into Microsoft Teams conversations.</p>
        </div>
        <form className="compact-form" onSubmit={submit}>
          <Field label="Email">
            <input value={email} autoComplete="email" onChange={(event) => setEmail(event.target.value)} />
          </Field>
          <Field label="Password">
            <input
              value={password}
              type="password"
              autoComplete="current-password"
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
            <strong>Teams Messenger</strong>
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
        {route === "logs" ? <LogsPage /> : null}
      </main>
    </div>
  );
}

function DashboardPage() {
  const [routes, setRoutes] = useState<WebhookRouteOut[]>([]);
  const [references, setReferences] = useState<BotConversationReferenceOut[]>([]);

  useEffect(() => {
    void Promise.all([api.webhookRoutes(), api.botConversationReferences()]).then(([nextRoutes, nextReferences]) => {
      setRoutes(nextRoutes);
      setReferences(nextReferences);
    });
  }, []);

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

  return (
    <>
      <PageIntro
        eyebrow="Overview"
        title="Teams relay dashboard"
        description="Monitor relay routes, Teams conversations and recent delivery health from one operational view."
      />
      <div className="metric-grid">
        <Card className="metric-card">
          <span>Webhook routes</span>
          <strong>{counts.routes}</strong>
        </Card>
        <Card className="metric-card">
          <span>Active routes</span>
          <strong>{counts.active}</strong>
        </Card>
        <Card className="metric-card">
          <span>Needs attention</span>
          <strong>{counts.attention}</strong>
        </Card>
        <Card className="metric-card">
          <span>Known conversations</span>
          <strong>{counts.conversations}</strong>
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
          emptyBody="Create a webhook route to start relaying messages into Teams."
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
  const [regeneratedUrl, setRegeneratedUrl] = useState<{ routeName: string; url: string } | null>(null);
  const [testResult, setTestResult] = useState<WebhookRouteOut | null>(null);
  const [viewingBotReferences, setViewingBotReferences] = useState(false);
  const [botDefaultServiceUrl, setBotDefaultServiceUrl] = useState("");
  const [testingId, setTestingId] = useState("");
  const [regeneratingId, setRegeneratingId] = useState("");
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  async function refresh() {
    setRoutes(await api.webhookRoutes());
  }

  useEffect(() => {
    void refresh();
  }, [csrfToken]);

  useEffect(() => {
    void api.webhookRouteDefaults().then((defaults) => setBotDefaultServiceUrl(defaults.bot_default_service_url));
  }, []);

  async function deleteRoute(route: WebhookRouteOut) {
    await api.deleteWebhookRoute(csrfToken, route.id);
    notify({ tone: "info", title: "Webhook route deleted", description: route.name });
    await refresh();
  }

  async function testRoute(route: WebhookRouteOut) {
    setTestingId(route.id);
    try {
      await api.testWebhookRoute(csrfToken, route.id, {
        title: `Relay test: ${route.name}`,
        text: "This test message was sent from the Teams Webhook Relay.",
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

  return (
    <>
      <PageIntro
        eyebrow="Teams relay"
        title="Webhook routes"
        description="Map stable relay webhook URLs to Teams bot targets and validate delivery with deterministic test sends."
        actions={
          <div className="row-actions">
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
          columns={["Route", "Source", "Target", "Active", "Last delivery", "Relay URL", ""]}
          rows={routes.map((route) => [
            <div className="stacked-cell">
              <strong>{route.name}</strong>
              {route.bot_target_source === "bot_command" ? <StatusBadge label="Bot registered" tone="success" /> : null}
              {route.bot_target_source === "conversation_reference" ? <StatusBadge label="Conversation selected" tone="success" /> : null}
            </div>,
            <span className="muted">{route.source_system || "-"}</span>,
            <div className="stacked-cell">
              <strong>{route.target_name}</strong>
              <span className="muted">Bot conversation</span>
              <GraphTargetSummary
                kind={route.graph_target_kind}
                targetName={route.target_name}
                teamName={route.graph_team_name}
                teamId={route.graph_team_id}
                channelId={route.graph_channel_id}
              />
            </div>,
            route.is_active ? <StatusBadge label="Active" tone="success" /> : <StatusBadge label="Disabled" tone="warn" />,
            <DeliveryStatusBadge route={route} />,
            route.webhook_url ? (
              <IconButton label="Copy relay URL" icon={ClipboardCopy} onClick={() => void copyText(route.webhook_url ?? "", route.name)} />
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
                label={regeneratingId === route.id ? "Regenerating relay URL" : "Regenerate relay URL"}
                icon={RefreshCw}
                disabled={regeneratingId === route.id}
                spinning={regeneratingId === route.id}
                onClick={() => setConfirmingRegeneration(route)}
              />
              <IconButton label="Delete route" icon={Trash2} tone="danger" onClick={() => void deleteRoute(route)} />
            </div>,
          ])}
          emptyTitle="No webhook routes"
          emptyBody="Create a route to receive webhook requests and forward them through the Teams bot adapter."
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
      title="Known bot conversations"
      description="Recently captured Teams conversations from inbound bot activities."
      panelClassName="delivery-logs-modal"
      onClose={onClose}
    >
      {loading ? <p className="muted">Loading bot conversations...</p> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!loading && !error && references.length === 0 ? (
        <EmptyState title="No bot conversations captured" body="Send a message to the bot or install it in a Teams channel." />
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
  const [showAdvancedTarget, setShowAdvancedTarget] = useState(Boolean(route));
  const [createdWebhookUrl, setCreatedWebhookUrl] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  useEffect(() => {
    let mounted = true;
    setReferencesLoading(true);
    setReferencesError("");
    api
      .botConversationReferences()
      .then((rows) => {
        if (mounted) setReferences(rows);
      })
      .catch((err) => {
        if (mounted) setReferencesError(isApiError(err) ? err.message : "Bot conversations could not be loaded.");
      })
      .finally(() => {
        if (mounted) setReferencesLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

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
      description="Create stable relay URLs from conversations the Teams bot has already seen."
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
            <strong>Teams conversation</strong>
            {botConversationId ? <StatusBadge label="Conversation selected" tone="success" /> : null}
          </div>
          {targetName ? (
            <GraphTargetSummary
              kind={graphTargetKind}
              targetName={targetName}
              teamName={graphTeamName}
              teamId={graphTeamId}
              channelId={graphChannelId}
            />
          ) : null}
          {referencesLoading ? <p className="muted">Loading known conversations...</p> : null}
          {referencesError ? <p className="form-error">{referencesError}</p> : null}
          {!referencesLoading && !referencesError && references.length === 0 ? (
            <p className="muted">No bot conversations captured yet. Send the bot a message or install it in a channel.</p>
          ) : null}
          {references.length ? (
            <div className="search-result-list">
              {references.map((reference) => {
                const selected = reference.conversation_id === botConversationId;
                return (
                  <button
                    key={reference.id}
                    type="button"
                    className={selected ? "is-selected" : undefined}
                    onClick={() => applyReference(reference)}
                  >
                    <strong>{referenceTitle(reference)}</strong>
                    <span>
                      {reference.scope} · {formatRelativeTime(reference.last_seen_at)}
                    </span>
                  </button>
                );
              })}
            </div>
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
              <strong>Advanced target fields</strong>
              <StatusBadge label="Manual fallback" tone="warn" />
            </div>
            <Field label="Teams target name">
              <input value={targetName} required maxLength={200} onChange={(event) => setTargetName(event.target.value)} />
            </Field>
            <Field label="Bot service URL">
              <input
                value={botServiceUrl}
                required
                onChange={(event) => {
                  setBotServiceUrl(event.target.value);
                  setBotTargetSource("manual");
                }}
              />
            </Field>
            <Field label="Bot conversation ID">
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

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError("");
    api
      .webhookRouteDeliveries(route.id, statusFilter === "all" ? undefined : statusFilter)
      .then((rows) => {
        if (mounted) {
          setEvents(rows);
          setSelectedEventId(rows[0]?.id ?? "");
        }
      })
      .catch((err) => {
        if (mounted) setError(isApiError(err) ? err.message : "Delivery logs could not be loaded.");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [route.id, statusFilter]);

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
      {loading ? <p className="muted">Loading delivery logs...</p> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!loading && !error ? (
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
            rowKey={(index) => events[index]?.id ?? index}
            rowClassName={(index) => (events[index]?.id === selectedEvent?.id ? "is-selected" : null)}
            onRowClick={(index) => setSelectedEventId(events[index]?.id ?? "")}
          />
          {selectedEvent ? <DeliveryEventDetails event={selectedEvent} /> : null}
        </div>
      ) : null}
    </Modal>
  );
}

function DeliveryEventStatusBadge({ status }: { status: WebhookDeliveryEventOut["status"] }) {
  if (status === "delivered") return <StatusBadge label="Delivered" tone="success" />;
  if (status === "failed") return <StatusBadge label="Failed" tone="danger" />;
  return <StatusBadge label="Rejected" tone="warn" />;
}

function DeliveryEventDetails({ event }: { event: WebhookDeliveryEventOut }) {
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

function UsersPage() {
  const { session } = useAppContext();
  const [users, setUsers] = useState<UserOut[]>([]);
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  useEffect(() => {
    void api.adminUsers(csrfToken).then(setUsers);
  }, [csrfToken]);

  return (
    <>
      <PageIntro
        eyebrow="Admin"
        title="Users"
        description="Manage administrator access for Teams Messenger operations."
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
          rowKey={(index) => users[index]?.id ?? index}
        />
      </Card>
    </>
  );
}

function SettingsPage() {
  return (
    <>
      <PageIntro
        eyebrow="Configuration"
        title="Settings"
        description="Review the relay runtime, delivery mode and Teams integration defaults."
      />
      <div className="settings-grid">
        <Card title="Application" description="General app metadata and runtime stack.">
          <dl className="definition-list">
            <dt>Application</dt>
            <dd>Teams Messenger</dd>
            <dt>Stack</dt>
            <dd>FastAPI, Postgres, React, Vite</dd>
            <dt>Theme</dt>
            <dd>Light, dark and system preference</dd>
          </dl>
        </Card>
        <Card title="Relay operations" description="Core capabilities available in this workspace.">
          <ul className="check-list">
            <li>Create stable relay URLs for known Teams bot conversations.</li>
            <li>Regenerate route URLs when a source system credential needs rotation.</li>
            <li>Inspect delivery logs, normalized payloads and bot activity responses.</li>
          </ul>
        </Card>
      </div>
    </>
  );
}

function LogsPage() {
  const { session } = useAppContext();
  const [logs, setLogs] = useState<AuditEventOut[]>([]);
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  useEffect(() => {
    void api.adminLogs(csrfToken).then(setLogs);
  }, [csrfToken]);

  return (
    <>
      <PageIntro
        eyebrow="Audit"
        title="Logs"
        description="Track sign-ins, route changes and relay administration activity."
      />
      <Card>
        <DataTable
          columns={["Action", "Actor", "Metadata", "Time"]}
          rows={logs.map((event) => [
            <strong>{event.action}</strong>,
            `${event.actor_type}${event.actor_id ? `:${event.actor_id.slice(0, 8)}` : ""}`,
            <span className="muted">{compactJson(event.metadata)}</span>,
            formatDateTime(event.created_at),
          ])}
          emptyTitle="No audit events"
          emptyBody="Log entries appear after sign-in or route administration changes."
          rowKey={(index) => logs[index]?.id ?? index}
        />
      </Card>
    </>
  );
}

function InnerApp() {
  const { session } = useAppContext();
  if (session.status === "booting") return <LoadingScreen label="Loading workspace" />;
  if (session.status === "anonymous") return <LoginScreen />;
  return <AppShell />;
}

export default function App() {
  return (
    <AppProvider>
      <InnerApp />
      <ToastViewport />
    </AppProvider>
  );
}
