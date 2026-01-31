"use client";

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
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px] text-gray-500">
        No historical data available
      </div>
    );
  }

  // Transform data for the chart
  const chartData = data.map((point) => ({
    date: new Date(point.date).toLocaleDateString("en-US", {
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
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 12 }}
          tickLine={{ stroke: "#9ca3af" }}
          axisLine={{ stroke: "#9ca3af" }}
        />
        <YAxis
          tick={{ fontSize: 12 }}
          tickLine={{ stroke: "#9ca3af" }}
          axisLine={{ stroke: "#9ca3af" }}
          domain={["auto", "auto"]}
          tickFormatter={(value) => `${value > 0 ? "+" : ""}${value}`}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "white",
            border: "1px solid #e5e7eb",
            borderRadius: "8px",
            boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
          }}
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
        />
        <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="5 5" />
        {showSteam && (
          <Line
            type="monotone"
            dataKey="steam"
            stroke="#1b9aaa"
            strokeWidth={2}
            dot={false}
            connectNulls
          />
        )}
        {showMetacritic && (
          <Line
            type="monotone"
            dataKey="metacritic"
            stroke="#f59e0b"
            strokeWidth={2}
            dot={false}
            connectNulls
          />
        )}
        {showCombined && (
          <Line
            type="monotone"
            dataKey="combined"
            stroke="#6366f1"
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
  color = "#6366f1",
  height = 100,
}: MiniDisparityChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[80px] text-gray-400 text-sm">
        No data
      </div>
    );
  }

  const chartData = data.map((point) => ({
    date: point.date,
    value: point.avg_disparity_combined != null ? Number(point.avg_disparity_combined) : null,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
        <ReferenceLine y={0} stroke="#e5e7eb" />
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          dot={false}
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
