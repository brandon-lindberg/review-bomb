import {
  buildEntityPath,
  parseEntityRouteSegment,
  type EntityRouteType,
} from "./entity-paths";

export type EntityRequestResolution =
  | { kind: "found"; canonicalPath: string }
  | { kind: "not_found" }
  | { kind: "unavailable" };

interface ResolveEntityRequestOptions {
  apiUrl: string;
  entityType: EntityRouteType;
  entitySegment: string;
  fetchImpl?: typeof fetch;
  signal?: AbortSignal;
}

function getEntityLabel(
  entityType: EntityRouteType,
  payload: Record<string, unknown>,
): string | null {
  const value = entityType === "games" ? payload.title : payload.name;
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

export async function resolveEntityRequest({
  apiUrl,
  entityType,
  entitySegment,
  fetchImpl = fetch,
  signal,
}: ResolveEntityRequestOptions): Promise<EntityRequestResolution> {
  const { identifier } = parseEntityRouteSegment(entitySegment);

  try {
    const response = await fetchImpl(
      `${apiUrl}/${entityType}/${encodeURIComponent(identifier)}`,
      {
        headers: { Accept: "application/json" },
        signal,
      },
    );

    if (response.status === 404) {
      return { kind: "not_found" };
    }
    if (!response.ok) {
      return { kind: "unavailable" };
    }

    const payload = await response.json() as Record<string, unknown>;
    const publicId =
      typeof payload.public_id === "string" ? payload.public_id.trim() : "";
    const label = getEntityLabel(entityType, payload);

    if (!publicId || !label) {
      return { kind: "unavailable" };
    }

    return {
      kind: "found",
      canonicalPath: buildEntityPath(entityType, label, publicId),
    };
  } catch {
    return { kind: "unavailable" };
  }
}
