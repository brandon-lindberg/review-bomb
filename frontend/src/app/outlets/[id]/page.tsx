import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getOutlet, getOutletReviews, getOutletAllReviews } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { DisparityScoreCards } from "@/components/DisparityScores";
import { getDisparityColor, formatDisparity } from "@/lib/disparity-colors";
import { ReviewDisparityChart } from "@/components/ReviewDisparityChart";
import { JsonLd } from "@/components/JsonLd";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ page?: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  try {
    const outlet = await getOutlet(parseInt(id));
    const disparity = outlet.avg_disparity_combined ?? outlet.avg_disparity;
    const disparityStr = disparity != null ? `${Number(disparity) > 0 ? "+" : ""}${Number(disparity).toFixed(1)}` : null;

    let description = `${outlet.name} game review scores and critic-to-user disparity data.`;
    if (disparityStr) {
      description = `${outlet.name} has a ${disparityStr} average review disparity across ${outlet.review_count || 0} reviews from ${outlet.journalist_count || 0} journalists.`;
    }

    return {
      title: `${outlet.name} - Review Scores & Disparity`,
      description,
      alternates: { canonical: `/outlets/${id}` },
      openGraph: {
        title: `${outlet.name} - Review Scores & Disparity | ReviewDisparity`,
        description,
        url: `/outlets/${id}`,
        type: "website",
        ...(outlet.logo_url && { images: [{ url: outlet.logo_url }] }),
      },
      twitter: { card: "summary", title: outlet.name, description },
    };
  } catch {
    return { title: "Outlet Details" };
  }
}

export default async function OutletDetailPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const { page: pageParam } = await searchParams;
  const page = parseInt(pageParam || "1");

  let outlet = null;
  let reviews = null;
  let allReviews = null;

  try {
    [outlet, reviews, allReviews] = await Promise.all([
      getOutlet(parseInt(id)),
      getOutletReviews(parseInt(id), page, 20),
      getOutletAllReviews(parseInt(id)).catch(() => []),
    ]);
  } catch (error) {
    console.error("Error fetching outlet:", error);
    notFound();
  }

  if (!outlet) {
    notFound();
  }

  const jsonLdData: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: outlet.name,
    url: `/outlets/${id}`,
    ...(outlet.logo_url && { logo: outlet.logo_url }),
    ...(outlet.website_url && { sameAs: [outlet.website_url] }),
  };

  return (
    <div className="space-y-8">
      <JsonLd data={jsonLdData} />
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
            <div className="mt-6 grid grid-cols-3 gap-4">
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

        {/* Disparity Breakdown */}
        <div className="mt-6 pt-6 border-t border-gray-200">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--foreground)" }}>
            Disparity Breakdown
          </h2>
          <DisparityScoreCards
            steamDisparity={outlet.avg_disparity_steam}
            metacriticDisparity={outlet.avg_disparity_metacritic}
            combinedDisparity={outlet.avg_disparity_combined ?? outlet.avg_disparity}
          />
        </div>

        {/* Scoring Pattern - Transparency metrics */}
        {(outlet.min_score_given != null || outlet.max_score_given != null || outlet.score_std_deviation != null) && (
          <div className="mt-6 pt-6 border-t border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Scoring Pattern
            </h2>
            <div className="grid grid-cols-3 gap-4">
              <div className="p-4 bg-gray-50 rounded-lg text-center">
                <div className="text-2xl font-bold text-gray-900">
                  {outlet.min_score_given != null ? Number(outlet.min_score_given).toFixed(0) : "N/A"}
                </div>
                <div className="text-xs text-gray-600 mt-1">Lowest Score</div>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg text-center">
                <div className="text-2xl font-bold text-gray-900">
                  {outlet.max_score_given != null ? Number(outlet.max_score_given).toFixed(0) : "N/A"}
                </div>
                <div className="text-xs text-gray-600 mt-1">Highest Score</div>
              </div>
              <div 
                className="p-4 bg-gray-50 rounded-lg text-center cursor-help"
                title="Score Spread measures how varied this outlet's scores are (not vs users). Low spread = gives similar scores to most games. High spread = uses the full scoring range."
              >
                <div className="text-2xl font-bold text-gray-900">
                  {outlet.score_std_deviation != null ? Number(outlet.score_std_deviation).toFixed(1) : "N/A"}
                </div>
                <div className="text-xs text-gray-600 mt-1">
                  Score Spread
                  <span className="block text-[10px] text-gray-400">(variance in their own scores)</span>
                </div>
              </div>
            </div>
            {outlet.score_std_deviation != null && Number(outlet.score_std_deviation) < 10 && (
              <p className="mt-3 text-xs text-amber-600">
                Low score spread detected. This outlet may use a narrow scoring range or binary scoring system.
              </p>
            )}
          </div>
        )}
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
      {allReviews && allReviews.length > 0 && (
        <section className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Disparity Over Time
          </h2>
          <ReviewDisparityChart reviews={allReviews} context="outlet" height={300} />
          <p className="mt-4 text-sm text-gray-500 text-center">
            Each point represents a review. Hover for details.
            Positive = critic higher than users. Negative = critic lower.
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
                className="p-4 border rounded-lg"
                style={{ borderColor: "var(--border)" }}
              >
                <div className="flex items-start justify-between gap-4">
                  {/* Left side: Review info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link
                        href={`/games/${review.game_id}`}
                        className="font-medium hover:opacity-80"
                        style={{ color: "var(--foreground)" }}
                      >
                        {review.game_title || "Unknown Game"}
                      </Link>
                      {review.journalist_id && review.journalist_name && (
                        <>
                          <span style={{ color: "var(--foreground-muted)" }}>by</span>
                          <Link
                            href={`/journalists/${review.journalist_id}`}
                            className="hover:opacity-80"
                            style={{ color: "var(--foreground-muted)" }}
                          >
                            {review.journalist_name}
                          </Link>
                        </>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      {review.published_at && (
                        <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
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
                    {/* Snippet */}
                    {review.snippet && (
                      <p className="mt-2 text-sm italic" style={{ color: "var(--foreground-muted)" }}>
                        &ldquo;{review.snippet}&rdquo;
                      </p>
                    )}
                  </div>

                  {/* Right side: Scores and Read button */}
                  <div className="flex items-center gap-4 flex-shrink-0">
                    {/* Compact score display */}
                    <div className="flex items-center gap-2">
                      {/* Critic Score */}
                      <div className="text-center px-3 py-2 rounded" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
                        <div className="text-xs" style={{ color: "var(--foreground-muted)" }}>Critic</div>
                        <div className="text-lg font-bold" style={{ color: "var(--foreground)" }}>
                          {review.score_normalized != null ? Number(review.score_normalized).toFixed(0) : "—"}
                        </div>
                      </div>
                      {/* Steam Disparity */}
                      <div className="text-center px-3 py-2 rounded" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
                        <div className="text-xs" style={{ color: "#708160" }}>Steam</div>
                        <div className="text-lg font-bold" style={{ color: getDisparityColor(review.disparity_steam != null ? Number(review.disparity_steam) : null) }}>
                          {review.disparity_steam != null
                            ? formatDisparity(Number(review.disparity_steam))
                            : "N/A"}
                        </div>
                      </div>
                      {/* Metacritic Disparity */}
                      <div className="text-center px-3 py-2 rounded" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
                        <div className="text-xs" style={{ color: "#DD7631" }}>MC</div>
                        <div className="text-lg font-bold" style={{ color: getDisparityColor(review.disparity_metacritic != null ? Number(review.disparity_metacritic) : null) }}>
                          {review.disparity_metacritic != null
                            ? formatDisparity(Number(review.disparity_metacritic))
                            : "N/A"}
                        </div>
                      </div>
                    </div>
                    {review.review_url && (
                      <a
                        href={review.review_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm px-3 py-2 rounded hover:opacity-80"
                        style={{ backgroundColor: "var(--color-rust)", color: "white" }}
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
