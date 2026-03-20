import type { Metadata } from "next";
import { notFound, permanentRedirect } from "next/navigation";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { DisparityScoreCards } from "@/components/DisparityScores";
import { GameAvatar } from "@/components/GameAvatar";
import { ScoreDisplay } from "@/components/ScoreDisplay";
import { LazyChartSection } from "@/components/LazyChartSection";
import { JsonLd } from "@/components/JsonLd";
import { ExpandableText } from "@/components/ExpandableText";
import { getDisplayDisparity } from "@/lib/disparity-colors";
import { ShareButtons } from "@/components/ShareButtons";
import {
  buildEntityPath,
  buildEntitySegment,
  buildPathWithQuery,
  normalizeEntityRouteSegment,
  parseEntityRouteSegment,
} from "@/lib/entity-paths";
import { getSiteUrl } from "@/lib/site-url";
import {
  buildEntitySnapshotShareUrl,
} from "@/lib/share-url";
import {
  encodeSnapshotCount,
  encodeTrendSnapshot,
  hashSnapshotKey,
  readSnapshotCount,
  readSnapshotMetric,
  readTrendSnapshot,
  toTrendSnapshot,
} from "@/lib/share-snapshot";
import { getCachedGame, getCachedGameHistory, getCachedGameNews } from "@/lib/server-entity-loaders";

export const revalidate = 60;
const GAME_CARD_VERSION = "g15";
const GAME_CHART_CARD_VERSION = "gc1";

function formatDateLabel(value: string | null | undefined): string | null {
  if (!value) return null;
  return new Date(value).toLocaleDateString();
}

function formatPlayerCount(value: number | null | undefined): string | undefined {
  if (value == null) return undefined;
  return value.toLocaleString();
}

function formatRelativePeakLabel(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return undefined;
  const diffMs = Date.now() - parsed.getTime();
  if (diffMs < 0) return formatDateLabel(value) ?? undefined;
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "today";
  if (diffDays === 1) return "1 day ago";
  return `${diffDays} days ago`;
}

function buildGameSnapshotVersion(game: {
  critic_review_count?: number | null;
  avg_critic_score?: number | null;
  steam_user_score?: number | null;
  metacritic_user_score?: number | null;
  disparity_steam?: number | null;
  disparity_metacritic?: number | null;
}): string {
  const disparity = getDisplayDisparity(game.disparity_steam ?? null, game.disparity_metacritic ?? null);
  return [
    (game.critic_review_count ?? 0).toString(),
    game.avg_critic_score != null ? Number(game.avg_critic_score).toFixed(2) : "na",
    game.steam_user_score != null ? Number(game.steam_user_score).toFixed(2) : "na",
    game.metacritic_user_score != null ? Number(game.metacritic_user_score).toFixed(2) : "na",
    disparity != null ? Number(disparity).toFixed(2) : "na",
  ].join("-");
}

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}

export async function generateMetadata({ params, searchParams }: PageProps): Promise<Metadata> {
  const { id } = await params;
  const query = await searchParams;
  const siteUrl = getSiteUrl();
  try {
    const requestedSegment = parseEntityRouteSegment(id);
    const game = await getCachedGame(requestedSegment.identifier);
    const canonicalId = game.public_id;
    const canonicalPath = buildEntityPath("games", game.title, canonicalId);
    const requestedCardVersion = query.card?.trim() || GAME_CARD_VERSION;
    const shareMode = query.mode?.trim() === "chart"
      ? "chart"
      : query.mode?.trim() === "timing"
        ? "timing"
        : "default";
    const snapshotVersion = query.v?.trim() || buildGameSnapshotVersion(game);
    const shareNonce = query.sx?.trim()?.slice(0, 24) || undefined;
    const snapshotTrendParam = readTrendSnapshot(query.t);
    let snapshotTrend = snapshotTrendParam;
    if (shareMode === "chart" && snapshotTrend === undefined) {
      try {
        const history = await getCachedGameHistory(canonicalId, 180);
        snapshotTrend = toTrendSnapshot(history);
      } catch {
        snapshotTrend = [];
      }
    }
    const snapshotTrendEncoded = snapshotTrend && snapshotTrend.length > 0
      ? encodeTrendSnapshot(snapshotTrend)
      : "";
    const liveCriticScore = game.avg_critic_score != null ? Number(game.avg_critic_score) : null;
    const liveSteamScore = game.steam_user_score != null ? Number(game.steam_user_score) : null;
    const liveMetacriticScore = game.metacritic_user_score != null ? Number(game.metacritic_user_score) : null;
    const liveDisparity = getDisplayDisparity(game.disparity_steam, game.disparity_metacritic);
    const liveTiming = {
      early: game.early_review_count ?? 0,
      launch: game.launch_window_review_count ?? 0,
      late: game.late_review_count ?? 0,
    };
    const snapshotCriticParam = readSnapshotMetric(query.critic);
    const snapshotSteamParam = readSnapshotMetric(query.steam);
    const snapshotMetacriticParam = readSnapshotMetric(query.mc);
    const snapshotDisparityParam = readSnapshotMetric(query.disp);
    const snapshotEarlyParam = readSnapshotCount(query.early);
    const snapshotLaunchParam = readSnapshotCount(query.launch);
    const snapshotLateParam = readSnapshotCount(query.late);
    const snapshotCritic = snapshotCriticParam !== undefined ? snapshotCriticParam : liveCriticScore;
    const snapshotSteam = snapshotSteamParam !== undefined ? snapshotSteamParam : liveSteamScore;
    const snapshotMetacritic = snapshotMetacriticParam !== undefined ? snapshotMetacriticParam : liveMetacriticScore;
    const snapshotDisparity = snapshotDisparityParam !== undefined ? snapshotDisparityParam : liveDisparity;
    const snapshotTiming = {
      early: snapshotEarlyParam ?? liveTiming.early,
      launch: snapshotLaunchParam ?? liveTiming.launch,
      late: snapshotLateParam ?? liveTiming.late,
    };
    const isCardShareUrl = query.card != null
      || query.v != null
      || query.sx != null
      || query.critic != null
      || query.steam != null
      || query.mc != null
      || query.disp != null
      || query.t != null
      || query.early != null
      || query.launch != null
      || query.late != null
      || query.mode != null;
    const sharePageUrl = buildEntitySnapshotShareUrl(siteUrl, "games", game.title, canonicalId, {
      card: requestedCardVersion,
      version: snapshotVersion,
      critic: snapshotCritic,
      steam: snapshotSteam,
      metacritic: snapshotMetacritic,
      disparity: snapshotDisparity,
      mode: shareMode,
      trend: snapshotTrendEncoded || undefined,
      early: snapshotTiming.early,
      launch: snapshotTiming.launch,
      late: snapshotTiming.late,
      nonce: shareNonce,
    });
    const criticScore = snapshotCritic != null ? Number(snapshotCritic).toFixed(0) : null;
    const steamUserScore = snapshotSteam != null ? Number(snapshotSteam).toFixed(0) : null;
    const metacriticUserScore = snapshotMetacritic != null ? Number(snapshotMetacritic).toFixed(0) : null;
    const releaseDateLabel = formatDateLabel(game.release_date);
    const userScoreSummary = steamUserScore && metacriticUserScore
      ? `Steam ${steamUserScore} | MC ${metacriticUserScore}`
      : steamUserScore
        ? `Steam ${steamUserScore}`
        : metacriticUserScore
          ? `MC ${metacriticUserScore}`
          : null;
    const disparity = snapshotDisparity;
    const disparityStr = disparity != null ? `${Number(disparity) > 0 ? "+" : ""}${Number(disparity).toFixed(0)}` : null;
    const ogParams = new URLSearchParams({
      name: game.title,
      critic: criticScore ?? "N/A",
      steam: steamUserScore ?? "N/A",
      mc: metacriticUserScore ?? "N/A",
      disparity: disparity != null ? Number(disparity).toFixed(1) : "",
      reviews: (game.critic_review_count ?? 0).toString(),
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
    const openGraphImage = `${siteUrl}/og/game-card?${ogParams.toString()}`;

    const timingSummary = `Early ${snapshotTiming.early}, Launch ${snapshotTiming.launch}, Late ${snapshotTiming.late}`;
    const scoreSummary = criticScore && userScoreSummary
      ? `Critic ${criticScore} vs ${userScoreSummary}`
      : criticScore
        ? `Critic ${criticScore}`
        : userScoreSummary
          ? userScoreSummary
          : "Snapshot";
    const modeTitle = shareMode === "timing"
      ? `${game.title} - Review Timing Snapshot`
      : shareMode === "chart"
        ? `${game.title} - Disparity Trend Snapshot`
        : `${game.title} - Critic vs User Scores`;

    let description = `${game.title} critic vs user review scores.`;
    if (shareMode === "timing") {
      description = `${game.title}: review timing snapshot (${timingSummary}). ${scoreSummary}${disparityStr ? ` (${disparityStr} disparity).` : "."}`;
    } else if (shareMode === "chart") {
      description = `${game.title}: disparity trend snapshot. ${scoreSummary}${disparityStr ? ` (${disparityStr} disparity).` : "."}`;
    } else if (criticScore && userScoreSummary && disparityStr) {
      description = `${game.title}: critic score ${criticScore} vs ${userScoreSummary} (${disparityStr} disparity). See all ${game.critic_review_count || 0} critic reviews.`;
    } else if (criticScore) {
      description = `${game.title}: critic score ${criticScore} across ${game.critic_review_count || 0} review${(game.critic_review_count || 0) === 1 ? "" : "s"}.${releaseDateLabel ? ` Released ${releaseDateLabel}.` : ""}${userScoreSummary ? ` Player-score coverage currently shows ${userScoreSummary}.` : " Player-score coverage is still limited."}`;
    }

    return {
      title: modeTitle,
      description,
      alternates: { canonical: canonicalPath },
      ...(isCardShareUrl && { robots: { index: false, follow: true } }),
      openGraph: {
        title: `${modeTitle} | ReviewDisparity`,
        description,
        url: isCardShareUrl ? sharePageUrl : `${siteUrl}${canonicalPath}`,
        type: "article",
        images: [{ url: openGraphImage, width: 1200, height: 630, alt: `${game.title} ${shareMode === "timing" ? "review timing" : "review disparity"} snapshot` }],
      },
      twitter: {
        card: "summary_large_image",
        title: modeTitle,
        description,
        images: [openGraphImage],
      },
    };
  } catch {
    return { title: "Game Details" };
  }
}

export default async function GameDetailPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const query = await searchParams;
  const normalizedId = normalizeEntityRouteSegment(id);
  const requestedSegment = parseEntityRouteSegment(id);
  const siteUrl = getSiteUrl();

  let game = null;
  let newsArticles: Awaited<ReturnType<typeof getCachedGameNews>>["items"] = [];
  let newsTotalPages = 0;
  let chartTrendEncoded = "";

  try {
    game = await getCachedGame(requestedSegment.identifier);
  } catch (error) {
    console.error("Error fetching game:", error);
    notFound();
  }

  if (!game) {
    notFound();
  }

  const canonicalSegment = buildEntitySegment(game.title, game.public_id);
  const canonicalPath = buildEntityPath("games", game.title, game.public_id);
  if (normalizedId !== canonicalSegment) {
    permanentRedirect(buildPathWithQuery(canonicalPath, query));
  }

  const [newsResponse, history] = await Promise.all([
    getCachedGameNews(game.public_id, 1, 5).catch(() => null),
    getCachedGameHistory(game.public_id, 180).catch(() => null),
  ]);

  if (newsResponse) {
    newsArticles = newsResponse.items;
    newsTotalPages = newsResponse.total_pages;
  }

  if (history) {
    chartTrendEncoded = encodeTrendSnapshot(toTrendSnapshot(history));
  }

  const jsonLdData: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "VideoGame",
    name: game.title,
    url: `${siteUrl}${canonicalPath}`,
    ...(game.release_date && { datePublished: game.release_date }),
    ...(game.description && { description: game.description }),
    ...(game.avg_critic_score != null && {
      aggregateRating: {
        "@type": "AggregateRating",
        ratingValue: Number(game.avg_critic_score).toFixed(1),
        bestRating: 100,
        worstRating: 0,
        ratingCount: game.critic_review_count || 1,
      },
    }),
  };

  const shareDisparity = getDisplayDisparity(game.disparity_steam, game.disparity_metacritic);
  const shareDisparityStr = shareDisparity != null ? `${Number(shareDisparity) > 0 ? "+" : ""}${Number(shareDisparity).toFixed(0)}` : null;
  const shareCriticScore = game.avg_critic_score != null ? Number(game.avg_critic_score).toFixed(0) : null;
  const releaseDateLabel = formatDateLabel(game.release_date);
  const shareSnapshotVersion = buildGameSnapshotVersion(game);
  const breadcrumbJsonLd: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: `${siteUrl}/` },
      { "@type": "ListItem", position: 2, name: "Games", item: `${siteUrl}/games` },
      { "@type": "ListItem", position: 3, name: game.title, item: `${siteUrl}${canonicalPath}` },
    ],
  };

  const shareUrl = buildEntitySnapshotShareUrl(siteUrl, "games", game.title, game.public_id, {
    card: GAME_CARD_VERSION,
    version: shareSnapshotVersion,
    critic: game.avg_critic_score,
    steam: game.steam_user_score,
    metacritic: game.metacritic_user_score,
    disparity: shareDisparity,
  });
  const disparityChartShareUrl = buildEntitySnapshotShareUrl(siteUrl, "games", game.title, game.public_id, {
    card: GAME_CHART_CARD_VERSION,
    version: shareSnapshotVersion,
    critic: game.avg_critic_score,
    steam: game.steam_user_score,
    metacritic: game.metacritic_user_score,
    disparity: shareDisparity,
    mode: "chart",
    trend: chartTrendEncoded || undefined,
  });
  const timingChartShareUrl = buildEntitySnapshotShareUrl(siteUrl, "games", game.title, game.public_id, {
    card: GAME_CHART_CARD_VERSION,
    version: shareSnapshotVersion,
    critic: game.avg_critic_score,
    steam: game.steam_user_score,
    metacritic: game.metacritic_user_score,
    disparity: shareDisparity,
    mode: "timing",
    early: game.early_review_count,
    launch: game.launch_window_review_count,
    late: game.late_review_count,
  });
  const hasBothUserScores = game.steam_user_score != null && game.metacritic_user_score != null;
  const shareTextParts = [`${game.title} on Review Disparity`];
  if (shareCriticScore) shareTextParts.push(`Critic: ${shareCriticScore}`);
  if (hasBothUserScores) {
    shareTextParts.push(`Steam: ${Number(game.steam_user_score).toFixed(0)}`);
    shareTextParts.push(`MC: ${Number(game.metacritic_user_score).toFixed(0)}`);
  } else if (game.steam_user_score != null) {
    shareTextParts.push(`Steam: ${Number(game.steam_user_score).toFixed(0)}`);
  } else if (game.metacritic_user_score != null) {
    shareTextParts.push(`MC: ${Number(game.metacritic_user_score).toFixed(0)}`);
  }
  if (shareDisparityStr) shareTextParts.push(`Disparity: ${shareDisparityStr}`);
  const shareText = shareTextParts.join(" — ");
  const chartShareTextParts = [`${game.title} disparity trend snapshot on Review Disparity`];
  if (shareCriticScore) chartShareTextParts.push(`Critic: ${shareCriticScore}`);
  if (hasBothUserScores) {
    chartShareTextParts.push(`Steam: ${Number(game.steam_user_score).toFixed(0)}`);
    chartShareTextParts.push(`MC: ${Number(game.metacritic_user_score).toFixed(0)}`);
  } else if (game.steam_user_score != null) {
    chartShareTextParts.push(`Steam: ${Number(game.steam_user_score).toFixed(0)}`);
  } else if (game.metacritic_user_score != null) {
    chartShareTextParts.push(`MC: ${Number(game.metacritic_user_score).toFixed(0)}`);
  }
  if (shareDisparityStr) chartShareTextParts.push(`Disparity: ${shareDisparityStr}`);
  const disparityChartShareText = chartShareTextParts.join(" — ");
  const timingShareTextParts = [`${game.title} review timing snapshot on Review Disparity`];
  if (shareCriticScore) timingShareTextParts.push(`Critic: ${shareCriticScore}`);
  if (hasBothUserScores) {
    timingShareTextParts.push(`Steam: ${Number(game.steam_user_score).toFixed(0)}`);
    timingShareTextParts.push(`MC: ${Number(game.metacritic_user_score).toFixed(0)}`);
  } else if (game.steam_user_score != null) {
    timingShareTextParts.push(`Steam: ${Number(game.steam_user_score).toFixed(0)}`);
  } else if (game.metacritic_user_score != null) {
    timingShareTextParts.push(`MC: ${Number(game.metacritic_user_score).toFixed(0)}`);
  }
  timingShareTextParts.push(`Early: ${game.early_review_count ?? 0}`);
  timingShareTextParts.push(`Launch: ${game.launch_window_review_count ?? 0}`);
  timingShareTextParts.push(`Late: ${game.late_review_count ?? 0}`);
  if (shareDisparityStr) timingShareTextParts.push(`Disparity: ${shareDisparityStr}`);
  const timingChartShareText = timingShareTextParts.join(" — ");
  const hasSteamApp = game.steam_app_id != null;

  return (
    <div className="space-y-8">
      <JsonLd data={jsonLdData} />
      <JsonLd data={breadcrumbJsonLd} />
      <Breadcrumbs
        items={[
          { href: "/", label: "Home" },
          { href: "/games", label: "Games" },
          { label: game.title },
        ]}
      />
      {/* Header */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6">
          <div className="flex flex-1 flex-col gap-4 sm:flex-row sm:items-start">
            <GameAvatar
              title={game.title}
              imageUrl={game.image_url}
              width={640}
              height={360}
              sizes="(max-width: 639px) 100vw, 144px"
              className="w-full rounded-2xl object-cover aspect-[16/9] sm:h-[81px] sm:w-36 sm:shrink-0 sm:aspect-auto sm:object-contain"
            />
            <div className="min-w-0 flex-1">
              <h1 className="text-3xl sm:text-4xl font-bold leading-tight" style={{ color: "var(--foreground)" }}>{game.title}</h1>
              {game.release_date && (
                <p className="mt-2 text-sm text-gray-500">
                  Released: {releaseDateLabel}
                </p>
              )}
              <div className="mt-3">
                <ShareButtons url={shareUrl} text={shareText} />
              </div>
              {game.description && (
                <ExpandableText
                  text={game.description}
                  className="mt-4 text-gray-600"
                />
              )}
            </div>
          </div>

          <ScoreDisplay
            criticScore={game.avg_critic_score}
            steamUserScore={game.steam_user_score}
            metacriticUserScore={game.metacritic_user_score}
            criticDisparity={shareDisparity}
            steamDisparity={game.disparity_steam}
            metacriticDisparity={game.disparity_metacritic}
            size="lg"
            useDisparityPalette
          />
        </div>

        {/* Score Breakdown */}
        <div className="mt-6 pt-6 border-t border-gray-200">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--foreground)" }}>
            Score Breakdown
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <ScoreCard
              label="Critic Average"
              value={game.avg_critic_score != null ? Number(game.avg_critic_score).toFixed(1) : undefined}
              subtitle={`${game.critic_review_count || 0} reviews`}
            />
            <ScoreCard
              label="Steam User Score"
              value={game.steam_user_score != null ? Number(game.steam_user_score).toFixed(0) : undefined}
              subtitle={
                game.steam_user_score != null
                  ? game.steam_sample_size
                    ? `${game.steam_sample_size.toLocaleString()} reviews`
                    : undefined
                  : "Less than 50 reviews"
              }
            />
            <ScoreCard
              label="Metacritic User Score"
              value={game.metacritic_user_score != null ? Number(game.metacritic_user_score).toFixed(0) : undefined}
              subtitle={
                game.metacritic_user_score != null
                  ? game.metacritic_sample_size
                    ? `${game.metacritic_sample_size.toLocaleString()} reviews`
                    : undefined
                  : "Less than 20 reviews"
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
            combinedDisparity={getDisplayDisparity(game.disparity_steam, game.disparity_metacritic)}
          />
        </div>

        {hasSteamApp && (
          <div className="mt-6 pt-6 border-t border-gray-200">
            <div>
              <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--foreground)" }}>
                Steam Activity
              </h2>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
              <ScoreCard
                label="All-Time High"
                value={formatPlayerCount(game.steam_player_all_time_peak)}
                subtitle={formatRelativePeakLabel(game.steam_player_all_time_peak_at)}
              />
              <ScoreCard
                label="24-Hour High"
                value={formatPlayerCount(game.steam_player_24h_peak)}
              />
              <ScoreCard
                label="24-Hour Low"
                value={formatPlayerCount(game.steam_player_24h_low_observed)}
              />
              <ScoreCard
                label="Achievements"
                value={formatPlayerCount(game.steam_achievement_count)}
                subtitle={game.steam_achievement_count != null ? "Steam public store data" : undefined}
              />
            </div>
          </div>
        )}

        {/* Review Timing Breakdown */}
        {(game.early_review_count != null || game.launch_window_review_count != null || game.late_review_count != null) && (() => {
          const early = game.early_review_count ?? 0;
          const launchWindow = game.launch_window_review_count ?? 0;
          const late = game.late_review_count ?? 0;
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

      {/* Disparity Chart + Critic Reviews + Journalist Alignment + News - lazy loaded on scroll */}
      <LazyChartSection
        entityType="game"
        entityId={game.public_id}
        gameTitle={game.title}
        hasSteamApp={hasSteamApp}
        disparityChartShareUrl={disparityChartShareUrl}
        disparityChartShareText={disparityChartShareText}
        timingChartShareUrl={timingChartShareUrl}
        timingChartShareText={timingChartShareText}
        newsArticles={newsArticles}
        newsTotalPages={newsTotalPages}
        timingCounts={{
          early: game.early_review_count ?? 0,
          launchWindow: game.launch_window_review_count ?? 0,
          late: game.late_review_count ?? 0,
        }}
        releaseDate={game.release_date}
        steamUserScore={game.steam_user_score}
        metacriticUserScore={game.metacritic_user_score}
      />
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
