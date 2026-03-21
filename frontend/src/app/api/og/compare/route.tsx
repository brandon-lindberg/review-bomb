import { ImageResponse } from "next/og";
import { getGame, getGameHistory, getGameSteamActivity, getJournalist, getJournalistHistory, getOutlet, getOutletHistory } from "@/lib/api";
import { parseCompareMetricSelection } from "@/lib/compare-metrics";
import { formatDisparity, getDisparityColor, getDisplayDisparity } from "@/lib/disparity-colors";
import { buildSparklinePath, formatCompactPlayerCount, toPlayerCountTrend } from "@/lib/player-count-chart";
import { deriveSourceScoreFromDisparity } from "@/lib/share-snapshot";
import type { DisparitySnapshot } from "@/types";

export const revalidate = 300;
export const dynamic = "force-dynamic";

const IMAGE_WIDTH = 1200;
const IMAGE_HEIGHT = 630;
const COMPARE_PLAYER_TREND_LIMIT = 72;

type CompareType = "journalists" | "outlets" | "games";

interface SnapshotItem {
  id: number;
  name: string;
  disparity: number | null;
  reviewCount: number | null;
  criticScore: number | null;
  steamScore: number | null;
  metacriticScore: number | null;
  currentPlayers: number | null;
  playerPeak24h: number | null;
  playerLow24h: number | null;
  playerAllTimePeak: number | null;
  achievementCount: number | null;
  playerTrend: number[];
  trend: number[];
}

interface SnapshotPayloadItem {
  n?: unknown;
  c?: unknown;
  s?: unknown;
  m?: unknown;
  d?: unknown;
  r?: unknown;
  t?: unknown;
  p?: unknown;
  h?: unknown;
  l?: unknown;
  a?: unknown;
  ac?: unknown;
  pt?: unknown;
}

const avatarColors = ["#BB3B0E", "#DD7631", "#708160", "#D8C593"];

interface CompareCardLayout {
  gap: number;
  cardPadding: string;
  avatarSize: number;
  avatarFontSize: number;
  titleFontSize: number;
  titleMaxWidth: number;
  titleChars: number;
  metricLabelFontSize: number;
  metricValueFontSize: number;
  panelLabelFontSize: number;
  chartWidth: number;
  chartHeight: number;
}

function getCompareCardLayout(itemCount: number): CompareCardLayout {
  if (itemCount <= 2) {
    return {
      gap: 24,
      cardPadding: "22px 22px 18px",
      avatarSize: 50,
      avatarFontSize: 24,
      titleFontSize: 31,
      titleMaxWidth: 360,
      titleChars: 28,
      metricLabelFontSize: 17,
      metricValueFontSize: 26,
      panelLabelFontSize: 15,
      chartWidth: 320,
      chartHeight: 68,
    };
  }

  if (itemCount === 3) {
    return {
      gap: 18,
      cardPadding: "20px 18px 16px",
      avatarSize: 46,
      avatarFontSize: 23,
      titleFontSize: 28,
      titleMaxWidth: 280,
      titleChars: 24,
      metricLabelFontSize: 16,
      metricValueFontSize: 24,
      panelLabelFontSize: 14,
      chartWidth: 260,
      chartHeight: 62,
    };
  }

  return {
    gap: 16,
    cardPadding: "18px 18px 16px",
    avatarSize: 42,
    avatarFontSize: 22,
    titleFontSize: 27,
    titleMaxWidth: 220,
    titleChars: 22,
    metricLabelFontSize: 16,
    metricValueFontSize: 22,
    panelLabelFontSize: 14,
    chartWidth: 220,
    chartHeight: 58,
  };
}

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

function getTypeLabel(type: CompareType): string {
  if (type === "journalists") return "journalists";
  if (type === "outlets") return "outlets";
  return "games";
}

function truncate(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 1)}…`;
}

function formatScore(value: number | null): string {
  if (value == null) return "N/A";
  return Number(value).toFixed(0);
}

function formatReviewCount(value: number | null): string {
  if (value == null) return "N/A";
  return value.toLocaleString();
}

function parseLabels(rawLabels?: string | null): string[] {
  if (!rawLabels) return [];
  return rawLabels
    .split("|")
    .map((label) => label.trim())
    .filter((label) => label.length > 0)
    .slice(0, 4);
}

function parseOptionalNumber(rawValue: unknown): number | null {
  if (rawValue == null) return null;
  const parsed = Number(rawValue);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseTrendSnapshot(rawValue: unknown): number[] {
  if (!Array.isArray(rawValue)) return [];
  return rawValue
    .map((value) => {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? Number(parsed.toFixed(1)) : null;
    })
    .filter((value): value is number => value != null)
    .slice(-16);
}

function toTrendSnapshot(history: DisparitySnapshot[]): number[] {
  if (!history || history.length === 0) return [];
  const points = history
    .map((snapshot) => {
      const combined = snapshot.avg_disparity_combined != null
        ? Number(snapshot.avg_disparity_combined)
        : snapshot.avg_disparity_steam != null && snapshot.avg_disparity_metacritic != null
          ? (Number(snapshot.avg_disparity_steam) + Number(snapshot.avg_disparity_metacritic)) / 2
          : snapshot.avg_disparity_steam ?? snapshot.avg_disparity_metacritic ?? null;
      if (combined == null || !Number.isFinite(Number(combined))) return null;
      return Number(Number(combined).toFixed(1));
    })
    .filter((value): value is number => value != null);
  return points.slice(-16);
}

function parseSnapshotPayload(rawSnapshot?: string | null): SnapshotItem[] {
  if (!rawSnapshot) return [];

  try {
    const parsed = JSON.parse(rawSnapshot);
    if (!Array.isArray(parsed)) return [];

    const items: SnapshotItem[] = [];
    for (let index = 0; index < parsed.length && items.length < 4; index += 1) {
      const rawItem = parsed[index] as SnapshotPayloadItem;
      const name = typeof rawItem?.n === "string" ? rawItem.n.trim() : "";
      if (!name) continue;
      items.push({
        id: index + 1,
        name,
        criticScore: parseOptionalNumber(rawItem.c),
        steamScore: parseOptionalNumber(rawItem.s),
        metacriticScore: parseOptionalNumber(rawItem.m),
        disparity: parseOptionalNumber(rawItem.d),
        reviewCount: parseOptionalNumber(rawItem.r),
        currentPlayers: parseOptionalNumber(rawItem.p),
        playerPeak24h: parseOptionalNumber(rawItem.h),
        playerLow24h: parseOptionalNumber(rawItem.l),
        playerAllTimePeak: parseOptionalNumber(rawItem.a),
        achievementCount: parseOptionalNumber(rawItem.ac),
        playerTrend: parseTrendSnapshot(rawItem.pt),
        trend: parseTrendSnapshot(rawItem.t),
      });
    }

    return items;
  } catch {
    return [];
  }
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T | null> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), ms);
    promise
      .then((value) => resolve(value))
      .catch(() => resolve(null))
      .finally(() => clearTimeout(timer));
  });
}

function buildTrendPolyline(points: number[], width: number, height: number): string {
  if (points.length === 0) return "";
  const pad = 6;
  const chartWidth = width - pad * 2;
  const chartHeight = height - pad * 2;
  const min = Math.min(...points, 0);
  const max = Math.max(...points, 0);
  const span = Math.max(max - min, 1);
  return points
    .map((value, index) => {
      const x = pad + (index / Math.max(points.length - 1, 1)) * chartWidth;
      const y = pad + (1 - (value - min) / span) * chartHeight;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function zeroBaselineY(points: number[], height: number): number {
  const pad = 6;
  const chartHeight = height - pad * 2;
  const min = Math.min(...points, 0);
  const max = Math.max(...points, 0);
  const span = Math.max(max - min, 1);
  return pad + (1 - (0 - min) / span) * chartHeight;
}

async function getSnapshotItems(type: CompareType, ids: number[]): Promise<SnapshotItem[]> {
  if (ids.length === 0) return [];

  if (type === "journalists") {
    const results: Array<SnapshotItem | null> = await Promise.all(ids.map(async (id): Promise<SnapshotItem | null> => {
      try {
        const [journalist, history] = await Promise.all([
          getJournalist(id),
          getJournalistHistory(id, 180),
        ]);
        const criticScore = journalist.stats?.avg_score_given ?? null;
        const steamScore = deriveSourceScoreFromDisparity(
          criticScore,
          journalist.stats?.overall_disparity_steam ?? journalist.stats?.avg_disparity_steam
        );
        const metacriticScore = deriveSourceScoreFromDisparity(
          criticScore,
          journalist.stats?.overall_disparity_metacritic ?? journalist.stats?.avg_disparity_metacritic
        );
        const combinedDisparity = journalist.stats?.overall_disparity_combined
          ?? journalist.avg_disparity
          ?? journalist.stats?.avg_disparity_combined;

        return {
          id: journalist.id,
          name: journalist.name,
          disparity: combinedDisparity,
          reviewCount: journalist.review_count,
          criticScore,
          steamScore,
          metacriticScore,
          currentPlayers: null,
          playerPeak24h: null,
          playerLow24h: null,
          playerAllTimePeak: null,
          achievementCount: null,
          playerTrend: [],
          trend: toTrendSnapshot(history),
        };
      } catch {
        return null;
      }
    }));

    return results.filter((item): item is SnapshotItem => item != null);
  }

  if (type === "outlets") {
    const results: Array<SnapshotItem | null> = await Promise.all(ids.map(async (id): Promise<SnapshotItem | null> => {
      try {
        const [outlet, history] = await Promise.all([
          getOutlet(id),
          getOutletHistory(id, 180),
        ]);
        const criticScore = outlet.avg_score ?? null;
        const steamScore = deriveSourceScoreFromDisparity(criticScore, outlet.avg_disparity_steam);
        const metacriticScore = deriveSourceScoreFromDisparity(criticScore, outlet.avg_disparity_metacritic);
        const combinedDisparity = outlet.avg_disparity_combined ?? outlet.avg_disparity ?? null;

        return {
          id: outlet.id,
          name: outlet.name,
          disparity: combinedDisparity,
          reviewCount: outlet.review_count ?? 0,
          criticScore,
          steamScore,
          metacriticScore,
          currentPlayers: null,
          playerPeak24h: null,
          playerLow24h: null,
          playerAllTimePeak: null,
          achievementCount: null,
          playerTrend: [],
          trend: toTrendSnapshot(history),
        };
      } catch {
        return null;
      }
    }));

    return results.filter((item): item is SnapshotItem => item != null);
  }

  const results: Array<SnapshotItem | null> = await Promise.all(ids.map(async (id): Promise<SnapshotItem | null> => {
    try {
      const [game, history, steamActivity] = await Promise.all([
        getGame(id),
        getGameHistory(id, 180),
        getGameSteamActivity(id, COMPARE_PLAYER_TREND_LIMIT).catch(() => null),
      ]);
      const latestPoint = steamActivity?.points.length
        ? steamActivity.points[steamActivity.points.length - 1]
        : null;
      return {
        id: game.id,
        name: game.title,
        disparity: getDisplayDisparity(game.disparity_steam, game.disparity_metacritic),
        reviewCount: game.critic_review_count ?? 0,
        criticScore: game.avg_critic_score ?? null,
        steamScore: game.steam_user_score ?? null,
        metacriticScore: game.metacritic_user_score ?? null,
        currentPlayers: latestPoint?.latest_players
          ?? steamActivity?.summary.steam_current_players
          ?? game.steam_current_players
          ?? null,
        playerPeak24h: steamActivity?.summary.steam_player_24h_peak
          ?? game.steam_player_24h_peak
          ?? null,
        playerLow24h: steamActivity?.summary.steam_player_24h_low_observed
          ?? game.steam_player_24h_low_observed
          ?? null,
        playerAllTimePeak: steamActivity?.summary.steam_player_all_time_peak
          ?? game.steam_player_all_time_peak
          ?? null,
        achievementCount: game.steam_achievement_count ?? null,
        playerTrend: steamActivity ? toPlayerCountTrend(steamActivity.points) : [],
        trend: toTrendSnapshot(history),
      };
    } catch {
      return null;
    }
  }));

  return results.filter((item): item is SnapshotItem => item != null);
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const type = normalizeCompareType(searchParams.get("type") ?? undefined);
    const ids = parseCompareIds(searchParams.get("ids") ?? undefined);
    const labels = parseLabels(searchParams.get("labels"));
    const selectedMetricIds = parseCompareMetricSelection(type, searchParams.get("metrics"));
    const selectedMetricSet = new Set(selectedMetricIds);
    const snapshotItems = parseSnapshotPayload(searchParams.get("snap"));

    const quickItems: SnapshotItem[] = ids.map((id, index) => ({
      id,
      name: labels[index] ?? `Item ${index + 1}`,
      disparity: null,
      reviewCount: null,
      criticScore: null,
      steamScore: null,
      metacriticScore: null,
      currentPlayers: null,
      playerPeak24h: null,
      playerLow24h: null,
      playerAllTimePeak: null,
      achievementCount: null,
      playerTrend: [],
      trend: [],
    }));

    const loadedItems = snapshotItems.length > 0
      ? snapshotItems
      : ids.length > 0
        ? await withTimeout(getSnapshotItems(type, ids), 1800)
        : [];

    const merged = (loadedItems ?? []).map((item, index) => ({
      ...item,
      name: labels[index] ?? item.name,
      id: ids[index] ?? item.id,
    }));

    const items = merged.length > 0 ? merged : quickItems;
    const typeLabel = getTypeLabel(type);
    const cardLayout = getCompareCardLayout(items.length);
    const title = items.length > 0
      ? `Compare ${items.map((item) => truncate(item.name, 20)).join(" vs ")}`
      : `Compare ${typeLabel}`;

    return new ImageResponse(
      (
        <div
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            flexDirection: "column",
            padding: "42px 48px",
            color: "#F7F2E7",
            background: "linear-gradient(135deg, #161310 0%, #2A211A 55%, #1D1A17 100%)",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              gap: 16,
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", fontSize: 28, color: "#D8C593", fontWeight: 700 }}>
                ReviewDisparity
              </div>
              <div
                style={{
                  display: "flex",
                  fontSize: 50,
                  fontWeight: 800,
                  lineHeight: 1.05,
                  maxWidth: 980,
                }}
              >
                {title}
              </div>
            </div>
            <div style={{ display: "flex", fontSize: 22, color: "#B8AFA3", marginTop: 6 }}>
              {items.length > 0 ? `${items.length} selected` : "Share a live comparison"}
            </div>
          </div>

          <div style={{ display: "flex", gap: cardLayout.gap, marginTop: 26, flex: 1 }}>
            {items.length > 0 ? (
              items.map((item, index) => (
                (() => {
                  const hasPlayerData = type === "games" && (
                    item.currentPlayers != null
                    || item.playerAllTimePeak != null
                    || item.playerTrend.length > 1
                  );
                  const metricRows = [
                    selectedMetricSet.has("avg_disparity") ? {
                      label: "Combined disparity",
                      value: formatDisparity(item.disparity),
                      color: getDisparityColor(item.disparity),
                    } : null,
                    selectedMetricSet.has("avg_score") ? {
                      label: "Critic score",
                      value: formatScore(item.criticScore),
                      color: "#F7F2E7",
                    } : null,
                    selectedMetricSet.has("steam_user_score") ? {
                      label: "Steam score",
                      value: formatScore(item.steamScore),
                      color: "#F7F2E7",
                    } : null,
                    selectedMetricSet.has("metacritic_user_score") ? {
                      label: "Metacritic score",
                      value: formatScore(item.metacriticScore),
                      color: "#F7F2E7",
                    } : null,
                    type === "games" && selectedMetricSet.has("current_players") ? {
                      label: "Current players",
                      value: formatCompactPlayerCount(item.currentPlayers),
                      color: "#F7F2E7",
                    } : null,
                    type === "games" && selectedMetricSet.has("all_time_peak_players") ? {
                      label: "All-time peak",
                      value: formatCompactPlayerCount(item.playerAllTimePeak),
                      color: "#F7F2E7",
                    } : null,
                    selectedMetricSet.has("review_count") ? {
                      label: "Total reviews",
                      value: formatReviewCount(item.reviewCount),
                      color: "#F7F2E7",
                    } : null,
                  ].filter((row): row is { label: string; value: string; color: string } => row != null);
                  const playerTrendPath = item.playerTrend.length > 1
                    ? buildSparklinePath(item.playerTrend, cardLayout.chartWidth, cardLayout.chartHeight, 6)
                    : "";

                  return (
                    <div
                      key={`${item.id}-${index}`}
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        flex: 1,
                        borderRadius: 18,
                        padding: cardLayout.cardPadding,
                        backgroundColor: "rgba(255, 255, 255, 0.08)",
                        border: "1px solid rgba(255, 255, 255, 0.18)",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div
                          style={{
                            display: "flex",
                            width: cardLayout.avatarSize,
                            height: cardLayout.avatarSize,
                            borderRadius: 999,
                            alignItems: "center",
                            justifyContent: "center",
                            backgroundColor: avatarColors[index % avatarColors.length],
                            color: "#F8F8F8",
                            fontWeight: 700,
                            fontSize: cardLayout.avatarFontSize,
                          }}
                        >
                          {item.name.charAt(0).toUpperCase()}
                        </div>
                        <div
                          style={{
                            display: "flex",
                            fontSize: cardLayout.titleFontSize,
                            fontWeight: 700,
                            lineHeight: 1.05,
                            maxWidth: cardLayout.titleMaxWidth,
                          }}
                        >
                          {truncate(item.name, cardLayout.titleChars)}
                        </div>
                      </div>

                      <div style={{ display: "flex", flexDirection: "column", marginTop: 14, gap: 6 }}>
                        {metricRows.map((row) => (
                          <div
                            key={row.label}
                            style={{ display: "flex", justifyContent: "space-between", fontSize: cardLayout.metricLabelFontSize }}
                          >
                            <span style={{ color: "#CFC5B8" }}>{row.label}</span>
                            <span style={{ color: row.color, fontWeight: 700, fontSize: cardLayout.metricValueFontSize }}>
                              {row.value}
                            </span>
                          </div>
                        ))}
                      </div>

                      {hasPlayerData && selectedMetricSet.has("player_count_trend") && (
                        <div
                          style={{
                            display: "flex",
                            flexDirection: "column",
                            marginTop: 10,
                            borderRadius: 10,
                            border: "1px solid rgba(255,255,255,0.16)",
                            backgroundColor: "rgba(216,197,147,0.08)",
                            padding: "8px 10px",
                            gap: 6,
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", fontSize: cardLayout.panelLabelFontSize, color: "#D8C593", letterSpacing: "0.3px" }}>
                            <span>Player count trend</span>
                            <span>{formatCompactPlayerCount(item.currentPlayers)} now</span>
                          </div>
                          {playerTrendPath ? (
                            <svg
                              width={cardLayout.chartWidth}
                              height={cardLayout.chartHeight}
                              viewBox={`0 0 ${cardLayout.chartWidth} ${cardLayout.chartHeight}`}
                              fill="none"
                              xmlns="http://www.w3.org/2000/svg"
                            >
                              <line
                                x1="6"
                                y1={cardLayout.chartHeight - 6}
                                x2={cardLayout.chartWidth - 6}
                                y2={cardLayout.chartHeight - 6}
                                stroke="rgba(255,255,255,0.18)"
                                strokeWidth="1"
                              />
                              <path
                                d={playerTrendPath}
                                fill="none"
                                stroke="#D8C593"
                                strokeWidth="2.4"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              />
                            </svg>
                          ) : (
                            <div style={{ display: "flex", height: cardLayout.chartHeight, alignItems: "center", color: "#A69C8F", fontSize: 16 }}>
                              Not enough points
                            </div>
                          )}
                        </div>
                      )}

                      {selectedMetricSet.has("disparity_trend") && (
                        <div
                          style={{
                            display: "flex",
                            flexDirection: "column",
                            marginTop: 12,
                            borderRadius: 10,
                            border: "1px solid rgba(255,255,255,0.16)",
                            backgroundColor: "rgba(0,0,0,0.18)",
                            padding: "8px 10px",
                            gap: 6,
                          }}
                        >
                          <div style={{ display: "flex", fontSize: cardLayout.panelLabelFontSize, color: "#CFC5B8", letterSpacing: "0.3px" }}>
                            Disparity trend
                          </div>
                          {item.trend.length > 1 ? (
                            <svg
                              width={cardLayout.chartWidth}
                              height={cardLayout.chartHeight}
                              viewBox={`0 0 ${cardLayout.chartWidth} ${cardLayout.chartHeight}`}
                              fill="none"
                              xmlns="http://www.w3.org/2000/svg"
                            >
                              <line
                                x1="6"
                                y1={zeroBaselineY(item.trend, cardLayout.chartHeight)}
                                x2={cardLayout.chartWidth - 6}
                                y2={zeroBaselineY(item.trend, cardLayout.chartHeight)}
                                stroke="rgba(255,255,255,0.24)"
                                strokeWidth="1"
                              />
                              <polyline
                                points={buildTrendPolyline(item.trend, cardLayout.chartWidth, cardLayout.chartHeight)}
                                fill="none"
                                stroke={getDisparityColor(item.disparity)}
                                strokeWidth="2.4"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              />
                            </svg>
                          ) : (
                            <div style={{ display: "flex", height: cardLayout.chartHeight, alignItems: "center", color: "#A69C8F", fontSize: 16 }}>
                              Not enough points
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })()
              ))
            ) : (
              <div
                style={{
                  width: "100%",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 10,
                  borderRadius: 18,
                  border: "1px solid rgba(255, 255, 255, 0.14)",
                  backgroundColor: "rgba(255, 255, 255, 0.05)",
                }}
              >
                <div style={{ display: "flex", fontSize: 34, fontWeight: 700 }}>
                  Select up to 4 {typeLabel}
                </div>
                <div style={{ display: "flex", fontSize: 24, color: "#CFC5B8" }}>
                  Snapshot reflects the metric selection from the compare view.
                </div>
              </div>
            )}
          </div>

          <div style={{ display: "flex", marginTop: 20, fontSize: 22, color: "#A69C8F" }}>
            reviewdisparity.com/compare
          </div>
        </div>
      ),
      { width: IMAGE_WIDTH, height: IMAGE_HEIGHT }
    );
  } catch (error) {
    console.error("Compare OG image generation failed:", error);
    return new ImageResponse(
      (
        <div
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            padding: "48px",
            color: "#F7F2E7",
            background: "linear-gradient(135deg, #161310 0%, #2A211A 55%, #1D1A17 100%)",
          }}
        >
          <div style={{ display: "flex", fontSize: 34, color: "#D8C593", fontWeight: 700 }}>
            ReviewDisparity
          </div>
          <div style={{ display: "flex", marginTop: 16, fontSize: 68, fontWeight: 800 }}>
            Compare
          </div>
          <div style={{ display: "flex", marginTop: 18, fontSize: 30, color: "#CFC5B8" }}>
            Side-by-side critic disparity analysis
          </div>
        </div>
      ),
      { width: IMAGE_WIDTH, height: IMAGE_HEIGHT }
    );
  }
}
