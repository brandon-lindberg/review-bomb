import { ImageResponse } from "next/og";
import { getGameHistory, getJournalistHistory, getOutletHistory } from "@/lib/api";
import { formatDisparity, getDisparityColor } from "@/lib/disparity-colors";
import { readTrendSnapshot, toTrendSnapshot } from "@/lib/share-snapshot";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const IMAGE_WIDTH = 1200;
const IMAGE_HEIGHT = 630;

type EntityKind = "game" | "journalist" | "outlet";

function normalizeKind(rawKind?: string | null): EntityKind {
  if (rawKind === "game" || rawKind === "journalist" || rawKind === "outlet") {
    return rawKind;
  }
  return "game";
}

function truncate(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 1)}…`;
}

function parseNumber(rawValue?: string | null): number | null {
  if (!rawValue) return null;
  const parsed = Number(rawValue);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseCount(rawValue?: string | null): number | null {
  if (!rawValue) return null;
  const parsed = Number.parseInt(rawValue, 10);
  if (!Number.isFinite(parsed) || parsed < 0) return null;
  return parsed;
}

type SnapshotMode = "default" | "chart" | "timing";

function normalizeMode(rawMode?: string | null): SnapshotMode {
  if (rawMode === "chart" || rawMode === "timing") return rawMode;
  return "default";
}

function kindSubtitle(kind: EntityKind, mode: SnapshotMode): string {
  if (mode === "chart") return "Chart Snapshot";
  if (mode === "timing") return "Timing Snapshot";
  if (kind === "journalist") return "Journalist Snapshot";
  if (kind === "outlet") return "Outlet Snapshot";
  return "Game Snapshot";
}

function buildTrendPolyline(points: number[], width: number, height: number): string {
  if (points.length === 0) return "";
  const pad = 8;
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
  const pad = 8;
  const chartHeight = height - pad * 2;
  const min = Math.min(...points, 0);
  const max = Math.max(...points, 0);
  const span = Math.max(max - min, 1);
  return pad + (1 - (0 - min) / span) * chartHeight;
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const mode = normalizeMode(searchParams.get("mode")?.trim());
  const kind = normalizeKind(searchParams.get("kind"));
  const entityId = searchParams.get("id")?.trim();
  const name = truncate(searchParams.get("name")?.trim() || "ReviewDisparity", 64);
  const disparity = parseNumber(searchParams.get("disparity"));
  const reviews = searchParams.get("reviews")?.trim() || "N/A";
  const criticScore = searchParams.get("critic")?.trim() || searchParams.get("score")?.trim() || "N/A";
  const steamScore = searchParams.get("steam")?.trim() || "N/A";
  const metacriticScore = searchParams.get("mc")?.trim() || "N/A";
  const early = parseCount(searchParams.get("early"));
  const launch = parseCount(searchParams.get("launch"));
  const late = parseCount(searchParams.get("late"));
  const totalTiming = (early ?? 0) + (launch ?? 0) + (late ?? 0);
  let trend = readTrendSnapshot(searchParams.get("t")) ?? [];
  if (mode === "chart" && trend.length < 2 && entityId) {
    try {
      const history = kind === "journalist"
        ? await getJournalistHistory(entityId, 180)
        : kind === "outlet"
          ? await getOutletHistory(entityId, 180)
          : await getGameHistory(entityId, 180);
      trend = toTrendSnapshot(history);
    } catch {
      trend = [];
    }
  }
  const trendColor = getDisparityColor(disparity);
  const compactMetrics = mode !== "default";
  const chartWidth = 1068;
  const chartHeight = 138;
  const metricsPanelStyle = {
    display: "flex",
    flexDirection: "column",
    gap: 12,
    borderRadius: 20,
    border: "1px solid rgba(255, 255, 255, 0.18)",
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    padding: "14px",
  } as const;
  const metricsRowStyle = {
    display: "flex",
    gap: 12,
  } as const;
  const metricTileStyle = {
    display: "flex",
    flexDirection: "column",
    gap: 9,
    padding: "14px 16px 15px 16px",
    borderRadius: 14,
    backgroundColor: "rgba(0, 0, 0, 0.20)",
    border: "1px solid rgba(255, 255, 255, 0.14)",
    flex: 1,
  } as const;
  const metricLabelStyle = {
    display: "flex",
    fontSize: 14,
    lineHeight: 1.2,
    color: "#CFC5B8",
    letterSpacing: "0.7px",
    textTransform: "uppercase",
  } as const;
  const metricValueStyle = {
    display: "flex",
    fontSize: 52,
    lineHeight: 1,
    fontWeight: 750,
    ...(compactMetrics ? { fontSize: 42 } : {}),
  } as const;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          padding: "44px 52px",
          color: "#F7F2E7",
          background: "linear-gradient(135deg, #161310 0%, #2A211A 55%, #1D1A17 100%)",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", fontSize: 30, color: "#D8C593", fontWeight: 700, justifyContent: "space-between", width: "100%" }}>
            ReviewDisparity
            <span style={{ fontSize: 20, color: "#B8AFA3", fontWeight: 600 }}>{kindSubtitle(kind, mode)}</span>
          </div>
          <div style={{ display: "flex", fontSize: 64, fontWeight: 800, lineHeight: 1.05, maxWidth: 1080 }}>
            {truncate(name, 40)}
          </div>
        </div>

        {mode === "chart" && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 8,
              marginTop: 14,
              borderRadius: 18,
              border: "1px solid rgba(255,255,255,0.18)",
              backgroundColor: "rgba(255,255,255,0.08)",
              padding: "12px 14px",
            }}
          >
            <div style={{ display: "flex", fontSize: 18, color: "#CFC5B8", letterSpacing: "0.3px" }}>
              Disparity trend
            </div>
            {trend.length > 1 ? (
              <svg
                width={chartWidth}
                height={chartHeight}
                viewBox={`0 0 ${chartWidth} ${chartHeight}`}
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <line
                  x1="8"
                  y1={zeroBaselineY(trend, chartHeight)}
                  x2={chartWidth - 8}
                  y2={zeroBaselineY(trend, chartHeight)}
                  stroke="rgba(255,255,255,0.24)"
                  strokeWidth="1"
                />
                <polyline
                  points={buildTrendPolyline(trend, chartWidth, chartHeight)}
                  fill="none"
                  stroke={trendColor}
                  strokeWidth="4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            ) : (
              <div style={{ display: "flex", height: chartHeight, alignItems: "center", color: "#A69C8F", fontSize: 24 }}>
                Not enough trend points yet
              </div>
            )}
          </div>
        )}

        {mode === "timing" && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 8,
              marginTop: 14,
              borderRadius: 18,
              border: "1px solid rgba(255,255,255,0.18)",
              backgroundColor: "rgba(255,255,255,0.08)",
              padding: "12px 14px",
            }}
          >
            <div style={{ display: "flex", fontSize: 18, color: "#CFC5B8", letterSpacing: "0.3px" }}>
              Review timing
            </div>
            {totalTiming > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div
                  style={{
                    display: "flex",
                    width: "100%",
                    height: 24,
                    borderRadius: 999,
                    overflow: "hidden",
                    background: "rgba(0,0,0,0.22)",
                    border: "1px solid rgba(255,255,255,0.14)",
                  }}
                >
                  <div style={{ width: `${(((early ?? 0) / totalTiming) * 100).toFixed(1)}%`, background: "#5C9BE6", height: "100%" }} />
                  <div style={{ width: `${(((launch ?? 0) / totalTiming) * 100).toFixed(1)}%`, background: "#4FC97A", height: "100%" }} />
                  <div style={{ width: `${(((late ?? 0) / totalTiming) * 100).toFixed(1)}%`, background: "#E5B74D", height: "100%" }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 12, height: 12, borderRadius: 999, background: "#5C9BE6" }} />
                    <div style={{ display: "flex", fontSize: 20, color: "#CFC5B8" }}>
                      Early {early ?? 0}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 12, height: 12, borderRadius: 999, background: "#4FC97A" }} />
                    <div style={{ display: "flex", fontSize: 20, color: "#CFC5B8" }}>
                      Launch {launch ?? 0}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 12, height: 12, borderRadius: 999, background: "#E5B74D" }} />
                    <div style={{ display: "flex", fontSize: 20, color: "#CFC5B8" }}>
                      Late {late ?? 0}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ display: "flex", height: chartHeight, alignItems: "center", color: "#A69C8F", fontSize: 24 }}>
                No timing data yet
              </div>
            )}
          </div>
        )}

        <div style={{ ...metricsPanelStyle, marginTop: mode === "default" ? 0 : 14 }}>
          <div style={metricsRowStyle}>
            <div style={metricTileStyle}>
              <div style={metricLabelStyle}>Critic Score</div>
              <div style={metricValueStyle}>{criticScore}</div>
            </div>
            <div style={metricTileStyle}>
              <div style={metricLabelStyle}>Steam Score</div>
              <div style={metricValueStyle}>{steamScore}</div>
            </div>
            <div style={metricTileStyle}>
              <div style={metricLabelStyle}>Metacritic Score</div>
              <div style={metricValueStyle}>{metacriticScore}</div>
            </div>
          </div>
          <div style={metricsRowStyle}>
            <div style={metricTileStyle}>
              <div style={metricLabelStyle}>Combined Disparity</div>
              <div style={{ ...metricValueStyle, color: trendColor }}>
                {formatDisparity(disparity)}
              </div>
            </div>
            <div style={metricTileStyle}>
              <div style={metricLabelStyle}>Total Reviews</div>
              <div style={metricValueStyle}>{reviews}</div>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", fontSize: 24, color: "#A69C8F", marginTop: "auto" }}>
          reviewdisparity.com
        </div>
      </div>
    ),
    {
      width: IMAGE_WIDTH,
      height: IMAGE_HEIGHT,
      headers: {
        "Cache-Control": "no-store, max-age=0",
      },
    }
  );
}
