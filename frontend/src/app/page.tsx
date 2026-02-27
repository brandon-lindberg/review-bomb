import Link from "next/link";
import { getStats, getRecentReviews, getGames, getNews } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { JsonLd } from "@/components/JsonLd";
import { NewsCard } from "@/components/NewsCard";
import { getDisplayDisparity } from "@/lib/disparity-colors";
import { getSiteUrl } from "@/lib/site-url";

// Keep the home page shell revalidating frequently so section freshness is driven
// by the underlying API/fetch caches (typically ~60s), not an extra 60s page cache.
export const revalidate = 1;

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

  try {
    [stats, recentReviews, recentGames, recentNews] = await Promise.all([
      getStats(),
      getRecentReviews(5),
      getGames(1, 5, "release_date", "desc"),
      getNews(1, 5).catch(() => null),
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

  return (
    <div className="space-y-12">
      <JsonLd data={websiteJsonLd} />
      {/* Hero Section */}
      <section className="text-center py-12">
        <h1 className="text-4xl font-bold mb-4" style={{ color: "var(--foreground)" }}>
          Review<span style={{ color: "var(--color-rust)" }}>Disparity</span> Tracker
        </h1>
        <p className="text-xl max-w-2xl mx-auto" style={{ color: "var(--foreground-muted)" }}>
          Track the gap between game journalist scores and player opinions.
          See which critics align with audiences and which diverge.
        </p>
      </section>

      {/* Stats Grid */}
      {stats && (
        <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Journalists" value={stats.total_journalists} />
          <StatCard label="Outlets" value={stats.total_outlets} />
          <StatCard label="Games" value={stats.total_games} />
          <StatCard label="Reviews" value={stats.total_reviews} />
        </section>
      )}

      {/* Recent Content */}
      <div className="grid md:grid-cols-2 gap-8">
        {/* Recent Reviews */}
        {sortedRecentReviews.length > 0 && (
          <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 min-w-0 overflow-hidden">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>
                Recent Reviews
              </h2>
              <Link
                href="/journalists"
                className="text-sm hover:underline"
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
                    className="p-3 rounded hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 min-w-0">
                          <Link
                            href={`/games/${review.game_id}`}
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
                            href={`/journalists/${review.journalist_id}`}
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
          <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 min-w-0 overflow-hidden">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>
                Recent Games
              </h2>
              <Link
                href="/games"
                className="text-sm hover:underline"
                style={{ color: "var(--color-rust)" }}
              >
                Browse All
              </Link>
            </div>
            <div className="space-y-3">
              {sortedRecentGames.map((game) => (
                <Link
                  key={game.id}
                  href={`/games/${game.id}`}
                  className="flex items-center justify-between p-3 rounded hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                >
                  <div className="flex-1 min-w-0">
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
                  {(game.disparity_steam != null || game.disparity_metacritic != null) && (
                    <DisparityBadge
                      disparity={getDisplayDisparity(game.disparity_steam, game.disparity_metacritic)}
                      size="sm"
                    />
                  )}
                </Link>
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Latest News */}
      {recentNews && recentNews.items.length > 0 && (
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>
              Latest News
            </h2>
            <Link
              href="/news"
              className="text-sm hover:underline"
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

      {/* Call to Action */}
      <section className="text-center py-8">
        <div className="flex flex-wrap justify-center gap-4">
          <Link
            href="/journalists"
            className="px-6 py-3 text-white rounded-lg font-medium hover:opacity-90 transition-opacity"
            style={{ backgroundColor: "var(--color-rust)" }}
          >
            Browse Journalists
          </Link>
          <Link
            href="/games"
            className="px-6 py-3 rounded-lg font-medium hover:opacity-80 transition-opacity"
            style={{ backgroundColor: "var(--color-tan)", color: "#1a1a1a" }}
          >
            Browse Games
          </Link>
          <Link
            href="/leaderboards"
            className="px-6 py-3 rounded-lg font-medium hover:opacity-80 transition-opacity"
            style={{ backgroundColor: "var(--color-sage)", color: "white" }}
          >
            View Leaderboards
          </Link>
        </div>
      </section>

      {/* Empty state if no data */}
      {!stats && (
        <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-lg shadow">
          <p style={{ color: "var(--foreground-muted)" }}>
            Unable to load data. Make sure the backend API is running.
          </p>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 text-center" style={{ borderTop: "3px solid var(--color-rust)" }}>
      <p className="text-3xl font-bold" style={{ color: "var(--foreground)" }}>
        {value != null ? value.toLocaleString() : "—"}
      </p>
      <p style={{ color: "var(--foreground-muted)" }}>{label}</p>
    </div>
  );
}
