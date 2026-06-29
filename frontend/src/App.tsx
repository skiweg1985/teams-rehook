import { useCallback, useEffect, useId, useMemo, useRef, useState, type FocusEvent, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  Bot,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardCopy,
  Eye,
  EyeOff,
  FileClock,
  Info,
  MessageSquareText,
  MessagesSquare,
  MoreHorizontal,
  Pencil,
  Plus,
  Power,
  PowerOff,
  Radio,
  RefreshCw,
  RotateCcwKey,
  Search,
  Send,
  ShieldAlert,
  Trash2,
  Wrench,
  Webhook,
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
  ClientIpAccessMode,
  DeliveryAuthRefreshOut,
  DeliveryBackend,
  EventLogEntryOut,
  EventLogEntryPageOut,
  GraphTargetKind,
  OAuthDiagnosticsOut,
  SettingItemOut,
  SystemLogEventOut,
  TeamsTargetSearchResult,
  UserOut,
  WebhookAbuseBucketOut,
  WebhookDeliveryEventDetailOut,
  WebhookDeliveryEventOut,
  WebhookDeliveryEventPageOut,
  WebhookDeliveryEventSummaryOut,
  WebhookDeliveryStatus,
  WebhookRouteOut,
} from "./types";
import { classNames, compactJson, formatDateTime, formatRelativeTime } from "./utils";

type RouteName = "dashboard" | "status" | "webhooks" | "payload-generator" | "delivery" | "users" | "settings" | "logs" | "system-logs";
type DeliveryStatusFilter = "all" | WebhookDeliveryStatus;
type PayloadGeneratorMode = "text" | "adaptive";
type PayloadAccent = "neutral" | "success" | "warning" | "critical";
type PayloadImageSize = "Auto" | "Stretch";
type PayloadTitleSize = "Default" | "Medium" | "Large";
type PayloadTitleWeight = "Default" | "Bolder";
type SystemLogTab = "timeline" | "security" | "audit" | "bot";

type PayloadFact = {
  id: string;
  name: string;
  value: string;
};

type PayloadAction = {
  id: string;
  title: string;
  url: string;
};

const NAV: Array<{ route: RouteName; label: string; path: string; icon: string }> = [
  { route: "dashboard", label: "Dashboard", path: "/dashboard", icon: "D" },
  { route: "status", label: "Status", path: "/status", icon: "S" },
  { route: "webhooks", label: "Webhooks", path: "/webhooks", icon: "W" },
  { route: "payload-generator", label: "Payload Generator", path: "/payload-generator", icon: "P" },
  { route: "delivery", label: "Delivery", path: "/delivery", icon: "D" },
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
  { value: "pending", label: "Pending" },
];

const PAYLOAD_ACCENTS: Array<{ value: PayloadAccent; label: string }> = [
  { value: "neutral", label: "Neutral" },
  { value: "success", label: "Success" },
  { value: "warning", label: "Warning" },
  { value: "critical", label: "Critical" },
];

const PAYLOAD_TITLE_SIZES: Array<{ value: PayloadTitleSize; label: string }> = [
  { value: "Default", label: "Default" },
  { value: "Medium", label: "Medium" },
  { value: "Large", label: "Large" },
];

const PAYLOAD_TITLE_WEIGHTS: Array<{ value: PayloadTitleWeight; label: string }> = [
  { value: "Default", label: "Default" },
  { value: "Bolder", label: "Bolder" },
];

const PAYLOAD_IMAGE_SIZES: Array<{ value: PayloadImageSize; label: string }> = [
  { value: "Auto", label: "Auto" },
  { value: "Stretch", label: "Stretch" },
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

type RowActionItem = {
  label: string;
  icon: LucideIcon;
  onClick: () => void;
  disabled?: boolean;
  spinning?: boolean;
  tone?: "default" | "danger";
  separated?: boolean;
};

function RowActionMenu({ label, items }: { label: string; items: RowActionItem[] }) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<{ top: number; right: number }>({ top: 0, right: 0 });
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  function openMenu() {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) setCoords({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
    setOpen(true);
  }

  useEffect(() => {
    if (!open) return;
    function handlePointer(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false);
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    function handleReposition() {
      setOpen(false);
    }
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("keydown", handleKey);
    window.addEventListener("resize", handleReposition);
    window.addEventListener("scroll", handleReposition, true);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("keydown", handleKey);
      window.removeEventListener("resize", handleReposition);
      window.removeEventListener("scroll", handleReposition, true);
    };
  }, [open]);

  return (
    <div className="row-action-menu" ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        className="icon-button"
        aria-label={label}
        title={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => (open ? setOpen(false) : openMenu())}
      >
        <MoreHorizontal aria-hidden="true" className="button-icon" focusable="false" />
      </button>
      {open ? (
        <div className="row-action-menu-popover" role="menu" style={{ top: coords.top, right: coords.right }}>
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              className={classNames(
                "row-action-menu-item",
                item.tone === "danger" && "row-action-menu-item--danger",
                item.separated && "row-action-menu-item--separated",
              )}
              disabled={item.disabled}
              onClick={() => {
                setOpen(false);
                item.onClick();
              }}
            >
              <item.icon
                aria-hidden="true"
                className={classNames("button-icon", item.spinning && "button-icon--spin")}
                focusable="false"
              />
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
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
  if (pathname === "/status") return "status";
  if (pathname === "/webhooks") return "webhooks";
  if (pathname === "/payload-generator") return "payload-generator";
  if (pathname === "/delivery") return "delivery";
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
              placeholder="admin@example.local"
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

function FirstAdminSetupScreen() {
  const { createFirstAdmin } = useAppContext();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await createFirstAdmin(email, displayName, password);
      window.history.replaceState(null, "", "/dashboard");
    } catch (err) {
      setError(isApiError(err) ? err.message : err instanceof Error ? err.message : "Setup failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-screen">
      <section className="login-panel setup-panel">
        <div className="login-panel-header">
          <div className="app-mark">T</div>
          <ThemeToggle />
        </div>
        <div>
          <p className="eyebrow">First-run setup</p>
          <h1>Create the first admin</h1>
          <p className="lede">This account controls Teams Rehook administration for the default workspace.</p>
        </div>
        <form className="compact-form" onSubmit={submit}>
          <Field label="Email">
            <input
              value={email}
              autoComplete="email"
              placeholder="admin@example.local"
              required
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>
          <Field label="Display name">
            <input
              value={displayName}
              autoComplete="name"
              placeholder="Operations Admin"
              required
              maxLength={255}
              onChange={(event) => setDisplayName(event.target.value)}
            />
          </Field>
          <Field label="Password">
            <input
              value={password}
              type="password"
              autoComplete="new-password"
              placeholder="Set a password"
              required
              minLength={8}
              maxLength={200}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          <Field label="Confirm password">
            <input
              value={confirmPassword}
              type="password"
              autoComplete="new-password"
              placeholder="Repeat the password"
              required
              minLength={8}
              maxLength={200}
              onChange={(event) => setConfirmPassword(event.target.value)}
            />
          </Field>
          {error ? <p className="form-error">{error}</p> : null}
          <button className="primary-button" type="submit" disabled={busy}>
            {busy ? "Creating admin..." : "Create admin"}
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
  const [copied, setCopied] = useState(false);
  const copiedTimer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => () => clearTimeout(copiedTimer.current), []);

  async function copyWebhookUrl() {
    if (!webhookUrl) return;
    try {
      await navigator.clipboard.writeText(webhookUrl);
      setStatus("");
      setCopied(true);
      clearTimeout(copiedTimer.current);
      copiedTimer.current = setTimeout(() => setCopied(false), 2000);
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
          className={`primary-button button-with-icon copy-url-button${copied ? " is-copied" : ""}`}
          type="button"
          disabled={!webhookUrl}
          onClick={() => void copyWebhookUrl()}
        >
          <span className="copy-url-button-label" key={copied ? "copied" : "idle"}>
            {copied ? (
              <>
                <Check aria-hidden="true" className="button-icon" focusable="false" />
                Copied
              </>
            ) : (
              <>
                <ClipboardCopy aria-hidden="true" className="button-icon" focusable="false" />
                Copy URL
              </>
            )}
          </span>
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
        {route === "status" ? <StatusPage /> : null}
        {route === "webhooks" ? <WebhooksPage /> : null}
        {route === "payload-generator" ? <PayloadGeneratorPage /> : null}
        {route === "delivery" ? <DeliveryMethodsPage /> : null}
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
          <div className="metric-card__head">
            <span className="metric-icon" aria-hidden="true">
              <Webhook size={18} strokeWidth={2} />
            </span>
            <span className="metric-label">Webhook routes</span>
          </div>
          <strong className="metric-value">{metricValue(counts.routes)}</strong>
          <span className="metric-context">All configured relay routes</span>
        </Card>
        <Card className="metric-card">
          <div className="metric-card__head">
            <span className="metric-icon" aria-hidden="true">
              <Radio size={18} strokeWidth={2} />
            </span>
            <span className="metric-label">Active routes</span>
          </div>
          <strong className="metric-value">{metricValue(counts.active)}</strong>
          <span className="metric-context">Currently accepting requests</span>
        </Card>
        <Card className={classNames("metric-card", !loading && !error && counts.attention > 0 ? "metric-card--alert" : null)}>
          <div className="metric-card__head">
            <span className="metric-icon" aria-hidden="true">
              <AlertTriangle size={18} strokeWidth={2} />
            </span>
            <span className="metric-label">Needs attention</span>
          </div>
          <strong className="metric-value">{metricValue(counts.attention)}</strong>
          <span className="metric-context">Failed or rejected deliveries</span>
        </Card>
        <Card className="metric-card">
          <div className="metric-card__head">
            <span className="metric-icon" aria-hidden="true">
              <MessagesSquare size={18} strokeWidth={2} />
            </span>
            <span className="metric-label">Known conversations</span>
          </div>
          <strong className="metric-value">{metricValue(counts.conversations)}</strong>
          <span className="metric-context">Captured Teams targets</span>
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
                <span>Send a test message before sharing the relay URL.</span>
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

function newPayloadFact(name = "", value = ""): PayloadFact {
  return { id: `${Date.now()}-${Math.random().toString(16).slice(2)}`, name, value };
}

function newPayloadAction(title = "", url = ""): PayloadAction {
  return { id: `${Date.now()}-${Math.random().toString(16).slice(2)}`, title, url };
}

function defaultPayloadFacts(): PayloadFact[] {
  return [];
}

function defaultPayloadActions(): PayloadAction[] {
  return [];
}

function compactPayloadFacts(facts: PayloadFact[]): Array<{ name: string; value: string }> {
  return facts
    .map((fact) => ({ name: fact.name.trim(), value: fact.value.trim() }))
    .filter((fact) => fact.name || fact.value);
}

function compactPayloadActions(actions: PayloadAction[]): Array<{ title: string; url: string }> {
  return actions
    .map((action) => ({ title: action.title.trim(), url: action.url.trim() }))
    .filter((action) => action.title && action.url);
}

function adaptiveCardColor(accent: PayloadAccent): string {
  if (accent === "success") return "Good";
  if (accent === "warning") return "Warning";
  if (accent === "critical") return "Attention";
  return "Default";
}

function buildGeneratedPayload({
  mode,
  title,
  message,
  accent,
  facts,
  titleSize,
  titleWeight,
  imageUrl,
  imageAlt,
  imageSize,
  fullWidth,
  actions,
}: {
  mode: PayloadGeneratorMode;
  title: string;
  message: string;
  accent: PayloadAccent;
  facts: PayloadFact[];
  titleSize: PayloadTitleSize;
  titleWeight: PayloadTitleWeight;
  imageUrl: string;
  imageAlt: string;
  imageSize: PayloadImageSize;
  fullWidth: boolean;
  actions: PayloadAction[];
}): Record<string, unknown> {
  const cleanTitle = title.trim() || "Message title";
  const cleanMessage = message.trim() || "Write the message content here.";
  const cleanFacts = compactPayloadFacts(facts);
  const cleanImageUrl = imageUrl.trim();
  const cleanImageAlt = imageAlt.trim();
  const cleanActions = compactPayloadActions(actions);

  if (mode === "text") {
    return {
      title: cleanTitle,
      message: cleanMessage,
      ...(cleanFacts.length ? { facts: cleanFacts } : {}),
    };
  }

  const adaptiveFacts = cleanFacts.map((fact) => ({ title: fact.name || "Detail", value: fact.value || "-" }));
  const cardBody: Array<Record<string, unknown>> = [
    {
      type: "TextBlock",
      text: cleanTitle,
      weight: titleWeight,
      size: titleSize,
      color: adaptiveCardColor(accent),
      wrap: true,
    },
    {
      type: "TextBlock",
      text: cleanMessage,
      wrap: true,
      spacing: "Small",
    },
  ];
  if (cleanImageUrl) {
    cardBody.push({
      type: "Image",
      url: cleanImageUrl,
      size: imageSize,
      ...(cleanImageAlt ? { altText: cleanImageAlt } : {}),
    });
  }
  if (adaptiveFacts.length) {
    cardBody.push({
      type: "FactSet",
      facts: adaptiveFacts,
    });
  }

  const cardContent: Record<string, unknown> = {
    $schema: "http://adaptivecards.io/schemas/adaptive-card.json",
    type: "AdaptiveCard",
    version: "1.4",
    body: cardBody,
    ...(cleanActions.length
      ? {
          actions: cleanActions.map((action) => ({
            type: "Action.OpenUrl",
            title: action.title,
            url: action.url,
          })),
        }
      : {}),
    ...(fullWidth ? { msteams: { width: "Full" } } : {}),
  };

  return {
    type: "message",
    attachments: [
      {
        contentType: "application/vnd.microsoft.card.adaptive",
        content: cardContent,
      },
    ],
  };
}

function PayloadGeneratorPage() {
  const { notify } = useAppContext();
  const messageRef = useRef<HTMLTextAreaElement>(null);
  const [mode, setMode] = useState<PayloadGeneratorMode>("text");
  const [title, setTitle] = useState("Message title");
  const [message, setMessage] = useState("Write the message content here.");
  const [accent, setAccent] = useState<PayloadAccent>("neutral");
  const [facts, setFacts] = useState<PayloadFact[]>(() => defaultPayloadFacts());
  const [titleSize, setTitleSize] = useState<PayloadTitleSize>("Medium");
  const [titleWeight, setTitleWeight] = useState<PayloadTitleWeight>("Bolder");
  const [imageUrl, setImageUrl] = useState("");
  const [imageAlt, setImageAlt] = useState("");
  const [imageSize, setImageSize] = useState<PayloadImageSize>("Stretch");
  const [fullWidth, setFullWidth] = useState(true);
  const [actions, setActions] = useState<PayloadAction[]>(() => defaultPayloadActions());

  const payload = useMemo(
    () =>
      buildGeneratedPayload({
        mode,
        title,
        message,
        accent,
        facts,
        titleSize,
        titleWeight,
        imageUrl,
        imageAlt,
        imageSize,
        fullWidth,
        actions,
      }),
    [accent, actions, facts, fullWidth, imageAlt, imageSize, imageUrl, message, mode, title, titleSize, titleWeight],
  );
  const payloadJson = useMemo(() => JSON.stringify(payload, null, 2), [payload]);
  const previewFacts = useMemo(() => compactPayloadFacts(facts), [facts]);
  const previewActions = useMemo(() => compactPayloadActions(actions), [actions]);

  function resetGenerator() {
    setMode("text");
    setTitle("Message title");
    setMessage("Write the message content here.");
    setAccent("neutral");
    setFacts(defaultPayloadFacts());
    setTitleSize("Medium");
    setTitleWeight("Bolder");
    setImageUrl("");
    setImageAlt("");
    setImageSize("Stretch");
    setFullWidth(true);
    setActions(defaultPayloadActions());
  }

  function updateFact(id: string, patch: Partial<Pick<PayloadFact, "name" | "value">>) {
    setFacts((current) => current.map((fact) => (fact.id === id ? { ...fact, ...patch } : fact)));
  }

  function updateAction(id: string, patch: Partial<Pick<PayloadAction, "title" | "url">>) {
    setActions((current) => current.map((action) => (action.id === id ? { ...action, ...patch } : action)));
  }

  function applyMarkdown(kind: "bold" | "italic" | "list" | "link") {
    const textarea = messageRef.current;
    const start = textarea?.selectionStart ?? message.length;
    const end = textarea?.selectionEnd ?? message.length;
    const selected = message.slice(start, end);
    let insert = "";
    let selectionOffsetStart = 0;
    let selectionOffsetEnd = 0;

    if (kind === "bold") {
      const inner = selected || "bold text";
      insert = `**${inner}**`;
      selectionOffsetStart = 2;
      selectionOffsetEnd = 2 + inner.length;
    } else if (kind === "italic") {
      const inner = selected || "italic text";
      insert = `*${inner}*`;
      selectionOffsetStart = 1;
      selectionOffsetEnd = 1 + inner.length;
    } else if (kind === "link") {
      const inner = selected || "link label";
      insert = `[${inner}](https://example.com)`;
      selectionOffsetStart = 1;
      selectionOffsetEnd = 1 + inner.length;
    } else {
      const inner = selected || "First item\nSecond item";
      insert = inner
        .split("\n")
        .map((line) => (line.trim().startsWith("- ") ? line : `- ${line}`))
        .join("\n");
      selectionOffsetStart = 0;
      selectionOffsetEnd = insert.length;
    }

    const nextMessage = `${message.slice(0, start)}${insert}${message.slice(end)}`;
    setMessage(nextMessage);
    window.requestAnimationFrame(() => {
      messageRef.current?.focus();
      messageRef.current?.setSelectionRange(start + selectionOffsetStart, start + selectionOffsetEnd);
    });
  }

  async function copyPayload() {
    try {
      await navigator.clipboard.writeText(payloadJson);
      notify({ tone: "success", title: "Payload copied", description: mode === "adaptive" ? "Adaptive Card JSON" : "Text JSON" });
    } catch {
      notify({ tone: "error", title: "Copy failed", description: "The payload could not be copied automatically." });
    }
  }

  return (
    <>
      <PageIntro
        eyebrow="Webhook helper"
        title="Payload Generator"
        description="Build JSON payloads for Teams Rehook webhook routes and preview the Teams message shape before copying it into an external system."
        actions={
          <div className="row-actions">
            <button className="secondary-button button-with-icon" type="button" onClick={resetGenerator}>
              <RotateCcwKey aria-hidden="true" className="button-icon" focusable="false" />
              Reset
            </button>
            <button className="primary-button button-with-icon" type="button" onClick={() => void copyPayload()}>
              <ClipboardCopy aria-hidden="true" className="button-icon" focusable="false" />
              Copy JSON
            </button>
          </div>
        }
      />
      <div className="payload-generator-layout">
        <Card title="Payload details" description="Choose a payload type, then fill in the message fields used by the webhook relay.">
          <div className="payload-builder-form">
            <div className="payload-mode-row">
              <span>Payload type</span>
              <div className="segmented-control" role="group" aria-label="Payload type">
                <button
                  className={classNames("segmented-control-button", mode === "text" && "is-active")}
                  type="button"
                  onClick={() => setMode("text")}
                >
                  Text
                </button>
                <button
                  className={classNames("segmented-control-button", mode === "adaptive" && "is-active")}
                  type="button"
                  onClick={() => setMode("adaptive")}
                >
                  Adaptive Card
                </button>
              </div>
            </div>
            <Field label="Title">
              <input value={title} placeholder="Message title" onChange={(event) => setTitle(event.target.value)} />
            </Field>
            <Field label="Message">
              <textarea
                ref={messageRef}
                value={message}
                placeholder="Write the message content here."
                rows={5}
                onChange={(event) => setMessage(event.target.value)}
              />
            </Field>
            <div className="payload-options-section">
              <div className="payload-section-header">
                <strong>Text formatting</strong>
                <span>Teams Adaptive Cards support a practical subset of Markdown.</span>
              </div>
              <div className="payload-format-toolbar" aria-label="Message formatting helpers">
                <button className="secondary-button secondary-button--small" type="button" onClick={() => applyMarkdown("bold")}>
                  B
                </button>
                <button className="secondary-button secondary-button--small" type="button" onClick={() => applyMarkdown("italic")}>
                  I
                </button>
                <button className="secondary-button secondary-button--small" type="button" onClick={() => applyMarkdown("list")}>
                  List
                </button>
                <button className="secondary-button secondary-button--small" type="button" onClick={() => applyMarkdown("link")}>
                  Link
                </button>
              </div>
            </div>
            {mode === "adaptive" ? (
              <>
                <div className="payload-options-section">
                  <div className="payload-section-header">
                    <strong>Teams display</strong>
                    <span>Display options that are included in the Adaptive Card content.</span>
                  </div>
                  <label className="checkbox-field">
                    <input type="checkbox" checked={fullWidth} onChange={(event) => setFullWidth(event.target.checked)} />
                    Full-width card
                  </label>
                  <Field label="Card accent" hint="Visual only">
                    <select value={accent} onChange={(event) => setAccent(event.target.value as PayloadAccent)}>
                      {PAYLOAD_ACCENTS.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <div className="payload-field-grid">
                    <Field label="Title size">
                      <select value={titleSize} onChange={(event) => setTitleSize(event.target.value as PayloadTitleSize)}>
                        {PAYLOAD_TITLE_SIZES.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Title weight">
                      <select value={titleWeight} onChange={(event) => setTitleWeight(event.target.value as PayloadTitleWeight)}>
                        {PAYLOAD_TITLE_WEIGHTS.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </Field>
                  </div>
                </div>
                <div className="payload-options-section">
                  <div className="payload-section-header">
                    <strong>Image</strong>
                    <span>Optional Adaptive Card image rendered from a public or external-system URL.</span>
                  </div>
                  <Field label="Image URL" hint="Optional">
                    <input value={imageUrl} placeholder="https://example.com/image.png" onChange={(event) => setImageUrl(event.target.value)} />
                  </Field>
                  <div className="payload-field-grid">
                    <Field label="Alt text" hint="Optional">
                      <input value={imageAlt} placeholder="Message image" onChange={(event) => setImageAlt(event.target.value)} />
                    </Field>
                    <Field label="Image size">
                      <select value={imageSize} onChange={(event) => setImageSize(event.target.value as PayloadImageSize)}>
                        {PAYLOAD_IMAGE_SIZES.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </Field>
                  </div>
                </div>
              </>
            ) : null}
            <div className="payload-facts-section">
              <div className="payload-facts-header">
                <div>
                  <strong>Details</strong>
                  <span>Optional name/value details such as Status, Owner, Customer, Ticket or Due date.</span>
                </div>
                <button
                  className="secondary-button secondary-button--small button-with-icon"
                  type="button"
                  onClick={() => setFacts((current) => [...current, newPayloadFact()])}
                >
                  <Plus aria-hidden="true" className="button-icon" focusable="false" />
                  Add detail
                </button>
              </div>
              {facts.length ? (
                <div className="payload-fact-list">
                  {facts.map((fact) => (
                    <div className="payload-fact-row" key={fact.id}>
                      <Field label="Name">
                        <input value={fact.name} placeholder="Status" onChange={(event) => updateFact(fact.id, { name: event.target.value })} />
                      </Field>
                      <Field label="Value">
                        <input value={fact.value} placeholder="open" onChange={(event) => updateFact(fact.id, { value: event.target.value })} />
                      </Field>
                      <button
                        className="icon-button icon-button--danger payload-fact-remove"
                        type="button"
                        aria-label="Remove detail"
                        title="Remove detail"
                        onClick={() => setFacts((current) => current.filter((item) => item.id !== fact.id))}
                      >
                        <Trash2 aria-hidden="true" className="button-icon" focusable="false" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyGuidance title="No details" body="Add a detail when the message should include structured name/value information." />
              )}
            </div>
            {mode === "adaptive" ? (
              <div className="payload-actions-section">
                <div className="payload-facts-header">
                  <div>
                    <strong>Buttons</strong>
                    <span>OpenURL actions for related pages or external-system details.</span>
                  </div>
                  <button
                    className="secondary-button secondary-button--small button-with-icon"
                    type="button"
                    onClick={() => setActions((current) => [...current, newPayloadAction()])}
                  >
                    <Plus aria-hidden="true" className="button-icon" focusable="false" />
                    Add button
                  </button>
                </div>
                {actions.length ? (
                  <div className="payload-action-list">
                    {actions.map((action) => (
                      <div className="payload-action-row" key={action.id}>
                        <Field label="Label">
                          <input value={action.title} placeholder="Open link" onChange={(event) => updateAction(action.id, { title: event.target.value })} />
                        </Field>
                        <Field label="URL">
                          <input value={action.url} placeholder="https://example.com/details" onChange={(event) => updateAction(action.id, { url: event.target.value })} />
                        </Field>
                        <button
                          className="icon-button icon-button--danger payload-fact-remove"
                          type="button"
                          aria-label="Remove button"
                          title="Remove button"
                          onClick={() => setActions((current) => current.filter((item) => item.id !== action.id))}
                        >
                          <Trash2 aria-hidden="true" className="button-icon" focusable="false" />
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyGuidance title="No buttons" body="Add an OpenURL button when the Teams message should link to another system." />
                )}
              </div>
            ) : null}
          </div>
        </Card>
        <div className="payload-output-stack">
          <Card title="Preview" description="A pragmatic Teams-like preview of the generated message.">
            <PayloadPreview
              mode={mode}
              title={title}
              message={message}
              accent={accent}
              facts={previewFacts}
              titleSize={titleSize}
              titleWeight={titleWeight}
              imageUrl={imageUrl}
              imageAlt={imageAlt}
              imageSize={imageSize}
              fullWidth={fullWidth}
              actions={previewActions}
            />
          </Card>
          <Card
            title="Generated JSON"
            description="Send this as application/json to a relay webhook URL."
            headerActions={
              <button className="secondary-button secondary-button--small button-with-icon" type="button" onClick={() => void copyPayload()}>
                <ClipboardCopy aria-hidden="true" className="button-icon" focusable="false" />
                Copy
              </button>
            }
          >
            <textarea className="payload-code-output" value={payloadJson} readOnly spellCheck={false} rows={18} />
          </Card>
        </div>
      </div>
    </>
  );
}

function renderMarkdownInline(value: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(value)) !== null) {
    if (match.index > cursor) parts.push(value.slice(cursor, match.index));
    const token = match[0];
    const key = `${match.index}-${token}`;
    if (token.startsWith("**") && token.endsWith("**")) {
      parts.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("*") && token.endsWith("*")) {
      parts.push(<em key={key}>{token.slice(1, -1)}</em>);
    } else {
      const linkMatch = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      if (linkMatch) {
        parts.push(
          <a key={key} href={linkMatch[2]} target="_blank" rel="noreferrer">
            {linkMatch[1]}
          </a>,
        );
      } else {
        parts.push(token);
      }
    }
    cursor = pattern.lastIndex;
  }
  if (cursor < value.length) parts.push(value.slice(cursor));
  return parts;
}

function MarkdownPreview({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let listItems: string[] = [];

  function flushList() {
    if (!listItems.length) return;
    const items = listItems;
    listItems = [];
    blocks.push(
      <ul key={`list-${blocks.length}`}>
        {items.map((item, index) => (
          <li key={`${item}-${index}`}>{renderMarkdownInline(item)}</li>
        ))}
      </ul>,
    );
  }

  text.split("\n").forEach((line, index) => {
    const trimmed = line.trim();
    if (trimmed.startsWith("- ")) {
      listItems.push(trimmed.slice(2));
      return;
    }
    flushList();
    if (!trimmed) return;
    blocks.push(<p key={`p-${index}`}>{renderMarkdownInline(line)}</p>);
  });
  flushList();

  return <div className="teams-preview-markdown">{blocks.length ? blocks : <p>{text}</p>}</div>;
}

function PayloadPreview({
  mode,
  title,
  message,
  accent,
  facts,
  titleSize,
  titleWeight,
  imageUrl,
  imageAlt,
  imageSize,
  fullWidth,
  actions,
}: {
  mode: PayloadGeneratorMode;
  title: string;
  message: string;
  accent: PayloadAccent;
  facts: Array<{ name: string; value: string }>;
  titleSize: PayloadTitleSize;
  titleWeight: PayloadTitleWeight;
  imageUrl: string;
  imageAlt: string;
  imageSize: PayloadImageSize;
  fullWidth: boolean;
  actions: Array<{ title: string; url: string }>;
}) {
  const cleanTitle = title.trim() || "Message title";
  const cleanMessage = message.trim() || "Write the message content here.";
  const cleanImageUrl = imageUrl.trim();
  const cleanImageAlt = imageAlt.trim();

  return (
    <div className={classNames("teams-preview-surface", mode === "adaptive" && fullWidth && "teams-preview-surface--full")}>
      <div className="teams-preview-message">
        <div className="teams-preview-avatar" aria-hidden="true">
          T
        </div>
        <div className="teams-preview-content">
          <div className="teams-preview-meta">
            <strong>Teams Rehook</strong>
            <span>Now</span>
          </div>
          <article className={classNames("teams-preview-card", `teams-preview-card--${accent}`)}>
            <span className="teams-preview-type">{mode === "adaptive" ? "Adaptive Card" : "Text payload"}</span>
            <h2
              className={classNames(
                `teams-preview-title--${titleSize.toLowerCase()}`,
                titleWeight === "Bolder" && "teams-preview-title--bolder",
              )}
            >
              {cleanTitle}
            </h2>
            <MarkdownPreview text={cleanMessage} />
            {mode === "adaptive" && cleanImageUrl ? (
              <img
                className={classNames("teams-preview-image", imageSize === "Stretch" && "teams-preview-image--stretch")}
                src={cleanImageUrl}
                alt={cleanImageAlt || ""}
              />
            ) : null}
            {facts.length ? (
              <dl className="teams-preview-facts">
                {facts.map((fact, index) => (
                  <div key={`${fact.name}-${index}`}>
                    <dt>{fact.name || "Detail"}</dt>
                    <dd>{fact.value || "-"}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
            {mode === "adaptive" && actions.length ? (
              <div className="teams-preview-actions">
                {actions.map((action, index) => (
                  <a key={`${action.title}-${index}`} href={action.url} target="_blank" rel="noreferrer">
                    {action.title}
                  </a>
                ))}
              </div>
            ) : null}
          </article>
        </div>
      </div>
    </div>
  );
}

type DeliveryFeaturePolicy = {
  botFrameworkEnabled: boolean;
  graphLookupEnabled: boolean;
  graphDeliveryEnabled: boolean;
};

const DEFAULT_DELIVERY_FEATURE_POLICY: DeliveryFeaturePolicy = {
  botFrameworkEnabled: true,
  graphLookupEnabled: true,
  graphDeliveryEnabled: true,
};

function featurePolicyFromReadiness(readiness: AdminReadinessOut): DeliveryFeaturePolicy {
  return {
    botFrameworkEnabled: readiness.bot.enabled,
    graphLookupEnabled: readiness.graph_lookup.enabled,
    graphDeliveryEnabled: readiness.graph_delivery.enabled,
  };
}

function routeDeliveryFeatureEnabled(route: WebhookRouteOut, policy: DeliveryFeaturePolicy): boolean {
  if (route.delivery_backend === "bot_framework") return policy.botFrameworkEnabled;
  if (route.delivery_backend === "graph") return policy.graphDeliveryEnabled && policy.graphLookupEnabled;
  return false;
}

type WebhookRouteView = {
  route: WebhookRouteOut;
  tone: StatusTone;
  statusLabel: string;
  summary: string;
  targetSummary: string;
  deliveryLabel: string;
  lastActivityLabel: string;
  topIssue: string;
  topIssueDetail: string;
  featureEnabled: boolean;
  facts: StatusFact[];
  technicalRows: StatusTechnicalRow[];
};

function buildWebhookRouteView(route: WebhookRouteOut, policy: DeliveryFeaturePolicy): WebhookRouteView {
  const featureEnabled = routeDeliveryFeatureEnabled(route, policy);
  const deliveryLabel = route.last_delivery_status ? capitalize(route.last_delivery_status) : "Not tested";
  const lastActivityLabel = route.last_delivery_at ? formatRelativeTime(route.last_delivery_at) : "No delivery yet";
  const tone = webhookRouteTone(route, featureEnabled);
  const statusLabel = webhookRouteStatusLabel(route, featureEnabled);
  const topIssue = webhookRouteTopIssue(route, featureEnabled);
  const targetSummary = webhookTargetSummary(route);

  return {
    route,
    tone,
    statusLabel,
    summary: route.is_active
      ? featureEnabled
        ? `Accepts relay requests for ${route.target_name || "the selected Teams target"}.`
        : "Route is active, but its delivery feature is disabled."
      : "Route is disabled and rejects incoming webhook requests.",
    targetSummary,
    deliveryLabel,
    lastActivityLabel,
    topIssue,
    topIssueDetail: webhookRouteIssueDetail(route, featureEnabled),
    featureEnabled,
    facts: [
      { label: "State", value: route.is_active ? "Active" : "Disabled", tone: route.is_active ? "success" : "warn" },
      { label: "Backend", value: deliveryBackendLabel(route.delivery_backend) },
      { label: "Client IP access", value: clientIpAccessLabel(route) },
      { label: "Delivery", value: deliveryLabel, tone: webhookDeliveryTone(route) },
      { label: "Last activity", value: lastActivityLabel },
    ],
    technicalRows: [
      { label: "Route ID", value: route.id },
      { label: "Webhook URL", value: route.webhook_url ? <code>{route.webhook_url}</code> : "-" },
      { label: "Client IP allowlist", value: route.client_ip_allowlist ? <code>{route.client_ip_allowlist}</code> : "All clients" },
      { label: "Target type", value: route.target_type },
      { label: "Bot conversation", value: route.bot_conversation_id ? <code>{shortId(route.bot_conversation_id)}</code> : "-" },
      { label: "Bot service URL", value: route.bot_service_url || "-" },
      { label: "Graph target kind", value: route.graph_target_kind || "-" },
      { label: "Graph target ID", value: route.graph_target_id ? <code>{shortId(route.graph_target_id)}</code> : "-" },
      { label: "Team ID", value: route.graph_team_id ? <code>{shortId(route.graph_team_id)}</code> : "-" },
      { label: "Channel ID", value: route.graph_channel_id ? <code>{shortId(route.graph_channel_id)}</code> : "-" },
      { label: "Created", value: route.created_at ? formatDateTime(route.created_at) : "-" },
      { label: "Updated", value: route.updated_at ? formatDateTime(route.updated_at) : "-" },
    ],
  };
}

function webhookRouteTone(route: WebhookRouteOut, featureEnabled: boolean): StatusTone {
  if (!route.is_active || !featureEnabled) return "warn";
  if (route.last_delivery_status === "failed" || route.last_delivery_status === "rejected") return "danger";
  if (route.last_delivery_status === "delivered") return "success";
  return "warn";
}

function webhookDeliveryTone(route: WebhookRouteOut): StatusTone {
  if (route.last_delivery_status === "delivered") return "success";
  if (route.last_delivery_status === "failed" || route.last_delivery_status === "rejected") return "danger";
  return "warn";
}

function webhookRouteStatusLabel(route: WebhookRouteOut, featureEnabled: boolean): string {
  if (!route.is_active) return "Disabled";
  if (!featureEnabled) return "Feature disabled";
  if (route.last_delivery_status === "failed") return "Delivery failed";
  if (route.last_delivery_status === "rejected") return "Rejected";
  if (route.last_delivery_status === "delivered") return "Ready";
  return "Untested";
}

function webhookRouteTopIssue(route: WebhookRouteOut, featureEnabled: boolean): string {
  if (!route.is_active) return "Route disabled";
  if (!featureEnabled) return "Delivery feature disabled";
  if (route.last_delivery_status === "failed") return "Last delivery failed";
  if (route.last_delivery_status === "rejected") return "Last request rejected";
  if (!route.last_delivery_status) return "Send a test";
  return "No active issue";
}

function webhookRouteIssueDetail(route: WebhookRouteOut, featureEnabled: boolean): string {
  if (!route.is_active) return "Incoming webhook requests are rejected until this route is activated.";
  if (!featureEnabled) return "The selected backend depends on a disabled readiness feature.";
  if (route.last_delivery_status === "failed") return "Open delivery logs or send another test after correcting the target.";
  if (route.last_delivery_status === "rejected") return "The relay rejected the latest request before delivery completed.";
  if (!route.last_delivery_status) return "Run a deterministic test before sharing this relay URL.";
  return "The latest delivery check completed successfully.";
}

function webhookTargetSummary(route: WebhookRouteOut): string {
  if (route.delivery_backend === "graph") {
    const type = route.graph_target_kind ? capitalize(route.graph_target_kind) : "Graph target";
    return `${type} · ${route.target_name || route.graph_target_id || "No target name"}`;
  }
  return route.target_name || "Bot conversation";
}

function clientIpAccessLabel(route: WebhookRouteOut): string {
  if (route.client_ip_access_mode === "restricted") {
    const count = route.client_ip_allowlist.split(/\s+/).filter(Boolean).length;
    return `Restricted (${count} allowed)`;
  }
  return "Public";
}

function capitalize(value: string): string {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

function WebhooksPage() {
  const { session, notify } = useAppContext();
  const [routes, setRoutes] = useState<WebhookRouteOut[]>([]);
  const [editing, setEditing] = useState<WebhookRouteOut | null>(null);
  const [viewingLogs, setViewingLogs] = useState<WebhookRouteOut | null>(null);
  const [confirmingRegeneration, setConfirmingRegeneration] = useState<WebhookRouteOut | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState<WebhookRouteOut | null>(null);
  const [regeneratedUrl, setRegeneratedUrl] = useState<{ routeName: string; url: string } | null>(null);
  const [viewingBotReferences, setViewingBotReferences] = useState(false);
  const [botDefaultServiceUrl, setBotDefaultServiceUrl] = useState("");
  const [featurePolicy, setFeaturePolicy] = useState<DeliveryFeaturePolicy>(DEFAULT_DELIVERY_FEATURE_POLICY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [testingId, setTestingId] = useState("");
  const [regeneratingId, setRegeneratingId] = useState("");
  const [deletingId, setDeletingId] = useState("");
  const [togglingId, setTogglingId] = useState("");
  const [refreshingRouteNameId, setRefreshingRouteNameId] = useState("");
  const [refreshingMembersId, setRefreshingMembersId] = useState("");
  const [selectedRouteId, setSelectedRouteId] = useState("");
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [routeRows, readiness] = await Promise.all([api.webhookRoutes(), api.adminReadiness(csrfToken)]);
      setRoutes(routeRows);
      setFeaturePolicy(featurePolicyFromReadiness(readiness));
    } catch (err) {
      setError(isApiError(err) ? err.message : "Webhook routes could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [csrfToken]);

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

  async function toggleRouteActive(route: WebhookRouteOut) {
    setTogglingId(route.id);
    try {
      await api.updateWebhookRoute(csrfToken, route.id, { is_active: !route.is_active });
      notify({
        tone: "success",
        title: route.is_active ? "Route deactivated" : "Route activated",
        description: route.name,
      });
      await refresh();
    } catch (err) {
      notify({
        tone: "error",
        title: "Update failed",
        description: isApiError(err) ? err.message : "The route status could not be changed.",
      });
    } finally {
      setTogglingId("");
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
      notify({ tone: "success", title: "Test delivered", description: route.name });
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

  async function refreshRouteMembers(route: WebhookRouteOut) {
    setRefreshingMembersId(route.id);
    try {
      const updated = await api.refreshWebhookRouteMembers(csrfToken, route.id);
      if (updated.members_lookup_error) {
        notify({
          tone: "error",
          title: "Member refresh failed",
          description: updated.members_lookup_error,
        });
      } else {
        notify({
          tone: "success",
          title: "Members refreshed",
          description: updated.member_summary || `${updated.member_count} members`,
        });
      }
      await refresh();
    } catch (err) {
      notify({
        tone: "error",
        title: "Member refresh failed",
        description: isApiError(err) ? err.message : "The member list could not be refreshed.",
      });
    } finally {
      setRefreshingMembersId("");
    }
  }

  const routeViews = routes.map((route) => buildWebhookRouteView(route, featurePolicy));
  const defaultSelectedRouteId =
    routeViews.find((view) => view.tone === "danger")?.route.id ??
    routeViews.find((view) => view.tone === "warn")?.route.id ??
    routeViews[0]?.route.id ??
    "";
  const selectedRouteView =
    routeViews.find((view) => view.route.id === selectedRouteId) ??
    routeViews.find((view) => view.route.id === defaultSelectedRouteId) ??
    routeViews[0] ??
    null;
  const selectedRouteIdEffective = selectedRouteView?.route.id ?? defaultSelectedRouteId;

  return (
    <>
      <PageIntro
        eyebrow="Teams Rehook"
        title="Webhook routes"
        description="Operate relay endpoints, validate delivery and inspect route health without digging through raw diagnostics."
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
      <div className="webhooks-command-center">
        <WebhookRouteSummary routeViews={routeViews} loading={loading} />
        <WebhookRouteConsole
          error={error}
          loading={loading}
          onCopyRoute={(route) => void copyText(route.webhook_url ?? "", route.name)}
          onCreateRoute={() => setEditing(emptyWebhookRoute(botDefaultServiceUrl))}
          onEditRoute={setEditing}
          onRetry={() => void refresh()}
          onSelectRoute={setSelectedRouteId}
          onTestRoute={(route) => void testRoute(route)}
          routeViews={routeViews}
          selectedRouteId={selectedRouteIdEffective}
          testingId={testingId}
        />
        <WebhookRouteInspector
          featurePolicy={featurePolicy}
          onCopyRoute={(route) => void copyText(route.webhook_url ?? "", route.name)}
          onDeleteRoute={setConfirmingDelete}
          onEditRoute={setEditing}
          onRefreshMembers={(route) => void refreshRouteMembers(route)}
          onRefreshNames={(route) => void refreshRouteGraphNames(route)}
          onRegenerateRoute={setConfirmingRegeneration}
          onTestRoute={(route) => void testRoute(route)}
          onToggleRoute={(route) => void toggleRouteActive(route)}
          onViewLogs={setViewingLogs}
          refreshingMembersId={refreshingMembersId}
          refreshingRouteNameId={refreshingRouteNameId}
          regeneratingId={regeneratingId}
          routeView={selectedRouteView}
          testingId={testingId}
          togglingId={togglingId}
        />
      </div>
      {editing ? (
        <WebhookRouteModal
          route={editing.id ? editing : null}
          initial={editing}
          featurePolicy={featurePolicy}
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
            <p>External systems using this relay URL will fail until they are pointed to another active route.</p>
          </div>
        </ConfirmModal>
      ) : null}
      {regeneratedUrl ? (
        <WebhookUrlRevealModal
          title="Webhook URL regenerated"
          routeName={regeneratedUrl.routeName}
          note="The previous URL stopped working immediately. Update any external systems that still use it."
          onCopy={() => void copyText(regeneratedUrl.url, regeneratedUrl.routeName)}
          onClose={() => setRegeneratedUrl(null)}
        />
      ) : null}
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

function WebhookRouteSummary({ loading, routeViews }: { loading: boolean; routeViews: WebhookRouteView[] }) {
  const activeCount = routeViews.filter((view) => view.route.is_active).length;
  const attentionCount = routeViews.filter((view) => view.tone === "danger" || view.tone === "warn").length;
  const graphCount = routeViews.filter((view) => view.route.delivery_backend === "graph").length;
  const botCount = routeViews.filter((view) => view.route.delivery_backend === "bot_framework").length;
  const deliveredCount = routeViews.filter((view) => view.route.last_delivery_status === "delivered").length;

  return (
    <section className="webhook-route-summary" aria-label="Webhook route summary">
      <StatusOverviewMetric
        label="Routes"
        value={loading ? "..." : String(routeViews.length)}
        detail={routeViews.length === 1 ? "1 relay endpoint." : `${routeViews.length} relay endpoints.`}
        tone="neutral"
      />
      <StatusOverviewMetric
        label="Active"
        value={loading ? "..." : `${activeCount}/${routeViews.length || 0}`}
        detail={activeCount === routeViews.length && routeViews.length ? "All routes accept traffic." : "Some routes are paused."}
        tone={routeViews.length && activeCount === routeViews.length ? "success" : activeCount ? "warn" : "neutral"}
      />
      <StatusOverviewMetric
        label="Attention"
        value={loading ? "..." : attentionCount ? String(attentionCount) : "None"}
        detail={attentionCount ? "Review the selected route." : "No open route issue."}
        tone={attentionCount ? "warn" : "success"}
      />
      <StatusOverviewMetric
        label="Delivery"
        value={loading ? "..." : `${deliveredCount}/${routeViews.length || 0} tested`}
        detail={`${graphCount} Graph / ${botCount} Bot Framework`}
        tone={deliveredCount === routeViews.length && routeViews.length ? "success" : deliveredCount ? "warn" : "neutral"}
      />
    </section>
  );
}

function WebhookRouteConsole({
  error,
  loading,
  onCopyRoute,
  onCreateRoute,
  onEditRoute,
  onRetry,
  onSelectRoute,
  onTestRoute,
  routeViews,
  selectedRouteId,
  testingId,
}: {
  error: string;
  loading: boolean;
  onCopyRoute: (route: WebhookRouteOut) => void;
  onCreateRoute: () => void;
  onEditRoute: (route: WebhookRouteOut) => void;
  onRetry: () => void;
  onSelectRoute: (routeId: string) => void;
  onTestRoute: (route: WebhookRouteOut) => void;
  routeViews: WebhookRouteView[];
  selectedRouteId: string;
  testingId: string;
}) {
  if (loading) {
    return (
      <Card>
        <div className="table-state" role="status" aria-live="polite">
          <div className="spinner spinner--small" aria-hidden="true" />
          <p>Loading webhook routes...</p>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <div className="table-state table-state--error" role="alert">
          <h3>Could not load webhook routes</h3>
          <p>{error}</p>
          <button className="secondary-button secondary-button--small" type="button" onClick={onRetry}>
            Retry
          </button>
        </div>
      </Card>
    );
  }

  if (!routeViews.length) {
    return (
      <Card>
        <EmptyState
          title="No webhook routes"
          body="Add the bot to a Teams chat or channel, create a route from a known conversation, then send a test before sharing the relay URL."
        />
        <div className="form-actions form-actions--start">
          <button className="primary-button button-with-icon" type="button" onClick={onCreateRoute}>
            <Plus aria-hidden="true" className="button-icon" focusable="false" />
            New route
          </button>
        </div>
      </Card>
    );
  }

  return (
    <section className="webhook-route-console" aria-label="Relay route console">
      <div className="webhook-route-console-header">
        <div>
          <p className="integration-kicker">Relay routes</p>
          <h2>Route health</h2>
        </div>
        <span>{routeViews.length} routes</span>
      </div>
      <div className="webhook-route-list" role="list">
        {routeViews.map((view) => (
          <WebhookRouteRow
            key={view.route.id}
            onCopyRoute={onCopyRoute}
            onEditRoute={onEditRoute}
            onSelectRoute={onSelectRoute}
            onTestRoute={onTestRoute}
            selected={selectedRouteId === view.route.id}
            testing={testingId === view.route.id}
            view={view}
          />
        ))}
      </div>
    </section>
  );
}

function WebhookRouteRow({
  onCopyRoute,
  onEditRoute,
  onSelectRoute,
  onTestRoute,
  selected,
  testing,
  view,
}: {
  onCopyRoute: (route: WebhookRouteOut) => void;
  onEditRoute: (route: WebhookRouteOut) => void;
  onSelectRoute: (routeId: string) => void;
  onTestRoute: (route: WebhookRouteOut) => void;
  selected: boolean;
  testing: boolean;
  view: WebhookRouteView;
}) {
  return (
    <article className={classNames("webhook-route-row", selected && "webhook-route-row--selected")} role="listitem">
      <button
        aria-pressed={selected}
        className="webhook-route-row-main"
        type="button"
        onClick={() => onSelectRoute(view.route.id)}
      >
        <span className={classNames("status-dot", `status-dot--${view.tone}`)} aria-hidden="true" />
        <span className="webhook-route-row-title">
          <strong>{view.route.name}</strong>
          <small>{view.targetSummary}</small>
        </span>
        <span className="webhook-route-row-status">
          <strong>{view.statusLabel}</strong>
          <small>{view.lastActivityLabel}</small>
        </span>
        <span className="webhook-route-row-issue">
          <span>{view.topIssue}</span>
          <small>{view.deliveryLabel}</small>
        </span>
      </button>
      <div className="webhook-route-row-actions">
        {view.route.webhook_url ? (
          <IconButton label="Copy relay URL" icon={ClipboardCopy} onClick={() => onCopyRoute(view.route)} />
        ) : null}
        <IconButton
          label={testing ? "Sending test" : "Send test"}
          icon={Send}
          disabled={testing || !view.featureEnabled}
          onClick={() => onTestRoute(view.route)}
        />
        <IconButton label="Edit route" icon={Pencil} onClick={() => onEditRoute(view.route)} />
      </div>
    </article>
  );
}

function WebhookRouteInspector({
  featurePolicy,
  onCopyRoute,
  onDeleteRoute,
  onEditRoute,
  onRefreshMembers,
  onRefreshNames,
  onRegenerateRoute,
  onTestRoute,
  onToggleRoute,
  onViewLogs,
  refreshingMembersId,
  refreshingRouteNameId,
  regeneratingId,
  routeView,
  testingId,
  togglingId,
}: {
  featurePolicy: DeliveryFeaturePolicy;
  onCopyRoute: (route: WebhookRouteOut) => void;
  onDeleteRoute: (route: WebhookRouteOut) => void;
  onEditRoute: (route: WebhookRouteOut) => void;
  onRefreshMembers: (route: WebhookRouteOut) => void;
  onRefreshNames: (route: WebhookRouteOut) => void;
  onRegenerateRoute: (route: WebhookRouteOut) => void;
  onTestRoute: (route: WebhookRouteOut) => void;
  onToggleRoute: (route: WebhookRouteOut) => void;
  onViewLogs: (route: WebhookRouteOut) => void;
  refreshingMembersId: string;
  refreshingRouteNameId: string;
  regeneratingId: string;
  routeView: WebhookRouteView | null;
  testingId: string;
  togglingId: string;
}) {
  if (!routeView) return null;
  const route = routeView.route;

  return (
    <aside className="webhook-route-inspector" aria-label={`${route.name} route details`}>
      <div className="webhook-route-inspector-header">
        <div>
          <p className="integration-kicker">Selected route</p>
          <h2>{route.name}</h2>
          <p>{routeView.summary}</p>
        </div>
        <div className={classNames("status-health-pill", `status-health-pill--${routeView.tone}`)}>
          <span aria-hidden="true" />
          <strong>{routeView.statusLabel}</strong>
        </div>
      </div>

      {routeView.tone !== "success" ? (
        <div className={classNames("status-detail-alert", routeView.tone === "danger" && "status-detail-alert--danger")}>
          <strong>{routeView.topIssue}</strong>
          <span>{routeView.topIssueDetail}</span>
        </div>
      ) : null}

      <section className="webhook-route-inspector-section">
        <h3>Overview</h3>
        <StatusFactList facts={routeView.facts} />
      </section>

      <section className="webhook-route-inspector-section">
        <h3>Target</h3>
        <div className="webhook-target-panel">
          <div>
            <strong>{route.target_name || "Unnamed target"}</strong>
            <span>{deliveryBackendLabel(route.delivery_backend)}</span>
            {route.member_summary ? <small>{route.member_summary}</small> : null}
            {route.members_refreshed_at ? <small>Members refreshed {formatRelativeTime(route.members_refreshed_at)}</small> : null}
            {route.members_lookup_error ? <small className="form-error">{route.members_lookup_error}</small> : null}
          </div>
        </div>
      </section>

      <section className="webhook-route-inspector-section">
        <h3>Relay URL</h3>
        <div className="webhook-route-url-action">
          {!route.webhook_url ? <span className="muted">Unavailable for old route</span> : null}
          <button
            className="secondary-button secondary-button--small button-with-icon"
            type="button"
            disabled={!route.webhook_url}
            onClick={() => onCopyRoute(route)}
          >
            <ClipboardCopy aria-hidden="true" className="button-icon" focusable="false" />
            Copy URL
          </button>
        </div>
      </section>

      <section className="webhook-route-inspector-section">
        <h3>Operator actions</h3>
        <div className="webhook-route-action-grid">
          <button
            className="primary-button button-with-icon"
            type="button"
            disabled={testingId === route.id || !routeView.featureEnabled}
            onClick={() => onTestRoute(route)}
          >
            <Send aria-hidden="true" className="button-icon" focusable="false" />
            {testingId === route.id ? "Sending..." : "Send test"}
          </button>
          <button className="secondary-button button-with-icon" type="button" onClick={() => onEditRoute(route)}>
            <Pencil aria-hidden="true" className="button-icon" focusable="false" />
            Edit route
          </button>
          <button className="secondary-button button-with-icon" type="button" onClick={() => onViewLogs(route)}>
            <FileClock aria-hidden="true" className="button-icon" focusable="false" />
            Delivery logs
          </button>
          <button
            className="secondary-button button-with-icon"
            type="button"
            disabled={togglingId === route.id}
            onClick={() => onToggleRoute(route)}
          >
            {route.is_active ? <PowerOff aria-hidden="true" className="button-icon" focusable="false" /> : <Power aria-hidden="true" className="button-icon" focusable="false" />}
            {togglingId === route.id ? "Updating..." : route.is_active ? "Deactivate" : "Activate"}
          </button>
        </div>
      </section>

      <details className="status-detail-disclosure">
        <summary>
          <span>Advanced actions</span>
          <small>Refresh metadata, rotate URL or delete the route</small>
        </summary>
        <div className="webhook-route-danger-zone">
          <button
            className="secondary-button secondary-button--small button-with-icon"
            type="button"
            disabled={refreshingMembersId === route.id}
            onClick={() => onRefreshMembers(route)}
          >
            <MessagesSquare
              aria-hidden="true"
              className={classNames("button-icon", refreshingMembersId === route.id && "button-icon--spin")}
              focusable="false"
            />
            {refreshingMembersId === route.id ? "Refreshing..." : "Refresh members"}
          </button>
          <button
            className="secondary-button secondary-button--small button-with-icon"
            type="button"
            disabled={refreshingRouteNameId === route.id || !featurePolicy.graphLookupEnabled}
            onClick={() => onRefreshNames(route)}
          >
            <RefreshCw
              aria-hidden="true"
              className={classNames("button-icon", refreshingRouteNameId === route.id && "button-icon--spin")}
              focusable="false"
            />
            {refreshingRouteNameId === route.id ? "Refreshing..." : "Refresh Graph names"}
          </button>
          <button
            className="secondary-button secondary-button--small button-with-icon"
            type="button"
            disabled={regeneratingId === route.id}
            onClick={() => onRegenerateRoute(route)}
          >
            <RotateCcwKey aria-hidden="true" className="button-icon" focusable="false" />
            {regeneratingId === route.id ? "Regenerating..." : "Regenerate URL"}
          </button>
          <button className="danger-button danger-button--small button-with-icon" type="button" onClick={() => onDeleteRoute(route)}>
            <Trash2 aria-hidden="true" className="button-icon" focusable="false" />
            Delete route
          </button>
        </div>
      </details>

      <details className="status-detail-disclosure">
        <summary>
          <span>Diagnostics</span>
          <small>Delivery backend, feature state and technical identifiers</small>
        </summary>
        <div className="status-detail-disclosure-body">
          <dl className="definition-list definition-list--compact advanced-definition-list">
            <FragmentPair label="Backend available" value={routeDeliveryFeatureEnabled(route, featurePolicy) ? "Yes" : "No"} />
            {routeView.technicalRows.map((row) => (
              <FragmentPair key={row.label} label={row.label} value={row.value} />
            ))}
          </dl>
        </div>
      </details>
    </aside>
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
        <p>Any external system still using the current URL will receive a not found response as soon as the new URL is created.</p>
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
      description="Conversations captured from inbound Teams bot activities, grouped by channel or user."
      panelClassName="delivery-logs-modal"
      onClose={onClose}
    >
      {loading ? <p className="muted">Loading bot conversations...</p> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!loading && !error && references.length === 0 ? (
        <div className="guidance-box">
          <strong>No bot conversations captured yet.</strong>
          <p>Add Teams Rehook to a chat or channel, then send a message or mention the bot. The next inbound bot activity stores the service URL and conversation ID needed for delivery.</p>
          <p>After a conversation appears here, create a route from it and use Send test before sharing the relay URL with an external system.</p>
        </div>
      ) : null}
      {references.length ? (
        <div className="conversation-reference-list">
          {references.map((reference) => (
            <section className="conversation-reference-card" key={reference.id}>
              <div className="conversation-reference-main">
                <div className="conversation-reference-heading">
                  <h3>{referenceTitle(reference)}</h3>
                  <StatusBadge label={reference.scope || "unknown"} tone={reference.scope === "channel" || reference.scope === "chat" ? "success" : reference.scope === "team" ? "neutral" : "warn"} />
                </div>
                <p className="conversation-reference-meta">
                  {reference.user_name ? <span>{reference.user_name}</span> : null}
                  <span>{formatRelativeTime(reference.last_seen_at)}</span>
                </p>
              </div>
              <button className="secondary-button secondary-button--small" type="button" onClick={() => onCreateRoute(reference)}>
                Create route
              </button>
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
  if (reference.member_summary) return reference.member_summary;
  if (reference.scope === "chat" || reference.conversation_type.toLowerCase() === "groupchat") return "Group chat";
  if (reference.user_name) return reference.user_name;
  return reference.conversation_type === "personal" ? "Personal chat" : "Teams conversation";
}

function referenceSubtitle(reference: BotConversationReferenceOut): string {
  const parts = [
    reference.scope || reference.conversation_type || "conversation",
    `seen ${formatRelativeTime(reference.last_seen_at)}`,
    reference.member_count ? `${reference.member_count} members` : "",
    reference.channel_id ? `channel ${shortId(reference.channel_id)}` : "",
    reference.scope === "chat" || reference.conversation_type.toLowerCase() === "groupchat" ? `chat ${shortId(reference.conversation_id)}` : "",
    reference.graph_user_id || reference.user_id ? `user ${shortId(reference.graph_user_id || reference.user_id)}` : "",
  ].filter(Boolean);
  return parts.join(" · ");
}

function referenceGraphKind(reference: BotConversationReferenceOut): GraphTargetKind | "" {
  if (reference.scope === "chat" || reference.conversation_type.toLowerCase() === "groupchat") return "chat";
  if (reference.scope === "channel" || reference.channel_id) return "channel";
  if (reference.scope === "team" || reference.graph_team_id) return "team";
  if (reference.scope === "user" || reference.graph_user_id || reference.user_id) return "user";
  return "";
}

function referenceGraphTargetId(reference: BotConversationReferenceOut): string {
  const kind = referenceGraphKind(reference);
  if (kind === "channel") return reference.channel_id;
  if (kind === "team") return reference.graph_team_id || reference.team_id;
  if (kind === "chat") return reference.conversation_id;
  if (kind === "user") return reference.graph_user_id || reference.user_id;
  return "";
}

function referenceTargetName(reference: BotConversationReferenceOut): string {
  return referenceTitle(reference);
}

function GraphTargetSummary({
  kind,
  targetId,
  targetName,
  teamName,
  teamId,
  channelId,
  compact = false,
}: {
  kind: GraphTargetKind | "";
  targetId: string;
  targetName: string;
  teamName: string;
  teamId: string;
  channelId: string;
  compact?: boolean;
}) {
  if (!kind) return null;
  const technicalParts = [
    kind === "chat" && targetId ? `chat ${shortId(targetId)}` : "",
    teamId ? `team ${shortId(teamId)}` : "",
    channelId ? `channel ${shortId(channelId)}` : "",
  ].filter(Boolean);
  if (compact) {
    const typeLabel = kind === "channel" ? "Channel" : kind === "team" ? "Team" : kind === "chat" ? "Chat" : "User";
    return (
      <span className="graph-target-summary">
        <span className="muted" title={technicalParts.length ? technicalParts.join(" / ") : undefined}>{typeLabel}</span>
      </span>
    );
  }
  const label = kind === "channel" ? "Graph channel" : kind === "team" ? "Graph team" : kind === "chat" ? "Graph chat" : "Graph user";
  const title = kind === "channel" && teamName ? targetName || teamName : targetName || teamName || "Selected target";
  return (
    <span className="graph-target-summary">
      <span>{label}: {title}</span>
      {technicalParts.length ? <small>{technicalParts.join(" / ")}</small> : null}
    </span>
  );
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
  const tone =
    route.last_delivery_status === "delivered" ? "success" : route.last_delivery_status === "failed" ? "danger" : "warn";
  return (
    <span className={classNames("delivery-status-text", `delivery-status-text--${tone}`)} aria-label={ariaLabel} title={detail}>
      {label}
    </span>
  );
}

function emptyWebhookRoute(botDefaultServiceUrl = ""): WebhookRouteOut {
  return {
    id: "",
    organization_id: "",
    name: "",
    is_active: true,
    delivery_backend: "bot_framework",
    client_ip_access_mode: "public",
    client_ip_allowlist: "",
    target_type: "bot_conversation",
    target_name: "",
    bot_service_url: botDefaultServiceUrl,
    bot_conversation_id: "",
    graph_target_kind: "",
    graph_target_id: "",
    graph_team_id: "",
    graph_team_name: "",
    graph_channel_id: "",
    graph_user_id: "",
    graph_user_display_name: "",
    graph_user_principal_name: "",
    member_summary: "",
    member_count: 0,
    members: [],
    members_refreshed_at: null,
    members_lookup_error: "",
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
    target_name: referenceTargetName(reference),
    bot_service_url: reference.service_url,
    bot_conversation_id: reference.conversation_id,
    graph_target_kind: kind,
    graph_target_id: referenceGraphTargetId(reference),
    graph_team_id: reference.graph_team_id,
    graph_team_name: reference.team_name,
    graph_channel_id: kind === "channel" ? reference.channel_id : "",
    graph_user_id: kind === "user" ? reference.graph_user_id || reference.user_id : "",
    graph_user_display_name: kind === "user" ? reference.user_name : "",
    graph_user_principal_name: "",
    member_summary: reference.member_summary,
    member_count: reference.member_count,
    members: reference.members,
    members_refreshed_at: reference.members_refreshed_at,
    members_lookup_error: reference.members_lookup_error,
    bot_target_source: "conversation_reference",
    bot_registered_by_id: reference.graph_user_id || reference.user_id,
  };
}

function WebhookRouteModal({
  featurePolicy,
  route,
  initial,
  onClose,
  onChanged,
}: {
  featurePolicy: DeliveryFeaturePolicy;
  route: WebhookRouteOut | null;
  initial: WebhookRouteOut;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const { session, notify } = useAppContext();
  const [name, setName] = useState(initial.name);
  const [isActive, setIsActive] = useState(initial.is_active);
  const [deliveryBackend, setDeliveryBackend] = useState<DeliveryBackend>(initial.delivery_backend);
  const [clientIpAccessMode, setClientIpAccessMode] = useState<ClientIpAccessMode>(initial.client_ip_access_mode);
  const [clientIpAllowlist, setClientIpAllowlist] = useState(initial.client_ip_allowlist);
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
  const [graphTeamSearch, setGraphTeamSearch] = useState("");
  const [graphTeams, setGraphTeams] = useState<TeamsTargetSearchResult[]>([]);
  const [graphTeamsLoading, setGraphTeamsLoading] = useState(false);
  const [graphChannelSearch, setGraphChannelSearch] = useState("");
  const [graphChannels, setGraphChannels] = useState<TeamsTargetSearchResult[]>([]);
  const [graphChannelsLoading, setGraphChannelsLoading] = useState(false);
  const [graphChatSearch, setGraphChatSearch] = useState("");
  const [graphChats, setGraphChats] = useState<TeamsTargetSearchResult[]>([]);
  const [graphChatsLoading, setGraphChatsLoading] = useState(false);
  const [graphUserSearch, setGraphUserSearch] = useState(initial.graph_user_principal_name || initial.graph_user_display_name);
  const [graphUsers, setGraphUsers] = useState<TeamsTargetSearchResult[]>([]);
  const [graphUsersLoading, setGraphUsersLoading] = useState(false);
  const [graphUserId, setGraphUserId] = useState(initial.graph_user_id);
  const [graphUserDisplayName, setGraphUserDisplayName] = useState(initial.graph_user_display_name);
  const [graphUserPrincipalName, setGraphUserPrincipalName] = useState(initial.graph_user_principal_name);
  const [graphSearchError, setGraphSearchError] = useState("");
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

  const botBackendEnabled = featurePolicy.botFrameworkEnabled;
  const graphBackendEnabled = featurePolicy.graphLookupEnabled && featurePolicy.graphDeliveryEnabled;
  const selectedBackendEnabled = deliveryBackend === "bot_framework" ? botBackendEnabled : graphBackendEnabled;

  useEffect(() => {
    if (route) return;
    if (deliveryBackend === "bot_framework" && !botBackendEnabled && graphBackendEnabled) {
      setDeliveryBackend("graph");
      if (!graphTargetKind || graphTargetKind === "team") selectGraphTargetKind("channel");
    }
    if (deliveryBackend === "graph" && !graphBackendEnabled && botBackendEnabled) {
      setDeliveryBackend("bot_framework");
    }
  }, [botBackendEnabled, deliveryBackend, graphBackendEnabled, graphTargetKind, route]);

  const visibleGraphUserTargetId = graphUserId.trim() || (showAdvancedTarget ? graphTargetId.trim() : "");
  const routeTargetReady =
    !selectedBackendEnabled
      ? false
      : deliveryBackend === "bot_framework"
      ? Boolean(targetName.trim() && botServiceUrl.trim() && botConversationId.trim())
      : graphTargetKind === "channel"
        ? Boolean(targetName.trim() && graphTeamId.trim() && graphChannelId.trim())
        : graphTargetKind === "chat"
          ? Boolean(targetName.trim() && graphTargetId.trim())
          : graphTargetKind === "user"
            ? Boolean(targetName.trim() && visibleGraphUserTargetId)
          : false;

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
    setGraphUserId(kind === "user" ? reference.graph_user_id || reference.user_id : "");
    setGraphUserDisplayName(kind === "user" ? reference.user_name : "");
    setGraphUserPrincipalName("");
    setBotTargetSource("conversation_reference");
    setShowAdvancedTarget(false);
  }

  async function searchGraphTeams() {
    setGraphTeamsLoading(true);
    setGraphSearchError("");
    try {
      setGraphTeams(await api.searchTeamsTargets("team", graphTeamSearch));
    } catch (err) {
      setGraphSearchError(isApiError(err) ? err.message : "Team search failed.");
    } finally {
      setGraphTeamsLoading(false);
    }
  }

  async function searchGraphChannels() {
    if (!graphTeamId.trim()) return;
    setGraphChannelsLoading(true);
    setGraphSearchError("");
    try {
      setGraphChannels(await api.teamChannels(graphTeamId.trim(), graphChannelSearch));
    } catch (err) {
      setGraphSearchError(isApiError(err) ? err.message : "Channel search failed.");
    } finally {
      setGraphChannelsLoading(false);
    }
  }

  async function searchGraphChats() {
    setGraphChatsLoading(true);
    setGraphSearchError("");
    try {
      setGraphChats(await api.serviceUserChats(graphChatSearch));
    } catch (err) {
      setGraphSearchError(isApiError(err) ? err.message : "Service-user chat search failed.");
    } finally {
      setGraphChatsLoading(false);
    }
  }

  async function searchGraphUsers() {
    setGraphUsersLoading(true);
    setGraphSearchError("");
    try {
      setGraphUsers(await api.searchTeamsTargets("user", graphUserSearch));
    } catch (err) {
      setGraphSearchError(isApiError(err) ? err.message : "User search failed.");
    } finally {
      setGraphUsersLoading(false);
    }
  }

  function applyGraphTeam(target: TeamsTargetSearchResult) {
    setGraphTeamId(target.team_id || target.id);
    setGraphTeamName(target.team_name || target.display_name);
    setGraphChannelId("");
    setGraphTargetId("");
    setGraphChannels([]);
    setGraphUserId("");
    setGraphUserDisplayName("");
    setGraphUserPrincipalName("");
    setTargetName(target.display_name);
  }

  function applyGraphChannel(target: TeamsTargetSearchResult) {
    const teamName = target.team_name || graphTeamName;
    setDeliveryBackend("graph");
    setGraphTargetKind("channel");
    setGraphTargetId(target.channel_id || target.id);
    setGraphTeamId(target.team_id || graphTeamId);
    setGraphTeamName(teamName);
    setGraphChannelId(target.channel_id || target.id);
    setGraphUserId("");
    setGraphUserDisplayName("");
    setGraphUserPrincipalName("");
    setTargetName(teamName ? `${teamName} / ${target.display_name}` : target.display_name);
    setBotServiceUrl("");
    setBotConversationId("");
    setBotTargetSource("graph_lookup");
  }

  function applyGraphChat(target: TeamsTargetSearchResult) {
    setDeliveryBackend("graph");
    setGraphTargetKind("chat");
    setGraphTargetId(target.id);
    setGraphTeamId("");
    setGraphTeamName("");
    setGraphChannelId("");
    setGraphUserId("");
    setGraphUserDisplayName("");
    setGraphUserPrincipalName("");
    setTargetName(target.display_name);
    setBotServiceUrl("");
    setBotConversationId("");
    setBotTargetSource("graph_lookup");
  }

  function selectGraphTargetKind(kind: GraphTargetKind) {
    setGraphTargetKind(kind);
    setGraphSearchError("");
    if (kind !== "channel") {
      setGraphTeamId("");
      setGraphTeamName("");
      setGraphChannelId("");
    }
    if (kind !== "chat") setGraphTargetId("");
    if (kind !== "user") {
      setGraphUserId("");
      setGraphUserDisplayName("");
      setGraphUserPrincipalName("");
    }
  }

  function applyGraphUser(target: TeamsTargetSearchResult) {
    setDeliveryBackend("graph");
    setGraphTargetKind("user");
    setGraphTargetId(target.id);
    setGraphTeamId("");
    setGraphTeamName("");
    setGraphChannelId("");
    setGraphUserId(target.id);
    setGraphUserDisplayName(target.display_name);
    setGraphUserPrincipalName(target.subtitle);
    setTargetName(target.display_name);
    setBotServiceUrl("");
    setBotConversationId("");
    setBotTargetSource("graph_user_lookup");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const body = {
      name: name.trim(),
      is_active: isActive,
      delivery_backend: deliveryBackend,
      client_ip_access_mode: clientIpAccessMode,
      client_ip_allowlist: clientIpAccessMode === "restricted" ? clientIpAllowlist.trim() : "",
      target_type: "bot_conversation" as const,
      target_name: targetName.trim(),
      bot_service_url: botServiceUrl.trim(),
      bot_conversation_id: botConversationId.trim(),
      graph_target_kind: graphTargetKind || null,
      graph_target_id: graphTargetKind === "user" ? visibleGraphUserTargetId : graphTargetId.trim(),
      graph_team_id: graphTeamId.trim(),
      graph_team_name: graphTeamName.trim(),
      graph_channel_id: graphChannelId.trim(),
      graph_user_id: graphUserId.trim(),
      graph_user_display_name: graphUserDisplayName.trim(),
      graph_user_principal_name: graphUserPrincipalName.trim(),
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
      panelClassName="webhook-route-modal"
      onClose={onClose}
    >
      <form className="compact-form" onSubmit={submit}>
        <div className="webhook-route-modal-top">
          <Field label="Name">
            <input value={name} required maxLength={200} onChange={(event) => setName(event.target.value)} />
          </Field>
          <div className="field">
            <span>Status</span>
            <div className="segmented-control" aria-label="Route status">
              <button
                type="button"
                className={classNames("segmented-control-button", isActive && "is-active")}
                aria-pressed={isActive}
                onClick={() => setIsActive(true)}
              >
                Active
              </button>
              <button
                type="button"
                className={classNames("segmented-control-button", !isActive && "is-active")}
                aria-pressed={!isActive}
                onClick={() => setIsActive(false)}
              >
                Disabled
              </button>
            </div>
          </div>
          <div className="field">
            <span>Delivery backend</span>
            <div className="segmented-control" aria-label="Delivery backend">
              {botBackendEnabled || deliveryBackend === "bot_framework" ? (
                <button
                  type="button"
                  className={classNames("segmented-control-button", deliveryBackend === "bot_framework" && "is-active")}
                  aria-pressed={deliveryBackend === "bot_framework"}
                  disabled={!botBackendEnabled}
                  onClick={() => setDeliveryBackend("bot_framework")}
                >
                  Bot Framework
                </button>
              ) : null}
              {graphBackendEnabled || deliveryBackend === "graph" ? (
                <button
                  type="button"
                  className={classNames("segmented-control-button", deliveryBackend === "graph" && "is-active")}
                  aria-pressed={deliveryBackend === "graph"}
                  disabled={!graphBackendEnabled}
                  onClick={() => {
                    setDeliveryBackend("graph");
                    setBotServiceUrl("");
                    setBotConversationId("");
                    if (!graphTargetKind || graphTargetKind === "team") selectGraphTargetKind("channel");
                  }}
                >
                  Microsoft Graph
                </button>
              ) : null}
            </div>
            {!selectedBackendEnabled ? <p className="form-error">{deliveryBackend === "graph" ? "Microsoft Graph delivery is disabled." : "Bot Framework delivery is disabled."}</p> : null}
          </div>
          <div className="field">
            <span>Client IP access</span>
            <div className="segmented-control" aria-label="Client IP access">
              <button
                type="button"
                className={classNames("segmented-control-button", clientIpAccessMode === "public" && "is-active")}
                aria-pressed={clientIpAccessMode === "public"}
                onClick={() => setClientIpAccessMode("public")}
              >
                Public
              </button>
              <button
                type="button"
                className={classNames("segmented-control-button", clientIpAccessMode === "restricted" && "is-active")}
                aria-pressed={clientIpAccessMode === "restricted"}
                onClick={() => setClientIpAccessMode("restricted")}
              >
                Restricted
              </button>
            </div>
          </div>
        </div>
        {clientIpAccessMode === "restricted" ? (
          <Field label="Allowed client IPs" hint="Enter IPv4/IPv6 addresses or CIDR ranges, separated by commas or new lines.">
            <textarea
              value={clientIpAllowlist}
              required
              placeholder={"203.0.113.10\n10.0.0.0/24"}
              onChange={(event) => setClientIpAllowlist(event.target.value)}
            />
          </Field>
        ) : null}
        {deliveryBackend === "bot_framework" && botBackendEnabled ? (
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
        ) : null}
        {deliveryBackend === "graph" && graphBackendEnabled ? (
          <div className="graph-target-picker">
            <div className="graph-target-picker-header">
              <div>
                <strong>Microsoft Graph target</strong>
                <p>Send as the connected service user to a Team channel, existing chat or one-on-one chat.</p>
              </div>
              <StatusBadge label="Delegated" tone="neutral" />
            </div>
            <div className="segmented-control" aria-label="Graph target type">
              <button
                type="button"
                className={classNames("segmented-control-button", graphTargetKind === "channel" && "is-active")}
                aria-pressed={graphTargetKind === "channel"}
                onClick={() => selectGraphTargetKind("channel")}
              >
                Channel
              </button>
              <button
                type="button"
                className={classNames("segmented-control-button", graphTargetKind === "chat" && "is-active")}
                aria-pressed={graphTargetKind === "chat"}
                onClick={() => selectGraphTargetKind("chat")}
              >
                Existing chat
              </button>
              <button
                type="button"
                className={classNames("segmented-control-button", graphTargetKind === "user" && "is-active")}
                aria-pressed={graphTargetKind === "user"}
                onClick={() => selectGraphTargetKind("user")}
              >
                One-on-one
              </button>
            </div>
            {targetName && routeTargetReady ? (
              <div className="selected-conversation-summary">
                <div className="selected-conversation-copy">
                  <span>Current Graph target</span>
                  <strong>{targetName}</strong>
                  <small>
                    {graphTargetKind === "user"
                      ? graphUserPrincipalName || shortId(visibleGraphUserTargetId)
                      : graphTargetKind === "chat"
                        ? shortId(graphTargetId)
                        : [graphTeamName, shortId(graphChannelId)].filter(Boolean).join(" / ")}
                  </small>
                </div>
                <StatusBadge label={graphTargetKind === "user" ? "One-on-one" : graphTargetKind === "chat" ? "Chat" : "Channel"} tone="success" />
              </div>
            ) : null}
            {graphSearchError ? <p className="form-error">{graphSearchError}</p> : null}
            {graphTargetKind === "channel" ? (
              <>
                <Field label="Find team" hint="App-only Graph lookup is used for team and channel search.">
                  <div className="webhook-lookup-field">
                    <input value={graphTeamSearch} placeholder="Search Teams" onChange={(event) => setGraphTeamSearch(event.target.value)} />
                    <button className="secondary-button secondary-button--small button-with-icon" type="button" onClick={() => void searchGraphTeams()} disabled={graphTeamsLoading || graphTeamSearch.trim().length < 2 || !featurePolicy.graphLookupEnabled}>
                      <Search aria-hidden="true" className="button-icon" focusable="false" />
                      {graphTeamsLoading ? "Searching..." : "Search team"}
                    </button>
                  </div>
                </Field>
                {graphTeams.length ? (
                  <div className="compact-conversation-list">
                    {graphTeams.map((target) => (
                      <button key={target.id} type="button" onClick={() => applyGraphTeam(target)} aria-pressed={(target.team_id || target.id) === graphTeamId}>
                        <span className="compact-conversation-list-copy">
                          <strong>{target.display_name}</strong>
                          <small>{target.subtitle || target.id}</small>
                        </span>
                        {(target.team_id || target.id) === graphTeamId ? <StatusBadge label="Team" tone="success" /> : null}
                      </button>
                    ))}
                  </div>
                ) : null}
                <Field label="Find channel" hint="Select a team first, then search its channels.">
                  <div className="webhook-lookup-field">
                    <input value={graphChannelSearch} placeholder="Search channels" onChange={(event) => setGraphChannelSearch(event.target.value)} disabled={!graphTeamId.trim()} />
                    <button className="secondary-button secondary-button--small button-with-icon" type="button" onClick={() => void searchGraphChannels()} disabled={graphChannelsLoading || !graphTeamId.trim() || !featurePolicy.graphLookupEnabled}>
                      <Search aria-hidden="true" className="button-icon" focusable="false" />
                      {graphChannelsLoading ? "Loading..." : "Find channels"}
                    </button>
                  </div>
                </Field>
                {graphChannels.length ? (
                  <div className="compact-conversation-list">
                    {graphChannels.map((target) => {
                      const channelId = target.channel_id || target.id;
                      return (
                        <button key={channelId} type="button" onClick={() => applyGraphChannel(target)} aria-pressed={channelId === graphChannelId}>
                          <span className="compact-conversation-list-copy">
                            <strong>{target.display_name}</strong>
                            <small>{target.subtitle || channelId}</small>
                          </span>
                          {channelId === graphChannelId ? <StatusBadge label="Selected" tone="success" /> : null}
                        </button>
                      );
                    })}
                  </div>
                ) : null}
              </>
            ) : null}
            {graphTargetKind === "chat" ? (
              <>
                <Field label="Find service-user chat" hint="Lists existing chats the connected service user belongs to.">
                  <div className="webhook-lookup-field">
                    <input value={graphChatSearch} placeholder="Search chat topic, type or ID" onChange={(event) => setGraphChatSearch(event.target.value)} />
                    <button className="secondary-button secondary-button--small button-with-icon" type="button" onClick={() => void searchGraphChats()} disabled={graphChatsLoading || !featurePolicy.graphLookupEnabled}>
                      <Search aria-hidden="true" className="button-icon" focusable="false" />
                      {graphChatsLoading ? "Searching..." : "Search chats"}
                    </button>
                  </div>
                </Field>
                {graphChats.length ? (
                  <div className="compact-conversation-list">
                    {graphChats.map((target) => (
                      <button key={target.id} type="button" onClick={() => applyGraphChat(target)} aria-pressed={target.id === graphTargetId}>
                        <span className="compact-conversation-list-copy">
                          <strong>{target.display_name}</strong>
                          <small>{target.subtitle || shortId(target.id)}</small>
                        </span>
                        {target.id === graphTargetId ? <StatusBadge label="Selected" tone="success" /> : null}
                      </button>
                    ))}
                  </div>
                ) : null}
              </>
            ) : null}
            {graphTargetKind === "user" ? (
              <>
                <Field label="Find user" hint="Select a Microsoft 365 user. The route will be linked to a one-on-one chat on save.">
                  <div className="webhook-lookup-field">
                    <input
                      value={graphUserSearch}
                      placeholder="Search name, email or UPN"
                      onChange={(event) => setGraphUserSearch(event.target.value)}
                    />
                    <button
                      className="secondary-button secondary-button--small button-with-icon"
                      type="button"
                      onClick={() => void searchGraphUsers()}
                      disabled={graphUsersLoading || graphUserSearch.trim().length < 2 || !featurePolicy.graphLookupEnabled}
                    >
                      <Search aria-hidden="true" className="button-icon" focusable="false" />
                      {graphUsersLoading ? "Searching..." : "Search users"}
                    </button>
                  </div>
                </Field>
                {graphUsers.length ? (
                  <div className="compact-conversation-list">
                    {graphUsers.map((target) => (
                      <button key={target.id} type="button" onClick={() => applyGraphUser(target)} aria-pressed={target.id === graphUserId}>
                        <span className="compact-conversation-list-copy">
                          <strong>{target.display_name}</strong>
                          <small>{target.subtitle || shortId(target.id)}</small>
                        </span>
                        {target.id === graphUserId ? <StatusBadge label="Selected" tone="success" /> : null}
                      </button>
                    ))}
                  </div>
                ) : null}
              </>
            ) : null}
          </div>
        ) : null}
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
                <p>
                  {deliveryBackend === "bot_framework"
                    ? "Use this only when you already have a valid Bot Framework service URL and conversation ID for the target conversation."
                    : "Use this when you already know the Graph channel, chat or user identifiers."}
                </p>
              </div>
              <StatusBadge label="Manual fallback" tone="warn" />
            </div>
            <Field label="Teams target name" hint="A human-readable label shown in the route table.">
              <input value={targetName} required maxLength={200} onChange={(event) => setTargetName(event.target.value)} />
            </Field>
            {deliveryBackend === "bot_framework" ? (
              <>
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
              </>
            ) : (
              <>
                <Field label="Graph target kind">
                  <select value={graphTargetKind || "channel"} onChange={(event) => selectGraphTargetKind(event.target.value as GraphTargetKind)}>
                    <option value="channel">Channel</option>
                    <option value="chat">Existing chat</option>
                    <option value="user">One-on-one user</option>
                  </select>
                </Field>
                <Field label={graphTargetKind === "chat" ? "Chat ID" : graphTargetKind === "user" ? "User ID or UPN" : "Graph target ID"}>
                  <textarea value={graphTargetId} required={graphTargetKind === "chat" || graphTargetKind === "user"} onChange={(event) => setGraphTargetId(event.target.value)} />
                </Field>
                {graphTargetKind === "channel" ? (
                  <>
                    <Field label="Team ID">
                      <textarea value={graphTeamId} required onChange={(event) => setGraphTeamId(event.target.value)} />
                    </Field>
                    <Field label="Team name">
                      <input value={graphTeamName} maxLength={200} onChange={(event) => setGraphTeamName(event.target.value)} />
                    </Field>
                    <Field label="Channel ID">
                      <textarea value={graphChannelId} required onChange={(event) => setGraphChannelId(event.target.value)} />
                    </Field>
                  </>
                ) : null}
              </>
            )}
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
            disabled={busy || Boolean(createdWebhookUrl) || !routeTargetReady}
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
  const refreshSequence = useRef(0);
  const selectedEvent = useMemo(
    () => events.find((event) => event.id === selectedEventId) ?? events[0] ?? null,
    [events, selectedEventId],
  );

  const refresh = useCallback(async () => {
    const requestId = refreshSequence.current + 1;
    refreshSequence.current = requestId;
    setLoading(true);
    setError("");
    try {
      const rows = await api.webhookRouteDeliveries(route.id, statusFilter === "all" ? undefined : statusFilter);
      if (refreshSequence.current !== requestId) return;
      setEvents(rows);
      setSelectedEventId(rows[0]?.id ?? "");
    } catch (err) {
      if (refreshSequence.current !== requestId) return;
      setError(isApiError(err) ? err.message : "Delivery logs could not be loaded.");
    } finally {
      if (refreshSequence.current === requestId) setLoading(false);
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
          columns={["Status", "Time", "Message", "Payload", "Backend", "Mode", "Error"]}
          rows={events.map((event) => [
            <DeliveryEventStatusBadge status={event.status} />,
            formatDateTime(event.created_at),
            <span>{eventTitle(event)}</span>,
            <span className="muted">{eventPayloadType(event)}</span>,
            <span className="muted">{eventDeliveryBackend(event)}</span>,
            <span className="muted">{eventDeliveryMode(event)}</span>,
            eventErrorMessage(event) ? <span className="form-error">{eventErrorMessage(event)}</span> : <span className="muted">-</span>,
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
  if (status === "pending") return <StatusBadge label="Pending" tone="neutral" />;
  return <StatusBadge label="Rejected" tone="warn" />;
}

function DeliveryEventDetails({ event }: { event: WebhookDeliveryEventOut & Partial<WebhookDeliveryEventDetailOut> }) {
  const requestMetadata = event.request_metadata;
  const deliveryResult = event.delivery_result;
  const errorMessage = eventErrorMessage(event);
  const graphResponseMessage = stringField(deliveryResult, "graph_error_message");
  const clientHostSource = stringField(requestMetadata, "client_host_source");
  const directClientHost = stringField(requestMetadata, "direct_client_host");
  const xForwardedFor = stringField(requestMetadata, "x_forwarded_for");
  const hasForwardedHeader = xForwardedFor !== "-";
  const usesForwardedHeader = clientHostSource === "x_forwarded_for";
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
        <dt>Backend</dt>
        <dd>{eventDeliveryBackend(event)}</dd>
        <dt>Mode</dt>
        <dd>{stringField(deliveryResult, "mode")}</dd>
        <dt>Status code</dt>
        <dd>{primitiveField(deliveryResult, "status_code")}</dd>
        <dt>Activity ID</dt>
        <dd>{stringField(deliveryResult, "activity_id")}</dd>
      </dl>

      {errorMessage ? (
        <section className="detail-section">
          <h4>Error</h4>
          <p className="form-error">{errorMessage}</p>
          {graphResponseMessage !== "-" && graphResponseMessage !== errorMessage ? (
            <p className="muted">Graph response: {graphResponseMessage}</p>
          ) : null}
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
          <dt>Client IP</dt>
          <dd>{stringField(requestMetadata, "client_host")}</dd>
          <dt>IP source</dt>
          <dd>{usesForwardedHeader ? "Forwarded header" : "Direct connection"}</dd>
          {usesForwardedHeader ? (
            <>
              <dt>Proxy peer</dt>
              <dd>{directClientHost}</dd>
            </>
          ) : hasForwardedHeader ? (
            <>
              <dt>Forwarded header</dt>
              <dd>{xForwardedFor} (not trusted)</dd>
            </>
          ) : null}
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

function eventErrorMessage(event: WebhookDeliveryEventOut): string {
  const operatorMessage = event.delivery_result.operator_message;
  if (typeof operatorMessage === "string" && operatorMessage.trim()) return operatorMessage;
  return event.error;
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

function eventDeliveryBackend(event: WebhookDeliveryEventOut): string {
  const backend = event.delivery_result.backend;
  return typeof backend === "string" && backend.trim() ? deliveryBackendLabel(backend) : "-";
}

function deliverySummaryMode(event: WebhookDeliveryEventSummaryOut): string {
  const mode = event.delivery_mode || "-";
  return typeof event.status_code === "number" ? `${mode} / ${event.status_code}` : mode;
}

function deliverySummaryBackend(event: WebhookDeliveryEventSummaryOut): string {
  return event.delivery_backend ? deliveryBackendLabel(event.delivery_backend) : "-";
}

function deliverySummaryErrorMessage(event: WebhookDeliveryEventSummaryOut): string {
  return event.error;
}

function deliveryBackendLabel(backend: string): string {
  if (backend === "bot_framework") return "Bot Framework";
  if (backend === "graph") return "Microsoft Graph";
  return backend || "-";
}

function UsersPage() {
  const { notify, refreshSession, session } = useAppContext();
  const [users, setUsers] = useState<UserOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserOut | null>(null);
  const [passwordUser, setPasswordUser] = useState<UserOut | null>(null);
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";
  const currentUserId = session.status === "authenticated" ? session.user.id : "";

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
        actions={
          <button className="primary-button button-with-icon" type="button" onClick={() => setCreateOpen(true)}>
            <Plus aria-hidden="true" className="button-icon" focusable="false" />
            <span>Create user</span>
          </button>
        }
      />
      <Card>
        <DataTable
          columns={["Name", "Email", "Role", "Status", "Created", "Actions"]}
          rows={users.map((user) => [
            <span className="user-name-cell">
              <strong>{user.display_name}</strong>
              {user.id === currentUserId ? <StatusBadge label="You" /> : null}
            </span>,
            user.email,
            user.is_admin ? <StatusBadge label="Admin" tone="success" /> : <StatusBadge label="Member" />,
            user.is_active ? <StatusBadge label="Active" tone="success" /> : <StatusBadge label="Disabled" tone="danger" />,
            formatDateTime(user.created_at),
            <RowActionMenu
              label={`Actions for ${user.display_name}`}
              items={[
                { label: "Edit user", icon: Pencil, onClick: () => setEditingUser(user) },
                { label: "Set password", icon: RotateCcwKey, onClick: () => setPasswordUser(user) },
              ]}
            />,
          ])}
          emptyTitle="No users"
          emptyBody="Users appear here after bootstrap or creation."
          loading={loading}
          loadingLabel="Loading users..."
          error={error}
          onRetry={() => void refresh()}
          rowKey={(index) => users[index]?.id ?? index}
        />
      </Card>
      {createOpen ? (
        <UserCreateModal
          csrfToken={csrfToken}
          onClose={() => setCreateOpen(false)}
          onSaved={() => {
            setCreateOpen(false);
            notify({ tone: "success", title: "User created" });
            void refresh();
          }}
        />
      ) : null}
      {editingUser ? (
        <UserEditModal
          csrfToken={csrfToken}
          currentUserId={currentUserId}
          user={editingUser}
          onClose={() => setEditingUser(null)}
          onSaved={(updatedUser) => {
            setEditingUser(null);
            notify({ tone: "success", title: "User updated" });
            void refresh();
            if (updatedUser.id === currentUserId) void refreshSession();
          }}
        />
      ) : null}
      {passwordUser ? (
        <UserPasswordModal
          csrfToken={csrfToken}
          currentUserId={currentUserId}
          user={passwordUser}
          onClose={() => setPasswordUser(null)}
          onSaved={(updatedUser) => {
            setPasswordUser(null);
            notify({ tone: "success", title: "Password updated" });
            void refresh();
            if (updatedUser.id === currentUserId) void refreshSession();
          }}
        />
      ) : null}
    </>
  );
}

function UserCreateModal({
  csrfToken,
  onClose,
  onSaved,
}: {
  csrfToken: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(true);
  const [isActive, setIsActive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.createAdminUser(csrfToken, {
        email,
        display_name: displayName,
        password,
        is_admin: isAdmin,
        is_active: isActive,
      });
      onSaved();
    } catch (err) {
      setError(isApiError(err) ? err.message : "User could not be created.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Create user" onClose={onClose}>
      <form className="user-form" onSubmit={(event) => void submit(event)}>
        <Field label="Display name">
          <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} required maxLength={255} autoFocus />
        </Field>
        <Field label="Email">
          <input value={email} onChange={(event) => setEmail(event.target.value)} required maxLength={255} type="email" autoComplete="email" />
        </Field>
        <Field label="Password">
          <input value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} maxLength={200} type="password" autoComplete="new-password" />
        </Field>
        <UserToggleRow label="Admin access" checked={isAdmin} onChange={setIsAdmin} />
        <UserToggleRow label="Active" checked={isActive} onChange={setIsActive} />
        {error ? <p className="form-error">{error}</p> : null}
        <div className="form-actions">
          <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="primary-button" type="submit" disabled={busy}>
            {busy ? "Creating..." : "Create user"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function UserEditModal({
  csrfToken,
  currentUserId,
  user,
  onClose,
  onSaved,
}: {
  csrfToken: string;
  currentUserId: string;
  user: UserOut;
  onClose: () => void;
  onSaved: (user: UserOut) => void;
}) {
  const [email, setEmail] = useState(user.email);
  const [displayName, setDisplayName] = useState(user.display_name);
  const [isAdmin, setIsAdmin] = useState(user.is_admin);
  const [isActive, setIsActive] = useState(user.is_active);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isCurrentUser = user.id === currentUserId;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const updatedUser = await api.updateAdminUser(csrfToken, user.id, {
        email,
        display_name: displayName,
        is_admin: isAdmin,
        is_active: isActive,
      });
      onSaved(updatedUser);
    } catch (err) {
      setError(isApiError(err) ? err.message : "User could not be updated.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Edit user" description={user.email} onClose={onClose}>
      <form className="user-form" onSubmit={(event) => void submit(event)}>
        <Field label="Display name">
          <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} required maxLength={255} autoFocus />
        </Field>
        <Field label="Email">
          <input value={email} onChange={(event) => setEmail(event.target.value)} required maxLength={255} type="email" autoComplete="email" />
        </Field>
        <UserToggleRow label="Admin access" checked={isAdmin} disabled={isCurrentUser} onChange={setIsAdmin} />
        <UserToggleRow label="Active" checked={isActive} disabled={isCurrentUser} onChange={setIsActive} />
        {error ? <p className="form-error">{error}</p> : null}
        <div className="form-actions">
          <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="primary-button" type="submit" disabled={busy}>
            {busy ? "Saving..." : "Save changes"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function UserPasswordModal({
  csrfToken,
  currentUserId,
  user,
  onClose,
  onSaved,
}: {
  csrfToken: string;
  currentUserId: string;
  user: UserOut;
  onClose: () => void;
  onSaved: (user: UserOut) => void;
}) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isCurrentUser = user.id === currentUserId;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const updatedUser = await api.updateAdminUserPassword(csrfToken, user.id, { password });
      onSaved(updatedUser);
    } catch (err) {
      setError(isApiError(err) ? err.message : "Password could not be updated.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Set password" description={isCurrentUser ? "Your current session stays active." : user.email} onClose={onClose}>
      <form className="user-form" onSubmit={(event) => void submit(event)}>
        <Field label="New password">
          <input value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} maxLength={200} type="password" autoComplete="new-password" autoFocus />
        </Field>
        {error ? <p className="form-error">{error}</p> : null}
        <div className="form-actions">
          <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="primary-button" type="submit" disabled={busy}>
            {busy ? "Saving..." : "Set password"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function UserToggleRow({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="user-toggle-row">
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

type SettingSection = "delivery" | "runtime" | "advancedIdentity";
type SettingDisplay = "switch" | "segmented" | "number" | "technical" | "secret";

type SettingMeta = {
  section: SettingSection;
  label?: string;
  description?: string;
  help?: string;
  unit?: string;
  display: SettingDisplay;
  sourceLabel?: string;
};

const SETTING_META: Record<string, SettingMeta> = {
  bot_framework_enabled: {
    section: "delivery",
    label: "Bot Framework",
    description: "Route messages through captured Teams conversations.",
    display: "switch",
    sourceLabel: "App",
  },
  graph_lookup_enabled: {
    section: "delivery",
    label: "Graph lookup",
    description: "Resolve Teams users, chats and channels from Microsoft Graph.",
    display: "switch",
    sourceLabel: "App",
  },
  graph_delivery_enabled: {
    section: "delivery",
    label: "Graph delivery",
    description: "Send delegated Teams messages through the connected service user.",
    help: "Requires Graph lookup to stay enabled.",
    display: "switch",
    sourceLabel: "App",
  },
  bot_default_service_url: {
    section: "runtime",
    label: "Default service URL",
    description: "Fallback Bot Framework endpoint for routes without a captured URL.",
    display: "technical",
    sourceLabel: "Bot Framework",
  },
  webhook_max_payload_bytes: {
    section: "runtime",
    label: "Payload limit",
    description: "Maximum accepted webhook body size.",
    unit: "bytes",
    display: "number",
  },
  webhook_abuse_blocking_enabled: {
    section: "runtime",
    label: "Abuse blocking",
    description: "Temporarily block clients after repeated failed webhook attempts.",
    display: "switch",
  },
  webhook_abuse_failure_limit: {
    section: "runtime",
    label: "Failure limit",
    description: "Failed attempts allowed inside the abuse window.",
    unit: "failures",
    display: "number",
  },
  webhook_abuse_window_minutes: {
    section: "runtime",
    label: "Abuse window",
    description: "Rolling window used for webhook failure counting.",
    unit: "minutes",
    display: "number",
  },
  log_retention_days: {
    section: "runtime",
    label: "Log retention",
    description: "How long delivery, audit and bot events are kept.",
    unit: "days",
    display: "number",
  },
  log_cleanup_interval_minutes: {
    section: "runtime",
    label: "Cleanup cadence",
    description: "Minimum time between automatic cleanup runs.",
    unit: "minutes",
    display: "number",
  },
  trust_x_forwarded_for: {
    section: "runtime",
    label: "Trust X-Forwarded-For",
    description: "Use forwarded client IPs only when the direct peer is trusted.",
    display: "switch",
  },
  session_secure_cookie: {
    section: "runtime",
    label: "Secure session cookie",
    description: "Require HTTPS before browsers send the session cookie.",
    display: "switch",
  },
  cors_origins: {
    section: "runtime",
    label: "CORS origins",
    description: "Comma-separated browser origins allowed to send authenticated requests.",
    display: "technical",
  },
  app_public_base_url: {
    section: "runtime",
    label: "Public URL",
    description: "Base URL used to build relay webhook links.",
    display: "technical",
  },
  frontend_base_url: {
    section: "runtime",
    label: "Frontend URL",
    description: "Base URL used in generated operator links.",
    display: "technical",
  },
  ms_app_tenant_id: {
    section: "advancedIdentity",
    label: "Tenant ID",
    description: "Directory ID for the Entra app registration.",
    display: "technical",
  },
  ms_app_client_id: {
    section: "advancedIdentity",
    label: "Client ID",
    description: "Application ID for the Entra app registration.",
    display: "technical",
  },
  ms_app_client_secret: {
    section: "advancedIdentity",
    label: "Client secret",
    description: "Used for Bot Framework delivery and Graph lookup.",
    display: "secret",
  },
  botframework_scope: {
    section: "advancedIdentity",
    label: "Bot Framework scope",
    description: "OAuth scope requested for Bot Framework tokens.",
    display: "technical",
  },
  graph_scope: {
    section: "advancedIdentity",
    label: "Graph scope",
    description: "OAuth scope requested for Microsoft Graph tokens.",
    display: "technical",
  },
};

const DELIVERY_SETTING_KEYS = [
  "bot_framework_enabled",
  "graph_lookup_enabled",
  "graph_delivery_enabled",
] as const;

const RUNTIME_SETTING_KEYS = [
  "app_public_base_url",
  "frontend_base_url",
  "cors_origins",
  "session_secure_cookie",
  "bot_default_service_url",
  "webhook_max_payload_bytes",
  "webhook_abuse_blocking_enabled",
  "webhook_abuse_failure_limit",
  "webhook_abuse_window_minutes",
  "log_retention_days",
  "log_cleanup_interval_minutes",
  "trust_x_forwarded_for",
] as const;

const ABUSE_SETTING_KEYS = [
  "webhook_abuse_blocking_enabled",
  "webhook_abuse_failure_limit",
  "webhook_abuse_window_minutes",
] as const;

const ADVANCED_IDENTITY_SETTING_KEYS = [
  "ms_app_tenant_id",
  "ms_app_client_id",
  "ms_app_client_secret",
  "botframework_scope",
  "graph_scope",
] as const;

function StatusPage() {
  const { notify, session } = useAppContext();
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
      setError(isApiError(err) ? err.message : "Status data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [csrfToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function copyDiagnosticValue(value: string, label: string) {
    await navigator.clipboard.writeText(value);
    notify({ tone: "success", title: `${label} copied` });
  }

  return (
    <>
      <PageIntro
        eyebrow="System"
        title="Status"
        description="General runtime information for the application. Delivery operations now live on the Delivery page."
        actions={readiness ? <StatusBadge label={readiness.app_version} tone="neutral" /> : null}
      />
      {loading ? (
        <Card>
          <div className="table-state" role="status" aria-live="polite">
            <div className="spinner spinner--small" aria-hidden="true" />
            <p>Loading status...</p>
          </div>
        </Card>
      ) : error ? (
        <Card>
          <div className="table-state table-state--error" role="alert">
            <h3>Could not load status</h3>
            <p>{error}</p>
            <button className="secondary-button secondary-button--small" type="button" onClick={() => void refresh()}>
              Retry
            </button>
          </div>
        </Card>
      ) : readiness ? (
        <div className="status-command-center">
          <section className="status-overview" aria-label="System overview">
            <StatusOverviewMetric label="Application" value={readiness.app_name} detail={`Version ${readiness.app_version}`} />
            <StatusOverviewMetric
              label="Settings"
              value={settingsEncryptionLabel(readiness.runtime.settings_encryption_key_source, readiness.runtime.settings_encryption_ready)}
              detail="Encryption state for stored runtime settings."
              tone={readiness.runtime.settings_encryption_ready ? "success" : "warn"}
            />
            <StatusOverviewMetric label="Payload limit" value={formatBytes(readiness.runtime.webhook_max_payload_bytes)} detail="Maximum accepted webhook request body." />
            <StatusOverviewMetric label="Retention" value={`${readiness.runtime.log_retention_days} days`} detail="Event and audit data retention window." />
          </section>
          <section className="status-operations-grid" aria-label="Operational context">
            <RuntimeSnapshotCard readiness={readiness} onCopy={copyDiagnosticValue} />
          </section>
        </div>
      ) : null}
    </>
  );
}

function deliveryAuthRefreshToastTone(result: DeliveryAuthRefreshOut): "success" | "info" {
  return deliveryAuthRefreshComponents(result).some((component) => component.status === "skipped") ? "info" : "success";
}

function deliveryAuthRefreshToastDescription(result: DeliveryAuthRefreshOut): string {
  const components = deliveryAuthRefreshComponents(result);
  const failed = components.filter((component) => component.status === "failed");
  if (failed.length) {
    return failed.map((component) => `${component.label}: ${component.message}`).join(" ");
  }
  const refreshed = components.filter((component) => component.status === "refreshed").length;
  const cleared = components.filter((component) => component.status === "cleared").length;
  const skipped = components.filter((component) => component.status === "skipped").length;
  const parts = [
    refreshed ? `${refreshed} refreshed` : "",
    cleared ? `${cleared} cache${cleared === 1 ? "" : "s"} cleared` : "",
    skipped ? `${skipped} skipped` : "",
  ].filter(Boolean);
  return parts.join(", ") || "Delivery authentication state was checked.";
}

function deliveryAuthRefreshComponents(result: DeliveryAuthRefreshOut) {
  return [
    { label: "Bot delivery", ...result.bot_delivery },
    { label: "Graph lookup", ...result.graph_lookup },
    { label: "Graph delivery", ...result.graph_delivery },
    { label: "Bot inbound auth", ...result.bot_inbound_auth },
  ];
}

function DeliveryMethodsPage() {
  const { notify, session } = useAppContext();
  const [readiness, setReadiness] = useState<AdminReadinessOut | null>(null);
  const [settings, setSettings] = useState<SettingItemOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [graphOAuthBusy, setGraphOAuthBusy] = useState(false);
  const [authRefreshBusy, setAuthRefreshBusy] = useState(false);
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextReadiness, nextSettings] = await Promise.all([api.adminReadiness(csrfToken), api.adminSettings(csrfToken)]);
      setReadiness(nextReadiness);
      setSettings(nextSettings);
    } catch (err) {
      setError(isApiError(err) ? err.message : "Delivery data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [csrfToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function copyDiagnosticValue(value: string, label: string) {
    await navigator.clipboard.writeText(value);
    notify({ tone: "success", title: `${label} copied` });
  }

  async function connectGraphDelivery() {
    setGraphOAuthBusy(true);
    setError("");
    try {
      const result = await api.startGraphDeliveryOAuth(csrfToken);
      window.location.href = result.authorization_url;
    } catch (err) {
      setError(isApiError(err) ? err.message : "Graph delivery connection could not be started.");
      setGraphOAuthBusy(false);
    }
  }

  async function disconnectGraphDelivery() {
    setGraphOAuthBusy(true);
    setError("");
    try {
      await api.disconnectGraphDeliveryOAuth(csrfToken);
      notify({ tone: "success", title: "Graph delivery disconnected" });
      await refresh();
    } catch (err) {
      setError(isApiError(err) ? err.message : "Graph delivery connection could not be removed.");
    } finally {
      setGraphOAuthBusy(false);
    }
  }

  async function refreshDeliveryAuth() {
    setAuthRefreshBusy(true);
    setError("");
    try {
      const result = await api.refreshDeliveryAuth(csrfToken);
      setReadiness(result.readiness);
      notify({
        tone: result.ok ? deliveryAuthRefreshToastTone(result) : "error",
        title: result.ok ? "Auth tokens refreshed" : "Auth refresh needs attention",
        description: deliveryAuthRefreshToastDescription(result),
      });
    } catch (err) {
      setError(isApiError(err) ? err.message : "Delivery auth tokens could not be refreshed.");
    } finally {
      setAuthRefreshBusy(false);
    }
  }

  const settingsByKey = useMemo(() => new Map(settings.map((item) => [item.key, item])), [settings]);
  const deliverySettings = orderedSettings(DELIVERY_SETTING_KEYS, settingsByKey);
  const enabledCount = deliverySettings.filter((item) => item.effective_value === "true").length;
  const deliveryMethodCount = deliverySettings.length || DELIVERY_SETTING_KEYS.length;
  const graphLookupEnabled = settingEnabled(settingsByKey, "graph_lookup_enabled");
  const integrationViews = readiness
    ? [
        buildBotIntegrationView(readiness, copyDiagnosticValue),
        buildGraphLookupIntegrationView(readiness, copyDiagnosticValue),
        buildGraphDeliveryIntegrationView(readiness.graph_delivery, graphOAuthBusy, () => void connectGraphDelivery(), () => void disconnectGraphDelivery(), copyDiagnosticValue),
      ]
    : [];
  const overallTone = integrationViews.some((view) => view.tone === "danger") ? "danger" : integrationViews.some((view) => view.tone === "warn") ? "warn" : "success";
  const overallLabel = overallTone === "danger" ? "Degraded" : overallTone === "warn" ? "Attention" : "Ready";

  return (
    <>
      <PageIntro
        eyebrow="Operations"
        title="Delivery"
        description="Operate the complete delivery pipeline from one place."
        actions={
          readiness ? (
            <div className="row-actions">
              <StatusBadge label={overallLabel} tone={overallTone} />
              <button
                className="secondary-button secondary-button--small button-with-icon"
                type="button"
                onClick={() => void refreshDeliveryAuth()}
                disabled={authRefreshBusy}
                aria-busy={authRefreshBusy}
              >
                <RefreshCw aria-hidden="true" className={classNames("button-icon", authRefreshBusy && "button-icon--spin")} focusable="false" />
                {authRefreshBusy ? "Refreshing..." : "Refresh auth tokens"}
              </button>
            </div>
          ) : null
        }
      />
      {loading ? (
        <Card>
          <div className="table-state" role="status" aria-live="polite">
            <div className="spinner spinner--small" aria-hidden="true" />
            <p>Loading delivery operations...</p>
          </div>
        </Card>
      ) : error ? (
        <Card>
          <div className="table-state table-state--error" role="alert">
            <h3>Could not load delivery operations</h3>
            <p>{error}</p>
            <button className="secondary-button secondary-button--small" type="button" onClick={() => void refresh()}>
              Retry
            </button>
          </div>
        </Card>
      ) : readiness ? (
        <div className="delivery-page delivery-operations-page">
          <RelayHealthHero
            deliveryMethodCount={deliveryMethodCount}
            enabledCount={enabledCount}
            integrations={integrationViews}
            overallLabel={overallLabel}
            overallTone={overallTone}
            readiness={readiness}
          />
          <section className="delivery-component-grid" aria-label="Delivery methods">
            {integrationViews.map((integration) => (
              <DeliveryComponentCard
                key={integration.id}
                csrfToken={csrfToken}
                graphLookupEnabled={graphLookupEnabled}
                integration={integration}
                item={settingsByKey.get(deliverySettingKeyForIntegration(integration.id))}
                notify={notify}
                onChanged={refresh}
              />
            ))}
          </section>
          <section className="status-operations-grid" aria-label="Runtime context">
            <RuntimeSnapshotCard readiness={readiness} onCopy={copyDiagnosticValue} />
          </section>
        </div>
      ) : null}
    </>
  );
}

function deliverySettingKeyForIntegration(integrationId: string): (typeof DELIVERY_SETTING_KEYS)[number] {
  if (integrationId === "graph-lookup") return "graph_lookup_enabled";
  if (integrationId === "graph-delivery") return "graph_delivery_enabled";
  return "bot_framework_enabled";
}

function DeliveryComponentCard({
  csrfToken,
  graphLookupEnabled,
  item,
  integration,
  notify,
  onChanged,
}: {
  csrfToken: string;
  graphLookupEnabled: boolean;
  item?: SettingItemOut;
  integration: IntegrationStatusView;
  notify: SettingsNotify;
  onChanged: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [detailView, setDetailView] = useState<DeliveryDetailView | null>(null);
  const inputId = useId();
  const enabled = item?.effective_value === "true";
  const graphDeliveryBlocked = item?.key === "graph_delivery_enabled" && !enabled && !graphLookupEnabled;
  const readyChecks = integration.healthChecks.filter((check) => check.tone === "success").length;
  const tokenFactValue = integration.facts.find((fact) => fact.label === "Token");
  const actionItem = integration.attentionItems[0];
  const checksTone = readyChecks === integration.healthChecks.length ? "success" : readyChecks > 0 ? "warn" : "danger";
  const tokenTooltip = `Token ${tokenFactValue?.value ?? "Unknown"}`;

  async function toggle(nextEnabled: boolean) {
    if (!item) return;
    setBusy(true);
    setError("");
    try {
      await api.updateSetting(csrfToken, item.key, nextEnabled ? "true" : "false");
      notify({ tone: "success", title: `${item.label} ${nextEnabled ? "enabled" : "disabled"}` });
      await onChanged();
    } catch (err) {
      setError(isApiError(err) ? err.message : "Delivery method could not be updated.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Card className={classNames("delivery-component-card", `delivery-component-card--${integration.tone}`)}>
        <div className="delivery-component-header">
          <div className="delivery-component-title">
            <DeliveryMethodIcon integrationId={integration.id} />
            <span>
              <h2>{integration.title}</h2>
              <p>{integration.description}</p>
            </span>
          </div>
          <div className="delivery-component-kpis" aria-label={`${integration.title} summary`}>
            <DeliveryStatusGroup integration={integration} overridden={Boolean(item?.source === "environment" && item.is_overridden)} tokenLabel={tokenTooltip} />
            {item ? (
              <label className="settings-switch delivery-method-switch" htmlFor={inputId}>
                <input
                  id={inputId}
                  type="checkbox"
                  checked={enabled}
                  disabled={busy || graphDeliveryBlocked}
                  onChange={(event) => void toggle(event.target.checked)}
                  aria-describedby={error ? `${inputId}-error` : undefined}
                />
                <span aria-hidden="true" />
                <strong>{busy ? "Saving..." : enabled ? "Enabled" : "Disabled"}</strong>
              </label>
            ) : null}
            {integration.manageActionSlot ? <div className="delivery-manage-action">{integration.manageActionSlot}</div> : null}
          </div>
          <div className="delivery-detail-hub" aria-label={`${integration.title} details`}>
            <button
              type="button"
              className={classNames("delivery-detail-button", `delivery-detail-button--${checksTone}`)}
              aria-label={`Open ${integration.title} readiness checks, ${readyChecks} of ${integration.healthChecks.length} passing`}
              onClick={() => setDetailView("readiness")}
            >
              <Check aria-hidden="true" className="button-icon" focusable="false" />
              <span>Checks</span>
              <strong>{readyChecks}/{integration.healthChecks.length}</strong>
            </button>
            <button type="button" className="delivery-detail-button" aria-label={`Open ${integration.title} configuration`} onClick={() => setDetailView("configuration")}>
              <Wrench aria-hidden="true" className="button-icon" focusable="false" />
              <span>Config</span>
              <strong>{integration.credentials.filter(([, value]) => value === "Configured" || value === "Inherited").length}/{integration.credentials.length}</strong>
            </button>
            <button type="button" className="delivery-detail-button" aria-label={`Open ${integration.title} diagnostics`} onClick={() => setDetailView("diagnostics")}>
              <Activity aria-hidden="true" className="button-icon" focusable="false" />
              <span>Diagnostics</span>
            </button>
            <button type="button" className="delivery-detail-button" aria-label={`Open ${integration.title} technical information`} onClick={() => setDetailView("technical")}>
              <Info aria-hidden="true" className="button-icon" focusable="false" />
              <span>Technical</span>
            </button>
          </div>
        </div>

        {actionItem || graphDeliveryBlocked || error ? (
          <div className="delivery-inline-issues">
            {actionItem ? (
              <div className={classNames("delivery-inline-issue", `delivery-inline-issue--${actionItem.tone}`)}>
                <strong>{actionItem.title}</strong>
                <span>{actionItem.description}</span>
              </div>
            ) : null}
            {actionItem && integration.primaryActionSlot ? <div className="delivery-inline-action">{integration.primaryActionSlot}</div> : null}
            {graphDeliveryBlocked ? <p className="settings-warning">Enable Graph lookup first.</p> : null}
            {error ? (
              <p className="form-error" id={`${inputId}-error`}>
                {error}
              </p>
            ) : null}
          </div>
        ) : null}

      </Card>
      {detailView ? <DeliveryDetailModal integration={integration} view={detailView} onClose={() => setDetailView(null)} /> : null}
    </>
  );
}

function DeliveryMethodIcon({ integrationId }: { integrationId: string }) {
  const Icon = integrationId === "graph-lookup" ? Search : integrationId === "graph-delivery" ? Send : Bot;
  return (
    <span className={classNames("delivery-method-icon", `delivery-method-icon--${integrationId}`)} aria-hidden="true">
      <Icon focusable="false" />
    </span>
  );
}

type DeliveryDetailView = "readiness" | "configuration" | "diagnostics" | "technical";

function DeliveryDetailModal({ integration, onClose, view }: { integration: IntegrationStatusView; onClose: () => void; view: DeliveryDetailView }) {
  const titleByView: Record<DeliveryDetailView, string> = {
    readiness: "Readiness Checks",
    configuration: "Configuration",
    diagnostics: "Diagnostics",
    technical: "Technical Information",
  };

  return (
    <Modal title={titleByView[view]} description={`${integration.title} · ${integration.statusLabel}`} onClose={onClose} panelClassName="delivery-inspector-modal">
      {view === "readiness" ? <DeliveryReadinessInspector integration={integration} /> : null}
      {view === "configuration" ? <DeliveryConfigurationInspector integration={integration} /> : null}
      {view === "diagnostics" ? <DeliveryDiagnosticsInspector integration={integration} /> : null}
      {view === "technical" ? <DeliveryTechnicalInspector integration={integration} /> : null}
      <div className="form-actions">
        <button className="secondary-button secondary-button--small" type="button" onClick={onClose}>
          Close
        </button>
      </div>
    </Modal>
  );
}

function DeliveryReadinessInspector({ integration }: { integration: IntegrationStatusView }) {
  return (
    <div className="delivery-inspector-body">
      <StatusCheckList checks={integration.healthChecks} />
    </div>
  );
}

function DeliveryConfigurationInspector({ integration }: { integration: IntegrationStatusView }) {
  return (
    <div className="delivery-inspector-body">
      <section className="delivery-inspector-section">
        <h3>Credentials</h3>
        <div className="credential-check-grid">
          {integration.credentials.map(([label, value]) => (
            <CredentialCheck key={label} label={label} value={value} />
          ))}
        </div>
      </section>
      <section className="delivery-inspector-section">
        <h3>Capabilities</h3>
        <StatusFactList facts={integration.capabilities} />
      </section>
    </div>
  );
}

function DeliveryDiagnosticsInspector({ integration }: { integration: IntegrationStatusView }) {
  return (
    <div className="delivery-inspector-body">
      <section className="delivery-inspector-section">
        <h3>Permissions</h3>
        <p>{integration.permissionSummary}</p>
        <div className="permission-badge-list">
          {integration.permissionBadges.map((badge) => (
            <span className={classNames("permission-badge", `permission-badge--${badge.tone}`)} key={badge.label}>
              {badge.label}
            </span>
          ))}
        </div>
      </section>
      <section className="delivery-inspector-section">
        <h3>Diagnostic output</h3>
        <dl className="definition-list definition-list--compact advanced-definition-list">
          {integration.diagnosticRows.map((row) => (
            <FragmentPair key={row.label} label={row.label} value={row.value} />
          ))}
        </dl>
      </section>
    </div>
  );
}

function DeliveryTechnicalInspector({ integration }: { integration: IntegrationStatusView }) {
  return (
    <div className="delivery-inspector-body">
      <dl className="definition-list definition-list--compact advanced-definition-list">
        {integration.technicalRows.map((row) => (
          <FragmentPair key={row.label} label={row.label} value={row.value} />
        ))}
      </dl>
    </div>
  );
}

function DeliveryStatusGroup({ integration, overridden, tokenLabel }: { integration: IntegrationStatusView; overridden: boolean; tokenLabel: string }) {
  return (
    <div
      className="delivery-status-group delivery-token-tooltip"
      aria-label={`${integration.title}: ${integration.statusLabel}${overridden ? ", Override active" : ""}. ${tokenLabel}`}
      data-tooltip={tokenLabel}
      tabIndex={0}
    >
      <span className={classNames("delivery-status-dot", `delivery-status-dot--${integration.tone}`)} aria-hidden="true" />
      <strong>{integration.statusLabel}</strong>
      {overridden ? (
        <>
          <span aria-hidden="true">·</span>
          <span>Override</span>
        </>
      ) : null}
    </div>
  );
}

function SettingsPage() {
  const { notify, session } = useAppContext();
  const [settings, setSettings] = useState<SettingItemOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [identityOpen, setIdentityOpen] = useState(false);
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setSettings(await api.adminSettings(csrfToken));
    } catch (err) {
      setError(isApiError(err) ? err.message : "Settings data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [csrfToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const settingsByKey = useMemo(() => new Map(settings.map((item) => [item.key, item])), [settings]);
  const overrideCount = settings.filter((item) => item.is_overridden).length;
  const runtimeSettings = orderedSettings(RUNTIME_SETTING_KEYS, settingsByKey);
  const identitySettings = orderedSettings(ADVANCED_IDENTITY_SETTING_KEYS, settingsByKey);
  const overrideBadge = overrideCount > 0 ? `${overrideCount} ${overrideCount === 1 ? "override" : "overrides"}` : "All defaults";

  return (
    <>
      <PageIntro
        eyebrow="Configuration"
        title="Settings"
        description="Manage runtime defaults and Microsoft identity values."
        actions={<StatusBadge label={overrideBadge} tone={overrideCount > 0 ? "warn" : "neutral"} />}
      />
      {loading ? (
        <Card>
          <div className="table-state" role="status" aria-live="polite">
            <div className="spinner spinner--small" aria-hidden="true" />
            <p>Loading settings...</p>
          </div>
        </Card>
      ) : error ? (
        <Card>
          <div className="table-state table-state--error" role="alert">
            <h3>Could not load settings</h3>
            <p>{error}</p>
            <button className="secondary-button secondary-button--small" type="button" onClick={() => void refresh()}>
              Retry
            </button>
          </div>
        </Card>
      ) : (
        <div className="settings-page">
          <SettingsOverviewStrip settingsByKey={settingsByKey} overrideCount={overrideCount} />
          <RuntimeDefaultsCard
            settings={runtimeSettings}
            settingsByKey={settingsByKey}
            csrfToken={csrfToken}
            onChanged={refresh}
            notify={notify}
          />
          <AdvancedIdentityCard
            settings={identitySettings}
            settingsByKey={settingsByKey}
            csrfToken={csrfToken}
            onChanged={refresh}
            notify={notify}
            open={identityOpen}
            onToggle={() => setIdentityOpen((value) => !value)}
          />
        </div>
      )}
    </>
  );
}

function orderedSettings(keys: readonly string[], settingsByKey: Map<string, SettingItemOut>) {
  return keys.map((key) => settingsByKey.get(key)).filter((item): item is SettingItemOut => Boolean(item));
}

function settingValue(settingsByKey: Map<string, SettingItemOut>, key: string) {
  return settingsByKey.get(key)?.effective_value ?? "";
}

function settingEnabled(settingsByKey: Map<string, SettingItemOut>, key: string) {
  return settingValue(settingsByKey, key) === "true";
}

function SettingsOverviewStrip({
  overrideCount,
  settingsByKey,
}: {
  overrideCount: number;
  settingsByKey: Map<string, SettingItemOut>;
}) {
  const tenantConfigured = Boolean(settingValue(settingsByKey, "ms_app_tenant_id"));
  const clientConfigured = Boolean(settingValue(settingsByKey, "ms_app_client_id"));
  const secretConfigured = settingValue(settingsByKey, "ms_app_client_secret") === "configured";
  const identityReady = tenantConfigured && clientConfigured && secretConfigured;
  const runtimeOverrideCount = RUNTIME_SETTING_KEYS.filter((key) => settingsByKey.get(key)?.is_overridden).length;

  return (
    <section className="settings-overview" aria-label="Runtime configuration overview">
      <OverviewMetric
        label="Source"
        value={overrideCount > 0 ? `${overrideCount} active` : "Environment"}
        detail={overrideCount > 0 ? "Runtime overrides are applied immediately." : "All values inherit from environment defaults."}
      />
      <OverviewMetric
        label="Runtime"
        value={runtimeOverrideCount > 0 ? `${runtimeOverrideCount} overrides` : "Defaults"}
        detail={runtimeOverrideCount > 0 ? "URL, retention or proxy values are overridden." : "Runtime values inherit from environment config."}
        tone={runtimeOverrideCount > 0 ? "warn" : "neutral"}
      />
      <OverviewMetric
        label="Identity"
        value={identityReady ? "Configured" : "Needs attention"}
        detail={identityReady ? "Tenant, client and secret are present." : "Check Microsoft Entra values."}
        tone={identityReady ? "success" : "warn"}
      />
    </section>
  );
}

function OverviewMetric({
  detail,
  label,
  tone = "neutral",
  value,
}: {
  detail: string;
  label: string;
  tone?: "neutral" | "success" | "warn";
  value: string;
}) {
  return (
    <div className={classNames("settings-overview-item", tone !== "neutral" && `settings-overview-item--${tone}`)}>
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </div>
  );
}

function RuntimeDefaultsCard({
  csrfToken,
  notify,
  onChanged,
  settings,
  settingsByKey,
}: SettingsCardProps) {
  const urlSettings = settings.filter((item) => item.type === "url" && item.key !== "bot_default_service_url");
  const browserSettings = settings.filter((item) => item.key === "cors_origins" || item.key === "session_secure_cookie");
  const limitSettings = settings.filter((item) => item.type === "int" && !item.key.startsWith("webhook_abuse_"));
  const abuseSettings = orderedSettings(ABUSE_SETTING_KEYS, settingsByKey);
  const fallbackSettings = settings.filter((item) => item.key === "bot_default_service_url");
  const proxySettings = settings.filter((item) => item.key === "trust_x_forwarded_for");

  return (
    <Card className="settings-card" title="Runtime defaults" description="Effective URLs, limits and retention used by relay operations.">
      <div className="settings-runtime-grid">
        <div className="settings-card-block">
          <div className="settings-card-block-header">
            <h3>URLs</h3>
            <p>Copied into generated links and fallback delivery paths.</p>
          </div>
          {[...urlSettings, ...browserSettings, ...fallbackSettings].map((item) => (
            <RuntimeSettingControl
              key={item.key}
              item={item}
              csrfToken={csrfToken}
              onChanged={onChanged}
              notify={notify}
              settingsByKey={settingsByKey}
            />
          ))}
        </div>
        <div className="settings-card-block">
          <div className="settings-card-block-header">
            <h3>Limits</h3>
            <p>Small operational values should be fast to scan and adjust.</p>
          </div>
          {limitSettings.map((item) => (
            <RuntimeSettingControl
              key={item.key}
              item={item}
              csrfToken={csrfToken}
              onChanged={onChanged}
              notify={notify}
              settingsByKey={settingsByKey}
              compact
            />
          ))}
        </div>
        <div className="settings-card-block">
          <div className="settings-card-block-header">
            <h3>Abuse blocking</h3>
            <p>Core controls for temporary webhook blocks. Advanced timings stay in environment config.</p>
          </div>
          {abuseSettings.map((item) => (
            <RuntimeSettingControl
              key={item.key}
              item={item}
              csrfToken={csrfToken}
              onChanged={onChanged}
              notify={notify}
              settingsByKey={settingsByKey}
              compact
            />
          ))}
        </div>
        <div className="settings-card-block">
          <div className="settings-card-block-header">
            <h3>Proxy logging</h3>
            <p>Controls how source IPs are recorded for incoming webhook logs.</p>
          </div>
          {proxySettings.map((item) => (
            <RuntimeSettingControl
              key={item.key}
              item={item}
              csrfToken={csrfToken}
              onChanged={onChanged}
              notify={notify}
              settingsByKey={settingsByKey}
              compact={item.type === "bool"}
            />
          ))}
        </div>
      </div>
    </Card>
  );
}

function AdvancedIdentityCard({
  csrfToken,
  notify,
  onChanged,
  onToggle,
  open,
  settings,
  settingsByKey,
}: SettingsCardProps & { open: boolean; onToggle: () => void }) {
  const overriddenCount = settings.filter((item) => item.is_overridden).length;
  const secret = settingsByKey.get("ms_app_client_secret");
  const secretReady = secret?.effective_value === "configured";

  return (
    <Card className="settings-card settings-card--identity">
      <div className="settings-disclosure">
        <button
          className="settings-disclosure-trigger"
          type="button"
          aria-expanded={open}
          aria-controls="advanced-identity-settings"
          onClick={onToggle}
        >
          <span>
            <span className="settings-disclosure-kicker">Advanced</span>
            <strong>Microsoft identity</strong>
            <small>Tenant, client secret and OAuth scopes for Bot Framework and Graph.</small>
          </span>
          <span className="settings-disclosure-badges">
            <StatusBadge label={secretReady ? "Secret configured" : "Secret missing"} tone={secretReady ? "success" : "warn"} />
            {overriddenCount > 0 ? <StatusBadge label={`${overriddenCount} overrides`} tone="warn" /> : <StatusBadge label="ENV" />}
            <ChevronDown aria-hidden="true" className="settings-disclosure-icon" focusable="false" />
          </span>
        </button>
        {open ? (
          <div className="settings-advanced-list" id="advanced-identity-settings">
            <p className="settings-advanced-intro">
              Microsoft Entra app registration used for Bot Framework and Graph. These values apply immediately after saving.
            </p>
            {settings.map((item) => (
              <RuntimeSettingControl
                key={item.key}
                item={item}
                csrfToken={csrfToken}
                onChanged={onChanged}
                notify={notify}
                settingsByKey={settingsByKey}
              />
            ))}
          </div>
        ) : null}
      </div>
    </Card>
  );
}

type SettingsNotify = ReturnType<typeof useAppContext>["notify"];

type SettingsCardProps = {
  settings: SettingItemOut[];
  settingsByKey: Map<string, SettingItemOut>;
  csrfToken: string;
  onChanged: () => Promise<void>;
  notify: SettingsNotify;
};

function RuntimeSettingControl({
  compact = false,
  item,
  csrfToken,
  onChanged,
  notify,
  settingsByKey,
}: {
  item: SettingItemOut;
  csrfToken: string;
  onChanged: () => Promise<void>;
  notify: SettingsNotify;
  settingsByKey: Map<string, SettingItemOut>;
  compact?: boolean;
}) {
  const initialDraft = item.type === "secret" ? "" : item.effective_value;
  const [draft, setDraft] = useState(initialDraft);
  const [busy, setBusy] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [secretVisible, setSecretVisible] = useState(false);
  const [error, setError] = useState("");
  const inputId = useId();
  const errorId = `${inputId}-error`;

  useEffect(() => {
    setDraft(item.type === "secret" ? "" : item.effective_value);
    setSecretVisible(false);
    setError("");
  }, [item.key, item.effective_value, item.type]);

  const canSave =
    item.type === "secret" ? draft.trim().length > 0 : draft !== item.effective_value || (draft === "" && item.is_overridden);
  const canCancel = item.type === "secret" ? draft.trim().length > 0 : draft !== item.effective_value;
  const meta = SETTING_META[item.key];
  const display = meta?.display ?? (item.type === "bool" ? "switch" : item.type === "int" ? "number" : item.type === "secret" ? "secret" : "technical");
  const label = meta?.label ?? item.label;
  const autoSavePending = item.type !== "secret" && canSave;

  async function save(nextValue = draft) {
    setBusy(true);
    setError("");
    try {
      await api.updateSetting(csrfToken, item.key, nextValue);
      notify({ tone: "success", title: `${item.label} saved` });
      await onChanged();
    } catch (err) {
      setError(isApiError(err) ? err.message : "Saving the setting failed.");
    } finally {
      setBusy(false);
    }
  }

  function commitChoice(nextValue: string) {
    setDraft(nextValue);
    if (nextValue !== item.effective_value || (nextValue === "" && item.is_overridden)) void save(nextValue);
  }

  function handleAutoSaveBlur(event: FocusEvent<HTMLInputElement>) {
    if (!autoSavePending || busy) return;
    const nextTarget = event.relatedTarget;
    const control = event.currentTarget.closest(".settings-control");
    if (nextTarget && control?.contains(nextTarget as Node)) return;
    void save(draft);
  }

  function blurOnEnter(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") event.currentTarget.blur();
  }

  async function copyValue() {
    const value = draft || item.effective_value;
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      notify({ tone: "success", title: `${label} copied` });
    } catch {
      notify({ tone: "error", title: "Copy failed", description: `${label} could not be copied automatically.` });
    }
  }

  async function reset() {
    setBusy(true);
    setError("");
    try {
      await api.resetSetting(csrfToken, item.key);
      notify({ tone: "info", title: `${item.label} reset`, description: "Environment default restored." });
      setResetOpen(false);
      await onChanged();
    } catch (err) {
      setError(isApiError(err) ? err.message : "Resetting the setting failed.");
    } finally {
      setBusy(false);
    }
  }

  function cancelDraft() {
    setDraft(item.type === "secret" ? "" : item.effective_value);
    setError("");
  }

  return (
    <div className={classNames("settings-control", compact && "settings-control--compact")}>
      <div className="settings-control-copy">
        <div className="settings-control-heading">
          <label htmlFor={inputId}>{label}</label>
          {meta?.help ? (
            <span className="settings-info" title={meta.help} aria-label={meta.help}>
              <Info aria-hidden="true" focusable="false" />
            </span>
          ) : null}
        </div>
        {meta?.description ? <p>{meta.description}</p> : null}
      </div>
      <div className="settings-control-editor">
        {display === "switch" ? (
          <label className="settings-switch" htmlFor={inputId}>
            <input
              id={inputId}
              type="checkbox"
              checked={draft === "true"}
              disabled={busy}
              aria-describedby={error ? errorId : undefined}
              onChange={(event) => commitChoice(event.target.checked ? "true" : "false")}
            />
            <span aria-hidden="true" />
            <strong>{draft === "true" ? "Enabled" : "Disabled"}</strong>
          </label>
        ) : display === "segmented" ? (
          <div className="settings-segmented" role="radiogroup" aria-label={label} aria-describedby={error ? errorId : undefined}>
            {item.enum_values.map((value) => (
              <button
                key={value}
                className={classNames("settings-segmented-button", draft === value && "is-active")}
                type="button"
                role="radio"
                aria-checked={draft === value}
                disabled={busy}
                onClick={() => commitChoice(value)}
              >
                {value}
              </button>
            ))}
          </div>
        ) : display === "secret" ? (
          <div className="settings-secret-field">
            <div className="settings-secret-state">
              <StatusBadge label={item.effective_value === "configured" ? "Configured" : "Missing"} tone={item.effective_value === "configured" ? "success" : "warn"} />
              <span>Stored secret is never displayed.</span>
            </div>
            <div className="settings-input-action">
              <input
                id={inputId}
                className="settings-input--mono"
                type={secretVisible ? "text" : "password"}
                value={draft}
                placeholder="Enter replacement secret"
                autoComplete="new-password"
                disabled={busy}
                aria-describedby={error ? errorId : undefined}
                onChange={(event) => setDraft(event.target.value)}
              />
              <button
                className="icon-button icon-button--tiny"
                type="button"
                disabled={!draft}
                onClick={() => setSecretVisible((value) => !value)}
                aria-label={secretVisible ? "Hide replacement secret" : "Reveal replacement secret"}
                title={secretVisible ? "Hide replacement secret" : "Reveal replacement secret"}
              >
                {secretVisible ? <EyeOff aria-hidden="true" focusable="false" /> : <Eye aria-hidden="true" focusable="false" />}
              </button>
            </div>
          </div>
        ) : display === "number" ? (
          <div className="settings-number-field">
            <input
              id={inputId}
              type="number"
              value={draft}
              disabled={busy}
              aria-describedby={error ? errorId : undefined}
              onChange={(event) => setDraft(event.target.value)}
              onBlur={handleAutoSaveBlur}
              onKeyDown={blurOnEnter}
            />
            {meta?.unit ? <span className="settings-unit">{meta.unit}</span> : null}
          </div>
        ) : (
          <div className="settings-input-action">
            <input
              id={inputId}
              className="settings-input--mono"
              value={draft}
              disabled={busy}
              aria-describedby={error ? errorId : undefined}
              onChange={(event) => setDraft(event.target.value)}
              onBlur={handleAutoSaveBlur}
              onKeyDown={blurOnEnter}
            />
            <button
              className="icon-button icon-button--tiny"
              type="button"
              disabled={!draft && !item.effective_value}
              onClick={() => void copyValue()}
              aria-label={`Copy ${label}`}
              title={`Copy ${label}`}
            >
              <ClipboardCopy aria-hidden="true" focusable="false" />
            </button>
          </div>
        )}
        <div className="settings-control-footer">
          <div className="settings-source-row">
            <SourceBadge label={meta?.sourceLabel} overridden={item.is_overridden} source={item.source} />
            {autoSavePending ? <StatusBadge label="Unsaved" tone="warn" /> : null}
            {item.is_overridden ? (
              <span>
                Default <code>{item.env_default || "-"}</code>
              </span>
            ) : null}
          </div>
          <div className="settings-control-actions">
            {canCancel ? (
              <button className="ghost-button ghost-button--small" type="button" disabled={busy} onClick={cancelDraft}>
                Cancel
              </button>
            ) : null}
            {item.is_overridden ? (
              <button className="secondary-button secondary-button--small button-with-icon" type="button" disabled={busy} onClick={() => setResetOpen(true)}>
                <RotateCcwKey aria-hidden="true" className="button-icon" focusable="false" />
                Reset
              </button>
            ) : null}
            {canSave && item.type === "secret" ? (
              <button className="primary-button secondary-button--small" type="button" disabled={busy} onClick={() => void save()}>
                Save
              </button>
            ) : null}
          </div>
        </div>
        {error ? (
          <p className="form-error" id={errorId}>
            {error}
          </p>
        ) : null}
      </div>
      {resetOpen ? (
        <ConfirmModal
          title={`Reset ${label}?`}
          description="This removes the override and restores the value from the environment file."
          confirmLabel="Reset"
          busy={busy}
          onClose={() => setResetOpen(false)}
          onConfirm={() => void reset()}
        />
      ) : null}
    </div>
  );
}

function SourceBadge({
  label,
  overridden,
  source,
}: {
  label?: string;
  overridden: boolean;
  source: SettingItemOut["source"];
}) {
  const isOverride = source === "environment" && overridden;
  const sourceLabel = label ?? (source === "application" ? "App" : "ENV");
  return <span className={classNames("settings-source-badge", isOverride && "settings-source-badge--override")}>{isOverride ? "Override" : sourceLabel}</span>;
}

type StatusTone = "neutral" | "success" | "warn" | "danger";

type StatusFact = {
  label: string;
  value: ReactNode;
  tone?: StatusTone;
};

type StatusCheck = {
  label: string;
  value: ReactNode;
  tone: StatusTone;
  detail?: string;
};

type StatusTechnicalRow = {
  label: string;
  value: ReactNode;
};

type IntegrationStatusView = {
  id: string;
  title: string;
  description: string;
  enabled: boolean;
  statusLabel: string;
  tone: StatusTone;
  summary: string;
  lastCheckedLabel: string;
  badges: Array<{ label: string; tone?: StatusTone }>;
  facts: StatusFact[];
  healthChecks: StatusCheck[];
  capabilities: StatusFact[];
  credentials: Array<[string, string]>;
  permissionSummary: string;
  permissionBadges: Array<{ label: string; tone: "success" | "warn" | "neutral" }>;
  attentionItems: Array<{ title: string; description: string; tone: "warn" | "danger" }>;
  diagnosticRows: StatusTechnicalRow[];
  technicalRows: StatusTechnicalRow[];
  primaryActionSlot?: ReactNode;
  manageActionSlot?: ReactNode;
};

function buildBotIntegrationView(readiness: AdminReadinessOut, onCopy: (value: string, label: string) => void): IntegrationStatusView {
  const oauth = readiness.bot.oauth;
  const authStatus = readiness.bot.auth_status;
  const permissionTone = oauth.token.succeeded && oauth.token.roles.length ? "success" : oauth.token.succeeded ? "neutral" : "warn";
  return {
    id: "bot-framework",
    title: "Bot Framework",
    description: "Teams conversation delivery",
    enabled: readiness.bot.enabled,
    statusLabel: healthStateLabel(authStatus),
    tone: authStatusTone(authStatus),
    summary: readinessSummary(authStatus, readiness.bot.message, oauth),
    lastCheckedLabel: oauth.token.checked ? "Current request" : "Not checked",
    badges: [
      { label: readiness.bot.enabled ? "Enabled" : "Disabled", tone: readiness.bot.enabled ? "success" : "neutral" },
      {
        label: readiness.bot.default_service_url_configured ? "Service URL set" : "No service URL",
        tone: readiness.bot.default_service_url_configured ? "success" : "warn",
      },
    ],
    facts: oauthFacts(oauth),
    healthChecks: [
      { label: "Availability", value: readiness.bot.enabled ? "Enabled" : "Disabled", tone: readiness.bot.enabled ? "success" : "neutral" },
      { label: "App credentials", value: readiness.bot.credentials_configured ? "Configured" : "Missing", tone: readiness.bot.credentials_configured ? "success" : "warn" },
      { label: "Token request", value: tokenFact(oauth), tone: oauth.token.succeeded ? "success" : oauth.token.checked ? "danger" : "neutral" },
      {
        label: "Default service URL",
        value: readiness.bot.default_service_url_configured ? "Configured" : "Missing",
        tone: readiness.bot.default_service_url_configured ? "success" : "warn",
      },
    ],
    capabilities: [
      { label: "Message path", value: "Bot conversation" },
      { label: "Scope", value: compactScope(oauth.scope || oauth.token.audience) },
    ],
    credentials: [
      ["Tenant ID", credentialStatusLabel(readiness.bot.credential_fields.tenant_id)],
      ["Client ID", credentialStatusLabel(readiness.bot.credential_fields.client_id)],
      ["Client secret", credentialStatusLabel(readiness.bot.credential_fields.client_secret)],
      ["Default service URL", credentialStatusLabel(readiness.bot.credential_fields.default_service_url)],
    ],
    permissionSummary: permissionSummary(oauth),
    permissionBadges: oauthPermissionBadges(oauth, permissionTone),
    attentionItems: readinessAttentionItems(authStatus, readiness.bot.message, oauth),
    diagnosticRows: oauthDiagnosticRows(oauth),
    technicalRows: oauthTechnicalRows(oauth, onCopy),
  };
}

function buildGraphLookupIntegrationView(readiness: AdminReadinessOut, onCopy: (value: string, label: string) => void): IntegrationStatusView {
  const oauth = readiness.graph_lookup.oauth;
  const authStatus = readiness.graph_lookup.auth_status;
  const permissionTone = oauth.token.succeeded && oauth.token.roles.length ? "success" : oauth.token.succeeded ? "neutral" : "warn";
  return {
    id: "graph-lookup",
    title: "Graph lookup",
    description: "Target discovery and names",
    enabled: readiness.graph_lookup.enabled,
    statusLabel: healthStateLabel(authStatus),
    tone: authStatusTone(authStatus),
    summary: readinessSummary(authStatus, readiness.graph_lookup.message, oauth),
    lastCheckedLabel: oauth.token.checked ? "Current request" : "Not checked",
    badges: [
      { label: readiness.graph_lookup.enabled ? "Enabled" : "Disabled", tone: readiness.graph_lookup.enabled ? "success" : "neutral" },
      {
        label: graphCredentialLabel(readiness.graph_lookup.credential_source),
        tone: readiness.graph_lookup.credential_source === "missing" ? "warn" : "neutral",
      },
    ],
    facts: oauthFacts(oauth),
    healthChecks: [
      { label: "Availability", value: readiness.graph_lookup.enabled ? "Enabled" : "Disabled", tone: readiness.graph_lookup.enabled ? "success" : "neutral" },
      { label: "App credentials", value: readiness.graph_lookup.configured ? "Configured" : "Missing", tone: readiness.graph_lookup.configured ? "success" : "warn" },
      { label: "Token request", value: tokenFact(oauth), tone: oauth.token.succeeded ? "success" : oauth.token.checked ? "danger" : "neutral" },
      { label: "Directory metadata", value: oauth.app.available || oauth.tenant.available ? "Available" : "Limited", tone: oauth.app.available || oauth.tenant.available ? "success" : "warn" },
    ],
    capabilities: [
      { label: "Lookup mode", value: readiness.graph_lookup.enabled ? "Enabled" : "Disabled", tone: readiness.graph_lookup.enabled ? "success" : "neutral" },
      { label: "Credentials", value: graphCredentialLabel(readiness.graph_lookup.credential_source), tone: readiness.graph_lookup.credential_source === "missing" ? "warn" : "neutral" },
      { label: "Scope", value: compactScope(oauth.scope || oauth.token.audience) },
    ],
    credentials: [
      ["Tenant ID", credentialStatusLabel(readiness.graph_lookup.credential_fields.tenant_id)],
      ["Client ID", credentialStatusLabel(readiness.graph_lookup.credential_fields.client_id)],
      ["Client secret", credentialStatusLabel(readiness.graph_lookup.credential_fields.client_secret)],
    ],
    permissionSummary: permissionSummary(oauth),
    permissionBadges: oauthPermissionBadges(oauth, permissionTone),
    attentionItems: readinessAttentionItems(authStatus, readiness.graph_lookup.message, oauth),
    diagnosticRows: oauthDiagnosticRows(oauth),
    technicalRows: oauthTechnicalRows(oauth, onCopy),
  };
}

function buildGraphDeliveryIntegrationView(
  readiness: AdminReadinessOut["graph_delivery"],
  busy: boolean,
  onConnect: () => void,
  onDisconnect: () => void,
  onCopy: (value: string, label: string) => void,
): IntegrationStatusView {
  const serviceUser = readiness.service_user_display_name || readiness.service_user_principal_name || readiness.service_user_id || "-";
  const missingScopes = new Set(readiness.missing_scopes.map((scope) => scope.toLowerCase()));
  return {
    id: "graph-delivery",
    title: "Graph delivery",
    description: "Delegated Teams sends",
    enabled: readiness.enabled,
    statusLabel: healthStateLabel(readiness.auth_status),
    tone: authStatusTone(readiness.auth_status),
    summary: graphDeliverySummary(readiness),
    lastCheckedLabel: readiness.refresh_checked_at ? formatDateTime(readiness.refresh_checked_at) : readiness.token_checked ? "Current request" : "Not checked",
    badges: [
      { label: readiness.enabled ? "Enabled" : "Disabled", tone: readiness.enabled ? "success" : "neutral" },
      {
        label: readiness.credential_source === "delegated_service_user" ? "Service user connected" : "Not connected",
        tone: readiness.credential_source === "delegated_service_user" ? "success" : readiness.enabled ? "warn" : "neutral",
      },
    ],
    facts: [
      {
        label: "Token",
        value: delegatedTokenFact(readiness),
        tone: readiness.token_request_succeeded ? "success" : readiness.token_checked ? "danger" : "neutral",
      },
      {
        label: "Expires",
        value: readiness.access_token_expires_at ? formatRelativeTime(readiness.access_token_expires_at) : "-",
        tone: readiness.access_token_expires_at ? "success" : "neutral",
      },
      { label: "Service user", value: serviceUser },
      { label: "Last checked", value: readiness.refresh_checked_at ? formatDateTime(readiness.refresh_checked_at) : "Not checked" },
    ],
    healthChecks: [
      { label: "Availability", value: readiness.enabled ? "Enabled" : "Disabled", tone: readiness.enabled ? "success" : "neutral" },
      { label: "Service user", value: readiness.configured ? "Connected" : "Not connected", tone: readiness.configured ? "success" : readiness.enabled ? "warn" : "neutral" },
      { label: "Token refresh", value: delegatedTokenFact(readiness), tone: readiness.token_request_succeeded ? "success" : readiness.token_checked ? "danger" : "neutral" },
      {
        label: "Required scopes",
        value: readiness.missing_scopes.length ? `${readiness.missing_scopes.length} missing` : "Present",
        tone: readiness.missing_scopes.length ? "warn" : "success",
      },
    ],
    capabilities: [
      { label: "Availability", value: readiness.enabled ? "Available" : "Disabled", tone: readiness.enabled ? "success" : "neutral" },
      { label: "Sender", value: serviceUser },
      { label: "Token expires", value: readiness.access_token_expires_at ? formatRelativeTime(readiness.access_token_expires_at) : "-" },
    ],
    credentials: [
      ["Tenant ID", readiness.tenant_id ? "Configured" : "Missing"],
      ["Client ID", readiness.client_id ? "Configured" : "Missing"],
      ["Service user", readiness.configured ? "Configured" : "Missing"],
    ],
    permissionSummary: graphDeliveryScopeSummary(readiness),
    permissionBadges: readiness.required_scopes.map((scope) => ({
      label: scope,
      tone: missingScopes.has(scope.toLowerCase()) ? "warn" : "success",
    })),
    attentionItems: graphDeliveryAttentionItems(readiness),
    primaryActionSlot: (
      <GraphDeliveryActionBar
        busy={busy}
        configured={readiness.configured}
        enabled={readiness.enabled}
        onConnect={onConnect}
        onDisconnect={onDisconnect}
      />
    ),
    manageActionSlot: (
      <GraphDeliveryManageMenu
        busy={busy}
        configured={readiness.configured}
        enabled={readiness.enabled}
        onConnect={onConnect}
        onDisconnect={onDisconnect}
      />
    ),
    diagnosticRows: [
      { label: "Credential source", value: readiness.credential_source || "missing" },
      { label: "Refresh checked", value: readiness.refresh_checked_at ? formatDateTime(readiness.refresh_checked_at) : "Not checked" },
      { label: "Token request", value: readiness.token_request_succeeded ? "Succeeded" : readiness.token_checked ? "Failed" : "Not checked" },
      { label: "Missing scopes", value: readiness.missing_scopes.join(", ") || "-" },
    ],
    technicalRows: [
      { label: "Tenant ID", value: <DiagnosticValue value={readiness.tenant_id} label="Tenant ID" onCopy={onCopy} /> },
      { label: "Client ID", value: <DiagnosticValue value={readiness.client_id} label="Client ID" onCopy={onCopy} /> },
      { label: "Service user ID", value: <DiagnosticValue value={readiness.service_user_id} label="Service user ID" onCopy={onCopy} /> },
      { label: "Service user UPN", value: readiness.service_user_principal_name || "-" },
      { label: "Granted scopes", value: readiness.scopes.join(", ") || "-" },
      { label: "Missing scopes", value: readiness.missing_scopes.join(", ") || "-" },
    ],
  };
}

function oauthFacts(oauth: OAuthDiagnosticsOut): StatusFact[] {
  return [
    { label: "Token", value: tokenFact(oauth), tone: oauth.token.succeeded ? "success" : oauth.token.checked ? "danger" : "neutral" },
    { label: "Expires", value: tokenExpirationShortLabel(oauth), tone: oauth.token.succeeded ? "success" : "neutral" },
    { label: "Credentials", value: oauthCredentialSourceLabel(oauth.credential_source) },
    { label: "Scope", value: compactScope(oauth.scope || oauth.token.audience) },
  ];
}

function oauthPermissionBadges(oauth: OAuthDiagnosticsOut, fallbackTone: "success" | "warn" | "neutral") {
  if (oauth.token.roles.length) {
    return oauth.token.roles.map((role) => ({ label: role, tone: "success" as const }));
  }
  return [{ label: oauth.token.succeeded ? "No roles reported" : "Permissions not verified", tone: fallbackTone }];
}

function oauthDiagnosticRows(oauth: OAuthDiagnosticsOut): StatusTechnicalRow[] {
  return [
    { label: "Credential source", value: oauthCredentialSourceLabel(oauth.credential_source) },
    { label: "Token checked", value: yesNo(oauth.token.checked) },
    { label: "Token request", value: oauth.token.succeeded ? "Succeeded" : oauth.token.checked ? "Failed" : "Not checked" },
    { label: "Token expires", value: tokenExpirationShortLabel(oauth) },
    { label: "App metadata", value: oauth.app.metadata_checked ? (oauth.app.available ? "Available" : oauth.app.message || "Unavailable") : "Not checked" },
    { label: "Tenant metadata", value: oauth.tenant.metadata_checked ? (oauth.tenant.available ? "Available" : oauth.tenant.message || "Unavailable") : "Not checked" },
  ];
}

function oauthTechnicalRows(oauth: OAuthDiagnosticsOut, onCopy: (value: string, label: string) => void): StatusTechnicalRow[] {
  return [
    { label: "Tenant ID", value: <DiagnosticValue value={oauth.tenant_id} label="Tenant ID" onCopy={onCopy} /> },
    { label: "Client ID", value: <DiagnosticValue value={oauth.client_id} label="Client ID" onCopy={onCopy} /> },
    { label: "Audience", value: oauth.token.audience || "-" },
    { label: "Issuer", value: oauth.token.issuer || "-" },
    { label: "App name", value: oauth.app.display_name || "-" },
    { label: "App ID", value: <DiagnosticValue value={oauth.app.app_id} label="App ID" onCopy={onCopy} /> },
    { label: "Service principal", value: <DiagnosticValue value={oauth.app.service_principal_id} label="Service principal ID" onCopy={onCopy} /> },
    { label: "Principal type", value: oauth.app.service_principal_type || "-" },
    { label: "Account enabled", value: oauth.app.account_enabled === null ? "-" : yesNo(oauth.app.account_enabled) },
    { label: "Tenant", value: oauth.tenant.display_name || "-" },
    { label: "Primary domain", value: oauth.tenant.primary_domain || "-" },
  ];
}

function RelayHealthHero({
  deliveryMethodCount,
  enabledCount,
  integrations,
  overallLabel,
  overallTone,
  readiness,
}: {
  deliveryMethodCount?: number;
  enabledCount?: number;
  integrations: IntegrationStatusView[];
  overallLabel: string;
  overallTone: StatusTone;
  readiness: AdminReadinessOut;
}) {
  const tokenCount = integrations.filter((integration) => integration.facts.some((fact) => fact.label === "Token" && fact.tone === "success")).length;
  const attentionItems = integrations.flatMap((integration) => integration.attentionItems);
  const readyCount = integrations.filter((integration) => integration.tone === "success").length;
  const nextStep = attentionItems[0]?.title ?? (readiness.graph_delivery.configured ? "Monitor message delivery" : "Connect service user");
  const methodsEnabled = enabledCount ?? readyCount;
  const methodsTotal = deliveryMethodCount ?? integrations.length;

  return (
    <section className={classNames("status-relay-hero", `status-relay-hero--${overallTone}`)} aria-label="Relay health">
      <div className="status-relay-hero-main">
        <div className={classNames("status-relay-indicator", `status-relay-indicator--${overallTone}`)} aria-hidden="true" />
        <div>
          <p className="integration-kicker">Relay health</p>
          <h2>{overallLabel === "Ready" ? "Relay is ready to deliver messages" : overallLabel === "Attention" ? "Relay needs operator attention" : "Relay delivery is degraded"}</h2>
          <p>
            {overallTone === "success"
              ? "No immediate action is required. Keep an eye on message logs after new routes are added."
              : "Start with the first item below, then refresh auth tokens to confirm the fix."}
          </p>
        </div>
      </div>
      <div className="status-relay-metrics">
        <StatusOverviewMetric label="Status" value={overallLabel} detail={overallTone === "success" ? "No active blockers." : "Review the selected component."} tone={overallTone} />
        <StatusOverviewMetric
          label="Action"
          value={attentionItems.length ? `${attentionItems.length} item${attentionItems.length === 1 ? "" : "s"}` : "None"}
          detail={nextStep}
          tone={attentionItems.length ? (attentionItems.some((item) => item.tone === "danger") ? "danger" : "warn") : "success"}
        />
        <StatusOverviewMetric
          label="Methods"
          value={`${methodsEnabled}/${methodsTotal} enabled`}
          detail={`${readyCount}/${integrations.length} components ready.`}
          tone={methodsEnabled === methodsTotal ? "success" : methodsEnabled > 0 ? "warn" : "danger"}
        />
        <StatusOverviewMetric
          label="Auth"
          value={`${tokenCount}/${integrations.length} valid`}
          detail="Token checks that currently pass."
          tone={tokenCount === integrations.length ? "success" : tokenCount > 0 ? "warn" : "danger"}
        />
      </div>
    </section>
  );
}

function StatusCheckList({ checks }: { checks: StatusCheck[] }) {
  return (
    <div className="status-check-list">
      {checks.map((check) => (
        <div className="status-check-row" key={check.label}>
          <span className={classNames("status-dot", `status-dot--${check.tone}`)} aria-hidden="true" />
          <span>
            <strong>{check.label}</strong>
            {check.detail ? <small>{check.detail}</small> : null}
          </span>
          <em>{check.value}</em>
        </div>
      ))}
    </div>
  );
}

function StatusFactList({ facts }: { facts: StatusFact[] }) {
  return (
    <dl className="status-detail-facts">
      {facts.map((fact) => (
        <FragmentPair
          key={fact.label}
          label={fact.label}
          value={<span className={classNames("status-detail-fact-value", fact.tone && fact.tone !== "neutral" && `status-detail-fact-value--${fact.tone}`)}>{fact.value}</span>}
        />
      ))}
    </dl>
  );
}

function StatusOverviewMetric({
  detail,
  label,
  tone = "neutral",
  value,
}: {
  detail: string;
  label: string;
  tone?: StatusTone;
  value: string;
}) {
  return (
    <div className={classNames("status-overview-item", tone !== "neutral" && `status-overview-item--${tone}`)}>
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </div>
  );
}

function FragmentPair({ label, value }: { label: string; value: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

function GraphDeliveryActionBar({
  busy,
  configured,
  enabled,
  onConnect,
  onDisconnect,
}: {
  busy: boolean;
  configured: boolean;
  enabled: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  return (
    <div className="graph-delivery-action-bar">
      <button className="secondary-button secondary-button--small" type="button" onClick={onConnect} disabled={busy || !enabled}>
        {configured ? "Reconnect service user" : "Connect service user"}
      </button>
      {configured ? (
        <button className="ghost-button ghost-button--small" type="button" onClick={onDisconnect} disabled={busy}>
          Disconnect
        </button>
      ) : null}
    </div>
  );
}

function GraphDeliveryManageMenu({
  busy,
  configured,
  enabled,
  onConnect,
  onDisconnect,
}: {
  busy: boolean;
  configured: boolean;
  enabled: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  const items: RowActionItem[] = configured
    ? [
        {
          label: "Reconnect service user",
          icon: RefreshCw,
          onClick: onConnect,
          disabled: busy || !enabled,
          spinning: busy,
        },
        {
          label: "Disconnect service user",
          icon: PowerOff,
          onClick: onDisconnect,
          disabled: busy,
          separated: true,
        },
      ]
    : [
        {
          label: "Connect service user",
          icon: Power,
          onClick: onConnect,
          disabled: busy || !enabled,
        },
      ];

  return <RowActionMenu label="Manage Graph delivery connection" items={items} />;
}

function RuntimeSnapshotCard({ onCopy, readiness }: { onCopy: (value: string, label: string) => void; readiness: AdminReadinessOut }) {
  return (
    <Card className="status-context-card">
      <details className="status-runtime-disclosure">
        <summary>
          <span>
            <span className="integration-kicker">Developer details</span>
            <strong>Runtime and environment</strong>
            <small>URLs, proxy settings, limits and retention values.</small>
          </span>
          <span className="status-runtime-summary-badges">
            <StatusBadge
              label={`Retention ${readiness.runtime.log_retention_days}d`}
              tone="neutral"
            />
            <StatusBadge
              label={settingsEncryptionLabel(readiness.runtime.settings_encryption_key_source, readiness.runtime.settings_encryption_ready)}
              tone={readiness.runtime.settings_encryption_ready ? "success" : "warn"}
            />
            <ChevronDown aria-hidden="true" className="settings-disclosure-icon" focusable="false" />
          </span>
        </summary>
        <dl className="status-runtime-list">
          <dt>Application</dt>
          <dd>
            {readiness.app_name} {readiness.app_version}
          </dd>
          <dt>Public URL</dt>
          <dd>
            <CopyInlineValue label="Public URL" onCopy={onCopy} value={readiness.runtime.app_public_base_url} />
          </dd>
          <dt>Frontend URL</dt>
          <dd>
            <CopyInlineValue label="Frontend URL" onCopy={onCopy} value={readiness.runtime.frontend_base_url} />
          </dd>
          <dt>CORS origins</dt>
          <dd>{readiness.runtime.cors_origins.join(", ") || "-"}</dd>
          <dt>Compose subnet</dt>
          <dd>{readiness.runtime.compose_app_subnet || "-"}</dd>
          <dt>Trusted upstream proxies</dt>
          <dd>{readiness.runtime.trusted_proxy_ips || "-"}</dd>
          <dt>Trusted proxy chain</dt>
          <dd>{readiness.runtime.trusted_proxy_chain || "-"}</dd>
          <dt>Payload limit</dt>
          <dd>{formatBytes(readiness.runtime.webhook_max_payload_bytes)}</dd>
          <dt>Log retention</dt>
          <dd>{readiness.runtime.log_retention_days} days</dd>
          <dt>Cleanup interval</dt>
          <dd>{readiness.runtime.log_cleanup_interval_minutes} minutes</dd>
          <dt>Secure session cookie</dt>
          <dd>{yesNo(readiness.runtime.session_secure_cookie)}</dd>
          <dt>Settings encryption</dt>
          <dd>{settingsEncryptionLabel(readiness.runtime.settings_encryption_key_source, readiness.runtime.settings_encryption_ready)}</dd>
        </dl>
      </details>
    </Card>
  );
}

function settingsEncryptionLabel(source: string, ready: boolean) {
  if (!ready) return "Missing";
  if (source === "configured") return "Configured";
  if (source === "generated") return "Generated";
  return "Configured";
}

function CopyInlineValue({ label, onCopy, value }: { label: string; onCopy: (value: string, label: string) => void; value: string }) {
  if (!value) return <>-</>;
  return (
    <span className="copy-inline-value">
      <code>{value}</code>
      <button className="icon-button icon-button--tiny" type="button" onClick={() => onCopy(value, label)} aria-label={`Copy ${label}`} title={`Copy ${label}`}>
        <ClipboardCopy aria-hidden="true" focusable="false" />
      </button>
    </span>
  );
}

function CredentialCheck({ label, value }: { label: string; value: string }) {
  const tone = value === "Missing" ? "warn" : value === "Configured" || value === "Inherited" ? "success" : "neutral";

  return (
    <div className={classNames("credential-check", `credential-check--${tone}`)}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DiagnosticValue({ label, onCopy, value }: { label: string; onCopy: (value: string, label: string) => void; value: string }) {
  if (!value) return <>-</>;
  return (
    <span className="diagnostic-value">
      <code>{shortDiagnosticId(value)}</code>
      <button className="icon-button icon-button--tiny" type="button" onClick={() => onCopy(value, label)} aria-label={`Copy ${label}`} title={`Copy ${label}`}>
        <ClipboardCopy aria-hidden="true" focusable="false" />
      </button>
    </span>
  );
}

function tokenFact(oauth: OAuthDiagnosticsOut): string {
  if (!oauth.token.checked) return "Not checked";
  if (!oauth.token.succeeded) return "Failed";
  if (!oauth.token.expires_at) return "Valid";
  return tokenValidityLabel(oauth.token.expires_at);
}

function tokenExpirationShortLabel(oauth: OAuthDiagnosticsOut): string {
  if (!oauth.token.checked) return "Not checked";
  if (!oauth.token.succeeded) return "Unavailable";
  if (!oauth.token.expires_at) return "Not provided";
  return formatRelativeTime(oauth.token.expires_at);
}

function tokenValidityLabel(expiresAt: string): string {
  const relative = formatRelativeTime(expiresAt);
  if (relative.startsWith("in ")) return `Valid for ${relative.slice(3)}`;
  if (relative === "now") return "Expires now";
  return `Expired ${relative}`;
}

function readinessSummary(authStatus: string, message: string, oauth: OAuthDiagnosticsOut): string {
  if (authStatus === "disabled") return message || "This integration is disabled by feature policy.";
  if (authStatus === "ready") return "Token checks passed, required credentials are present and the integration is ready for production traffic.";
  if (authStatus === "permission_warning") return "Core token checks passed, but optional directory metadata is limited by Microsoft Graph permissions.";
  if (authStatus === "mock") return "Token checks are skipped in this environment, but local delivery checks remain available.";
  if (authStatus === "token_error") return message || "Token verification failed, so runtime delivery cannot be trusted yet.";
  if (authStatus === "incomplete") return message || "Required credentials are missing for this integration.";
  if (oauth.token.succeeded) return "Token checks passed, but the readiness state needs review.";
  return message || "Readiness could not be fully determined.";
}

function graphDeliverySummary(readiness: AdminReadinessOut["graph_delivery"]): string {
  if (readiness.auth_status === "disabled") return readiness.message || "Delegated Microsoft Graph delivery is disabled by feature policy.";
  if (readiness.auth_status === "ready") return "Delegated token checks passed, required scopes are present and Graph delivery can be used.";
  if (readiness.auth_status === "missing") return readiness.message || "Connect a delegated service user before Microsoft Graph delivery can send messages.";
  if (readiness.auth_status === "expired") return readiness.message || "The delegated service-user connection has expired or was revoked.";
  if (readiness.auth_status === "permission_warning") return readiness.message || "The delegated token is valid, but required Graph delivery scopes are missing.";
  if (readiness.auth_status === "token_error") return readiness.message || "Delegated token verification failed.";
  if (readiness.auth_status === "configuration_error") return readiness.message || "Delegated Graph delivery has a configuration error.";
  if (readiness.auth_status === "incomplete") return readiness.message || "Required app registration settings are missing.";
  return readiness.message || "Graph delivery readiness could not be fully determined.";
}

function delegatedTokenFact(readiness: AdminReadinessOut["graph_delivery"]): string {
  if (!readiness.token_checked) return "Not checked";
  if (!readiness.token_request_succeeded) return "Failed";
  if (!readiness.access_token_expires_at) return "Valid";
  return tokenValidityLabel(readiness.access_token_expires_at);
}

function graphDeliveryScopeSummary(readiness: AdminReadinessOut["graph_delivery"]): string {
  if (!readiness.token_checked) return "Scopes are verified after a delegated token refresh succeeds.";
  if (!readiness.token_request_succeeded) return "Scopes cannot be verified until delegated token refresh succeeds.";
  if (readiness.missing_scopes.length) return `${readiness.missing_scopes.length} required delegated scope${readiness.missing_scopes.length === 1 ? "" : "s"} missing.`;
  return "All required delegated delivery scopes are present.";
}

function compactScope(value: string): string {
  if (!value) return "-";
  return value.replace(/^https:\/\/(graph\.microsoft\.com|api\.botframework\.com)\//, "");
}

function shortDiagnosticId(value: string): string {
  if (value.length <= 18) return value;
  return `${value.slice(0, 8)}...${value.slice(-6)}`;
}

function yesNo(value: boolean): string {
  return value ? "Yes" : "No";
}

function graphCredentialLabel(source: string): string {
  if (source === "disabled") return "Disabled";
  if (source === "ms_app") return "Entra app credentials";
  return "Missing";
}

function oauthCredentialSourceLabel(source: string): string {
  if (source === "disabled") return "Disabled";
  if (source === "ms_app") return "Entra app credentials";
  return "Missing";
}

function credentialStatusLabel(status?: string): string {
  if (status === "configured") return "Configured";
  return "Missing";
}

function authStatusTone(status: string): "neutral" | "success" | "warn" | "danger" {
  if (status === "ready") return "success";
  if (status === "permission_warning") return "warn";
  if (status === "token_error") return "danger";
  if (status === "configuration_error") return "danger";
  if (status === "expired") return "danger";
  if (status === "missing") return "warn";
  if (status === "incomplete") return "warn";
  return "neutral";
}

function healthStateLabel(status: string): string {
  if (status === "disabled") return "Disabled";
  if (status === "ready" || status === "mock") return "Ready";
  if (status === "token_error" || status === "expired" || status === "configuration_error") return "Error";
  return "Warning";
}

function permissionSummary(oauth: OAuthDiagnosticsOut): string {
  if (oauth.credential_source === "disabled") return "Permission checks are skipped while this integration is disabled.";
  if (!oauth.token.checked) return "Permissions have not been checked yet.";
  if (!oauth.token.succeeded) return "Permissions cannot be verified until token acquisition succeeds.";
  if (oauth.token.roles.length) return `${oauth.token.roles.length} application permission${oauth.token.roles.length === 1 ? "" : "s"} returned in the token.`;
  return "The token is valid, but no application roles were reported.";
}

function readinessAttentionItems(authStatus: string, message: string, oauth: OAuthDiagnosticsOut): Array<{ title: string; description: string; tone: "warn" | "danger" }> {
  const items: Array<{ title: string; description: string; tone: "warn" | "danger" }> = [];
  if (authStatus === "disabled") return items;

  if (authStatus === "token_error") {
    items.push({
      title: "Token request failed",
      description: message || "Required: fix the credentials or tenant configuration before this integration can be trusted.",
      tone: "danger",
    });
  }

  if (authStatus === "incomplete") {
    items.push({
      title: "Required credentials are missing",
      description: message || "Required: configure the missing tenant, client or secret values.",
      tone: "warn",
    });
  }

  if (oauth.app.metadata_checked && !oauth.app.available) {
    items.push({
      title: "App metadata is limited",
      description: `${oauth.app.message || "App metadata is not available."} Optional: this only affects diagnostics such as app display name.`,
      tone: "warn",
    });
  }

  if (oauth.tenant.metadata_checked && !oauth.tenant.available) {
    items.push({
      title: "Tenant metadata is limited",
      description: `${oauth.tenant.message || "Tenant metadata is not available."} Optional: this only affects tenant display details.`,
      tone: "warn",
    });
  }

  return items;
}

function graphDeliveryAttentionItems(readiness: AdminReadinessOut["graph_delivery"]): Array<{ title: string; description: string; tone: "warn" | "danger" }> {
  const items: Array<{ title: string; description: string; tone: "warn" | "danger" }> = [];
  if (readiness.auth_status === "disabled") return items;

  if (readiness.auth_status === "missing") {
    items.push({
      title: "Delegated service user missing",
      description: readiness.message || "Required: connect a delegated Graph service user before selecting Microsoft Graph delivery.",
      tone: "warn",
    });
  }

  if (readiness.auth_status === "expired") {
    items.push({
      title: "Delegated connection expired",
      description: readiness.message || "Required: reconnect the service user because Microsoft rejected the refresh token.",
      tone: "danger",
    });
  }

  if (readiness.auth_status === "token_error") {
    items.push({
      title: "Delegated token check failed",
      description: readiness.message || "Required: verify the service-user connection and tenant access.",
      tone: "danger",
    });
  }

  if (readiness.auth_status === "configuration_error") {
    items.push({
      title: "Settings encryption key error",
      description: readiness.message || "Required: restore the previous SETTINGS_ENC_KEY or reconnect the delegated Graph service user.",
      tone: "danger",
    });
  }

  if (readiness.missing_scopes.length) {
    items.push({
      title: "Required scopes missing",
      description: `Required: grant ${readiness.missing_scopes.join(", ")} to the delegated Microsoft Graph connection.`,
      tone: "warn",
    });
  }

  return items;
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
  const refreshSequence = useRef(0);
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
    const requestId = refreshSequence.current + 1;
    refreshSequence.current = requestId;
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
      if (refreshSequence.current !== requestId) return;
      setDeliveryPage(nextDeliveryPage);
      setRoutes(nextRoutes);
      setSelectedEventId((current) =>
        nextDeliveryPage.items.some((event) => event.id === current) ? current : "",
      );
    } catch (err) {
      if (refreshSequence.current !== requestId) return;
      setError(isApiError(err) ? err.message : "Logs could not be loaded.");
    } finally {
      if (refreshSequence.current === requestId) setLoading(false);
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
              placeholder="Route, message, error, payload"
              onChange={(event) => setSearchText(event.target.value)}
            />
          </label>
        </div>
        <div className="logs-list-panel">
          <DataTable
            columns={["Status", "Time", "Route", "Message", "Backend", "Mode", "Error"]}
            rows={deliveryEvents.map((event) => [
              <DeliveryEventStatusBadge status={event.status} />,
              formatDateTime(event.created_at),
              <div className="stacked-cell">
                <strong>{event.route_name || "Deleted route"}</strong>
                <span className="muted">{event.target_name || "No route metadata"}</span>
              </div>,
              <div className="stacked-cell">
                <span>{event.title || "-"}</span>
                <span className="muted">{event.payload_type || "-"}</span>
              </div>,
              <span className="muted">{deliverySummaryBackend(event)}</span>,
              <span className="muted">{deliverySummaryMode(event)}</span>,
              deliverySummaryErrorMessage(event) ? (
                <span className="form-error">{deliverySummaryErrorMessage(event)}</span>
              ) : (
                <span className="muted">-</span>
              ),
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
      </Card>
      {selectedEventId && !loading && !error ? (
        <MessageLogDetailsModal
          event={selectedEvent}
          loading={detailLoading}
          error={detailError}
          onClose={() => setSelectedEventId("")}
        />
      ) : null}
    </>
  );
}

function MessageLogDetailsModal({
  event,
  loading,
  error,
  onClose,
}: {
  event: WebhookDeliveryEventDetailOut | null;
  loading: boolean;
  error: string;
  onClose: () => void;
}) {
  return (
    <Modal
      title="Message log details"
      description={event ? `${eventTitle(event)} · ${formatDateTime(event.created_at)}` : "Delivery event details"}
      panelClassName="message-log-detail-modal"
      onClose={onClose}
    >
      {loading ? (
        <div className="modal-loading-state" role="status" aria-live="polite">
          <div className="spinner spinner--small" aria-hidden="true" />
          <p className="muted">Loading event details...</p>
        </div>
      ) : error ? (
        <div className="inline-error" role="alert">
          <p className="form-error">{error}</p>
        </div>
      ) : event ? (
        <DeliveryEventDetails event={event} />
      ) : null}
      <div className="form-actions">
        <button className="secondary-button" type="button" onClick={onClose}>
          Close
        </button>
      </div>
    </Modal>
  );
}

function SystemLogsPage() {
  const { session, notify } = useAppContext();
  const [auditLogs, setAuditLogs] = useState<AuditEventOut[]>([]);
  const [systemLogs, setSystemLogs] = useState<SystemLogEventOut[]>([]);
  const [abuseBuckets, setAbuseBuckets] = useState<WebhookAbuseBucketOut[]>([]);
  const [eventLogPage, setEventLogPage] = useState<EventLogEntryPageOut | null>(null);
  const [activeTab, setActiveTab] = useState<SystemLogTab>("timeline");
  const [eventLevelFilter, setEventLevelFilter] = useState("");
  const [eventCategoryFilter, setEventCategoryFilter] = useState("");
  const [eventSearch, setEventSearch] = useState("");
  const [eventCorrelationId, setEventCorrelationId] = useState("");
  const [loading, setLoading] = useState(true);
  const [cleanupBusy, setCleanupBusy] = useState(false);
  const [abuseCleanupBusy, setAbuseCleanupBusy] = useState(false);
  const [unblockingClientKey, setUnblockingClientKey] = useState("");
  const [error, setError] = useState("");
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextEventLogs, nextAuditLogs, nextSystemLogs, nextAbuseBuckets] = await Promise.all([
        api.adminEventLogs(csrfToken, {
          pageSize: 80,
          level: eventLevelFilter,
          category: eventCategoryFilter,
          correlationId: eventCorrelationId.trim(),
          query: eventSearch.trim(),
        }),
        api.adminLogs(csrfToken),
        api.adminSystemLogs(csrfToken),
        api.adminWebhookAbuseBuckets(csrfToken),
      ]);
      setEventLogPage(nextEventLogs);
      setAuditLogs(nextAuditLogs);
      setSystemLogs(nextSystemLogs);
      setAbuseBuckets(nextAbuseBuckets);
    } catch (err) {
      setError(isApiError(err) ? err.message : "System logs could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [csrfToken, eventCategoryFilter, eventCorrelationId, eventLevelFilter, eventSearch]);

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

  async function cleanupAbuseBuckets() {
    setAbuseCleanupBusy(true);
    try {
      const result = await api.cleanupWebhookAbuseBuckets(csrfToken);
      notify({
        tone: "info",
        title: "Abuse clients cleaned up",
        description: `${result.deleted} inactive entries removed. Retention is ${result.cleanup_days} days.`,
      });
      await refresh();
    } catch (err) {
      notify({
        tone: "error",
        title: "Cleanup failed",
        description: isApiError(err) ? err.message : "Abuse clients could not be cleaned up.",
      });
    } finally {
      setAbuseCleanupBusy(false);
    }
  }

  async function unblockAbuseClient(client: WebhookAbuseClientRow) {
    setUnblockingClientKey(client.key);
    try {
      await Promise.all(client.buckets.map((bucket) => api.unblockWebhookAbuseBucket(csrfToken, bucket.id)));
      notify({
        tone: "success",
        title: "Webhook client unblocked",
        description: `${client.clientHost || client.clientFingerprint} is no longer actively blocked.`,
      });
      await refresh();
    } catch (err) {
      notify({
        tone: "error",
        title: "Unblock failed",
        description: isApiError(err) ? err.message : "Webhook abuse client could not be unblocked.",
      });
    } finally {
      setUnblockingClientKey("");
    }
  }

  const abuseClients = useMemo(() => buildWebhookAbuseClients(abuseBuckets), [abuseBuckets]);
  const eventLogs = eventLogPage?.items ?? [];
  const errorEventCount = eventLogs.filter((event) => ["error", "critical"].includes(event.level)).length;
  const activeBlockCount = abuseClients.filter((client) => client.status === "blocked").length;
  const observedClientCount = abuseClients.filter((client) => client.status === "watching").length;
  const unknownAuthCount = systemLogs.filter((event) => event.auth_status !== "verified").length;
  const lastActivityAt = latestDate(
    [
      ...abuseClients.map((client) => client.lastSeen),
      ...eventLogs.map((event) => event.created_at),
      ...auditLogs.map((event) => event.created_at),
      ...systemLogs.map((event) => event.created_at),
    ].filter(Boolean),
  );
  const attentionClients = abuseClients.filter((client) => client.status === "blocked").slice(0, 3);
  const observedClients = abuseClients.filter((client) => client.status === "watching").slice(0, 3);

  return (
    <>
      <PageIntro
        eyebrow="Administration"
        title="System logs"
        description="Monitor ingress protection, admin actions and Teams bot activity from one operational view."
        actions={
          <div className="system-logs-actions">
            <StatusBadge
              label={activeBlockCount ? `${activeBlockCount} blocked` : "No active blocks"}
              title={activeBlockCount ? "These clients are currently receiving 429 responses." : "No webhook client is currently blocked."}
              tone={activeBlockCount ? "warn" : "success"}
            />
            <button className="secondary-button button-with-icon" type="button" disabled={loading} onClick={() => void refresh()}>
              <RefreshCw aria-hidden="true" className={classNames("button-icon", loading && "button-icon--spin")} focusable="false" />
              Refresh
            </button>
            <details className="maintenance-menu">
              <summary>
                <Wrench aria-hidden="true" className="button-icon" focusable="false" />
                Maintenance
              </summary>
              <div className="maintenance-menu-popover">
                <button className="secondary-button button-with-icon" type="button" disabled={abuseCleanupBusy} onClick={() => void cleanupAbuseBuckets()}>
                  <Trash2 aria-hidden="true" className="button-icon" focusable="false" />
                  {abuseCleanupBusy ? "Cleaning..." : "Clean abuse clients"}
                </button>
                <button className="secondary-button button-with-icon" type="button" disabled={cleanupBusy} onClick={() => void cleanupLogs()}>
                  <Trash2 aria-hidden="true" className="button-icon" focusable="false" />
                  {cleanupBusy ? "Cleaning..." : "Clean retained logs"}
                </button>
              </div>
            </details>
          </div>
        }
      />

      <section className="system-summary-grid" aria-label="System log overview">
        <SystemSummaryTile
          icon={ShieldAlert}
          label="Ingress protection"
          value={activeBlockCount ? `${activeBlockCount} blocked` : "Clear"}
          context={`${observedClientCount} observed ${observedClientCount === 1 ? "client" : "clients"}`}
          tone={activeBlockCount ? "warn" : "success"}
        />
        <SystemSummaryTile
          icon={Activity}
          label="Event ledger"
          value={String(eventLogPage?.total ?? eventLogs.length)}
          context={errorEventCount ? `${errorEventCount} errors in view` : "Unified timeline"}
          tone={errorEventCount ? "warn" : "neutral"}
        />
        <SystemSummaryTile
          icon={Bot}
          label="Bot activity"
          value={String(systemLogs.length)}
          context={unknownAuthCount ? `${unknownAuthCount} legacy auth events` : "Auth verified where available"}
          tone={unknownAuthCount ? "neutral" : "success"}
        />
        <SystemSummaryTile
          icon={FileClock}
          label="Last activity"
          value={lastActivityAt ? formatRelativeTime(lastActivityAt) : "None"}
          context={lastActivityAt ? formatDateTime(lastActivityAt) : "Waiting for events"}
        />
      </section>

      <section className={classNames("system-attention-panel", activeBlockCount > 0 && "system-attention-panel--warn")}>
        <div className="system-attention-copy">
          <span className="system-attention-icon" aria-hidden="true">
            {activeBlockCount ? <AlertTriangle className="button-icon" focusable="false" /> : <Check className="button-icon" focusable="false" />}
          </span>
          <div>
            <h2>{activeBlockCount ? "Ingress needs attention" : "Ingress is quiet"}</h2>
            <p>
              {activeBlockCount
                ? "Blocked webhook clients are listed first so they can be reviewed or unblocked quickly."
                : "No active webhook blocks. Observed clients only mean failed attempts were seen."}
            </p>
          </div>
        </div>
        <div className="attention-client-list">
          {(attentionClients.length ? attentionClients : observedClients).map((client) => (
            <AbuseClientCompactRow
              key={client.key}
              client={client}
              unblocking={unblockingClientKey === client.key}
              onUnblock={() => void unblockAbuseClient(client)}
            />
          ))}
          {!attentionClients.length && !observedClients.length ? (
            <div className="attention-empty">
              <strong>No tracked clients</strong>
              <span>Repeated failed webhook attempts will appear here.</span>
            </div>
          ) : null}
        </div>
      </section>

      <Card
        title="Activity explorer"
        description="Start with the unified event timeline, then jump into specialized security, audit or bot views when needed."
        headerActions={
          <div className="segmented-control" aria-label="System log sections">
            {SYSTEM_LOG_TABS.map((tab) => (
              <button
                key={tab.value}
                className={classNames("segmented-control-button", activeTab === tab.value && "is-active")}
                type="button"
                onClick={() => setActiveTab(tab.value)}
              >
                {tab.label}
              </button>
            ))}
          </div>
        }
      >
        {activeTab === "timeline" ? (
          <SystemLogState
            loading={loading}
            error={error}
            empty={!eventLogs.length}
            emptyTitle="No event ledger entries"
            emptyBody="Structured request, audit, webhook, integration and system events will appear here."
            onRetry={() => void refresh()}
          >
            <div className="event-log-filters">
              <label className="compact-filter">
                <span>Level</span>
                <select value={eventLevelFilter} onChange={(event) => setEventLevelFilter(event.target.value)}>
                  <option value="">All levels</option>
                  <option value="info">Info</option>
                  <option value="warning">Warning</option>
                  <option value="error">Error</option>
                  <option value="critical">Critical</option>
                </select>
              </label>
              <label className="compact-filter">
                <span>Category</span>
                <select value={eventCategoryFilter} onChange={(event) => setEventCategoryFilter(event.target.value)}>
                  <option value="">All categories</option>
                  <option value="request">Request</option>
                  <option value="auth">Auth</option>
                  <option value="audit">Audit</option>
                  <option value="security">Security</option>
                  <option value="webhook">Webhook</option>
                  <option value="integration">Integration</option>
                  <option value="system">System</option>
                  <option value="frontend">Frontend</option>
                </select>
              </label>
              <label className="compact-filter">
                <span>Correlation</span>
                <input value={eventCorrelationId} placeholder="Correlation ID" onChange={(event) => setEventCorrelationId(event.target.value)} />
              </label>
              <label className="compact-filter">
                <span>Search</span>
                <input value={eventSearch} placeholder="Message, type, actor, source" onChange={(event) => setEventSearch(event.target.value)} />
              </label>
            </div>
            <div className="activity-list">
              {eventLogs.map((event) => (
                <EventLogActivityRow key={event.id} event={event} />
              ))}
            </div>
          </SystemLogState>
        ) : null}
        {activeTab === "security" ? (
          <SystemLogState loading={loading} error={error} empty={!abuseClients.length} emptyTitle="No webhook abuse clients" emptyBody="Failed webhook attempts will appear here when a client starts being observed." onRetry={() => void refresh()}>
            <div className="activity-list">
              {abuseClients.map((client) => (
                <AbuseClientActivityRow
                  key={client.key}
                  client={client}
                  unblocking={unblockingClientKey === client.key}
                  onUnblock={() => void unblockAbuseClient(client)}
                />
              ))}
            </div>
          </SystemLogState>
        ) : null}
        {activeTab === "audit" ? (
          <SystemLogState loading={loading} error={error} empty={!auditLogs.length} emptyTitle="No audit events" emptyBody="Sign-ins, route changes and administration activity will appear here." onRetry={() => void refresh()}>
            <div className="activity-list">
              {auditLogs.map((event) => (
                <AuditActivityRow key={event.id} event={event} />
              ))}
            </div>
          </SystemLogState>
        ) : null}
        {activeTab === "bot" ? (
          <SystemLogState loading={loading} error={error} empty={!systemLogs.length} emptyTitle="No bot activity" emptyBody="Teams bot endpoint events will appear after Teams sends activities to the relay service." onRetry={() => void refresh()}>
            <div className="activity-list">
              {systemLogs.map((event) => (
                <BotActivityRow key={event.id} event={event} />
              ))}
            </div>
          </SystemLogState>
        ) : null}
      </Card>
    </>
  );
}

const SYSTEM_LOG_TABS: Array<{ value: SystemLogTab; label: string }> = [
  { value: "timeline", label: "Timeline" },
  { value: "security", label: "Security" },
  { value: "audit", label: "Audit" },
  { value: "bot", label: "Bot activity" },
];

function SystemSummaryTile({
  icon: Icon,
  label,
  value,
  context,
  tone = "neutral",
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  context: string;
  tone?: "neutral" | "success" | "warn";
}) {
  return (
    <div className={classNames("system-summary-tile", `system-summary-tile--${tone}`)}>
      <span className="system-summary-icon" aria-hidden="true">
        <Icon className="button-icon" focusable="false" />
      </span>
      <div>
        <span className="system-summary-label">{label}</span>
        <strong>{value}</strong>
        <span>{context}</span>
      </div>
    </div>
  );
}

function SystemLogState({
  loading,
  error,
  empty,
  emptyTitle,
  emptyBody,
  onRetry,
  children,
}: {
  loading: boolean;
  error: string;
  empty: boolean;
  emptyTitle: string;
  emptyBody: string;
  onRetry: () => void;
  children: ReactNode;
}) {
  if (loading) {
    return (
      <div className="table-state" role="status" aria-live="polite">
        <div className="spinner spinner--small" aria-hidden="true" />
        <p>Loading activity...</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="table-state table-state--error" role="alert">
        <h3>Could not load activity</h3>
        <p>{error}</p>
        <button className="secondary-button secondary-button--small" type="button" onClick={onRetry}>
          Retry
        </button>
      </div>
    );
  }
  if (empty) return <EmptyState title={emptyTitle} body={emptyBody} />;
  return <>{children}</>;
}

function AbuseClientCompactRow({
  client,
  unblocking,
  onUnblock,
}: {
  client: WebhookAbuseClientRow;
  unblocking: boolean;
  onUnblock: () => void;
}) {
  return (
    <div className="attention-client-row">
      <div>
        <strong>{client.clientHost || "Unknown client"}</strong>
        <span>{abuseReasonLabel(client.lastReason)} · {client.failureCount} failed attempts · {formatRelativeTime(client.lastSeen)}</span>
      </div>
      <StatusBadge
        label={abuseStatusLabel(client.status)}
        title={abuseStatusTooltip(client.status)}
        tone={client.status === "blocked" ? "warn" : "neutral"}
      />
      {client.status === "blocked" ? (
        <button
          className="secondary-button secondary-button--small"
          type="button"
          disabled={unblocking}
          title="Remove the active block and clear current failed attempts. Previous block history is kept."
          onClick={onUnblock}
        >
          {unblocking ? "Unblocking..." : "Unblock"}
        </button>
      ) : null}
    </div>
  );
}

function EventLogActivityRow({ event }: { event: EventLogEntryOut }) {
  const statusCode = stringField(event.http, "status_code");
  const duration = stringField(event.http, "duration_ms");
  const sourceIp = stringField(event.source, "ip");
  const actorLabel = eventActorLabel(event);
  const targetLabel = eventTargetLabel(event);
  return (
    <article className="activity-row event-log-row">
      <div className="activity-row-main">
        <StatusBadge label={event.level || "info"} tone={eventLevelTone(event.level)} />
        <div className="activity-row-copy">
          <strong>{event.message || humanizeLogToken(event.event_type)}</strong>
          <span>
            <code>{event.event_type}</code>
            {actorLabel ? ` · ${actorLabel}` : ""}
            {targetLabel ? ` · ${targetLabel}` : ""}
          </span>
        </div>
      </div>
      <div className="activity-row-meta">
        <StatusBadge label={event.category || "event"} tone={eventCategoryTone(event.category)} />
        {statusCode !== "-" ? <span>HTTP {statusCode}{duration !== "-" ? ` · ${duration}ms` : ""}</span> : null}
        <span>{formatRelativeTime(event.created_at)}</span>
      </div>
      <details className="activity-row-details">
        <summary>Structured event</summary>
        <dl className="definition-list definition-list--compact">
          <dt>Request ID</dt>
          <dd><code>{event.request_id || "-"}</code></dd>
          <dt>Correlation ID</dt>
          <dd><code>{event.correlation_id || "-"}</code></dd>
          <dt>Source</dt>
          <dd>{sourceIp || "-"}</dd>
          <dt>Domain</dt>
          <dd>{event.domain || "-"}{event.domain_event_id ? ` / ${event.domain_event_id}` : ""}</dd>
          <dt>Time</dt>
          <dd>{formatDateTime(event.created_at)}</dd>
        </dl>
        <pre className="json-block">{compactJson({
          actor: event.actor,
          target: event.target,
          source: event.source,
          http: event.http,
          security: event.security,
          raw: event.raw,
        })}</pre>
      </details>
    </article>
  );
}

function AbuseClientActivityRow({
  client,
  unblocking,
  onUnblock,
}: {
  client: WebhookAbuseClientRow;
  unblocking: boolean;
  onUnblock: () => void;
}) {
  return (
    <article className="activity-row">
      <div className="activity-row-main">
        <StatusBadge
          label={abuseStatusLabel(client.status)}
          title={abuseStatusTooltip(client.status)}
          tone={client.status === "blocked" ? "warn" : "neutral"}
        />
        <div className="activity-row-copy">
          <strong>{client.clientHost || "Unknown webhook client"}</strong>
          <span>
            {abuseReasonLabel(client.lastReason)} · {client.failureCount} failed attempts
            {client.blockedUntil ? ` · blocked until ${formatDateTime(client.blockedUntil)}` : ""}
          </span>
        </div>
      </div>
      <div className="activity-row-meta">
        <span>{formatRelativeTime(client.lastSeen)}</span>
        {client.status === "blocked" ? (
          <button
            className="secondary-button secondary-button--small"
            type="button"
            disabled={unblocking}
            title="Remove the active block and clear current failed attempts. Previous block history is kept."
            onClick={onUnblock}
          >
            {unblocking ? "Unblocking..." : "Unblock"}
          </button>
        ) : null}
      </div>
      <details className="activity-row-details">
        <summary>Technical details</summary>
        <dl className="definition-list definition-list--compact">
          <dt>Client fingerprint</dt>
          <dd><code>{client.clientFingerprint || "-"}</code></dd>
          <dt>Activity</dt>
          <dd>{client.activityLabel}</dd>
          <dt>Route fingerprints</dt>
          <dd>{client.routeFingerprints.length ? client.routeFingerprints.map((value) => `route ${value}`).join(", ") : "all routes"}</dd>
          <dt>Blocked until</dt>
          <dd>{client.blockedUntil ? formatDateTime(client.blockedUntil) : "-"}</dd>
          <dt>Previous blocks</dt>
          <dd>{client.blockCount}</dd>
          <dt>Tracked records</dt>
          <dd>{client.bucketCount}</dd>
        </dl>
      </details>
    </article>
  );
}

function AuditActivityRow({ event }: { event: AuditEventOut }) {
  return (
    <article className="activity-row">
      <div className="activity-row-main">
        <span className="activity-dot" aria-hidden="true" />
        <div className="activity-row-copy">
          <strong>{humanizeLogToken(event.action)}</strong>
          <span><code>{event.action}</code> by {formatAuditActor(event)}</span>
        </div>
      </div>
      <div className="activity-row-meta">
        <span>{formatRelativeTime(event.created_at)}</span>
        <span>{formatDateTime(event.created_at)}</span>
      </div>
      <details className="activity-row-details">
        <summary>Metadata</summary>
        <pre className="json-block">{compactJson(event.metadata)}</pre>
      </details>
    </article>
  );
}

function BotActivityRow({ event }: { event: SystemLogEventOut }) {
  return (
    <article className="activity-row">
      <div className="activity-row-main">
        <StatusBadge label={event.scope || "unknown"} tone={event.scope === "channel" ? "success" : "neutral"} />
        <div className="activity-row-copy">
          <strong>{humanizeLogToken(event.activity_type || "activity")}</strong>
          <span>{systemLogConversation(event)} · {event.user_name || "Unknown user"}</span>
        </div>
      </div>
      <div className="activity-row-meta">
        <StatusBadge label={systemLogAuthLabel(event)} tone={event.auth_status === "verified" ? "success" : "neutral"} />
        <span>{formatRelativeTime(event.created_at)}</span>
      </div>
      <details className="activity-row-details">
        <summary>Bot payload context</summary>
        <dl className="definition-list definition-list--compact">
          <dt>Conversation</dt>
          <dd><code>{event.conversation_id || "-"}</code></dd>
          <dt>Conversation type</dt>
          <dd>{event.conversation_type || "-"}</dd>
          <dt>Graph user</dt>
          <dd><code>{event.graph_user_id || "-"}</code></dd>
          <dt>Tenant</dt>
          <dd><code>{event.tenant_id || "-"}</code></dd>
          <dt>Auth validated</dt>
          <dd>{event.auth_validated_at ? formatDateTime(event.auth_validated_at) : "legacy or unavailable"}</dd>
          <dt>Service URL</dt>
          <dd><code>{event.service_url || "-"}</code></dd>
        </dl>
      </details>
    </article>
  );
}

function humanizeLogToken(value: string): string {
  return value
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .split(/[._\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function eventLevelTone(level: string): "neutral" | "success" | "warn" | "danger" {
  if (level === "critical" || level === "error") return "danger";
  if (level === "warning") return "warn";
  if (level === "info") return "success";
  return "neutral";
}

function eventCategoryTone(category: string): "neutral" | "success" | "warn" | "danger" {
  if (category === "security" || category === "system") return "warn";
  if (category === "webhook" || category === "integration") return "success";
  return "neutral";
}

function eventActorLabel(event: EventLogEntryOut): string {
  const type = stringField(event.actor, "type");
  const name = stringField(event.actor, "displayName");
  const id = stringField(event.actor, "id");
  if (name !== "-") return `${type !== "-" ? type : "actor"} ${name}`;
  if (id !== "-") return `${type !== "-" ? type : "actor"} ${id.slice(0, 8)}`;
  return "";
}

function eventTargetLabel(event: EventLogEntryOut): string {
  const type = stringField(event.target, "type");
  const name = stringField(event.target, "name");
  const id = stringField(event.target, "id");
  if (name !== "-") return `${type !== "-" ? type : "target"} ${name}`;
  if (id !== "-") return `${type !== "-" ? type : "target"} ${id.slice(0, 12)}`;
  return "";
}

function formatAuditActor(event: AuditEventOut): string {
  return `${event.actor_type}${event.actor_id ? `:${event.actor_id.slice(0, 8)}` : ""}`;
}

function systemLogConversation(event: SystemLogEventOut): string {
  if (event.team_name && event.channel_name) return `${event.team_name} / ${event.channel_name}`;
  return event.channel_name || event.team_name || shortId(event.conversation_id) || "-";
}

function systemLogAuthLabel(event: SystemLogEventOut): string {
  if (event.auth_status === "verified" && event.auth_service_url_matched) return "Verified";
  if (event.auth_status === "verified") return "Verified";
  return event.auth_status || "unknown";
}

function abuseReasonLabel(reason: string): string {
  switch (reason) {
    case "delivery_backend_disabled":
      return "Delivery backend disabled";
    case "invalid_payload":
      return "Invalid payload";
    case "payload_too_large":
      return "Payload too large";
    case "route_disabled":
      return "Route disabled";
    case "unknown_route":
      return "Unknown route";
    case "client_ip_not_allowed":
      return "Client IP not allowed";
    default:
      return reason || "-";
  }
}

function abuseStatusLabel(status: "watching" | "blocked"): string {
  return status === "blocked" ? "Blocked" : "Observed";
}

function abuseStatusTooltip(status: "watching" | "blocked"): string {
  if (status === "blocked") return "This client is currently blocked and receives 429 responses.";
  return "Failed attempts were seen, but this client is not currently blocked.";
}

type WebhookAbuseClientRow = {
  key: string;
  buckets: WebhookAbuseBucketOut[];
  status: "watching" | "blocked";
  clientHost: string;
  clientFingerprint: string;
  routeFingerprints: string[];
  failureCount: number;
  blockCount: number;
  bucketCount: number;
  lastReason: string;
  blockedUntil: string | null;
  lastSeen: string;
  activityLabel: string;
};

function buildWebhookAbuseClients(buckets: WebhookAbuseBucketOut[]): WebhookAbuseClientRow[] {
  const grouped = new Map<string, WebhookAbuseBucketOut[]>();
  for (const bucket of buckets) {
    const key = `${bucket.client_host || ""}:${bucket.client_fingerprint}`;
    grouped.set(key, [...(grouped.get(key) ?? []), bucket]);
  }

  return Array.from(grouped.entries())
    .map(([key, rows]) => {
      const sortedBySeen = [...rows].sort((a, b) => timestampMs(b.last_seen_at) - timestampMs(a.last_seen_at));
      const blockedBuckets = rows.filter((bucket) => bucket.status === "blocked" && bucket.blocked_until);
      const blockedUntil = latestDate(blockedBuckets.map((bucket) => bucket.blocked_until).filter((value): value is string => Boolean(value)));
      const routeFingerprints = Array.from(new Set(rows.map((bucket) => bucket.route_token_fingerprint).filter(Boolean)));
      const hasAllRoutes = rows.some((bucket) => !bucket.route_token_fingerprint);
      const failureCount = rows.reduce((sum, bucket) => sum + bucket.failure_count, 0);
      return {
        key,
        buckets: rows,
        status: blockedBuckets.length ? "blocked" : "watching",
        clientHost: sortedBySeen[0]?.client_host ?? "",
        clientFingerprint: sortedBySeen[0]?.client_fingerprint ?? "",
        routeFingerprints,
        failureCount,
        blockCount: rows.reduce((sum, bucket) => sum + bucket.block_count, 0),
        bucketCount: rows.length,
        lastReason: sortedBySeen.find((bucket) => bucket.last_reason)?.last_reason ?? "",
        blockedUntil,
        lastSeen: sortedBySeen[0]?.last_seen_at ?? "",
        activityLabel: abuseActivityLabel(hasAllRoutes, routeFingerprints.length),
      } satisfies WebhookAbuseClientRow;
    })
    .filter((client) => client.status === "blocked" || client.failureCount > 0)
    .sort((a, b) => {
      if (a.status !== b.status) return a.status === "blocked" ? -1 : 1;
      return timestampMs(b.lastSeen) - timestampMs(a.lastSeen);
    });
}

function abuseActivityLabel(hasAllRoutes: boolean, routeCount: number): string {
  const parts: string[] = [];
  if (hasAllRoutes) parts.push("All routes");
  if (routeCount === 1) parts.push("1 route");
  if (routeCount > 1) parts.push(`${routeCount} routes`);
  return parts.join(" + ") || "-";
}

function latestDate(values: string[]): string | null {
  if (!values.length) return null;
  return values.reduce((latest, value) => (timestampMs(value) > timestampMs(latest) ? value : latest));
}

function timestampMs(value: string): number {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function InnerApp() {
  const { session } = useAppContext();
  if (session.status === "booting") return <LoadingScreen label="Loading workspace" />;
  if (session.status === "setup") return <FirstAdminSetupScreen />;
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
