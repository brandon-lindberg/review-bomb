import {
  ENTITY_SITEMAP_TYPES,
  getEntitySitemapPages,
  getStaticSitemapPages,
  sitemapUnavailableResponse,
  sitemapXmlResponse,
  type EntitySitemapType,
} from "@/lib/server-sitemaps";

export const dynamic = "force-dynamic";

interface RouteContext {
  params: Promise<{ name: string }>;
}

export async function GET(
  _request: Request,
  { params }: RouteContext,
): Promise<Response> {
  const { name } = await params;
  if (name === "static.xml") {
    return sitemapXmlResponse(getStaticSitemapPages(), "static");
  }

  const match = name.match(/^(games|journalists|outlets)\.xml$/);
  if (!match || !ENTITY_SITEMAP_TYPES.includes(match[1] as EntitySitemapType)) {
    return new Response("Sitemap not found.\n", {
      status: 404,
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "X-Robots-Tag": "noindex",
      },
    });
  }

  const type = match[1] as EntitySitemapType;
  try {
    const { pages, source } = await getEntitySitemapPages(type);
    return sitemapXmlResponse(pages, source);
  } catch (error) {
    return sitemapUnavailableResponse(error);
  }
}
