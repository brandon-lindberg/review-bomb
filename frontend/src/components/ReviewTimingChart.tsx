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

interface ReviewTimingChartProps {
  early: number;
  launchWindow: number;
  late: number;
}

const TIMING_COLORS = {
  light: {
    early: "#3b82f6",      // blue-500
    launchWindow: "#22c55e", // green-500
    late: "#f59e0b",        // amber-500
  },
  dark: {
    early: "#60a5fa",      // blue-400
    launchWindow: "#4ade80", // green-400
    late: "#fbbf24",        // amber-400
  },
};

export function ReviewTimingChart({ early, launchWindow, late }: ReviewTimingChartProps) {
  const isDark = useIsDarkMode();
  const colors = isDark ? TIMING_COLORS.dark : TIMING_COLORS.light;
  const total = early + launchWindow + late;

  if (total === 0) {
    return (
      <div className="flex items-center justify-center h-[250px]" style={{ color: "var(--foreground-muted)" }}>
        No review timing data available
      </div>
    );
  }

  const data = [
    ...(early > 0 ? [{ name: "Early", value: early }] : []),
    { name: "Launch Window", value: launchWindow },
    { name: "Late", value: late },
  ];

  const colorMap: Record<string, string> = {
    Early: colors.early,
    "Launch Window": colors.launchWindow,
    Late: colors.late,
  };

  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={90}
            paddingAngle={2}
            dataKey="value"
          >
            {data.map((entry) => (
              <Cell key={entry.name} fill={colorMap[entry.name]} />
            ))}
          </Pie>
          <Tooltip
            offset={20}
            wrapperStyle={{ zIndex: 10 }}
            contentStyle={{
              backgroundColor: isDark ? "#2D2A26" : "#ffffff",
              border: `1px solid ${isDark ? "#3D3A35" : "#e5e7eb"}`,
              borderRadius: "8px",
              boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
              opacity: 1,
            }}
            itemStyle={{
              color: isDark ? "#E5E2DD" : "#374151",
            }}
            labelStyle={{
              color: isDark ? "#E5E2DD" : "#374151",
              fontWeight: 600,
            }}
            formatter={(value, name) => {
              const v = Number(value);
              return [`${v} (${((v / total) * 100).toFixed(1)}%)`, name];
            }}
          />
          <Legend
            wrapperStyle={{ color: isDark ? "#B8B4AC" : "#6b7280" }}
            formatter={(value) => (
              <span style={{ color: isDark ? "#B8B4AC" : "#6b7280" }}>{value}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
      <div
        className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none"
        style={{ marginTop: "-30px" }}
      >
        <span className="text-2xl font-bold" style={{ color: isDark ? "#B8B4AC" : "#374151" }}>
          {total}
        </span>
        <span className="text-xs" style={{ color: isDark ? "#B8B4AC" : "#6b7280" }}>
          reviews
        </span>
      </div>
      <p className="mt-2 text-sm text-center" style={{ color: "var(--foreground-muted)" }}>
        Early = before release. Launch Window = within 60 days. Late = after 60 days.
      </p>
    </div>
  );
}
