import {
  buildEntityPath,
  parseEntityRouteSegment,
  type EntityRouteType,
} from "./entity-paths";

export type EntityRequestResolution =
  | { kind: "found"; canonicalPath: string }
  | { kind: "not_found" }
  | { kind: "unavailable" };

/**
 * Every entity page resolves through this call, and an "unavailable" result is
 * served to crawlers as a 503. The API shares a Postgres instance with the
 * scraper fleet, so a single slow moment must not de-index a page: transient
 * failures (5xx, dropped connections, a timed-out attempt) get a second and
 * third chance, while definitive answers (404, bad payload) return immediately.
 */
const DEFAULT_ATTEMPT_TIMEOUT_MS = 2_500;
const DEFAULT_ATTEMPTS = 3;
const RETRY_BACKOFF_MS = [100, 250];

interface ResolveEntityRequestOptions {
  apiUrl: string;
  entityType: EntityRouteType;
  entitySegment: string;
  fetchImpl?: typeof fetch;
  /** Overall budget for all attempts; retries stop once it aborts. */
  signal?: AbortSignal;
  /** Per-attempt timeout, independent of the overall budget. */
  timeoutMs?: number;
  attempts?: number;
  /** Injectable so tests do not pay real backoff delays. */
  delayImpl?: (ms: number) => Promise<void>;
}

interface AttemptOutcome {
  resolution: EntityRequestResolution;
  retryable: boolean;
}

function getEntityLabel(
  entityType: EntityRouteType,
  payload: Record<string, unknown>,
): string | null {
  const value = entityType === "games" ? payload.title : payload.name;
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function defaultDelay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function attemptSignal(
  callerSignal: AbortSignal | undefined,
  timeoutMs: number,
): AbortSignal {
  const timeout = AbortSignal.timeout(timeoutMs);
  return callerSignal ? AbortSignal.any([callerSignal, timeout]) : timeout;
}

async function attemptResolveEntityRequest(
  url: string,
  entityType: EntityRouteType,
  fetchImpl: typeof fetch,
  signal: AbortSignal,
): Promise<AttemptOutcome> {
  let response: Response;
  try {
    response = await fetchImpl(url, {
      headers: { Accept: "application/json" },
      signal,
    });
  } catch {
    // Network error, or this attempt's timeout fired.
    return { resolution: { kind: "unavailable" }, retryable: true };
  }

  if (response.status === 404) {
    return { resolution: { kind: "not_found" }, retryable: false };
  }
  if (!response.ok) {
    return { resolution: { kind: "unavailable" }, retryable: true };
  }

  let payload: Record<string, unknown>;
  try {
    payload = (await response.json()) as Record<string, unknown>;
  } catch {
    return { resolution: { kind: "unavailable" }, retryable: true };
  }

  const publicId =
    typeof payload.public_id === "string" ? payload.public_id.trim() : "";
  const label = getEntityLabel(entityType, payload);

  if (!publicId || !label) {
    // A well-formed 200 that is missing required fields is a data problem, not
    // a blip — retrying only multiplies load for the same answer.
    return { resolution: { kind: "unavailable" }, retryable: false };
  }

  return {
    resolution: {
      kind: "found",
      canonicalPath: buildEntityPath(entityType, label, publicId),
    },
    retryable: false,
  };
}

export async function resolveEntityRequest({
  apiUrl,
  entityType,
  entitySegment,
  fetchImpl = fetch,
  signal,
  timeoutMs = DEFAULT_ATTEMPT_TIMEOUT_MS,
  attempts = DEFAULT_ATTEMPTS,
  delayImpl = defaultDelay,
}: ResolveEntityRequestOptions): Promise<EntityRequestResolution> {
  const { identifier } = parseEntityRouteSegment(entitySegment);
  const url = `${apiUrl}/${entityType}/${encodeURIComponent(identifier)}`;
  const budget = Math.max(1, attempts);

  let outcome: AttemptOutcome = {
    resolution: { kind: "unavailable" },
    retryable: true,
  };

  for (let attempt = 0; attempt < budget; attempt += 1) {
    outcome = await attemptResolveEntityRequest(
      url,
      entityType,
      fetchImpl,
      attemptSignal(signal, timeoutMs),
    );

    if (!outcome.retryable) return outcome.resolution;
    if (attempt === budget - 1) break;
    if (signal?.aborted) break;

    await delayImpl(RETRY_BACKOFF_MS[attempt] ?? RETRY_BACKOFF_MS.at(-1) ?? 0);
  }

  return outcome.resolution;
}
