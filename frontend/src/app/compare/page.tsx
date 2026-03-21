import { Suspense, type ReactNode } from "react";
import type { Metadata } from "next";
import Image from "@/components/AppImage";
import Link from "next/link";
import { getGame, getGameHistory, getGameSteamActivity, getJournalist, getJournalistHistory, getOutlet, getOutletHistory } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { MiniDisparityChart } from "@/components/DisparityChart";
import { CompareMetricControls } from "@/components/CompareMetricControls";
import { CompareMetricRowToggle } from "@/components/CompareMetricRowToggle";
import { CompareSelector } from "@/components/CompareSelector";
import { GameAvatar } from "@/components/GameAvatar";
import { MiniPlayerCountChart } from "@/components/MiniPlayerCountChart";
import { ShareButtons } from "@/components/ShareButtons";
import { parseCompareMetricSelection, type CompareType } from "@/lib/compare-metrics";
import { getDisplayDisparity } from "@/lib/disparity-colors";
import { buildEntityPath } from "@/lib/entity-paths";
import { toPlayerCountTrend } from "@/lib/player-count-chart";
import { getSiteUrl } from "@/lib/site-url";
import { deriveSourceScoreFromDisparity } from "@/lib/share-snapshot";
import { buildCompareShareUrl } from "@/lib/share-url";
import type { DisparitySnapshot } from "@/types";

export const revalidate = 300;
const COMPARE_PLAYER_TREND_LIMIT = 72;

const compareTypeLabel: Record<CompareType, string> = {
  journalists: "journalists",
  outlets: "outlets",
  games: "games",
};

function normalizeCompareType(rawType?: string): CompareType {
  if (rawType === "journalists" || rawType === "outlets" || rawType === "games") {
    return rawType;
  }
  return "journalists";
}

function parseCompareIds(rawIds?: string): number[] {
  if (!rawIds) return [];

  const ids: number[] = [];
  const seen = new Set<number>();

  for (const token of rawIds.split(",")) {
    const parsed = Number.parseInt(token.trim(), 10);
    if (!Number.isInteger(parsed) || parsed <= 0 || seen.has(parsed)) continue;
    seen.add(parsed);
    ids.push(parsed);
    if (ids.length >= 4) break;
  }

  return ids;
}

interface PageProps {
  searchParams: Promise<{
    type?: string;
    ids?: string;
    card?: string;
    labels?: string;
    metrics?: string;
    snap?: string;
    sx?: string;
  }>;
}

interface CompareData {
  id: number;
  name: string;
  image_url: string | null;
  review_count: number;
  avg_disparity: number | null;
  avg_score: number | null;
  steam_user_score: number | null;
  steam_current_players: number | null;
  steam_player_24h_peak: number | null;
  steam_player_24h_low_observed: number | null;
  steam_player_all_time_peak: number | null;
  steam_achievement_count: number | null;
  metacritic_user_score: number | null;
  player_count_trend: number[];
  history: DisparitySnapshot[];
  linkHref: string;
}

function parseCompareLabels(rawLabels?: string): string[] {
  if (!rawLabels) return [];
  return rawLabels
    .split("|")
    .map((label) => label.trim())
    .filter((label) => label.length > 0)
    .slice(0, 4);
}

function toTrendSnapshot(history: DisparitySnapshot[]): number[] {
  if (!history || history.length === 0) return [];

  const values = history
    .map((point) => {
      const combined = point.avg_disparity_combined != null
        ? Number(point.avg_disparity_combined)
        : point.avg_disparity_steam != null && point.avg_disparity_metacritic != null
          ? (Number(point.avg_disparity_steam) + Number(point.avg_disparity_metacritic)) / 2
          : point.avg_disparity_steam ?? point.avg_disparity_metacritic ?? null;
      if (combined == null || !Number.isFinite(Number(combined))) return null;
      return Number(Number(combined).toFixed(1));
    })
    .filter((value): value is number => value != null);

  return values.slice(-16);
}

function buildCompareSnapshotPayload(items: CompareData[]): string {
  return JSON.stringify(
    items.slice(0, 4).map((item) => ({
      n: item.name,
      c: item.avg_score,
      s: item.steam_user_score,
      m: item.metacritic_user_score,
      d: item.avg_disparity,
      r: item.review_count,
      t: toTrendSnapshot(item.history),
      ...((
        item.steam_current_players != null
        || item.steam_player_24h_peak != null
        || item.steam_player_24h_low_observed != null
        || item.steam_player_all_time_peak != null
        || item.player_count_trend.length > 0
      ) ? {
        p: item.steam_current_players,
        h: item.steam_player_24h_peak,
        l: item.steam_player_24h_low_observed,
        a: item.steam_player_all_time_peak,
        ac: item.steam_achievement_count,
        pt: item.player_count_trend,
      } : {}),
    }))
  );
}

function formatPlayerCount(value: number | null): string {
  return value != null ? value.toLocaleString() : "N/A";
}

export async function generateMetadata({ searchParams }: PageProps): Promise<Metadata> {
  const params = await searchParams;
  const type = normalizeCompareType(params.type);
  const ids = parseCompareIds(params.ids);
  const labels = parseCompareLabels(params.labels);
  const siteUrl = getSiteUrl();
  const queryParams = new URLSearchParams({ type });
  if (ids.length > 0) {
    queryParams.set("ids", ids.join(","));
  }
  if (params.card) {
    queryParams.set("card", params.card);
  }
  if (labels.length > 0) {
    queryParams.set("labels", labels.join("|"));
  }
  if (params.metrics?.trim()) {
    queryParams.set("metrics", params.metrics.trim());
  }
  if (params.snap?.trim()) {
    queryParams.set("snap", params.snap.trim());
  }
  if (params.sx?.trim()) {
    queryParams.set("sx", params.sx.trim().slice(0, 24));
  }

  const compareLabel = compareTypeLabel[type];
  const compareCount = Math.max(ids.length, labels.length);
  const isParameterizedState = ids.length > 0
    || labels.length > 0
    || Boolean(params.snap?.trim())
    || Boolean(params.card?.trim())
    || Boolean(params.sx?.trim());
  const title = labels.length > 0
    ? `Compare ${labels.join(" vs ")}`
    : compareCount > 0
      ? `Compare ${compareCount} ${compareLabel}`
    : `Compare ${compareLabel}`;
  const description = compareCount > 0
    ? type === "games"
      ? "Compare selected games on ReviewDisparity. See disparity, critic and user scores, Steam player counts, and trend snapshots side by side."
      : `Compare selected ${compareLabel} on ReviewDisparity. See disparity, review volume, score averages, and trend snapshots side by side.`
    : "Compare game journalists, outlets, and games side by side. See how their review scores, disparity trends, and Steam player counts differ over time.";
  const comparePath = `/compare?${queryParams.toString()}`;
  const openGraphImage = `${siteUrl}/compare/og?${queryParams.toString()}`;

  return {
    title,
    description,
    alternates: { canonical: "/compare" },
    ...(isParameterizedState && { robots: { index: false, follow: true } }),
    openGraph: {
      title: `${title} - ReviewDisparity`,
      description,
      url: `${siteUrl}${comparePath}`,
      images: [
        {
          url: openGraphImage,
          width: 1200,
          height: 630,
          alt: title,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [openGraphImage],
    },
  };
}

export default async function ComparePage({ searchParams }: PageProps) {
  const params = await searchParams;
  const type = normalizeCompareType(params.type);
  const ids = parseCompareIds(params.ids);
  const selectedMetricIds = parseCompareMetricSelection(type, params.metrics);
  const selectedMetricSet = new Set(selectedMetricIds);

  const tabs = [
    { id: "journalists", label: "Journalists" },
    { id: "outlets", label: "Outlets" },
    { id: "games", label: "Games" },
  ];

  // Fetch data for selected items
  const compareData: CompareData[] = [];

  if (ids.length > 0) {
    try {
      if (type === "journalists") {
        const results = await Promise.all(
          ids.slice(0, 4).map(async (id) => {
            try {
              const [journalist, history] = await Promise.all([
                getJournalist(id),
                getJournalistHistory(id),
              ]);
              return { journalist, history };
            } catch {
              return null;
            }
          })
        );

        for (const result of results) {
          if (result) {
            const criticScore = result.journalist.stats?.avg_score_given ?? null;
            const steamScore = deriveSourceScoreFromDisparity(
              criticScore,
              result.journalist.stats?.overall_disparity_steam ?? result.journalist.stats?.avg_disparity_steam
            );
            const metacriticScore = deriveSourceScoreFromDisparity(
              criticScore,
              result.journalist.stats?.overall_disparity_metacritic ?? result.journalist.stats?.avg_disparity_metacritic
            );
            const combinedDisparity = result.journalist.stats?.overall_disparity_combined
              ?? result.journalist.avg_disparity
              ?? result.journalist.stats?.avg_disparity_combined;
            compareData.push({
              id: result.journalist.id,
              name: result.journalist.name,
              image_url: result.journalist.image_url,
              review_count: result.journalist.review_count,
              avg_disparity: combinedDisparity,
              avg_score: criticScore,
              steam_user_score: steamScore,
              steam_current_players: null,
              steam_player_24h_peak: null,
              steam_player_24h_low_observed: null,
              steam_player_all_time_peak: null,
              steam_achievement_count: null,
              metacritic_user_score: metacriticScore,
              player_count_trend: [],
              history: result.history,
              linkHref: buildEntityPath("journalists", result.journalist.name, result.journalist.public_id),
            });
          }
        }
      } else if (type === "outlets") {
        const results = await Promise.all(
          ids.slice(0, 4).map(async (id) => {
            try {
              const [outlet, history] = await Promise.all([
                getOutlet(id),
                getOutletHistory(id),
              ]);
              return { outlet, history };
            } catch {
              return null;
            }
          })
        );

        for (const result of results) {
          if (result) {
            const criticScore = result.outlet.avg_score ?? null;
            const steamScore = deriveSourceScoreFromDisparity(criticScore, result.outlet.avg_disparity_steam);
            const metacriticScore = deriveSourceScoreFromDisparity(criticScore, result.outlet.avg_disparity_metacritic);
            const combinedDisparity = result.outlet.avg_disparity_combined ?? result.outlet.avg_disparity ?? null;
            compareData.push({
              id: result.outlet.id,
              name: result.outlet.name,
              image_url: result.outlet.logo_url,
              review_count: result.outlet.review_count ?? 0,
              avg_disparity: combinedDisparity,
              avg_score: criticScore,
              steam_user_score: steamScore,
              steam_current_players: null,
              steam_player_24h_peak: null,
              steam_player_24h_low_observed: null,
              steam_player_all_time_peak: null,
              steam_achievement_count: null,
              metacritic_user_score: metacriticScore,
              player_count_trend: [],
              history: result.history,
              linkHref: buildEntityPath("outlets", result.outlet.name, result.outlet.public_id),
            });
          }
        }
      } else if (type === "games") {
        const results = await Promise.all(
          ids.slice(0, 4).map(async (id) => {
            try {
              const [game, history, steamActivity] = await Promise.all([
                getGame(id),
                getGameHistory(id),
                getGameSteamActivity(id, COMPARE_PLAYER_TREND_LIMIT).catch(() => null),
              ]);
              return { game, history, steamActivity };
            } catch {
              return null;
            }
          })
        );

        for (const result of results) {
          if (result) {
            const latestPlayerPoint = result.steamActivity?.points.length
              ? result.steamActivity.points[result.steamActivity.points.length - 1]
              : null;
            compareData.push({
              id: result.game.id,
              name: result.game.title,
              image_url: result.game.image_url,
              review_count: result.game.critic_review_count ?? 0,
              avg_disparity: getDisplayDisparity(
                result.game.disparity_steam,
                result.game.disparity_metacritic
              ),
              avg_score: result.game.avg_critic_score ?? null,
              steam_user_score: result.game.steam_user_score ?? null,
              steam_current_players: latestPlayerPoint?.latest_players
                ?? result.steamActivity?.summary.steam_current_players
                ?? result.game.steam_current_players
                ?? null,
              steam_player_24h_peak: result.steamActivity?.summary.steam_player_24h_peak
                ?? result.game.steam_player_24h_peak
                ?? null,
              steam_player_24h_low_observed: result.steamActivity?.summary.steam_player_24h_low_observed
                ?? result.game.steam_player_24h_low_observed
                ?? null,
              steam_player_all_time_peak: result.steamActivity?.summary.steam_player_all_time_peak
                ?? result.game.steam_player_all_time_peak
                ?? null,
              steam_achievement_count: result.game.steam_achievement_count ?? null,
              metacritic_user_score: result.game.metacritic_user_score ?? null,
              player_count_trend: result.steamActivity
                ? toPlayerCountTrend(result.steamActivity.points)
                : [],
              history: result.history,
              linkHref: buildEntityPath("games", result.game.title, result.game.public_id),
            });
          }
        }
      }
    } catch (error) {
      console.error("Error fetching compare data:", error);
    }
  }

  // Brand colors for comparison charts
  const colors = ["#BB3B0E", "#DD7631", "#708160", "#D8C593"];
  const compareIds = ids;
  const comparedNames = compareData.slice(0, 4).map((item) => item.name);
  const shareUrl = buildCompareShareUrl(getSiteUrl(), {
    type,
    card: "v7",
    ids: compareIds,
    labels: comparedNames,
    metrics: selectedMetricIds,
    snapshotPayload: compareData.length > 0 ? buildCompareSnapshotPayload(compareData) : undefined,
  });
  const shareText = comparedNames.length > 0
    ? type === "games"
      ? `Compare ${comparedNames.join(" vs ")} on Review Disparity — critic, user score, and Steam player-count trends`
      : `Compare ${comparedNames.join(" vs ")} on Review Disparity`
    : `Compare ${type} on Review Disparity`;
  const compareTitleLabel = type === "journalists"
    ? "Journalists"
    : type === "outlets"
      ? "Outlets"
      : "Games";
  const compareColumnWidthClass = compareData.length === 1
    ? "w-[36rem] min-w-[36rem]"
    : compareData.length === 2
      ? "w-[24rem] min-w-[24rem]"
      : compareData.length === 3
        ? "w-[18rem] min-w-[18rem]"
        : "w-[14rem] min-w-[14rem]";
  const mobileMetricCardStyle = {
    borderColor: "var(--border)",
    background: "linear-gradient(180deg, var(--background-card-strong), var(--background-card))",
    boxShadow: "var(--shadow-soft)",
  };
  const mobileCompareItemStyle = {
    borderColor: "color-mix(in srgb, var(--border) 82%, transparent)",
    backgroundColor: "color-mix(in srgb, var(--background-card-strong) 72%, transparent)",
  };
  const renderMobileCompareIdentity = (item: CompareData, index: number) => (
    <div className="flex min-w-0 items-center gap-3">
      {item.image_url ? (
        type === "games" ? (
          <GameAvatar
            title={item.name}
            imageUrl={item.image_url}
            width={52}
            height={30}
            sizes="52px"
            className="h-[1.875rem] w-[3.25rem] rounded-lg object-contain"
          />
        ) : (
          <Image
            src={item.image_url}
            alt={item.name}
            width={36}
            height={36}
            sizes="36px"
            className="h-9 w-9 rounded-full object-cover"
          />
        )
      ) : (
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-medium text-white"
          style={{ backgroundColor: colors[index] }}
        >
          {item.name.charAt(0)}
        </div>
      )}
      <Link
        href={item.linkHref}
        className="block truncate text-sm font-medium transition-colors hover:opacity-80"
        style={{ color: "var(--foreground)" }}
      >
        {item.name}
      </Link>
    </div>
  );
  const renderMobileValueEntry = (item: CompareData, index: number, value: ReactNode) => (
    <div
      key={item.id}
      className="rounded-[1.25rem] border px-3 py-3"
      style={mobileCompareItemStyle}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          {renderMobileCompareIdentity(item, index)}
        </div>
        <div className="shrink-0">
          {value}
        </div>
      </div>
    </div>
  );
  const renderMobileChartEntry = (item: CompareData, index: number, chart: ReactNode) => (
    <div
      key={item.id}
      className="rounded-[1.25rem] border px-3 py-3"
      style={mobileCompareItemStyle}
    >
      <div className="mb-3 min-w-0">
        {renderMobileCompareIdentity(item, index)}
      </div>
      {chart}
    </div>
  );
  const renderMetricControlCell = (metricId: Parameters<typeof CompareMetricRowToggle>[0]["metricId"], label: string, description?: string) => (
    <td className="px-4 py-4 align-top text-sm font-medium text-gray-700">
      <div className="flex items-start gap-4">
        <CompareMetricRowToggle
          type={type}
          metricId={metricId}
          label={label}
          selectedMetricIds={selectedMetricIds}
        />
        <div className="min-w-0 pt-0.5">
          <div>{label}</div>
          {description ? (
            <div className="mt-1 text-xs font-normal text-gray-500">
              {description}
            </div>
          ) : null}
        </div>
      </div>
    </td>
  );
  const renderMobileMetricSection = (
    metricId: Parameters<typeof CompareMetricRowToggle>[0]["metricId"],
    label: string,
    content: ReactNode,
    description?: string
  ) => {
    if (!selectedMetricSet.has(metricId)) {
      return null;
    }

    return (
      <section
        key={metricId}
        className="overflow-hidden rounded-[1.5rem] border lg:hidden"
        style={mobileMetricCardStyle}
      >
        <div
          className="flex items-start gap-3 px-4 py-4"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <CompareMetricRowToggle
            type={type}
            metricId={metricId}
            label={label}
            selectedMetricIds={selectedMetricIds}
          />
          <div className="min-w-0">
            <div className="text-sm font-semibold text-gray-900">{label}</div>
            {description ? (
              <div className="mt-1 text-xs text-gray-500">
                {description}
              </div>
            ) : null}
          </div>
        </div>
        <div className="space-y-3 p-3">
          {content}
        </div>
      </section>
    );
  };

  return (
    <div className="space-y-6">
      <section className="space-y-5 py-2 text-center">
        <div className="mx-auto max-w-4xl space-y-4">
          <h1
            className="route-hero-title mx-auto"
          >
            Stack up the same entities on one view
          </h1>
          <p
            className="mx-auto max-w-4xl text-lg leading-8 sm:text-xl"
            style={{ color: "var(--foreground-muted)" }}
          >
            Compare up to four {compareTypeLabel[type]} side by side, including disparity,
            {type === "games"
              ? " critic and user scores, Steam player counts, and recent trend direction."
              : " score baselines, review volume, and recent trend direction."}
          </p>
        </div>
      </section>

      {/* Tab Navigation */}
      <div className="flex justify-center">
        <nav className="site-tab-nav">
          {tabs.map((t) => (
            <Link
              key={t.id}
              href={`/compare?type=${t.id}`}
              scroll={false}
              data-no-nav-progress="true"
              className={`site-tab-link${type === t.id ? " site-tab-link--active" : ""}`}
            >
              {t.label}
            </Link>
          ))}
        </nav>
      </div>

      {/* Selector */}
      <div className="route-header relative z-20 overflow-visible">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <span className="site-data-label">Selection</span>
            <h2 className="mt-2 text-xl font-semibold text-gray-900">
              Select {compareTitleLabel} to compare
            </h2>
          </div>
          {compareData.length > 0 && (
            <ShareButtons url={shareUrl} text={shareText} />
          )}
        </div>
        <Suspense fallback={<CompareSelectorFallback />}>
          <CompareSelector
            type={type}
            selectedIds={ids}
            selectedItems={compareData.map((item) => ({
              id: item.id,
              name: item.name,
              image_url: item.image_url,
            }))}
            maxSelections={4}
          />
        </Suspense>
      </div>

      {/* Comparison Grid */}
      {compareData.length > 0 ? (
        <div className="space-y-4">
          <CompareMetricControls type={type} selectedMetricIds={selectedMetricIds} />
          <div className="space-y-3 lg:hidden">
            {renderMobileMetricSection(
              "avg_disparity",
              "Avg Disparity",
              compareData.map((item, index) => renderMobileValueEntry(
                item,
                index,
                <div className="flex justify-end">
                  <DisparityBadge disparity={item.avg_disparity} />
                </div>
              ))
            )}

            {type !== "games" && renderMobileMetricSection(
              "review_count",
              "Total Reviews",
              compareData.map((item, index) => renderMobileValueEntry(
                item,
                index,
                <div className="text-right text-lg font-semibold text-gray-900">
                  {item.review_count.toLocaleString()}
                </div>
              ))
            )}

            {renderMobileMetricSection(
              "avg_score",
              type === "games" ? "Avg Critic Score" : "Avg Score Given",
              compareData.map((item, index) => renderMobileValueEntry(
                item,
                index,
                <div className="text-right text-lg font-semibold text-gray-900">
                  {item.avg_score != null ? Number(item.avg_score).toFixed(1) : "N/A"}
                </div>
              ))
            )}

            {type === "games" && renderMobileMetricSection(
              "steam_user_score",
              "Steam User Score",
              compareData.map((item, index) => renderMobileValueEntry(
                item,
                index,
                <div className="text-right text-lg font-semibold text-gray-900">
                  {item.steam_user_score != null ? Number(item.steam_user_score).toFixed(1) : "N/A"}
                </div>
              ))
            )}

            {type === "games" && renderMobileMetricSection(
              "metacritic_user_score",
              "Metacritic User Score",
              compareData.map((item, index) => renderMobileValueEntry(
                item,
                index,
                <div className="text-right text-lg font-semibold text-gray-900">
                  {item.metacritic_user_score != null ? Number(item.metacritic_user_score).toFixed(1) : "N/A"}
                </div>
              ))
            )}

            {type === "games" && renderMobileMetricSection(
              "current_players",
              "Current Player Count",
              compareData.map((item, index) => renderMobileValueEntry(
                item,
                index,
                <div className="text-right text-lg font-semibold text-gray-900">
                  {formatPlayerCount(item.steam_current_players)}
                </div>
              ))
            )}

            {type === "games" && renderMobileMetricSection(
              "all_time_peak_players",
              "All-Time Peak Player Count",
              compareData.map((item, index) => renderMobileValueEntry(
                item,
                index,
                <div className="text-right text-lg font-semibold text-gray-900">
                  {formatPlayerCount(item.steam_player_all_time_peak)}
                </div>
              ))
            )}

            {type === "games" && renderMobileMetricSection(
              "player_count_trend",
              "Player Count Trend",
              compareData.map((item, index) => renderMobileChartEntry(
                item,
                index,
                item.player_count_trend.length > 1 ? (
                  <MiniPlayerCountChart
                    values={item.player_count_trend}
                    color={colors[index]}
                    className="w-full"
                    ariaLabel={`${item.name} player count trend`}
                  />
                ) : (
                  <div
                    className="flex h-20 items-center justify-center rounded-xl border border-dashed text-sm text-gray-400"
                    style={{ borderColor: "var(--border)" }}
                  >
                    N/A
                  </div>
                )
              )),
              "Recent hourly current-player trend with the latest value shown above"
            )}

            {renderMobileMetricSection(
              "disparity_trend",
              "Disparity Trend",
              compareData.map((item, index) => renderMobileChartEntry(
                item,
                index,
                <MiniDisparityChart
                  data={item.history}
                  color={colors[index]}
                  height={88}
                />
              )),
              "Combined disparity over time"
            )}
          </div>

          <div className="hidden lg:inline-block lg:max-w-full lg:align-top site-table-wrap">
            <div>
              <table className="site-table" style={{ width: "max-content" }}>
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 w-[18rem] min-w-[18rem]">
                      Metric
                    </th>
                    {compareData.map((item, index) => (
                      <th
                        key={item.id}
                        className={`px-4 py-3 text-center text-sm font-medium text-gray-900 ${compareColumnWidthClass}`}
                      >
                        <div className="flex flex-col items-center gap-2">
                          {item.image_url ? (
                            type === "games" ? (
                              <GameAvatar
                                title={item.name}
                                imageUrl={item.image_url}
                                width={72}
                                height={40}
                                sizes="72px"
                                className="h-10 w-[4.5rem] rounded-xl object-contain"
                              />
                            ) : (
                              <Image
                                src={item.image_url}
                                alt={item.name}
                                width={48}
                                height={48}
                                sizes="48px"
                                className="w-12 h-12 rounded-full object-cover"
                              />
                            )
                          ) : (
                            <div
                              className="w-12 h-12 rounded-full flex items-center justify-center text-white font-medium"
                              style={{ backgroundColor: colors[index] }}
                            >
                              {item.name.charAt(0)}
                            </div>
                          )}
                          <Link
                            href={item.linkHref}
                            className="transition-colors hover:opacity-80"
                            style={{ color: "var(--color-rust)" }}
                          >
                            {item.name}
                          </Link>
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                {/* Disparity Row */}
                {selectedMetricSet.has("avg_disparity") && (
                  <tr>
                    {renderMetricControlCell("avg_disparity", "Avg Disparity")}
                    {compareData.map((item) => (
                      <td key={item.id} className="px-4 py-4 text-center">
                        <div className="flex justify-center">
                          <DisparityBadge disparity={item.avg_disparity} />
                        </div>
                      </td>
                    ))}
                  </tr>
                )}

                {/* Review Count Row */}
                {type !== "games" && selectedMetricSet.has("review_count") && (
                  <tr>
                    {renderMetricControlCell("review_count", "Total Reviews")}
                    {compareData.map((item) => (
                      <td
                        key={item.id}
                        className="px-4 py-4 text-center text-gray-900 font-medium"
                      >
                        {item.review_count.toLocaleString()}
                      </td>
                    ))}
                  </tr>
                )}

                {/* Avg Score Row */}
                {selectedMetricSet.has("avg_score") && (
                  <tr>
                    {renderMetricControlCell("avg_score", type === "games" ? "Avg Critic Score" : "Avg Score Given")}
                    {compareData.map((item) => (
                      <td
                        key={item.id}
                        className="px-4 py-4 text-center text-gray-900 font-medium"
                      >
                        {item.avg_score != null
                          ? Number(item.avg_score).toFixed(1)
                          : "N/A"}
                      </td>
                    ))}
                  </tr>
                )}

                {/* Steam Score Row (games only) */}
                {type === "games" && selectedMetricSet.has("steam_user_score") && (
                  <tr>
                    {renderMetricControlCell("steam_user_score", "Steam User Score")}
                    {compareData.map((item) => (
                      <td
                        key={item.id}
                        className="px-4 py-4 text-center text-gray-900 font-medium"
                      >
                        {item.steam_user_score != null
                          ? Number(item.steam_user_score).toFixed(1)
                          : "N/A"}
                      </td>
                    ))}
                  </tr>
                )}

                {type === "games" && selectedMetricSet.has("metacritic_user_score") && (
                  <tr>
                    {renderMetricControlCell("metacritic_user_score", "Metacritic User Score")}
                    {compareData.map((item) => (
                      <td
                        key={item.id}
                        className="px-4 py-4 text-center text-gray-900 font-medium"
                      >
                        {item.metacritic_user_score != null
                          ? Number(item.metacritic_user_score).toFixed(1)
                          : "N/A"}
                      </td>
                    ))}
                  </tr>
                )}

                {type === "games" && selectedMetricSet.has("current_players") && (
                  <tr>
                    {renderMetricControlCell("current_players", "Current Player Count")}
                    {compareData.map((item) => (
                      <td
                        key={item.id}
                        className="px-4 py-4 text-center text-gray-900 font-medium"
                      >
                        {formatPlayerCount(item.steam_current_players)}
                      </td>
                    ))}
                  </tr>
                )}

                {type === "games" && selectedMetricSet.has("all_time_peak_players") && (
                  <tr>
                    {renderMetricControlCell("all_time_peak_players", "All-Time Peak Player Count")}
                    {compareData.map((item) => (
                      <td
                        key={item.id}
                        className="px-4 py-4 text-center text-gray-900 font-medium"
                      >
                        {formatPlayerCount(item.steam_player_all_time_peak)}
                      </td>
                    ))}
                  </tr>
                )}

                {type === "games" && selectedMetricSet.has("player_count_trend") && (
                  <tr>
                    {renderMetricControlCell(
                      "player_count_trend",
                      "Player Count Trend",
                      "Recent hourly current-player trend with the latest value shown above"
                    )}
                    {compareData.map((item, index) => (
                      <td key={item.id} className="px-4 py-4">
                        {item.player_count_trend.length > 1 ? (
                          <MiniPlayerCountChart
                            values={item.player_count_trend}
                            color={colors[index]}
                            className="w-full"
                            ariaLabel={`${item.name} player count trend`}
                          />
                        ) : (
                          <div className="flex h-20 items-center justify-center rounded-xl border border-dashed text-sm text-gray-400" style={{ borderColor: "var(--border)" }}>
                            N/A
                          </div>
                        )}
                      </td>
                    ))}
                  </tr>
                )}

                {/* Trend Chart Row */}
                {selectedMetricSet.has("disparity_trend") && (
                  <tr>
                    {renderMetricControlCell("disparity_trend", "Disparity Trend", "Combined disparity over time")}
                    {compareData.map((item, index) => (
                      <td key={item.id} className="px-4 py-4">
                        <MiniDisparityChart
                          data={item.history}
                          color={colors[index]}
                          height={100}
                        />
                      </td>
                    ))}
                  </tr>
                )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : ids.length > 0 ? (
        <div className="site-empty">
          <p className="text-gray-600">
            Unable to load comparison data. Please try again.
          </p>
        </div>
      ) : (
        <div className="site-empty">
          <p className="text-gray-500">
            Select up to 4 {type === "journalists" ? "journalists" : type === "outlets" ? "outlets" : "games"} to
            compare their disparity metrics side by side.
          </p>
        </div>
      )}
    </div>
  );
}

function CompareSelectorFallback() {
  return (
    <div className="space-y-4" aria-busy="true">
      <div className="h-10 w-full rounded-lg bg-gray-100 animate-pulse" />
      <div className="flex flex-wrap gap-2">
        <div className="h-8 w-24 rounded-full bg-gray-100 animate-pulse" />
        <div className="h-8 w-28 rounded-full bg-gray-100 animate-pulse" />
      </div>
    </div>
  );
}
