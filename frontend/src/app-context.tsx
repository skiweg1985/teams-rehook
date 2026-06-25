import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";

import { api } from "./api";
import type { ApiError, SessionState, Toast, UserOut } from "./types";

type AppContextValue = {
  session: SessionState;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
  notify: (toast: Omit<Toast, "id">) => void;
  dismissToast: (id: number) => void;
  toasts: Toast[];
};

const AppContext = createContext<AppContextValue | null>(null);

function isApiError(error: unknown): error is ApiError {
  return typeof error === "object" && error !== null && "status" in error && "message" in error;
}

export function AppProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<SessionState>({
    status: "booting",
    user: null,
    csrfToken: "",
  });
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const notify = useCallback(
    (toast: Omit<Toast, "id">) => {
      const id = Date.now() + Math.floor(Math.random() * 1000);
      setToasts((current) => [...current, { ...toast, id }]);
      window.setTimeout(() => dismissToast(id), 4200);
    },
    [dismissToast],
  );

  const setAuthenticatedSession = (user: UserOut, csrfToken: string) => {
    setSession({ status: "authenticated", user, csrfToken });
  };

  const refreshSession = useCallback(async () => {
    try {
      const response = await api.me();
      setAuthenticatedSession(response.user, response.csrf_token);
    } catch (error) {
      setSession({ status: "anonymous", user: null, csrfToken: "" });
      if (isApiError(error) && error.status === 401) return;
      notify({
        tone: "error",
        title: "Session bootstrap failed",
        description: isApiError(error) ? error.message : "Unexpected error while loading your session.",
      });
    }
  }, [notify]);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      const response = await api.login(email, password);
      setAuthenticatedSession(response.user, response.csrf_token);
      notify({ tone: "success", title: "Signed in", description: `Welcome back, ${response.user.display_name}.` });
    },
    [notify],
  );

  const logout = useCallback(async () => {
    const csrfToken = session.status === "authenticated" ? session.csrfToken : "";
    try {
      if (csrfToken) await api.logout(csrfToken);
    } finally {
      setSession({ status: "anonymous", user: null, csrfToken: "" });
      notify({ tone: "info", title: "Signed out" });
    }
  }, [notify, session]);

  const value = useMemo<AppContextValue>(
    () => ({ session, login, logout, refreshSession, notify, dismissToast, toasts }),
    [dismissToast, login, logout, notify, refreshSession, session, toasts],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppContext(): AppContextValue {
  const context = useContext(AppContext);
  if (!context) throw new Error("useAppContext must be used inside AppProvider");
  return context;
}
