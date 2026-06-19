import type { MetadataRoute } from "next";
import { buildEntityPath, type EntityRouteType } from "./entity-paths";

export interface SitemapEntityEntry {
  public_id?: unknown;
  name?: unknown;
  title?: unknown;
}

type SitemapLabelKey = "name" | "title";

interface BuildSitemapEntityPagesInput {
  siteUrl: string;
  entityType: EntityRouteType;
  entries: SitemapEntityEntry[];
  labelKey: SitemapLabelKey;
}

interface BuildSitemapEntityPagesResult {
  pages: MetadataRoute.Sitemap;
  skippedCount: number;
}

function normalizedNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function buildSitemapEntityPages({
  siteUrl,
  entityType,
  entries,
  labelKey,
}: BuildSitemapEntityPagesInput): BuildSitemapEntityPagesResult {
  let skippedCount = 0;
  const pages: MetadataRoute.Sitemap = [];

  for (const entry of entries) {
    const publicId = normalizedNonEmptyString(entry.public_id);
    const label = normalizedNonEmptyString(entry[labelKey]);

    if (!publicId || !label) {
      skippedCount += 1;
      continue;
    }

    pages.push({
      url: `${siteUrl}${buildEntityPath(entityType, label, publicId)}`,
      changeFrequency: "weekly" as const,
      priority: 0.7,
    });
  }

  return { pages, skippedCount };
}
