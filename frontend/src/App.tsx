import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type FocusEvent, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  Bot,
  Check,
  CheckCircle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardCopy,
  Eye,
  EyeOff,
  FileClock,
  Info,
  Menu,
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
  Settings as SettingsIcon,
  ShieldAlert,
  Trash2,
  Wrench,
  Webhook,
  X,
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
  BotAccessRoleCreate,
  BotAccessRoleOut,
  BotAccessRoleUpdate,
  BotAuthorizedGroupCreate,
  BotAuthorizedGroupOut,
  BotAuthorizedUserCreate,
  BotAuthorizedUserOut,
  BotUserPermissions,
  BotUserRole,
  BotConversationReferenceDetailOut,
  BotConversationReferenceOut,
  ClientIpAccessMode,
  DeliveryAuthRefreshOut,
  DeliveryBackend,
  EventLogEntryOut,
  EventLogEntryPageOut,
  GraphDeliveryOAuthPendingOut,
  GraphTargetKind,
  OAuthDiagnosticsOut,
  SettingItemOut,
  SystemLogEventOut,
  TeamsGroupMember,
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

type RouteName = "dashboard" | "webhooks" | "payload-generator" | "delivery" | "users" | "settings" | "logs" | "system-logs";
type DeliveryStatusFilter = "all" | WebhookDeliveryStatus;
type PayloadGeneratorMode = "text" | "adaptive";
type PayloadAccent = "neutral" | "success" | "warning" | "critical";
type PayloadImageSize = "Auto" | "Stretch";
type PayloadTitleSize = "Default" | "Medium" | "Large";
type PayloadTitleWeight = "Default" | "Bolder";
type SystemLogTab = "timeline" | "security" | "audit" | "bot";
type UserAdminTab = "app-users" | "bot-access";

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

type ResponsiveActionItem = RowActionItem & {
  buttonTone?: "primary" | "secondary" | "danger";
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

function ResponsiveActionBar({ items, moreLabel }: { items: ResponsiveActionItem[]; moreLabel: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const [visibleCount, setVisibleCount] = useState(items.length);
  const overflowItems = items.slice(visibleCount);

  useLayoutEffect(() => {
    const container = containerRef.current;
    const measure = measureRef.current;
    if (!container || !measure) return;
    const actionContainer = container;
    const actionMeasure = measure;

    function calculateVisibleCount() {
      const containerWidth = actionContainer.clientWidth;
      const measuredActions = Array.from(actionMeasure.querySelectorAll<HTMLElement>("[data-measure-action]"));
      const measuredMenu = actionMeasure.querySelector<HTMLElement>("[data-measure-menu]");
      if (!containerWidth || measuredActions.length !== items.length || !measuredMenu) return;

      const styles = window.getComputedStyle(actionContainer);
      const gap = Number.parseFloat(styles.columnGap || styles.gap || "0") || 0;
      const actionWidths = measuredActions.map((action) => Math.ceil(action.getBoundingClientRect().width));
      const menuWidth = Math.ceil(measuredMenu.getBoundingClientRect().width);
      const availableWidth = Math.floor(actionContainer.getBoundingClientRect().width) - 4;
      const fullWidth = actionWidths.reduce((total, width) => total + width, 0) + Math.max(0, items.length - 1) * gap;

      let nextVisibleCount = items.length;
      if (fullWidth <= availableWidth) {
        setVisibleCount((current) => (current === items.length ? current : items.length));
        return;
      }

      for (let count = items.length - 1; count >= 0; count -= 1) {
        const visibleWidths = actionWidths.slice(0, count).reduce((total, width) => total + width, 0);
        const shownItems = count + 1;
        const totalGap = Math.max(0, shownItems - 1) * gap;
        const totalWidth = visibleWidths + menuWidth + totalGap;
        if (totalWidth <= availableWidth) {
          nextVisibleCount = count;
          break;
        }
      }

      setVisibleCount((current) => (current === nextVisibleCount ? current : nextVisibleCount));
    }

    calculateVisibleCount();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", calculateVisibleCount);
      return () => window.removeEventListener("resize", calculateVisibleCount);
    }
    const observer = new ResizeObserver(calculateVisibleCount);
    observer.observe(actionContainer);
    return () => observer.disconnect();
  }, [items]);

  useEffect(() => {
    setVisibleCount((current) => Math.min(current, items.length));
  }, [items.length]);

  return (
    <div className="responsive-action-bar" ref={containerRef}>
      {items.slice(0, visibleCount).map((item) => (
        <RouteActionButton item={item} key={item.label} />
      ))}
      {overflowItems.length ? <RowActionMenu label={moreLabel} items={overflowItems} /> : null}
      <div className="responsive-action-bar-measure" ref={measureRef} aria-hidden="true">
        {items.map((item) => (
          <RouteActionButton item={item} key={item.label} measure />
        ))}
        <button className="icon-button" type="button" data-measure-menu tabIndex={-1}>
          <MoreHorizontal aria-hidden="true" className="button-icon" focusable="false" />
        </button>
      </div>
    </div>
  );
}

function RouteActionButton({ item, measure = false }: { item: ResponsiveActionItem; measure?: boolean }) {
  const Icon = item.icon;
  const tone = item.buttonTone || "secondary";
  return (
    <button
      className={classNames(
        tone === "primary" ? "primary-button" : tone === "danger" ? "danger-button" : "secondary-button",
        "button-with-icon",
        "route-action-button",
      )}
      type="button"
      disabled={item.disabled}
      onClick={item.onClick}
      data-measure-action={measure || undefined}
      tabIndex={measure ? -1 : undefined}
    >
      <Icon aria-hidden="true" className={classNames("button-icon", item.spinning && "button-icon--spin")} focusable="false" />
      {item.label}
    </button>
  );
}

function EmptyGuidance({ title, body }: { title: string; body?: string }) {
  return (
    <div className="empty-guidance">
      <strong>{title}</strong>
      {body ? <p>{body}</p> : null}
    </div>
  );
}

function AppLogo() {
  return (
    <span className="app-logo" aria-hidden="true">
      <img className="app-logo-image app-logo-image--light" src="/brand/logo-light.png" alt="" />
      <img className="app-logo-image app-logo-image--dark" src="/brand/logo-dark.png" alt="" />
    </span>
  );
}

function routeFromPath(pathname: string): RouteName {
  if (pathname === "/" || pathname === "/dashboard") return "dashboard";
  if (pathname === "/webhooks" || pathname.startsWith("/webhooks/")) return "webhooks";
  if (pathname === "/payload-generator") return "payload-generator";
  if (pathname === "/delivery") return "delivery";
  if (pathname === "/users") return "users";
  if (pathname === "/settings" || pathname.startsWith("/settings/")) return "settings";
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
          <AppLogo />
          <ThemeToggle />
        </div>
        <div>
          <h1>Teams Rehook</h1>
          <p className="lede">Sign in to continue.</p>
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
          <AppLogo />
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
  const revealToken = useMemo(() => new URLSearchParams(window.location.search).get("token") ?? "", []);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [routeName, setRouteName] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [loading, setLoading] = useState(Boolean(revealToken));
  const [error, setError] = useState(revealToken ? "" : "This webhook URL link is missing or expired.");
  const [status, setStatus] = useState("");
  const [copied, setCopied] = useState(false);
  const copiedTimer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (!revealToken) return;
    let cancelled = false;
    async function loadReveal() {
      setLoading(true);
      setError("");
      try {
        const reveal = await api.webhookUrlReveal(revealToken);
        if (cancelled) return;
        setWebhookUrl(reveal.webhook_url);
        setRouteName(reveal.route_name);
        setExpiresAt(reveal.expires_at);
      } catch (err) {
        if (cancelled) return;
        setWebhookUrl("");
        setRouteName("");
        setExpiresAt("");
        setError(isApiError(err) ? err.message : "This webhook URL link is invalid or expired.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadReveal();
    return () => {
      cancelled = true;
    };
  }, [revealToken]);

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
          <AppLogo />
          <ThemeToggle />
        </div>
        <div>
          <p className="eyebrow">Teams Rehook</p>
          <h1>Copy webhook URL</h1>
          {routeName ? <p className="copy-route-name">{routeName}</p> : null}
        </div>
        <div className="copy-url-field">
          <label htmlFor="webhook-copy-url">Webhook URL</label>
          <input
            id="webhook-copy-url"
            ref={inputRef}
            readOnly
            value={webhookUrl}
            placeholder={loading ? "Loading webhook URL..." : "No webhook URL available"}
            onFocus={(event) => event.currentTarget.select()}
          />
        </div>
        <button
          className={`primary-button button-with-icon copy-url-button${copied ? " is-copied" : ""}`}
          type="button"
          disabled={loading || !webhookUrl}
          onClick={() => void copyWebhookUrl()}
        >
          <span className="copy-url-button-label" key={copied ? "copied" : "idle"}>
            {loading ? (
              <>
                <RefreshCw aria-hidden="true" className="button-icon button-icon--spin" focusable="false" />
                Loading
              </>
            ) : copied ? (
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
        {error ? (
          <p className="copy-status copy-status--error" role="alert">
            {error}
          </p>
        ) : expiresAt ? (
          <p className="copy-status" role="status">
            This reveal link expires {formatDateTime(expiresAt)}.
          </p>
        ) : null}
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
  const [path, setPath] = useState(() => window.location.pathname);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const route = routeFromPath(path);

  useEffect(() => {
    if (path !== "/status") return;
    window.history.replaceState(null, "", "/dashboard");
    setPath("/dashboard");
  }, [path]);

  useEffect(() => {
    const onPop = () => {
      setPath(window.location.pathname);
      setSidebarOpen(false);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    if (!sidebarOpen) return undefined;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSidebarOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [sidebarOpen]);

  function navigate(path: string) {
    window.history.pushState(null, "", path);
    setPath(path);
    setSidebarOpen(false);
  }

  if (session.status !== "authenticated") return null;

  return (
    <div className="app-shell">
      <button
        className={classNames("sidebar-backdrop", sidebarOpen && "sidebar-backdrop--open")}
        type="button"
        aria-label="Dismiss menu overlay"
        onClick={() => setSidebarOpen(false)}
      />
      <aside className={classNames("sidebar", sidebarOpen && "sidebar--open")} id="app-sidebar">
        <div className="brand-row">
          <AppLogo />
          <div>
            <strong>Teams Rehook</strong>
            <span>Webhook Relay</span>
          </div>
          <button className="sidebar-close" type="button" aria-label="Close navigation" onClick={() => setSidebarOpen(false)}>
            <X aria-hidden="true" />
          </button>
        </div>
        <nav className="nav-list" aria-label="Primary navigation">
          {NAV.map((item) => (
            <button
              key={item.route}
              type="button"
              className={classNames("nav-link", route === item.route && "nav-link--active")}
              onClick={() => navigate(item.path)}
            >
              <span aria-hidden="true">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-theme-control">
          <span>Theme</span>
          <ThemeToggle id="sidebar-theme-toggle" />
        </div>
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
          <div className="topbar-spacer" />
          <button
            className="sidebar-toggle"
            type="button"
            aria-controls="app-sidebar"
            aria-expanded={sidebarOpen}
            onClick={() => setSidebarOpen(true)}
          >
            <Menu aria-hidden="true" />
            <span>Menu</span>
          </button>
        </header>
        {route === "dashboard" ? <DashboardPage /> : null}
        {route === "webhooks" ? <WebhooksPage /> : null}
        {route === "payload-generator" ? <PayloadGeneratorPage /> : null}
        {route === "delivery" ? <DeliveryMethodsPage /> : null}
        {route === "users" ? <UsersPage /> : null}
        {route === "settings" ? path.startsWith("/settings/graph-delivery/") ? <GraphDeliveryOAuthPage /> : <SettingsPage /> : null}
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
      <PageIntro title="Dashboard" />
      <div className="metric-grid">
        <Card className="metric-card">
          <div className="metric-card__head">
            <span className="metric-icon" aria-hidden="true">
              <Webhook size={18} strokeWidth={2} />
            </span>
            <span className="metric-label">Routes</span>
          </div>
          <strong className="metric-value">{metricValue(counts.routes)}</strong>
        </Card>
        <Card className="metric-card">
          <div className="metric-card__head">
            <span className="metric-icon" aria-hidden="true">
              <Radio size={18} strokeWidth={2} />
            </span>
            <span className="metric-label">Active</span>
          </div>
          <strong className="metric-value">{metricValue(counts.active)}</strong>
        </Card>
        <Card className={classNames("metric-card", !loading && !error && counts.attention > 0 ? "metric-card--alert" : null)}>
          <div className="metric-card__head">
            <span className="metric-icon" aria-hidden="true">
              <AlertTriangle size={18} strokeWidth={2} />
            </span>
            <span className="metric-label">Delivery issues</span>
          </div>
          <strong className="metric-value">{metricValue(counts.attention)}</strong>
        </Card>
        <Card className="metric-card">
          <div className="metric-card__head">
            <span className="metric-icon" aria-hidden="true">
              <MessagesSquare size={18} strokeWidth={2} />
            </span>
            <span className="metric-label">Conversations</span>
          </div>
          <strong className="metric-value">{metricValue(counts.conversations)}</strong>
        </Card>
      </div>
      <div className="attention-grid">
        <Card title="Delivery issues">
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
            <EmptyGuidance title="No delivery issues" />
          )}
        </Card>
        <Card title="Setup">
          <ul className="compact-list">
            {!references.length ? (
              <li>
                <strong>No conversations</strong>
                <span>Add the bot, then send one message.</span>
              </li>
            ) : null}
            {untestedRoutes.map((route) => (
              <li key={route.id}>
                <strong>{route.name}</strong>
                <span>Send a test before sharing.</span>
              </li>
            ))}
            {inactiveRoutes.map((route) => (
              <li key={route.id}>
                <strong>{route.name}</strong>
                <span>Disabled.</span>
              </li>
            ))}
            {references.length && !untestedRoutes.length && !inactiveRoutes.length ? (
              <li>
                <strong>Setup complete</strong>
              </li>
            ) : null}
          </ul>
        </Card>
      </div>
      <Card title="Recent routes">
        <DataTable
          className="data-table--dashboard-routes"
          columns={["Route", "Target", "Active", "Last delivery", "Updated"]}
          rows={recentRoutes.map((route) => {
            const target = dashboardRouteTargetDisplay(route);
            return [
              <span className="dashboard-route-name" title={route.name}>
                {route.name}
              </span>,
              <div className="stacked-cell dashboard-target-cell" title={target.full}>
                <span className="dashboard-target-kind">{target.primary}</span>
                {target.secondary ? <span className="dashboard-target-detail">{target.secondary}</span> : null}
              </div>,
              route.is_active ? <StatusBadge label="Active" tone="success" /> : <StatusBadge label="Disabled" tone="warn" />,
              <DeliveryStatusBadge route={route} />,
              formatDateTime(route.updated_at),
            ];
          })}
          emptyTitle="No routes"
          emptyBody="Create a route after the bot has captured a conversation."
          loading={loading}
          loadingLabel="Loading routes..."
          error={error}
          onRetry={() => void refresh()}
          rowKey={(index) => recentRoutes[index]?.id ?? index}
        />
      </Card>
    </>
  );
}

function dashboardRouteTargetDisplay(route: WebhookRouteOut): { primary: string; secondary: string; full: string } {
  const target = webhookTargetPresentation(route);
  const fallback = webhookRouteTargetSecondaryDetail(route, target);
  const full = [target.kindLabel, fallback || target.title || route.target_name].filter(Boolean).join(": ");

  if (target.kindLabel === "Group chat") {
    const memberNames = webhookTargetMemberNames(route).map(compactDashboardPersonName);
    return {
      primary: target.kindLabel,
      secondary: memberNames.length ? compactMemberSummary(memberNames, route.member_count || memberNames.length) : compactDashboardTargetText(fallback),
      full,
    };
  }

  if (target.kindLabel === "1:1 chat") {
    return {
      primary: target.kindLabel,
      secondary: compactDashboardPersonName(fallback || target.title),
      full,
    };
  }

  return {
    primary: target.kindLabel,
    secondary: compactDashboardTargetText(fallback || target.title || route.target_name),
    full,
  };
}

function compactDashboardPersonName(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return trimmed.split(" - ")[0]?.trim() || trimmed;
}

function compactDashboardTargetText(value: string): string {
  return value.trim().replace(/\s+\+\s+(\d+)$/, " +$1");
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
  targetPresentation: WebhookTargetPresentation;
  deliveryLabel: string;
  lastActivityLabel: string;
  topIssue: string;
  topIssueDetail: string;
  featureEnabled: boolean;
  facts: StatusFact[];
  technicalRows: StatusTechnicalRow[];
};

type WebhookTargetPresentation = {
  kindLabel: string;
  title: string;
  subtitle: string;
};

type WebhookTargetTableDisplay = {
  primary: string;
  secondary: string;
};

function buildWebhookRouteView(route: WebhookRouteOut, policy: DeliveryFeaturePolicy): WebhookRouteView {
  const featureEnabled = routeDeliveryFeatureEnabled(route, policy);
  const deliveryLabel = route.last_delivery_status ? capitalize(route.last_delivery_status) : "Not tested";
  const lastActivityLabel = route.last_delivery_at ? formatRelativeTime(route.last_delivery_at) : "No delivery yet";
  const tone = webhookRouteTone(route, featureEnabled);
  const statusLabel = webhookRouteStatusLabel(route, featureEnabled);
  const topIssue = webhookRouteTopIssue(route, featureEnabled);
  const targetPresentation = webhookTargetPresentation(route);

  return {
    route,
    tone,
    statusLabel,
    summary: route.is_active
      ? featureEnabled
        ? `Accepts relay requests for ${route.target_name || "the selected Teams target"}.`
        : "Route is active, but its delivery feature is disabled."
      : "Route is disabled and rejects incoming webhook requests.",
    targetPresentation,
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

function webhookTargetPresentation(route: WebhookRouteOut): WebhookTargetPresentation {
  const kindLabel = webhookTargetKindLabel(route);
  const targetName = route.target_name.trim();
  const memberSummary = route.member_summary.trim();
  const graphUserDisplayName = route.graph_user_display_name.trim();
  const graphUserPrincipalName = route.graph_user_principal_name.trim();
  const graphTeamName = route.graph_team_name.trim();
  const graphTargetId = route.graph_target_id.trim();

  if (kindLabel === "Group chat") {
    const title = memberSummary || nonGenericTargetName(targetName, ["group chat", "teams group chat", "chat"]) || "Group chat";
    return {
      kindLabel,
      title,
      subtitle: title === kindLabel ? "" : kindLabel,
    };
  }

  if (kindLabel === "1:1 chat") {
    const title = nonGenericTargetName(targetName, ["1:1 chat", "one-on-one chat", "teams 1:1 chat"]) || graphUserDisplayName || memberSummary || "1:1 chat";
    return {
      kindLabel,
      title,
      subtitle: graphUserPrincipalName || (title === kindLabel ? "" : kindLabel),
    };
  }

  if (kindLabel === "Channel") {
    const title = targetName || graphTeamName || "Teams channel";
    const subtitle = graphTeamName && graphTeamName !== title && !title.includes(graphTeamName) ? graphTeamName : "Channel";
    return {
      kindLabel,
      title,
      subtitle: subtitle === title ? "" : subtitle,
    };
  }

  if (kindLabel === "Team") {
    const title = targetName || graphTeamName || "Team";
    return {
      kindLabel,
      title,
      subtitle: title === kindLabel ? "" : kindLabel,
    };
  }

  const title = targetName || graphTeamName || graphUserDisplayName || graphTargetId || kindLabel;
  return {
    kindLabel,
    title,
    subtitle: title === kindLabel ? "" : kindLabel,
  };
}

function webhookRouteTargetTableDisplay(view: WebhookRouteView): WebhookTargetTableDisplay {
  const route = view.route;
  const target = view.targetPresentation;
  const secondary = webhookRouteTargetSecondaryDetail(route, target);

  return {
    primary: target.kindLabel,
    secondary: secondary || target.title || route.target_name.trim() || target.subtitle || target.kindLabel,
  };
}

function webhookRouteTargetSecondaryDetail(route: WebhookRouteOut, target: WebhookTargetPresentation): string {
  const targetName = route.target_name.trim();

  if (target.kindLabel === "Group chat") {
    const memberNames = webhookTargetMemberNames(route);
    if (memberNames.length) return compactMemberSummary(memberNames, route.member_count || memberNames.length);
    return nonGenericTargetName(target.title, ["group chat", "teams group chat", "chat"]) || targetName;
  }

  if (target.kindLabel === "1:1 chat") {
    return (
      nonGenericTargetName(target.title, ["1:1 chat", "one-on-one chat", "teams 1:1 chat"]) ||
      route.graph_user_display_name.trim() ||
      route.graph_user_principal_name.trim() ||
      targetName
    );
  }

  if (target.kindLabel === "Channel") {
    return target.title || route.graph_channel_id.trim() || targetName;
  }

  if (target.kindLabel === "Team") {
    return target.title || route.graph_team_name.trim() || targetName;
  }

  return target.title || target.subtitle || targetName;
}

function compactMemberSummary(memberNames: string[], totalCount: number): string {
  const uniqueNames = Array.from(new Set(memberNames.map((name) => name.trim()).filter(Boolean)));
  const visibleNames = uniqueNames.slice(0, 2);
  const remaining = Math.max(totalCount || uniqueNames.length, uniqueNames.length) - visibleNames.length;
  return [visibleNames.join(", "), remaining > 0 ? `+${remaining}` : ""].filter(Boolean).join(" ");
}

function nonGenericTargetName(value: string, genericLabels: string[]): string {
  const normalized = value.trim().toLowerCase();
  return normalized && !genericLabels.includes(normalized) ? value.trim() : "";
}

function webhookUrlPreview(url: string): string {
  try {
    const parsed = new URL(url);
    const parts = parsed.pathname.split("/").filter(Boolean);
    const token = parts.length ? parts[parts.length - 1] : "";
    const tokenPreview = token.length > 18 ? `${token.slice(0, 10)}...${token.slice(-6)}` : token;
    return `${parsed.origin}/${parts.slice(0, -1).join("/")}/${tokenPreview}`;
  } catch {
    return url.length > 48 ? `${url.slice(0, 30)}...${url.slice(-12)}` : url;
  }
}

function webhookRouteBackendTableLabel(backend: DeliveryBackend): string {
  return backend === "graph" ? "Graph Delivery" : "Bot Framework";
}

function webhookTargetKindLabel(route: WebhookRouteOut): string {
  if (route.delivery_backend === "graph") {
    if (route.graph_target_kind === "channel") return "Channel";
    if (route.graph_target_kind === "chat") return route.graph_user_id || route.graph_user_display_name || route.graph_user_principal_name ? "1:1 chat" : "Group chat";
    if (route.graph_target_kind === "user") return "1:1 chat";
    if (route.graph_target_kind === "team") return "Team";
    return "Graph target";
  }
  const targetName = route.target_name.toLowerCase();
  const summary = route.member_summary.toLowerCase();
  if (targetName.includes(" / ") || route.graph_channel_id) return "Channel";
  if (route.member_count > 2 || summary.includes(",") || summary.includes(" members")) return "Group chat";
  if (route.member_count > 0 && route.member_count <= 2) return "1:1 chat";
  return "1:1 chat";
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

function currentWebhookRouteId(): string {
  const match = window.location.pathname.match(/^\/webhooks\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]) : "";
}

function currentBotConversationReferenceId(): string {
  const match = window.location.pathname.match(/^\/webhooks\/conversations\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]) : "";
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
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";
  const conversationReferenceId = currentBotConversationReferenceId();
  const routeDetailId = currentWebhookRouteId();

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
      if (currentWebhookRouteId() === route.id) navigateInApp("/webhooks");
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

  async function refreshRouteGraphData(route: WebhookRouteOut) {
    const errors: string[] = [];
    let memberSummary = "";
    let namesChanged = false;
    setRefreshingMembersId(route.id);
    setRefreshingRouteNameId(route.id);
    try {
      const updated = await api.refreshWebhookRouteMembers(csrfToken, route.id);
      if (updated.members_lookup_error) {
        errors.push(updated.members_lookup_error);
      } else {
        memberSummary = updated.member_summary || `${updated.member_count} members`;
      }
    } catch (err) {
      errors.push(isApiError(err) ? err.message : "The member list could not be refreshed.");
    }

    try {
      const result = await api.refreshSingleWebhookRouteGraphNames(csrfToken, route.id);
      if (!result.ok) {
        errors.push(result.error || "Microsoft Graph could not resolve the route name.");
      } else {
        namesChanged = result.routes_updated > 0;
      }
    } catch (err) {
      errors.push(isApiError(err) ? err.message : "Microsoft Graph could not resolve the route name.");
    }

    if (errors.length) {
      notify({
        tone: "error",
        title: "Refresh incomplete",
        description: errors.join(" "),
      });
    } else {
      notify({
        tone: "success",
        title: "Route refreshed",
        description: namesChanged ? "Members and Graph names were updated." : memberSummary || "Route data is already current.",
      });
    }

    try {
      await refresh();
    } finally {
      setRefreshingMembersId("");
      setRefreshingRouteNameId("");
    }
  }

  const routeViews = routes.map((route) => buildWebhookRouteView(route, featurePolicy));
  const selectedRouteView = routeDetailId ? routeViews.find((view) => view.route.id === routeDetailId) ?? null : null;
  const pageTitle = conversationReferenceId ? "Conversation inspector" : routeDetailId && selectedRouteView ? selectedRouteView.route.name : "Webhooks";
  const pageDescription = conversationReferenceId ? "Inspect a captured Teams bot conversation and its linked webhook routes." : routeDetailId && selectedRouteView ? selectedRouteView.summary : undefined;
  const pageEyebrow = conversationReferenceId ? "Bot conversation" : routeDetailId ? "Route workspace" : undefined;

  return (
    <>
      <PageIntro
        eyebrow={pageEyebrow}
        title={pageTitle}
        description={pageDescription}
        actions={
          <div className="row-actions">
            {routeDetailId || conversationReferenceId ? (
              <button className="secondary-button button-with-icon" type="button" onClick={() => navigateInApp("/webhooks")}>
                <ChevronLeft aria-hidden="true" className="button-icon" focusable="false" />
                Back to routes
              </button>
            ) : (
              <>
                <button
                  className="secondary-button button-with-icon"
                  type="button"
                  onClick={() => setViewingBotReferences(true)}
                >
                  <MessageSquareText aria-hidden="true" className="button-icon" focusable="false" />
                  Conversations
                </button>
                <button
                  className="primary-button button-with-icon"
                  type="button"
                  onClick={() => setEditing(emptyWebhookRoute(botDefaultServiceUrl))}
                >
                  <Plus aria-hidden="true" className="button-icon" focusable="false" />
                  New
                </button>
              </>
            )}
          </div>
        }
      />
      {conversationReferenceId ? (
        <BotConversationReferenceDetailPage
          referenceId={conversationReferenceId}
          csrfToken={csrfToken}
          onCreateRoute={(reference) => setEditing(webhookRouteFromReference(reference))}
          onDeleted={() => {
            void refresh();
            navigateInApp("/webhooks");
          }}
        />
      ) : routeDetailId ? (
        <WebhookRouteDetailPage
          error={error}
          featurePolicy={featurePolicy}
          loading={loading}
          onCopyRoute={(route) => void copyText(route.webhook_url ?? "", route.name)}
          onDeleteRoute={setConfirmingDelete}
          onEditRoute={setEditing}
          onRefreshRouteData={(route) => void refreshRouteGraphData(route)}
          onRegenerateRoute={setConfirmingRegeneration}
          onRetry={() => void refresh()}
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
      ) : (
        <div className="webhooks-command-center">
          <WebhookRouteSummary routeViews={routeViews} loading={loading} />
          <WebhookRouteOverviewTable
            error={error}
            loading={loading}
            onCopyRoute={(route) => void copyText(route.webhook_url ?? "", route.name)}
            onCreateRoute={() => setEditing(emptyWebhookRoute(botDefaultServiceUrl))}
            onEditRoute={setEditing}
            onOpenRoute={(routeId) => navigateInApp(`/webhooks/${encodeURIComponent(routeId)}`)}
            onRetry={() => void refresh()}
            onTestRoute={(route) => void testRoute(route)}
            routeViews={routeViews}
            testingId={testingId}
          />
        </div>
      )}
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
          onInspect={(reference) => {
            navigateInApp(`/webhooks/conversations/${encodeURIComponent(reference.id)}`);
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
        tone="neutral"
      />
      <StatusOverviewMetric
        label="Active"
        value={loading ? "..." : `${activeCount}/${routeViews.length || 0}`}
        tone={routeViews.length && activeCount === routeViews.length ? "success" : activeCount ? "warn" : "neutral"}
      />
      <StatusOverviewMetric
        label="Issues"
        value={loading ? "..." : attentionCount ? String(attentionCount) : "None"}
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

function WebhookRouteOverviewTable({
  error,
  loading,
  onCopyRoute,
  onCreateRoute,
  onEditRoute,
  onOpenRoute,
  onRetry,
  onTestRoute,
  routeViews,
  testingId,
}: {
  error: string;
  loading: boolean;
  onCopyRoute: (route: WebhookRouteOut) => void;
  onCreateRoute: () => void;
  onEditRoute: (route: WebhookRouteOut) => void;
  onOpenRoute: (routeId: string) => void;
  onRetry: () => void;
  onTestRoute: (route: WebhookRouteOut) => void;
  routeViews: WebhookRouteView[];
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
    <section className="webhook-route-console webhook-route-console--overview" aria-label="Relay route console">
      <div className="webhook-route-console-header">
        <div>
          <h2>Routes</h2>
        </div>
        <span>{routeViews.length} routes</span>
      </div>
      <div className="webhook-route-table" role="table" aria-label="Webhook relay routes">
        <div className="webhook-route-table-head" role="row">
          <span>Name</span>
          <span>Target</span>
          <span>Status</span>
          <span>Last activity</span>
          <span>Delivery</span>
          <span aria-label="Actions" />
        </div>
        {routeViews.map((view) => (
          <WebhookRouteTableRow
            key={view.route.id}
            onCopyRoute={onCopyRoute}
            onEditRoute={onEditRoute}
            onOpenRoute={onOpenRoute}
            onTestRoute={onTestRoute}
            testing={testingId === view.route.id}
            view={view}
          />
        ))}
      </div>
    </section>
  );
}

function WebhookRouteTableRow({
  onCopyRoute,
  onEditRoute,
  onOpenRoute,
  onTestRoute,
  testing,
  view,
}: {
  onCopyRoute: (route: WebhookRouteOut) => void;
  onEditRoute: (route: WebhookRouteOut) => void;
  onOpenRoute: (routeId: string) => void;
  onTestRoute: (route: WebhookRouteOut) => void;
  testing: boolean;
  view: WebhookRouteView;
}) {
  return (
    <article className="webhook-route-table-row" role="row" data-route-id={view.route.id}>
      <button
        aria-label={`Open route ${view.route.name}`}
        className="webhook-route-table-main"
        type="button"
        onClick={() => onOpenRoute(view.route.id)}
      >
        <span className="webhook-route-table-cell webhook-route-table-route">
          <strong>{view.route.name}</strong>
          <small>{webhookRouteBackendTableLabel(view.route.delivery_backend)}</small>
        </span>
        <WebhookRouteTargetCell view={view} />
        <span className="webhook-route-table-cell">
          <span className="webhook-route-status-line">
            <span className={classNames("status-dot", `status-dot--${view.tone}`)} aria-hidden="true" />
            <strong>{view.statusLabel}</strong>
          </span>
          {view.topIssue === "No active issue" ? null : <small>{view.topIssue}</small>}
        </span>
        <span className="webhook-route-table-cell">
          <strong>{view.lastActivityLabel}</strong>
          <small>{view.route.last_delivery_at ? formatDateTime(view.route.last_delivery_at) : "No event recorded"}</small>
        </span>
        <span className="webhook-route-table-cell">
          <strong>{view.statusLabel}</strong>
          <small>{view.deliveryLabel}</small>
        </span>
      </button>
      <div className="webhook-route-table-actions">
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

function WebhookRouteTargetCell({ view }: { view: WebhookRouteView }) {
  const route = view.route;
  const target = view.targetPresentation;
  const display = webhookRouteTargetTableDisplay(view);
  const members = route.members.filter((member) => memberDisplayName(member));
  const detailRows = webhookTargetDetailRows(view);

  return (
    <span className="webhook-route-table-cell webhook-route-target-cell">
      <strong title={display.primary}>{display.primary}</strong>
      <small title={display.secondary}>{display.secondary}</small>
      <span className="webhook-target-popover" aria-hidden="true">
        <span className="webhook-target-popover-title">{target.kindLabel}</span>
        <span className="webhook-target-popover-subtitle">{target.title}</span>
        {members.length ? (
          <span className="webhook-target-member-list">
            {members.slice(0, 8).map((member) => (
              <span className="webhook-target-member" key={member.id || member.aad_object_id || memberDisplayName(member)}>
                <strong>{memberDisplayName(member)}</strong>
                <small>{member.user_principal_name || member.email || member.aad_object_id || "Teams member"}</small>
              </span>
            ))}
            {members.length > 8 ? <span className="webhook-target-popover-note">+{members.length - 8} more members</span> : null}
          </span>
        ) : (
          <span className="webhook-target-detail-list">
            {detailRows.map((row) => (
              <span className="webhook-target-detail-row" key={row.label}>
                <small>{row.label}</small>
                <strong>{row.value}</strong>
              </span>
            ))}
          </span>
        )}
      </span>
    </span>
  );
}

function memberDisplayName(member: WebhookRouteOut["members"][number]): string {
  return member.name || member.user_principal_name || member.email || member.aad_object_id;
}

function WebhookTargetMeta({ route }: { route: WebhookRouteOut }) {
  if (!route.members_refreshed_at && !route.members_lookup_error) return null;

  return (
    <span className="webhook-target-meta">
      {route.members_refreshed_at ? <span>Member list updated {formatRelativeTime(route.members_refreshed_at)}</span> : null}
      {route.members_lookup_error ? <span className="webhook-target-meta-error">{route.members_lookup_error}</span> : null}
    </span>
  );
}

function webhookTargetMemberNames(route: WebhookRouteOut): string[] {
  const members = route.members.filter((member) => memberDisplayName(member));
  if (members.length) {
    return members.map((member) => memberDisplayName(member));
  }

  return route.member_summary
    .split(",")
    .map((name) => name.trim())
    .filter(Boolean);
}

function webhookTargetDetailRows(view: WebhookRouteView): Array<{ label: string; value: string }> {
  const route = view.route;
  const target = view.targetPresentation;
  const rows = [
    { label: "Type", value: target.kindLabel },
    { label: "Target", value: target.title },
  ];
  if (target.subtitle) rows.push({ label: "Context", value: target.subtitle });
  if (route.delivery_backend === "graph") {
    if (route.graph_team_name) rows.push({ label: "Team", value: route.graph_team_name });
    if (route.graph_user_principal_name) rows.push({ label: "User", value: route.graph_user_principal_name });
    if (route.graph_target_id) rows.push({ label: "Graph target", value: shortId(route.graph_target_id) });
  }
  if (route.member_summary) rows.push({ label: "Members", value: route.member_summary });
  if (route.members_refreshed_at) rows.push({ label: "Members refreshed", value: formatRelativeTime(route.members_refreshed_at) });
  if (route.members_lookup_error) rows.push({ label: "Lookup", value: route.members_lookup_error });
  return rows.slice(0, 7);
}

function WebhookRouteDetailPage({
  error,
  featurePolicy,
  loading,
  onCopyRoute,
  onDeleteRoute,
  onEditRoute,
  onRefreshRouteData,
  onRegenerateRoute,
  onRetry,
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
  error: string;
  featurePolicy: DeliveryFeaturePolicy;
  loading: boolean;
  onCopyRoute: (route: WebhookRouteOut) => void;
  onDeleteRoute: (route: WebhookRouteOut) => void;
  onEditRoute: (route: WebhookRouteOut) => void;
  onRefreshRouteData: (route: WebhookRouteOut) => void;
  onRegenerateRoute: (route: WebhookRouteOut) => void;
  onRetry: () => void;
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
  if (loading) {
    return (
      <Card>
        <div className="table-state" role="status" aria-live="polite">
          <div className="spinner spinner--small" aria-hidden="true" />
          <p>Loading route workspace...</p>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <div className="table-state table-state--error" role="alert">
          <h3>Could not load route</h3>
          <p>{error}</p>
          <button className="secondary-button secondary-button--small" type="button" onClick={onRetry}>
            Retry
          </button>
        </div>
      </Card>
    );
  }

  if (!routeView) {
    return (
      <Card>
        <EmptyState title="Route not found" body="This webhook route no longer exists or is not available to the current organization." />
        <div className="form-actions form-actions--start">
          <button className="secondary-button button-with-icon" type="button" onClick={() => navigateInApp("/webhooks")}>
            <ChevronLeft aria-hidden="true" className="button-icon" focusable="false" />
            Back to routes
          </button>
        </div>
      </Card>
    );
  }

  const route = routeView.route;
  const target = routeView.targetPresentation;
  const targetMemberNames = target.kindLabel === "Group chat" ? webhookTargetMemberNames(route) : [];
  const heroTone = routeView.tone;
  const refreshingRouteData = refreshingMembersId === route.id || refreshingRouteNameId === route.id;
  const actionItems: ResponsiveActionItem[] = [
    {
      label: testingId === route.id ? "Testing..." : "Test",
      icon: Send,
      buttonTone: "primary",
      disabled: testingId === route.id || !routeView.featureEnabled,
      onClick: () => onTestRoute(route),
    },
    {
      label: "Edit",
      icon: Pencil,
      onClick: () => onEditRoute(route),
    },
    {
      label: "Logs",
      icon: FileClock,
      onClick: () => onViewLogs(route),
    },
    {
      label: togglingId === route.id ? "Updating..." : route.is_active ? "Disable" : "Enable",
      icon: route.is_active ? PowerOff : Power,
      disabled: togglingId === route.id,
      onClick: () => onToggleRoute(route),
    },
    {
      label: refreshingRouteData ? "Refreshing..." : "Refresh",
      icon: RefreshCw,
      disabled: refreshingRouteData || !featurePolicy.graphLookupEnabled,
      spinning: refreshingRouteData,
      onClick: () => onRefreshRouteData(route),
    },
    {
      label: regeneratingId === route.id ? "Creating URL..." : "New URL",
      icon: RotateCcwKey,
      disabled: regeneratingId === route.id,
      onClick: () => onRegenerateRoute(route),
    },
    {
      label: "Delete route",
      icon: Trash2,
      tone: "danger",
      buttonTone: "danger",
      separated: true,
      onClick: () => onDeleteRoute(route),
    },
  ];

  return (
    <div className="webhook-route-workspace" aria-label={`${route.name} route workspace`}>
      <section className={classNames("status-relay-hero", `status-relay-hero--${heroTone}`)} aria-label="Route health">
        <div className="status-relay-hero-main">
          <div className={classNames("status-relay-indicator", `status-relay-indicator--${heroTone}`)} aria-hidden="true" />
          <div>
            <p className="integration-kicker">Route health</p>
            <h2>{routeView.statusLabel === "Ready" ? "Route is ready for relay traffic" : routeView.topIssue}</h2>
            <p>{routeView.topIssueDetail}</p>
          </div>
        </div>
        <div className="status-relay-metrics">
          <StatusOverviewMetric label="Status" value={routeView.statusLabel} detail={routeView.topIssue} tone={heroTone} />
          <StatusOverviewMetric label="Backend" value={deliveryBackendLabel(route.delivery_backend)} detail={routeView.featureEnabled ? "Delivery feature ready." : "Feature is unavailable."} tone={routeView.featureEnabled ? "success" : "warn"} />
          <StatusOverviewMetric label="Delivery" value={routeView.deliveryLabel} detail={routeView.lastActivityLabel} tone={webhookDeliveryTone(route)} />
          <StatusOverviewMetric label="Access" value={clientIpAccessLabel(route)} detail={route.is_active ? "Accepts incoming requests." : "Incoming requests are paused."} tone={route.is_active ? "success" : "warn"} />
        </div>
      </section>

      {routeView.tone !== "success" ? (
        <div className={classNames("status-detail-alert", routeView.tone === "danger" && "status-detail-alert--danger")}>
          <strong>{routeView.topIssue}</strong>
          <span>{routeView.topIssueDetail}</span>
        </div>
      ) : null}

      <div className="webhook-route-workspace-grid">
        <section className="webhook-route-inspector webhook-route-workspace-card">
          <div className="webhook-route-inspector-header">
            <div>
              <p className="integration-kicker">Overview</p>
              <h2>Operational state</h2>
            </div>
            <div className={classNames("status-health-pill", `status-health-pill--${routeView.tone}`)}>
              <span aria-hidden="true" />
              <strong>{routeView.statusLabel}</strong>
            </div>
          </div>
          <StatusFactList facts={routeView.facts} />
        </section>

        <section className="webhook-route-inspector webhook-route-workspace-card">
          <div className="webhook-route-inspector-section">
            <h3>Target</h3>
            <div className="webhook-target-panel">
              <div>
                <strong>{target.kindLabel === "Group chat" ? target.kindLabel : target.title}</strong>
                {target.kindLabel === "Group chat" ? (
                  targetMemberNames.length ? (
                    <span className="webhook-target-member-inline" aria-label="Group chat members">
                      {targetMemberNames.map((name, index) => (
                        <span className="webhook-target-member-token" key={`${name}-${index}`}>
                          <span>{name}</span>
                          {index < targetMemberNames.length - 1 ? <span aria-hidden="true">·</span> : null}
                        </span>
                      ))}
                    </span>
                  ) : target.title !== target.kindLabel ? (
                    <small>{target.title}</small>
                  ) : null
                ) : target.subtitle ? (
                  <small>{target.subtitle}</small>
                ) : null}
                <WebhookTargetMeta route={route} />
              </div>
            </div>
          </div>

          <div className="webhook-route-inspector-section">
            <h3>Relay URL</h3>
            <div className="webhook-route-url-action">
              <code title={route.webhook_url || undefined}>{route.webhook_url ? webhookUrlPreview(route.webhook_url) : "Unavailable for old route"}</code>
              <button
                className="secondary-button secondary-button--small button-with-icon"
                type="button"
                disabled={!route.webhook_url}
                onClick={() => onCopyRoute(route)}
              >
                <ClipboardCopy aria-hidden="true" className="button-icon" focusable="false" />
                Copy
              </button>
            </div>
          </div>
        </section>
      </div>

      <section className="webhook-route-inspector webhook-route-workspace-card">
        <div className="webhook-route-inspector-header">
          <div>
            <p className="integration-kicker">Operate</p>
            <h2>Route actions</h2>
          </div>
        </div>
        <ResponsiveActionBar items={actionItems} moreLabel="More route actions" />
      </section>

      <WebhookRouteRecentDeliveries route={route} />

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
    </div>
  );
}

function WebhookRouteRecentDeliveries({ route }: { route: WebhookRouteOut }) {
  const [events, setEvents] = useState<WebhookDeliveryEventOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError("");
    api
      .webhookRouteDeliveries(route.id)
      .then((rows) => {
        if (mounted) setEvents(rows.slice(0, 5));
      })
      .catch((err) => {
        if (mounted) setError(isApiError(err) ? err.message : "Recent deliveries could not be loaded.");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [route.id]);

  return (
    <section className="webhook-route-inspector webhook-route-workspace-card">
      <div className="webhook-route-inspector-header">
        <div>
          <p className="integration-kicker">Inspect</p>
          <h2>Recent deliveries</h2>
        </div>
      </div>
      {loading ? (
        <div className="table-state" role="status" aria-live="polite">
          <div className="spinner spinner--small" aria-hidden="true" />
          <p>Loading delivery events...</p>
        </div>
      ) : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!loading && !error && !events.length ? (
        <EmptyGuidance title="No deliveries yet" body="Send a test message to create a first delivery event for this route." />
      ) : null}
      {events.length ? (
        <div className="webhook-delivery-preview-table" role="table" aria-label="Recent route deliveries">
          <div className="webhook-delivery-preview-head" role="row">
            <span>Time</span>
            <span>Status</span>
            <span>Message</span>
            <span>Result</span>
          </div>
          {events.map((event) => (
            <div className="webhook-delivery-preview-row" role="row" key={event.id}>
              <span>{formatRelativeTime(event.created_at)}</span>
              <span>
                <DeliveryEventStatusBadge status={event.status} />
              </span>
              <span>{eventTitle(event)}</span>
              <span>{event.error || eventDeliveryMode(event)}</span>
            </div>
          ))}
        </div>
      ) : null}
    </section>
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
          {busy ? "Creating..." : "New URL"}
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
  onInspect,
}: {
  onClose: () => void;
  onCreateRoute: (reference: BotConversationReferenceOut) => void;
  onInspect: (reference: BotConversationReferenceOut) => void;
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
              <div className="conversation-reference-actions">
                <button className="secondary-button secondary-button--small button-with-icon" type="button" onClick={() => onInspect(reference)}>
                  <Info aria-hidden="true" className="button-icon" focusable="false" />
                  Inspect
                </button>
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

function BotConversationReferenceDetailPage({
  csrfToken,
  onCreateRoute,
  onDeleted,
  referenceId,
}: {
  csrfToken: string;
  onCreateRoute: (reference: BotConversationReferenceOut) => void;
  onDeleted: () => void;
  referenceId: string;
}) {
  const { notify } = useAppContext();
  const [detail, setDetail] = useState<BotConversationReferenceDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setDetail(await api.botConversationReference(referenceId));
    } catch (err) {
      setError(isApiError(err) ? err.message : "Bot conversation could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [referenceId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function refreshMembers() {
    setRefreshing(true);
    try {
      const updated = await api.refreshBotConversationReferenceMembers(csrfToken, referenceId);
      setDetail(updated);
      notify({
        tone: updated.members_lookup_error ? "error" : "success",
        title: updated.members_lookup_error ? "Member refresh failed" : "Members refreshed",
        description: updated.members_lookup_error || (updated.member_count ? `${updated.member_count} members found.` : "Conversation metadata is current."),
      });
    } catch (err) {
      notify({
        tone: "error",
        title: "Refresh failed",
        description: isApiError(err) ? err.message : "The member list could not be refreshed.",
      });
    } finally {
      setRefreshing(false);
    }
  }

  async function deleteConversation() {
    setDeleting(true);
    try {
      await api.deleteBotConversationReference(csrfToken, referenceId, true);
      notify({
        tone: "info",
        title: "Conversation deleted",
        description: detail?.linked_route_count ? `${detail.linked_route_count} linked route${detail.linked_route_count === 1 ? "" : "s"} deleted.` : "No linked routes were deleted.",
      });
      setConfirmingDelete(false);
      onDeleted();
    } catch (err) {
      notify({
        tone: "error",
        title: "Delete failed",
        description: isApiError(err) ? err.message : "The conversation could not be deleted.",
      });
    } finally {
      setDeleting(false);
    }
  }

  if (loading) {
    return (
      <Card>
        <div className="table-state" role="status" aria-live="polite">
          <div className="spinner spinner--small" aria-hidden="true" />
          <p>Loading conversation inspector...</p>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <div className="table-state table-state--error" role="alert">
          <h3>Could not load conversation</h3>
          <p>{error}</p>
          <button className="secondary-button secondary-button--small" type="button" onClick={() => void refresh()}>
            Retry
          </button>
        </div>
      </Card>
    );
  }

  if (!detail) {
    return (
      <Card>
        <EmptyState title="Conversation not found" body="This captured Teams conversation no longer exists." />
      </Card>
    );
  }

  const participants = botConversationParticipants(detail);
  const title = referenceTitle(detail);
  const actionItems: ResponsiveActionItem[] = [
    {
      label: "Create route",
      icon: Plus,
      buttonTone: "primary",
      onClick: () => onCreateRoute(detail),
    },
    {
      label: refreshing ? "Refreshing..." : "Refresh members",
      icon: RefreshCw,
      disabled: refreshing,
      spinning: refreshing,
      onClick: () => void refreshMembers(),
    },
    {
      label: "Delete conversation",
      icon: Trash2,
      tone: "danger",
      buttonTone: "danger",
      separated: true,
      onClick: () => setConfirmingDelete(true),
    },
  ];

  return (
    <>
      <div className="bot-conversation-workspace" aria-label={`${title} conversation inspector`}>
        <section className="status-relay-hero status-relay-hero--success" aria-label="Conversation overview">
          <div className="status-relay-hero-main">
            <div className="status-relay-indicator status-relay-indicator--success" aria-hidden="true" />
            <div>
              <p className="integration-kicker">Captured Teams conversation</p>
              <h2>{title}</h2>
              <p>{referenceSubtitle(detail)}</p>
            </div>
          </div>
          <div className="status-relay-metrics">
            <StatusOverviewMetric label="Scope" value={detail.scope || "unknown"} detail={detail.conversation_type || "Teams conversation"} tone={conversationScopeTone(detail)} />
            <StatusOverviewMetric label="Last contact" value={formatRelativeTime(detail.last_seen_at)} detail={formatDateTime(detail.last_seen_at)} tone="success" />
            <StatusOverviewMetric label="Routes" value={String(detail.linked_route_count)} detail={detail.linked_route_count ? "Using this conversation." : "No linked routes."} tone={detail.linked_route_count ? "success" : "neutral"} />
            <StatusOverviewMetric label="Participants" value={detail.member_count ? String(detail.member_count) : String(participants.length || "-")} detail={detail.members_refreshed_at ? `Refreshed ${formatRelativeTime(detail.members_refreshed_at)}` : "Captured metadata."} tone={detail.members_lookup_error ? "warn" : "neutral"} />
          </div>
        </section>

        {detail.members_lookup_error ? (
          <div className="status-detail-alert">
            <strong>Member lookup failed</strong>
            <span>{detail.members_lookup_error}</span>
          </div>
        ) : null}

        <section className="webhook-route-inspector webhook-route-workspace-card">
          <div className="webhook-route-inspector-header">
            <div>
              <p className="integration-kicker">Operate</p>
              <h2>Conversation actions</h2>
            </div>
          </div>
          <ResponsiveActionBar items={actionItems} moreLabel="More conversation actions" />
        </section>

        <div className="webhook-route-workspace-grid">
          <section className="webhook-route-inspector webhook-route-workspace-card">
            <div className="webhook-route-inspector-header">
              <div>
                <p className="integration-kicker">Participants</p>
                <h2>Known members</h2>
              </div>
            </div>
            {participants.length ? (
              <div className="bot-conversation-member-list">
                {participants.map((member, index) => (
                  <div className="bot-conversation-member" key={`${member.id || member.name}-${index}`}>
                    <strong>{member.name || shortId(member.id) || "Unknown participant"}</strong>
                    <span>{[member.email, member.user_principal_name, member.aad_object_id ? `AAD ${shortId(member.aad_object_id)}` : ""].filter(Boolean).join(" · ") || member.id || "No member identifiers"}</span>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyGuidance title="No participants captured" body={detail.member_summary || "Teams has not provided a member list for this conversation yet."} />
            )}
          </section>

          <section className="webhook-route-inspector webhook-route-workspace-card">
            <div className="webhook-route-inspector-header">
              <div>
                <p className="integration-kicker">Usage</p>
                <h2>Linked routes</h2>
              </div>
            </div>
            {detail.linked_routes.length ? (
              <DataTable
                className="data-table--linked-routes"
                columns={["Route", "Status", "Backend", "Last delivery", ""]}
                emptyTitle="No linked routes"
                emptyBody="Create a webhook route when this conversation should receive relay messages."
                rows={detail.linked_routes.map((route) => [
                  <div className="stacked-cell">
                    <strong>{route.name}</strong>
                    <span>{route.target_name}</span>
                  </div>,
                  <StatusBadge label={route.is_active ? "Active" : "Disabled"} tone={route.is_active ? "success" : "warn"} />,
                  deliveryBackendLabel(route.delivery_backend),
                  route.last_delivery_at ? `${route.last_delivery_status || "delivery"} ${formatRelativeTime(route.last_delivery_at)}` : "No deliveries",
                  <button className="secondary-button secondary-button--small" type="button" onClick={() => navigateInApp(`/webhooks/${encodeURIComponent(route.id)}`)}>
                    Open
                  </button>,
                ])}
                rowKey={(index) => detail.linked_routes[index]?.id ?? index}
              />
            ) : (
              <EmptyGuidance title="No linked routes" body="Create a webhook route when this conversation should receive relay messages." />
            )}
          </section>
        </div>

        <section className="webhook-route-inspector webhook-route-workspace-card">
          <div className="webhook-route-inspector-header">
            <div>
              <p className="integration-kicker">Technical</p>
              <h2>Conversation identifiers</h2>
            </div>
          </div>
          <dl className="definition-list definition-list--compact advanced-definition-list bot-conversation-technical-list">
            {botConversationTechnicalRows(detail).map((row) => (
              <FragmentPair key={row.label} label={row.label} value={row.value || "-"} />
            ))}
          </dl>
        </section>
      </div>

      {confirmingDelete ? (
        <ConfirmModal
          title="Delete bot conversation"
          description={`Delete ${title}?`}
          confirmLabel="Delete conversation"
          busyLabel="Deleting..."
          busy={deleting}
          onClose={() => setConfirmingDelete(false)}
          onConfirm={() => void deleteConversation()}
        >
          <div className="warning-box">
            <strong>
              {detail.linked_route_count
                ? `${detail.linked_route_count} linked route${detail.linked_route_count === 1 ? "" : "s"} will be deleted too.`
                : "This removes the captured conversation reference."}
            </strong>
            {detail.linked_routes.length ? (
              <>
                <p>These relay URLs will stop working immediately:</p>
                <ul className="destructive-route-list">
                  {detail.linked_routes.map((route) => (
                    <li key={route.id}>{route.name}</li>
                  ))}
                </ul>
              </>
            ) : (
              <p>No webhook routes currently use this conversation.</p>
            )}
          </div>
        </ConfirmModal>
      ) : null}
    </>
  );
}

function botConversationParticipants(reference: BotConversationReferenceOut) {
  if (reference.members.length) return reference.members;
  if (reference.user_name || reference.user_id || reference.graph_user_id) {
    return [
      {
        id: reference.user_id || reference.graph_user_id,
        name: reference.user_name,
        aad_object_id: reference.graph_user_id,
        email: "",
        user_principal_name: "",
      },
    ];
  }
  return [];
}

function botConversationTechnicalRows(reference: BotConversationReferenceOut): Array<{ label: string; value: ReactNode }> {
  return [
    { label: "Service URL", value: <code>{reference.service_url || "-"}</code> },
    { label: "Conversation ID", value: <code>{reference.conversation_id || "-"}</code> },
    { label: "Tenant ID", value: <code>{reference.tenant_id || "-"}</code> },
    { label: "Team ID", value: <code>{reference.team_id || "-"}</code> },
    { label: "Graph team ID", value: <code>{reference.graph_team_id || "-"}</code> },
    { label: "Channel ID", value: <code>{reference.channel_id || "-"}</code> },
    { label: "User ID", value: <code>{reference.user_id || "-"}</code> },
    { label: "Graph user ID", value: <code>{reference.graph_user_id || "-"}</code> },
    { label: "Raw activity", value: reference.raw_activity_type || "-" },
    { label: "Created", value: formatDateTime(reference.created_at) },
    { label: "Updated", value: formatDateTime(reference.updated_at) },
  ];
}

function conversationScopeTone(reference: BotConversationReferenceOut): StatusTone {
  if (reference.scope === "channel" || reference.scope === "chat") return "success";
  if (reference.scope === "team" || reference.scope === "user") return "neutral";
  return "warn";
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
  const [activeTab, setActiveTab] = useState<UserAdminTab>("app-users");
  return (
    <>
      <PageIntro
        eyebrow="Admin"
        title="Users"
        description={activeTab === "app-users" ? "Manage administrator access for Teams Rehook operations." : "Manage Entra users who can operate the relay bot from Teams."}
        actions={
          <div className="segmented-control" aria-label="User management section">
            <button
              className={classNames("segmented-control-button", activeTab === "app-users" && "is-active")}
              type="button"
              aria-pressed={activeTab === "app-users"}
              onClick={() => setActiveTab("app-users")}
            >
              App users
            </button>
            <button
              className={classNames("segmented-control-button", activeTab === "bot-access" && "is-active")}
              type="button"
              aria-pressed={activeTab === "bot-access"}
              onClick={() => setActiveTab("bot-access")}
            >
              Bot access
            </button>
          </div>
        }
      />
      {activeTab === "app-users" ? <AppUsersPanel /> : <BotAccessPanel />}
    </>
  );
}

function AppUsersPanel() {
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
      <div className="section-actions">
        <div />
        <div>
          <button className="primary-button button-with-icon" type="button" onClick={() => setCreateOpen(true)}>
            <Plus aria-hidden="true" className="button-icon" focusable="false" />
            <span>Create user</span>
          </button>
        </div>
      </div>
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

const BOT_PERMISSION_FIELDS: Array<{ key: keyof BotUserPermissions; label: string }> = [
  { key: "can_view_routes", label: "View routes" },
  { key: "can_reveal_webhook_urls", label: "Reveal webhook URLs" },
  { key: "can_manage_route_status", label: "Enable or disable routes" },
  { key: "can_delete_routes", label: "Delete routes" },
  { key: "can_manage_allowlist", label: "Manage IP allowlists" },
  { key: "can_create_private_chat_routes", label: "Create private chat routes" },
  { key: "can_create_channel_routes", label: "Create channel routes" },
];

type BotGroupMemberCountState = { loading: boolean; count?: number; error?: string } | null;
type BotAccessSubview = "users" | "groups" | "roles";
type BotAccessGrant = (BotAuthorizedUserOut | BotAuthorizedGroupOut) & { role_id?: string | null; role?: BotUserRole };

const BOT_PERMISSION_SHORT_LABELS: Record<keyof BotUserPermissions, string> = {
  can_view_routes: "View routes",
  can_reveal_webhook_urls: "Reveal URLs",
  can_manage_route_status: "Enable / Disable",
  can_delete_routes: "Delete routes",
  can_manage_allowlist: "Manage allowlists",
  can_create_private_chat_routes: "Private chat routes",
  can_create_channel_routes: "Channel routes",
};

const BOT_PERMISSION_GROUPS: Array<{ title: string; fields: Array<keyof BotUserPermissions> }> = [
  { title: "Read", fields: ["can_view_routes", "can_reveal_webhook_urls"] },
  { title: "Operate", fields: ["can_manage_route_status"] },
  { title: "Create", fields: ["can_create_channel_routes", "can_create_private_chat_routes"] },
  { title: "Administration", fields: ["can_delete_routes", "can_manage_allowlist"] },
];

function BotAccessPanel() {
  const { notify, session } = useAppContext();
  const [activeView, setActiveView] = useState<BotAccessSubview>("users");
  const [botRoles, setBotRoles] = useState<BotAccessRoleOut[]>([]);
  const [botUsers, setBotUsers] = useState<BotAuthorizedUserOut[]>([]);
  const [botGroups, setBotGroups] = useState<BotAuthorizedGroupOut[]>([]);
  const [groupMemberCounts, setGroupMemberCounts] = useState<Record<string, { loading: boolean; count?: number; error?: string }>>({});
  const requestedGroupMemberCounts = useRef(new Set<string>());
  const [rolesLoading, setRolesLoading] = useState(true);
  const [usersLoading, setUsersLoading] = useState(true);
  const [groupsLoading, setGroupsLoading] = useState(true);
  const [rolesError, setRolesError] = useState("");
  const [usersError, setUsersError] = useState("");
  const [groupsError, setGroupsError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [editingRole, setEditingRole] = useState<BotAccessRoleOut | null>(null);
  const [editingUser, setEditingUser] = useState<BotAuthorizedUserOut | null>(null);
  const [editingGroup, setEditingGroup] = useState<BotAuthorizedGroupOut | null>(null);
  const [viewingGroupMembers, setViewingGroupMembers] = useState<BotAuthorizedGroupOut | null>(null);
  const [deletingRole, setDeletingRole] = useState<BotAccessRoleOut | null>(null);
  const [deletingUser, setDeletingUser] = useState<BotAuthorizedUserOut | null>(null);
  const [deletingGroup, setDeletingGroup] = useState<BotAuthorizedGroupOut | null>(null);
  const [deleting, setDeleting] = useState(false);
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  const refreshRoles = useCallback(async () => {
    setRolesLoading(true);
    setRolesError("");
    try {
      setBotRoles(await api.adminBotRoles(csrfToken));
    } catch (err) {
      setRolesError(isApiError(err) ? err.message : "Bot access roles could not be loaded.");
    } finally {
      setRolesLoading(false);
    }
  }, [csrfToken]);

  const refreshUsers = useCallback(async () => {
    setUsersLoading(true);
    setUsersError("");
    try {
      setBotUsers(await api.adminBotUsers(csrfToken));
    } catch (err) {
      setUsersError(isApiError(err) ? err.message : "Bot access users could not be loaded.");
    } finally {
      setUsersLoading(false);
    }
  }, [csrfToken]);

  const refreshGroups = useCallback(async () => {
    setGroupsLoading(true);
    setGroupsError("");
    try {
      setBotGroups(await api.adminBotGroups(csrfToken));
    } catch (err) {
      setGroupsError(isApiError(err) ? err.message : "Bot access groups could not be loaded.");
    } finally {
      setGroupsLoading(false);
    }
  }, [csrfToken]);

  useEffect(() => {
    void refreshRoles();
    void refreshUsers();
    void refreshGroups();
  }, [refreshGroups, refreshRoles, refreshUsers]);

  useEffect(() => {
    if (!csrfToken || !botGroups.length) return;
    const missingGroups = botGroups.filter((group) => !requestedGroupMemberCounts.current.has(group.id));
    if (!missingGroups.length) return;
    for (const group of missingGroups) {
      requestedGroupMemberCounts.current.add(group.id);
    }
    setGroupMemberCounts((current) => {
      const next = { ...current };
      for (const group of botGroups) {
        if (current[group.id]) continue;
        next[group.id] = { loading: true };
      }
      return next;
    });
    for (const group of missingGroups) {
      void api.groupMemberCount(group.group_object_id)
        .then((result) => {
          setGroupMemberCounts((current) => ({ ...current, [group.id]: { loading: false, count: result.count } }));
        })
        .catch((err) => {
          setGroupMemberCounts((current) => ({
            ...current,
            [group.id]: { loading: false, error: isApiError(err) ? err.message : "Member count unavailable." },
          }));
        });
    }
  }, [botGroups, csrfToken]);

  async function deleteBotUser() {
    if (!deletingUser) return;
    setDeleting(true);
    try {
      await api.deleteAdminBotUser(csrfToken, deletingUser.id);
      notify({ tone: "success", title: "Bot access removed" });
      setDeletingUser(null);
      await refreshUsers();
    } catch (err) {
      notify({ tone: "error", title: "Bot access could not be removed", description: isApiError(err) ? err.message : undefined });
    } finally {
      setDeleting(false);
    }
  }

  async function deleteBotGroup() {
    if (!deletingGroup) return;
    setDeleting(true);
    try {
      await api.deleteAdminBotGroup(csrfToken, deletingGroup.id);
      notify({ tone: "success", title: "Bot group access removed" });
      setDeletingGroup(null);
      await refreshGroups();
    } catch (err) {
      notify({ tone: "error", title: "Bot group access could not be removed", description: isApiError(err) ? err.message : undefined });
    } finally {
      setDeleting(false);
    }
  }

  async function deleteBotRole() {
    if (!deletingRole) return;
    setDeleting(true);
    try {
      await api.deleteAdminBotRole(csrfToken, deletingRole.id);
      notify({ tone: "success", title: "Bot role removed" });
      setDeletingRole(null);
      await refreshRoles();
    } catch (err) {
      notify({ tone: "error", title: "Bot role could not be removed", description: isApiError(err) ? err.message : undefined });
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <div className="section-actions">
        <div className="segmented-control" aria-label="Bot access view">
          <button
            className={classNames("segmented-control-button", activeView === "users" && "is-active")}
            type="button"
            aria-pressed={activeView === "users"}
            onClick={() => setActiveView("users")}
          >
            Users
          </button>
          <button
            className={classNames("segmented-control-button", activeView === "groups" && "is-active")}
            type="button"
            aria-pressed={activeView === "groups"}
            onClick={() => setActiveView("groups")}
          >
            Groups
          </button>
          <button
            className={classNames("segmented-control-button", activeView === "roles" && "is-active")}
            type="button"
            aria-pressed={activeView === "roles"}
            onClick={() => setActiveView("roles")}
          >
            Roles
          </button>
        </div>
        <div>
          <button className="primary-button button-with-icon" type="button" onClick={() => setCreateOpen(true)}>
            <Plus aria-hidden="true" className="button-icon" focusable="false" />
            <span>{activeView === "users" ? "Add bot user" : activeView === "groups" ? "Add bot group" : "Add bot role"}</span>
          </button>
        </div>
      </div>
      {activeView === "users" ? (
        <Card>
          <DataTable
            columns={["Name", "UPN", "Role", "Status", "Permissions", "Last seen", "Actions"]}
            rows={botUsers.map((user) => [
              <span className="user-name-cell" title={`AAD object ID: ${user.aad_object_id}`}>
                <strong>{user.display_name}</strong>
              </span>,
              user.user_principal_name || "-",
              <StatusBadge label={botGrantRoleLabel(user, botRoles)} tone={user.role_id ? "success" : "warn"} />,
              user.is_active ? <StatusBadge label="Active" tone="success" /> : <StatusBadge label="Disabled" tone="danger" />,
              botPermissionSummary(botGrantPermissions(user, botRoles)),
              user.last_seen_at ? formatRelativeTime(user.last_seen_at) : "Never",
              <RowActionMenu
                label={`Actions for ${user.display_name}`}
                items={[
                  { label: "Edit access", icon: Pencil, onClick: () => setEditingUser(user) },
                  { label: "Remove access", icon: Trash2, onClick: () => setDeletingUser(user) },
                ]}
              />,
            ])}
            emptyTitle="No bot access users"
            emptyBody="Add Entra users here before they can operate Teams bot commands."
            loading={usersLoading}
            loadingLabel="Loading bot access users..."
            error={usersError}
            onRetry={() => void refreshUsers()}
            rowKey={(index) => botUsers[index]?.id ?? index}
          />
        </Card>
      ) : activeView === "groups" ? (
        <Card>
          <DataTable
            className="data-table--bot-groups"
            columns={["Group", "Mail / Type", "Role", "Status", "Permissions", "Members", "Last matched", "Actions"]}
            rows={botGroups.map((group) => [
              <span className="bot-group-name-cell" title={`Group object ID: ${group.group_object_id}`}>
                <strong>{group.display_name}</strong>
              </span>,
              <span className="bot-group-mail-type-cell">
                {botGroupMailLabel(group) ? <span>{botGroupMailLabel(group)}</span> : null}
                <small>{botGroupTypeLabel(group)}</small>
              </span>,
              <StatusBadge label={botGrantRoleLabel(group, botRoles)} tone={group.role_id ? "success" : "warn"} />,
              group.is_active ? <StatusBadge label="Active" tone="success" /> : <StatusBadge label="Disabled" tone="danger" />,
              botPermissionSummary(botGrantPermissions(group, botRoles)),
              botGroupMemberCountLabel(groupMemberCounts[group.id]),
              group.last_matched_at ? formatRelativeTime(group.last_matched_at) : "Never",
              <RowActionMenu
                label={`Actions for ${group.display_name}`}
                items={[
                  { label: "View members", icon: Eye, onClick: () => setViewingGroupMembers(group) },
                  { label: "Edit access", icon: Pencil, onClick: () => setEditingGroup(group) },
                  { label: "Remove access", icon: Trash2, onClick: () => setDeletingGroup(group) },
                ]}
              />,
            ])}
            emptyTitle="No bot access groups"
            emptyBody="Add Entra groups here to grant Teams bot permissions by membership."
            loading={groupsLoading}
            loadingLabel="Loading bot access groups..."
            error={groupsError}
            onRetry={() => void refreshGroups()}
            rowKey={(index) => botGroups[index]?.id ?? index}
          />
        </Card>
      ) : (
        <Card>
          <DataTable
            columns={["Role", "Type", "Permissions", "Updated", "Actions"]}
            rows={botRoles.map((role) => [
              <span className="user-name-cell">
                <strong>{role.name}</strong>
                {role.description ? <small>{role.description}</small> : null}
              </span>,
              <StatusBadge label={role.is_system ? "System" : "Custom"} tone={role.is_system ? "success" : "neutral"} />,
              botPermissionSummary(role),
              role.updated_at ? formatRelativeTime(role.updated_at) : "-",
              <RowActionMenu
                label={`Actions for ${role.name}`}
                items={[
                  { label: "Edit role", icon: Pencil, onClick: () => setEditingRole(role) },
                  ...(role.is_system ? [] : [{ label: "Delete role", icon: Trash2, onClick: () => setDeletingRole(role) }]),
                ]}
              />,
            ])}
            emptyTitle="No bot access roles"
            emptyBody="Create role templates to reuse permission sets for bot users and groups."
            loading={rolesLoading}
            loadingLabel="Loading bot access roles..."
            error={rolesError}
            onRetry={() => void refreshRoles()}
            rowKey={(index) => botRoles[index]?.id ?? index}
          />
        </Card>
      )}
      {createOpen && activeView === "users" ? (
        <BotAccessCreateModal
          csrfToken={csrfToken}
          roles={botRoles}
          onClose={() => setCreateOpen(false)}
          onSaved={() => {
            setCreateOpen(false);
            notify({ tone: "success", title: "Bot access added" });
            void refreshUsers();
          }}
        />
      ) : null}
      {createOpen && activeView === "groups" ? (
        <BotGroupCreateModal
          csrfToken={csrfToken}
          roles={botRoles}
          onClose={() => setCreateOpen(false)}
          onSaved={() => {
            setCreateOpen(false);
            notify({ tone: "success", title: "Bot group access added" });
            void refreshGroups();
          }}
        />
      ) : null}
      {createOpen && activeView === "roles" ? (
        <BotRoleEditModal
          csrfToken={csrfToken}
          onClose={() => setCreateOpen(false)}
          onSaved={() => {
            setCreateOpen(false);
            notify({ tone: "success", title: "Bot role added" });
            void refreshRoles();
          }}
        />
      ) : null}
      {editingRole ? (
        <BotRoleEditModal
          csrfToken={csrfToken}
          role={editingRole}
          onClose={() => setEditingRole(null)}
          onSaved={() => {
            setEditingRole(null);
            notify({ tone: "success", title: "Bot role updated" });
            void refreshRoles();
            void refreshUsers();
            void refreshGroups();
          }}
        />
      ) : null}
      {editingUser ? (
        <BotAccessEditModal
          csrfToken={csrfToken}
          roles={botRoles}
          user={editingUser}
          onClose={() => setEditingUser(null)}
          onSaved={() => {
            setEditingUser(null);
            notify({ tone: "success", title: "Bot access updated" });
            void refreshUsers();
          }}
        />
      ) : null}
      {editingGroup ? (
        <BotGroupEditModal
          csrfToken={csrfToken}
          roles={botRoles}
          group={editingGroup}
          onClose={() => setEditingGroup(null)}
          onSaved={() => {
            setEditingGroup(null);
            notify({ tone: "success", title: "Bot group access updated" });
            void refreshGroups();
          }}
        />
      ) : null}
      {viewingGroupMembers ? (
        <BotGroupMembersModal group={viewingGroupMembers} onClose={() => setViewingGroupMembers(null)} />
      ) : null}
      {deletingUser ? (
        <ConfirmModal
          title="Remove bot access?"
          description={`${deletingUser.display_name} will no longer be able to use Teams bot commands.`}
          confirmLabel="Remove access"
          busyLabel="Removing..."
          busy={deleting}
          tone="danger"
          onClose={() => setDeletingUser(null)}
          onConfirm={() => void deleteBotUser()}
        />
      ) : null}
      {deletingGroup ? (
        <ConfirmModal
          title="Remove bot group access?"
          description={`${deletingGroup.display_name} will no longer grant Teams bot permissions to its members.`}
          confirmLabel="Remove access"
          busyLabel="Removing..."
          busy={deleting}
          tone="danger"
          onClose={() => setDeletingGroup(null)}
          onConfirm={() => void deleteBotGroup()}
        />
      ) : null}
      {deletingRole ? (
        <ConfirmModal
          title="Delete bot role?"
          description={`${deletingRole.name} can only be deleted while no bot users or groups use it.`}
          confirmLabel="Delete role"
          busyLabel="Deleting..."
          busy={deleting}
          tone="danger"
          onClose={() => setDeletingRole(null)}
          onConfirm={() => void deleteBotRole()}
        />
      ) : null}
    </>
  );
}

function BotAccessCreateModal({
  csrfToken,
  roles,
  onClose,
  onSaved,
}: {
  csrfToken: string;
  roles: BotAccessRoleOut[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TeamsTargetSearchResult[]>([]);
  const [selectedUser, setSelectedUser] = useState<TeamsTargetSearchResult | null>(null);
  const initialRole = defaultBotAccessRole(roles);
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(initialRole?.id ?? null);
  const [role, setRole] = useState<BotUserRole>(initialRole ? botRoleValue(initialRole) : "custom");
  const [permissions, setPermissions] = useState<BotUserPermissions>(initialRole ? botPermissionsFromGrant(initialRole) : emptyBotPermissions());
  const [isActive, setIsActive] = useState(true);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const selectedRole = roles.find((entry) => entry.id === selectedRoleId) ?? null;

  async function searchUsers() {
    setSearching(true);
    setError("");
    try {
      setResults(await api.searchTeamsTargets("user", query));
    } catch (err) {
      setError(isApiError(err) ? err.message : "User search failed.");
    } finally {
      setSearching(false);
    }
  }

  function selectUser(user: TeamsTargetSearchResult) {
    setSelectedUser(user);
    setResults([]);
    setQuery(user.display_name);
  }

  function changeSelectedUser() {
    setSelectedUser(null);
    setResults([]);
  }

  function selectRole(nextRole: BotAccessRoleOut | "custom") {
    if (nextRole === "custom") {
      setSelectedRoleId(null);
      setRole("custom");
      return;
    }
    setSelectedRoleId(nextRole.id);
    setRole(botRoleValue(nextRole));
    setPermissions(botPermissionsFromGrant(nextRole));
  }

  function updateCustomPermission(key: keyof BotUserPermissions, checked: boolean) {
    setPermissions({ ...permissions, [key]: checked });
    setSelectedRoleId(null);
    setRole("custom");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selectedUser) {
      setError("Select an Entra user first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const body: BotAuthorizedUserCreate = {
        aad_object_id: selectedUser.id,
        display_name: selectedUser.display_name,
        user_principal_name: selectedUser.subtitle || "",
        role_id: selectedRoleId,
        role,
        is_active: isActive,
        ...permissions,
      };
      await api.createAdminBotUser(csrfToken, body);
      onSaved();
    } catch (err) {
      setError(isApiError(err) ? err.message : "Bot access could not be added.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Add bot access" onClose={onClose} panelClassName="bot-access-workflow-modal">
      <form className="bot-access-flow" onSubmit={(event) => void submit(event)}>
        <section className="bot-access-step">
          <div className="bot-access-step-heading">
            <span>1</span>
            <h3>Select Entra user</h3>
          </div>
          {selectedUser ? (
            <SelectedBotPrincipalSummary target={selectedUser} onChange={changeSelectedUser} />
          ) : (
            <>
              <div className="bot-access-search">
                <Search aria-hidden="true" focusable="false" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void searchUsers();
                    }
                  }}
                  placeholder="Search users..."
                  autoFocus
                />
                <button className="secondary-button secondary-button--small" type="button" onClick={() => void searchUsers()} disabled={searching || query.trim().length < 2}>
                  {searching ? "Searching..." : "Search"}
                </button>
              </div>
              <BotPrincipalSearchResults results={results} onSelect={selectUser} />
            </>
          )}
        </section>
        <section className="bot-access-step">
          <div className="bot-access-step-heading bot-access-step-heading--split">
            <span>2</span>
            <h3>Access level</h3>
            <label className="bot-access-active-toggle">
              <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />
              <span>Active</span>
            </label>
          </div>
          <BotAccessRoleList roles={roles} selectedRoleId={selectedRoleId} permissions={permissions} onRoleChange={selectRole} />
        </section>
        <section className="bot-access-step">
          <div className="bot-access-step-heading bot-access-step-heading--split">
            <span>3</span>
            <h3>Permissions</h3>
            <small>{selectedRole ? `Inherited from ${selectedRole.name}` : "Inline custom"}</small>
          </div>
          {selectedRole ? (
            <BotAccessPermissionSummary permissions={permissions} />
          ) : (
            <BotAccessCustomPermissions permissions={permissions} onPermissionChange={updateCustomPermission} />
          )}
        </section>
        {error ? <p className="form-error">{error}</p> : null}
        <div className="bot-access-flow-footer">
          <div className="bot-access-footer-summary">
            <div>
              <span>User</span>
              <strong>{selectedUser?.display_name ?? "Not selected"}</strong>
            </div>
            <div>
              <span>Access level</span>
              <strong>{botAccessLevelLabel(selectedRole, role)}</strong>
            </div>
            <div>
              <span>UPN</span>
              <strong>{selectedUser?.subtitle || "-"}</strong>
            </div>
          </div>
          <div className="bot-access-footer-actions">
            <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button className="primary-button" type="submit" disabled={busy || !selectedUser}>
              {busy ? "Adding..." : `Add ${botAccessLevelLabel(selectedRole, role)} Access`}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

function directoryTargetMeta(target: TeamsTargetSearchResult): string {
  if (target.kind === "group") {
    return [target.mail, groupTypeLabelFromParts(target.group_types, target.security_enabled)].filter(Boolean).join(" · ");
  }
  return target.subtitle || "No mail address returned";
}

function BotAccessEditModal({
  csrfToken,
  roles,
  user,
  onClose,
  onSaved,
}: {
  csrfToken: string;
  roles: BotAccessRoleOut[];
  user: BotAuthorizedUserOut;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [displayName, setDisplayName] = useState(user.display_name);
  const [userPrincipalName, setUserPrincipalName] = useState(user.user_principal_name);
  const initialRole = roleForGrant(user, roles);
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(initialRole?.id ?? null);
  const [role, setRole] = useState<BotUserRole>(initialRole ? botRoleValue(initialRole) : user.role);
  const [permissions, setPermissions] = useState<BotUserPermissions>(initialRole ? botPermissionsFromGrant(initialRole) : botPermissionsFromGrant(user));
  const [isActive, setIsActive] = useState(user.is_active);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const selectedRole = roles.find((entry) => entry.id === selectedRoleId) ?? null;

  function selectRole(nextRole: BotAccessRoleOut | "custom") {
    if (nextRole === "custom") {
      setSelectedRoleId(null);
      setRole("custom");
      return;
    }
    setSelectedRoleId(nextRole.id);
    setRole(botRoleValue(nextRole));
    setPermissions(botPermissionsFromGrant(nextRole));
  }

  function updateCustomPermission(key: keyof BotUserPermissions, checked: boolean) {
    setPermissions({ ...permissions, [key]: checked });
    setSelectedRoleId(null);
    setRole("custom");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.updateAdminBotUser(csrfToken, user.id, {
        display_name: displayName,
        user_principal_name: userPrincipalName,
        role_id: selectedRoleId,
        role,
        is_active: isActive,
        ...permissions,
      });
      onSaved();
    } catch (err) {
      setError(isApiError(err) ? err.message : "Bot access could not be updated.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Edit bot access" onClose={onClose} panelClassName="bot-access-workflow-modal">
      <form className="bot-access-flow" onSubmit={(event) => void submit(event)}>
        <section className="bot-access-step">
          <div className="bot-access-step-heading">
            <span>1</span>
            <h3>User details</h3>
          </div>
          <div className="bot-access-identity-editor">
            <label>
              <span>Display name</span>
              <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} required maxLength={255} autoFocus />
            </label>
            <label>
              <span>UPN</span>
              <input value={userPrincipalName} onChange={(event) => setUserPrincipalName(event.target.value)} maxLength={255} />
            </label>
            <div className="bot-access-technical-id">
              <span>AAD object ID</span>
              <code>{user.aad_object_id}</code>
            </div>
          </div>
        </section>
        <section className="bot-access-step">
          <div className="bot-access-step-heading bot-access-step-heading--split">
            <span>2</span>
            <h3>Access level</h3>
            <label className="bot-access-active-toggle">
              <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />
              <span>Active</span>
            </label>
          </div>
          <BotAccessRoleList roles={roles} selectedRoleId={selectedRoleId} permissions={permissions} onRoleChange={selectRole} />
        </section>
        <section className="bot-access-step">
          <div className="bot-access-step-heading bot-access-step-heading--split">
            <span>3</span>
            <h3>Permissions</h3>
            <small>{selectedRole ? `Inherited from ${selectedRole.name}` : "Inline custom"}</small>
          </div>
          {selectedRole ? (
            <BotAccessPermissionSummary permissions={permissions} />
          ) : (
            <BotAccessCustomPermissions permissions={permissions} onPermissionChange={updateCustomPermission} />
          )}
        </section>
        {error ? <p className="form-error">{error}</p> : null}
        <div className="bot-access-flow-footer">
          <div className="bot-access-footer-summary">
            <div>
              <span>User</span>
              <strong>{displayName || "Not named"}</strong>
            </div>
            <div>
              <span>Access level</span>
              <strong>{botAccessLevelLabel(selectedRole, role)}</strong>
            </div>
            <div>
              <span>UPN</span>
              <strong>{userPrincipalName || "-"}</strong>
            </div>
          </div>
          <div className="bot-access-footer-actions">
            <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button className="primary-button" type="submit" disabled={busy}>
              {busy ? "Saving..." : `Save ${botAccessLevelLabel(selectedRole, role)} Access`}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

function BotGroupCreateModal({
  csrfToken,
  roles,
  onClose,
  onSaved,
}: {
  csrfToken: string;
  roles: BotAccessRoleOut[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TeamsTargetSearchResult[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<TeamsTargetSearchResult | null>(null);
  const [selectedGroupMemberCount, setSelectedGroupMemberCount] = useState<BotGroupMemberCountState>(null);
  const initialRole = defaultBotAccessRole(roles);
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(initialRole?.id ?? null);
  const [role, setRole] = useState<BotUserRole>(initialRole ? botRoleValue(initialRole) : "custom");
  const [permissions, setPermissions] = useState<BotUserPermissions>(initialRole ? botPermissionsFromGrant(initialRole) : emptyBotPermissions());
  const [isActive, setIsActive] = useState(true);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const selectedRole = roles.find((entry) => entry.id === selectedRoleId) ?? null;

  async function searchGroups() {
    setSearching(true);
    setError("");
    try {
      setResults(await api.searchTeamsTargets("group", query));
    } catch (err) {
      setError(isApiError(err) ? err.message : "Group search failed.");
    } finally {
      setSearching(false);
    }
  }

  useEffect(() => {
    if (!selectedGroup) {
      setSelectedGroupMemberCount(null);
      return;
    }
    let cancelled = false;
    setSelectedGroupMemberCount({ loading: true });
    void api.groupMemberCount(selectedGroup.id)
      .then((result) => {
        if (!cancelled) setSelectedGroupMemberCount({ loading: false, count: result.count });
      })
      .catch((err) => {
        if (!cancelled) {
          setSelectedGroupMemberCount({ loading: false, error: isApiError(err) ? err.message : "Member count unavailable." });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedGroup]);

  function selectGroup(group: TeamsTargetSearchResult) {
    setSelectedGroup(group);
    setResults([]);
    setQuery(group.display_name);
  }

  function changeSelectedGroup() {
    setSelectedGroup(null);
    setSelectedGroupMemberCount(null);
    setResults([]);
  }

  function selectRole(nextRole: BotAccessRoleOut | "custom") {
    if (nextRole === "custom") {
      setSelectedRoleId(null);
      setRole("custom");
      return;
    }
    setSelectedRoleId(nextRole.id);
    setRole(botRoleValue(nextRole));
    setPermissions(botPermissionsFromGrant(nextRole));
  }

  function updateCustomPermission(key: keyof BotUserPermissions, checked: boolean) {
    setPermissions({ ...permissions, [key]: checked });
    setSelectedRoleId(null);
    setRole("custom");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selectedGroup) {
      setError("Select an Entra group first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const body: BotAuthorizedGroupCreate = {
        group_object_id: selectedGroup.id,
        display_name: selectedGroup.display_name,
        mail: selectedGroup.mail || "",
        security_enabled: Boolean(selectedGroup.security_enabled),
        group_types: selectedGroup.group_types || [],
        role_id: selectedRoleId,
        role,
        is_active: isActive,
        ...permissions,
      };
      await api.createAdminBotGroup(csrfToken, body);
      onSaved();
    } catch (err) {
      setError(isApiError(err) ? err.message : "Bot group access could not be added.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Add bot group access" onClose={onClose} panelClassName="bot-access-workflow-modal">
      <form className="bot-access-flow" onSubmit={(event) => void submit(event)}>
        <section className="bot-access-step">
          <div className="bot-access-step-heading">
            <span>1</span>
            <h3>Select Entra group</h3>
          </div>
          {selectedGroup ? (
            <SelectedBotPrincipalSummary target={selectedGroup} metaSuffix={formatMemberCount(selectedGroupMemberCount, "members")} onChange={changeSelectedGroup} />
          ) : (
            <>
              <div className="bot-access-search">
                <Search aria-hidden="true" focusable="false" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void searchGroups();
                    }
                  }}
                  placeholder="Search groups..."
                  autoFocus
                />
                <button className="secondary-button secondary-button--small" type="button" onClick={() => void searchGroups()} disabled={searching || query.trim().length < 2}>
                  {searching ? "Searching..." : "Search"}
                </button>
              </div>
              <BotPrincipalSearchResults results={results} onSelect={selectGroup} />
            </>
          )}
        </section>
        <section className="bot-access-step">
          <div className="bot-access-step-heading bot-access-step-heading--split">
            <span>2</span>
            <h3>Access level</h3>
            <label className="bot-access-active-toggle">
              <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />
              <span>Active</span>
            </label>
          </div>
          <BotAccessRoleList roles={roles} selectedRoleId={selectedRoleId} permissions={permissions} onRoleChange={selectRole} />
        </section>
        <section className="bot-access-step">
          <div className="bot-access-step-heading bot-access-step-heading--split">
            <span>3</span>
            <h3>Permissions</h3>
            <small>{selectedRole ? `Inherited from ${selectedRole.name}` : "Inline custom"}</small>
          </div>
          {selectedRole ? (
            <BotAccessPermissionSummary permissions={permissions} />
          ) : (
            <BotAccessCustomPermissions permissions={permissions} onPermissionChange={updateCustomPermission} />
          )}
        </section>
        {error ? <p className="form-error">{error}</p> : null}
        <div className="bot-access-flow-footer">
          <div className="bot-access-footer-summary">
            <div>
              <span>Group</span>
              <strong>{selectedGroup?.display_name ?? "Not selected"}</strong>
            </div>
            <div>
              <span>Access level</span>
              <strong>{botAccessLevelLabel(selectedRole, role)}</strong>
            </div>
            <div>
              <span>Members</span>
              <strong>{formatMemberCount(selectedGroupMemberCount)}</strong>
            </div>
          </div>
          <div className="bot-access-footer-actions">
          <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="primary-button" type="submit" disabled={busy || !selectedGroup}>
            {busy ? "Adding..." : `Add ${botAccessLevelLabel(selectedRole, role)} Access`}
          </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

function BotPrincipalSearchResults({
  results,
  onSelect,
}: {
  results: TeamsTargetSearchResult[];
  onSelect: (target: TeamsTargetSearchResult) => void;
}) {
  if (!results.length) return null;
  return (
    <div className="bot-principal-result-list">
      {results.map((target) => (
        <button type="button" key={target.id} className="bot-principal-result" onClick={() => onSelect(target)}>
          <span>
            <strong>{target.display_name}</strong>
            <small>{directoryTargetMeta(target)}</small>
          </span>
        </button>
      ))}
    </div>
  );
}

function SelectedBotPrincipalSummary({
  target,
  metaSuffix,
  onChange,
}: {
  target: TeamsTargetSearchResult;
  metaSuffix?: string;
  onChange: () => void;
}) {
  const meta = [directoryTargetMeta(target), metaSuffix].filter((value) => value && value !== "-").join(" · ");
  return (
    <div className="selected-bot-principal">
      <div>
        <strong>{target.display_name}</strong>
        <span>{meta || "No directory metadata returned"}</span>
      </div>
      <button className="secondary-button secondary-button--small" type="button" onClick={onChange}>
        Change
      </button>
    </div>
  );
}

function BotAccessRoleList({
  roles,
  selectedRoleId,
  permissions,
  onRoleChange,
}: {
  roles: BotAccessRoleOut[];
  selectedRoleId: string | null;
  permissions: BotUserPermissions;
  onRoleChange: (role: BotAccessRoleOut | "custom") => void;
}) {
  return (
    <div className="bot-access-role-list" role="radiogroup" aria-label="Access level">
      {roles.map((entry) => {
        const selected = selectedRoleId === entry.id;
        return (
          <button
            type="button"
            key={entry.id}
            className={classNames("bot-access-role-option", selected && "is-selected")}
            role="radio"
            aria-checked={selected}
            onClick={() => onRoleChange(entry)}
          >
            <span className="bot-access-radio" aria-hidden="true" />
            <span className="bot-access-role-copy">
              <strong>{entry.name}</strong>
              <small>{entry.description || (entry.is_system ? "Managed system role" : "Managed custom role")}</small>
            </span>
            <span className="bot-access-role-summary">{compactPermissionSummary(entry)}</span>
          </button>
        );
      })}
      <button
        type="button"
        className={classNames("bot-access-role-option", selectedRoleId === null && "is-selected")}
        role="radio"
        aria-checked={selectedRoleId === null}
        onClick={() => onRoleChange("custom")}
      >
        <span className="bot-access-radio" aria-hidden="true" />
        <span className="bot-access-role-copy">
          <strong>Inline Custom</strong>
          <small>Specific permissions for this assignment only</small>
        </span>
        <span className="bot-access-role-summary">{compactPermissionSummary(permissions)}</span>
      </button>
    </div>
  );
}

function BotAccessPermissionSummary({ permissions }: { permissions: BotUserPermissions }) {
  const selected = BOT_PERMISSION_FIELDS.filter((field) => permissions[field.key]);
  return (
    <div className="bot-access-permission-summary">
      {selected.slice(0, 4).map((field) => (
        <span key={field.key}>{BOT_PERMISSION_SHORT_LABELS[field.key]}</span>
      ))}
      {selected.length > 4 ? <span>+{selected.length - 4} more</span> : null}
      {!selected.length ? <span>No permissions</span> : null}
    </div>
  );
}

function BotAccessCustomPermissions({
  permissions,
  onPermissionChange,
}: {
  permissions: BotUserPermissions;
  onPermissionChange: (key: keyof BotUserPermissions, checked: boolean) => void;
}) {
  return (
    <div className="bot-access-custom-permissions">
      {BOT_PERMISSION_GROUPS.map((group) => (
        <div className="bot-access-permission-group" key={group.title}>
          <h4>{group.title}</h4>
          <div>
            {group.fields.map((field) => (
              <label className="bot-access-permission-check" key={field}>
                <input type="checkbox" checked={permissions[field]} onChange={(event) => onPermissionChange(field, event.target.checked)} />
                <span>{BOT_PERMISSION_FIELDS.find((entry) => entry.key === field)?.label ?? BOT_PERMISSION_SHORT_LABELS[field]}</span>
              </label>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function BotRoleEditModal({
  csrfToken,
  role,
  onClose,
  onSaved,
}: {
  csrfToken: string;
  role?: BotAccessRoleOut;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [permissions, setPermissions] = useState<BotUserPermissions>(role ? botPermissionsFromGrant(role) : emptyBotPermissions());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const permissionCount = permissionCountFor(permissions);

  function updatePermission(key: keyof BotUserPermissions, checked: boolean) {
    setPermissions({ ...permissions, [key]: checked });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body: BotAccessRoleCreate | BotAccessRoleUpdate = {
        name,
        description,
        ...permissions,
      };
      if (role) {
        await api.updateAdminBotRole(csrfToken, role.id, body);
      } else {
        await api.createAdminBotRole(csrfToken, body as BotAccessRoleCreate);
      }
      onSaved();
    } catch (err) {
      setError(isApiError(err) ? err.message : "Bot role could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={role ? "Edit bot role" : "Add bot role"} onClose={onClose} panelClassName="bot-access-workflow-modal">
      <form className="bot-access-flow" onSubmit={(event) => void submit(event)}>
        <section className="bot-access-step">
          <div className="bot-access-step-heading">
            <span>1</span>
            <h3>Role details</h3>
          </div>
          <div className="bot-access-identity-editor">
            <label>
              <span>Name</span>
              <input value={name} onChange={(event) => setName(event.target.value)} required maxLength={120} autoFocus />
            </label>
            <label>
              <span>Description</span>
              <input value={description} onChange={(event) => setDescription(event.target.value)} maxLength={500} />
            </label>
            {role?.is_system ? (
              <div className="bot-access-readonly-meta">
                <span>Type</span>
                <strong>System role</strong>
              </div>
            ) : null}
          </div>
        </section>
        <section className="bot-access-step">
          <div className="bot-access-step-heading bot-access-step-heading--split">
            <span>2</span>
            <h3>Permissions</h3>
            <small>{permissionCount === 1 ? "1 permission" : `${permissionCount} permissions`}</small>
          </div>
          <BotAccessCustomPermissions permissions={permissions} onPermissionChange={updatePermission} />
        </section>
        {error ? <p className="form-error">{error}</p> : null}
        <div className="bot-access-flow-footer">
          <div className="bot-access-footer-summary">
            <div>
              <span>Role</span>
              <strong>{name || "Not named"}</strong>
            </div>
            <div>
              <span>Type</span>
              <strong>{role?.is_system ? "System" : "Custom"}</strong>
            </div>
            <div>
              <span>Permissions</span>
              <strong>{permissionCount}</strong>
            </div>
          </div>
          <div className="bot-access-footer-actions">
            <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button className="primary-button" type="submit" disabled={busy || !name.trim()}>
              {busy ? "Saving..." : role ? "Save Role" : "Add Role"}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

function BotGroupEditModal({
  csrfToken,
  roles,
  group,
  onClose,
  onSaved,
}: {
  csrfToken: string;
  roles: BotAccessRoleOut[];
  group: BotAuthorizedGroupOut;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [displayName, setDisplayName] = useState(group.display_name);
  const [mail, setMail] = useState(group.mail);
  const [memberCount, setMemberCount] = useState<BotGroupMemberCountState>(null);
  const initialRole = roleForGrant(group, roles);
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(initialRole?.id ?? null);
  const [role, setRole] = useState<BotUserRole>(initialRole ? botRoleValue(initialRole) : group.role);
  const [permissions, setPermissions] = useState<BotUserPermissions>(initialRole ? botPermissionsFromGrant(initialRole) : botPermissionsFromGrant(group));
  const [isActive, setIsActive] = useState(group.is_active);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const selectedRole = roles.find((entry) => entry.id === selectedRoleId) ?? null;

  useEffect(() => {
    let cancelled = false;
    setMemberCount({ loading: true });
    void api.groupMemberCount(group.group_object_id)
      .then((result) => {
        if (!cancelled) setMemberCount({ loading: false, count: result.count });
      })
      .catch((err) => {
        if (!cancelled) setMemberCount({ loading: false, error: isApiError(err) ? err.message : "Member count unavailable." });
      });
    return () => {
      cancelled = true;
    };
  }, [group.group_object_id]);

  function selectRole(nextRole: BotAccessRoleOut | "custom") {
    if (nextRole === "custom") {
      setSelectedRoleId(null);
      setRole("custom");
      return;
    }
    setSelectedRoleId(nextRole.id);
    setRole(botRoleValue(nextRole));
    setPermissions(botPermissionsFromGrant(nextRole));
  }

  function updateCustomPermission(key: keyof BotUserPermissions, checked: boolean) {
    setPermissions({ ...permissions, [key]: checked });
    setSelectedRoleId(null);
    setRole("custom");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.updateAdminBotGroup(csrfToken, group.id, {
        display_name: displayName,
        mail,
        security_enabled: group.security_enabled,
        group_types: group.group_types,
        role_id: selectedRoleId,
        role,
        is_active: isActive,
        ...permissions,
      });
      onSaved();
    } catch (err) {
      setError(isApiError(err) ? err.message : "Bot group access could not be updated.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Edit bot group access" onClose={onClose} panelClassName="bot-access-workflow-modal">
      <form className="bot-access-flow" onSubmit={(event) => void submit(event)}>
        <section className="bot-access-step">
          <div className="bot-access-step-heading">
            <span>1</span>
            <h3>Group details</h3>
          </div>
          <div className="bot-access-identity-editor">
            <label>
              <span>Display name</span>
              <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} required maxLength={255} autoFocus />
            </label>
            <label>
              <span>Mail</span>
              <input value={mail} onChange={(event) => setMail(event.target.value)} maxLength={255} />
            </label>
            <div className="bot-access-readonly-meta">
              <span>Type</span>
              <strong>{botGroupTypeLabel(group)}</strong>
            </div>
            <div className="bot-access-technical-id">
              <span>Group object ID</span>
              <code>{group.group_object_id}</code>
            </div>
          </div>
        </section>
        <section className="bot-access-step">
          <div className="bot-access-step-heading bot-access-step-heading--split">
            <span>2</span>
            <h3>Access level</h3>
            <label className="bot-access-active-toggle">
              <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />
              <span>Active</span>
            </label>
          </div>
          <BotAccessRoleList roles={roles} selectedRoleId={selectedRoleId} permissions={permissions} onRoleChange={selectRole} />
        </section>
        <section className="bot-access-step">
          <div className="bot-access-step-heading bot-access-step-heading--split">
            <span>3</span>
            <h3>Permissions</h3>
            <small>{selectedRole ? `Inherited from ${selectedRole.name}` : "Inline custom"}</small>
          </div>
          {selectedRole ? (
            <BotAccessPermissionSummary permissions={permissions} />
          ) : (
            <BotAccessCustomPermissions permissions={permissions} onPermissionChange={updateCustomPermission} />
          )}
        </section>
        {error ? <p className="form-error">{error}</p> : null}
        <div className="bot-access-flow-footer">
          <div className="bot-access-footer-summary">
            <div>
              <span>Group</span>
              <strong>{displayName || "Not named"}</strong>
            </div>
            <div>
              <span>Access level</span>
              <strong>{botAccessLevelLabel(selectedRole, role)}</strong>
            </div>
            <div>
              <span>Members</span>
              <strong>{formatMemberCount(memberCount)}</strong>
            </div>
          </div>
          <div className="bot-access-footer-actions">
            <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button className="primary-button" type="submit" disabled={busy}>
              {busy ? "Saving..." : `Save ${botAccessLevelLabel(selectedRole, role)} Access`}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

function BotGroupMembersModal({ group, onClose }: { group: BotAuthorizedGroupOut; onClose: () => void }) {
  const [members, setMembers] = useState<TeamsGroupMember[]>([]);
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const pageSize = 100;

  const loadMembers = useCallback(async (nextQuery: string, nextOffset = 0, append = false) => {
    if (append) {
      setLoadingMore(true);
    } else {
      setLoading(true);
    }
    setError("");
    try {
      const page = await api.groupMembers(group.group_object_id, nextQuery, nextOffset, pageSize);
      setMembers((current) => (append ? [...current, ...page.items] : page.items));
      setActiveQuery(nextQuery);
      setHasMore(page.has_more);
    } catch (err) {
      setError(isApiError(err) ? err.message : "Group members could not be loaded.");
    } finally {
      if (append) {
        setLoadingMore(false);
      } else {
        setLoading(false);
      }
    }
  }, [group.group_object_id]);

  useEffect(() => {
    void loadMembers("");
  }, [loadMembers]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    void loadMembers(query);
  }

  return (
    <Modal title="Group members" onClose={onClose} panelClassName="group-members-modal">
      <div className="group-members-heading">
        <strong>{group.display_name}</strong>
        <span>{[botGroupMailLabel(group), botGroupTypeLabel(group)].filter((value) => value && value !== "-").join(" · ")}</span>
      </div>
      <form className="inline-search" onSubmit={submitSearch}>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter members" />
        <button className="secondary-button button-with-icon" type="submit" disabled={loading}>
          <Search aria-hidden="true" className="button-icon" focusable="false" />
          <span>Search</span>
        </button>
      </form>
      <DataTable
        className="group-members-table"
        columns={["Name", "UPN", "Mail"]}
        rows={members.map((member) => [
          <span className="user-name-cell" title={`AAD object ID: ${member.id}`}>
            <strong>{member.display_name}</strong>
          </span>,
          member.user_principal_name || "-",
          member.mail || "-",
        ])}
        emptyTitle="No members found"
        emptyBody="No transitive user members matched this query."
        loading={loading}
        loadingLabel="Loading group members..."
        error={error}
        onRetry={() => void loadMembers(query)}
        rowKey={(index) => members[index]?.id ?? index}
      />
      {!loading && !error ? (
        <div className="member-pagination-row">
          <span>
            Showing {members.length}
            {hasMore ? "+" : ""} {activeQuery.trim() ? "matching" : "transitive"} user members
          </span>
          {hasMore ? (
            <button className="secondary-button" type="button" onClick={() => void loadMembers(activeQuery, members.length, true)} disabled={loadingMore}>
              {loadingMore ? "Loading..." : "Load next 100"}
            </button>
          ) : null}
        </div>
      ) : null}
      <div className="form-actions">
        <button className="secondary-button" type="button" onClick={onClose}>
          Close
        </button>
      </div>
    </Modal>
  );
}

function botPermissionsFromGrant(grant: BotUserPermissions): BotUserPermissions {
  return Object.fromEntries(BOT_PERMISSION_FIELDS.map((field) => [field.key, Boolean(grant[field.key])])) as BotUserPermissions;
}

function emptyBotPermissions(): BotUserPermissions {
  return Object.fromEntries(BOT_PERMISSION_FIELDS.map((field) => [field.key, false])) as BotUserPermissions;
}

function defaultBotAccessRole(roles: BotAccessRoleOut[]): BotAccessRoleOut | null {
  return roles.find((role) => role.system_key === "route_viewer") ?? roles[0] ?? null;
}

function roleForGrant(grant: BotAccessGrant, roles: BotAccessRoleOut[]): BotAccessRoleOut | null {
  if (grant.role_id) {
    const byId = roles.find((role) => role.id === grant.role_id);
    if (byId) return byId;
  }
  if (grant.role === "route_viewer" || grant.role === "viewer") {
    return roles.find((role) => role.system_key === "route_viewer") ?? null;
  }
  if (grant.role === "route_operator" || grant.role === "operator" || grant.role === "route_manager") {
    return roles.find((role) => role.system_key === "route_operator") ?? null;
  }
  return null;
}

function botRoleValue(role: BotAccessRoleOut): BotUserRole {
  return role.system_key || "role";
}

function botAccessLevelLabel(role: BotAccessRoleOut | null, fallback: BotUserRole): string {
  if (role) return role.name;
  return fallback === "custom" ? "Custom" : titleCaseRole(fallback);
}

function botGrantRoleLabel(grant: BotAccessGrant, roles: BotAccessRoleOut[]): string {
  return botAccessLevelLabel(roleForGrant(grant, roles), grant.role ?? "custom");
}

function botGrantPermissions(grant: BotAccessGrant, roles: BotAccessRoleOut[]): BotUserPermissions {
  const role = roleForGrant(grant, roles);
  return role ? botPermissionsFromGrant(role) : botPermissionsFromGrant(grant);
}

function titleCaseRole(role: string): string {
  return role
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

function permissionCountFor(grant: BotUserPermissions): number {
  return BOT_PERMISSION_FIELDS.filter((field) => grant[field.key]).length;
}

function botPermissionSummary(grant: BotUserPermissions): string {
  const permissions = BOT_PERMISSION_FIELDS.filter((field) => grant[field.key]).map((field) => field.label);
  if (!permissions.length) return "No command permissions";
  if (permissions.length <= 2) return permissions.join(", ");
  return `${permissions.length} permissions`;
}

function compactPermissionSummary(grant: BotUserPermissions): string {
  const permissions = BOT_PERMISSION_FIELDS.filter((field) => grant[field.key]).map((field) => BOT_PERMISSION_SHORT_LABELS[field.key]);
  if (!permissions.length) return "No permissions";
  if (permissions.length <= 2) return permissions.join(", ");
  return `${permissions[0]}, ${permissions[1]}, +${permissions.length - 2} more`;
}

function botGroupTypeLabel(group: BotAuthorizedGroupOut): string {
  return groupTypeLabelFromParts(group.group_types, group.security_enabled);
}

function botGroupMailLabel(group: BotAuthorizedGroupOut): string {
  const mail = group.mail.trim();
  return mail && mail !== group.display_name ? mail : "";
}

function botGroupMemberCountLabel(state?: { loading: boolean; count?: number; error?: string }): ReactNode {
  if (!state || state.loading) return <span className="muted">Loading...</span>;
  if (state.error) return <span className="muted" title={state.error}>Unavailable</span>;
  return String(state.count ?? 0);
}

function formatMemberCount(state: BotGroupMemberCountState | undefined, suffix = ""): string {
  if (!state) return "-";
  if (state.loading) return "Loading";
  if (state.error) return "Unavailable";
  const count = state.count ?? 0;
  if (suffix === "members") return count === 1 ? "1 member" : `${count} members`;
  return suffix ? `${count} ${suffix}` : String(count);
}

function groupTypeLabelFromParts(groupTypes: string[], securityEnabled: boolean | null): string {
  const type = groupTypes.includes("Unified") ? "Microsoft 365 group" : "Security group";
  return securityEnabled ? `${type}, security enabled` : type;
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
  webhook_url_reveal_ttl_hours: {
    section: "runtime",
    label: "URL reveal lifetime",
    description: "How long Teams-generated webhook URL reveal links stay usable.",
    unit: "hours",
    display: "number",
    sourceLabel: "App",
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
  "webhook_url_reveal_ttl_hours",
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

const DELIVERY_IDENTITY_SETTING_KEYS = [
  "ms_app_tenant_id",
  "ms_app_client_id",
  "ms_app_client_secret",
] as const;

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
  const [graphOAuthConfirm, setGraphOAuthConfirm] = useState<"reconnect" | "disconnect" | null>(null);
  const [authRefreshBusy, setAuthRefreshBusy] = useState(false);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  const refresh = useCallback(async (options?: { showLoading?: boolean }) => {
    const showLoading = options?.showLoading !== false;
    if (showLoading) setLoading(true);
    setError("");
    try {
      const [nextReadiness, nextSettings] = await Promise.all([api.adminReadiness(csrfToken), api.adminSettings(csrfToken)]);
      setReadiness(nextReadiness);
      setSettings(nextSettings);
    } catch (err) {
      setError(isApiError(err) ? err.message : "Delivery data could not be loaded.");
    } finally {
      if (showLoading) setLoading(false);
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

  function requestGraphDeliveryConnect() {
    if (readiness?.graph_delivery.configured) {
      setGraphOAuthConfirm("reconnect");
      return;
    }
    void connectGraphDelivery();
  }

  function requestGraphDeliveryDisconnect() {
    setGraphOAuthConfirm("disconnect");
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
  const identitySettings = orderedSettings(DELIVERY_IDENTITY_SETTING_KEYS, settingsByKey);
  const enabledCount = deliverySettings.filter((item) => item.effective_value === "true").length;
  const deliveryMethodCount = deliverySettings.length || DELIVERY_SETTING_KEYS.length;
  const graphLookupEnabled = settingEnabled(settingsByKey, "graph_lookup_enabled");
  const refreshSilently = useCallback(() => refresh({ showLoading: false }), [refresh]);
  const integrationViews = readiness
    ? [
        buildBotIntegrationView(readiness, copyDiagnosticValue),
        buildGraphLookupIntegrationView(readiness, copyDiagnosticValue),
        buildGraphDeliveryIntegrationView(readiness.graph_delivery, graphOAuthBusy, requestGraphDeliveryConnect, requestGraphDeliveryDisconnect, copyDiagnosticValue),
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
            <div className="row-actions delivery-page-actions">
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
              <button
                className="icon-button delivery-settings-trigger"
                type="button"
                onClick={() => setSettingsModalOpen(true)}
                aria-label="Configure delivery settings"
                title="Configure delivery settings"
              >
                <SettingsIcon aria-hidden="true" focusable="false" />
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
          {settingsModalOpen ? (
            <DeliverySettingsModal
              settings={identitySettings}
              settingsByKey={settingsByKey}
              csrfToken={csrfToken}
              onChanged={refreshSilently}
              notify={notify}
              onClose={() => setSettingsModalOpen(false)}
            />
          ) : null}
          {graphOAuthConfirm && readiness ? (
            <ConfirmModal
              title={graphOAuthConfirm === "reconnect" ? "Reconnect service user?" : "Disconnect service user?"}
              description={
                graphOAuthConfirm === "reconnect"
                  ? "The current Graph Delivery service user stays active until the newly authenticated user is reviewed and confirmed."
                  : "Graph Delivery will stop using the currently connected service user."
              }
              confirmLabel={graphOAuthConfirm === "reconnect" ? "Start reconnect" : "Disconnect"}
              busyLabel={graphOAuthConfirm === "reconnect" ? "Starting..." : "Disconnecting..."}
              tone={graphOAuthConfirm === "reconnect" ? "primary" : "danger"}
              busy={graphOAuthBusy}
              onClose={() => setGraphOAuthConfirm(null)}
              onConfirm={async () => {
                const action = graphOAuthConfirm;
                setGraphOAuthConfirm(null);
                if (action === "reconnect") {
                  await connectGraphDelivery();
                } else {
                  await disconnectGraphDelivery();
                }
              }}
            >
              <dl className="advanced-definition-list">
                <dt>Current service user</dt>
                <dd>{graphDeliveryServiceUserLabel(readiness.graph_delivery)}</dd>
                <dt>User principal name</dt>
                <dd>{readiness.graph_delivery.service_user_principal_name || "-"}</dd>
                <dt>User ID</dt>
                <dd>{readiness.graph_delivery.service_user_id || "-"}</dd>
              </dl>
            </ConfirmModal>
          ) : null}
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
  const configuredCount = integration.credentials.filter(([, value]) => value === "Configured" || value === "Inherited").length;
  const tokenTooltip = `Token ${tokenFactValue?.value ?? "Unknown"}`;
  const secondaryDetailItems: RowActionItem[] = [
    { label: "Open diagnostics", icon: Activity, onClick: () => setDetailView("diagnostics") },
    { label: "Open technical information", icon: Info, onClick: () => setDetailView("technical") },
  ];
  const overflowItems: RowActionItem[] = integration.manageActionItems?.length
    ? [
        ...secondaryDetailItems,
        ...integration.manageActionItems.map((item, index) => ({
          ...item,
          separated: index === 0 ? true : item.separated,
        })),
      ]
    : secondaryDetailItems;

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
          <div className="delivery-component-control">
            <div className="delivery-component-health" aria-label={`${integration.title} health`}>
              <DeliveryStatusGroup integration={integration} overridden={Boolean(item?.source === "environment" && item.is_overridden)} tokenLabel={tokenTooltip} />
            </div>
            <div className="delivery-component-state" aria-label={`${integration.title} state`}>
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
            </div>
          </div>
          <div className="delivery-detail-hub" aria-label={`${integration.title} actions`}>
            <button
              type="button"
              className={classNames("delivery-detail-button delivery-detail-button--primary", `delivery-detail-button--${checksTone}`)}
              aria-label={`Open ${integration.title} readiness checks, ${readyChecks} of ${integration.healthChecks.length} passing`}
              onClick={() => setDetailView("readiness")}
            >
              <Check aria-hidden="true" className="button-icon" focusable="false" />
              <span className="delivery-action-label" aria-hidden="true">
                <span className="delivery-action-label-full">Checks</span>
                <span className="delivery-action-label-short">Checks</span>
              </span>
              <strong>{readyChecks}/{integration.healthChecks.length}</strong>
            </button>
            <button type="button" className="delivery-detail-button delivery-detail-button--primary" aria-label={`Open ${integration.title} configuration`} onClick={() => setDetailView("configuration")}>
              <Wrench aria-hidden="true" className="button-icon" focusable="false" />
              <span className="delivery-action-label" aria-hidden="true">
                <span className="delivery-action-label-full">Config</span>
                <span className="delivery-action-label-short">Config</span>
              </span>
              <strong>{configuredCount}/{integration.credentials.length}</strong>
            </button>
            <button type="button" className="delivery-detail-button delivery-detail-button--secondary" aria-label={`Open ${integration.title} diagnostics`} onClick={() => setDetailView("diagnostics")}>
              <Activity aria-hidden="true" className="button-icon" focusable="false" />
              <span className="delivery-action-label" aria-hidden="true">
                <span className="delivery-action-label-full">Diagnostics</span>
                <span className="delivery-action-label-short">Diag</span>
              </span>
            </button>
            <button type="button" className="delivery-detail-button delivery-detail-button--secondary" aria-label={`Open ${integration.title} technical information`} onClick={() => setDetailView("technical")}>
              <Info aria-hidden="true" className="button-icon" focusable="false" />
              <span className="delivery-action-label" aria-hidden="true">
                <span className="delivery-action-label-full">Technical</span>
                <span className="delivery-action-label-short">Tech</span>
              </span>
            </button>
          </div>
          {integration.manageActionItems?.length ? (
            <div className="delivery-overflow-action delivery-overflow-action--manage">
              <RowActionMenu label={`Manage ${integration.title}`} items={integration.manageActionItems} />
            </div>
          ) : null}
          <div className="delivery-overflow-action delivery-overflow-action--details">
            <RowActionMenu label={`More ${integration.title} actions`} items={overflowItems} />
          </div>
        </div>

        {actionItem || graphDeliveryBlocked || error ? (
          <div className="delivery-inline-issues">
            {actionItem ? (
              <div className={classNames("delivery-inline-issue", `delivery-inline-issue--${actionItem.tone}`)}>
                <strong>{actionItem.title}</strong>
                <span>{actionItem.description}</span>
                {integration.primaryActionSlot ? <div className="delivery-inline-action">{integration.primaryActionSlot}</div> : null}
              </div>
            ) : null}
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

function DeliverySettingsModal({
  csrfToken,
  notify,
  onChanged,
  onClose,
  settings,
  settingsByKey,
}: SettingsCardProps & { onClose: () => void }) {
  const tenantConfigured = Boolean(settingValue(settingsByKey, "ms_app_tenant_id"));
  const clientConfigured = Boolean(settingValue(settingsByKey, "ms_app_client_id"));
  const secretConfigured = settingValue(settingsByKey, "ms_app_client_secret") === "configured";
  const configuredCount = [tenantConfigured, clientConfigured, secretConfigured].filter(Boolean).length;
  const identityReady = configuredCount === 3;
  const overrideCount = settings.filter((item) => item.is_overridden).length;

  return (
    <Modal
      title="Delivery settings"
      description="Microsoft identity values used by Bot Framework and Graph delivery."
      onClose={onClose}
      panelClassName="delivery-settings-modal"
    >
      <div className="delivery-settings-modal-body">
        <section className={classNames("delivery-settings-summary", identityReady ? "delivery-settings-summary--ready" : "delivery-settings-summary--warn")}>
          <span className={classNames("delivery-status-dot", identityReady ? "delivery-status-dot--success" : "delivery-status-dot--warn")} aria-hidden="true" />
          <div>
            <strong>{configuredCount}/3 identity values configured</strong>
            <p>{identityReady ? "Tenant, client and secret are ready for delivery auth." : "Complete the missing identity values before refreshing auth tokens."}</p>
          </div>
          <StatusBadge label={overrideCount > 0 ? `${overrideCount} overrides` : "ENV"} tone={overrideCount > 0 ? "warn" : "neutral"} />
        </section>
        <div className="delivery-settings-list">
          {settings.length ? (
            settings.map((item) => (
              <RuntimeSettingControl
                key={item.key}
                item={item}
                csrfToken={csrfToken}
                onChanged={onChanged}
                notify={notify}
                settingsByKey={settingsByKey}
              />
            ))
          ) : (
            <EmptyState title="No identity settings available" body="Delivery identity settings could not be loaded." />
          )}
        </div>
        <p className="delivery-settings-footnote">
          OAuth scopes use the built-in Bot Framework and Microsoft Graph defaults. Override them only through environment variables when needed.
        </p>
      </div>
      <div className="form-actions">
        <button className="secondary-button secondary-button--small" type="button" onClick={onClose}>
          Close
        </button>
      </div>
    </Modal>
  );
}

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

function GraphDeliveryOAuthPage() {
  const { notify, session } = useAppContext();
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";
  const [pending, setPending] = useState<GraphDeliveryOAuthPendingOut | null>(null);
  const [confirmedUser, setConfirmedUser] = useState<GraphDeliveryOAuthPendingOut | AdminReadinessOut["graph_delivery"] | null>(null);
  const [readiness, setReadiness] = useState<AdminReadinessOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isSuccess = window.location.pathname.endsWith("/success");
  const pendingId = useMemo(() => new URLSearchParams(window.location.search).get("pending_id") ?? "", []);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        if (isSuccess) {
          const nextReadiness = await api.adminReadiness(csrfToken);
          if (!active) return;
          setReadiness(nextReadiness);
          setConfirmedUser(nextReadiness.graph_delivery);
          return;
        }
        if (!pendingId) throw new Error("Missing pending Graph Delivery connection.");
        const [nextPending, nextReadiness] = await Promise.all([
          api.graphDeliveryOAuthPending(csrfToken, pendingId),
          api.adminReadiness(csrfToken),
        ]);
        if (!active) return;
        setPending(nextPending);
        setReadiness(nextReadiness);
      } catch (err) {
        if (!active) return;
        setError(isApiError(err) ? err.message : err instanceof Error ? err.message : "Graph Delivery connection could not be loaded.");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [csrfToken, isSuccess, pendingId]);

  async function confirmPending() {
    if (!pending) return;
    setBusy(true);
    setError("");
    try {
      const nextReadiness = await api.confirmGraphDeliveryOAuthPending(csrfToken, pending.id);
      setReadiness(nextReadiness);
      setConfirmedUser(pending);
      setPending(null);
      window.history.replaceState(null, "", "/settings/graph-delivery/success");
      notify({ tone: "success", title: "Graph delivery connected" });
    } catch (err) {
      setError(isApiError(err) ? err.message : "Graph Delivery connection could not be confirmed.");
    } finally {
      setBusy(false);
    }
  }

  async function cancelPending() {
    if (!pending) return;
    setBusy(true);
    setError("");
    try {
      await api.cancelGraphDeliveryOAuthPending(csrfToken, pending.id);
      notify({ tone: "info", title: "Graph delivery connection canceled" });
      navigateInApp("/delivery");
    } catch (err) {
      setError(isApiError(err) ? err.message : "Graph Delivery connection could not be canceled.");
      setBusy(false);
    }
  }

  const current = readiness?.graph_delivery ?? null;
  const pendingScopes = pending?.scopes ?? [];
  const pendingServiceUser = pending ? graphDeliveryServiceUserLabel(pending) : "-";
  const currentServiceUser = current?.configured ? graphDeliveryServiceUserLabel(current) : "None";
  const pendingScopeBadges = pendingScopes.map((scope) => ({ label: scope, tone: "success" as const }));

  return (
    <>
      <PageIntro
        eyebrow="Graph delivery"
        title={isSuccess || confirmedUser ? "Service user connected" : "Confirm service user"}
        description={
          isSuccess || confirmedUser
            ? "The delegated Graph Delivery service user is active."
            : "Review the authenticated Microsoft account before it is used for Graph Delivery."
        }
        actions={current ? <StatusBadge label={current.auth_status === "ready" ? "Ready" : healthStateLabel(current.auth_status)} tone={authStatusTone(current.auth_status)} /> : null}
      />
      {loading ? (
        <Card>
          <div className="table-state" role="status" aria-live="polite">
            <div className="spinner spinner--small" aria-hidden="true" />
            <p>Loading Graph Delivery connection...</p>
          </div>
        </Card>
      ) : error ? (
        <Card>
          <div className="table-state table-state--error" role="alert">
            <h3>Could not load Graph Delivery connection</h3>
            <p>{error}</p>
            <button className="secondary-button secondary-button--small" type="button" onClick={() => navigateInApp("/delivery")}>
              Back to delivery
            </button>
          </div>
        </Card>
      ) : confirmedUser || isSuccess ? (
        <div className="delivery-page delivery-operations-page graph-oauth-page">
          <section className="status-relay-hero status-relay-hero--success" aria-label="Graph Delivery connection success">
            <div className="status-relay-hero-main">
              <div className="graph-oauth-success-mark" aria-hidden="true">
                <CheckCircle focusable="false" />
              </div>
              <div>
                <p className="integration-kicker">Connection confirmed</p>
                <h2>Graph Delivery is connected</h2>
                <p>The confirmed service user is now active for delegated Microsoft Graph sends.</p>
              </div>
            </div>
            <div className="status-relay-metrics">
              <StatusOverviewMetric label="Service user" value={graphDeliveryServiceUserLabel(confirmedUser ?? current!)} detail="Active delegated sender." tone="success" />
              <StatusOverviewMetric label="Token" value={current?.access_token_expires_at ? formatRelativeTime(current.access_token_expires_at) : "Valid"} detail="Latest readiness state." tone="success" />
              <StatusOverviewMetric label="Scopes" value={`${(current?.scopes ?? []).length || "-"} granted`} detail="Delegated permissions." tone="success" />
              <StatusOverviewMetric label="Status" value={current ? healthStateLabel(current.auth_status) : "Ready"} detail="Graph Delivery readiness." tone="success" />
            </div>
          </section>
          <Card className="delivery-component-card delivery-component-card--success graph-oauth-card">
            <div className="graph-oauth-card-body">
              <section className="status-detail-section">
                <h3>Active service user</h3>
                <StatusFactList facts={graphDeliveryUserFacts(confirmedUser ?? current)} />
              </section>
              <div className="form-actions">
                <button className="primary-button secondary-button--small" type="button" onClick={() => navigateInApp("/delivery")}>
                  Back to delivery
                </button>
              </div>
            </div>
          </Card>
        </div>
      ) : pending ? (
        <div className="delivery-page delivery-operations-page graph-oauth-page">
          <section className="status-relay-hero status-relay-hero--warn" aria-label="Graph Delivery pending connection">
            <div className="status-relay-hero-main">
              <div className="status-relay-indicator status-relay-indicator--warn" aria-hidden="true" />
              <div>
                <p className="integration-kicker">Pending connection</p>
                <h2>Review the delegated sender before activation</h2>
                <p>The current Graph Delivery service user remains active until this connection is confirmed.</p>
              </div>
            </div>
            <div className="status-relay-metrics">
              <StatusOverviewMetric label="New user" value={pendingServiceUser} detail={pending.service_user_principal_name || pending.service_user_id || "Authenticated account."} tone="warn" />
              <StatusOverviewMetric label="Current user" value={currentServiceUser} detail={current?.service_user_principal_name || "Unchanged until confirm."} tone={current?.configured ? "neutral" : "warn"} />
              <StatusOverviewMetric label="Review window" value={formatRelativeTime(pending.expires_at)} detail="Pending approval expires." tone="warn" />
              <StatusOverviewMetric label="Scopes" value={`${pendingScopes.length} granted`} detail="Delegated permissions to review." tone="success" />
            </div>
          </section>
          <Card className="delivery-component-card delivery-component-card--warn graph-oauth-card">
            <div className="delivery-component-header graph-oauth-component-header">
              <div className="delivery-component-title">
                <span className="delivery-method-icon delivery-method-icon--graph-delivery" aria-hidden="true">
                  <Send focusable="false" />
                </span>
                <span>
                  <h2>New authenticated user</h2>
                  <p>This account will become active only after confirmation.</p>
                </span>
              </div>
              <div className="delivery-status-group">
                <span className="delivery-status-dot delivery-status-dot--warn" aria-hidden="true" />
                <strong>Pending</strong>
              </div>
              <div className="graph-oauth-actions">
                <button className="secondary-button secondary-button--small" type="button" onClick={() => void cancelPending()} disabled={busy}>
                  Cancel
                </button>
                <button className="primary-button secondary-button--small" type="button" onClick={() => void confirmPending()} disabled={busy}>
                  {busy ? "Confirming..." : "Use service user"}
                </button>
              </div>
            </div>
            <div className="delivery-inline-issues">
              <div className="delivery-inline-issue">
                <strong>Review required</strong>
                <span>Confirm only if the display name, user principal name, tenant and granted scopes match the intended Graph Delivery service account.</span>
              </div>
            </div>
            <div className="graph-oauth-detail-grid">
              <section className="status-detail-section">
                <h3>Pending service user</h3>
                <StatusFactList facts={graphDeliveryUserFacts(pending)} />
              </section>
              <section className="status-detail-section">
                <h3>Current active user</h3>
                {current?.configured ? <StatusFactList facts={graphDeliveryUserFacts(current)} /> : <EmptyState title="No active service user" body="Graph Delivery has no confirmed delegated sender yet." />}
              </section>
              <section className="status-detail-section graph-oauth-permissions">
                <h3>Granted scopes</h3>
                <p>{pendingScopes.length ? `${pendingScopes.length} delegated scopes were returned by Microsoft.` : "No scopes were reported for this pending connection."}</p>
                <div className="permission-badge-list">
                  {pendingScopeBadges.length ? (
                    pendingScopeBadges.map((badge) => (
                      <span className={classNames("permission-badge", `permission-badge--${badge.tone}`)} key={badge.label}>
                        {badge.label}
                      </span>
                    ))
                  ) : (
                    <span className="permission-badge permission-badge--warn">No scopes reported</span>
                  )}
                </div>
              </section>
              <section className="status-detail-section">
                <h3>Token window</h3>
                <StatusFactList
                  facts={[
                    { label: "Pending expires", value: formatRelativeTime(pending.expires_at), tone: "warn" },
                    { label: "Access token", value: pending.access_token_expires_at ? formatRelativeTime(pending.access_token_expires_at) : "-", tone: pending.access_token_expires_at ? "success" : "neutral" },
                  ]}
                />
              </section>
            </div>
          </Card>
        </div>
      ) : null}
    </>
  );
}

function graphDeliveryUserFacts(user: GraphDeliveryOAuthPendingOut | AdminReadinessOut["graph_delivery"] | null): StatusFact[] {
  if (!user) return [];
  return [
    { label: "Display name", value: graphDeliveryServiceUserLabel(user), tone: user.service_user_display_name ? "success" : "neutral" },
    { label: "UPN", value: user.service_user_principal_name || "-", tone: user.service_user_principal_name ? "success" : "neutral" },
    { label: "User ID", value: user.service_user_id || "-", tone: user.service_user_id ? "success" : "neutral" },
    { label: "Tenant ID", value: user.tenant_id || "-", tone: user.tenant_id ? "success" : "neutral" },
    { label: "Client ID", value: user.client_id || "-", tone: user.client_id ? "success" : "neutral" },
  ];
}

function navigateInApp(path: string) {
  window.history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function SettingsPage() {
  const { notify, session } = useAppContext();
  const [settings, setSettings] = useState<SettingItemOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
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
  const runtimeSettings = orderedSettings(RUNTIME_SETTING_KEYS, settingsByKey);
  const runtimeOverrideCount = runtimeSettings.filter((item) => item.is_overridden).length;
  const overrideBadge = runtimeOverrideCount > 0 ? `${runtimeOverrideCount} ${runtimeOverrideCount === 1 ? "override" : "overrides"}` : "All defaults";

  return (
    <>
      <PageIntro
        eyebrow="Configuration"
        title="Settings"
        description="Manage runtime defaults used by relay operations."
        actions={<StatusBadge label={overrideBadge} tone={runtimeOverrideCount > 0 ? "warn" : "neutral"} />}
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
          <SettingsOverviewStrip settingsByKey={settingsByKey} overrideCount={runtimeOverrideCount} />
          <RuntimeDefaultsCard
            settings={runtimeSettings}
            settingsByKey={settingsByKey}
            csrfToken={csrfToken}
            onChanged={refresh}
            notify={notify}
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
  manageActionItems?: RowActionItem[];
};

function buildBotIntegrationView(readiness: AdminReadinessOut, onCopy: (value: string, label: string) => void): IntegrationStatusView {
  const oauth = readiness.bot.oauth;
  const authStatus = readiness.bot.auth_status;
  const permissionTone = oauth.token.succeeded && oauth.token.roles.length ? "success" : oauth.token.succeeded ? "neutral" : "warn";
  return {
    id: "bot-framework",
    title: "Bot Framework",
    description: "Teams delivery",
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
  const attentionItems = readinessAttentionItems(authStatus, readiness.graph_lookup.message, oauth);
  if (readiness.graph_lookup.enabled && !readiness.graph_lookup.group_membership_lookup_ready) {
    attentionItems.push({
      title: "Graph group membership permission missing",
      description: readiness.graph_lookup.group_membership_message,
      tone: "warn",
    });
  }
  return {
    id: "graph-lookup",
    title: "Graph lookup",
    description: "Target lookup",
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
      {
        label: "Group membership",
        value: readiness.graph_lookup.group_membership_lookup_ready ? "Ready" : "Permission warning",
        tone: readiness.graph_lookup.group_membership_lookup_ready ? "success" : "warn",
      },
    ],
    capabilities: [
      { label: "Lookup mode", value: readiness.graph_lookup.enabled ? "Enabled" : "Disabled", tone: readiness.graph_lookup.enabled ? "success" : "neutral" },
      { label: "Credentials", value: graphCredentialLabel(readiness.graph_lookup.credential_source), tone: readiness.graph_lookup.credential_source === "missing" ? "warn" : "neutral" },
      { label: "Scope", value: compactScope(oauth.scope || oauth.token.audience) },
      {
        label: "Group roles",
        value: readiness.graph_lookup.group_membership_lookup_ready
          ? "GroupMember.Read.All / Directory.Read.All"
          : readiness.graph_lookup.group_membership_missing_roles.join(", ") || "Not verified",
        tone: readiness.graph_lookup.group_membership_lookup_ready ? "success" : "warn",
      },
    ],
    credentials: [
      ["Tenant ID", credentialStatusLabel(readiness.graph_lookup.credential_fields.tenant_id)],
      ["Client ID", credentialStatusLabel(readiness.graph_lookup.credential_fields.client_id)],
      ["Client secret", credentialStatusLabel(readiness.graph_lookup.credential_fields.client_secret)],
    ],
    permissionSummary: permissionSummary(oauth),
    permissionBadges: oauthPermissionBadges(oauth, permissionTone),
    attentionItems,
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
  const serviceUser = graphDeliveryServiceUserLabel(readiness);
  const missingScopes = new Set(readiness.missing_scopes.map((scope) => scope.toLowerCase()));
  return {
    id: "graph-delivery",
    title: "Graph delivery",
    description: "Delegated sends",
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
    manageActionItems: graphDeliveryManageItems({
      busy,
      configured: readiness.configured,
      enabled: readiness.enabled,
      onConnect,
      onDisconnect,
    }),
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
  detail?: string;
  label: string;
  tone?: StatusTone;
  value: string;
}) {
  return (
    <div className={classNames("status-overview-item", tone !== "neutral" && `status-overview-item--${tone}`)}>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <p>{detail}</p> : null}
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

function graphDeliveryManageItems({
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
}): RowActionItem[] {
  if (configured) {
    return [
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
    ];
  }

  return [
    {
      label: "Connect service user",
      icon: Power,
      onClick: onConnect,
      disabled: busy || !enabled,
    },
  ];
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
          <dt>URL reveal lifetime</dt>
          <dd>{readiness.runtime.webhook_url_reveal_ttl_hours} hours</dd>
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

function graphDeliveryServiceUserLabel(user: Pick<AdminReadinessOut["graph_delivery"], "service_user_display_name" | "service_user_principal_name" | "service_user_id">): string {
  return user.service_user_display_name || user.service_user_principal_name || user.service_user_id || "-";
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
