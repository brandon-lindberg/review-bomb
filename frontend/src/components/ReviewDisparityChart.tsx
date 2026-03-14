"use client";

import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import {
  ComposedChart,
  Line,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
} from "recharts";
import type { ReviewWithDisparity, ReviewWithJournalist } from "@/types";
import { encodeTrendSnapshot } from "@/lib/share-snapshot";

// Hook to detect dark mode
function useIsDarkMode() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const checkDarkMode = () => {
      setIsDark(document.documentElement.classList.contains("dark"));
    };

    checkDarkMode();

    const observer = new MutationObserver(checkDarkMode);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    return () => observer.disconnect();
  }, []);

  return isDark;
}

// Theme colors
const getThemeColors = (isDark: boolean) => ({
  rust: isDark ? "#E05A2B" : "#BB3B0E",
  orange: isDark ? "#E8904D" : "#DD7631",
  sage: isDark ? "#8FA87A" : "#708160",
  tan: isDark ? "#E5D9B3" : "#D8C593",
  grid: isDark ? "#3D3A35" : "#e5e7eb",
  axis: isDark ? "#6A655C" : "#9ca3af",
  text: isDark ? "#B8B4AC" : "#6b7280",
  background: isDark ? "#2D2A26" : "#ffffff",
  border: isDark ? "#3D3A35" : "#e5e7eb",
});

type DisparityType = "steam" | "metacritic" | "combined";
type PointPosition = { x: number; y: number };
type PointPositionsByType = Partial<Record<DisparityType, PointPosition>>;
type SecondaryMapKind = "release" | "score";
type TrendRange = "pre" | "1m" | "3m" | "6m" | "1y" | "3y" | "max";
type SecondaryMapPoint = {
  x: number;
  disparity: number;
  point: ChartDataPoint;
  type: DisparityType;
  axisValue: number;
};
type TrendSpanSegment = {
  type: DisparityType;
  start: { x: number; y: number };
  end: { x: number; y: number };
};
type TrendShareState = {
  trend: string;
  window: TrendRange;
  windowLabel: string;
  series: DisparityType;
  seriesLabel: string;
};

// Union type for both review types
type ReviewData = ReviewWithDisparity | ReviewWithJournalist;

// Type guard to check if it's ReviewWithDisparity (has game_title)
function isReviewWithDisparity(review: ReviewData): review is ReviewWithDisparity {
  return "game_title" in review;
}

// Type guard to check if it's ReviewWithJournalist
function isReviewWithJournalist(review: ReviewData): review is ReviewWithJournalist {
  return "journalist_name" in review;
}

interface ChartDataPoint {
  date: number; // timestamp for sorting
  dateLabel: string;
  index: number; // unique index for identification
  // All disparity values
  steamDisparity: number | null;
  metacriticDisparity: number | null;
  combinedDisparity: number | null;
  // Rolling averages for each type
  steamRollingAvg?: number | null;
  metacriticRollingAvg?: number | null;
  combinedRollingAvg?: number | null;
  daysFromRelease?: number | null;
  reviewTiming?: string;
  // Context info for tooltip
  gameName?: string;
  journalistName?: string;
  outletName?: string | null;
  criticScore?: number | null;
}

function isFiniteChartNumber(value: number | null | undefined): value is number {
  return value != null && Number.isFinite(value);
}

function getDisparityValue(point: ChartDataPoint, type: DisparityType): number | null {
  if (type === "steam") return point.steamDisparity;
  if (type === "metacritic") return point.metacriticDisparity;
  return point.combinedDisparity;
}

function getTrendValue(point: ChartDataPoint, type: DisparityType): number | null {
  if (type === "steam") return point.steamRollingAvg ?? null;
  if (type === "metacritic") return point.metacriticRollingAvg ?? null;
  return point.combinedRollingAvg ?? null;
}

function toUtcDateOnlyTimestamp(value: string): number | null {
  if (!value) return null;

  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split("-").map(Number);
    return Date.UTC(year, month - 1, day);
  }

  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
}

function calculateDaysFromRelease(publishedAt: string | null | undefined, releaseDate: string | null | undefined): number | null {
  if (!publishedAt || !releaseDate) return null;

  const publishedTs = toUtcDateOnlyTimestamp(publishedAt);
  const releaseTs = toUtcDateOnlyTimestamp(releaseDate);
  if (publishedTs == null || releaseTs == null) return null;

  return Math.round((publishedTs - releaseTs) / 86400000);
}

function formatDaysFromRelease(daysFromRelease: number | null | undefined): string | null {
  if (daysFromRelease == null) return null;
  if (daysFromRelease === 0) return "Release day";
  if (daysFromRelease > 0) return `Day +${daysFromRelease}`;
  return `Day ${daysFromRelease}`;
}

const TRAILING_TREND_RANGE_OPTIONS: Array<{ value: Exclude<TrendRange, "pre">; label: string }> = [
  { value: "1m", label: "1M" },
  { value: "3m", label: "3M" },
  { value: "6m", label: "6M" },
  { value: "1y", label: "1Y" },
  { value: "3y", label: "3Y" },
  { value: "max", label: "MAX" },
];

const GAME_TREND_RANGE_OPTIONS: Array<{ value: TrendRange; label: string }> = [
  { value: "pre", label: "PRE" },
  ...TRAILING_TREND_RANGE_OPTIONS,
];

const TREND_SERIES_PRIORITY: DisparityType[] = ["combined", "steam", "metacritic"];
const TREND_SERIES_LABELS: Record<DisparityType, string> = {
  combined: "Combined",
  steam: "Steam",
  metacritic: "Metacritic",
};

function getTrendRangeStartTimestamp(latestTimestamp: number, range: TrendRange): number | null {
  if (range === "max" || range === "pre") return null;

  const date = new Date(latestTimestamp);
  const start = new Date(latestTimestamp);

  if (range === "1m") start.setMonth(date.getMonth() - 1);
  if (range === "3m") start.setMonth(date.getMonth() - 3);
  if (range === "6m") start.setMonth(date.getMonth() - 6);
  if (range === "1y") start.setFullYear(date.getFullYear() - 1);
  if (range === "3y") start.setFullYear(date.getFullYear() - 3);

  return start.getTime();
}

function withRollingAverages(data: ChartDataPoint[], windowSize: number): ChartDataPoint[] {
  const processed = data.map((point) => ({
    ...point,
    steamRollingAvg: null,
    metacriticRollingAvg: null,
    combinedRollingAvg: null,
  }));

  calculateRollingAverageForField(
    processed,
    windowSize,
    (p) => p.steamDisparity,
    (p, val) => { p.steamRollingAvg = val; }
  );
  calculateRollingAverageForField(
    processed,
    windowSize,
    (p) => p.metacriticDisparity,
    (p, val) => { p.metacriticRollingAvg = val; }
  );
  calculateRollingAverageForField(
    processed,
    windowSize,
    (p) => p.combinedDisparity,
    (p, val) => { p.combinedRollingAvg = val; }
  );

  return processed;
}

function buildSecondaryMapData(
  data: ChartDataPoint[],
  type: DisparityType,
  kind: SecondaryMapKind
): SecondaryMapPoint[] {
  const groups = new Map<number, Array<{ point: ChartDataPoint; disparity: number }>>();
  const seriesOffset = kind === "release"
    ? type === "steam" ? -0.18 : type === "metacritic" ? 0 : 0.18
    : type === "steam" ? -0.32 : type === "metacritic" ? 0 : 0.32;

  data.forEach((point) => {
    const disparity = getDisparityValue(point, type);
    const axisValue = kind === "release"
      ? point.daysFromRelease
      : point.criticScore != null
        ? Math.round(point.criticScore)
        : null;

    if (!isFiniteChartNumber(disparity) || !isFiniteChartNumber(axisValue)) return;

    const group = groups.get(axisValue) ?? [];
    group.push({ point, disparity });
    groups.set(axisValue, group);
  });

  const mapPoints: SecondaryMapPoint[] = [];

  for (const [axisValue, entries] of Array.from(groups.entries()).sort((a, b) => a[0] - b[0])) {
    const sortedEntries = entries
      .slice()
      .sort((a, b) => a.disparity - b.disparity || a.point.index - b.point.index);

    const spread = sortedEntries.length <= 1
      ? 0
      : kind === "release"
        ? Math.min(0.86, Math.max(0.24, (sortedEntries.length - 1) * 0.045))
        : Math.min(0.92, Math.max(0.28, (sortedEntries.length - 1) * 0.06));
    const step = sortedEntries.length <= 1 ? 0 : spread / (sortedEntries.length - 1);

    sortedEntries.forEach((entry, entryIndex) => {
      const centeredOffset = sortedEntries.length <= 1
        ? 0
        : -spread / 2 + step * entryIndex;

      mapPoints.push({
        x: axisValue + centeredOffset + seriesOffset,
        disparity: entry.disparity,
        point: entry.point,
        type,
        axisValue,
      });
    });
  }

  return mapPoints;
}

// Calculate rolling average for a specific field
function calculateRollingAverageForField(
  data: ChartDataPoint[],
  windowSize: number,
  getValue: (p: ChartDataPoint) => number | null,
  setValue: (p: ChartDataPoint, val: number | null) => void
): void {
  data.forEach((point, index) => {
    const value = getValue(point);
    if (value === null) {
      setValue(point, null);
      return;
    }

    // Get window of points (up to windowSize previous points including current)
    const start = Math.max(0, index - windowSize + 1);
    const window = data.slice(start, index + 1).filter(p => getValue(p) !== null);

    if (window.length === 0) {
      setValue(point, null);
      return;
    }

    const sum = window.reduce((acc, p) => acc + (getValue(p) || 0), 0);
    setValue(point, sum / window.length);
  });
}

interface ReviewDisparityChartProps {
  reviews: ReviewData[];
  height?: number;
  /**
   * Context determines what info shows in the tooltip:
   * - "journalist": Shows game name (we're on a journalist's page)
   * - "game": Shows journalist name (we're on a game's page)
   * - "outlet": Shows game name + journalist name (we're on an outlet's page)
   */
  context: "journalist" | "game" | "outlet";
  /**
   * For game context, we need to pass the game title since ReviewWithJournalist doesn't have it
   */
  gameTitle?: string;
  onTrendShareStateChange?: (state: TrendShareState | null) => void;
}

type ChartMode = "trend" | "map";

export function ReviewDisparityChart({
  reviews,
  height = 300,
  context,
  gameTitle,
  onTrendShareStateChange,
}: ReviewDisparityChartProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);

  // Track which lines are visible (all enabled by default if they have data)
  const [visibleLines, setVisibleLines] = useState<Record<DisparityType, boolean>>({
    combined: true,
    steam: true,
    metacritic: true,
  });

  const [chartMode, setChartMode] = useState<ChartMode>("trend");
  const [trendRange, setTrendRange] = useState<TrendRange>("max");
  const [hoveredPoint, setHoveredPoint] = useState<ChartDataPoint | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState<{ x: number; y: number; containerWidth: number } | null>(null);
  const chartContainerRef = useRef<HTMLDivElement>(null);

  // Responsive margins - smaller on mobile
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 640);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  // Calculate rolling window size based on data volume
  const rollingWindowSize = useMemo(() => {
    const count = reviews.length;
    if (count > 500) return 30;
    if (count > 200) return 20;
    if (count > 50) return 10;
    return 5;
  }, [reviews.length]);

  // Transform reviews into chart data points with all disparity types
  const chartData = useMemo(() => {
    return reviews
      .filter((review) => review.published_at != null)
      .map((review, idx) => {
        const date = new Date(review.published_at!);
        const steamDisp = review.disparity_steam != null ? Number(review.disparity_steam) : null;
        const mcDisp = review.disparity_metacritic != null ? Number(review.disparity_metacritic) : null;

        // Calculate combined disparity
        let combinedDisp: number | null = null;
        if (steamDisp != null && mcDisp != null) {
          combinedDisp = (steamDisp + mcDisp) / 2;
        } else {
          combinedDisp = steamDisp ?? mcDisp ?? null;
        }

        const point: ChartDataPoint = {
          date: date.getTime(),
          dateLabel: date.toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
          }),
          index: idx,
          steamDisparity: steamDisp,
          metacriticDisparity: mcDisp,
          combinedDisparity: combinedDisp,
          daysFromRelease: calculateDaysFromRelease(review.published_at, review.game_release_date),
          reviewTiming: review.review_timing,
          criticScore: review.score_normalized != null ? Number(review.score_normalized) : null,
          outletName: review.outlet_name,
        };

        // Add context-specific fields
        if (isReviewWithDisparity(review)) {
          point.gameName = review.game_title;
        } else if (isReviewWithJournalist(review) && review.game_title) {
          point.gameName = review.game_title;
        } else if (context === "game" && gameTitle) {
          point.gameName = gameTitle;
        }

        if (isReviewWithJournalist(review)) {
          point.journalistName = review.journalist_name;
        }

        return point;
      })
      .sort((a, b) => a.date - b.date);
  }, [reviews, context, gameTitle]);

  // Check which disparity types have data
  const hasData = useMemo(() => ({
    steam: chartData.some((p) => p.steamDisparity != null),
    metacritic: chartData.some((p) => p.metacriticDisparity != null),
    combined: chartData.some((p) => p.combinedDisparity != null),
  }), [chartData]);

  const visibleTypeCount = useMemo(
    () =>
      (visibleLines.steam && hasData.steam ? 1 : 0)
      + (visibleLines.metacritic && hasData.metacritic ? 1 : 0)
      + (visibleLines.combined && hasData.combined ? 1 : 0),
    [hasData, visibleLines]
  );

  const hasReleaseAnchoredTrend = useMemo(
    () => context === "game" && chartData.some((point) => point.daysFromRelease != null),
    [chartData, context]
  );

  const hasPreReleaseTrendData = useMemo(
    () => hasReleaseAnchoredTrend && chartData.some((point) => (point.daysFromRelease ?? Infinity) < 0),
    [chartData, hasReleaseAnchoredTrend]
  );

  const trendRangeOptions = useMemo(
    () => (hasReleaseAnchoredTrend ? GAME_TREND_RANGE_OPTIONS : TRAILING_TREND_RANGE_OPTIONS),
    [hasReleaseAnchoredTrend]
  );

  const effectiveTrendRange: TrendRange = useMemo(() => {
    if (trendRange === "pre" && !hasReleaseAnchoredTrend) return "max";
    if (trendRange === "pre" && hasReleaseAnchoredTrend && !hasPreReleaseTrendData) return "1m";
    return trendRange;
  }, [hasPreReleaseTrendData, hasReleaseAnchoredTrend, trendRange]);

  const latestTrendTimestamp = useMemo(
    () => (chartData.length > 0 ? chartData[chartData.length - 1].date : null),
    [chartData]
  );

  const trendRangeStart = useMemo(
    () => (latestTrendTimestamp != null ? getTrendRangeStartTimestamp(latestTrendTimestamp, effectiveTrendRange) : null),
    [effectiveTrendRange, latestTrendTimestamp]
  );

  const trendWindowData = useMemo(() => {
    if (hasReleaseAnchoredTrend) {
      const filtered = chartData.filter((point) => {
        if (point.daysFromRelease == null) return false;

        if (effectiveTrendRange === "pre") return point.daysFromRelease < 0;
        if (effectiveTrendRange === "1m") return point.daysFromRelease >= 0 && point.daysFromRelease <= 30;
        if (effectiveTrendRange === "3m") return point.daysFromRelease >= 0 && point.daysFromRelease <= 90;
        if (effectiveTrendRange === "6m") return point.daysFromRelease >= 0 && point.daysFromRelease <= 180;
        if (effectiveTrendRange === "1y") return point.daysFromRelease >= 0 && point.daysFromRelease <= 365;
        if (effectiveTrendRange === "3y") return point.daysFromRelease >= 0 && point.daysFromRelease <= 1095;
        return true;
      });

      if (filtered.length > 0) return filtered;
      return [];
    }

    if (trendRangeStart == null) return chartData;

    const filtered = chartData.filter((point) => point.date >= trendRangeStart);
    return filtered.length > 0 ? filtered : chartData.slice(-1);
  }, [chartData, effectiveTrendRange, hasReleaseAnchoredTrend, trendRangeStart]);

  const trendChartData = useMemo(
    () => withRollingAverages(trendWindowData, rollingWindowSize),
    [rollingWindowSize, trendWindowData]
  );

  const trendSummaryText = useMemo(() => {
    if (hasReleaseAnchoredTrend) {
      if (effectiveTrendRange === "pre") return "Viewing pre-release reviews only.";
      if (effectiveTrendRange === "1m") return "Viewing the first 30 days after release.";
      if (effectiveTrendRange === "3m") return "Viewing the first 90 days after release.";
      if (effectiveTrendRange === "6m") return "Viewing the first 180 days after release.";
      if (effectiveTrendRange === "1y") return "Viewing the first year after release.";
      if (effectiveTrendRange === "3y") return "Viewing the first 3 years after release.";
      return "Viewing the full review history.";
    }

    if (latestTrendTimestamp == null) return null;
    const selectedRangeLabel = trendRangeOptions.find((option) => option.value === effectiveTrendRange)?.label ?? effectiveTrendRange.toUpperCase();
    return `Viewing ${effectiveTrendRange === "max" ? "the full review history" : `the last ${selectedRangeLabel}`} ending ${new Date(latestTrendTimestamp).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    })}.`;
  }, [effectiveTrendRange, hasReleaseAnchoredTrend, latestTrendTimestamp, trendRangeOptions]);

  const trendShareState = useMemo<TrendShareState | null>(() => {
    const selectedSeries = TREND_SERIES_PRIORITY.find((type) =>
      visibleLines[type] && trendChartData.some((point) => isFiniteChartNumber(getTrendValue(point, type)))
    );

    if (!selectedSeries) return null;

    const trendPoints = trendChartData
      .map((point) => getTrendValue(point, selectedSeries))
      .filter((value): value is number => isFiniteChartNumber(value));

    if (trendPoints.length < 2) return null;

    const trend = encodeTrendSnapshot(trendPoints);
    if (!trend) return null;

    const windowLabel = trendRangeOptions.find((option) => option.value === effectiveTrendRange)?.label ?? effectiveTrendRange.toUpperCase();

    return {
      trend,
      window: effectiveTrendRange,
      windowLabel,
      series: selectedSeries,
      seriesLabel: TREND_SERIES_LABELS[selectedSeries],
    };
  }, [effectiveTrendRange, trendChartData, trendRangeOptions, visibleLines]);

  useEffect(() => {
    onTrendShareStateChange?.(trendShareState);
  }, [onTrendShareStateChange, trendShareState]);

  const trendWindowSpanSegments = useMemo<TrendSpanSegment[]>(() => {
    if (!(chartMode === "trend" && hasReleaseAnchoredTrend)) return [];

    return (["steam", "metacritic", "combined"] as DisparityType[]).flatMap((type) => {
      if (!visibleLines[type]) return [];

      const seriesPoints = trendChartData.filter((point) => isFiniteChartNumber(getDisparityValue(point, type)));
      if (seriesPoints.length < 2) return [];

      const firstPoint = seriesPoints[0];
      const lastPoint = seriesPoints[seriesPoints.length - 1];
      const firstValue = getDisparityValue(firstPoint, type);
      const lastValue = getDisparityValue(lastPoint, type);
      if (!isFiniteChartNumber(firstValue) || !isFiniteChartNumber(lastValue)) return [];

      return [{
        type,
        start: { x: firstPoint.date, y: firstValue },
        end: { x: lastPoint.date, y: lastValue },
      }];
    });
  }, [chartMode, hasReleaseAnchoredTrend, trendChartData, visibleLines]);

  const secondaryMapKind: SecondaryMapKind = context === "game" ? "release" : "score";
  const secondaryMapLabel = secondaryMapKind === "release" ? "Release Map" : "Score Map";

  const secondaryMapData = useMemo(
    () => ({
      steam: buildSecondaryMapData(chartData, "steam", secondaryMapKind),
      metacritic: buildSecondaryMapData(chartData, "metacritic", secondaryMapKind),
      combined: buildSecondaryMapData(chartData, "combined", secondaryMapKind),
    }),
    [chartData, secondaryMapKind]
  );

  const plottedReviewIndexes = useMemo(() => {
    const indexes = new Set<number>();
    if (visibleLines.steam) secondaryMapData.steam.forEach((item) => indexes.add(item.point.index));
    if (visibleLines.metacritic) secondaryMapData.metacritic.forEach((item) => indexes.add(item.point.index));
    if (visibleLines.combined) secondaryMapData.combined.forEach((item) => indexes.add(item.point.index));
    return indexes;
  }, [secondaryMapData, visibleLines]);

  const plottedReviewCount = useMemo(
    () => plottedReviewIndexes.size,
    [plottedReviewIndexes]
  );

  const plottedPointCount = useMemo(
    () =>
      (visibleLines.steam ? secondaryMapData.steam.length : 0)
      + (visibleLines.metacritic ? secondaryMapData.metacritic.length : 0)
      + (visibleLines.combined ? secondaryMapData.combined.length : 0),
    [secondaryMapData, visibleLines]
  );

  const hiddenReviewCount = Math.max(0, reviews.length - plottedReviewCount);

  const hasVisibleTrendData = useMemo(
    () => trendChartData.some((point) =>
      (visibleLines.steam && isFiniteChartNumber(point.steamRollingAvg))
      || (visibleLines.metacritic && isFiniteChartNumber(point.metacriticRollingAvg))
      || (visibleLines.combined && isFiniteChartNumber(point.combinedRollingAvg))
    ),
    [trendChartData, visibleLines]
  );

  const mapPointStyle = useMemo(() => {
    const pointLoad = plottedPointCount || chartData.length * Math.max(1, visibleTypeCount);

    if (pointLoad > 2500) {
      return { pointRadius: 1.75, pointOpacity: 0.18, hoverRadius: 6 };
    }
    if (pointLoad > 1200) {
      return { pointRadius: 2.25, pointOpacity: 0.22, hoverRadius: 6.5 };
    }
    if (pointLoad > 500) {
      return { pointRadius: 2.75, pointOpacity: 0.28, hoverRadius: 7 };
    }

    return { pointRadius: 3.25, pointOpacity: 0.38, hoverRadius: 7.5 };
  }, [chartData.length, plottedPointCount, visibleTypeCount]);

  // Calculate domain bounds for scaling
  const { xDomain, yDomain } = useMemo(() => {
    const visibleChartData = chartMode === "trend" ? trendChartData : chartData;
    const disparities: number[] = [];
    visibleChartData.forEach(d => {
      if (chartMode === "trend") {
        if (visibleLines.steam && d.steamRollingAvg != null) disparities.push(d.steamRollingAvg);
        if (visibleLines.metacritic && d.metacriticRollingAvg != null) disparities.push(d.metacriticRollingAvg);
        if (visibleLines.combined && d.combinedRollingAvg != null) disparities.push(d.combinedRollingAvg);
        return;
      }

      if (visibleLines.steam && d.steamDisparity != null) disparities.push(d.steamDisparity);
      if (visibleLines.metacritic && d.metacriticDisparity != null) disparities.push(d.metacriticDisparity);
      if (visibleLines.combined && d.combinedDisparity != null) disparities.push(d.combinedDisparity);
    });

    if (disparities.length === 0) return { xDomain: [0, 1], yDomain: [-10, 10] };

    const minDisp = Math.min(...disparities);
    const maxDisp = Math.max(...disparities);
    const yRange = maxDisp - minDisp || 20;
    const yPadding = Math.max(yRange * 0.12, 8);

    if (chartMode === "map") {
      const mapXs: number[] = [];
      if (visibleLines.steam) mapXs.push(...secondaryMapData.steam.map((point) => point.x));
      if (visibleLines.metacritic) mapXs.push(...secondaryMapData.metacritic.map((point) => point.x));
      if (visibleLines.combined) mapXs.push(...secondaryMapData.combined.map((point) => point.x));

      if (mapXs.length === 0) return { xDomain: [-1, 1], yDomain: [minDisp - yPadding, maxDisp + yPadding] };

      const minX = secondaryMapKind === "release"
        ? Math.min(...mapXs, 0)
        : Math.max(0, Math.min(...mapXs) - 3);
      const maxX = secondaryMapKind === "release"
        ? Math.max(...mapXs, 0)
        : Math.min(100, Math.max(...mapXs) + 3);
      const xRange = maxX - minX || (secondaryMapKind === "release" ? 6 : 20);
      const xPadding = secondaryMapKind === "release"
        ? Math.max(xRange * 0.05, 1.5)
        : 0;

      return {
        xDomain: [minX - xPadding, maxX + xPadding],
        yDomain: [minDisp - yPadding, maxDisp + yPadding],
      };
    }

    if (visibleChartData.length === 0) return { xDomain: [0, 1], yDomain: [-10, 10] };

    const dates = visibleChartData.map(d => d.date);
    const minDate = Math.min(...dates);
    const maxDate = Math.max(...dates);
    const dateRange = maxDate - minDate || 86400000;
    const xPadding = Math.max(dateRange * 0.05, 86400000);

    return {
      xDomain: [minDate - xPadding, maxDate + xPadding],
      yDomain: [minDisp - yPadding, maxDisp + yPadding],
    };
  }, [chartData, chartMode, secondaryMapData, secondaryMapKind, trendChartData, visibleLines]);

  // Store point positions after rendering
  const pointPositionsRef = useRef<Map<number, PointPositionsByType>>(new Map());

  const resetHoverState = useCallback(() => {
    pointPositionsRef.current.clear();
    setHoveredPoint(null);
    setTooltipPosition(null);
  }, []);

  const setPointPosition = useCallback((index: number, type: DisparityType, x?: number, y?: number) => {
    if (!isFiniteChartNumber(x) || !isFiniteChartNumber(y)) return;

    const existing = pointPositionsRef.current.get(index) ?? {};
    existing[type] = { x, y };
    pointPositionsRef.current.set(index, existing);
  }, []);

  // Handle mouse move to find closest point
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (chartMode !== "map" || !chartContainerRef.current || chartData.length === 0) return;

    const rect = chartContainerRef.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    let closestPoint: ChartDataPoint | null = null;
    let closestDistance = Infinity;

    for (const point of chartData) {
      // Only consider points that have at least one visible disparity
      const hasVisibleData =
        (visibleLines.steam && point.steamDisparity !== null) ||
        (visibleLines.metacritic && point.metacriticDisparity !== null) ||
        (visibleLines.combined && point.combinedDisparity !== null);

      if (!hasVisibleData) continue;

      const positions = pointPositionsRef.current.get(point.index);
      if (!positions) continue;

      for (const type of ["steam", "metacritic", "combined"] as DisparityType[]) {
        if (!visibleLines[type]) continue;
        const pos = positions[type];
        if (!pos) continue;

        const dx = mouseX - pos.x;
        const dy = mouseY - pos.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance < closestDistance) {
          closestDistance = distance;
          closestPoint = point;
        }
      }
    }

    if (closestPoint && closestDistance < 50) {
      setHoveredPoint(closestPoint);
      setTooltipPosition({ x: mouseX, y: mouseY, containerWidth: rect.width });
    } else {
      setHoveredPoint(null);
      setTooltipPosition(null);
    }
  }, [chartData, chartMode, visibleLines]);

  const handleMouseLeave = useCallback(() => {
    resetHoverState();
  }, [resetHoverState]);

  // Toggle line visibility
  const toggleLine = (type: DisparityType) => {
    if (!hasData[type]) return;
    resetHoverState();
    setVisibleLines(prev => ({ ...prev, [type]: !prev[type] }));
  };

  const changeChartMode = (mode: ChartMode) => {
    resetHoverState();
    setChartMode(mode);
  };

  if (!reviews || reviews.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px] text-gray-500">
        No review data available for chart
      </div>
    );
  }

  const hasAnyData = hasData.steam || hasData.metacritic || hasData.combined;
  if (!hasAnyData) {
    return (
      <div className="flex items-center justify-center h-[200px] text-gray-500">
        No disparity data available for chart
      </div>
    );
  }

  // Check if at least one line is visible
  const hasVisibleLine =
    (visibleLines.steam && hasData.steam) ||
    (visibleLines.metacritic && hasData.metacritic) ||
    (visibleLines.combined && hasData.combined);
  const effectiveHeight = chartMode === "map"
    ? Math.max(height, secondaryMapKind === "release" ? 360 : 420)
    : height;

  // Render custom tooltip
  const renderTooltip = () => {
    if (chartMode !== "map" || !hoveredPoint || !tooltipPosition) return null;

    const data = hoveredPoint;

    const tooltipWidth = 220;
    let tooltipX = tooltipPosition.x + 15;
    const tooltipY = tooltipPosition.y - 10;

    if (tooltipX > tooltipPosition.containerWidth - tooltipWidth) {
      tooltipX = tooltipPosition.x - (tooltipWidth + 15);
    }

    return (
      <div
        className="absolute z-50 p-3 rounded-lg shadow-lg text-sm pointer-events-none"
        style={{
          left: tooltipX,
          top: tooltipY,
          backgroundColor: colors.background,
          border: `1px solid ${colors.border}`,
          maxWidth: 220,
        }}
      >
        {/* Primary info based on context */}
        {context === "journalist" && data.gameName && (
          <p className="font-medium" style={{ color: colors.text }}>
            {data.gameName}
          </p>
        )}
        {context === "game" && data.journalistName && (
          <p className="font-medium" style={{ color: colors.text }}>
            {data.journalistName}
            {data.outletName && (
              <span className="font-normal" style={{ color: colors.axis }}>
                {" "}at {data.outletName}
              </span>
            )}
          </p>
        )}
        {context === "outlet" && (
          <>
            {data.gameName && (
              <p className="font-medium" style={{ color: colors.text }}>
                {data.gameName}
              </p>
            )}
            {data.journalistName && (
              <p style={{ color: colors.axis }}>
                by {data.journalistName}
              </p>
            )}
          </>
        )}

        {/* Date */}
        <p className="mt-1" style={{ color: colors.axis }}>
          {data.dateLabel}
        </p>

        {data.daysFromRelease != null && (
          <p style={{ color: colors.axis }}>
            {formatDaysFromRelease(data.daysFromRelease)}
            {data.reviewTiming && data.reviewTiming !== "unknown" ? ` • ${data.reviewTiming.replace("_", " ")}` : ""}
          </p>
        )}

        {/* Scores */}
        <div className="mt-2 pt-2 border-t" style={{ borderColor: colors.border }}>
          {data.criticScore != null && (
            <p style={{ color: colors.text }}>
              Critic Score: <span className="font-medium">{data.criticScore.toFixed(0)}</span>
            </p>
          )}

          {/* All disparity values (only show visible ones) */}
          <div className="mt-2 space-y-1">
            {visibleLines.steam && data.steamDisparity != null && (
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colors.sage }}></span>
                  <span style={{ color: colors.sage }}>Steam</span>
                </span>
                <span className="font-medium" style={{ color: colors.sage }}>
                  {data.steamDisparity > 0 ? "+" : ""}{data.steamDisparity.toFixed(1)}
                </span>
              </div>
            )}
            {visibleLines.metacritic && data.metacriticDisparity != null && (
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colors.orange }}></span>
                  <span style={{ color: colors.orange }}>Metacritic</span>
                </span>
                <span className="font-medium" style={{ color: colors.orange }}>
                  {data.metacriticDisparity > 0 ? "+" : ""}{data.metacriticDisparity.toFixed(1)}
                </span>
              </div>
            )}
            {visibleLines.combined && data.combinedDisparity != null && (
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colors.rust }}></span>
                  <span style={{ color: colors.rust }}>Combined</span>
                </span>
                <span className="font-medium" style={{ color: colors.rust }}>
                  {data.combinedDisparity > 0 ? "+" : ""}{data.combinedDisparity.toFixed(1)}
                </span>
              </div>
            )}
          </div>

        </div>
      </div>
    );
  };

  return (
    <div>
      {/* Toggle buttons */}
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        {/* Disparity type toggles - now checkboxes */}
        <div className="flex gap-2">
          {(["steam", "metacritic", "combined"] as DisparityType[]).map((type) => {
            const typeHasData = hasData[type];
            const isVisible = visibleLines[type] && typeHasData;
            const typeColor = type === "steam" ? colors.sage : type === "metacritic" ? colors.orange : colors.rust;

            return (
              <button
                key={type}
                onClick={() => toggleLine(type)}
                disabled={!typeHasData}
                className={`flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg transition-all ${
                  !typeHasData
                    ? "bg-gray-100 dark:bg-gray-800 opacity-40 cursor-not-allowed"
                    : "hover:opacity-80"
                }`}
                style={{
                  backgroundColor: isVisible ? typeColor : isDark ? "#3D3A35" : "#f3f4f6",
                  color: isVisible ? "white" : colors.text,
                  border: `2px solid ${typeHasData ? typeColor : "transparent"}`,
                }}
              >
                {/* Checkbox indicator */}
                <span
                  className="w-3.5 h-3.5 rounded-sm flex items-center justify-center text-xs"
                  style={{
                    backgroundColor: isVisible ? "rgba(255,255,255,0.3)" : "transparent",
                    border: isVisible ? "none" : `1.5px solid ${typeHasData ? typeColor : colors.axis}`,
                  }}
                >
                  {isVisible && "✓"}
                </span>
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            );
          })}
        </div>

        <div className="flex flex-col items-start gap-2 sm:items-end">
          {/* Chart mode toggle */}
          <div className="flex gap-1 text-xs">
            <button
              onClick={() => changeChartMode("trend")}
              className={`px-2 py-1 rounded transition-colors ${
                chartMode === "trend"
                  ? "bg-gray-700 text-white dark:bg-gray-200 dark:text-gray-900"
                  : "bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600"
              }`}
              style={chartMode !== "trend" ? { color: colors.text } : {}}
            >
              Trend
            </button>
            <button
              onClick={() => changeChartMode("map")}
              className={`px-2 py-1 rounded transition-colors ${
                chartMode === "map"
                  ? "bg-gray-700 text-white dark:bg-gray-200 dark:text-gray-900"
                  : "bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600"
              }`}
              style={chartMode !== "map" ? { color: colors.text } : {}}
            >
              {secondaryMapLabel}
            </button>
          </div>

          {chartMode === "trend" && chartData.length > 1 && (
            <div className="flex flex-wrap gap-1 text-[11px] sm:text-xs">
              {trendRangeOptions
                .filter((option) => option.value !== "pre" || hasPreReleaseTrendData)
                .map((option) => (
                <button
                  key={option.value}
                  onClick={() => setTrendRange(option.value)}
                  className={`px-2 py-1 rounded transition-colors ${
                    effectiveTrendRange === option.value
                      ? "bg-gray-700 text-white dark:bg-gray-200 dark:text-gray-900"
                      : "bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600"
                  }`}
                  style={effectiveTrendRange !== option.value ? { color: colors.text } : {}}
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {chartMode === "trend" && trendSummaryText && (
        <p className="mb-4 text-xs sm:text-sm" style={{ color: colors.axis }}>
          {trendSummaryText}
        </p>
      )}

      {chartMode === "map" && hasVisibleLine && (
        <p className="mb-4 text-xs sm:text-sm" style={{ color: colors.axis }}>
          Showing {plottedPointCount.toLocaleString()} plotted point{plottedPointCount === 1 ? "" : "s"} across {plottedReviewCount.toLocaleString()} review{plottedReviewCount === 1 ? "" : "s"} on a {secondaryMapKind === "release" ? "days-from-release" : "score-vs-disparity"} map.
          {" "}
          {hiddenReviewCount > 0
            ? `${hiddenReviewCount.toLocaleString()} loaded review${hiddenReviewCount === 1 ? "" : "s"} are omitted because the selected sources do not have plottable disparity or ${secondaryMapKind === "release" ? "release-date" : "score"} context.`
            : `All ${reviews.length.toLocaleString()} loaded reviews are represented.`}
        </p>
      )}

      {!hasVisibleLine ? (
        <div
          className="flex items-center justify-center text-gray-500"
          style={{ height }}
        >
          Select at least one disparity type to display
        </div>
      ) : chartMode === "trend" && !hasVisibleTrendData ? (
        <div
          className="flex items-center justify-center text-gray-500 text-sm"
          style={{ height }}
        >
          No reviews fall within the selected trend window
        </div>
      ) : (
        <div
          ref={chartContainerRef}
          className="relative"
          onMouseMove={chartMode === "map" ? handleMouseMove : undefined}
          onMouseLeave={handleMouseLeave}
        >
          <ResponsiveContainer width="100%" height={effectiveHeight}>
            <ComposedChart
              data={chartMode === "trend" ? trendChartData : []}
              margin={isMobile ? { top: 5, right: 10, left: 5, bottom: 20 } : { top: 10, right: 15, left: 10, bottom: 25 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
              <XAxis
                dataKey={chartMode === "trend" ? "date" : "x"}
                type="number"
                domain={xDomain as [number, number]}
                tick={{ fontSize: isMobile ? 10 : 12, fill: colors.text }}
                tickLine={{ stroke: colors.axis }}
                axisLine={{ stroke: colors.axis }}
                tickFormatter={(value) => {
                  if (chartMode === "map") {
                    const rounded = Math.round(Number(value));
                    if (secondaryMapKind === "release") {
                      if (rounded === 0) return "Release";
                      return `${rounded > 0 ? "+" : ""}${rounded}d`;
                    }
                    return `${rounded}`;
                  }

                  const date = new Date(value);
                  if (effectiveTrendRange === "pre" || effectiveTrendRange === "1m" || effectiveTrendRange === "3m" || effectiveTrendRange === "6m") {
                    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
                  }
                  if (effectiveTrendRange === "1y") {
                    return date.toLocaleDateString("en-US", { month: "short", year: isMobile ? undefined : "2-digit" });
                  }
                  return date.toLocaleDateString("en-US", { month: "short", year: isMobile ? "2-digit" : "numeric" });
                }}
                label={isMobile ? undefined : chartMode === "map" ? {
                  value: secondaryMapKind === "release" ? "Days From Release" : "Critic Score",
                  position: "insideBottom",
                  offset: -10,
                  style: { fill: colors.text, fontSize: 12 },
                } : undefined}
              />
              <YAxis
                tick={{ fontSize: isMobile ? 10 : 12, fill: colors.text }}
                tickLine={{ stroke: colors.axis }}
                axisLine={{ stroke: colors.axis }}
                domain={yDomain as [number, number]}
                width={isMobile ? 35 : 45}
                tickFormatter={(value) => `${value > 0 ? "+" : ""}${Math.round(value)}`}
                label={isMobile ? undefined : {
                  value: "Disparity",
                  angle: -90,
                  position: "insideLeft",
                  style: { textAnchor: "middle", fill: colors.text, fontSize: 12 },
                }}
              />
              <ReferenceLine y={0} stroke={colors.tan} strokeWidth={2} strokeDasharray="5 5" />
              {trendWindowSpanSegments.map((segment) => {
                const stroke = segment.type === "steam"
                  ? colors.sage
                  : segment.type === "metacritic"
                    ? colors.orange
                    : colors.rust;

                return (
                  <ReferenceLine
                    key={`first-month-span-${segment.type}`}
                    ifOverflow="extendDomain"
                    segment={[segment.start, segment.end]}
                    stroke={stroke}
                    strokeWidth={2}
                    strokeDasharray="6 4"
                    strokeOpacity={0.75}
                  />
                );
              })}
              {chartMode === "map" && secondaryMapKind === "release" && (
                <>
                  {Number(xDomain[1]) > 0 && (
                    <ReferenceArea
                      x1={0}
                      x2={Math.min(60, Number(xDomain[1]))}
                      ifOverflow="extendDomain"
                      fill={colors.tan}
                      fillOpacity={0.08}
                      strokeOpacity={0}
                    />
                  )}
                  <ReferenceLine x={0} stroke={colors.axis} strokeDasharray="4 4" />
                  {Number(xDomain[1]) > 60 && (
                    <ReferenceLine x={60} stroke={colors.axis} strokeDasharray="4 4" />
                  )}
                </>
              )}

              {chartMode === "trend" ? (
                <>
                  {/* Steam trend line */}
                  {visibleLines.steam && hasData.steam && (
                    <Line
                      type="monotone"
                      dataKey="steamRollingAvg"
                      stroke={colors.sage}
                      strokeWidth={3}
                      dot={false}
                      activeDot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  )}
                  {/* Metacritic trend line */}
                  {visibleLines.metacritic && hasData.metacritic && (
                    <Line
                      type="monotone"
                      dataKey="metacriticRollingAvg"
                      stroke={colors.orange}
                      strokeWidth={3}
                      dot={false}
                      activeDot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  )}
                  {/* Combined trend line */}
                  {visibleLines.combined && hasData.combined && (
                    <Line
                      type="monotone"
                      dataKey="combinedRollingAvg"
                      stroke={colors.rust}
                      strokeWidth={3}
                      dot={false}
                      activeDot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  )}
                </>
              ) : (
                <>
                  {/* Steam release map */}
                  {visibleLines.steam && hasData.steam && (
                    <Scatter
                      data={secondaryMapData.steam}
                      dataKey="disparity"
                      fill={colors.sage}
                      fillOpacity={0.7}
                      isAnimationActive={false}
                      shape={(props: { cx?: number; cy?: number; payload?: SecondaryMapPoint }) => {
                        if (
                          !props.payload
                          || !isFiniteChartNumber(props.payload.disparity)
                          || !isFiniteChartNumber(props.cx)
                          || !isFiniteChartNumber(props.cy)
                        ) {
                          return <circle r={0} />;
                        }

                        setPointPosition(props.payload.point.index, "steam", props.cx, props.cy);

                        const isHovered = hoveredPoint?.index === props.payload.point.index;
                        return (
                          <circle
                            cx={props.cx}
                            cy={props.cy}
                            r={isHovered ? mapPointStyle.hoverRadius : mapPointStyle.pointRadius}
                            fill={colors.sage}
                            fillOpacity={isHovered ? 0.95 : mapPointStyle.pointOpacity}
                            stroke={isHovered ? colors.background : "none"}
                            strokeWidth={isHovered ? 2 : 0}
                          />
                        );
                      }}
                    />
                  )}
                  {/* Metacritic release map */}
                  {visibleLines.metacritic && hasData.metacritic && (
                    <Scatter
                      data={secondaryMapData.metacritic}
                      dataKey="disparity"
                      fill={colors.orange}
                      fillOpacity={0.7}
                      isAnimationActive={false}
                      shape={(props: { cx?: number; cy?: number; payload?: SecondaryMapPoint }) => {
                        if (
                          !props.payload
                          || !isFiniteChartNumber(props.payload.disparity)
                          || !isFiniteChartNumber(props.cx)
                          || !isFiniteChartNumber(props.cy)
                        ) {
                          return <circle r={0} />;
                        }

                        setPointPosition(props.payload.point.index, "metacritic", props.cx, props.cy);

                        const isHovered = hoveredPoint?.index === props.payload.point.index;
                        return (
                          <circle
                            cx={props.cx}
                            cy={props.cy}
                            r={isHovered ? mapPointStyle.hoverRadius : mapPointStyle.pointRadius}
                            fill={colors.orange}
                            fillOpacity={isHovered ? 0.95 : mapPointStyle.pointOpacity}
                            stroke={isHovered ? colors.background : "none"}
                            strokeWidth={isHovered ? 2 : 0}
                          />
                        );
                      }}
                    />
                  )}
                  {/* Combined release map */}
                  {visibleLines.combined && hasData.combined && (
                    <Scatter
                      data={secondaryMapData.combined}
                      dataKey="disparity"
                      fill={colors.rust}
                      fillOpacity={0.7}
                      isAnimationActive={false}
                      shape={(props: { cx?: number; cy?: number; payload?: SecondaryMapPoint }) => {
                        if (
                          !props.payload
                          || !isFiniteChartNumber(props.payload.disparity)
                          || !isFiniteChartNumber(props.cx)
                          || !isFiniteChartNumber(props.cy)
                        ) {
                          return <circle r={0} />;
                        }

                        setPointPosition(props.payload.point.index, "combined", props.cx, props.cy);

                        const isHovered = hoveredPoint?.index === props.payload.point.index;
                        return (
                          <circle
                            cx={props.cx}
                            cy={props.cy}
                            r={isHovered ? mapPointStyle.hoverRadius : mapPointStyle.pointRadius}
                            fill={colors.rust}
                            fillOpacity={isHovered ? 0.95 : mapPointStyle.pointOpacity}
                            stroke={isHovered ? colors.background : "none"}
                            strokeWidth={isHovered ? 2 : 0}
                          />
                        );
                      }}
                    />
                  )}
                </>
              )}
            </ComposedChart>
          </ResponsiveContainer>

          {/* Custom tooltip */}
          {renderTooltip()}
        </div>
      )}

      {/* Legend */}
      <div className="mt-3 flex items-center justify-center gap-4 text-xs" style={{ color: colors.axis }}>
        <span>Positive = critic higher than users</span>
        <span className="w-1 h-1 rounded-full" style={{ backgroundColor: colors.axis }}></span>
        <span>Negative = critic lower than users</span>
      </div>
      {chartMode === "trend" && hasReleaseAnchoredTrend && trendWindowSpanSegments.length > 0 && (
        <div className="mt-2 text-center text-xs" style={{ color: colors.axis }}>
          Dashed lines mark the change from the first review to the last review inside the selected release window.
        </div>
      )}
      {chartMode === "map" && secondaryMapKind === "release" && (
        <div className="mt-2 text-center text-xs" style={{ color: colors.axis }}>
          Day 0 marks release. The shaded band covers the first 60 days after launch.
        </div>
      )}
      {chartMode === "map" && secondaryMapKind === "score" && (
        <div className="mt-2 text-center text-xs" style={{ color: colors.axis }}>
          X-axis shows critic score. Each dot is a review positioned against its critic-to-user disparity.
        </div>
      )}
    </div>
  );
}
