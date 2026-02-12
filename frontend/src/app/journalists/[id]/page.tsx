import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getJournalist, getJournalistReviews } from "@/lib/api";
import { getDisparityColor, getDisparityBgColor, getDisparityBorderColor, formatDisparity } from "@/lib/disparity-colors";
import { DisparityBadge } from "@/components/DisparityBadge";
import { ReviewScoreCards } from "@/components/ReviewScoreTable";
import { LazyChartSection } from "@/components/LazyChartSection";
import { JsonLd } from "@/components/JsonLd";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ page?: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  try {
    const journalist = await getJournalist(parseInt(id));
    const disparity = journalist.stats?.avg_disparity_combined ?? journalist.stats?.overall_disparity_combined;
    const disparityStr = disparity != null ? `${Number(disparity) > 0 ? "+" : ""}${Number(disparity).toFixed(1)}` : null;

    let description = `${journalist.name}'s game review scores and critic-to-user disparity data.`;
    if (disparityStr) {
      description = `${journalist.name} has a ${disparityStr} average review disparity across ${journalist.review_count} reviews. See full scoring patterns and trends.`;
    }

    return {
      title: `${journalist.name} - Review Scores & Disparity`,
      description,
      alternates: { canonical: `/journalists/${id}` },
      openGraph: {
        title: `${journalist.name} - Review Scores & Disparity | ReviewDisparity`,
        description,
        url: `/journalists/${id}`,
        type: "profile",
        ...(journalist.image_url && { images: [{ url: journalist.image_url }] }),
      },
      twitter: { card: "summary", title: journalist.name, description },
    };
  } catch {
    return { title: "Journalist Details" };
  }
}

export default async function JournalistDetailPage({
  params,
  searchParams,
}: PageProps) {
  const { id } = await params;
  const { page: pageParam } = await searchParams;
  const page = parseInt(pageParam || "1");

  let journalist = null;
  let reviews = null;

  try {
    [journalist, reviews] = await Promise.all([
      getJournalist(parseInt(id)),
      getJournalistReviews(parseInt(id), page, 20),
    ]);
  } catch (error) {
    console.error("Error fetching journalist:", error);
    notFound();
  }

  if (!journalist) {
    notFound();
  }

  const jsonLdData: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Person",
    name: journalist.name,
    url: `/journalists/${id}`,
    ...(journalist.image_url && { image: journalist.image_url }),
    ...(journalist.bio && { description: journalist.bio }),
    jobTitle: "Game Journalist",
  };

  return (
    <div className="space-y-8">
      <JsonLd data={jsonLdData} />
      {/* Header */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex flex-col md:flex-row md:items-start gap-6">
          <div className="flex-shrink-0">
            {journalist.image_url ? (
              <img
                src={journalist.image_url}
                alt={journalist.name}
                className="w-24 h-24 rounded-full object-cover"
              />
            ) : (
              <div className="w-24 h-24 rounded-full bg-gray-200 flex items-center justify-center">
                <span className="text-gray-500 text-3xl font-medium">
                  {journalist.name.charAt(0)}
                </span>
              </div>
            )}
          </div>

          <div className="flex-1">
            <h1 className="text-3xl font-bold" style={{ color: "var(--foreground)" }}>
              {journalist.name}
            </h1>
            {journalist.bio && (
              <p className="mt-2 text-gray-600">{journalist.bio}</p>
            )}

            {/* Scoring Stats */}
            <div className="mt-6">
              {/* Use launch window disparity if available, otherwise fall back to overall */}
              {(() => {
                const steamDisparity = journalist.stats?.avg_disparity_steam ?? journalist.stats?.overall_disparity_steam;
                const mcDisparity = journalist.stats?.avg_disparity_metacritic ?? journalist.stats?.overall_disparity_metacritic;
                const combinedDisparity = journalist.stats?.avg_disparity_combined ?? journalist.stats?.overall_disparity_combined;
                const isUsingOverall = journalist.stats?.avg_disparity_combined == null && journalist.stats?.overall_disparity_combined != null;

                return (
                  <>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                      {/* Avg Score Given */}
                      <div
                        className="p-4 rounded-lg text-center"
                        style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
                      >
                        <div className="text-2xl font-bold" style={{ color: "var(--foreground)" }}>
                          {journalist.stats?.avg_score_given != null ? Number(journalist.stats.avg_score_given).toFixed(1) : "N/A"}
                        </div>
                        <div className="text-xs mt-1" style={{ color: "var(--foreground-muted)" }}>
                          Avg Score Given
                        </div>
                      </div>

                      {/* Steam Disparity */}
                      <div
                        className="p-4 rounded-lg text-center"
                        style={{
                          backgroundColor: getDisparityBgColor(steamDisparity),
                          border: `1px solid ${getDisparityBorderColor(steamDisparity)}`
                        }}
                      >
                        <div
                          className="text-2xl font-bold"
                          style={{ color: getDisparityColor(steamDisparity) }}
                        >
                          {formatDisparity(steamDisparity)}
                        </div>
                        <div className="text-xs mt-1" style={{ color: "#708160" }}>
                          Steam Disparity
                        </div>
                      </div>

                      {/* Metacritic Disparity */}
                      <div
                        className="p-4 rounded-lg text-center"
                        style={{
                          backgroundColor: getDisparityBgColor(mcDisparity),
                          border: `1px solid ${getDisparityBorderColor(mcDisparity)}`
                        }}
                      >
                        <div
                          className="text-2xl font-bold"
                          style={{ color: getDisparityColor(mcDisparity) }}
                        >
                          {formatDisparity(mcDisparity)}
                        </div>
                        <div className="text-xs mt-1" style={{ color: "#DD7631" }}>
                          MC Disparity
                        </div>
                      </div>

                      {/* Combined Disparity */}
                      <div
                        className="p-4 rounded-lg text-center"
                        style={{
                          backgroundColor: getDisparityBgColor(combinedDisparity),
                          border: `1px solid ${getDisparityBorderColor(combinedDisparity)}`
                        }}
                      >
                        <div
                          className="text-2xl font-bold"
                          style={{ color: getDisparityColor(combinedDisparity) }}
                        >
                          {formatDisparity(combinedDisparity)}
                        </div>
                        <div className="text-xs mt-1" style={{ color: "#5C574F" }}>
                          Combined Disparity{isUsingOverall && "*"}
                        </div>
                      </div>

                      {/* Review Count */}
                      <div
                        className="p-4 rounded-lg text-center"
                        style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
                      >
                        <div className="text-2xl font-bold" style={{ color: "var(--foreground)" }}>
                          {journalist.review_count}
                        </div>
                        <div className="text-xs mt-1" style={{ color: "var(--foreground-muted)" }}>
                          Reviews
                        </div>
                      </div>
                    </div>

                    {/* Transparency: Early, launch window, and late review breakdown */}
                    {(journalist.stats?.early_review_count != null || journalist.stats?.launch_window_review_count != null || journalist.stats?.late_review_count != null) && (
                      <div className="mt-3 text-xs" style={{ color: "var(--foreground-muted)" }}>
                        {(journalist.stats?.early_review_count ?? 0) > 0 && (
                          <>
                            <span className="inline-flex items-center gap-1">
                              <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                              {journalist.stats?.early_review_count ?? 0} early reviews (before release)
                            </span>
                            <span className="mx-2">|</span>
                          </>
                        )}
                        <span className="inline-flex items-center gap-1">
                          <span className="w-2 h-2 rounded-full bg-green-500"></span>
                          {journalist.stats?.launch_window_review_count ?? 0} launch window reviews (within 60 days of release)
                        </span>
                        <span className="mx-2">|</span>
                        <span className="inline-flex items-center gap-1">
                          <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                          {journalist.stats?.late_review_count ?? 0} late reviews
                        </span>
                        {isUsingOverall && (
                          <span className="ml-2 text-amber-600">
                            *No launch window reviews - showing overall disparity
                          </span>
                        )}
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
          </div>
        </div>

        {/* Scoring Pattern - Transparency metrics */}
        {(journalist.stats?.min_score_given != null || journalist.stats?.max_score_given != null || journalist.stats?.score_std_deviation != null) && (
          <div className="mt-6 pt-6 border-t border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Scoring Pattern
            </h2>
            <div className="grid grid-cols-3 gap-4">
              <div className="p-4 bg-gray-50 rounded-lg text-center">
                <div className="text-2xl font-bold text-gray-900">
                  {journalist.stats?.min_score_given != null ? Number(journalist.stats.min_score_given).toFixed(0) : "N/A"}
                </div>
                <div className="text-xs text-gray-600 mt-1">Lowest Score</div>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg text-center">
                <div className="text-2xl font-bold text-gray-900">
                  {journalist.stats?.max_score_given != null ? Number(journalist.stats.max_score_given).toFixed(0) : "N/A"}
                </div>
                <div className="text-xs text-gray-600 mt-1">Highest Score</div>
              </div>
              <div 
                className="p-4 bg-gray-50 rounded-lg text-center cursor-help"
                title="Score Variance measures how varied this critic's scores are (not vs users). Low variance = gives similar scores to most games. High variance = uses the full scoring range."
              >
                <div className="text-2xl font-bold text-gray-900">
                  {journalist.stats?.score_std_deviation != null ? Number(journalist.stats.score_std_deviation).toFixed(1) : "N/A"}
                </div>
                <div className="text-xs text-gray-600 mt-1">
                  Score Spread
                  <span className="block text-[10px] text-gray-400">(variance in their own scores)</span>
                </div>
              </div>
            </div>
            {journalist.stats?.score_std_deviation != null && Number(journalist.stats.score_std_deviation) < 10 && (
              <p className="mt-3 text-xs text-amber-600">
                Low score spread detected. This reviewer may use a narrow scoring range or binary scoring system.
              </p>
            )}
          </div>
        )}

        {/* Outlet Breakdown */}
        {journalist.outlet_breakdown &&
          journalist.outlet_breakdown.length > 0 && (
            <div className="mt-6 pt-6 border-t border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                Disparity by Outlet
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {journalist.outlet_breakdown.map((outlet) => (
                  <Link
                    key={outlet.outlet_id}
                    href={`/outlets/${outlet.outlet_id}`}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                  >
                    <div>
                      <p className="font-medium text-gray-900">
                        {outlet.outlet_name}
                      </p>
                      <p className="text-sm text-gray-500">
                        {outlet.review_count} reviews
                      </p>
                    </div>
                    <DisparityBadge disparity={outlet.avg_disparity} />
                  </Link>
                ))}
              </div>
            </div>
          )}
      </div>

      {/* Disparity Trend Chart - lazy loaded on scroll */}
      <LazyChartSection entityType="journalist" entityId={parseInt(id)} />

      {/* Reviews */}
      {reviews && reviews.items.length > 0 && (
        <section className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">Reviews</h2>
          <div className="space-y-4">
            {reviews.items.map((review) => (
              <div
                key={review.id}
                className="p-4 border rounded-lg"
                style={{ borderColor: "var(--border)" }}
              >
                {/* Header: Game title, outlet, date */}
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link
                        href={`/games/${review.game_id}`}
                        className="font-medium hover:opacity-80"
                        style={{ color: "var(--foreground)" }}
                      >
                        {review.game_title}
                      </Link>
                      {review.outlet_name && (
                        <>
                          <span style={{ color: "var(--foreground-muted)" }}>via</span>
                          <Link
                            href={`/outlets/${review.outlet_id}`}
                            className="hover:opacity-80"
                            style={{ color: "var(--foreground-muted)" }}
                          >
                            {review.outlet_name}
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
                  </div>
                  {review.review_url && (
                    <a
                      href={review.review_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm px-3 py-1 rounded hover:opacity-80"
                      style={{ backgroundColor: "var(--color-rust)", color: "white" }}
                    >
                      Read Review
                    </a>
                  )}
                </div>

                {/* Snippet */}
                {review.snippet && (
                  <p className="mb-3 text-sm italic" style={{ color: "var(--foreground-muted)" }}>
                    &ldquo;{review.snippet}&rdquo;
                  </p>
                )}

                {/* Score breakdown */}
                <ReviewScoreCards
                  criticScore={review.score_normalized}
                  steamScore={review.steam_user_score}
                  steamDisparity={review.disparity_steam}
                  metacriticScore={review.metacritic_user_score}
                  metacriticDisparity={review.disparity_metacritic}
                  combinedDisparity={
                    review.disparity_steam != null && review.disparity_metacritic != null
                      ? (Number(review.disparity_steam) + Number(review.disparity_metacritic)) / 2
                      : review.disparity_steam ?? review.disparity_metacritic
                  }
                />
              </div>
            ))}
          </div>

          {/* Pagination */}
          {reviews.total_pages > 1 && (
            <div className="mt-6 flex justify-center gap-2">
              {page > 1 && (
                <Link
                  href={`/journalists/${id}?page=${page - 1}`}
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
                  href={`/journalists/${id}?page=${page + 1}`}
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
