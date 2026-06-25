import type { ThemePreference } from "./theme-context";
import { useTheme } from "./theme-context";
import { classNames } from "./utils";

const CYCLE: ThemePreference[] = ["system", "light", "dark"];

const PREFERENCE_LABEL: Record<ThemePreference, string> = {
  system: "System",
  light: "Light",
  dark: "Dark",
};

function nextPreference(current: ThemePreference): ThemePreference {
  const i = CYCLE.indexOf(current);
  return CYCLE[(i + 1) % CYCLE.length];
}

function ThemeIcon({ mode }: { mode: ThemePreference }) {
  const common = { className: "theme-toggle-icon", "aria-hidden": true as const };
  if (mode === "light") {
    return (
      <svg {...common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v1.5M12 20.5V22M4.22 4.22l1.06 1.06M18.72 18.72l1.06 1.06M2 12h1.5M20.5 12H22M4.22 19.78l1.06-1.06M18.72 5.28l1.06-1.06" />
      </svg>
    );
  }
  if (mode === "dark") {
    return (
      <svg {...common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    );
  }
  return (
    <svg {...common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <path d="M8 20h8M12 16v4" />
    </svg>
  );
}

export function ThemeToggle({ className, id }: { className?: string; id?: string }) {
  const { themePreference, setThemePreference } = useTheme();
  const btnId = id ?? "theme-toggle";
  const label = PREFERENCE_LABEL[themePreference];
  const nextLabel = PREFERENCE_LABEL[nextPreference(themePreference)];

  return (
    <div className={classNames("theme-toggle", className)}>
      <button
        id={btnId}
        type="button"
        className="theme-toggle-trigger"
        onClick={() => setThemePreference(nextPreference(themePreference))}
        aria-label={`Color theme: ${label}. Activate to switch to ${nextLabel}.`}
        title={`${label} - next: ${nextLabel}`}
      >
        <ThemeIcon mode={themePreference} />
      </button>
    </div>
  );
}
