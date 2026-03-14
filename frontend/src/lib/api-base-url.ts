const DEV_DEFAULT_API_URL = "http://localhost:8000/api/v1";

function normalizeApiUrl(value: string): string {
  return value.replace(/\/+$/, "");
}

function firstNonEmpty(values: Array<string | undefined>): string | null {
  for (const value of values) {
    const trimmed = value?.trim();
    if (trimmed) {
      return normalizeApiUrl(trimmed);
    }
  }
  return null;
}

export function getServerApiUrl(): string {
  const resolved = firstNonEmpty([
    process.env.API_URL,
    process.env.INTERNAL_API_URL,
    process.env.NEXT_PUBLIC_API_URL,
  ]);

  if (resolved) {
    return resolved;
  }

  if (process.env.NODE_ENV !== "production") {
    return DEV_DEFAULT_API_URL;
  }

  throw new Error(
    "Missing server API URL. Set API_URL, INTERNAL_API_URL, or NEXT_PUBLIC_API_URL.",
  );
}

export function getBrowserApiUrl(): string {
  const resolved = firstNonEmpty([process.env.NEXT_PUBLIC_API_URL]);
  return resolved ?? DEV_DEFAULT_API_URL;
}

export function getApiUrl(): string {
  return typeof window === "undefined" ? getServerApiUrl() : getBrowserApiUrl();
}
