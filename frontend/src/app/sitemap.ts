import type { MetadataRoute } from "next";
import { buildEntityPath } from "@/lib/entity-paths";
import { getSiteUrl } from "@/lib/site-url";

const siteUrl = getSiteUrl();
const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

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
    const response = await fetch(`${apiUrl}/stats/sitemap-data`, {
      next: { revalidate: 3600 },
    });

    if (!response.ok) return staticPages;

    const data = await response.json();

    const gameEntries: Array<{ public_id: string; title?: string }> = data.game_entries || [];
    const gamePages: MetadataRoute.Sitemap = (
      gameEntries.length > 0
        ? gameEntries.map((entry) => ({
            url: `${siteUrl}${buildEntityPath("games", entry.title || entry.public_id, entry.public_id)}`,
            changeFrequency: "weekly" as const,
            priority: 0.7,
          }))
        : (data.game_public_ids || data.game_ids || []).map((id: string) => ({
            url: `${siteUrl}${buildEntityPath("games", undefined, id)}`,
            changeFrequency: "weekly" as const,
            priority: 0.7,
          }))
    );

    const journalistEntries: Array<{ public_id: string; name?: string }> = data.journalist_entries || [];
    const journalistPages: MetadataRoute.Sitemap = (
      journalistEntries.length > 0
        ? journalistEntries.map((entry) => ({
            url: `${siteUrl}${buildEntityPath("journalists", entry.name || entry.public_id, entry.public_id)}`,
            changeFrequency: "weekly" as const,
            priority: 0.7,
          }))
        : (data.journalist_public_ids || data.journalist_ids || []).map((id: string) => ({
            url: `${siteUrl}${buildEntityPath("journalists", undefined, id)}`,
            changeFrequency: "weekly" as const,
            priority: 0.7,
          }))
    );

    const outletEntries: Array<{ public_id: string; name?: string }> = data.outlet_entries || [];
    const outletPages: MetadataRoute.Sitemap = (
      outletEntries.length > 0
        ? outletEntries.map((entry) => ({
            url: `${siteUrl}${buildEntityPath("outlets", entry.name || entry.public_id, entry.public_id)}`,
            changeFrequency: "weekly" as const,
            priority: 0.7,
          }))
        : (data.outlet_public_ids || data.outlet_ids || []).map((id: string) => ({
            url: `${siteUrl}${buildEntityPath("outlets", undefined, id)}`,
            changeFrequency: "weekly" as const,
            priority: 0.7,
          }))
    );

    return [...staticPages, ...gamePages, ...journalistPages, ...outletPages];
  } catch {
    return staticPages;
  }
}
