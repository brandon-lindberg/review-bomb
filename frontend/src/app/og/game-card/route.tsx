import { ImageResponse } from "next/og";
import { formatDisparity, getDisparityColor } from "@/lib/disparity-colors";

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

function metricTile(
  label: string,
  value: string,
  valueColor?: string
) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 8,
        padding: "14px 16px",
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
          fontSize: 52,
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

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const mode = searchParams.get("mode")?.trim() === "chart" ? "chart" : "default";
  const name = truncate(searchParams.get("name")?.trim() || "ReviewDisparity", 48);
  const critic = searchParams.get("critic")?.trim() || "N/A";
  const steam = searchParams.get("steam")?.trim() || "N/A";
  const metacritic = searchParams.get("mc")?.trim() || "N/A";
  const reviews = searchParams.get("reviews")?.trim() || "N/A";
  const disparityRaw = parseNumber(searchParams.get("disparity"));
  const disparity = formatDisparity(disparityRaw);

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
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", fontSize: 30, color: "#D8C593", fontWeight: 700, justifyContent: "space-between", width: "100%" }}>
            <span>ReviewDisparity</span>
            {mode === "chart" && (
              <span style={{ fontSize: 20, color: "#B8AFA3", fontWeight: 600 }}>Chart Snapshot</span>
            )}
          </div>
          <div style={{ display: "flex", fontSize: 64, fontWeight: 800, lineHeight: 1.04, maxWidth: 1080 }}>
            {name}
          </div>
        </div>

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 12,
            borderRadius: 20,
            border: "1px solid rgba(255,255,255,0.18)",
            background: "rgba(255,255,255,0.08)",
            padding: "14px",
          }}
        >
          <div style={{ display: "flex", gap: 12 }}>
            {metricTile("Critic", critic)}
            {metricTile("Steam", steam)}
            {metricTile("Metacritic", metacritic)}
          </div>
          <div style={{ display: "flex", gap: 12 }}>
            {metricTile("Disparity", disparity, getDisparityColor(disparityRaw))}
            {metricTile("Total reviews", reviews)}
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
