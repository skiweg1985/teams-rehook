import { useEffect, useMemo, useState, type FormEvent } from "react";

import { api } from "./api";
import { AppProvider, useAppContext } from "./app-context";
import { Card, DataTable, EmptyState, Field, LoadingScreen, Modal, PageIntro, StatusBadge, ToastViewport } from "./components";
import { ThemeToggle } from "./theme-toggle";
import type { AuditEventOut, DemoItemOut, DemoItemStatus, UserOut } from "./types";
import { classNames, compactJson, formatDateTime } from "./utils";

type RouteName = "dashboard" | "items" | "users" | "settings" | "logs";

const NAV: Array<{ route: RouteName; label: string; path: string; icon: string }> = [
  { route: "dashboard", label: "Dashboard", path: "/dashboard", icon: "D" },
  { route: "items", label: "Items", path: "/items", icon: "I" },
  { route: "users", label: "Users", path: "/users", icon: "U" },
  { route: "settings", label: "Settings", path: "/settings", icon: "S" },
  { route: "logs", label: "Logs", path: "/logs", icon: "L" },
];

function routeFromPath(pathname: string): RouteName {
  if (pathname === "/" || pathname === "/dashboard") return "dashboard";
  if (pathname === "/items") return "items";
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
