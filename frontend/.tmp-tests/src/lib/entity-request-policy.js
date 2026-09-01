"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.resolveEntityRequest = resolveEntityRequest;
const entity_paths_1 = require("./entity-paths");
/**
 * Every entity page resolves through this call, and an "unavailable" result is
 * served to crawlers as a 503. The API shares a Postgres instance with the
 * scraper fleet, so a single slow moment must not de-index a page: transient
 * failures (5xx, dropped connections, a timed-out attempt) get a second and
 * third chance, while definitive answers (404, bad payload) return immediately.
 */
const DEFAULT_ATTEMPT_TIMEOUT_MS = 2500;
const DEFAULT_ATTEMPTS = 3;
const RETRY_BACKOFF_MS = [100, 250];
function getEntityLabel(entityType, payload) {
    const value = entityType === "games" ? payload.title : payload.name;
    return typeof value === "string" && value.trim().length > 0 ? value : null;
}
function defaultDelay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}
function attemptSignal(callerSignal, timeoutMs) {
    const timeout = AbortSignal.timeout(timeoutMs);
    return callerSignal ? AbortSignal.any([callerSignal, timeout]) : timeout;
}
async function attemptResolveEntityRequest(url, entityType, fetchImpl, signal) {
    let response;
    try {
        response = await fetchImpl(url, {
            headers: { Accept: "application/json" },
            signal,
        });
    }
    catch {
        // Network error, or this attempt's timeout fired.
        return { resolution: { kind: "unavailable" }, retryable: true };
    }
    if (response.status === 404) {
        return { resolution: { kind: "not_found" }, retryable: false };
    }
    if (!response.ok) {
        return { resolution: { kind: "unavailable" }, retryable: true };
    }
    let payload;
    try {
        payload = (await response.json());
    }
    catch {
        return { resolution: { kind: "unavailable" }, retryable: true };
    }
    const publicId = typeof payload.public_id === "string" ? payload.public_id.trim() : "";
    const label = getEntityLabel(entityType, payload);
    if (!publicId || !label) {
        // A well-formed 200 that is missing required fields is a data problem, not
        // a blip — retrying only multiplies load for the same answer.
        return { resolution: { kind: "unavailable" }, retryable: false };
    }
    return {
        resolution: {
            kind: "found",
            canonicalPath: (0, entity_paths_1.buildEntityPath)(entityType, label, publicId),
        },
        retryable: false,
    };
}
async function resolveEntityRequest({ apiUrl, entityType, entitySegment, fetchImpl = fetch, signal, timeoutMs = DEFAULT_ATTEMPT_TIMEOUT_MS, attempts = DEFAULT_ATTEMPTS, delayImpl = defaultDelay, }) {
    const { identifier } = (0, entity_paths_1.parseEntityRouteSegment)(entitySegment);
    const url = `${apiUrl}/${entityType}/${encodeURIComponent(identifier)}`;
    const budget = Math.max(1, attempts);
    let outcome = {
        resolution: { kind: "unavailable" },
        retryable: true,
    };
    for (let attempt = 0; attempt < budget; attempt += 1) {
        outcome = await attemptResolveEntityRequest(url, entityType, fetchImpl, attemptSignal(signal, timeoutMs));
        if (!outcome.retryable)
            return outcome.resolution;
        if (attempt === budget - 1)
            break;
        if (signal?.aborted)
            break;
        await delayImpl(RETRY_BACKOFF_MS[attempt] ?? RETRY_BACKOFF_MS.at(-1) ?? 0);
    }
    return outcome.resolution;
}
