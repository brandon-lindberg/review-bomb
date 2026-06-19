import type { MetadataRoute } from "next";
import { getServerApiUrl } from "@/lib/api-base-url";
import { getSiteUrl } from "@/lib/site-url";
import { buildSitemapEntityPages, type SitemapEntityEntry } from "@/lib/sitemap-entries";

const siteUrl = getSiteUrl();
const apiUrl = getServerApiUrl();
export const revalidate = 3600;

interface SitemapEntityGroups {
  games: SitemapEntityEntry[];
  journalists: SitemapEntityEntry[];
  outlets: SitemapEntityEntry[];
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

async function fetchCombinedSitemapEntries(): Promise<SitemapEntityGroups> {
  const response = await fetch(`${apiUrl}/stats/sitemap-data`, {
    next: { revalidate },
  });

  if (!response.ok) {
    throw new Error(`Combined sitemap fetch failed: ${response.status} ${response.statusText}`);
  }

  const data = await response.json();
  return {
    games: Array.isArray(data.game_entries) ? data.game_entries : [],
    journalists: Array.isArray(data.journalist_entries) ? data.journalist_entries : [],
    outlets: Array.isArray(data.outlet_entries) ? data.outlet_entries : [],
  };
}

async function fetchEntityGroups(): Promise<SitemapEntityGroups> {
  const results = await Promise.allSettled([
    fetchSitemapEntries("/stats/sitemap-data/games"),
    fetchSitemapEntries("/stats/sitemap-data/journalists"),
    fetchSitemapEntries("/stats/sitemap-data/outlets"),
  ]);

  for (const result of results) {
    if (result.status === "rejected") {
      console.error("Sitemap entity fetch failed:", result.reason);
    }
  }

  const [gameResult, journalistResult, outletResult] = results;
  const groups = {
    games: gameResult.status === "fulfilled" ? gameResult.value : [],
    journalists: journalistResult.status === "fulfilled" ? journalistResult.value : [],
    outlets: outletResult.status === "fulfilled" ? outletResult.value : [],
  };

  const dynamicEntryCount =
    groups.games.length + groups.journalists.length + groups.outlets.length;

  if (dynamicEntryCount > 0) {
    return groups;
  }

  try {
    return await fetchCombinedSitemapEntries();
  } catch (error) {
    console.error("Combined sitemap entity fetch failed:", error);
    return groups;
  }
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

  const { games, journalists, outlets } = await fetchEntityGroups();
  const gameResult = buildSitemapEntityPages({
    siteUrl,
    entityType: "games",
    entries: games,
    labelKey: "title",
  });
  const journalistResult = buildSitemapEntityPages({
    siteUrl,
    entityType: "journalists",
    entries: journalists,
    labelKey: "name",
  });
  const outletResult = buildSitemapEntityPages({
    siteUrl,
    entityType: "outlets",
    entries: outlets,
    labelKey: "name",
  });

  const skippedEntryCount =
    gameResult.skippedCount + journalistResult.skippedCount + outletResult.skippedCount;
  if (skippedEntryCount > 0) {
    console.error(`Sitemap skipped ${skippedEntryCount} entity entries missing public_id or label.`);
  }

  const dynamicEntryCount =
    gameResult.pages.length + journalistResult.pages.length + outletResult.pages.length;
  if (dynamicEntryCount === 0) {
    console.error("Sitemap generation produced zero entity URLs; serving static pages only.");
  }

  return [
    ...staticPages,
    ...gameResult.pages,
    ...journalistResult.pages,
    ...outletResult.pages,
  ];
}
