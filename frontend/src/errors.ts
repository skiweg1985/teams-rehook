import type { ApiError } from "./types";

export function isApiError(error: unknown): error is ApiError {
  if (typeof error !== "object" || error === null) {
    return false;
  }
  const candidate = error as Record<string, unknown>;
  return typeof candidate.status === "number" && typeof candidate.message === "string";
}
