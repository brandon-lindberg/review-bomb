import "server-only";

import type { MetadataRoute } from "next";
import { getServerApiUrl } from "@/lib/api-base-url";
import { getSiteUrl } from "@/lib/site-url";
import {
  buildStaticSitemapPages,
  buildSitemapEntityPages,
  validateSitemapInventory,
  type SitemapEntityEntry,
} from "@/lib/sitemap-entries";
import { buildSitemapIndexXml, buildUrlSetXml } from "@/lib/sitemap-xml";

export const SITEMAP_REVALIDATE_SECONDS = 3600;
const SITEMAP_STALE_SECONDS = 86_400;
const apiUrl = getServerApiUrl();
const siteUrl = getSiteUrl();

export const ENTITY_SITEMAP_TYPES = ["games", "journalists", "outlets"] as const;
export type EntitySitemapType = (typeof ENTITY_SITEMAP_TYPES)[number];

interface EntitySitemapConfig {
  labelKey: "title" | "name";
  combinedKey: "game_entries" | "journalist_entries" | "outlet_entries";
  minimumCount: number;
}

function readMinimumCount(environmentKey: string, fallback: number): number {
  const parsed = Number.parseInt(process.env[environmentKey] || "", 10);
  return Number.isFinite(parsed) && parsed >= 1 ? parsed : fallback;
}

const ENTITY_CONFIG: Record<EntitySitemapType, EntitySitemapConfig> = {
  games: {
    labelKey: "title",
    combinedKey: "game_entries",
    minimumCount: readMinimumCount("SITEMAP_MIN_GAMES", 15_000),
  },
  journalists: {
    labelKey: "name",
    combinedKey: "journalist_entries",
    minimumCount: readMinimumCount("SITEMAP_MIN_JOURNALISTS", 8_000),
  },
  outlets: {
    labelKey: "name",
    combinedKey: "outlet_entries",
    minimumCount: readMinimumCount("SITEMAP_MIN_OUTLETS", 500),
  },
};

const lastKnownGood = new Map<EntitySitemapType, MetadataRoute.Sitemap>();
const SITEMAP_API_PAGE_SIZE = 5000;

async function fetchJson(path: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${apiUrl}${path}`, {
    next: { revalidate: SITEMAP_REVALIDATE_SECONDS },
    headers: { Accept: "application/json" },
    signal: AbortSignal.timeout(20_000),
  });

  if (!response.ok) {
    throw new Error(`${path} returned ${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<Record<string, unknown>>;
}

async function fetchEntityEntries(type: EntitySitemapType): Promise<SitemapEntityEntry[]> {
  try {
    const buildPath = (page: number) =>
      `/stats/sitemap-data/${type}?page=${page}&per_page=${SITEMAP_API_PAGE_SIZE}`;
    const payload = await fetchJson(buildPath(1));
    if (!Array.isArray(payload.entries)) {
      throw new Error(`Invalid entries payload for ${type}`);
    }
    const firstEntries = payload.entries as SitemapEntityEntry[];
    const totalPages =
      typeof payload.total_pages === "number" && Number.isInteger(payload.total_pages)
        ? payload.total_pages
        : 1;

    if (totalPages <= 1) {
      return firstEntries;
    }

    const remainingPayloads = await Promise.all(
      Array.from({ length: totalPages - 1 }, (_, index) =>
        fetchJson(buildPath(index + 2)),
      ),
    );
    const remainingEntries = remainingPayloads.flatMap((pagePayload, index) => {
      if (!Array.isArray(pagePayload.entries)) {
        throw new Error(`Invalid page ${index + 2} entries payload for ${type}`);
      }
      return pagePayload.entries as SitemapEntityEntry[];
    });
    const entries = [...firstEntries, ...remainingEntries];
    if (typeof payload.total === "number" && entries.length !== payload.total) {
      throw new Error(
        `${type} sitemap API returned ${entries.length} entries but reported ${payload.total}`,
      );
    }
    return entries;
  } catch (primaryError) {
    console.error(`Primary ${type} sitemap fetch failed; trying combined endpoint.`, primaryError);
    const combinedPayload = await fetchJson("/stats/sitemap-data");
    const combinedEntries = combinedPayload[ENTITY_CONFIG[type].combinedKey];
    if (!Array.isArray(combinedEntries)) {
      throw new Error(`Invalid combined entries payload for ${type}`);
    }
    return combinedEntries as SitemapEntityEntry[];
  }
}

function validateEntityPages(
  type: EntitySitemapType,
  entries: SitemapEntityEntry[],
): MetadataRoute.Sitemap {
  const config = ENTITY_CONFIG[type];
  const result = buildSitemapEntityPages({
    siteUrl,
    entityType: type,
    entries,
    labelKey: config.labelKey,
  });

  if (result.skippedCount > 0) {
    throw new Error(`${type} sitemap contains ${result.skippedCount} malformed entries`);
  }
  if (result.invalidLastModifiedCount > 0) {
    throw new Error(
      `${type} sitemap contains ${result.invalidLastModifiedCount} invalid last_modified values`,
    );
  }
  validateSitemapInventory({
    pages: result.pages,
    minimumCount: config.minimumCount,
    label: type,
  });

  return result.pages;
}

export async function getEntitySitemapPages(
  type: EntitySitemapType,
): Promise<{ pages: MetadataRoute.Sitemap; source: "fresh" | "last-known-good" }> {
  try {
    const entries = await fetchEntityEntries(type);
    const pages = validateEntityPages(type, entries);
    lastKnownGood.set(type, pages);
    return { pages, source: "fresh" };
  } catch (error) {
    const cachedPages = lastKnownGood.get(type);
    if (cachedPages) {
      console.error(`Serving last-known-good ${type} sitemap after refresh failure.`, error);
      return { pages: cachedPages, source: "last-known-good" };
    }
    throw error;
  }
}

export function getStaticSitemapPages(): MetadataRoute.Sitemap {
  return buildStaticSitemapPages(siteUrl);
}

export function getSitemapIndexXml(): string {
  return buildSitemapIndexXml([
    { url: `${siteUrl}/sitemaps/static.xml` },
    ...ENTITY_SITEMAP_TYPES.map((type) => ({
      url: `${siteUrl}/sitemaps/${type}.xml`,
    })),
  ]);
}

export function sitemapXmlResponse(
  pages: MetadataRoute.Sitemap,
  source: "static" | "fresh" | "last-known-good",
): Response {
  return new Response(buildUrlSetXml(pages), {
    headers: {
      "Content-Type": "application/xml; charset=utf-8",
      "Cache-Control": `public, max-age=0, s-maxage=${SITEMAP_REVALIDATE_SECONDS}, stale-while-revalidate=${SITEMAP_STALE_SECONDS}`,
      "X-Sitemap-Source": source,
      "X-Sitemap-Url-Count": String(pages.length),
    },
  });
}

export function sitemapUnavailableResponse(error: unknown): Response {
  console.error("Sitemap unavailable.", error);
  return new Response("Sitemap temporarily unavailable.\n", {
    status: 503,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
      "Retry-After": "300",
      "X-Robots-Tag": "noindex",
    },
  });
}
