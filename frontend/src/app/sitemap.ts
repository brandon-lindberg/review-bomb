import type { MetadataRoute } from "next";
import { buildEntityPath } from "@/lib/entity-paths";
import { getServerApiUrl } from "@/lib/api-base-url";
import { getSiteUrl } from "@/lib/site-url";

const siteUrl = getSiteUrl();
const apiUrl = getServerApiUrl();
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
    throw new Error(`Sitemap fetch failed for ${path}: ${response.status} ${response.statusText}`);
  }

  const data = await response.json();
  if (!Array.isArray(data.entries)) {
    throw new Error(`Sitemap fetch returned invalid payload for ${path}`);
  }

  return data.entries;
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
    { url: `${siteUrl}/faq`, changeFrequency: "monthly", priority: 0.4 },
    { url: `${siteUrl}/terms`, changeFrequency: "yearly", priority: 0.2 },
    { url: `${siteUrl}/privacy`, changeFrequency: "yearly", priority: 0.2 },
  ];

  const results = await Promise.allSettled([
    fetchSitemapEntries("/stats/sitemap-data/games"),
    fetchSitemapEntries("/stats/sitemap-data/journalists"),
    fetchSitemapEntries("/stats/sitemap-data/outlets"),
  ]);

  const [gameResult, journalistResult, outletResult] = results;
  const gameEntries = gameResult.status === "fulfilled" ? gameResult.value : [];
  const journalistEntries = journalistResult.status === "fulfilled" ? journalistResult.value : [];
  const outletEntries = outletResult.status === "fulfilled" ? outletResult.value : [];

  for (const result of results) {
    if (result.status === "rejected") {
      console.error("Sitemap entity fetch failed:", result.reason);
    }
  }

  const dynamicEntryCount =
    gameEntries.length + journalistEntries.length + outletEntries.length;

  if (dynamicEntryCount === 0) {
    if (process.env.NODE_ENV !== "production") {
      return staticPages;
    }

    throw new Error(
      "Sitemap generation produced zero entity URLs. Refusing to serve a truncated static-only sitemap in production.",
    );
  }

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
}
