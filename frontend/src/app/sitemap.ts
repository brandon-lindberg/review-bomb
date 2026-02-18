import type { MetadataRoute } from "next";
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

    const gamePages: MetadataRoute.Sitemap = (data.game_ids || []).map(
      (id: number) => ({
        url: `${siteUrl}/games/${id}`,
        changeFrequency: "weekly" as const,
        priority: 0.7,
      })
    );

    const journalistPages: MetadataRoute.Sitemap = (
      data.journalist_ids || []
    ).map((id: number) => ({
      url: `${siteUrl}/journalists/${id}`,
      changeFrequency: "weekly" as const,
      priority: 0.7,
    }));

    const outletPages: MetadataRoute.Sitemap = (data.outlet_ids || []).map(
      (id: number) => ({
        url: `${siteUrl}/outlets/${id}`,
        changeFrequency: "weekly" as const,
        priority: 0.7,
      })
    );

    return [...staticPages, ...gamePages, ...journalistPages, ...outletPages];
  } catch {
    return staticPages;
  }
}
