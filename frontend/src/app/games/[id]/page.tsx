import Link from "next/link";
import { notFound } from "next/navigation";
import { getGame, getGameReviews, getGameAllReviews } from "@/lib/api";
import { DisparityScoreCards } from "@/components/DisparityScores";
import { ScoreDisplay } from "@/components/ScoreDisplay";
import { ReviewDisparityChart } from "@/components/ReviewDisparityChart";

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
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-gray-500">
              {game.release_date && (
                <span>
                  Released: {new Date(game.release_date).toLocaleDateString()}
                </span>
              )}
              {game.tier && (
                <span className="px-2 py-0.5 bg-gray-100 rounded">
                  {game.tier}
                </span>
              )}
            </div>
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
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <ScoreCard
              label="Critic Average"
              value={game.avg_critic_score != null ? Number(game.avg_critic_score).toFixed(1) : undefined}
              subtitle={`${game.critic_review_count || 0} reviews`}
            />
            <ScoreCard
              label="Top Critic Score"
              value={game.opencritic_score != null ? Number(game.opencritic_score).toFixed(1) : undefined}
              subtitle="OpenCritic"
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

      {/* Reviews */}
      {reviews && reviews.items.length > 0 && (
        <section className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Critic Reviews
          </h2>
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
        </section>
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
