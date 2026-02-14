"use client";

import {
  getDisparityColor,
  getDisparityBgColor,
  formatDisparity,
} from "@/lib/disparity-colors";

interface ReviewScoreTableProps {
  criticScore: number | null;
  steamScore: number | null;
  steamDisparity: number | null;
  metacriticScore: number | null;
  metacriticDisparity: number | null;
  combinedDisparity: number | null;
}

function formatScore(value: number | null): string {
  if (value == null) return "—";
  return Number(value).toFixed(0);
}

export function ReviewScoreTable({
  criticScore,
  steamScore,
  steamDisparity,
  metacriticScore,
  metacriticDisparity,
  combinedDisparity,
}: ReviewScoreTableProps) {
  // Ensure proper number conversion for calculations
  const steamNum = steamScore != null ? Number(steamScore) : null;
  const metacriticNum = metacriticScore != null ? Number(metacriticScore) : null;

  // Calculate combined user score for display
  const combinedScore =
    steamNum != null && metacriticNum != null
      ? (steamNum + metacriticNum) / 2
      : steamNum ?? metacriticNum;

  return (
    <div className="overflow-x-auto">
      <table className="text-sm">
        <thead>
          <tr>
            <th
              className="px-3 py-1.5 text-center font-medium border-b"
              style={{ color: "var(--foreground-muted)", borderColor: "var(--border)" }}
            >
              Critic
            </th>
            <th
              className="px-3 py-1.5 text-center font-medium border-b"
              style={{ color: "#708160", borderColor: "var(--border)" }}
            >
              Steam
            </th>
            <th
              className="px-3 py-1.5 text-center font-medium border-b"
              style={{ color: "#708160", borderColor: "var(--border)" }}
            >
              Steam Disp.
            </th>
            <th
              className="px-3 py-1.5 text-center font-medium border-b"
              style={{ color: "#DD7631", borderColor: "var(--border)" }}
            >
              MC
            </th>
            <th
              className="px-3 py-1.5 text-center font-medium border-b"
              style={{ color: "#DD7631", borderColor: "var(--border)" }}
            >
              MC Disp.
            </th>
            <th
              className="px-3 py-1.5 text-center font-medium border-b"
              style={{ color: "#5C574F", borderColor: "var(--border)" }}
            >
              Combined
            </th>
            <th
              className="px-3 py-1.5 text-center font-medium border-b"
              style={{ color: "#5C574F", borderColor: "var(--border)" }}
            >
              Comb. Disp.
            </th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td
              className="px-3 py-2 text-center font-bold text-lg"
              style={{ color: "var(--foreground)" }}
            >
              {formatScore(criticScore)}
            </td>
            <td
              className="px-3 py-2 text-center"
              style={{ color: "var(--foreground-muted)" }}
            >
              {formatScore(steamScore)}
            </td>
            <td
              className="px-3 py-2 text-center font-medium"
              style={{ color: getDisparityColor(steamDisparity) }}
            >
              {formatDisparity(steamDisparity)}
            </td>
            <td
              className="px-3 py-2 text-center"
              style={{ color: "var(--foreground-muted)" }}
            >
              {formatScore(metacriticScore)}
            </td>
            <td
              className="px-3 py-2 text-center font-medium"
              style={{ color: getDisparityColor(metacriticDisparity) }}
            >
              {formatDisparity(metacriticDisparity)}
            </td>
            <td
              className="px-3 py-2 text-center"
              style={{ color: "var(--foreground-muted)" }}
            >
              {combinedScore != null ? combinedScore.toFixed(0) : "—"}
            </td>
            <td
              className="px-3 py-2 text-center font-medium"
              style={{ color: getDisparityColor(combinedDisparity) }}
            >
              {formatDisparity(combinedDisparity)}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

// Compact inline version for tighter spaces
export function ReviewScoreInline({
  criticScore,
  steamScore,
  steamDisparity,
  metacriticScore,
  metacriticDisparity,
  combinedDisparity,
}: ReviewScoreTableProps) {
  // Ensure proper number conversion for calculations
  const steamNum = steamScore != null ? Number(steamScore) : null;
  const metacriticNum = metacriticScore != null ? Number(metacriticScore) : null;

  const combinedScore =
    steamNum != null && metacriticNum != null
      ? (steamNum + metacriticNum) / 2
      : steamNum ?? metacriticNum;

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
      {/* Critic Score */}
      <div className="flex items-center gap-1">
        <span style={{ color: "var(--foreground-muted)" }}>Critic:</span>
        <span className="font-bold" style={{ color: "var(--foreground)" }}>
          {formatScore(criticScore)}
        </span>
      </div>

      {/* Steam */}
      <div className="flex items-center gap-1">
        <span style={{ color: "#708160" }}>Steam:</span>
        <span style={{ color: "var(--foreground-muted)" }}>{formatScore(steamScore)}</span>
        <span
          className="font-medium px-1.5 py-0.5 rounded text-xs"
          style={{
            color: getDisparityColor(steamDisparity),
            backgroundColor: getDisparityBgColor(steamDisparity),
          }}
        >
          {formatDisparity(steamDisparity)}
        </span>
      </div>

      {/* Metacritic */}
      <div className="flex items-center gap-1">
        <span style={{ color: "#DD7631" }}>MC:</span>
        <span style={{ color: "var(--foreground-muted)" }}>{formatScore(metacriticScore)}</span>
        <span
          className="font-medium px-1.5 py-0.5 rounded text-xs"
          style={{
            color: getDisparityColor(metacriticDisparity),
            backgroundColor: getDisparityBgColor(metacriticDisparity),
          }}
        >
          {formatDisparity(metacriticDisparity)}
        </span>
      </div>

      {/* Combined */}
      <div className="flex items-center gap-1">
        <span style={{ color: "#5C574F" }}>Combined:</span>
        <span style={{ color: "var(--foreground-muted)" }}>
          {combinedScore != null ? combinedScore.toFixed(0) : "—"}
        </span>
        <span
          className="font-medium px-1.5 py-0.5 rounded text-xs"
          style={{
            color: getDisparityColor(combinedDisparity),
            backgroundColor: getDisparityBgColor(combinedDisparity),
          }}
        >
          {formatDisparity(combinedDisparity)}
        </span>
      </div>
    </div>
  );
}

// Card-style grouped version
export function ReviewScoreCards({
  criticScore,
  steamScore,
  steamDisparity,
  metacriticScore,
  metacriticDisparity,
  combinedDisparity,
}: ReviewScoreTableProps) {
  // Ensure proper number conversion for calculations
  const steamNum = steamScore != null ? Number(steamScore) : null;
  const metacriticNum = metacriticScore != null ? Number(metacriticScore) : null;

  const combinedScore =
    steamNum != null && metacriticNum != null
      ? (steamNum + metacriticNum) / 2
      : steamNum ?? metacriticNum;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
      {/* Critic Score */}
      <div
        className="px-3 py-2 rounded-lg text-center"
        style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
      >
        <div className="text-xs mb-0.5" style={{ color: "var(--foreground-muted)" }}>
          Critic
        </div>
        <div className="text-xl font-bold" style={{ color: "var(--foreground)" }}>
          {formatScore(criticScore)}
        </div>
      </div>

      {/* Steam */}
      <div
        className="px-3 py-2 rounded-lg text-center"
        style={{ backgroundColor: "rgba(112, 129, 96, 0.1)", border: "1px solid rgba(112, 129, 96, 0.3)" }}
      >
        <div className="text-xs mb-0.5" style={{ color: "#708160" }}>
          Steam
        </div>
        <div className="flex items-baseline justify-center gap-1">
          <span className="text-lg" style={{ color: "var(--foreground)" }}>
            {formatScore(steamScore)}
          </span>
          <span
            className="text-sm font-medium"
            style={{ color: getDisparityColor(steamDisparity) }}
          >
            {formatDisparity(steamDisparity)}
          </span>
        </div>
      </div>

      {/* Metacritic */}
      <div
        className="px-3 py-2 rounded-lg text-center"
        style={{ backgroundColor: "rgba(221, 118, 49, 0.1)", border: "1px solid rgba(221, 118, 49, 0.3)" }}
      >
        <div className="text-xs mb-0.5" style={{ color: "#DD7631" }}>
          MC
        </div>
        <div className="flex items-baseline justify-center gap-1">
          <span className="text-lg" style={{ color: "var(--foreground)" }}>
            {formatScore(metacriticScore)}
          </span>
          <span
            className="text-sm font-medium"
            style={{ color: getDisparityColor(metacriticDisparity) }}
          >
            {formatDisparity(metacriticDisparity)}
          </span>
        </div>
      </div>

      {/* Combined */}
      <div
        className="px-3 py-2 rounded-lg text-center"
        style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
      >
        <div className="text-xs mb-0.5" style={{ color: "#5C574F" }}>
          Combined
        </div>
        <div className="flex items-baseline justify-center gap-1">
          <span className="text-lg" style={{ color: "var(--foreground)" }}>
            {combinedScore != null ? combinedScore.toFixed(0) : "—"}
          </span>
          <span
            className="text-sm font-medium"
            style={{ color: getDisparityColor(combinedDisparity) }}
          >
            {formatDisparity(combinedDisparity)}
          </span>
        </div>
      </div>
    </div>
  );
}
