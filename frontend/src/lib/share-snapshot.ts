import type { DisparitySnapshot } from "../types";

export function hashSnapshotKey(value: string): string {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export function deriveSourceScoreFromDisparity(
  criticScore: number | null | undefined,
  disparity: number | null | undefined
): number | null {
  if (criticScore == null || disparity == null) return null;
  return Number(criticScore) - Number(disparity);
}

export function encodeSnapshotMetric(value: number | null | undefined, digits = 2): string {
  if (value == null) return "na";
  return Number(value).toFixed(digits);
}

export function readSnapshotMetric(rawValue?: string | null): number | null | undefined {
  if (rawValue == null) return undefined;
  const normalized = rawValue.trim().toLowerCase();
  if (!normalized || normalized === "na") return null;
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed)) return undefined;
  return parsed;
}

export function readSnapshotCount(rawValue?: string | null): number | undefined {
  if (rawValue == null) return undefined;
  const parsed = Number.parseInt(rawValue, 10);
  if (!Number.isFinite(parsed) || parsed < 0) return undefined;
  return parsed;
}

export function encodeSnapshotCount(value: number | null | undefined): string | undefined {
  if (value == null) return undefined;
  const rounded = Math.round(Number(value));
  if (!Number.isFinite(rounded) || rounded < 0) return undefined;
  return String(rounded);
}

export function formatSnapshotDisplay(value: number | null | undefined, digits = 0): string {
  if (value == null) return "N/A";
  return Number(value).toFixed(digits);
}

const TREND_SNAPSHOT_MAX_POINTS = 16;

function compressTrendSnapshotPoints(points: number[], maxPoints = TREND_SNAPSHOT_MAX_POINTS): number[] {
  const normalized = points
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value))
    .map((value) => Number(value.toFixed(1)));

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

export function toTrendSnapshot(
  history: DisparitySnapshot[],
  maxPoints = TREND_SNAPSHOT_MAX_POINTS
): number[] {
  if (!history || history.length === 0) return [];

  const points = history
    .map((snapshot) => {
      const combined = snapshot.avg_disparity_combined != null
        ? Number(snapshot.avg_disparity_combined)
        : snapshot.avg_disparity_steam != null && snapshot.avg_disparity_metacritic != null
          ? (Number(snapshot.avg_disparity_steam) + Number(snapshot.avg_disparity_metacritic)) / 2
          : snapshot.avg_disparity_steam ?? snapshot.avg_disparity_metacritic ?? null;
      if (combined == null || !Number.isFinite(Number(combined))) return null;
      return Number(Number(combined).toFixed(1));
    })
    .filter((value): value is number => value != null);

  return compressTrendSnapshotPoints(points, maxPoints);
}

export function encodeTrendSnapshot(
  points: number[],
  maxPoints = TREND_SNAPSHOT_MAX_POINTS
): string {
  const normalized = compressTrendSnapshotPoints(points, maxPoints)
    .map((value) => Number(value).toFixed(1));
  return normalized.join(",");
}

export function readTrendSnapshot(
  rawValue?: string | null,
  maxPoints = TREND_SNAPSHOT_MAX_POINTS
): number[] | undefined {
  if (rawValue == null) return undefined;
  const trimmed = rawValue.trim();
  if (!trimmed) return [];

  const values = trimmed
    .split(",")
    .map((token) => Number(token))
    .filter((value) => Number.isFinite(value))
    .map((value) => Number(Number(value).toFixed(1)));

  return values.slice(-Math.max(1, maxPoints));
}
