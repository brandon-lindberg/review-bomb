import Link from "next/link";
import { notFound } from "next/navigation";
import { getOutlet, getOutletReviews, getOutletHistory } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { DisparityChart } from "@/components/DisparityChart";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ page?: string }>;
}

export default async function OutletDetailPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const { page: pageParam } = await searchParams;
  const page = parseInt(pageParam || "1");

  let outlet = null;
  let reviews = null;
  let history = null;

  try {
    [outlet, reviews, history] = await Promise.all([
      getOutlet(parseInt(id)),
      getOutletReviews(parseInt(id), page, 20),
      getOutletHistory(parseInt(id)).catch(() => []),
    ]);
  } catch (error) {
    console.error("Error fetching outlet:", error);
    notFound();
  }

  if (!outlet) {
    notFound();
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex flex-col md:flex-row md:items-start gap-6">
          <div className="flex-shrink-0">
            {outlet.logo_url ? (
              <img
                src={outlet.logo_url}
                alt={outlet.name}
                className="w-24 h-24 rounded object-contain bg-gray-100"
              />
            ) : (
              <div className="w-24 h-24 rounded bg-gray-200 flex items-center justify-center">
                <span className="text-gray-500 text-3xl font-medium">
                  {outlet.name.charAt(0)}
                </span>
              </div>
            )}
          </div>

          <div className="flex-1">
            <div className="flex items-center gap-4">
              <h1 className="text-3xl font-bold" style={{ color: "var(--foreground)" }}>
                {outlet.name}
              </h1>
              {outlet.website_url && (
                <a
                  href={outlet.website_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:text-blue-800 text-sm"
                >
                  Visit Website
                </a>
              )}
            </div>

            {/* Stats Grid */}
            <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard
                label="Overall Disparity"
                value={
                  outlet.avg_disparity !== null ? (
                    <DisparityBadge disparity={outlet.avg_disparity} size="lg" />
                  ) : (
                    "N/A"
                  )
                }
              />
              <StatCard
                label="Total Reviews"
                value={outlet.review_count?.toString() ?? "0"}
              />
              <StatCard
                label="Journalists"
                value={outlet.journalist_count?.toString() ?? "0"}
              />
              <StatCard
                label="Average Score"
                value={outlet.avg_score != null ? Number(outlet.avg_score).toFixed(1) : "N/A"}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Journalists at this outlet */}
      {outlet.journalists && outlet.journalists.length > 0 && (
        <section className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Journalists
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {outlet.journalists.map((journalist) => (
              <Link
                key={journalist.id}
                href={`/journalists/${journalist.id}`}
                className="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  {journalist.image_url ? (
                    <img
                      src={journalist.image_url}
                      alt={journalist.name}
                      className="w-10 h-10 rounded-full object-cover"
                    />
                  ) : (
                    <div className="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center">
                      <span className="text-gray-500 font-medium">
                        {journalist.name.charAt(0)}
                      </span>
                    </div>
                  )}
                  <div>
                    <p className="font-medium text-gray-900">
                      {journalist.name}
                    </p>
                    <p className="text-sm text-gray-500">
                      {journalist.review_count} reviews
                    </p>
                  </div>
                </div>
                <DisparityBadge disparity={journalist.avg_disparity} />
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Disparity Trend Chart */}
      {history && history.length > 0 && (
        <section className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Disparity Over Time
          </h2>
          <DisparityChart data={history} height={300} />
          <p className="mt-4 text-sm text-gray-500 text-center">
            Positive values indicate critic scores higher than user scores.
            Negative values indicate critic scores lower than user scores.
          </p>
        </section>
      )}

      {/* Reviews */}
      {reviews && reviews.items.length > 0 && (
        <section className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Recent Reviews
          </h2>
          <div className="space-y-4">
            {reviews.items.map((review) => (
              <div
                key={review.id}
                className="p-4 border border-gray-200 rounded-lg"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link
                        href={`/games/${review.game_id}`}
                        className="font-medium text-gray-900 hover:text-blue-600"
                      >
                        {review.journalist_name ? `Review by ${review.journalist_name}` : "Review"}
                      </Link>
                      {review.journalist_id && (
                        <>
                          <span className="text-gray-400">by</span>
                          <Link
                            href={`/journalists/${review.journalist_id}`}
                            className="text-gray-600 hover:text-blue-600"
                          >
                            {review.journalist_name}
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
                  href={`/outlets/${id}?page=${page - 1}`}
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
                  href={`/outlets/${id}?page=${page + 1}`}
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

function StatCard({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="p-4 bg-gray-50 rounded-lg text-center">
      <div className="text-2xl font-bold text-gray-900 flex justify-center">
        {value}
      </div>
      <p className="text-sm text-gray-600 mt-1">{label}</p>
    </div>
  );
}
