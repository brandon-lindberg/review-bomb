import Link from "next/link";
import { getStats, getRecentReviews, getGames, getNews } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { JsonLd } from "@/components/JsonLd";
import { NewsCard } from "@/components/NewsCard";

export const dynamic = "force-dynamic";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://reviewdisparity.com";

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
      getNews(1, 4).catch(() => null),
    ]);
  } catch (error) {
    console.error("Error fetching data:", error);
  }

  const websiteJsonLd = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "ReviewDisparity",
    url: siteUrl,
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
        {recentReviews && recentReviews.length > 0 && (
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
              {recentReviews.map((review) => {
                const disparity = review.disparity_steam ?? review.disparity_metacritic ?? null;
                return (
                  <div
                    key={review.id}
                    className="p-3 rounded hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <Link
                          href={`/games/${review.game_id}`}
                          className="font-medium hover:underline block truncate"
                          style={{ color: "var(--foreground)" }}
                          title={review.game_title ?? undefined}
                        >
                          {review.game_title}
                        </Link>
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
        {recentGames && recentGames.items.length > 0 && (
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
              {recentGames.items.map((game) => (
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
                      {game.steam_user_score != null
                        ? Number(game.steam_user_score).toFixed(0)
                        : game.metacritic_user_score != null
                          ? Number(game.metacritic_user_score).toFixed(0)
                          : "N/A"}
                    </p>
                  </div>
                  {(game.disparity_steam != null || game.disparity_metacritic != null) && (
                    <DisparityBadge
                      disparity={game.disparity_steam ?? game.disparity_metacritic ?? 0}
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
