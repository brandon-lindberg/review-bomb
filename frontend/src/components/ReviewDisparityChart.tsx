"use client";

import { useEffect, useState, useMemo } from "react";
import {
  ComposedChart,
  Scatter,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import type { ReviewWithDisparity, ReviewWithJournalist } from "@/types";

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
  disparity: number | null;
  // Context info for tooltip
  gameName?: string;
  journalistName?: string;
  outletName?: string | null;
  criticScore?: number | null;
  steamDisparity?: number | null;
  metacriticDisparity?: number | null;
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
}

export function ReviewDisparityChart({
  reviews,
  height = 300,
  context,
  gameTitle,
}: ReviewDisparityChartProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);
  const [activeType, setActiveType] = useState<DisparityType>("combined");

  // Transform reviews into chart data points (calculate all disparity types)
  const allChartData = useMemo(() => {
    return reviews
      .filter((review) => review.published_at != null)
      .map((review) => {
        const date = new Date(review.published_at!);

        // Calculate combined disparity
        const steamDisp = review.disparity_steam;
        const mcDisp = review.disparity_metacritic;
        let combinedDisp: number | null = null;
        if (steamDisp != null && mcDisp != null) {
          combinedDisp = (Number(steamDisp) + Number(mcDisp)) / 2;
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
          disparity: null, // Will be set based on activeType
          steamDisparity: steamDisp != null ? Number(steamDisp) : null,
          metacriticDisparity: mcDisp != null ? Number(mcDisp) : null,
          criticScore: review.score_normalized != null ? Number(review.score_normalized) : null,
          outletName: review.outlet_name,
        };

        // Store combined for later use
        (point as ChartDataPoint & { combinedDisparity: number | null }).combinedDisparity = combinedDisp;

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
    steam: allChartData.some((p) => p.steamDisparity != null),
    metacritic: allChartData.some((p) => p.metacriticDisparity != null),
    combined: allChartData.some((p) => (p as ChartDataPoint & { combinedDisparity: number | null }).combinedDisparity != null),
  }), [allChartData]);

  // Filter chart data for the active type
  const chartData = useMemo(() => {
    return allChartData
      .map((point) => ({
        ...point,
        disparity:
          activeType === "steam" ? point.steamDisparity :
          activeType === "metacritic" ? point.metacriticDisparity :
          (point as ChartDataPoint & { combinedDisparity: number | null }).combinedDisparity,
      }))
      .filter((point) => point.disparity != null);
  }, [allChartData, activeType]);

  if (!reviews || reviews.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px] text-gray-500">
        No review data available for chart
      </div>
    );
  }

  // Check if any disparity data exists at all
  const hasAnyData = hasData.steam || hasData.metacritic || hasData.combined;
  if (!hasAnyData) {
    return (
      <div className="flex items-center justify-center h-[200px] text-gray-500">
        No disparity data available for chart
      </div>
    );
  }

  // Custom tooltip component
  const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: Array<{ payload: ChartDataPoint }> }) => {
    if (!active || !payload || payload.length === 0) return null;

    const data = payload[0].payload;

    return (
      <div
        className="p-3 rounded-lg shadow-lg text-sm"
        style={{
          backgroundColor: colors.background,
          border: `1px solid ${colors.border}`,
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

        {/* Scores */}
        <div className="mt-2 pt-2 border-t" style={{ borderColor: colors.border }}>
          {data.criticScore != null && (
            <p style={{ color: colors.text }}>
              Critic Score: <span className="font-medium">{data.criticScore.toFixed(0)}</span>
            </p>
          )}

          {/* Disparity values */}
          <div className="mt-1 space-y-0.5">
            {data.steamDisparity != null && (
              <p style={{ color: colors.sage }}>
                Steam: <span className="font-medium">
                  {data.steamDisparity > 0 ? "+" : ""}{data.steamDisparity.toFixed(1)}
                </span>
              </p>
            )}
            {data.metacriticDisparity != null && (
              <p style={{ color: colors.orange }}>
                Metacritic: <span className="font-medium">
                  {data.metacriticDisparity > 0 ? "+" : ""}{data.metacriticDisparity.toFixed(1)}
                </span>
              </p>
            )}
          </div>
        </div>
      </div>
    );
  };

  // Get color for current active type
  const getActiveColor = () => {
    switch (activeType) {
      case "steam": return colors.sage;
      case "metacritic": return colors.orange;
      case "combined": return colors.rust;
    }
  };

  return (
    <div>
      {/* Toggle buttons */}
      <div className="flex gap-2 mb-4">
        {(["combined", "steam", "metacritic"] as DisparityType[]).map((type) => {
          const typeHasData = hasData[type];
          return (
            <button
              key={type}
              onClick={() => setActiveType(type)}
              disabled={!typeHasData}
              className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                activeType === type
                  ? "text-white"
                  : !typeHasData
                  ? "bg-gray-100 dark:bg-gray-800 opacity-50 cursor-not-allowed"
                  : "bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700"
              }`}
              style={activeType === type ? {
                backgroundColor:
                  type === "steam" ? colors.sage :
                  type === "metacritic" ? colors.orange :
                  colors.rust,
              } : {
                color: colors.text,
              }}
            >
              {type.charAt(0).toUpperCase() + type.slice(1)}
              {!typeHasData && " (N/A)"}
            </button>
          );
        })}
      </div>

      {chartData.length === 0 ? (
        <div
          className="flex items-center justify-center text-gray-500"
          style={{ height }}
        >
          No {activeType} disparity data available
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <ComposedChart data={chartData} margin={{ top: 10, right: 30, left: 20, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
            <XAxis
              dataKey="date"
              type="number"
              domain={["dataMin", "dataMax"]}
              tick={{ fontSize: 12, fill: colors.text }}
              tickLine={{ stroke: colors.axis }}
              axisLine={{ stroke: colors.axis }}
              tickFormatter={(value) => {
                const date = new Date(value);
                return date.toLocaleDateString("en-US", { month: "short", year: "numeric" });
              }}
            />
            <YAxis
              tick={{ fontSize: 12, fill: colors.text }}
              tickLine={{ stroke: colors.axis }}
              axisLine={{ stroke: colors.axis }}
              domain={["auto", "auto"]}
              tickFormatter={(value) => `${value > 0 ? "+" : ""}${value}`}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine y={0} stroke={colors.tan} strokeDasharray="5 5" />
            <Line
              type="monotone"
              dataKey="disparity"
              stroke={getActiveColor()}
              strokeWidth={2}
              dot={false}
              connectNulls
            />
            <Scatter
              dataKey="disparity"
              fill={getActiveColor()}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
