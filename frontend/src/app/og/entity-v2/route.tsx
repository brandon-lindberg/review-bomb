import { ImageResponse } from "next/og";
import { formatDisparity, getDisparityColor } from "@/lib/disparity-colors";

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

function kindSubtitle(kind: EntityKind, mode: "default" | "chart"): string {
  if (mode === "chart") return "Chart Snapshot";
  if (kind === "journalist") return "Journalist Snapshot";
  if (kind === "outlet") return "Outlet Snapshot";
  return "Game Snapshot";
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const mode = searchParams.get("mode")?.trim() === "chart" ? "chart" : "default";
  const kind = normalizeKind(searchParams.get("kind"));
  const name = truncate(searchParams.get("name")?.trim() || "ReviewDisparity", 64);
  const disparity = parseNumber(searchParams.get("disparity"));
  const reviews = searchParams.get("reviews")?.trim() || "N/A";
  const criticScore = searchParams.get("critic")?.trim() || searchParams.get("score")?.trim() || "N/A";
  const steamScore = searchParams.get("steam")?.trim() || "N/A";
  const metacriticScore = searchParams.get("mc")?.trim() || "N/A";
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
  } as const;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
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

        <div style={metricsPanelStyle}>
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
              <div style={{ ...metricValueStyle, color: getDisparityColor(disparity) }}>
                {formatDisparity(disparity)}
              </div>
            </div>
            <div style={metricTileStyle}>
              <div style={metricLabelStyle}>Total Reviews</div>
              <div style={metricValueStyle}>{reviews}</div>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", fontSize: 24, color: "#A69C8F" }}>
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
