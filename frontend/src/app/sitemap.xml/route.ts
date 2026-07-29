import {
  SITEMAP_REVALIDATE_SECONDS,
  getSitemapIndexXml,
} from "@/lib/server-sitemaps";

export const dynamic = "force-static";
export const revalidate = 3600;

export function GET(): Response {
  return new Response(getSitemapIndexXml(), {
    headers: {
      "Content-Type": "application/xml; charset=utf-8",
      "Cache-Control": `public, max-age=0, s-maxage=${SITEMAP_REVALIDATE_SECONDS}, stale-while-revalidate=86400`,
    },
  });
}
