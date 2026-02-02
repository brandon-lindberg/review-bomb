"use client";

import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from "recharts";

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
  positive: isDark ? "#E05A2B" : "#BB3B0E",
  negative: isDark ? "#8FA87A" : "#708160",
});

interface BarChartData {
  name: string;
  value: number;
  [key: string]: string | number;
}

interface DisparityBarChartProps {
  data: BarChartData[];
  height?: number;
  showReferenceLine?: boolean;
  colorByValue?: boolean;
  layout?: "horizontal" | "vertical";
}

export function DisparityBarChart({
  data,
  height = 300,
  showReferenceLine = true,
  colorByValue = true,
  layout = "vertical",
}: DisparityBarChartProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px] text-gray-500">
        No data available
      </div>
    );
  }

  const getBarColor = (value: number) => {
    if (!colorByValue) return colors.rust;
    return value >= 0 ? colors.positive : colors.negative;
  };

  if (layout === "horizontal") {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ top: 5, right: 30, left: 80, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} horizontal={true} vertical={false} />
          <XAxis
            type="number"
            tick={{ fontSize: 12, fill: colors.text }}
            tickLine={{ stroke: colors.axis }}
            axisLine={{ stroke: colors.axis }}
            tickFormatter={(value) => `${value > 0 ? "+" : ""}${value}`}
          />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ fontSize: 12, fill: colors.text }}
            tickLine={{ stroke: colors.axis }}
            axisLine={{ stroke: colors.axis }}
            width={75}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: colors.background,
              border: `1px solid ${colors.border}`,
              borderRadius: "8px",
              boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
              color: colors.text,
            }}
            formatter={(value) => {
              if (value == null) return ["N/A", "Disparity"];
              const v = Number(value);
              return [`${v > 0 ? "+" : ""}${v.toFixed(1)}`, "Disparity"];
            }}
          />
          {showReferenceLine && <ReferenceLine x={0} stroke={colors.tan} />}
          <Bar dataKey="value" radius={[0, 4, 4, 0]}>
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={getBarColor(entry.value)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
        <XAxis
          dataKey="name"
          tick={{ fontSize: 12, fill: colors.text }}
          tickLine={{ stroke: colors.axis }}
          axisLine={{ stroke: colors.axis }}
        />
        <YAxis
          tick={{ fontSize: 12, fill: colors.text }}
          tickLine={{ stroke: colors.axis }}
          axisLine={{ stroke: colors.axis }}
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
          formatter={(value) => {
            if (value == null) return ["N/A", "Disparity"];
            const v = Number(value);
            return [`${v > 0 ? "+" : ""}${v.toFixed(1)}`, "Disparity"];
          }}
        />
        {showReferenceLine && <ReferenceLine y={0} stroke={colors.tan} strokeDasharray="5 5" />}
        <Bar dataKey="value" radius={[4, 4, 0, 0]}>
          {data.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={getBarColor(entry.value)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// Score comparison bar chart for critic vs user scores
interface ScoreComparisonData {
  name: string;
  critic: number;
  steam?: number | null;
  metacritic?: number | null;
}

interface ScoreComparisonBarChartProps {
  data: ScoreComparisonData[];
  height?: number;
}

export function ScoreComparisonBarChart({
  data,
  height = 300,
}: ScoreComparisonBarChartProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px] text-gray-500">
        No data available
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
        <XAxis
          dataKey="name"
          tick={{ fontSize: 12, fill: colors.text }}
          tickLine={{ stroke: colors.axis }}
          axisLine={{ stroke: colors.axis }}
        />
        <YAxis
          domain={[0, 100]}
          tick={{ fontSize: 12, fill: colors.text }}
          tickLine={{ stroke: colors.axis }}
          axisLine={{ stroke: colors.axis }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: colors.background,
            border: `1px solid ${colors.border}`,
            borderRadius: "8px",
            boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
            color: colors.text,
          }}
        />
        <Bar dataKey="critic" name="Critic Score" fill={colors.rust} radius={[4, 4, 0, 0]} />
        <Bar dataKey="steam" name="Steam Score" fill={colors.sage} radius={[4, 4, 0, 0]} />
        <Bar dataKey="metacritic" name="Metacritic Score" fill={colors.orange} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
