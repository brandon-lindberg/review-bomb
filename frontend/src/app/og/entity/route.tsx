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

function metricLabelForKind(kind: EntityKind): string {
  if (kind === "game") return "Avg critic score";
  return "Avg score";
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const kind = normalizeKind(searchParams.get("kind"));
  const name = truncate(searchParams.get("name")?.trim() || "ReviewDisparity", 64);
  const subtitle = truncate(searchParams.get("subtitle")?.trim() || "Review disparity snapshot", 80);
  const disparity = parseNumber(searchParams.get("disparity"));
  const reviews = searchParams.get("reviews")?.trim() || "N/A";
  const score = searchParams.get("score")?.trim() || "N/A";
  const steamScore = searchParams.get("steam")?.trim() || "N/A";
  const metacriticScore = searchParams.get("mc")?.trim() || "N/A";
  const extra = truncate(searchParams.get("extra")?.trim() || "", 72);
  const sectionTitle = kind === "game"
    ? "Game Snapshot"
    : kind === "journalist"
      ? "Journalist Snapshot"
      : "Outlet Snapshot";

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
          <div style={{ display: "flex", fontSize: 30, color: "#D8C593", fontWeight: 700 }}>
            ReviewDisparity
          </div>
          <div style={{ display: "flex", fontSize: 20, color: "#B8AFA3", fontWeight: 600 }}>
            {sectionTitle}
          </div>
          <div style={{ display: "flex", fontSize: 64, fontWeight: 800, lineHeight: 1.05, maxWidth: 1080 }}>
            {truncate(name, 40)}
          </div>
          <div style={{ display: "flex", fontSize: 28, color: "#CFC5B8" }}>
            {subtitle}
          </div>
        </div>

        <div
          style={{
            display: "flex",
            borderRadius: 20,
            border: "1px solid rgba(255, 255, 255, 0.18)",
            backgroundColor: "rgba(255, 255, 255, 0.08)",
            padding: "20px 24px",
            gap: 36,
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", fontSize: 18, color: "#CFC5B8" }}>Avg disparity</div>
            <div style={{ display: "flex", fontSize: 48, fontWeight: 800, color: getDisparityColor(disparity) }}>
              {formatDisparity(disparity)}
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", fontSize: 18, color: "#CFC5B8" }}>Total reviews</div>
            <div style={{ display: "flex", fontSize: 42, fontWeight: 700 }}>{reviews}</div>
          </div>
          {kind === "game" ? (
            <>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", fontSize: 18, color: "#CFC5B8" }}>{metricLabelForKind(kind)}</div>
                <div style={{ display: "flex", fontSize: 42, fontWeight: 700 }}>{score}</div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", fontSize: 18, color: "#CFC5B8" }}>Steam user score</div>
                <div style={{ display: "flex", fontSize: 42, fontWeight: 700 }}>{steamScore}</div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", fontSize: 18, color: "#CFC5B8" }}>Metacritic user score</div>
                <div style={{ display: "flex", fontSize: 42, fontWeight: 700 }}>{metacriticScore}</div>
              </div>
            </>
          ) : (
            <>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", fontSize: 18, color: "#CFC5B8" }}>{metricLabelForKind(kind)}</div>
                <div style={{ display: "flex", fontSize: 42, fontWeight: 700 }}>{score}</div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 420 }}>
                <div style={{ display: "flex", fontSize: 18, color: "#CFC5B8" }}>Details</div>
                <div style={{ display: "flex", fontSize: 28, fontWeight: 600 }}>
                  {extra || "reviewdisparity.com"}
                </div>
              </div>
            </>
          )}
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
