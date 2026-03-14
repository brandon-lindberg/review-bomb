import { GameAvatar } from "@/components/GameAvatar";
import Link from "next/link";
import { getStats, getRecentReviews, getGames, getNews, getTrendingGames } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { JsonLd } from "@/components/JsonLd";
import { NewsCard } from "@/components/NewsCard";
import { getDisplayDisparity } from "@/lib/disparity-colors";
import { buildEntityPath } from "@/lib/entity-paths";
import { getSiteUrl } from "@/lib/site-url";

// Keep the home page fresh without forcing near-continuous server regeneration.
// Hot sub-sections already use shorter API/fetch caches where needed.
export const revalidate = 15;

const siteUrl = getSiteUrl();

function isUnreleasedNow(gameReleaseDate: string | null): boolean {
  if (!gameReleaseDate) return false;
  const releaseDate = new Date(`${gameReleaseDate}T00:00:00`);
  if (Number.isNaN(releaseDate.getTime())) return false;
  return releaseDate.getTime() > Date.now();
}

function getReleaseDateTimestamp(gameReleaseDate: string | null): number | null {
  if (!gameReleaseDate) return null;
  const releaseDate = new Date(`${gameReleaseDate}T00:00:00`);
  if (Number.isNaN(releaseDate.getTime())) return null;
  return releaseDate.getTime();
}

function getDateTimeTimestamp(dateTime: string | null): number | null {
  if (!dateTime) return null;
  const parsed = new Date(dateTime);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.getTime();
}

export default async function Home() {
  let stats = null;
  let recentReviews = null;
  let recentGames = null;
  let recentNews = null;
  let trendingGames = null;

  try {
    [stats, recentReviews, recentGames, recentNews, trendingGames] = await Promise.all([
      getStats(),
      getRecentReviews(5),
      getGames(1, 5, "release_date", "desc"),
      getNews(1, 5).catch(() => null),
      getTrendingGames(8, 48).catch(() => null),
    ]);
  } catch (error) {
    console.error("Error fetching data:", error);
  }

  const sortedRecentReviews = recentReviews
    ? [...recentReviews].sort((a, b) => {
        const aIsUnreleased = isUnreleasedNow(a.game_release_date);
        const bIsUnreleased = isUnreleasedNow(b.game_release_date);
        if (aIsUnreleased !== bIsUnreleased) return aIsUnreleased ? 1 : -1;

        const aPublishedTs = getDateTimeTimestamp(a.published_at);
        const bPublishedTs = getDateTimeTimestamp(b.published_at);

        if (aPublishedTs == null && bPublishedTs == null) return b.id - a.id;
        if (aPublishedTs == null) return 1;
        if (bPublishedTs == null) return -1;
        if (aPublishedTs !== bPublishedTs) return bPublishedTs - aPublishedTs;
        return b.id - a.id;
      })
    : [];

  const sortedRecentGames = recentGames
    ? [...recentGames.items].sort((a, b) => {
        const aReleaseTs = getReleaseDateTimestamp(a.release_date);
        const bReleaseTs = getReleaseDateTimestamp(b.release_date);

        const aIsUnreleased = isUnreleasedNow(a.release_date);
        const bIsUnreleased = isUnreleasedNow(b.release_date);
        if (aIsUnreleased !== bIsUnreleased) return aIsUnreleased ? 1 : -1;

        if (aReleaseTs == null && bReleaseTs == null) return b.id - a.id;
        if (aReleaseTs == null) return 1;
        if (bReleaseTs == null) return -1;
        if (aReleaseTs !== bReleaseTs) return bReleaseTs - aReleaseTs;
        return b.id - a.id;
      })
    : [];

  const websiteJsonLd = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "ReviewDisparity",
    url: `${siteUrl}/`,
    description:
      "Track the disparity between game journalist review scores and user scores from Steam and Metacritic.",
    potentialAction: {
      "@type": "SearchAction",
      target: {
        "@type": "EntryPoint",
        urlTemplate: `${siteUrl}/search?q={search_term_string}`,
      },
      "query-input": "required name=search_term_string",
    },
  };

  const trendingTickerItems = trendingGames?.items
    ? [...trendingGames.items, ...trendingGames.items]
    : [];
  const featuredTrend = trendingGames?.items?.[0] ?? null;
  const featuredReview = sortedRecentReviews[0] ?? null;

  return (
    <div className="space-y-8">
      <JsonLd data={websiteJsonLd} />
      <section className="space-y-5 py-2 text-center">
        <div className="mx-auto max-w-4xl space-y-4">
          <h1
            className="mx-auto max-w-4xl text-5xl font-extrabold tracking-tight sm:text-6xl lg:text-7xl"
            style={{ color: "var(--foreground)", lineHeight: 0.95 }}
          >
            See where critics and players split.
          </h1>
          <p
            className="mx-auto max-w-3xl text-lg leading-8 sm:text-xl"
            style={{ color: "var(--foreground-muted)" }}
          >
            ReviewDisparity maps the distance between critic scoring and player sentiment across
            games, journalists, and outlets so the strongest patterns are visible immediately.
          </p>
        </div>

        {stats && (
          <div className="route-kpis justify-center">
            <span className="route-kpi">
              <span className="route-kpi__value">{stats.total_journalists.toLocaleString()}</span>
              <span className="route-kpi__label">Journalists</span>
            </span>
            <span className="route-kpi">
              <span className="route-kpi__value">{stats.total_outlets.toLocaleString()}</span>
              <span className="route-kpi__label">Outlets</span>
            </span>
            <span className="route-kpi">
              <span className="route-kpi__value">{stats.total_games.toLocaleString()}</span>
              <span className="route-kpi__label">Games</span>
            </span>
            <span className="route-kpi">
              <span className="route-kpi__value">{stats.total_reviews.toLocaleString()}</span>
              <span className="route-kpi__label">Reviews</span>
            </span>
            {featuredTrend && (
              <span className="route-kpi">
                <span className="route-kpi__value">{featuredTrend.title}</span>
                <span className="route-kpi__label">Trending</span>
              </span>
            )}
            {featuredReview && (
              <span className="route-kpi">
                <span className="route-kpi__value">{featuredReview.game_title}</span>
                <span className="route-kpi__label">Latest review</span>
              </span>
            )}
          </div>
        )}
      </section>

      {/* Trending Games */}
      {trendingGames && trendingGames.items.length > 0 && (
        <section className="site-panel min-w-0 overflow-hidden rounded-[1.5rem]">
          <div className="flex items-center min-w-0">
            <div
              className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.08em] shrink-0"
              style={{ color: "var(--color-rust)", borderRight: "1px solid var(--border)" }}
            >
              Trending
            </div>
            <div className="trending-ticker-mask flex-1 min-w-0">
              <div className="trending-ticker-track">
                {trendingTickerItems.map((item, index) => {
                  const gameHref = item.game_public_id
                    ? buildEntityPath("games", item.title, item.game_public_id)
                    : null;
                  const articleHref = !gameHref && item.latest_article_url ? item.latest_article_url : null;
                  const content = (
                    <>
                      <span className="text-[11px] font-semibold" style={{ color: "var(--color-rust)" }}>
                        #{item.rank}
                      </span>
                      <span className="font-medium">{item.title}</span>
                      {Boolean(gameHref) && item.is_upcoming && (
                        <span className="text-[10px] uppercase tracking-[0.08em]" style={{ color: "var(--foreground-muted)" }}>
                          upcoming
                        </span>
                      )}
                    </>
                  );

                  if (gameHref) {
                    return (
                      <Link
                        key={`${item.trend_key}-${index}`}
                        href={gameHref}
                        className="trending-ticker-item"
                      >
                        {content}
                      </Link>
                    );
                  }

                  if (articleHref) {
                    return (
                      <a
                        key={`${item.trend_key}-${index}`}
                        href={articleHref}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="trending-ticker-item"
                      >
                        {content}
                      </a>
                    );
                  }

                  return (
                    <span
                      key={`${item.trend_key}-${index}`}
                      className="trending-ticker-item trending-ticker-item-static"
                      aria-disabled="true"
                    >
                      {content}
                    </span>
                  );
                })}
              </div>
            </div>
            <div
              className="hidden md:block px-3 py-3 text-[11px] shrink-0"
              style={{ color: "var(--foreground-muted)", borderLeft: "1px solid var(--border)" }}
            >
              {trendingGames.window_hours}h
            </div>
          </div>
        </section>
      )}

      {/* Recent Content */}
      <div className="grid md:grid-cols-2 gap-8">
        {/* Recent Reviews */}
        {sortedRecentReviews.length > 0 && (
          <section className="site-panel min-w-0 overflow-hidden rounded-[1.5rem] p-6">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <span className="site-data-label">Live feed</span>
                <h2 className="mt-2 text-2xl font-bold" style={{ color: "var(--foreground)" }}>
                  Recent Reviews
                </h2>
              </div>
              <Link
                href="/journalists"
                className="site-button site-button-secondary"
                style={{ color: "var(--color-rust)" }}
              >
                Browse All
              </Link>
            </div>
            <div className="space-y-3">
              {sortedRecentReviews.map((review) => {
                const disparity = getDisplayDisparity(review.disparity_steam, review.disparity_metacritic);
                const unreleasedNow = isUnreleasedNow(review.game_release_date);
                const isPreReleaseReview = (review.review_timing === "early") || unreleasedNow;
                const launchDateLabel = review.game_release_date
                  ? new Date(`${review.game_release_date}T00:00:00`).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })
                  : null;
                return (
                  <div
                    key={review.id}
                    className="site-list-item block rounded-2xl border-0 px-0 py-3 first:pt-0 last:pb-0"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 min-w-0">
                          <Link
                            href={buildEntityPath("games", review.game_title, review.game_public_id ?? review.game_id)}
                            className="font-medium hover:underline block truncate flex-1"
                            style={{ color: "var(--foreground)" }}
                            title={review.game_title ?? undefined}
                          >
                            {review.game_title}
                          </Link>
                          {isPreReleaseReview && (
                            <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium bg-amber-100 text-amber-800 shrink-0">
                              Pre-release Review
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-sm min-w-0 overflow-hidden" style={{ color: "var(--foreground-muted)" }}>
                          <Link
                            href={buildEntityPath("journalists", review.journalist_name, review.journalist_public_id ?? review.journalist_id)}
                            className="hover:underline truncate shrink-0 max-w-[45%]"
                          >
                            {review.journalist_name}
                          </Link>
                          {review.outlet_name && (
                            <>
                              <span className="shrink-0">•</span>
                              <span className="truncate">{review.outlet_name}</span>
                            </>
                          )}
                        </div>
                        <p className="text-xs mt-1" style={{ color: "var(--foreground-muted)" }}>
                          {review.published_at
                            ? new Date(review.published_at).toLocaleDateString("en-US", {
                                month: "short",
                                day: "numeric",
                                year: "numeric",
                              })
                            : "Unknown date"}
                          {" • "}
                          Score: {review.score_normalized != null ? Number(review.score_normalized).toFixed(0) : "N/A"}
                          {unreleasedNow && launchDateLabel && (
                            <>
                              {" • "}
                              Launches {launchDateLabel}
                            </>
                          )}
                        </p>
                      </div>
                      {disparity !== null && (
                        <DisparityBadge disparity={disparity} size="sm" />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* Recent Games */}
        {sortedRecentGames.length > 0 && (
          <section className="site-panel min-w-0 overflow-hidden rounded-[1.5rem] p-6">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <span className="site-data-label">Release view</span>
                <h2 className="mt-2 text-2xl font-bold" style={{ color: "var(--foreground)" }}>
                  Recent Games
                </h2>
              </div>
              <Link
                href="/games"
                className="site-button site-button-secondary"
                style={{ color: "var(--color-rust)" }}
              >
                Browse All
              </Link>
            </div>
            <div className="space-y-3">
              {sortedRecentGames.map((game) => (
                <Link
                  key={game.id}
                  href={buildEntityPath("games", game.title, game.public_id)}
                  className="site-list-item block rounded-2xl border-0 px-0 py-3 first:pt-0 last:pb-0"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 flex-1 items-start gap-3">
                      <GameAvatar
                        title={game.title}
                        imageUrl={game.image_url}
                        size={56}
                        sizes="56px"
                        className="h-14 w-14 shrink-0 rounded-xl object-cover"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="font-medium truncate" style={{ color: "var(--foreground)" }}>
                          {game.title}
                        </p>
                        <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
                          {game.release_date
                            ? new Date(game.release_date).toLocaleDateString("en-US", {
                                month: "short",
                                day: "numeric",
                                year: "numeric",
                              })
                            : "Unknown release date"}
                        </p>
                        <p className="text-xs mt-1" style={{ color: "var(--foreground-muted)" }}>
                          Critics: {game.avg_critic_score != null ? Number(game.avg_critic_score).toFixed(0) : "N/A"} | Users:{" "}
                          {game.steam_user_score != null && game.metacritic_user_score != null
                            ? `Steam ${Number(game.steam_user_score).toFixed(0)} • Metacritic ${Number(game.metacritic_user_score).toFixed(0)}`
                            : game.steam_user_score != null
                              ? `Steam ${Number(game.steam_user_score).toFixed(0)}`
                              : game.metacritic_user_score != null
                                ? `Metacritic ${Number(game.metacritic_user_score).toFixed(0)}`
                                : "N/A"}
                        </p>
                      </div>
                    </div>
                    {(game.disparity_steam != null || game.disparity_metacritic != null) && (
                      <DisparityBadge
                        disparity={getDisplayDisparity(game.disparity_steam, game.disparity_metacritic)}
                        size="sm"
                      />
                    )}
                  </div>
                </Link>
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Latest News */}
      {recentNews && recentNews.items.length > 0 && (
        <section className="site-panel rounded-[1.5rem] p-6">
          <div className="mb-5 flex items-center justify-between gap-3">
            <div>
              <span className="site-data-label">Coverage pulse</span>
              <h2 className="mt-2 text-2xl font-bold" style={{ color: "var(--foreground)" }}>
                Latest News
              </h2>
            </div>
            <Link
              href="/news"
              className="site-button site-button-secondary"
              style={{ color: "var(--color-rust)" }}
            >
              View All News
            </Link>
          </div>
          <div className="space-y-1">
            {recentNews.items.map((article) => (
              <NewsCard key={article.id} article={article} compact />
            ))}
          </div>
        </section>
      )}

      {/* Empty state if no data */}
      {!stats && (
        <div className="site-empty">
          <p style={{ color: "var(--foreground-muted)" }}>
            Unable to load data. Make sure the backend API is running.
          </p>
        </div>
      )}
    </div>
  );
}
