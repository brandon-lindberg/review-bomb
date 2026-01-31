import Link from "next/link";
import { notFound } from "next/navigation";
import { getGame, getGameReviews } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { ScoreDisplay } from "@/components/ScoreDisplay";

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

  try {
    [game, reviews] = await Promise.all([
      getGame(parseInt(id)),
      getGameReviews(parseInt(id), page, 20),
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

          <div className="flex items-center gap-6">
            <ScoreDisplay
              criticScore={game.critic_avg}
              userScore={game.user_avg}
              size="lg"
            />
            <DisparityBadge disparity={game.disparity} size="lg" />
          </div>
        </div>

        {/* Score Breakdown */}
        <div className="mt-6 pt-6 border-t border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Score Breakdown
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <ScoreCard
              label="Critic Average"
              value={game.critic_avg != null ? Number(game.critic_avg).toFixed(1) : undefined}
              subtitle={`${game.review_count || 0} reviews`}
            />
            <ScoreCard
              label="Top Critic Score"
              value={game.top_critic_score != null ? Number(game.top_critic_score).toFixed(1) : undefined}
              subtitle="OpenCritic"
            />
            <ScoreCard
              label="Steam User Score"
              value={game.steam_score != null ? Number(game.steam_score).toFixed(0) : undefined}
              subtitle={
                game.steam_sample_size
                  ? `${game.steam_sample_size.toLocaleString()} reviews`
                  : undefined
              }
            />
            <ScoreCard
              label="Metacritic User Score"
              value={game.metacritic_score != null ? Number(game.metacritic_score).toFixed(0) : undefined}
              subtitle={
                game.metacritic_sample_size
                  ? `${game.metacritic_sample_size.toLocaleString()} reviews`
                  : undefined
              }
            />
          </div>
        </div>
      </div>

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
                    {review.published_at && (
                      <p className="text-sm text-gray-500 mt-1">
                        {new Date(review.published_at).toLocaleDateString()}
                      </p>
                    )}
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
