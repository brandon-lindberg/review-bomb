import type { SteamPlayerPoint } from "@/types";

export const PLAYER_COUNT_SNAPSHOT_MAX_POINTS = 24;

export function compressPlayerCountSeries(
  values: Array<number | null | undefined>,
  maxPoints = PLAYER_COUNT_SNAPSHOT_MAX_POINTS
): number[] {
  const normalized = values
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value) && value >= 0)
    .map((value) => Math.round(value));

  const limit = Math.max(1, maxPoints);
  if (normalized.length <= limit) return normalized;
  if (limit === 1) return [normalized[normalized.length - 1]];

  const sampled: number[] = [];
  const lastIndex = normalized.length - 1;

  for (let index = 0; index < limit; index += 1) {
    const sourceIndex = Math.round((index / (limit - 1)) * lastIndex);
    sampled.push(normalized[sourceIndex]);
  }

  return sampled;
}

export function toPlayerCountTrend(
  points: SteamPlayerPoint[],
  maxPoints = PLAYER_COUNT_SNAPSHOT_MAX_POINTS
): number[] {
  return compressPlayerCountSeries(
    points.map((point) => point.latest_players ?? point.observed_24h_high),
    maxPoints
  );
}

export function buildSparklinePath(
  values: number[],
  width: number,
  height: number,
  padding = 4
): string {
  if (values.length === 0) return "";
  if (values.length === 1) {
    const y = height / 2;
    return `M ${padding} ${y} L ${width - padding} ${y}`;
  }

  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const valueRange = maxValue - minValue || 1;
  const usableWidth = width - padding * 2;
  const usableHeight = height - padding * 2;

  const points = values.map((value, index) => {
    const x = padding + (usableWidth * index) / Math.max(values.length - 1, 1);
    const normalized = (value - minValue) / valueRange;
    const y = padding + usableHeight - normalized * usableHeight;
    return { x, y };
  });

  if (points.length === 2) {
    return `M ${points[0].x} ${points[0].y} L ${points[1].x} ${points[1].y}`;
  }

  let path = `M ${points[0].x} ${points[0].y}`;
  for (let index = 1; index < points.length - 1; index += 1) {
    const current = points[index];
    const next = points[index + 1];
    const midX = (current.x + next.x) / 2;
    const midY = (current.y + next.y) / 2;
    path += ` Q ${current.x} ${current.y} ${midX} ${midY}`;
  }

  const lastPoint = points[points.length - 1];
  path += ` T ${lastPoint.x} ${lastPoint.y}`;
  return path;
}

export function formatCompactPlayerCount(value: number | null | undefined): string {
  if (value == null) return "N/A";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "N/A";
  if (numeric >= 1_000_000) {
    return `${(numeric / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  }
  if (numeric >= 1_000) {
    return `${(numeric / 1_000).toFixed(1).replace(/\.0$/, "")}k`;
  }
  return Math.round(numeric).toLocaleString();
}
