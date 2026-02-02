"use client";

import {
  getDisparityColor,
  getDisparityBgColor,
  getDisparityLevel,
  formatDisparity,
} from "@/lib/disparity-colors";

interface DisparityScoresProps {
  steamDisparity: number | null | undefined;
  metacriticDisparity: number | null | undefined;
  combinedDisparity: number | null | undefined;
  layout?: "horizontal" | "vertical" | "compact";
  showLabels?: boolean;
}

function getDisparityStyle(value: number | null | undefined): React.CSSProperties {
  if (value == null) {
    return { color: "var(--foreground-muted)" };
  }

  const level = getDisparityLevel(value);
  const color = getDisparityColor(value);
  const bgColor = getDisparityBgColor(value);

  if (level === "high" || level === "extreme") {
    return { backgroundColor: color, color: "white" };
  }
  return { backgroundColor: bgColor, color: color };
}

export function DisparityScores({
  steamDisparity,
  metacriticDisparity,
  combinedDisparity,
  layout = "horizontal",
  showLabels = true,
}: DisparityScoresProps) {
  const scores = [
    {
      key: "steam",
      label: "Steam",
      value: steamDisparity,
      icon: (
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
          <circle cx="9" cy="7" r="4"/>
        </svg>
      ),
      sourceColor: "#708160", // sage for Steam source identifier
    },
    {
      key: "metacritic",
      label: "Metacritic",
      value: metacriticDisparity,
      icon: (
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
        </svg>
      ),
      sourceColor: "#DD7631", // orange for Metacritic source identifier
    },
    {
      key: "combined",
      label: "Combined",
      value: combinedDisparity,
      icon: (
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="20" x2="18" y2="10"/>
          <line x1="12" y1="20" x2="12" y2="4"/>
          <line x1="6" y1="20" x2="6" y2="14"/>
        </svg>
      ),
      sourceColor: "#5C574F", // neutral for combined
    },
  ];

  if (layout === "compact") {
    return (
      <div className="flex items-center gap-2">
        {scores.map((score) => (
          <div
            key={score.key}
            className="flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium"
            style={getDisparityStyle(score.value)}
            title={`${score.label} Disparity`}
          >
            <span style={{ color: score.sourceColor }}>{score.icon}</span>
            <span>{formatDisparity(score.value)}</span>
          </div>
        ))}
      </div>
    );
  }

  if (layout === "vertical") {
    return (
      <div className="space-y-3">
        {scores.map((score) => (
          <div key={score.key} className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span style={{ color: score.sourceColor }}>{score.icon}</span>
              {showLabels && (
                <span className="text-sm" style={{ color: "var(--foreground-muted)" }}>
                  {score.label}
                </span>
              )}
            </div>
            <span
              className="px-2 py-1 rounded-full text-sm font-medium"
              style={getDisparityStyle(score.value)}
            >
              {formatDisparity(score.value)}
            </span>
          </div>
        ))}
      </div>
    );
  }

  // Horizontal layout (default)
  return (
    <div className="flex items-center gap-4">
      {scores.map((score) => (
        <div key={score.key} className="text-center">
          <div className="flex items-center justify-center gap-1 mb-1">
            <span style={{ color: score.sourceColor }}>{score.icon}</span>
            {showLabels && (
              <span className="text-xs" style={{ color: "var(--foreground-muted)" }}>
                {score.label}
              </span>
            )}
          </div>
          <span
            className="inline-block px-3 py-1 rounded-full text-sm font-medium"
            style={getDisparityStyle(score.value)}
          >
            {formatDisparity(score.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

// Card version for prominent display
interface DisparityScoreCardsProps {
  steamDisparity: number | null | undefined;
  metacriticDisparity: number | null | undefined;
  combinedDisparity: number | null | undefined;
  steamUserScore?: number | null;
  metacriticUserScore?: number | null;
  criticScore?: number | null;
}

export function DisparityScoreCards({
  steamDisparity,
  metacriticDisparity,
  combinedDisparity,
  steamUserScore,
  metacriticUserScore,
  criticScore,
}: DisparityScoreCardsProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* Steam Disparity */}
      <div
        className="p-4 rounded-lg"
        style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-2 mb-3">
          <div
            className="w-8 h-8 rounded flex items-center justify-center"
            style={{ backgroundColor: "#708160", color: "white" }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
            </svg>
          </div>
          <span className="font-medium" style={{ color: "var(--foreground)" }}>
            Steam Disparity
          </span>
        </div>
        <div className="flex items-end justify-between">
          <div>
            <span
              className="text-2xl font-bold"
              style={{ color: getDisparityColor(steamDisparity) }}
            >
              {formatDisparity(steamDisparity)}
            </span>
            {steamUserScore != null && criticScore != null && (
              <p className="text-xs mt-1" style={{ color: "var(--foreground-muted)" }}>
                {Number(criticScore).toFixed(0)} vs {Number(steamUserScore).toFixed(0)}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Metacritic Disparity */}
      <div
        className="p-4 rounded-lg"
        style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-2 mb-3">
          <div
            className="w-8 h-8 rounded flex items-center justify-center"
            style={{ backgroundColor: "#DD7631", color: "white" }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
            </svg>
          </div>
          <span className="font-medium" style={{ color: "var(--foreground)" }}>
            Metacritic Disparity
          </span>
        </div>
        <div className="flex items-end justify-between">
          <div>
            <span
              className="text-2xl font-bold"
              style={{ color: getDisparityColor(metacriticDisparity) }}
            >
              {formatDisparity(metacriticDisparity)}
            </span>
            {metacriticUserScore != null && criticScore != null && (
              <p className="text-xs mt-1" style={{ color: "var(--foreground-muted)" }}>
                {Number(criticScore).toFixed(0)} vs {Number(metacriticUserScore).toFixed(0)}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Combined Disparity */}
      <div
        className="p-4 rounded-lg"
        style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-2 mb-3">
          <div
            className="w-8 h-8 rounded flex items-center justify-center"
            style={{ backgroundColor: "#5C574F", color: "white" }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="20" x2="18" y2="10"/>
              <line x1="12" y1="20" x2="12" y2="4"/>
              <line x1="6" y1="20" x2="6" y2="14"/>
            </svg>
          </div>
          <span className="font-medium" style={{ color: "var(--foreground)" }}>
            Combined Disparity
          </span>
        </div>
        <div className="flex items-end justify-between">
          <div>
            <span
              className="text-2xl font-bold"
              style={{ color: getDisparityColor(combinedDisparity) }}
            >
              {formatDisparity(combinedDisparity)}
            </span>
            <p className="text-xs mt-1" style={{ color: "var(--foreground-muted)" }}>
              Average of both sources
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
