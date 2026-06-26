import { useEffect, useMemo, useState, type FormEvent } from "react";

import { api } from "./api";
import { AppProvider, useAppContext } from "./app-context";
import { Card, DataTable, EmptyState, Field, LoadingScreen, Modal, PageIntro, StatusBadge, ToastViewport } from "./components";
import { isApiError } from "./errors";
import { ThemeToggle } from "./theme-toggle";
import type { AuditEventOut, DemoItemOut, DemoItemStatus, UserOut, WebhookDeliveryEventOut, WebhookRouteOut } from "./types";
import { classNames, compactJson, formatDateTime } from "./utils";

type RouteName = "dashboard" | "items" | "webhooks" | "users" | "settings" | "logs";

const NAV: Array<{ route: RouteName; label: string; path: string; icon: string }> = [
  { route: "dashboard", label: "Dashboard", path: "/dashboard", icon: "D" },
  { route: "items", label: "Items", path: "/items", icon: "I" },
  { route: "webhooks", label: "Webhooks", path: "/webhooks", icon: "W" },
  { route: "users", label: "Users", path: "/users", icon: "U" },
  { route: "settings", label: "Settings", path: "/settings", icon: "S" },
  { route: "logs", label: "Logs", path: "/logs", icon: "L" },
];

function routeFromPath(pathname: string): RouteName {
  if (pathname === "/" || pathname === "/dashboard") return "dashboard";
  if (pathname === "/items") return "items";
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
          <div className="app-mark">C</div>
          <ThemeToggle />
        </div>
        <div>
          <p className="eyebrow">Template Workspace</p>
          <h1>codex-app-skeleton</h1>
          <p className="lede">A quiet internal-tool starter with auth, admin surfaces and reusable UI primitives.</p>
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
          <div className="app-mark">C</div>
          <div>
            <strong>Codex App</strong>
            <span>Skeleton</span>
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
        {route === "items" ? <ItemsPage /> : null}
        {route === "webhooks" ? <WebhooksPage /> : null}
        {route === "users" ? <UsersPage /> : null}
        {route === "settings" ? <SettingsPage /> : null}
        {route === "logs" ? <LogsPage /> : null}
      </main>
    </div>
  );
}

function DashboardPage() {
  const [items, setItems] = useState<DemoItemOut[]>([]);

  useEffect(() => {
    void api.demoItems().then(setItems);
  }, []);

  const counts = useMemo(
    () => ({
      total: items.length,
      active: items.filter((item) => item.status !== "done").length,
      done: items.filter((item) => item.status === "done").length,
    }),
    [items],
  );

  return (
    <>
      <PageIntro
        eyebrow="Overview"
        title="Application dashboard"
        description="Use this page as the first operational screen for a new internal tool."
      />
      <div className="metric-grid">
        <Card className="metric-card">
          <span>Total records</span>
          <strong>{counts.total}</strong>
        </Card>
        <Card className="metric-card">
          <span>Active work</span>
          <strong>{counts.active}</strong>
        </Card>
        <Card className="metric-card">
          <span>Completed</span>
          <strong>{counts.done}</strong>
        </Card>
      </div>
      <Card title="Recent items" description="Seed data is intentionally generic and safe to replace.">
        <DataTable
          columns={["Title", "Status", "Updated"]}
          rows={items.slice(0, 5).map((item) => [
            <strong>{item.title}</strong>,
            <ItemStatusBadge status={item.status} />,
            formatDateTime(item.updated_at),
          ])}
          emptyTitle="No records yet"
          emptyBody="Create the first record from the Items page."
          rowKey={(index) => items[index]?.id ?? index}
        />
      </Card>
    </>
  );
}

function ItemStatusBadge({ status }: { status: DemoItemStatus }) {
  if (status === "done") return <StatusBadge label="Done" tone="success" />;
  if (status === "in_progress") return <StatusBadge label="In progress" tone="warn" />;
  return <StatusBadge label="To do" />;
}

function ItemsPage() {
  const { session, notify } = useAppContext();
  const [items, setItems] = useState<DemoItemOut[]>([]);
  const [editing, setEditing] = useState<DemoItemOut | null>(null);
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  async function refresh() {
    setItems(await api.demoItems());
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function deleteItem(item: DemoItemOut) {
    await api.deleteDemoItem(csrfToken, item.id);
    notify({ tone: "info", title: "Item deleted", description: item.title });
    await refresh();
  }

  return (
    <>
      <PageIntro
        eyebrow="Demo CRUD"
        title="Items"
        description="A small authenticated CRUD surface to replace with your app's primary object."
        actions={
          <button className="primary-button" type="button" onClick={() => setEditing(emptyItem())}>
            New item
          </button>
        }
      />
      <Card>
        <DataTable
          columns={["Title", "Summary", "Status", "Updated", ""]}
          rows={items.map((item) => [
            <strong>{item.title}</strong>,
            <span className="muted">{item.summary || "-"}</span>,
            <ItemStatusBadge status={item.status} />,
            formatDateTime(item.updated_at),
            <div className="row-actions">
              <button className="secondary-button secondary-button--small" type="button" onClick={() => setEditing(item)}>
                Edit
              </button>
              <button className="ghost-button ghost-button--small" type="button" onClick={() => void deleteItem(item)}>
                Delete
              </button>
            </div>,
          ])}
          emptyTitle="No items"
          emptyBody="Create a record to verify authenticated writes and table states."
          rowKey={(index) => items[index]?.id ?? index}
        />
      </Card>
      {editing ? (
        <ItemModal
          item={editing.id ? editing : null}
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await refresh();
          }}
        />
      ) : null}
    </>
  );
}

function emptyItem(): DemoItemOut {
  return {
    id: "",
    organization_id: "",
    owner_id: null,
    title: "",
    status: "todo",
    summary: "",
    created_at: "",
    updated_at: "",
  };
}

function ItemModal({
  item,
  initial,
  onClose,
  onSaved,
}: {
  item: DemoItemOut | null;
  initial: DemoItemOut;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { session, notify } = useAppContext();
  const [title, setTitle] = useState(initial.title);
  const [summary, setSummary] = useState(initial.summary);
  const [status, setStatus] = useState<DemoItemStatus>(initial.status);
  const [busy, setBusy] = useState(false);
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      if (item) {
        await api.updateDemoItem(csrfToken, item.id, { title, summary, status });
        notify({ tone: "success", title: "Item updated" });
      } else {
        await api.createDemoItem(csrfToken, { title, summary, status });
        notify({ tone: "success", title: "Item created" });
      }
      await onSaved();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={item ? "Edit item" : "New item"} onClose={onClose}>
      <form className="compact-form" onSubmit={submit}>
        <Field label="Title">
          <input value={title} required onChange={(event) => setTitle(event.target.value)} />
        </Field>
        <Field label="Status">
          <select value={status} onChange={(event) => setStatus(event.target.value as DemoItemStatus)}>
            <option value="todo">To do</option>
            <option value="in_progress">In progress</option>
            <option value="done">Done</option>
          </select>
        </Field>
        <Field label="Summary">
          <textarea value={summary} onChange={(event) => setSummary(event.target.value)} />
        </Field>
        <div className="form-actions">
          <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="primary-button" type="submit" disabled={busy}>
            {busy ? "Saving..." : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function WebhooksPage() {
  const { session, notify } = useAppContext();
  const [routes, setRoutes] = useState<WebhookRouteOut[]>([]);
  const [editing, setEditing] = useState<WebhookRouteOut | null>(null);
  const [viewingLogs, setViewingLogs] = useState<WebhookRouteOut | null>(null);
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
      notify({ tone: "success", title: "Test delivered", description: route.target_name });
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

  async function copyWebhookUrl(route: WebhookRouteOut) {
    if (!route.webhook_url) return;
    await navigator.clipboard.writeText(route.webhook_url);
    notify({ tone: "success", title: "Webhook URL copied", description: route.name });
  }

  async function regenerateWebhookUrl(route: WebhookRouteOut) {
    if (!window.confirm(`Generate a new relay URL for "${route.name}"? The previous URL will stop working.`)) return;
    setRegeneratingId(route.id);
    try {
      const updated = await api.regenerateWebhookRouteUrl(csrfToken, route.id);
      if (updated.webhook_url) await navigator.clipboard.writeText(updated.webhook_url);
      notify({ tone: "success", title: "Webhook URL regenerated", description: "The new URL was copied." });
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
          <button className="primary-button" type="button" onClick={() => setEditing(emptyWebhookRoute(botDefaultServiceUrl))}>
            New route
          </button>
        }
      />
      <Card>
        <DataTable
          columns={["Route", "Source", "Target", "Active", "Last delivery", "Relay URL", ""]}
          rows={routes.map((route) => [
            <strong>{route.name}</strong>,
            <span className="muted">{route.source_system || "-"}</span>,
            <div className="stacked-cell">
              <strong>{route.target_name}</strong>
              <span className="muted">Bot conversation</span>
            </div>,
            route.is_active ? <StatusBadge label="Active" tone="success" /> : <StatusBadge label="Disabled" tone="warn" />,
            <DeliveryStatusBadge route={route} />,
            route.webhook_url ? (
              <button className="secondary-button secondary-button--small" type="button" onClick={() => void copyWebhookUrl(route)}>
                Copy URL
              </button>
            ) : (
              <span className="muted">Unavailable for old route</span>
            ),
            <div className="row-actions">
              <button
                className="secondary-button secondary-button--small"
                type="button"
                disabled={testingId === route.id}
                onClick={() => void testRoute(route)}
              >
                {testingId === route.id ? "Testing..." : "Test"}
              </button>
              <button className="secondary-button secondary-button--small" type="button" onClick={() => setEditing(route)}>
                Edit
              </button>
              <button className="secondary-button secondary-button--small" type="button" onClick={() => setViewingLogs(route)}>
                Logs
              </button>
              <button
                className="secondary-button secondary-button--small"
                type="button"
                disabled={regeneratingId === route.id}
                onClick={() => void regenerateWebhookUrl(route)}
              >
                {regeneratingId === route.id ? "Regenerating..." : "Regenerate URL"}
              </button>
              <button className="ghost-button ghost-button--small" type="button" onClick={() => void deleteRoute(route)}>
                Delete
              </button>
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
    </>
  );
}

function DeliveryStatusBadge({ route }: { route: WebhookRouteOut }) {
  if (!route.last_delivery_status) return <span className="muted">Not tested</span>;
  const label = `${route.last_delivery_status}${route.last_delivery_at ? ` · ${formatDateTime(route.last_delivery_at)}` : ""}`;
  if (route.last_delivery_status === "delivered") return <StatusBadge label={label} tone="success" />;
  if (route.last_delivery_status === "failed") return <StatusBadge label={label} tone="danger" />;
  return <StatusBadge label={label} tone="warn" />;
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
    webhook_url: null,
    webhook_url_available: false,
    last_delivery_status: null,
    last_delivery_at: null,
    created_at: "",
    updated_at: "",
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
  const [createdWebhookUrl, setCreatedWebhookUrl] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const csrfToken = session.status === "authenticated" ? session.csrfToken : "";

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
        notify({ tone: "success", title: "Webhook route created", description: "Copy the generated URL now." });
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
      description="Create stable relay URLs and map them to Teams bot conversations."
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
        <Field label="Teams target name">
          <input value={targetName} required maxLength={200} onChange={(event) => setTargetName(event.target.value)} />
        </Field>
        <Field label="Bot service URL">
          <input value={botServiceUrl} required onChange={(event) => setBotServiceUrl(event.target.value)} />
        </Field>
        <Field label="Bot conversation ID">
          <textarea value={botConversationId} required onChange={(event) => setBotConversationId(event.target.value)} />
        </Field>
        {createdWebhookUrl ? (
          <div className="webhook-url-box">
            <strong>Relay webhook URL</strong>
            <code>{createdWebhookUrl}</code>
            <small>This URL is also available in the route table for copying later.</small>
          </div>
        ) : null}
        {error ? <p className="form-error">{error}</p> : null}
        <div className="form-actions">
          <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>
            {createdWebhookUrl ? "Done" : "Cancel"}
          </button>
          <button className="primary-button" type="submit" disabled={busy || Boolean(createdWebhookUrl)}>
            {busy ? "Saving..." : route ? "Save" : "Create route"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function WebhookDeliveryLogsModal({ route, onClose }: { route: WebhookRouteOut; onClose: () => void }) {
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
        if (mounted) setEvents(rows);
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
  }, [route.id]);

  return (
    <Modal title={`Delivery logs: ${route.name}`} description="Recent delivery attempts for this webhook route." onClose={onClose}>
      {loading ? <p className="muted">Loading delivery logs...</p> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!loading && !error ? (
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
        />
      ) : null}
    </Modal>
  );
}

function DeliveryEventStatusBadge({ status }: { status: WebhookDeliveryEventOut["status"] }) {
  if (status === "delivered") return <StatusBadge label="Delivered" tone="success" />;
  if (status === "failed") return <StatusBadge label="Failed" tone="danger" />;
  return <StatusBadge label="Rejected" tone="warn" />;
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
        description="A ready-made admin table for the seeded organization."
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
        description="Use these panels as placeholders for app-specific preferences and operational controls."
      />
      <div className="settings-grid">
        <Card title="Application" description="General metadata and environment defaults.">
          <dl className="definition-list">
            <dt>Template</dt>
            <dd>codex-app-skeleton</dd>
            <dt>Stack</dt>
            <dd>FastAPI, Postgres, React, Vite</dd>
            <dt>Theme</dt>
            <dd>Light, dark and system preference</dd>
          </dl>
        </Card>
        <Card title="Next edits" description="Replace demo records with your domain model.">
          <ul className="check-list">
            <li>Rename app title and environment variables.</li>
            <li>Replace DemoItem with the first real resource.</li>
            <li>Expand roles and permissions where the product needs them.</li>
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
        description="A compact audit stream for authenticated actions."
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
          emptyBody="Log entries appear after sign-in or item changes."
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
