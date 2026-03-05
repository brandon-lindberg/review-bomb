import { ImageResponse } from "next/og";
import { getGameHistory } from "@/lib/api";
import { formatDisparity, getDisparityColor } from "@/lib/disparity-colors";
import { readTrendSnapshot, toTrendSnapshot } from "@/lib/share-snapshot";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const IMAGE_WIDTH = 1200;
const IMAGE_HEIGHT = 630;

function truncate(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 1)}...`;
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

function modeLabel(mode: SnapshotMode): string {
  if (mode === "chart") return "Chart Snapshot";
  if (mode === "timing") return "Timing Snapshot";
  return "";
}

function metricTile(
  label: string,
  value: string,
  valueColor?: string,
  compact = false,
) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: compact ? 6 : 8,
        padding: compact ? "12px 14px" : "14px 16px",
        borderRadius: 12,
        border: "1px solid rgba(255,255,255,0.14)",
        background: "rgba(0,0,0,0.18)",
        flex: 1,
      }}
    >
      <div
        style={{
          display: "flex",
          fontSize: 14,
          lineHeight: 1.2,
          textTransform: "uppercase",
          letterSpacing: "0.7px",
          color: "#CFC5B8",
        }}
      >
        {label}
      </div>
      <div
        style={{
          display: "flex",
          fontSize: compact ? 42 : 52,
          lineHeight: 1,
          fontWeight: 760,
          color: valueColor || "#F7F2E7",
        }}
      >
        {value}
      </div>
    </div>
  );
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
  const name = truncate(searchParams.get("name")?.trim() || "ReviewDisparity", 48);
  const critic = searchParams.get("critic")?.trim() || "N/A";
  const steam = searchParams.get("steam")?.trim() || "N/A";
  const metacritic = searchParams.get("mc")?.trim() || "N/A";
  const reviews = searchParams.get("reviews")?.trim() || "N/A";
  const early = parseCount(searchParams.get("early"));
  const launch = parseCount(searchParams.get("launch"));
  const late = parseCount(searchParams.get("late"));
  const totalTiming = (early ?? 0) + (launch ?? 0) + (late ?? 0);
  const disparityRaw = parseNumber(searchParams.get("disparity") ?? searchParams.get("disp"));
  const disparity = formatDisparity(disparityRaw);
  const historyId = searchParams.get("id")?.trim();
  let trend = readTrendSnapshot(searchParams.get("t")) ?? [];
  if (mode === "chart" && trend.length < 2 && historyId) {
    try {
      const history = await getGameHistory(historyId, 180);
      trend = toTrendSnapshot(history);
    } catch {
      trend = [];
    }
  }
  const trendColor = getDisparityColor(disparityRaw);
  const chartWidth = 1068;
  const chartHeight = 138;
  const compactMetrics = mode !== "default";

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
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", fontSize: 30, color: "#D8C593", fontWeight: 700, justifyContent: "space-between", width: "100%" }}>
            <span>ReviewDisparity</span>
            {mode !== "default" && (
              <span style={{ fontSize: 20, color: "#B8AFA3", fontWeight: 600 }}>{modeLabel(mode)}</span>
            )}
          </div>
          <div style={{ display: "flex", fontSize: 64, fontWeight: 800, lineHeight: 1.04, maxWidth: 1080 }}>
            {name}
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
              background: "rgba(255,255,255,0.08)",
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
              background: "rgba(255,255,255,0.08)",
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

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 12,
            borderRadius: 20,
            border: "1px solid rgba(255,255,255,0.18)",
            background: "rgba(255,255,255,0.08)",
            padding: "14px",
            marginTop: mode === "default" ? 0 : 14,
          }}
        >
          <div style={{ display: "flex", gap: 12 }}>
            {metricTile("Critic", critic, undefined, compactMetrics)}
            {metricTile("Steam", steam, undefined, compactMetrics)}
            {metricTile("Metacritic", metacritic, undefined, compactMetrics)}
          </div>
          <div style={{ display: "flex", gap: 12 }}>
            {metricTile("Disparity", disparity, trendColor, compactMetrics)}
            {metricTile("Total reviews", reviews, undefined, compactMetrics)}
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
