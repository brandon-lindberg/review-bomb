"use client";

import { useEffect, useState, useMemo } from "react";
import {
  ComposedChart,
  Line,
  Scatter,
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
  date: number; // timestamp for sorting (may include offset for overlapping points)
  originalDate?: number; // original timestamp without offset
  dateLabel: string;
  disparity: number | null;
  rollingAvg?: number | null; // Rolling average for trend line
  // Context info for tooltip
  gameName?: string;
  journalistName?: string;
  outletName?: string | null;
  criticScore?: number | null;
  steamDisparity?: number | null;
  metacriticDisparity?: number | null;
}

// Calculate rolling average
function calculateRollingAverage(data: ChartDataPoint[], windowSize: number): ChartDataPoint[] {
  return data.map((point, index) => {
    if (point.disparity === null) return point;
    
    // Get window of points (up to windowSize previous points including current)
    const start = Math.max(0, index - windowSize + 1);
    const window = data.slice(start, index + 1).filter(p => p.disparity !== null);
    
    if (window.length === 0) return point;
    
    const sum = window.reduce((acc, p) => acc + (p.disparity || 0), 0);
    const avg = sum / window.length;
    
    return {
      ...point,
      rollingAvg: avg,
    };
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
}

type ChartMode = "trend" | "all";

export function ReviewDisparityChart({
  reviews,
  height = 300,
  context,
  gameTitle,
}: ReviewDisparityChartProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);
  const [activeType, setActiveType] = useState<DisparityType>("combined");
  const [chartMode, setChartMode] = useState<ChartMode>("trend");
  
  // Calculate rolling window size based on data volume
  const rollingWindowSize = useMemo(() => {
    const count = reviews.length;
    if (count > 500) return 30;  // Large dataset: 30-review rolling avg
    if (count > 200) return 20;  // Medium dataset: 20-review rolling avg
    if (count > 50) return 10;   // Small dataset: 10-review rolling avg
    return 5;                     // Very small: 5-review rolling avg
  }, [reviews.length]);

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

  // Filter chart data for the active type, add offsets for overlapping dates, and calculate rolling average
  const chartData = useMemo(() => {
    const filtered = allChartData
      .map((point) => ({
        ...point,
        disparity:
          activeType === "steam" ? point.steamDisparity :
          activeType === "metacritic" ? point.metacriticDisparity :
          (point as ChartDataPoint & { combinedDisparity: number | null }).combinedDisparity,
      }))
      .filter((point) => point.disparity != null);
    
    // Add small time offsets to separate points with the same date
    // This allows each point to be individually selectable
    const dateCountMap = new Map<number, number>();
    const offsetData = filtered.map((point) => {
      const baseDate = point.date;
      const count = dateCountMap.get(baseDate) || 0;
      dateCountMap.set(baseDate, count + 1);
      
      // Add offset: each duplicate date gets 1 hour offset (3600000 ms)
      // This spreads points visually while keeping them on roughly the same day
      const offsetDate = baseDate + (count * 3600000);
      
      return {
        ...point,
        date: offsetDate,
        originalDate: baseDate, // Keep original for display
      };
    });
    
    // Calculate rolling average for trend line
    return calculateRollingAverage(offsetData, rollingWindowSize);
  }, [allChartData, activeType, rollingWindowSize]);

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
            {chartMode === "trend" && data.rollingAvg != null && (
              <p className="mt-1 pt-1 border-t" style={{ borderColor: colors.border, color: colors.text }}>
                Trend ({rollingWindowSize}-review avg): <span className="font-medium">
                  {data.rollingAvg > 0 ? "+" : ""}{data.rollingAvg.toFixed(1)}
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
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        {/* Disparity type toggles */}
        <div className="flex gap-2">
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
        
        {/* Chart mode toggle */}
        <div className="flex gap-1 text-xs">
          <button
            onClick={() => setChartMode("trend")}
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
            onClick={() => setChartMode("all")}
            className={`px-2 py-1 rounded transition-colors ${
              chartMode === "all"
                ? "bg-gray-700 text-white dark:bg-gray-200 dark:text-gray-900"
                : "bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600"
            }`}
            style={chartMode !== "all" ? { color: colors.text } : {}}
          >
            All Points
          </button>
        </div>
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
          <ComposedChart 
            data={chartData} 
            margin={{ top: 10, right: 30, left: 20, bottom: 10 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
            <XAxis
              dataKey="date"
              type="number"
              domain={[(dataMin: number) => dataMin - 86400000 * 7, (dataMax: number) => dataMax + 86400000 * 7]}
              tick={{ fontSize: 12, fill: colors.text }}
              tickLine={{ stroke: colors.axis }}
              axisLine={{ stroke: colors.axis }}
              tickFormatter={(value) => {
                const date = new Date(value);
                return date.toLocaleDateString("en-US", { month: "short", year: "numeric" });
              }}
              padding={{ left: 20, right: 20 }}
            />
            <YAxis
              tick={{ fontSize: 12, fill: colors.text }}
              tickLine={{ stroke: colors.axis }}
              axisLine={{ stroke: colors.axis }}
              domain={["auto", "auto"]}
              tickFormatter={(value) => `${value > 0 ? "+" : ""}${value}`}
            />
            <Tooltip 
              content={<CustomTooltip />} 
              cursor={{ strokeDasharray: '3 3', stroke: colors.axis }}
            />
            <ReferenceLine y={0} stroke={colors.tan} strokeDasharray="5 5" />
            
            {chartMode === "trend" ? (
              <>
                {/* Rolling average trend line */}
                <Line
                  type="monotone"
                  dataKey="rollingAvg"
                  stroke={getActiveColor()}
                  strokeWidth={3}
                  dot={false}
                  activeDot={false}
                  connectNulls
                  name="Rolling Average"
                  isAnimationActive={false}
                />
                {/* Trend mode: Scatter points for individual reviews (better hover detection) */}
                <Scatter
                  dataKey="disparity"
                  fill={getActiveColor()}
                  fillOpacity={0.4}
                  isAnimationActive={false}
                  shape={(props: { cx: number; cy: number }) => (
                    <circle cx={props.cx} cy={props.cy} r={6} fill={getActiveColor()} fillOpacity={0.4} />
                  )}
                />
              </>
            ) : (
              <>
                {/* All points mode: Connecting line */}
                <Line
                  type="monotone"
                  dataKey="disparity"
                  stroke={getActiveColor()}
                  strokeWidth={1.5}
                  strokeOpacity={0.5}
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
                {/* Scatter points for better hover detection */}
                <Scatter
                  dataKey="disparity"
                  fill={getActiveColor()}
                  isAnimationActive={false}
                  shape={(props: { cx: number; cy: number }) => (
                    <circle cx={props.cx} cy={props.cy} r={6} fill={getActiveColor()} />
                  )}
                />
              </>
            )}
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
