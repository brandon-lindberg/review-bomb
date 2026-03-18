"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SteamActivityResponse, SteamPlayerMarkerType } from "@/types";

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

const getThemeColors = (isDark: boolean) => ({
  lineRange: isDark ? "#BEFF0A" : "#95C11F",
  grid: isDark ? "#3D3A35" : "#e5e7eb",
  axis: isDark ? "#6A655C" : "#9ca3af",
  text: isDark ? "#B8B4AC" : "#6b7280",
  background: isDark ? "#2D2A26" : "#ffffff",
  border: isDark ? "#3D3A35" : "#e5e7eb",
  panel: isDark ? "#1F1D1A" : "#f8fafc",
  markers: {
    first_tracked: isDark ? "#D8C593" : "#8A6D1D",
    all_time_peak: isDark ? "#FF8A5B" : "#BB3B0E",
    major_surge: isDark ? "#8FA87A" : "#708160",
    major_drop: isDark ? "#FFB02E" : "#DD7631",
    rebound: isDark ? "#7AB0FF" : "#2563eb",
  } satisfies Record<SteamPlayerMarkerType, string>,
});

type SteamActivityWindow = "1y" | "6m" | "3m" | "1m" | "1w" | "48h" | "24h";

const STEAM_ACTIVITY_WINDOW_OPTIONS: Array<{ value: SteamActivityWindow; label: string; description: string }> = [
  { value: "1y", label: "1Y", description: "last year" },
  { value: "6m", label: "6M", description: "last 6 months" },
  { value: "3m", label: "3M", description: "last 3 months" },
  { value: "1m", label: "1M", description: "last month" },
  { value: "1w", label: "1W", description: "last week" },
  { value: "48h", label: "48H", description: "last 48 hours" },
  { value: "24h", label: "24H", description: "last 24 hours" },
];

interface SteamActivityPanelProps {
  activity: SteamActivityResponse;
}

interface SteamActivityTimelinePoint {
  sampledAt: number;
  sampledAtRaw: string;
  sampledAtLabel: string;
  observed24hHigh: number;
  observed24hLow: number;
}

interface RangeChartPoint extends SteamActivityTimelinePoint {
  rangePlayers: number;
}

function formatPlayers(value: number | null | undefined): string {
  if (value == null) return "N/A";
  return value.toLocaleString();
}

function formatAbsoluteDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatRelativeDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  const diffMs = Date.now() - parsed.getTime();
  if (diffMs < 0) return null;
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "today";
  if (diffDays === 1) return "1 day ago";
  return `${diffDays} days ago`;
}

function getSteamActivityWindowStart(latestTimestamp: number, window: SteamActivityWindow): number {
  const start = new Date(latestTimestamp);

  switch (window) {
    case "1y":
      start.setFullYear(start.getFullYear() - 1);
      break;
    case "6m":
      start.setMonth(start.getMonth() - 6);
      break;
    case "3m":
      start.setMonth(start.getMonth() - 3);
      break;
    case "1m":
      start.setMonth(start.getMonth() - 1);
      break;
    case "1w":
      start.setDate(start.getDate() - 7);
      break;
    case "48h":
      start.setHours(start.getHours() - 48);
      break;
    case "24h":
      start.setHours(start.getHours() - 24);
      break;
  }

  return start.getTime();
}

function buildSteamActivityTicks(points: SteamActivityTimelinePoint[], targetTickCount: number): number[] {
  if (points.length === 0) return [];

  const timestamps = Array.from(new Set(points.map((point) => point.sampledAt)));
  if (timestamps.length <= targetTickCount) return timestamps;

  const lastIndex = timestamps.length - 1;
  const ticks = new Set<number>();

  for (let index = 0; index < targetTickCount; index += 1) {
    const pointIndex = Math.round((lastIndex * index) / Math.max(targetTickCount - 1, 1));
    ticks.add(timestamps[pointIndex]);
  }

  return Array.from(ticks).sort((a, b) => a - b);
}

function formatSteamActivityTick(value: number, window: SteamActivityWindow): string {
  const date = new Date(value);

  if (window === "24h") {
    return date.toLocaleTimeString("en-US", {
      hour: "numeric",
    });
  }

  if (window === "48h") {
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
    });
  }

  if (window === "1y") {
    return date.toLocaleDateString("en-US", {
      month: "short",
      year: "numeric",
    });
  }

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export function SteamActivityPanel({ activity }: SteamActivityPanelProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);
  const summary = activity.summary;
  const [selectedWindow, setSelectedWindow] = useState<SteamActivityWindow>("1m");

  const timelinePoints = useMemo(() => {
    const parsedPoints: SteamActivityTimelinePoint[] = [];
    for (const point of activity.points) {
      const parsed = new Date(point.sampled_at);
      const sampledAt = parsed.getTime();
      if (Number.isNaN(sampledAt)) continue;

      parsedPoints.push({
        sampledAt,
        sampledAtRaw: point.sampled_at,
        sampledAtLabel: parsed.toLocaleString("en-US", {
          month: "short",
          day: "numeric",
          hour: "numeric",
          minute: "2-digit",
        }),
        observed24hHigh: point.observed_24h_high,
        observed24hLow: point.observed_24h_low,
      });
    }

    return parsedPoints;
  }, [activity.points]);

  const latestTimestamp = useMemo(
    () => (timelinePoints.length > 0 ? timelinePoints[timelinePoints.length - 1].sampledAt : null),
    [timelinePoints]
  );

  const selectedWindowStart = useMemo(
    () => (latestTimestamp != null ? getSteamActivityWindowStart(latestTimestamp, selectedWindow) : null),
    [latestTimestamp, selectedWindow]
  );

  const visibleTimelinePoints = useMemo(() => {
    if (selectedWindowStart == null) return timelinePoints;

    const filtered = timelinePoints.filter((point) => point.sampledAt >= selectedWindowStart);
    if (filtered.length > 0) return filtered;

    return timelinePoints.slice(-1);
  }, [selectedWindowStart, timelinePoints]);

  const chartData = useMemo(() => {
    const rangePoints: RangeChartPoint[] = [];

    for (const point of visibleTimelinePoints) {
      rangePoints.push({
        ...point,
        rangePlayers: point.observed24hHigh,
      });

      if (point.observed24hLow !== point.observed24hHigh) {
        rangePoints.push({
          ...point,
          rangePlayers: point.observed24hLow,
        });
      }
    }

    return rangePoints;
  }, [visibleTimelinePoints]);

  const markerAnchors = useMemo(
    () =>
      new Map(
        timelinePoints.map((point) => [
          point.sampledAtRaw,
          {
            sampledAt: point.sampledAt,
            y: point.observed24hHigh,
          },
        ])
      ),
    [timelinePoints]
  );

  const visibleRange = useMemo(
    () => (
      visibleTimelinePoints.length > 0
        ? {
            start: visibleTimelinePoints[0].sampledAt,
            end: visibleTimelinePoints[visibleTimelinePoints.length - 1].sampledAt,
          }
        : null
    ),
    [visibleTimelinePoints]
  );

  const visibleMarkers = useMemo(() => {
    if (!visibleRange) return [];

    return activity.markers.filter((marker) => {
      const anchor = markerAnchors.get(marker.sampled_at);
      return anchor != null && anchor.sampledAt >= visibleRange.start && anchor.sampledAt <= visibleRange.end;
    });
  }, [activity.markers, markerAnchors, visibleRange]);

  const xAxisTicks = useMemo(
    () => buildSteamActivityTicks(visibleTimelinePoints, selectedWindow === "24h" || selectedWindow === "48h" ? 4 : 5),
    [selectedWindow, visibleTimelinePoints]
  );

  const selectedWindowDescription = useMemo(
    () => STEAM_ACTIVITY_WINDOW_OPTIONS.find((option) => option.value === selectedWindow)?.description ?? "selected window",
    [selectedWindow]
  );

  const renderTooltip = ({
    active,
    payload,
  }: {
    active?: boolean;
    payload?: ReadonlyArray<{ payload: RangeChartPoint }>;
  }) => {
    if (!active || !payload?.length) return null;
    const point = payload[0].payload;

    return (
      <div
        className="rounded-xl px-4 py-3"
        style={{
          backgroundColor: colors.background,
          border: `1px solid ${colors.border}`,
          boxShadow: "0 6px 18px rgba(15, 23, 42, 0.18)",
        }}
      >
        <div className="text-sm" style={{ color: colors.text }}>
          {point.sampledAtLabel}
        </div>
        <div className="mt-3 text-sm font-medium" style={{ color: colors.lineRange }}>
          24-Hour High: {point.observed24hHigh.toLocaleString()} players
        </div>
        <div className="mt-1 text-sm" style={{ color: "var(--foreground-muted)" }}>
          24-Hour Low: {point.observed24hLow.toLocaleString()} players
        </div>
      </div>
    );
  };

  const latestMarkers = [...activity.markers].slice(-5).reverse();
  const allTimePeakWhen = formatRelativeDate(summary.steam_player_all_time_peak_at)
    ?? formatAbsoluteDate(summary.steam_player_all_time_peak_at);

  if (timelinePoints.length === 0) {
    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="All-Time High"
            value={formatPlayers(summary.steam_player_all_time_peak)}
            detail={allTimePeakWhen ?? undefined}
          />
          <MetricCard label="24-Hour High" value={formatPlayers(summary.steam_player_24h_peak)} />
          <MetricCard label="24-Hour Low" value={formatPlayers(summary.steam_player_24h_low_observed)} />
          <MetricCard label="Achievements" value={formatPlayers(summary.steam_achievement_count)} />
        </div>
        <div className="flex items-center justify-center h-[220px] rounded-lg" style={{ color: colors.text, backgroundColor: colors.panel }}>
          No 24-hour Steam range is available yet
        </div>
        <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
          24-hour high, 24-hour low, and all-time high come from Flopathon history. Achievement count comes from Steam public store data.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="All-Time High"
          value={formatPlayers(summary.steam_player_all_time_peak)}
          detail={allTimePeakWhen ?? undefined}
        />
        <MetricCard label="24-Hour High" value={formatPlayers(summary.steam_player_24h_peak)} />
        <MetricCard label="24-Hour Low" value={formatPlayers(summary.steam_player_24h_low_observed)} />
        <MetricCard label="Achievements" value={formatPlayers(summary.steam_achievement_count)} />
      </div>

      <div className="rounded-[1.25rem] p-4 sm:p-5" style={{ backgroundColor: colors.panel, border: `1px solid ${colors.border}` }}>
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>
              Steam Activity
            </h3>
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              Tracked 24-hour high and low player counts over the selected time window.
            </p>
          </div>
          <div className="text-xs text-right" style={{ color: colors.text }}>
            <div>Summary + chart 24h range: Flopathon history</div>
            <div>Achievements: Steam public store data</div>
          </div>
        </div>

        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-1 text-[11px] sm:text-xs">
            {STEAM_ACTIVITY_WINDOW_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setSelectedWindow(option.value)}
                className={`rounded px-2 py-1 transition-colors ${
                  selectedWindow === option.value
                    ? "bg-gray-700 text-white dark:bg-gray-200 dark:text-gray-900"
                    : "bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600"
                }`}
                style={selectedWindow !== option.value ? { color: colors.text } : undefined}
              >
                {option.label}
              </button>
            ))}
          </div>
          {latestTimestamp != null && (
            <p className="text-xs sm:text-sm" style={{ color: colors.text }}>
              Viewing the {selectedWindowDescription} ending{" "}
              {new Date(latestTimestamp).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
              .
            </p>
          )}
        </div>

        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={chartData} margin={{ top: 10, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
            <XAxis
              dataKey="sampledAt"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tick={{ fill: colors.text, fontSize: 12 }}
              tickLine={{ stroke: colors.axis }}
              axisLine={{ stroke: colors.axis }}
              ticks={xAxisTicks}
              tickFormatter={(value) => formatSteamActivityTick(Number(value), selectedWindow)}
            />
            <YAxis
              tick={{ fill: colors.text, fontSize: 12 }}
              tickLine={{ stroke: colors.axis }}
              axisLine={{ stroke: colors.axis }}
              tickFormatter={(value) => `${Math.round(Number(value) / 1000)}k`}
            />
            <Tooltip
              content={renderTooltip}
            />
            <Line
              type="linear"
              dataKey="rangePlayers"
              name="24-Hour Range"
              stroke={colors.lineRange}
              strokeWidth={3}
              dot={false}
              activeDot={{ r: 5 }}
            />
            {visibleMarkers.map((marker) => {
              const anchor = markerAnchors.get(marker.sampled_at);
              if (!anchor) return null;
              return (
                <ReferenceDot
                  key={`${marker.marker_type}-${marker.sampled_at}`}
                  x={anchor.sampledAt}
                  y={anchor.y}
                  r={5}
                  fill={colors.markers[marker.marker_type]}
                  stroke={colors.background}
                  ifOverflow="extendDomain"
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {latestMarkers.length > 0 && (
        <div className="rounded-[1.25rem] p-4 sm:p-5" style={{ backgroundColor: colors.panel, border: `1px solid ${colors.border}` }}>
          <h3 className="text-sm font-semibold uppercase tracking-[0.2em]" style={{ color: colors.text }}>
            Recent Player Markers
          </h3>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {latestMarkers.map((marker) => (
              <div
                key={`${marker.marker_type}-${marker.sampled_at}`}
                className="rounded-xl p-3"
                style={{ border: `1px solid ${colors.border}`, backgroundColor: colors.background }}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium" style={{ color: colors.markers[marker.marker_type] }}>
                    {marker.label}
                  </span>
                  <span className="text-xs" style={{ color: colors.text }}>
                    {formatAbsoluteDate(marker.sampled_at)}
                  </span>
                </div>
                <p className="mt-2 text-sm" style={{ color: colors.text }}>
                  {marker.detail}
                </p>
                <p className="mt-1 text-xs" style={{ color: "var(--foreground-muted)" }}>
                  {marker.concurrent_players.toLocaleString()} players
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="rounded-[1rem] px-4 py-4" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
      <div className="text-2xl font-bold" style={{ color: "var(--foreground)" }}>
        {value}
      </div>
      <div className="mt-1 text-sm font-medium" style={{ color: "var(--foreground-muted)" }}>
        {label}
      </div>
      {detail ? (
        <div className="mt-1 text-xs" style={{ color: "var(--foreground-muted)" }}>
          {detail}
        </div>
      ) : null}
    </div>
  );
}
