import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { getOutlet } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { DisparityScoreCards } from "@/components/DisparityScores";
import { LazyChartSection } from "@/components/LazyChartSection";
import { OutletReviewsSection } from "@/components/OutletReviewsSection";
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
    const outlet = await getOutlet(id);
    const canonicalId = outlet.public_id;
    const disparity = outlet.avg_disparity_combined ?? outlet.avg_disparity;
    const disparityStr = disparity != null ? `${Number(disparity) > 0 ? "+" : ""}${Number(disparity).toFixed(1)}` : null;
    const avgScore = outlet.avg_score != null ? Number(outlet.avg_score).toFixed(1) : "N/A";
    const ogParams = new URLSearchParams({
      kind: "outlet",
      id: canonicalId,
      name: outlet.name,
      subtitle: "Outlet review disparity profile",
      disparity: disparity != null ? Number(disparity).toFixed(1) : "",
      reviews: (outlet.review_count ?? 0).toString(),
      score: avgScore,
      extra: `${outlet.journalist_count ?? 0} journalists tracked`,
      card: "o2",
    });
    const openGraphImage = `${siteUrl}/og/entity?${ogParams.toString()}`;

    let description = `${outlet.name} game review scores and critic-to-user disparity data.`;
    if (disparityStr) {
      description = `${outlet.name} has a ${disparityStr} average review disparity across ${outlet.review_count || 0} reviews from ${outlet.journalist_count || 0} journalists.`;
    }

    return {
      title: `${outlet.name} - Review Scores & Disparity`,
      description,
      alternates: { canonical: `/outlets/${canonicalId}` },
      ...(page > 1 && { robots: { index: false, follow: true } }),
      openGraph: {
        title: `${outlet.name} - Review Scores & Disparity | ReviewDisparity`,
        description,
        url: `${siteUrl}/outlets/${canonicalId}`,
        type: "website",
        images: [{ url: openGraphImage, width: 1200, height: 630, alt: `${outlet.name} review disparity snapshot` }],
      },
      twitter: {
        card: "summary_large_image",
        title: outlet.name,
        description,
        images: [openGraphImage],
      },
    };
  } catch {
    return { title: "Outlet Details" };
  }
}

export default async function OutletDetailPage({ params }: PageProps) {
  const { id } = await params;

  let outlet = null;

  try {
    outlet = await getOutlet(id);
  } catch (error) {
    console.error("Error fetching outlet:", error);
    notFound();
  }

  if (!outlet) {
    notFound();
  }

  if (id !== outlet.public_id) {
    redirect(`/outlets/${outlet.public_id}`);
  }

  const shareUrl = `${getSiteUrl()}/outlets/${outlet.public_id}?card=o2`;
  const shareDisparity = outlet.avg_disparity_combined ?? outlet.avg_disparity;
  const shareDisparityStr = shareDisparity != null ? `${Number(shareDisparity) > 0 ? "+" : ""}${Number(shareDisparity).toFixed(1)}` : null;
  const shareTextParts = [`${outlet.name} on Review Disparity`];
  if (shareDisparityStr) shareTextParts.push(`Avg disparity: ${shareDisparityStr} across ${outlet.review_count ?? 0} reviews`);
  const shareText = shareTextParts.join(" — ");

  const jsonLdData: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: outlet.name,
    url: `/outlets/${outlet.public_id}`,
    ...(outlet.logo_url && { logo: outlet.logo_url }),
    ...(outlet.website_url && { sameAs: [outlet.website_url] }),
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
            <div className="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
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
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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

        {/* Review Timing Breakdown */}
        {(outlet.early_review_count != null || outlet.launch_window_review_count != null || outlet.late_review_count != null) && (() => {
          const early = outlet.early_review_count ?? 0;
          const launchWindow = outlet.launch_window_review_count ?? 0;
          const late = outlet.late_review_count ?? 0;
          const timingTotal = early + launchWindow + late;
          if (timingTotal === 0) return null;
          const pct = (n: number) => timingTotal > 0 ? ((n / timingTotal) * 100).toFixed(0) : "0";

          return (
            <div className="mt-6 pt-6 border-t border-gray-200">
              <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>
                Review Timing
              </h2>
              <div className="text-xs flex flex-wrap gap-x-3 gap-y-1" style={{ color: "var(--foreground-muted)" }}>
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
            </div>
          );
        })()}
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
                href={`/journalists/${journalist.public_id}`}
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

      {/* Disparity Trend Chart - lazy loaded on scroll */}
      <LazyChartSection
        entityType="outlet"
        entityId={outlet.public_id}
        timingCounts={{
          early: outlet.early_review_count ?? 0,
          launchWindow: outlet.launch_window_review_count ?? 0,
          late: outlet.late_review_count ?? 0,
        }}
      />

      {/* Reviews with filters */}
      <OutletReviewsSection outletId={outlet.public_id} />
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
