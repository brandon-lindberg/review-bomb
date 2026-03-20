"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
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
  rust: isDark ? "#E05A2B" : "#BB3B0E",
  orange: isDark ? "#E8904D" : "#DD7631",
  sage: isDark ? "#8FA87A" : "#708160",
  tan: isDark ? "#E5D9B3" : "#D8C593",
  lineCurrent: isDark ? "#E8904D" : "#BB3B0E",
  areaCurrent: isDark ? "rgba(224, 90, 43, 0.16)" : "rgba(187, 59, 14, 0.12)",
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

type SteamActivityWindow = "24h" | "48h" | "1w" | "1m" | "3m" | "6m" | "1y";

const STEAM_ACTIVITY_WINDOW_OPTIONS: Array<{ value: SteamActivityWindow; label: string; description: string }> = [
  { value: "24h", label: "24H", description: "last 24 hours" },
  { value: "48h", label: "48H", description: "last 48 hours" },
  { value: "1w", label: "1W", description: "last week" },
  { value: "1m", label: "1M", description: "last month" },
  { value: "3m", label: "3M", description: "last 3 months" },
  { value: "6m", label: "6M", description: "last 6 months" },
  { value: "1y", label: "1Y", description: "last year" },
];

interface SteamActivityPanelProps {
  activity: SteamActivityResponse;
}

interface SteamActivityTimelinePoint {
  sampledAt: number;
  sampledAtLabel: string;
  latestPlayers: number;
  observed24hHigh: number;
  observed24hLow: number;
}

function formatPlayers(value: number | null | undefined): string {
  if (value == null) return "N/A";
  return value.toLocaleString();
}

function formatAbsoluteDate(value: string | null | undefined, timeZone: string): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone,
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

function formatRangeDate(value: number, timeZone: string): string {
  return new Date(value).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone,
  });
}

function formatLatestWindowLabel(value: number, timeZone: string): string {
  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  });
}

function getSteamActivityWindowStart(latestTimestamp: number, window: SteamActivityWindow): number {
  const start = new Date(latestTimestamp);

  switch (window) {
    case "24h":
      start.setHours(start.getHours() - 24);
      break;
    case "48h":
      start.setHours(start.getHours() - 48);
      break;
    case "1w":
      start.setDate(start.getDate() - 7);
      break;
    case "1m":
      start.setMonth(start.getMonth() - 1);
      break;
    case "3m":
      start.setMonth(start.getMonth() - 3);
      break;
    case "6m":
      start.setMonth(start.getMonth() - 6);
      break;
    case "1y":
      start.setFullYear(start.getFullYear() - 1);
      break;
  }

  return start.getTime();
}

function isSteamActivityWindowAvailable(
  earliestTimestamp: number | null,
  latestTimestamp: number | null,
  window: SteamActivityWindow
): boolean {
  if (earliestTimestamp == null || latestTimestamp == null) return false;
  if (window === "24h") return true;
  return earliestTimestamp <= getSteamActivityWindowStart(latestTimestamp, window);
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

function formatSteamActivityTick(value: number, window: SteamActivityWindow, timeZone: string): string {
  const date = new Date(value);

  if (window === "24h") {
    return date.toLocaleTimeString("en-US", {
      hour: "numeric",
      timeZone,
    });
  }

  if (window === "48h") {
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      timeZone,
    });
  }

  if (window === "1y") {
    return date.toLocaleDateString("en-US", {
      month: "short",
      year: "numeric",
      timeZone,
    });
  }

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone,
  });
}

export function SteamActivityPanel({ activity }: SteamActivityPanelProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);
  const summary = activity.summary;
  const [selectedWindow, setSelectedWindow] = useState<SteamActivityWindow>("24h");
  const timeZone = useMemo(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    } catch {
      return "UTC";
    }
  }, []);

  const timelinePoints = useMemo(() => {
    const parsedPoints: SteamActivityTimelinePoint[] = [];
    for (const point of activity.points) {
      const parsed = new Date(point.sampled_at);
      const sampledAt = parsed.getTime();
      if (Number.isNaN(sampledAt)) continue;

      parsedPoints.push({
        sampledAt,
        sampledAtLabel: parsed.toLocaleString("en-US", {
          month: "short",
          day: "numeric",
          hour: "numeric",
          minute: "2-digit",
          timeZone,
          timeZoneName: "short",
        }),
        latestPlayers: point.latest_players ?? point.observed_24h_high,
        observed24hHigh: point.observed_24h_high,
        observed24hLow: point.observed_24h_low,
      });
    }

    return parsedPoints.sort((left, right) => left.sampledAt - right.sampledAt);
  }, [activity.points, timeZone]);

  const earliestTimestamp = useMemo(
    () => (timelinePoints.length > 0 ? timelinePoints[0].sampledAt : null),
    [timelinePoints]
  );

  const latestTimestamp = useMemo(
    () => (timelinePoints.length > 0 ? timelinePoints[timelinePoints.length - 1].sampledAt : null),
    [timelinePoints]
  );

  const latestTimelinePoint = useMemo(
    () => (timelinePoints.length > 0 ? timelinePoints[timelinePoints.length - 1] : null),
    [timelinePoints]
  );

  const availableWindows = useMemo(
    () => Object.fromEntries(
      STEAM_ACTIVITY_WINDOW_OPTIONS.map((option) => [
        option.value,
        isSteamActivityWindowAvailable(earliestTimestamp, latestTimestamp, option.value),
      ])
    ) as Record<SteamActivityWindow, boolean>,
    [earliestTimestamp, latestTimestamp]
  );

  const enabledWindows = useMemo(
    () => STEAM_ACTIVITY_WINDOW_OPTIONS.filter((option) => availableWindows[option.value]).map((option) => option.value),
    [availableWindows]
  );

  const effectiveSelectedWindow = useMemo(
    () => {
      if (availableWindows[selectedWindow]) return selectedWindow;
      return enabledWindows[enabledWindows.length - 1] ?? "24h";
    },
    [availableWindows, enabledWindows, selectedWindow]
  );

  const selectedWindowStart = useMemo(
    () => (latestTimestamp != null ? getSteamActivityWindowStart(latestTimestamp, effectiveSelectedWindow) : null),
    [effectiveSelectedWindow, latestTimestamp]
  );

  const visibleTimelinePoints = useMemo(() => {
    if (selectedWindowStart == null) return timelinePoints;

    const filtered = timelinePoints.filter((point) => point.sampledAt >= selectedWindowStart);
    if (filtered.length > 0) return filtered;

    return timelinePoints.slice(-1);
  }, [selectedWindowStart, timelinePoints]);

  const xAxisTicks = useMemo(
    () => buildSteamActivityTicks(visibleTimelinePoints, effectiveSelectedWindow === "24h" || effectiveSelectedWindow === "48h" ? 4 : 5),
    [effectiveSelectedWindow, visibleTimelinePoints]
  );

  const selectedWindowDescription = useMemo(
    () => STEAM_ACTIVITY_WINDOW_OPTIONS.find((option) => option.value === effectiveSelectedWindow)?.description ?? "selected window",
    [effectiveSelectedWindow]
  );

  const visibleStartTimestamp = visibleTimelinePoints.length > 0 ? visibleTimelinePoints[0].sampledAt : earliestTimestamp;
  const visibleEndTimestamp = visibleTimelinePoints.length > 0
    ? visibleTimelinePoints[visibleTimelinePoints.length - 1].sampledAt
    : latestTimestamp;

  const renderTooltip = ({
    active,
    payload,
  }: {
    active?: boolean;
    payload?: ReadonlyArray<{ payload: SteamActivityTimelinePoint }>;
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
        <div className="mt-3 text-sm font-medium" style={{ color: colors.lineCurrent }}>
          Current Players: {point.latestPlayers.toLocaleString()} players
        </div>
        <div className="mt-1 text-sm" style={{ color: "var(--foreground-muted)" }}>
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
    ?? formatAbsoluteDate(summary.steam_player_all_time_peak_at, timeZone);
  const currentPlayers = latestTimelinePoint?.latestPlayers ?? null;

  if (timelinePoints.length === 0) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Current Players"
            value={formatPlayers(currentPlayers)}
          />
          <MetricCard
            label="All-Time Peak"
            value={formatPlayers(summary.steam_player_all_time_peak)}
            detail={allTimePeakWhen ?? undefined}
          />
          <MetricCard label="24-Hour High" value={formatPlayers(summary.steam_player_24h_peak)} />
          <MetricCard label="24-Hour Low" value={formatPlayers(summary.steam_player_24h_low_observed)} />
        </div>
        <div className="flex items-center justify-center h-[220px] rounded-lg" style={{ color: colors.text, backgroundColor: colors.panel }}>
          No Steam player history is available yet
        </div>
        <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
          Steam player history will appear here once tracked samples are available.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Current Players" value={formatPlayers(currentPlayers)} />
        <MetricCard
          label="All-Time Peak"
          value={formatPlayers(summary.steam_player_all_time_peak)}
          detail={allTimePeakWhen ?? undefined}
        />
        <MetricCard label="24-Hour High" value={formatPlayers(summary.steam_player_24h_peak)} />
        <MetricCard label="24-Hour Low" value={formatPlayers(summary.steam_player_24h_low_observed)} />
      </div>

      <div
        className="rounded-[1.6rem] p-5 sm:p-6 lg:p-8"
        style={{ backgroundColor: colors.panel, border: `1px solid ${colors.border}` }}
      >
        <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h3 className="text-[1.9rem] font-semibold leading-none tracking-[-0.03em]" style={{ color: "var(--foreground)" }}>
              Hourly Player Count
            </h3>
            <p className="mt-2 text-base" style={{ color: "var(--foreground-muted)" }}>
              Current players over time. Summary cards above show the rolling 24-hour high and low.
            </p>
            <p className="mt-1 text-sm" style={{ color: colors.text }}>
              Times shown in your local timezone.
            </p>
          </div>
        </div>

        <div className="mb-6 flex flex-wrap items-center justify-end gap-2 text-[11px] sm:text-xs">
          {STEAM_ACTIVITY_WINDOW_OPTIONS.map((option) => {
            const isEnabled = availableWindows[option.value];
            const isActive = effectiveSelectedWindow === option.value;

            return (
              <button
                key={option.value}
                type="button"
                disabled={!isEnabled}
                onClick={() => setSelectedWindow(option.value)}
                className="rounded-xl border px-3 py-2 font-semibold tracking-[0.04em] transition-colors"
                style={{
                  borderColor: isActive ? colors.rust : colors.border,
                  backgroundColor: isActive
                    ? isDark
                      ? "rgba(224, 90, 43, 0.16)"
                      : "rgba(187, 59, 14, 0.1)"
                    : colors.background,
                  color: isActive ? colors.rust : isEnabled ? colors.text : "rgba(184, 180, 172, 0.42)",
                  cursor: isEnabled ? "pointer" : "not-allowed",
                  opacity: isEnabled ? 1 : 0.6,
                  boxShadow: isActive
                    ? isDark
                      ? "inset 0 0 0 1px rgba(229, 217, 179, 0.08)"
                      : "inset 0 0 0 1px rgba(216, 197, 147, 0.2)"
                    : "none",
                }}
              >
                {option.label}
              </button>
            );
          })}
        </div>

        <div
          className="rounded-[1.45rem] px-5 py-5 sm:px-6 sm:py-6 lg:px-8 lg:py-7"
          style={{ backgroundColor: "color-mix(in srgb, var(--background-card) 92%, var(--background) 8%)" }}
        >
          <div className="mb-4">
            <h4 className="text-[1.65rem] font-semibold leading-none tracking-[-0.03em]" style={{ color: "var(--foreground)" }}>
              Current Players
            </h4>
            {visibleStartTimestamp != null && visibleEndTimestamp != null && (
              <p className="mt-2 text-base" style={{ color: colors.text }}>
                Viewing the {selectedWindowDescription} of hourly history • {formatRangeDate(visibleStartTimestamp, timeZone)} to{" "}
                {formatRangeDate(visibleEndTimestamp, timeZone)}
              </p>
            )}
          </div>

          <ResponsiveContainer width="100%" height={360}>
            <AreaChart data={visibleTimelinePoints} margin={{ top: 12, right: 0, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="4 10" stroke={colors.grid} />
              <XAxis
                dataKey="sampledAt"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tick={{ fill: colors.text, fontSize: 12 }}
                tickLine={{ stroke: colors.axis }}
                axisLine={{ stroke: colors.axis }}
                ticks={xAxisTicks}
                tickFormatter={(value) => formatSteamActivityTick(Number(value), effectiveSelectedWindow, timeZone)}
              />
              <YAxis
                tick={{ fill: colors.text, fontSize: 12 }}
                tickLine={{ stroke: colors.axis }}
                axisLine={{ stroke: colors.axis }}
                tickFormatter={(value) => {
                  const numeric = Number(value);
                  if (numeric >= 1_000_000) return `${(numeric / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
                  if (numeric >= 1_000) return `${(numeric / 1_000).toFixed(1).replace(/\.0$/, "")}k`;
                  return String(Math.round(numeric));
                }}
              />
              <Tooltip
                content={renderTooltip}
              />
              <Area
                type="linear"
                dataKey="latestPlayers"
                name="Current Players"
                stroke={colors.lineCurrent}
                fill={colors.areaCurrent}
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 5, fill: colors.lineCurrent, stroke: colors.background }}
              />
            </AreaChart>
          </ResponsiveContainer>

          <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap gap-1 text-[11px] sm:text-xs">
              <div
                className="inline-flex items-center gap-3 rounded-full border px-5 py-4 text-sm font-semibold"
                style={{
                  borderColor: colors.border,
                  color: "var(--foreground)",
                  backgroundColor: isDark
                    ? "rgba(229, 217, 179, 0.04)"
                    : "rgba(216, 197, 147, 0.08)",
                }}
              >
                <span
                  className="h-[4px] w-8 rounded-full"
                  style={{ backgroundColor: colors.lineCurrent }}
                />
                <span>current players</span>
              </div>
            </div>
            {visibleEndTimestamp != null && (
              <p className="text-sm" style={{ color: colors.text }}>
                Latest sample: {formatLatestWindowLabel(visibleEndTimestamp, timeZone)}
              </p>
            )}
          </div>
        </div>
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
                    {formatAbsoluteDate(marker.sampled_at, timeZone)}
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
    <div
      className="min-h-[10rem] rounded-[1.5rem] px-6 py-5 sm:min-h-[10.75rem] sm:px-7 sm:py-6"
      style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
    >
      <div className="text-[2.3rem] font-black leading-none tracking-[-0.04em] sm:text-[2.65rem]" style={{ color: "var(--foreground)" }}>
        {value}
      </div>
      <div className="mt-3 text-base font-medium" style={{ color: "var(--foreground-muted)" }}>
        {label}
      </div>
      {detail ? (
        <div className="mt-3 text-sm" style={{ color: "var(--foreground-muted)" }}>
          {detail}
        </div>
      ) : null}
    </div>
  );
}
