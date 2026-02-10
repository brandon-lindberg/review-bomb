import Link from "next/link";
import { notFound } from "next/navigation";
import { getGame, getGameReviews, getGameAllReviews } from "@/lib/api";
import { DisparityScoreCards } from "@/components/DisparityScores";
import { ScoreDisplay } from "@/components/ScoreDisplay";
import { ReviewDisparityChart } from "@/components/ReviewDisparityChart";
import { GameDetailTabs } from "@/components/GameDetailTabs";
import type { ReviewWithJournalist } from "@/types";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ page?: string }>;
}

export default async function GameDetailPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const { page: pageParam } = await searchParams;
  const page = parseInt(pageParam || "1");

  let game = null;
  let reviews = null;
  let allReviews = null;

  try {
    [game, reviews, allReviews] = await Promise.all([
      getGame(parseInt(id)),
      getGameReviews(parseInt(id), page, 20),
      getGameAllReviews(parseInt(id)).catch(() => []),
    ]);
  } catch (error) {
    console.error("Error fetching game:", error);
    notFound();
  }

  if (!game) {
    notFound();
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6">
          <div className="flex-1">
            <h1 className="text-3xl font-bold" style={{ color: "var(--foreground)" }}>{game.title}</h1>
            {game.release_date && (
              <p className="mt-2 text-sm text-gray-500">
                Released: {new Date(game.release_date).toLocaleDateString()}
              </p>
            )}
            {game.description && (
              <p className="mt-4 text-gray-600">{game.description}</p>
            )}
          </div>

          <ScoreDisplay
            criticScore={game.avg_critic_score}
            userScore={game.steam_user_score || game.metacritic_user_score}
            size="lg"
          />
        </div>

        {/* Score Breakdown */}
        <div className="mt-6 pt-6 border-t border-gray-200">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--foreground)" }}>
            Score Breakdown
          </h2>
          <div className="grid grid-cols-3 gap-4">
            <ScoreCard
              label="Critic Average"
              value={game.avg_critic_score != null ? Number(game.avg_critic_score).toFixed(1) : undefined}
              subtitle={`${game.critic_review_count || 0} reviews`}
            />
            <ScoreCard
              label="Steam User Score"
              value={game.steam_user_score != null ? Number(game.steam_user_score).toFixed(0) : undefined}
              subtitle={
                game.steam_sample_size
                  ? `${game.steam_sample_size.toLocaleString()} reviews`
                  : undefined
              }
            />
            <ScoreCard
              label="Metacritic User Score"
              value={game.metacritic_user_score != null ? Number(game.metacritic_user_score).toFixed(0) : undefined}
              subtitle={
                game.metacritic_sample_size
                  ? `${game.metacritic_sample_size.toLocaleString()} reviews`
                  : undefined
              }
            />
          </div>
        </div>

        {/* Disparity Breakdown */}
        <div className="mt-6 pt-6 border-t border-gray-200">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--foreground)" }}>
            Disparity Breakdown
          </h2>
          <DisparityScoreCards
            steamDisparity={game.disparity_steam}
            metacriticDisparity={game.disparity_metacritic}
            combinedDisparity={game.disparity_steam != null && game.disparity_metacritic != null
              ? (Number(game.disparity_steam) + Number(game.disparity_metacritic)) / 2
              : game.disparity_steam ?? game.disparity_metacritic}
            steamUserScore={game.steam_user_score}
            metacriticUserScore={game.metacritic_user_score}
            criticScore={game.avg_critic_score}
          />
        </div>
      </div>

      {/* Disparity Chart */}
      {allReviews && allReviews.length > 0 && (
        <section className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Review Disparities
          </h2>
          <ReviewDisparityChart
            reviews={allReviews}
            context="game"
            gameTitle={game.title}
            height={300}
          />
          <p className="mt-4 text-sm text-gray-500 text-center">
            Each point represents a critic review. Hover for details.
            Positive = critic higher than users. Negative = critic lower.
          </p>
        </section>
      )}

      {/* Tabbed Section: Critic Reviews + Journalist Alignment */}
      {reviews && reviews.items.length > 0 && (
        <GameDetailTabs
          criticReviews={
            <>
              <div className="space-y-4">
                {reviews.items.map((review) => (
                  <div
                    key={review.id}
                    className="p-4 border border-gray-200 rounded-lg"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <Link
                            href={`/journalists/${review.journalist_id}`}
                            className="font-medium text-gray-900 hover:text-blue-600"
                          >
                            {review.journalist_name}
                          </Link>
                          {review.outlet_name && (
                            <>
                              <span className="text-gray-400">at</span>
                              <Link
                                href={`/outlets/${review.outlet_id}`}
                                className="text-gray-600 hover:text-blue-600"
                              >
                                {review.outlet_name}
                              </Link>
                            </>
                          )}
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          {review.published_at && (
                            <p className="text-sm text-gray-500">
                              {new Date(review.published_at).toLocaleDateString()}
                            </p>
                          )}
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium cursor-help ${
                              review.review_timing === "early"
                                ? "bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300"
                                : review.review_timing === "launch_window"
                                ? "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300"
                                : "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
                            }`}
                            title={review.game_release_date
                              ? `Game released: ${new Date(review.game_release_date).toLocaleDateString()}${
                                  review.review_timing === "early" ? " (before release)" :
                                  review.review_timing === "launch_window" ? " (within 60 days)" : " (more than 60 days ago)"
                                }`
                              : "Release date unknown"}
                          >
                            {review.review_timing === "early" ? "Early Review" :
                             review.review_timing === "launch_window" ? "Launch Window" : "Late Review"}
                          </span>
                        </div>
                        {review.snippet && (
                          <p className="mt-2 text-gray-600 text-sm italic">
                            &ldquo;{review.snippet}&rdquo;
                          </p>
                        )}
                      </div>

                      <div className="flex items-center gap-4 ml-4">
                        <div className="text-right">
                          <p className="text-2xl font-bold text-gray-900">
                            {review.score_normalized != null
                              ? Number(review.score_normalized).toFixed(0)
                              : "—"}
                          </p>
                          {review.score_raw && review.score_scale && (
                            <p className="text-xs text-gray-500">
                              {review.score_raw}/{review.score_scale}
                            </p>
                          )}
                        </div>
                        {review.review_url && (
                          <a
                            href={review.review_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:text-blue-800"
                          >
                            Read
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Pagination */}
              {reviews.total_pages > 1 && (
                <div className="mt-6 flex justify-center gap-2">
                  {page > 1 && (
                    <Link
                      href={`/games/${id}?page=${page - 1}`}
                      className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                    >
                      Previous
                    </Link>
                  )}
                  <span className="px-4 py-2 text-gray-600">
                    Page {page} of {reviews.total_pages}
                  </span>
                  {page < reviews.total_pages && (
                    <Link
                      href={`/games/${id}?page=${page + 1}`}
                      className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                    >
                      Next
                    </Link>
                  )}
                </div>
              )}
            </>
          }
          journalistAlignment={(() => {
            if (!allReviews || allReviews.length === 0) return null;

            // Build journalist alignment data from all reviews
            const journalistMap = new Map<number, {
              id: number;
              name: string;
              imageUrl: string | null;
              outletName: string | null;
              score: number;
              combinedDisparity: number | null;
            }>();

            for (const review of allReviews as ReviewWithJournalist[]) {
              if (review.score_normalized == null) continue;
              if (journalistMap.has(review.journalist_id)) continue;

              const steam = review.disparity_steam != null ? Number(review.disparity_steam) : null;
              const mc = review.disparity_metacritic != null ? Number(review.disparity_metacritic) : null;
              let combined: number | null = null;
              if (steam != null && mc != null) {
                combined = (steam + mc) / 2;
              } else {
                combined = steam ?? mc ?? null;
              }

              journalistMap.set(review.journalist_id, {
                id: review.journalist_id,
                name: review.journalist_name,
                imageUrl: review.journalist_image_url,
                outletName: review.outlet_name,
                score: Number(review.score_normalized),
                combinedDisparity: combined,
              });
            }

            const journalists = Array.from(journalistMap.values())
              .filter(j => j.combinedDisparity !== null);

            if (journalists.length < 2) return null;

            // FIX: Only show journalists with actual positive/negative disparity in each column
            const topGenerous = journalists
              .filter(j => (j.combinedDisparity ?? 0) > 0)
              .sort((a, b) => (b.combinedDisparity ?? 0) - (a.combinedDisparity ?? 0))
              .slice(0, 5);

            const topCritical = journalists
              .filter(j => (j.combinedDisparity ?? 0) < 0)
              .sort((a, b) => (a.combinedDisparity ?? 0) - (b.combinedDisparity ?? 0))
              .slice(0, 5);

            if (topGenerous.length === 0 && topCritical.length === 0) return null;

            const renderJournalist = (j: typeof journalists[0], i: number) => (
              <Link
                key={j.id}
                href={`/journalists/${j.id}`}
                className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-sm text-gray-400 w-5 text-right flex-shrink-0">{i + 1}</span>
                  {j.imageUrl ? (
                    <img src={j.imageUrl} alt={j.name} className="w-7 h-7 rounded-full object-cover flex-shrink-0" />
                  ) : (
                    <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
                      <span className="text-gray-500 text-xs">{j.name.charAt(0)}</span>
                    </div>
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{j.name}</p>
                    {j.outletName && (
                      <p className="text-xs text-gray-500 truncate">{j.outletName}</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0 ml-2">
                  <span className="text-sm text-gray-500">
                    Score: {j.score.toFixed(0)}
                  </span>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                    (j.combinedDisparity ?? 0) > 0 ? "bg-red-100 text-red-800" : "bg-blue-100 text-blue-800"
                  }`}>
                    {(j.combinedDisparity ?? 0) > 0 ? "+" : ""}{(j.combinedDisparity ?? 0).toFixed(1)}
                  </span>
                </div>
              </Link>
            );

            return (
              <div>
                <p className="text-sm text-gray-500 mb-4">
                  How individual critics scored this game compared to user consensus
                </p>

                <div className="grid md:grid-cols-2 gap-6">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
                      Scored Higher Than Users
                    </h3>
                    <div className="space-y-2">
                      {topGenerous.length > 0 ? (
                        topGenerous.map(renderJournalist)
                      ) : (
                        <p className="text-sm text-gray-400 py-3">No critics scored higher than users</p>
                      )}
                    </div>
                  </div>

                  <div>
                    <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
                      Scored Lower Than Users
                    </h3>
                    <div className="space-y-2">
                      {topCritical.length > 0 ? (
                        topCritical.map(renderJournalist)
                      ) : (
                        <p className="text-sm text-gray-400 py-3">No critics scored lower than users</p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })()}
        />
      )}
    </div>
  );
}

function ScoreCard({
  label,
  value,
  subtitle,
}: {
  label: string;
  value?: string;
  subtitle?: string;
}) {
  return (
    <div className="p-4 bg-gray-50 rounded-lg text-center">
      <p className="text-2xl font-bold text-gray-900">{value ?? "N/A"}</p>
      <p className="text-sm font-medium text-gray-700">{label}</p>
      {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}
    </div>
  );
}
