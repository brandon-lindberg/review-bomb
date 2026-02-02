"use client";

import { useEffect, useState } from "react";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
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
  text: isDark ? "#B8B4AC" : "#6b7280",
  background: isDark ? "#2D2A26" : "#ffffff",
  border: isDark ? "#3D3A35" : "#e5e7eb",
});

// Color palette for pie segments
const getPieColors = (isDark: boolean) => [
  isDark ? "#E05A2B" : "#BB3B0E", // rust
  isDark ? "#E8904D" : "#DD7631", // orange
  isDark ? "#8FA87A" : "#708160", // sage
  isDark ? "#E5D9B3" : "#D8C593", // tan
  isDark ? "#6A8CAF" : "#4A6FA5", // blue
  isDark ? "#9B8EC2" : "#7B6BA2", // purple
];

interface PieChartData {
  name: string;
  value: number;
}

interface ScoreDistributionPieProps {
  data: PieChartData[];
  height?: number;
  showLegend?: boolean;
  innerRadius?: number;
  outerRadius?: number;
}

export function ScoreDistributionPie({
  data,
  height = 300,
  showLegend = true,
  innerRadius = 0,
  outerRadius = 80,
}: ScoreDistributionPieProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);
  const pieColors = getPieColors(isDark);

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px] text-gray-500">
        No data available
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={innerRadius}
          outerRadius={outerRadius}
          paddingAngle={2}
          dataKey="value"
          label={({ name, percent }) => `${name}: ${((percent ?? 0) * 100).toFixed(0)}%`}
          labelLine={{ stroke: colors.text }}
        >
          {data.map((_, index) => (
            <Cell key={`cell-${index}`} fill={pieColors[index % pieColors.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            backgroundColor: colors.background,
            border: `1px solid ${colors.border}`,
            borderRadius: "8px",
            boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
            color: colors.text,
          }}
          formatter={(value, name) => [value ?? 0, name ?? ""]}
        />
        {showLegend && (
          <Legend
            wrapperStyle={{ color: colors.text }}
            formatter={(value) => <span style={{ color: colors.text }}>{value}</span>}
          />
        )}
      </PieChart>
    </ResponsiveContainer>
  );
}

// Donut chart variant (pie with inner radius)
interface DonutChartProps {
  data: PieChartData[];
  height?: number;
  showLegend?: boolean;
  centerLabel?: string;
  centerValue?: string | number;
}

export function DonutChart({
  data,
  height = 300,
  showLegend = true,
  centerLabel,
  centerValue,
}: DonutChartProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);
  const pieColors = getPieColors(isDark);

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px] text-gray-500">
        No data available
      </div>
    );
  }

  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={80}
            paddingAngle={2}
            dataKey="value"
          >
            {data.map((_, index) => (
              <Cell key={`cell-${index}`} fill={pieColors[index % pieColors.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              backgroundColor: colors.background,
              border: `1px solid ${colors.border}`,
              borderRadius: "8px",
              boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
              color: colors.text,
            }}
            formatter={(value, name) => [value ?? 0, name ?? ""]}
          />
          {showLegend && (
            <Legend
              wrapperStyle={{ color: colors.text }}
              formatter={(value) => <span style={{ color: colors.text }}>{value}</span>}
            />
          )}
        </PieChart>
      </ResponsiveContainer>
      {(centerLabel || centerValue) && (
        <div
          className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none"
          style={{ marginTop: showLegend ? "-40px" : "0" }}
        >
          {centerValue && (
            <span className="text-2xl font-bold" style={{ color: colors.rust }}>
              {centerValue}
            </span>
          )}
          {centerLabel && (
            <span className="text-sm" style={{ color: colors.text }}>
              {centerLabel}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// Disparity distribution pie (positive vs negative reviews)
interface DisparityDistributionData {
  positive: number;
  negative: number;
  neutral?: number;
}

interface DisparityDistributionPieProps {
  data: DisparityDistributionData;
  height?: number;
}

export function DisparityDistributionPie({
  data,
  height = 250,
}: DisparityDistributionPieProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);

  const chartData = [
    { name: "Higher than users", value: data.positive },
    { name: "Lower than users", value: data.negative },
  ];

  if (data.neutral && data.neutral > 0) {
    chartData.push({ name: "Aligned with users", value: data.neutral });
  }

  const customColors = [
    colors.rust,  // positive (critic higher)
    colors.sage,  // negative (critic lower)
    colors.tan,   // neutral
  ];

  const total = data.positive + data.negative + (data.neutral || 0);

  if (total === 0) {
    return (
      <div className="flex items-center justify-center h-[200px] text-gray-500">
        No data available
      </div>
    );
  }

  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={70}
            paddingAngle={2}
            dataKey="value"
          >
            {chartData.map((_, index) => (
              <Cell key={`cell-${index}`} fill={customColors[index]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              backgroundColor: colors.background,
              border: `1px solid ${colors.border}`,
              borderRadius: "8px",
              boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
              color: colors.text,
            }}
            formatter={(value, name) => {
              const v = value ?? 0;
              return [
                `${v} (${((Number(v) / total) * 100).toFixed(1)}%)`,
                name ?? "",
              ];
            }}
          />
          <Legend
            wrapperStyle={{ color: colors.text }}
            formatter={(value) => <span style={{ color: colors.text }}>{value}</span>}
          />
        </PieChart>
      </ResponsiveContainer>
      <div
        className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none"
        style={{ marginTop: "-30px" }}
      >
        <span className="text-xl font-bold" style={{ color: colors.text }}>
          {total}
        </span>
        <span className="text-xs" style={{ color: colors.text }}>
          reviews
        </span>
      </div>
    </div>
  );
}
