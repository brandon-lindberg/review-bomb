import type { MetadataRoute } from "next";
import { buildEntityPath } from "@/lib/entity-paths";
import { getSiteUrl } from "@/lib/site-url";

const siteUrl = getSiteUrl();
const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
export const revalidate = 3600;

interface SitemapEntityEntry {
  public_id: string;
  name?: string;
  title?: string;
}

async function fetchSitemapEntries(path: string): Promise<SitemapEntityEntry[]> {
  const response = await fetch(`${apiUrl}${path}`, {
    next: { revalidate },
  });

  if (!response.ok) {
    return [];
  }

  const data = await response.json();
  return Array.isArray(data.entries) ? data.entries : [];
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticPages: MetadataRoute.Sitemap = [
    { url: `${siteUrl}/`, changeFrequency: "daily", priority: 1.0 },
    { url: `${siteUrl}/games`, changeFrequency: "daily", priority: 0.9 },
    { url: `${siteUrl}/journalists`, changeFrequency: "daily", priority: 0.9 },
    { url: `${siteUrl}/outlets`, changeFrequency: "daily", priority: 0.9 },
    { url: `${siteUrl}/leaderboards`, changeFrequency: "daily", priority: 0.8 },
    { url: `${siteUrl}/compare`, changeFrequency: "weekly", priority: 0.6 },
    { url: `${siteUrl}/search`, changeFrequency: "weekly", priority: 0.5 },
    { url: `${siteUrl}/about`, changeFrequency: "monthly", priority: 0.4 },
    { url: `${siteUrl}/terms`, changeFrequency: "yearly", priority: 0.2 },
    { url: `${siteUrl}/privacy`, changeFrequency: "yearly", priority: 0.2 },
  ];

  try {
    const [gameEntries, journalistEntries, outletEntries] = await Promise.all([
      fetchSitemapEntries("/stats/sitemap-data/games"),
      fetchSitemapEntries("/stats/sitemap-data/journalists"),
      fetchSitemapEntries("/stats/sitemap-data/outlets"),
    ]);

    const gamePages: MetadataRoute.Sitemap = gameEntries.map((entry) => ({
      url: `${siteUrl}${buildEntityPath("games", entry.title || entry.public_id, entry.public_id)}`,
      changeFrequency: "weekly" as const,
      priority: 0.7,
    }));

    const journalistPages: MetadataRoute.Sitemap = journalistEntries.map((entry) => ({
      url: `${siteUrl}${buildEntityPath("journalists", entry.name || entry.public_id, entry.public_id)}`,
      changeFrequency: "weekly" as const,
      priority: 0.7,
    }));

    const outletPages: MetadataRoute.Sitemap = outletEntries.map((entry) => ({
      url: `${siteUrl}${buildEntityPath("outlets", entry.name || entry.public_id, entry.public_id)}`,
      changeFrequency: "weekly" as const,
      priority: 0.7,
    }));

    return [...staticPages, ...gamePages, ...journalistPages, ...outletPages];
  } catch {
    return staticPages;
  }
}
