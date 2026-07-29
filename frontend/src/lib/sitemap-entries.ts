import type { MetadataRoute } from "next";
import { buildEntityPath, type EntityRouteType } from "./entity-paths";

export interface SitemapEntityEntry {
  public_id?: unknown;
  name?: unknown;
  title?: unknown;
  last_modified?: unknown;
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
  invalidLastModifiedCount: number;
}

interface ValidateSitemapInventoryInput {
  pages: MetadataRoute.Sitemap;
  minimumCount: number;
  label: string;
}

function normalizedNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function normalizedLastModified(value: unknown): string | null {
  const rawValue = normalizedNonEmptyString(value);
  if (!rawValue) return null;

  const parsed = new Date(rawValue);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

export function buildSitemapEntityPages({
  siteUrl,
  entityType,
  entries,
  labelKey,
}: BuildSitemapEntityPagesInput): BuildSitemapEntityPagesResult {
  let skippedCount = 0;
  let invalidLastModifiedCount = 0;
  const pages: MetadataRoute.Sitemap = [];

  for (const entry of entries) {
    const publicId = normalizedNonEmptyString(entry.public_id);
    const label = normalizedNonEmptyString(entry[labelKey]);

    if (!publicId || !label) {
      skippedCount += 1;
      continue;
    }

    const lastModified = normalizedLastModified(entry.last_modified);
    if (entry.last_modified != null && !lastModified) {
      invalidLastModifiedCount += 1;
    }

    pages.push({
      url: `${siteUrl}${buildEntityPath(entityType, label, publicId)}`,
      ...(lastModified ? { lastModified } : {}),
      changeFrequency: "weekly" as const,
      priority: 0.7,
    });
  }

  return { pages, skippedCount, invalidLastModifiedCount };
}

export function validateSitemapInventory({
  pages,
  minimumCount,
  label,
}: ValidateSitemapInventoryInput): void {
  if (pages.length < minimumCount) {
    throw new Error(
      `${label} sitemap count ${pages.length} is below safety floor ${minimumCount}`,
    );
  }

  const uniqueUrls = new Set(pages.map((page) => page.url));
  if (uniqueUrls.size !== pages.length) {
    throw new Error(`${label} sitemap contains duplicate canonical URLs`);
  }
}

export function buildStaticSitemapPages(siteUrl: string): MetadataRoute.Sitemap {
  return [
    { url: `${siteUrl}/`, changeFrequency: "daily", priority: 1.0 },
    { url: `${siteUrl}/games`, changeFrequency: "daily", priority: 0.9 },
    { url: `${siteUrl}/news`, changeFrequency: "daily", priority: 0.8 },
    { url: `${siteUrl}/journalists`, changeFrequency: "daily", priority: 0.9 },
    { url: `${siteUrl}/outlets`, changeFrequency: "daily", priority: 0.9 },
    { url: `${siteUrl}/leaderboards`, changeFrequency: "daily", priority: 0.8 },
    { url: `${siteUrl}/compare`, changeFrequency: "weekly", priority: 0.6 },
    { url: `${siteUrl}/about`, changeFrequency: "monthly", priority: 0.4 },
    { url: `${siteUrl}/faq`, changeFrequency: "monthly", priority: 0.4 },
    { url: `${siteUrl}/terms`, changeFrequency: "yearly", priority: 0.2 },
    { url: `${siteUrl}/privacy`, changeFrequency: "yearly", priority: 0.2 },
  ];
}
