export type EntityRouteType = "games" | "journalists" | "outlets";

const ENTITY_SEGMENT_SEPARATOR = "--";

export interface ParsedEntityRouteSegment {
  identifier: string;
  slug: string | null;
  isSlugged: boolean;
}

export function normalizeEntityRouteSegment(segment: string): string {
  const trimmedSegment = segment.trim().replace(/^\/+|\/+$/g, "");

  try {
    return decodeURIComponent(trimmedSegment);
  } catch {
    return trimmedSegment;
  }
}

export function slugifyEntityLabel(label: string | null | undefined): string {
  if (!label) return "";

  return label
    .trim()
    .normalize("NFKC")
    .toLocaleLowerCase("en-US")
    .replace(/[’'`]+/g, "")
    .replace(/&/g, " and ")
    .replace(/[^\p{Letter}\p{Number}]+/gu, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

export function buildEntitySegment(
  label: string | null | undefined,
  publicId: string | number
): string {
  const stableId = String(publicId).trim();
  const slug = slugifyEntityLabel(label);
  return slug ? `${slug}${ENTITY_SEGMENT_SEPARATOR}${stableId}` : stableId;
}

export function buildEntityPath(
  entityType: EntityRouteType,
  label: string | null | undefined,
  publicId: string | number
): string {
  return `/${entityType}/${buildEntitySegment(label, publicId)}`;
}

export function buildEntityUrl(
  siteUrl: string,
  entityType: EntityRouteType,
  label: string | null | undefined,
  publicId: string | number
): string {
  return `${siteUrl}${buildEntityPath(entityType, label, publicId)}`;
}

export function parseEntityRouteSegment(segment: string): ParsedEntityRouteSegment {
  const normalizedSegment = normalizeEntityRouteSegment(segment);
  const separatorIndex = normalizedSegment.lastIndexOf(ENTITY_SEGMENT_SEPARATOR);

  if (separatorIndex <= 0 || separatorIndex === normalizedSegment.length - ENTITY_SEGMENT_SEPARATOR.length) {
    return {
      identifier: normalizedSegment,
      slug: null,
      isSlugged: false,
    };
  }

  return {
    identifier: normalizedSegment.slice(separatorIndex + ENTITY_SEGMENT_SEPARATOR.length),
    slug: normalizedSegment.slice(0, separatorIndex) || null,
    isSlugged: true,
  };
}

export function buildPathWithQuery(
  path: string,
  query: Record<string, string | string[] | undefined>
): string {
  const params = new URLSearchParams();

  for (const [key, value] of Object.entries(query)) {
    if (value == null) continue;
    if (Array.isArray(value)) {
      for (const item of value) {
        params.append(key, item);
      }
      continue;
    }
    params.set(key, value);
  }

  const serialized = params.toString();
  return serialized ? `${path}?${serialized}` : path;
}
