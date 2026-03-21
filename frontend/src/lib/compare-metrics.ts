export type CompareType = "journalists" | "outlets" | "games";

export type CompareMetricId =
  | "avg_disparity"
  | "review_count"
  | "avg_score"
  | "current_players"
  | "all_time_peak_players"
  | "steam_user_score"
  | "metacritic_user_score"
  | "player_count_trend"
  | "disparity_trend";

export interface CompareMetricOption {
  id: CompareMetricId;
  label: string;
}

const EMPTY_COMPARE_METRIC_SELECTION = "none";

const COMMON_COMPARE_METRICS: CompareMetricOption[] = [
  { id: "avg_disparity", label: "Avg Disparity" },
  { id: "review_count", label: "Reviews" },
  { id: "avg_score", label: "Avg Score" },
  { id: "disparity_trend", label: "Disparity Trend" },
];

const GAME_COMPARE_METRICS: CompareMetricOption[] = [
  { id: "avg_disparity", label: "Avg Disparity" },
  { id: "avg_score", label: "Avg Critic Score" },
  { id: "steam_user_score", label: "Steam User Score" },
  { id: "metacritic_user_score", label: "Metacritic User Score" },
  { id: "current_players", label: "Current Player Count" },
  { id: "all_time_peak_players", label: "All-Time Peak Player Count" },
  { id: "player_count_trend", label: "Player Count Trend" },
  { id: "disparity_trend", label: "Disparity Trend" },
];

export function getCompareMetricOptions(type: CompareType): CompareMetricOption[] {
  return type === "games" ? GAME_COMPARE_METRICS : COMMON_COMPARE_METRICS;
}

export function parseCompareMetricSelection(
  type: CompareType,
  rawMetrics?: string | null
): CompareMetricId[] {
  const allowed = new Set(getCompareMetricOptions(type).map((metric) => metric.id));
  const fallback = getCompareMetricOptions(type).map((metric) => metric.id);

  if (!rawMetrics?.trim()) {
    return fallback;
  }

  if (rawMetrics.trim() === EMPTY_COMPARE_METRIC_SELECTION) {
    return [];
  }

  const selected: CompareMetricId[] = [];
  const seen = new Set<CompareMetricId>();

  for (const token of rawMetrics.split(",")) {
    const metricId = token.trim() as CompareMetricId;
    if (!allowed.has(metricId) || seen.has(metricId)) continue;
    seen.add(metricId);
    selected.push(metricId);
  }

  return selected.length > 0 ? selected : fallback;
}

export function serializeCompareMetricSelection(
  type: CompareType,
  metricIds: CompareMetricId[]
): string | undefined {
  const defaults = getCompareMetricOptions(type).map((metric) => metric.id);
  const allowed = new Set(defaults);
  const requested = new Set(
    metricIds.filter((metricId): metricId is CompareMetricId => allowed.has(metricId))
  );
  const normalized = defaults.filter((metricId) => requested.has(metricId));

  if (normalized.length === 0) {
    return EMPTY_COMPARE_METRIC_SELECTION;
  }

  if (
    normalized.length === defaults.length
    && normalized.every((metricId, index) => metricId === defaults[index])
  ) {
    return undefined;
  }

  return normalized.join(",");
}
