import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";

const STORAGE_KEY = "teams-rehook-theme";

export type ThemePreference = "light" | "dark" | "system";

type ThemeContextValue = {
  themePreference: ThemePreference;
  setThemePreference: (value: ThemePreference) => void;
  resolvedTheme: "light" | "dark";
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStoredPreference(): ThemePreference {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === "light" || raw === "dark" || raw === "system") return raw;
  } catch {
    /* ignore */
  }
  return "system";
}

function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyDocumentTheme(preference: ThemePreference, systemDark: boolean): "light" | "dark" {
  const resolved: "light" | "dark" =
    preference === "system" ? (systemDark ? "dark" : "light") : preference;
  const root = document.documentElement;
  root.dataset.themePreference = preference;
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved === "dark" ? "dark" : "light";
  return resolved;
}

export function ThemeProvider({ children }: PropsWithChildren) {
  const [themePreference, setThemePreferenceState] = useState<ThemePreference>(() => {
    if (typeof window === "undefined") return "system";
    return readStoredPreference();
  });
  const [systemDark, setSystemDark] = useState(() =>
    typeof window !== "undefined" ? systemPrefersDark() : false,
  );

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setSystemDark(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, themePreference);
    } catch {
      /* ignore */
    }
    applyDocumentTheme(themePreference, systemDark);
  }, [themePreference, systemDark]);

  const setThemePreference = useCallback((value: ThemePreference) => {
    setThemePreferenceState(value);
  }, []);

  const resolvedTheme: "light" | "dark" = useMemo(
    () => (themePreference === "system" ? (systemDark ? "dark" : "light") : themePreference),
    [themePreference, systemDark],
  );

  const value = useMemo<ThemeContextValue>(
    () => ({
      themePreference,
      setThemePreference,
      resolvedTheme,
    }),
    [resolvedTheme, setThemePreference, themePreference],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used inside ThemeProvider");
  }
  return ctx;
}
