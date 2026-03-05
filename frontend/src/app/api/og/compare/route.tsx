import { ImageResponse } from "next/og";
import { getGame, getGameHistory, getJournalist, getJournalistHistory, getOutlet, getOutletHistory } from "@/lib/api";
import { formatDisparity, getDisparityColor, getDisplayDisparity } from "@/lib/disparity-colors";
import { deriveSourceScoreFromDisparity } from "@/lib/share-snapshot";
import type { DisparitySnapshot } from "@/types";

export const revalidate = 300;
export const dynamic = "force-dynamic";

const IMAGE_WIDTH = 1200;
const IMAGE_HEIGHT = 630;

type CompareType = "journalists" | "outlets" | "games";

interface SnapshotItem {
  id: number;
  name: string;
  disparity: number | null;
  reviewCount: number | null;
  criticScore: number | null;
  steamScore: number | null;
  metacriticScore: number | null;
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
}

const avatarColors = ["#BB3B0E", "#DD7631", "#708160", "#D8C593"];

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
      const [game, history] = await Promise.all([
        getGame(id),
        getGameHistory(id, 180),
      ]);
      return {
        id: game.id,
        name: game.title,
        disparity: getDisplayDisparity(game.disparity_steam, game.disparity_metacritic),
        reviewCount: game.critic_review_count ?? 0,
        criticScore: game.avg_critic_score ?? null,
        steamScore: game.steam_user_score ?? null,
        metacriticScore: game.metacritic_user_score ?? null,
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
    const snapshotItems = parseSnapshotPayload(searchParams.get("snap"));

    const quickItems: SnapshotItem[] = ids.map((id, index) => ({
      id,
      name: labels[index] ?? `Item ${index + 1}`,
      disparity: null,
      reviewCount: null,
      criticScore: null,
      steamScore: null,
      metacriticScore: null,
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

          <div style={{ display: "flex", gap: 16, marginTop: 26, flex: 1 }}>
            {items.length > 0 ? (
              items.map((item, index) => (
                <div
                  key={`${item.id}-${index}`}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    flex: 1,
                    borderRadius: 18,
                    padding: "18px 18px 16px",
                    backgroundColor: "rgba(255, 255, 255, 0.08)",
                    border: "1px solid rgba(255, 255, 255, 0.18)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div
                      style={{
                        display: "flex",
                        width: 42,
                        height: 42,
                        borderRadius: 999,
                        alignItems: "center",
                        justifyContent: "center",
                        backgroundColor: avatarColors[index % avatarColors.length],
                        color: "#F8F8F8",
                        fontWeight: 700,
                        fontSize: 22,
                      }}
                    >
                      {item.name.charAt(0).toUpperCase()}
                    </div>
                    <div
                      style={{
                        display: "flex",
                        fontSize: 27,
                        fontWeight: 700,
                        lineHeight: 1.05,
                        maxWidth: 220,
                      }}
                    >
                      {truncate(item.name, 22)}
                    </div>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", marginTop: 16, gap: 8 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 18 }}>
                      <span style={{ color: "#CFC5B8" }}>Critic score</span>
                      <span style={{ color: "#F7F2E7", fontWeight: 700, fontSize: 24 }}>
                        {formatScore(item.criticScore)}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 18 }}>
                      <span style={{ color: "#CFC5B8" }}>Steam score</span>
                      <span style={{ color: "#F7F2E7", fontWeight: 700, fontSize: 24 }}>
                        {formatScore(item.steamScore)}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 18 }}>
                      <span style={{ color: "#CFC5B8" }}>Metacritic score</span>
                      <span style={{ color: "#F7F2E7", fontWeight: 700, fontSize: 24 }}>
                        {formatScore(item.metacriticScore)}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 18 }}>
                      <span style={{ color: "#CFC5B8" }}>Combined disparity</span>
                      <span
                        style={{
                          color: getDisparityColor(item.disparity),
                          fontWeight: 800,
                          fontSize: 24,
                        }}
                      >
                        {formatDisparity(item.disparity)}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 18 }}>
                      <span style={{ color: "#CFC5B8" }}>Total reviews</span>
                      <span style={{ color: "#F7F2E7", fontWeight: 700, fontSize: 24 }}>
                        {formatReviewCount(item.reviewCount)}
                      </span>
                    </div>
                  </div>

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
                    <div style={{ display: "flex", fontSize: 14, color: "#CFC5B8", letterSpacing: "0.3px" }}>
                      Disparity trend
                    </div>
                    {item.trend.length > 1 ? (
                      <svg
                        width="220"
                        height="58"
                        viewBox="0 0 220 58"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                      >
                        <line
                          x1="6"
                          y1={zeroBaselineY(item.trend, 58)}
                          x2="214"
                          y2={zeroBaselineY(item.trend, 58)}
                          stroke="rgba(255,255,255,0.24)"
                          strokeWidth="1"
                        />
                        <polyline
                          points={buildTrendPolyline(item.trend, 220, 58)}
                          fill="none"
                          stroke={getDisparityColor(item.disparity)}
                          strokeWidth="2.4"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    ) : (
                      <div style={{ display: "flex", height: 58, alignItems: "center", color: "#A69C8F", fontSize: 16 }}>
                        Not enough points
                      </div>
                    )}
                  </div>
                </div>
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
                  Snapshot includes critic, steam, metacritic, and disparity.
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
