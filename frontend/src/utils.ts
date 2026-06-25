export function classNames(...tokens: Array<string | false | null | undefined>): string {
  return tokens.filter(Boolean).join(" ");
}

export function parseApiDateTime(value: string): Date {
  const trimmed = value.trim();
  const isoNaiveUtc = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$/i.test(trimmed);
  const hasTzSuffix = /Z$|[+-]\d{2}:\d{2}$/i.test(trimmed);
  return new Date(isoNaiveUtc && !hasTzSuffix ? `${trimmed}Z` : trimmed);
}

export function formatDateTime(value: string | null): string {
  if (!value) return "Not set";
  const date = parseApiDateTime(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function compactJson(value: Record<string, unknown>): string {
  const keys = Object.keys(value);
  if (!keys.length) return "-";
  return keys.map((key) => `${key}: ${String(value[key])}`).join(", ");
}
