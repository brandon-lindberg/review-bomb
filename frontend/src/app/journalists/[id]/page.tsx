import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { getJournalist } from "@/lib/api";
import { getDisparityColor, getDisparityBgColor, getDisparityBorderColor, formatDisparity } from "@/lib/disparity-colors";
import { DisparityBadge } from "@/components/DisparityBadge";
import { LazyChartSection } from "@/components/LazyChartSection";
import { JournalistReviewsSection } from "@/components/JournalistReviewsSection";
import { JsonLd } from "@/components/JsonLd";
import { ShareButtons } from "@/components/ShareButtons";
import { getSiteUrl } from "@/lib/site-url";

export const revalidate = 60;

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ page?: string }>;
}

export async function generateMetadata({ params, searchParams }: PageProps): Promise<Metadata> {
  const { id } = await params;
  const { page: pageParam } = await searchParams;
  const page = parseInt(pageParam || "1");
  const siteUrl = getSiteUrl();

  try {
    const journalist = await getJournalist(id);
    const canonicalId = journalist.public_id;
    const disparity = journalist.stats?.overall_disparity_combined ?? journalist.avg_disparity ?? journalist.stats?.avg_disparity_combined;
    const disparityStr = disparity != null ? `${Number(disparity) > 0 ? "+" : ""}${Number(disparity).toFixed(1)}` : null;

    let description = `${journalist.name}'s game review scores and critic-to-user disparity data.`;
    if (disparityStr) {
      description = `${journalist.name} has a ${disparityStr} average review disparity across ${journalist.review_count} reviews. See full scoring patterns and trends.`;
    }

    return {
      title: `${journalist.name} - Review Scores & Disparity`,
      description,
      alternates: { canonical: `/journalists/${canonicalId}` },
      ...(page > 1 && { robots: { index: false, follow: true } }),
      openGraph: {
        title: `${journalist.name} - Review Scores & Disparity | ReviewDisparity`,
        description,
        url: `/journalists/${canonicalId}`,
        type: "profile",
        images: journalist.image_url
          ? [{ url: journalist.image_url, alt: journalist.name }]
          : [{ url: `${siteUrl}/logo.png`, width: 900, height: 715, alt: "ReviewDisparity Logo" }],
      },
      twitter: {
        card: "summary",
        title: journalist.name,
        description,
        images: [journalist.image_url ?? `${siteUrl}/logo.png`],
      },
    };
  } catch {
    return { title: "Journalist Details" };
  }
}

export default async function JournalistDetailPage({
  params,
}: PageProps) {
  const { id } = await params;

  let journalist = null;

  try {
    journalist = await getJournalist(id);
  } catch (error) {
    console.error("Error fetching journalist:", error);
    notFound();
  }

  if (!journalist) {
    notFound();
  }

  if (id !== journalist.public_id) {
    redirect(`/journalists/${journalist.public_id}`);
  }

  const shareUrl = `${getSiteUrl()}/journalists/${journalist.public_id}`;
  const shareDisparity = journalist.stats?.overall_disparity_combined ?? journalist.avg_disparity ?? journalist.stats?.avg_disparity_combined;
  const shareDisparityStr = shareDisparity != null ? `${Number(shareDisparity) > 0 ? "+" : ""}${Number(shareDisparity).toFixed(1)}` : null;
  const shareTextParts = [`${journalist.name} on Review Disparity`];
  if (shareDisparityStr) shareTextParts.push(`Avg disparity: ${shareDisparityStr} across ${journalist.review_count} reviews`);
  const shareText = shareTextParts.join(" — ");

  const jsonLdData: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Person",
    name: journalist.name,
    url: `/journalists/${journalist.public_id}`,
    ...(journalist.image_url && { image: journalist.image_url }),
    ...(journalist.bio && { description: journalist.bio }),
    jobTitle: "Game Journalist",
  };

  return (
    <div className="space-y-8">
      <JsonLd data={jsonLdData} />
      {/* Header */}
      <div className="bg-white rounded-lg shadow p-6" style={{ position: 'relative' }}>
        <div style={{ position: 'absolute', top: '16px', right: '16px' }}>
          <ShareButtons url={shareUrl} text={shareText} />
        </div>
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
              {(() => {
                const steamDisparity = journalist.stats?.overall_disparity_steam ?? journalist.stats?.avg_disparity_steam;
                const mcDisparity = journalist.stats?.overall_disparity_metacritic ?? journalist.stats?.avg_disparity_metacritic;
                const combinedDisparity = journalist.stats?.overall_disparity_combined ?? journalist.avg_disparity ?? journalist.stats?.avg_disparity_combined;

                return (
                  <>
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
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
                          Combined Disparity
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
                    {(journalist.stats?.early_review_count != null || journalist.stats?.launch_window_review_count != null || journalist.stats?.late_review_count != null) && (() => {
                      const early = journalist.stats?.early_review_count ?? 0;
                      const launchWindow = journalist.stats?.launch_window_review_count ?? 0;
                      const late = journalist.stats?.late_review_count ?? 0;
                      const timingTotal = early + launchWindow + late;
                      const pct = (n: number) => timingTotal > 0 ? ((n / timingTotal) * 100).toFixed(0) : "0";

                      return (
                        <div className="mt-3 text-xs flex flex-wrap gap-x-3 gap-y-1" style={{ color: "var(--foreground-muted)" }}>
                          {early > 0 && (
                            <span className="inline-flex items-center gap-1">
                              <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                              {early} early ({pct(early)}%)
                            </span>
                          )}
                          <span className="inline-flex items-center gap-1">
                            <span className="w-2 h-2 rounded-full bg-green-500"></span>
                            {launchWindow} launch window ({pct(launchWindow)}%)
                          </span>
                          <span className="inline-flex items-center gap-1">
                            <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                            {late} late ({pct(late)}%)
                          </span>
                        </div>
                      );
                    })()}
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
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
              <h2 className="text-lg font-semibold text-gray-900 mb-1">
                Disparity by Outlet
              </h2>
              <p className="text-sm text-gray-500 mb-4">
                The journalist&apos;s average disparity score per outlet
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {journalist.outlet_breakdown.map((outlet) => (
                  <Link
                    key={outlet.outlet_id}
                    href={`/outlets/${outlet.outlet_public_id ?? outlet.outlet_id}`}
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
      <LazyChartSection
        entityType="journalist"
        entityId={journalist.public_id}
        timingCounts={{
          early: journalist.stats?.early_review_count ?? 0,
          launchWindow: journalist.stats?.launch_window_review_count ?? 0,
          late: journalist.stats?.late_review_count ?? 0,
        }}
      />

      {/* Reviews - client-side with filtering */}
      <JournalistReviewsSection journalistId={journalist.public_id} />
    </div>
  );
}
