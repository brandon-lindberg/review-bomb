import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { getOutlet, getOutletHistory } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { DisparityScoreCards } from "@/components/DisparityScores";
import { LazyChartSection } from "@/components/LazyChartSection";
import { OutletReviewsSection } from "@/components/OutletReviewsSection";
import { JsonLd } from "@/components/JsonLd";
import { ShareButtons } from "@/components/ShareButtons";
import { getSiteUrl } from "@/lib/site-url";
import { buildEntitySnapshotShareUrl } from "@/lib/share-url";
import {
  deriveSourceScoreFromDisparity,
  encodeSnapshotCount,
  encodeSnapshotMetric,
  encodeTrendSnapshot,
  formatSnapshotDisplay,
  hashSnapshotKey,
  readSnapshotCount,
  readSnapshotMetric,
  readTrendSnapshot,
  toTrendSnapshot,
} from "@/lib/share-snapshot";

export const revalidate = 60;
const OUTLET_CARD_VERSION = "o3";
const OUTLET_CHART_CARD_VERSION = "oc1";

function buildOutletSnapshotVersion(values: {
  reviewCount: number;
  criticScore: number | null | undefined;
  steamScore: number | null | undefined;
  metacriticScore: number | null | undefined;
  combinedDisparity: number | null | undefined;
}): string {
  return [
    values.reviewCount.toString(),
    encodeSnapshotMetric(values.criticScore),
    encodeSnapshotMetric(values.steamScore),
    encodeSnapshotMetric(values.metacriticScore),
    encodeSnapshotMetric(values.combinedDisparity),
  ].join(",");
}

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{
    page?: string;
    card?: string;
    v?: string;
    sx?: string;
    mode?: string;
    critic?: string;
    steam?: string;
    mc?: string;
    disp?: string;
    t?: string;
    early?: string;
    launch?: string;
    late?: string;
  }>;
}

export async function generateMetadata({ params, searchParams }: PageProps): Promise<Metadata> {
  const { id } = await params;
  const query = await searchParams;
  const { page: pageParam } = query;
  const page = parseInt(pageParam || "1");
  const siteUrl = getSiteUrl();

  try {
    const outlet = await getOutlet(id);
    const canonicalId = outlet.public_id;
    const requestedCardVersion = query.card?.trim() || OUTLET_CARD_VERSION;
    const shareMode = query.mode?.trim() === "chart"
      ? "chart"
      : query.mode?.trim() === "timing"
        ? "timing"
        : "default";
    const snapshotTrendParam = readTrendSnapshot(query.t);
    const liveCombinedDisparity = outlet.avg_disparity_combined ?? outlet.avg_disparity;
    const liveCriticScore = outlet.avg_score != null ? Number(outlet.avg_score) : null;
    const liveSteamScore = deriveSourceScoreFromDisparity(liveCriticScore, outlet.avg_disparity_steam);
    const liveMetacriticScore = deriveSourceScoreFromDisparity(liveCriticScore, outlet.avg_disparity_metacritic);
    const liveTiming = {
      early: outlet.early_review_count ?? 0,
      launch: outlet.launch_window_review_count ?? 0,
      late: outlet.late_review_count ?? 0,
    };
    const snapshotCriticMetric = readSnapshotMetric(query.critic);
    const snapshotSteamMetric = readSnapshotMetric(query.steam);
    const snapshotMetacriticMetric = readSnapshotMetric(query.mc);
    const snapshotDisparityMetric = readSnapshotMetric(query.disp);
    const snapshotEarlyMetric = readSnapshotCount(query.early);
    const snapshotLaunchMetric = readSnapshotCount(query.launch);
    const snapshotLateMetric = readSnapshotCount(query.late);
    const snapshotCriticScore = snapshotCriticMetric !== undefined ? snapshotCriticMetric : liveCriticScore;
    const snapshotSteamScore = snapshotSteamMetric !== undefined ? snapshotSteamMetric : liveSteamScore;
    const snapshotMetacriticScore = snapshotMetacriticMetric !== undefined ? snapshotMetacriticMetric : liveMetacriticScore;
    const snapshotCombinedDisparity = snapshotDisparityMetric !== undefined ? snapshotDisparityMetric : liveCombinedDisparity;
    const snapshotTiming = {
      early: snapshotEarlyMetric ?? liveTiming.early,
      launch: snapshotLaunchMetric ?? liveTiming.launch,
      late: snapshotLateMetric ?? liveTiming.late,
    };
    let snapshotTrend = snapshotTrendParam;
    if (shareMode === "chart" && snapshotTrend === undefined) {
      try {
        const history = await getOutletHistory(canonicalId, 180);
        snapshotTrend = toTrendSnapshot(history);
      } catch {
        snapshotTrend = [];
      }
    }
    const snapshotTrendEncoded = snapshotTrend && snapshotTrend.length > 0
      ? encodeTrendSnapshot(snapshotTrend)
      : "";
    const snapshotVersion = query.v?.trim() || buildOutletSnapshotVersion({
      reviewCount: outlet.review_count ?? 0,
      criticScore: snapshotCriticScore,
      steamScore: snapshotSteamScore,
      metacriticScore: snapshotMetacriticScore,
      combinedDisparity: snapshotCombinedDisparity,
    });
    const shareNonce = query.sx?.trim()?.slice(0, 24) || undefined;
    const isCardShareUrl = query.card != null
      || query.v != null
      || query.sx != null
      || query.mode != null
      || query.critic != null
      || query.steam != null
      || query.mc != null
      || query.disp != null
      || query.t != null
      || query.early != null
      || query.launch != null
      || query.late != null;
    const sharePageUrl = buildEntitySnapshotShareUrl(siteUrl, "outlets", canonicalId, {
      card: requestedCardVersion,
      version: snapshotVersion,
      critic: snapshotCriticScore,
      steam: snapshotSteamScore,
      metacritic: snapshotMetacriticScore,
      disparity: snapshotCombinedDisparity,
      mode: shareMode,
      trend: snapshotTrendEncoded || undefined,
      early: snapshotTiming.early,
      launch: snapshotTiming.launch,
      late: snapshotTiming.late,
      nonce: shareNonce,
    });
    const disparity = snapshotCombinedDisparity;
    const disparityStr = disparity != null ? `${Number(disparity) > 0 ? "+" : ""}${Number(disparity).toFixed(1)}` : null;
    const ogParams = new URLSearchParams({
      kind: "outlet",
      name: outlet.name,
      disparity: disparity != null ? Number(disparity).toFixed(1) : "",
      reviews: (outlet.review_count ?? 0).toString(),
      critic: formatSnapshotDisplay(snapshotCriticScore),
      steam: formatSnapshotDisplay(snapshotSteamScore),
      mc: formatSnapshotDisplay(snapshotMetacriticScore),
      card: requestedCardVersion,
      v: snapshotVersion,
      mode: shareMode,
      id: canonicalId,
    });
    if (snapshotTrendEncoded) {
      ogParams.set("t", snapshotTrendEncoded);
    }
    if (shareMode === "timing") {
      const early = encodeSnapshotCount(snapshotTiming.early);
      const launch = encodeSnapshotCount(snapshotTiming.launch);
      const late = encodeSnapshotCount(snapshotTiming.late);
      if (early !== undefined) ogParams.set("early", early);
      if (launch !== undefined) ogParams.set("launch", launch);
      if (late !== undefined) ogParams.set("late", late);
    }
    const timingKey = `${snapshotTiming.early}-${snapshotTiming.launch}-${snapshotTiming.late}`;
    const imageKeySource = shareNonce
      ? `${canonicalId}|${snapshotVersion}|${shareMode}|${snapshotTrendEncoded}|${timingKey}|${shareNonce}`
      : `${canonicalId}|${snapshotVersion}|${shareMode}|${snapshotTrendEncoded}|${timingKey}`;
    const imageCacheKey = `${requestedCardVersion}-${hashSnapshotKey(imageKeySource)}`;
    ogParams.set("ik", imageCacheKey);
    const openGraphImage = `${siteUrl}/og/entity?${ogParams.toString()}`;

    const timingSummary = `Early ${snapshotTiming.early}, Launch ${snapshotTiming.launch}, Late ${snapshotTiming.late}`;
    const modeTitle = shareMode === "timing"
      ? `${outlet.name} - Review Timing Snapshot`
      : shareMode === "chart"
        ? `${outlet.name} - Disparity Trend Snapshot`
        : `${outlet.name} - Review Scores & Disparity`;

    let description = `${outlet.name} game review scores and critic-to-user disparity data.`;
    if (shareMode === "timing") {
      description = `${outlet.name} review timing snapshot (${timingSummary}) across ${outlet.review_count || 0} reviews.${disparityStr ? ` Avg disparity ${disparityStr}.` : ""}`;
    } else if (shareMode === "chart") {
      description = `${outlet.name} disparity trend snapshot across ${outlet.review_count || 0} reviews.${disparityStr ? ` Avg disparity ${disparityStr}.` : ""}`;
    } else if (disparityStr) {
      description = `${outlet.name} has a ${disparityStr} average review disparity across ${outlet.review_count || 0} reviews from ${outlet.journalist_count || 0} journalists.`;
    }

    return {
      title: modeTitle,
      description,
      alternates: isCardShareUrl ? undefined : { canonical: `/outlets/${canonicalId}` },
      ...(isCardShareUrl && { robots: { index: false, follow: true } }),
      ...(page > 1 && { robots: { index: false, follow: true } }),
      openGraph: {
        title: `${modeTitle} | ReviewDisparity`,
        description,
        url: isCardShareUrl ? sharePageUrl : `${siteUrl}/outlets/${canonicalId}`,
        type: "website",
        images: [{ url: openGraphImage, width: 1200, height: 630, alt: `${outlet.name} ${shareMode === "timing" ? "review timing" : "review disparity"} snapshot` }],
      },
      twitter: {
        card: "summary_large_image",
        title: modeTitle,
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
  let chartTrendEncoded = "";

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

  try {
    const history = await getOutletHistory(outlet.public_id, 180);
    chartTrendEncoded = encodeTrendSnapshot(toTrendSnapshot(history));
  } catch {
    // Chart share still works without trend payload, OG route will try live fetch
  }

  const shareDisparity = outlet.avg_disparity_combined ?? outlet.avg_disparity;
  const shareDisparityStr = shareDisparity != null ? `${Number(shareDisparity) > 0 ? "+" : ""}${Number(shareDisparity).toFixed(1)}` : null;
  const shareCriticScore = outlet.avg_score != null ? Number(outlet.avg_score) : null;
  const shareSteamScore = deriveSourceScoreFromDisparity(shareCriticScore, outlet.avg_disparity_steam);
  const shareMetacriticScore = deriveSourceScoreFromDisparity(shareCriticScore, outlet.avg_disparity_metacritic);
  const shareSnapshotVersion = buildOutletSnapshotVersion({
    reviewCount: outlet.review_count ?? 0,
    criticScore: shareCriticScore,
    steamScore: shareSteamScore,
    metacriticScore: shareMetacriticScore,
    combinedDisparity: shareDisparity,
  });
  const shareUrl = buildEntitySnapshotShareUrl(getSiteUrl(), "outlets", outlet.public_id, {
    card: OUTLET_CARD_VERSION,
    version: shareSnapshotVersion,
    critic: shareCriticScore,
    steam: shareSteamScore,
    metacritic: shareMetacriticScore,
    disparity: shareDisparity,
  });
  const disparityChartShareUrl = buildEntitySnapshotShareUrl(getSiteUrl(), "outlets", outlet.public_id, {
    card: OUTLET_CHART_CARD_VERSION,
    version: shareSnapshotVersion,
    critic: shareCriticScore,
    steam: shareSteamScore,
    metacritic: shareMetacriticScore,
    disparity: shareDisparity,
    mode: "chart",
    trend: chartTrendEncoded || undefined,
  });
  const timingChartShareUrl = buildEntitySnapshotShareUrl(getSiteUrl(), "outlets", outlet.public_id, {
    card: OUTLET_CHART_CARD_VERSION,
    version: shareSnapshotVersion,
    critic: shareCriticScore,
    steam: shareSteamScore,
    metacritic: shareMetacriticScore,
    disparity: shareDisparity,
    mode: "timing",
    early: outlet.early_review_count,
    launch: outlet.launch_window_review_count,
    late: outlet.late_review_count,
  });
  const shareTextParts = [`${outlet.name} on Review Disparity`];
  if (shareCriticScore != null) shareTextParts.push(`Critic: ${Number(shareCriticScore).toFixed(0)}`);
  if (shareSteamScore != null) shareTextParts.push(`Steam: ${Number(shareSteamScore).toFixed(0)}`);
  if (shareMetacriticScore != null) shareTextParts.push(`MC: ${Number(shareMetacriticScore).toFixed(0)}`);
  if (shareDisparityStr) shareTextParts.push(`Avg disparity: ${shareDisparityStr} across ${outlet.review_count ?? 0} reviews`);
  const shareText = shareTextParts.join(" — ");
  const chartShareTextParts = [`${outlet.name} disparity trend snapshot on Review Disparity`];
  if (shareCriticScore != null) chartShareTextParts.push(`Critic: ${Number(shareCriticScore).toFixed(0)}`);
  if (shareSteamScore != null) chartShareTextParts.push(`Steam: ${Number(shareSteamScore).toFixed(0)}`);
  if (shareMetacriticScore != null) chartShareTextParts.push(`MC: ${Number(shareMetacriticScore).toFixed(0)}`);
  if (shareDisparityStr) chartShareTextParts.push(`Disparity: ${shareDisparityStr}`);
  const disparityChartShareText = chartShareTextParts.join(" — ");
  const timingShareTextParts = [`${outlet.name} review timing snapshot on Review Disparity`];
  if (shareCriticScore != null) timingShareTextParts.push(`Critic: ${Number(shareCriticScore).toFixed(0)}`);
  if (shareSteamScore != null) timingShareTextParts.push(`Steam: ${Number(shareSteamScore).toFixed(0)}`);
  if (shareMetacriticScore != null) timingShareTextParts.push(`MC: ${Number(shareMetacriticScore).toFixed(0)}`);
  timingShareTextParts.push(`Early: ${outlet.early_review_count ?? 0}`);
  timingShareTextParts.push(`Launch: ${outlet.launch_window_review_count ?? 0}`);
  timingShareTextParts.push(`Late: ${outlet.late_review_count ?? 0}`);
  if (shareDisparityStr) timingShareTextParts.push(`Disparity: ${shareDisparityStr}`);
  const timingChartShareText = timingShareTextParts.join(" — ");

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
        disparityChartShareUrl={disparityChartShareUrl}
        disparityChartShareText={disparityChartShareText}
        timingChartShareUrl={timingChartShareUrl}
        timingChartShareText={timingChartShareText}
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
