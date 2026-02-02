"use client";

import { useEffect, useState } from "react";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
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
  grid: isDark ? "#3D3A35" : "#e5e7eb",
  axis: isDark ? "#6A655C" : "#9ca3af",
  text: isDark ? "#B8B4AC" : "#6b7280",
  background: isDark ? "#2D2A26" : "#ffffff",
  border: isDark ? "#3D3A35" : "#e5e7eb",
});

// Visual score comparison component (gauge-style)
interface ScoreGaugeProps {
  criticScore: number;
  userScore: number;
  label?: string;
  size?: "sm" | "md" | "lg";
}

export function ScoreGauge({
  criticScore,
  userScore,
  label,
  size = "md",
}: ScoreGaugeProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);

  const disparity = criticScore - userScore;
  const sizeClasses = {
    sm: "w-24 h-24",
    md: "w-32 h-32",
    lg: "w-40 h-40",
  };

  // Calculate positions on circle (0-100 scale maps to 0-270 degrees)
  const criticAngle = (criticScore / 100) * 270 - 135;
  const userAngle = (userScore / 100) * 270 - 135;

  return (
    <div className="flex flex-col items-center">
      <div className={`relative ${sizeClasses[size]}`}>
        {/* Background arc */}
        <svg viewBox="0 0 100 100" className="w-full h-full">
          {/* Gray background arc */}
          <path
            d="M 15 85 A 40 40 0 1 1 85 85"
            fill="none"
            stroke={colors.grid}
            strokeWidth="8"
            strokeLinecap="round"
          />
          {/* Critic score indicator */}
          <circle
            cx={50 + 40 * Math.cos((criticAngle * Math.PI) / 180)}
            cy={50 + 40 * Math.sin((criticAngle * Math.PI) / 180)}
            r="6"
            fill={colors.rust}
          />
          {/* User score indicator */}
          <circle
            cx={50 + 40 * Math.cos((userAngle * Math.PI) / 180)}
            cy={50 + 40 * Math.sin((userAngle * Math.PI) / 180)}
            r="6"
            fill={colors.sage}
          />
        </svg>
        {/* Center content */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className={`font-bold ${size === "lg" ? "text-2xl" : size === "md" ? "text-xl" : "text-lg"}`}
            style={{ color: disparity >= 0 ? colors.rust : colors.sage }}
          >
            {disparity > 0 ? "+" : ""}{disparity.toFixed(1)}
          </span>
          <span className="text-xs" style={{ color: colors.text }}>
            disparity
          </span>
        </div>
      </div>
      {label && (
        <span className="mt-2 text-sm font-medium" style={{ color: colors.text }}>
          {label}
        </span>
      )}
      <div className="flex gap-4 mt-2 text-xs">
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: colors.rust }} />
          <span style={{ color: colors.text }}>Critic: {criticScore}</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: colors.sage }} />
          <span style={{ color: colors.text }}>User: {userScore}</span>
        </div>
      </div>
    </div>
  );
}

// Horizontal bar comparison
interface ScoreBarComparisonProps {
  criticScore: number;
  steamScore?: number | null;
  metacriticScore?: number | null;
  showLabels?: boolean;
}

export function ScoreBarComparison({
  criticScore,
  steamScore,
  metacriticScore,
  showLabels = true,
}: ScoreBarComparisonProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);

  const scores = [
    { label: "Critic", value: criticScore, color: colors.rust },
    { label: "Steam", value: steamScore, color: colors.sage },
    { label: "Metacritic", value: metacriticScore, color: colors.orange },
  ].filter((s) => s.value != null);

  return (
    <div className="space-y-3">
      {scores.map((score) => (
        <div key={score.label} className="space-y-1">
          {showLabels && (
            <div className="flex justify-between text-sm">
              <span style={{ color: colors.text }}>{score.label}</span>
              <span className="font-medium" style={{ color: score.color }}>
                {score.value}
              </span>
            </div>
          )}
          <div
            className="h-3 rounded-full overflow-hidden"
            style={{ backgroundColor: colors.grid }}
          >
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${score.value}%`,
                backgroundColor: score.color,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

// Radar chart for multi-metric comparison
interface RadarComparisonData {
  name: string;
  critic: number;
  user: number;
  fullMark?: number;
}

interface RadarComparisonChartProps {
  data: RadarComparisonData[];
  height?: number;
}

export function RadarComparisonChart({
  data,
  height = 300,
}: RadarComparisonChartProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px] text-gray-500">
        No data available
      </div>
    );
  }

  // Ensure fullMark is set
  const chartData = data.map((d) => ({
    ...d,
    fullMark: d.fullMark || 100,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart cx="50%" cy="50%" outerRadius="80%" data={chartData}>
        <PolarGrid stroke={colors.grid} />
        <PolarAngleAxis
          dataKey="name"
          tick={{ fill: colors.text, fontSize: 12 }}
        />
        <PolarRadiusAxis
          angle={90}
          domain={[0, 100]}
          tick={{ fill: colors.text, fontSize: 10 }}
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
        <Legend
          wrapperStyle={{ color: colors.text }}
        />
        <Radar
          name="Critic Score"
          dataKey="critic"
          stroke={colors.rust}
          fill={colors.rust}
          fillOpacity={0.3}
        />
        <Radar
          name="User Score"
          dataKey="user"
          stroke={colors.sage}
          fill={colors.sage}
          fillOpacity={0.3}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
}

// Simple side-by-side comparison boxes
interface ComparisonBoxesProps {
  criticScore: number;
  steamScore?: number | null;
  metacriticScore?: number | null;
}

export function ComparisonBoxes({
  criticScore,
  steamScore,
  metacriticScore,
}: ComparisonBoxesProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);

  const userAvg =
    steamScore != null && metacriticScore != null
      ? (steamScore + metacriticScore) / 2
      : steamScore ?? metacriticScore ?? null;

  const disparity = userAvg != null ? criticScore - userAvg : null;

  return (
    <div className="grid grid-cols-3 gap-4">
      <div
        className="p-4 rounded-lg text-center"
        style={{ backgroundColor: isDark ? colors.background : "#fef3ee" }}
      >
        <div className="text-3xl font-bold" style={{ color: colors.rust }}>
          {criticScore}
        </div>
        <div className="text-sm mt-1" style={{ color: colors.text }}>
          Critic Score
        </div>
      </div>

      <div
        className="p-4 rounded-lg text-center"
        style={{ backgroundColor: isDark ? colors.background : "#f0f5ed" }}
      >
        <div className="text-3xl font-bold" style={{ color: colors.sage }}>
          {userAvg?.toFixed(0) ?? "N/A"}
        </div>
        <div className="text-sm mt-1" style={{ color: colors.text }}>
          User Avg
        </div>
        <div className="text-xs mt-1" style={{ color: colors.text }}>
          {steamScore != null && `Steam: ${steamScore}`}
          {steamScore != null && metacriticScore != null && " / "}
          {metacriticScore != null && `MC: ${metacriticScore}`}
        </div>
      </div>

      <div
        className="p-4 rounded-lg text-center"
        style={{
          backgroundColor: isDark
            ? colors.background
            : disparity != null && disparity >= 0
              ? "#fef3ee"
              : "#f0f5ed",
        }}
      >
        <div
          className="text-3xl font-bold"
          style={{
            color:
              disparity != null && disparity >= 0 ? colors.rust : colors.sage,
          }}
        >
          {disparity != null
            ? `${disparity > 0 ? "+" : ""}${disparity.toFixed(1)}`
            : "N/A"}
        </div>
        <div className="text-sm mt-1" style={{ color: colors.text }}>
          Disparity
        </div>
      </div>
    </div>
  );
}
