import {
  getGameReviews,
  getGameSimilarGames,
  getJournalistReviews,
  getOutletReviews,
  getRecentReviews,
  getStats,
  isApiNotFoundError,
} from "@/lib/api";
import { parseEntityRouteSegment } from "@/lib/entity-paths";
import {
  buildGameMarkdown,
  buildHomeMarkdown,
  buildJournalistMarkdown,
  buildOutletMarkdown,
} from "@/lib/markdown-pages";
import {
  getCachedGame,
  getCachedJournalist,
  getCachedOutlet,
} from "@/lib/server-entity-loaders";
import { getSiteUrl } from "@/lib/site-url";

// Markdown variants of public pages, reached through `Accept: text/markdown`
// content negotiation in src/proxy.ts (a rewrite, so the public URL stays the
// canonical HTML URL). All data comes from the same fetch-cached API loaders
// the HTML pages use, so this adds no new backend endpoints or query shapes.

const REVIEWS_PER_MARKDOWN_PAGE = 20;

function markdownResponse(body: string, status = 200): Response {
  return new Response(body, {
    status,
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      // Never let a shared cache hand the Markdown variant to a browser (or
      // the HTML variant to an agent) for negotiated URLs.
      Vary: "Accept",
      // The Markdown variant duplicates canonical HTML pages; keep direct
      // hits on /md/... out of search indexes.
      "X-Robots-Tag": "noindex",
      "Cache-Control": "public, max-age=0, s-maxage=60, stale-while-revalidate=300",
    },
  });
}

function notFound(): Response {
  return markdownResponse("# Not found\n\nNo Markdown representation exists for this page.\n", 404);
}

function serviceUnavailable(): Response {
  return new Response(
    "# Temporarily unavailable\n\nThis page is temporarily unavailable. Please try again shortly.\n",
    {
      status: 503,
      headers: {
        "Content-Type": "text/markdown; charset=utf-8",
        Vary: "Accept",
        "X-Robots-Tag": "noindex",
        "Cache-Control": "no-store",
        "Retry-After": "60",
      },
    },
  );
}

async function renderHome(siteUrl: string): Promise<Response> {
  const [statsResult, recentResult] = await Promise.allSettled([
    getStats(),
    getRecentReviews(10),
  ]);

  return markdownResponse(
    buildHomeMarkdown({
      siteUrl,
      stats: statsResult.status === "fulfilled" ? statsResult.value : null,
      recentReviews: recentResult.status === "fulfilled" ? recentResult.value : [],
    })
  );
}

async function renderGame(siteUrl: string, segment: string): Promise<Response> {
  const { identifier } = parseEntityRouteSegment(segment);
  const game = await getCachedGame(identifier);

  const [reviewsResult, similarResult] = await Promise.allSettled([
    getGameReviews(game.public_id, 1, REVIEWS_PER_MARKDOWN_PAGE),
    getGameSimilarGames(game.public_id, 4),
  ]);
  const reviewsPage = reviewsResult.status === "fulfilled" ? reviewsResult.value : null;

  return markdownResponse(
    buildGameMarkdown({
      siteUrl,
      game,
      reviews: reviewsPage?.items ?? [],
      totalReviewCount: reviewsPage?.total ?? game.critic_review_count ?? 0,
      similarGames: similarResult.status === "fulfilled" ? similarResult.value : [],
    })
  );
}

async function renderJournalist(siteUrl: string, segment: string): Promise<Response> {
  const { identifier } = parseEntityRouteSegment(segment);
  const journalist = await getCachedJournalist(identifier);

  const reviewsPage = await getJournalistReviews(
    journalist.public_id,
    1,
    REVIEWS_PER_MARKDOWN_PAGE
  ).catch(() => null);

  return markdownResponse(
    buildJournalistMarkdown({
      siteUrl,
      journalist,
      reviews: reviewsPage?.items ?? [],
      totalReviewCount: reviewsPage?.total ?? journalist.review_count ?? 0,
    })
  );
}

async function renderOutlet(siteUrl: string, segment: string): Promise<Response> {
  const { identifier } = parseEntityRouteSegment(segment);
  const outlet = await getCachedOutlet(identifier);

  const reviewsPage = await getOutletReviews(
    outlet.public_id,
    1,
    REVIEWS_PER_MARKDOWN_PAGE
  ).catch(() => null);

  return markdownResponse(
    buildOutletMarkdown({
      siteUrl,
      outlet,
      reviews: reviewsPage?.items ?? [],
      totalReviewCount: reviewsPage?.total ?? outlet.review_count ?? 0,
    })
  );
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ slug?: string[] }> }
): Promise<Response> {
  const { slug = [] } = await params;
  const siteUrl = getSiteUrl();

  try {
    if (slug.length === 0) {
      return await renderHome(siteUrl);
    }

    if (slug.length === 2) {
      const [entityType, segment] = slug;
      if (entityType === "games") return await renderGame(siteUrl, segment);
      if (entityType === "journalists") return await renderJournalist(siteUrl, segment);
      if (entityType === "outlets") return await renderOutlet(siteUrl, segment);
    }

    return notFound();
  } catch (error) {
    return isApiNotFoundError(error) ? notFound() : serviceUnavailable();
  }
}
