import type { MetadataRoute } from "next";

export interface SitemapIndexEntry {
  url: string;
  lastModified?: string | Date;
}

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function serializeDate(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    throw new Error(`Invalid sitemap lastmod value: ${String(value)}`);
  }
  return date.toISOString();
}

export function buildUrlSetXml(entries: MetadataRoute.Sitemap): string {
  const urls = entries.map((entry) => {
    const fields = [
      `<loc>${escapeXml(entry.url)}</loc>`,
      ...(entry.lastModified
        ? [`<lastmod>${serializeDate(entry.lastModified)}</lastmod>`]
        : []),
      ...(entry.changeFrequency
        ? [`<changefreq>${entry.changeFrequency}</changefreq>`]
        : []),
      ...(entry.priority != null ? [`<priority>${entry.priority.toFixed(1)}</priority>`] : []),
    ];
    return `<url>${fields.join("")}</url>`;
  });

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ...urls,
    "</urlset>",
    "",
  ].join("\n");
}

export function buildSitemapIndexXml(entries: SitemapIndexEntry[]): string {
  const sitemaps = entries.map((entry) => {
    const fields = [
      `<loc>${escapeXml(entry.url)}</loc>`,
      ...(entry.lastModified
        ? [`<lastmod>${serializeDate(entry.lastModified)}</lastmod>`]
        : []),
    ];
    return `<sitemap>${fields.join("")}</sitemap>`;
  });

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ...sitemaps,
    "</sitemapindex>",
    "",
  ].join("\n");
}
