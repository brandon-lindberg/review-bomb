"use client";

import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import type { DisparitySnapshot } from "@/types";

// Hook to detect dark mode
function useIsDarkMode() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const checkDarkMode = () => {
      setIsDark(document.documentElement.classList.contains("dark"));
    };

    checkDarkMode();

    // Watch for class changes on html element
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

function parseSnapshotDate(dateValue: string): Date | null {
  // API returns date-only strings (YYYY-MM-DD); parse in local time to avoid UTC shift.
  const dateMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateValue);
  if (dateMatch) {
    const year = Number.parseInt(dateMatch[1], 10);
    const month = Number.parseInt(dateMatch[2], 10) - 1;
    const day = Number.parseInt(dateMatch[3], 10);
    return new Date(year, month, day);
  }

  const parsed = new Date(dateValue);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
}

function formatSnapshotDate(dateValue: string, options: Intl.DateTimeFormatOptions): string {
  const parsed = parseSnapshotDate(dateValue);
  if (!parsed) {
    return dateValue;
  }
  return parsed.toLocaleDateString("en-US", options);
}

function normalizeSnapshotSeries(data: DisparitySnapshot[]): DisparitySnapshot[] {
  // Keep the latest entry for each snapshot date, then sort chronologically.
  const byDate = new Map<string, DisparitySnapshot>();
  for (const point of data) {
    byDate.set(String(point.date), point);
  }
  return [...byDate.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

interface DisparityChartProps {
  data: DisparitySnapshot[];
  height?: number;
  showSteam?: boolean;
  showMetacritic?: boolean;
  showCombined?: boolean;
}

export function DisparityChart({
  data,
  height = 300,
  showSteam = true,
  showMetacritic = true,
  showCombined = true,
}: DisparityChartProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px] text-gray-500">
        No historical data available
      </div>
    );
  }

  const normalizedData = normalizeSnapshotSeries(data);

  // Transform data for the chart
  const chartData = normalizedData.map((point) => ({
    date: formatSnapshotDate(String(point.date), {
      month: "short",
      day: "numeric",
    }),
    steam: point.avg_disparity_steam != null ? Number(point.avg_disparity_steam) : null,
    metacritic: point.avg_disparity_metacritic != null ? Number(point.avg_disparity_metacritic) : null,
    combined: point.avg_disparity_combined != null ? Number(point.avg_disparity_combined) : null,
    reviews: point.review_count,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 12, fill: colors.text }}
          tickLine={{ stroke: colors.axis }}
          axisLine={{ stroke: colors.axis }}
        />
        <YAxis
          tick={{ fontSize: 12, fill: colors.text }}
          tickLine={{ stroke: colors.axis }}
          axisLine={{ stroke: colors.axis }}
          domain={["auto", "auto"]}
          tickFormatter={(value) => `${value > 0 ? "+" : ""}${value}`}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: colors.background,
            border: `1px solid ${colors.border}`,
            borderRadius: "8px",
            boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
            color: colors.text,
          }}
          labelStyle={{ color: colors.text }}
          formatter={(value, name) => {
            if (value === null || value === undefined) return ["N/A", String(name)];
            const numValue = Number(value);
            const label =
              name === "steam"
                ? "Steam"
                : name === "metacritic"
                  ? "Metacritic"
                  : "Combined";
            return [`${numValue > 0 ? "+" : ""}${numValue.toFixed(1)}`, label];
          }}
        />
        <Legend
          formatter={(value) => {
            return value === "steam"
              ? "Steam"
              : value === "metacritic"
                ? "Metacritic"
                : "Combined";
          }}
          wrapperStyle={{ color: colors.text }}
        />
        <ReferenceLine y={0} stroke={colors.tan} strokeDasharray="5 5" />
        {showSteam && (
          <Line
            type="monotone"
            dataKey="steam"
            stroke={colors.sage}
            strokeWidth={2}
            dot={false}
            connectNulls
          />
        )}
        {showMetacritic && (
          <Line
            type="monotone"
            dataKey="metacritic"
            stroke={colors.orange}
            strokeWidth={2}
            dot={false}
            connectNulls
          />
        )}
        {showCombined && (
          <Line
            type="monotone"
            dataKey="combined"
            stroke={colors.rust}
            strokeWidth={2}
            dot={false}
            connectNulls
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}

// Mini version for compare page
interface MiniDisparityChartProps {
  data: DisparitySnapshot[];
  color?: string;
  height?: number;
}

export function MiniDisparityChart({
  data,
  color = "#BB3B0E",
  height = 100,
}: MiniDisparityChartProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[80px] text-gray-400 text-sm">
        No data
      </div>
    );
  }

  const normalizedData = normalizeSnapshotSeries(data);

  const chartData = normalizedData.map((point) => ({
    date: point.date,
    dateFormatted: formatSnapshotDate(String(point.date), {
      month: "short",
      year: "numeric",
    }),
    value: point.avg_disparity_combined != null ? Number(point.avg_disparity_combined) : null,
  }));

  // Get first and last valid data points for labels
  const firstPoint = chartData.find(p => p.value !== null);
  const lastPoint = [...chartData].reverse().find(p => p.value !== null);
  
  // Get start and end values for trend display
  const startVal = firstPoint?.value ?? null;
  const endVal = lastPoint?.value ?? null;

  return (
    <div className="relative">
      {/* Chart */}
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 5 }}>
          <ReferenceLine y={0} stroke={colors.tan} strokeDasharray="3 3" />
          <Tooltip
            contentStyle={{
              backgroundColor: colors.background,
              border: `1px solid ${colors.border}`,
              borderRadius: "6px",
              fontSize: "12px",
              padding: "6px 10px",
            }}
            labelFormatter={(label, payload) => {
              if (payload && payload[0]) {
                return payload[0].payload.dateFormatted;
              }
              return label;
            }}
            formatter={(value: number | undefined) => {
              if (value === null || value === undefined) return ["N/A", "Disparity"];
              return [`${value > 0 ? "+" : ""}${value.toFixed(1)}`, "Disparity"];
            }}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: color, stroke: colors.background, strokeWidth: 2 }}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
      
      {/* Timeline labels - show start date, start→end values, end date */}
      <div className="flex justify-between items-center mt-1 px-2">
        <div className="text-[10px] text-left" style={{ color: colors.axis }}>
          <div>{firstPoint?.dateFormatted || "—"}</div>
          {startVal !== null && (
            <div className="font-medium" style={{ color: color }}>
              {startVal > 0 ? "+" : ""}{startVal.toFixed(0)}
            </div>
          )}
        </div>
        {startVal !== null && endVal !== null && startVal !== endVal && (
          <span className="text-[10px]" style={{ color: colors.axis }}>
            →
          </span>
        )}
        <div className="text-[10px] text-right" style={{ color: colors.axis }}>
          <div>{lastPoint?.dateFormatted || "—"}</div>
          {endVal !== null && (
            <div className="font-medium" style={{ color: color }}>
              {endVal > 0 ? "+" : ""}{endVal.toFixed(0)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
