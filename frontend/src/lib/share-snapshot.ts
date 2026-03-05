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

export function formatSnapshotDisplay(value: number | null | undefined, digits = 0): string {
  if (value == null) return "N/A";
  return Number(value).toFixed(digits);
}
