// Disparity color utility
// Colors based on MAGNITUDE of disparity (how far from users), not direction

export type DisparityLevel = "aligned" | "moderate" | "high" | "extreme";

export function getDisparityLevel(disparity: number | null | undefined): DisparityLevel {
  if (disparity == null) return "aligned";

  const magnitude = Math.abs(Number(disparity));

  if (magnitude < 5) return "aligned";
  if (magnitude < 10) return "moderate";
  if (magnitude < 15) return "high";
  return "extreme";
}

// Get color based on disparity magnitude
export function getDisparityColor(disparity: number | null | undefined): string {
  const level = getDisparityLevel(disparity);

  switch (level) {
    case "aligned":
      return "#708160"; // sage green - close to users
    case "moderate":
      return "#D4A017"; // golden yellow - some divergence
    case "high":
      return "#DD7631"; // orange - significant divergence
    case "extreme":
      return "#BB3B0E"; // rust red - major divergence
  }
}

// Get background color (lighter version) based on disparity magnitude
export function getDisparityBgColor(disparity: number | null | undefined): string {
  const level = getDisparityLevel(disparity);

  switch (level) {
    case "aligned":
      return "rgba(112, 129, 96, 0.15)"; // light sage
    case "moderate":
      return "rgba(212, 160, 23, 0.15)"; // light yellow
    case "high":
      return "rgba(221, 118, 49, 0.15)"; // light orange
    case "extreme":
      return "rgba(187, 59, 14, 0.15)"; // light rust
  }
}

// Get border color based on disparity magnitude
export function getDisparityBorderColor(disparity: number | null | undefined): string {
  const level = getDisparityLevel(disparity);

  switch (level) {
    case "aligned":
      return "rgba(112, 129, 96, 0.4)";
    case "moderate":
      return "rgba(212, 160, 23, 0.4)";
    case "high":
      return "rgba(221, 118, 49, 0.4)";
    case "extreme":
      return "rgba(187, 59, 14, 0.4)";
  }
}

// Get a label describing the disparity level
export function getDisparityLabel(disparity: number | null | undefined): string {
  const level = getDisparityLevel(disparity);

  switch (level) {
    case "aligned":
      return "Aligned with users";
    case "moderate":
      return "Moderate divergence";
    case "high":
      return "High divergence";
    case "extreme":
      return "Major divergence";
  }
}

// Format disparity value with + sign for positive
export function formatDisparity(value: number | null | undefined): string {
  if (value == null) return "N/A";
  const num = Number(value);
  return `${num > 0 ? "+" : ""}${num.toFixed(1)}`;
}

// Prefer combined disparity when both sources are available.
export function getDisplayDisparity(
  steamDisparity: number | null | undefined,
  metacriticDisparity: number | null | undefined
): number | null {
  if (steamDisparity != null && metacriticDisparity != null) {
    return (Number(steamDisparity) + Number(metacriticDisparity)) / 2;
  }
  return steamDisparity ?? metacriticDisparity ?? null;
}
