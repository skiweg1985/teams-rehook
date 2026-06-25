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
