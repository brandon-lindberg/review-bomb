import { ImageResponse } from "next/og";
import { getGame, getJournalist, getOutlet } from "@/lib/api";
import { formatDisparity, getDisparityColor, getDisplayDisparity } from "@/lib/disparity-colors";

export const revalidate = 300;
export const dynamic = "force-dynamic";

const IMAGE_WIDTH = 1200;
const IMAGE_HEIGHT = 630;

type CompareType = "journalists" | "outlets" | "games";

interface SnapshotItem {
  id: number;
  name: string;
  disparity: number | null;
  reviewCount: number;
  avgScore: number | null;
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
  return Number(value).toFixed(1);
}

async function getSnapshotItems(type: CompareType, ids: number[]): Promise<SnapshotItem[]> {
  if (ids.length === 0) return [];

  if (type === "journalists") {
    const results = await Promise.all(ids.map(async (id) => {
      try {
        const journalist = await getJournalist(id);
        return {
          id: journalist.id,
          name: journalist.name,
          disparity: journalist.avg_disparity,
          reviewCount: journalist.review_count,
          avgScore: journalist.stats?.avg_score_given ?? null,
        } satisfies SnapshotItem;
      } catch {
        return null;
      }
    }));
    return results.filter((result): result is SnapshotItem => result != null);
  }

  if (type === "outlets") {
    const results = await Promise.all(ids.map(async (id) => {
      try {
        const outlet = await getOutlet(id);
        return {
          id: outlet.id,
          name: outlet.name,
          disparity: outlet.avg_disparity ?? null,
          reviewCount: outlet.review_count ?? 0,
          avgScore: outlet.avg_score ?? null,
        } satisfies SnapshotItem;
      } catch {
        return null;
      }
    }));
    return results.filter((result): result is SnapshotItem => result != null);
  }

  const results = await Promise.all(ids.map(async (id) => {
    try {
      const game = await getGame(id);
      return {
        id: game.id,
        name: game.title,
        disparity: getDisplayDisparity(game.disparity_steam, game.disparity_metacritic),
        reviewCount: game.critic_review_count ?? 0,
        avgScore: game.avg_critic_score ?? null,
      } satisfies SnapshotItem;
    } catch {
      return null;
    }
  }));

  return results.filter((result): result is SnapshotItem => result != null);
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const type = normalizeCompareType(searchParams.get("type") ?? undefined);
    const ids = parseCompareIds(searchParams.get("ids") ?? undefined);

    const items = await getSnapshotItems(type, ids);
    const typeLabel = getTypeLabel(type);
    const title = items.length > 0
      ? `Compare ${items.map((item) => truncate(item.name, 20)).join(" vs ")}`
      : `Compare ${typeLabel}`;
    const scoreLabel = type === "games" ? "Avg critic score" : "Avg score";

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
                  fontSize: 52,
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
                  key={item.id}
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
                        fontSize: 29,
                        fontWeight: 700,
                        lineHeight: 1.05,
                        maxWidth: 210,
                      }}
                    >
                      {truncate(item.name, 20)}
                    </div>
                  </div>

                  <div
                    style={{
                      display: "flex",
                      alignItems: "baseline",
                      justifyContent: "space-between",
                      marginTop: 20,
                    }}
                  >
                    <div style={{ display: "flex", fontSize: 20, color: "#CFC5B8" }}>Avg disparity</div>
                    <div
                      style={{
                        display: "flex",
                        fontSize: 34,
                        fontWeight: 800,
                        color: getDisparityColor(item.disparity),
                      }}
                    >
                      {formatDisparity(item.disparity)}
                    </div>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", marginTop: 14, gap: 8 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 20 }}>
                      <span style={{ color: "#CFC5B8" }}>Total reviews</span>
                      <span style={{ color: "#F7F2E7", fontWeight: 700 }}>
                        {item.reviewCount.toLocaleString()}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 20 }}>
                      <span style={{ color: "#CFC5B8" }}>{scoreLabel}</span>
                      <span style={{ color: "#F7F2E7", fontWeight: 700 }}>
                        {formatScore(item.avgScore)}
                      </span>
                    </div>
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
                  Then share the comparison card to X or Reddit.
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
