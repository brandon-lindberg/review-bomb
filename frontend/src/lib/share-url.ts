import {
  encodeSnapshotCount,
  encodeSnapshotMetric,
} from "./share-snapshot";
import { buildEntityPath, type EntityRouteType } from "./entity-paths";
import { serializeCompareMetricSelection, type CompareMetricId } from "./compare-metrics";

export type SnapshotMode = "default" | "chart" | "timing";

interface SnapshotShareQueryInput {
  card: string;
  version: string;
  critic: number | null | undefined;
  steam: number | null | undefined;
  metacritic: number | null | undefined;
  disparity: number | null | undefined;
  mode?: SnapshotMode;
  trend?: string;
  early?: number | null | undefined;
  launch?: number | null | undefined;
  late?: number | null | undefined;
  nonce?: string;
}

interface TrendSnapshotUrlInput {
  trend: string;
  window?: string;
  series?: string;
}

interface CompareShareQueryInput {
  type: "journalists" | "outlets" | "games";
  card: string;
  ids?: number[];
  labels?: string[];
  metrics?: CompareMetricId[];
  snapshotPayload?: string;
}

export function buildSnapshotShareParams(input: SnapshotShareQueryInput): URLSearchParams {
  const params = new URLSearchParams({
    card: input.card,
    v: input.version,
    critic: encodeSnapshotMetric(input.critic),
    steam: encodeSnapshotMetric(input.steam),
    mc: encodeSnapshotMetric(input.metacritic),
    disp: encodeSnapshotMetric(input.disparity),
  });

  const mode = input.mode ?? "default";
  if (mode !== "default") {
    params.set("mode", mode);
  }

  const nonce = input.nonce?.trim();
  if (nonce) {
    params.set("sx", nonce.slice(0, 24));
  }

  const trend = input.trend?.trim();
  if (trend) {
    params.set("t", trend);
  }

  if (mode === "timing") {
    const early = encodeSnapshotCount(input.early);
    const launch = encodeSnapshotCount(input.launch);
    const late = encodeSnapshotCount(input.late);
    if (early !== undefined) params.set("early", early);
    if (launch !== undefined) params.set("launch", launch);
    if (late !== undefined) params.set("late", late);
  }

  return params;
}

export function buildEntitySnapshotShareUrl(
  siteUrl: string,
  entityType: EntityRouteType,
  entityLabel: string,
  publicId: string,
  input: SnapshotShareQueryInput
): string {
  return `${siteUrl}${buildEntityPath(entityType, entityLabel, publicId)}?${buildSnapshotShareParams(input).toString()}`;
}

export function buildCompareShareParams(input: CompareShareQueryInput): URLSearchParams {
  const params = new URLSearchParams({
    type: input.type,
    card: input.card,
  });

  if (input.ids && input.ids.length > 0) {
    params.set("ids", input.ids.join(","));
  }
  if (input.labels && input.labels.length > 0) {
    params.set("labels", input.labels.join("|"));
  }
  const serializedMetrics = input.metrics
    ? serializeCompareMetricSelection(input.type, input.metrics)
    : undefined;
  if (serializedMetrics) {
    params.set("metrics", serializedMetrics);
  }
  if (input.snapshotPayload && input.snapshotPayload.trim()) {
    params.set("snap", input.snapshotPayload.trim());
  }

  return params;
}

export function buildCompareShareUrl(siteUrl: string, input: CompareShareQueryInput): string {
  return `${siteUrl}/compare?${buildCompareShareParams(input).toString()}`;
}

export function withSnapshotNonce(url: string, nonce: string): string {
  try {
    const parsed = new URL(url);
    parsed.searchParams.set("sx", nonce);
    return parsed.toString();
  } catch {
    return url;
  }
}

export function withTrendSnapshot(url: string, input: TrendSnapshotUrlInput): string {
  try {
    const parsed = new URL(url);
    const trend = input.trend.trim();

    if (trend) parsed.searchParams.set("t", trend);
    else parsed.searchParams.delete("t");

    const window = input.window?.trim();
    if (window) parsed.searchParams.set("tw", window);
    else parsed.searchParams.delete("tw");

    const series = input.series?.trim();
    if (series) parsed.searchParams.set("ts", series);
    else parsed.searchParams.delete("ts");

    return parsed.toString();
  } catch {
    return url;
  }
}

export function buildRedditShareUrl(url: string, text: string, nonce?: string): string {
  const sharedUrl = nonce ? withSnapshotNonce(url, nonce) : url;
  return `https://reddit.com/submit?${new URLSearchParams({ url: sharedUrl, title: text }).toString()}`;
}

export function buildXIntentUrl(url: string, text: string, nonce: string): string {
  const sharedUrl = withSnapshotNonce(url, nonce);
  return `https://twitter.com/intent/tweet?${new URLSearchParams({ text, url: sharedUrl }).toString()}`;
}
