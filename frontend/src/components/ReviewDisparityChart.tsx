"use client";

import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import {
  ComposedChart,
  Line,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
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
  rollingAvg?: number | null; // Rolling average for trend line
  index: number; // unique index for identification
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
  const [hoveredPoint, setHoveredPoint] = useState<ChartDataPoint | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState<{ x: number; y: number } | null>(null);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  
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
      .map((review, idx) => {
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
          index: idx,
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

  // Filter chart data for the active type and calculate rolling average
  const chartData = useMemo(() => {
    const filtered = allChartData
      .map((point, idx) => ({
        ...point,
        index: idx, // Re-assign index after filtering
        disparity:
          activeType === "steam" ? point.steamDisparity :
          activeType === "metacritic" ? point.metacriticDisparity :
          (point as ChartDataPoint & { combinedDisparity: number | null }).combinedDisparity,
      }))
      .filter((point) => point.disparity != null);
    
    // Calculate rolling average for trend line
    return calculateRollingAverage(filtered, rollingWindowSize);
  }, [allChartData, activeType, rollingWindowSize]);

  // Calculate domain bounds for scaling
  const { xDomain, yDomain } = useMemo(() => {
    if (chartData.length === 0) return { xDomain: [0, 1], yDomain: [-10, 10] };
    
    const dates = chartData.map(d => d.date);
    const disparities = chartData.map(d => d.disparity!);
    
    const minDate = Math.min(...dates);
    const maxDate = Math.max(...dates);
    const minDisp = Math.min(...disparities);
    const maxDisp = Math.max(...disparities);
    
    // Use percentage-based padding for x-axis (5% of range, minimum 1 day)
    const dateRange = maxDate - minDate || 86400000; // At least 1 day
    const xPadding = Math.max(dateRange * 0.05, 86400000);
    // Add 10% padding to y-axis
    const yRange = maxDisp - minDisp || 20;
    const yPadding = yRange * 0.1;

    return {
      xDomain: [minDate - xPadding, maxDate + xPadding],
      yDomain: [minDisp - yPadding, maxDisp + yPadding],
    };
  }, [chartData]);

  // Store point positions after rendering
  const pointPositionsRef = useRef<Map<number, { x: number; y: number }>>(new Map());

  // Handle mouse move to find closest point using stored positions
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!chartContainerRef.current || chartData.length === 0) return;
    
    const rect = chartContainerRef.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
    // Find closest point by pixel distance using stored positions
    let closestPoint: ChartDataPoint | null = null;
    let closestDistance = Infinity;
    
    for (const point of chartData) {
      if (point.disparity === null) continue;
      
      const pos = pointPositionsRef.current.get(point.index);
      if (!pos) continue;
      
      // Calculate distance from mouse to point
      const dx = mouseX - pos.x;
      const dy = mouseY - pos.y;
      const distance = Math.sqrt(dx * dx + dy * dy);
      
      if (distance < closestDistance) {
        closestDistance = distance;
        closestPoint = point;
      }
    }
    
    // Only show tooltip if within reasonable distance (50px)
    if (closestPoint && closestDistance < 50) {
      setHoveredPoint(closestPoint);
      setTooltipPosition({ x: mouseX, y: mouseY });
    } else {
      setHoveredPoint(null);
      setTooltipPosition(null);
    }
  }, [chartData]);

  const handleMouseLeave = useCallback(() => {
    setHoveredPoint(null);
    setTooltipPosition(null);
  }, []);

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

  // Get color for current active type
  const getActiveColor = () => {
    switch (activeType) {
      case "steam": return colors.sage;
      case "metacritic": return colors.orange;
      case "combined": return colors.rust;
    }
  };

  // Render custom tooltip
  const renderTooltip = () => {
    if (!hoveredPoint || !tooltipPosition) return null;
    
    const data = hoveredPoint;
    
    // Calculate tooltip position (avoid going off-screen)
    let tooltipX = tooltipPosition.x + 15;
    let tooltipY = tooltipPosition.y - 10;
    
    // Adjust if too far right
    if (chartContainerRef.current && tooltipX > chartContainerRef.current.offsetWidth - 200) {
      tooltipX = tooltipPosition.x - 215;
    }
    
    return (
      <div
        className="absolute z-50 p-3 rounded-lg shadow-lg text-sm pointer-events-none"
        style={{
          left: tooltipX,
          top: tooltipY,
          backgroundColor: colors.background,
          border: `1px solid ${colors.border}`,
          maxWidth: 200,
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
        <div 
          ref={chartContainerRef}
          className="relative"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          <ResponsiveContainer width="100%" height={height}>
            <ComposedChart 
              data={chartData} 
              margin={{ top: 10, right: 30, left: 60, bottom: 30 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
              <XAxis
                dataKey="date"
                type="number"
                domain={xDomain as [number, number]}
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
                domain={yDomain as [number, number]}
                tickFormatter={(value) => `${value > 0 ? "+" : ""}${Math.round(value)}`}
                label={{
                  value: "Disparity",
                  angle: -90,
                  position: "insideLeft",
                  style: { textAnchor: "middle", fill: colors.text, fontSize: 12 },
                }}
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
                    connectNulls
                    name="Rolling Average"
                    isAnimationActive={false}
                  />
                  {/* Individual points */}
                  <Scatter
                    dataKey="disparity"
                    fill={getActiveColor()}
                    fillOpacity={0.4}
                    isAnimationActive={false}
                    shape={(props: { cx: number; cy: number; payload: ChartDataPoint }) => {
                      // Store position for hover detection
                      if (props.cx && props.cy) {
                        pointPositionsRef.current.set(props.payload.index, { x: props.cx, y: props.cy });
                      }
                      const isHovered = hoveredPoint?.index === props.payload.index;
                      return (
                        <circle 
                          cx={props.cx} 
                          cy={props.cy} 
                          r={isHovered ? 10 : 5} 
                          fill={getActiveColor()} 
                          fillOpacity={isHovered ? 1 : 0.4}
                          stroke={isHovered ? colors.background : "none"}
                          strokeWidth={isHovered ? 2 : 0}
                        />
                      );
                    }}
                  />
                </>
              ) : (
                <>
                  {/* Connecting line */}
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
                  {/* Individual points */}
                  <Scatter
                    dataKey="disparity"
                    fill={getActiveColor()}
                    isAnimationActive={false}
                    shape={(props: { cx: number; cy: number; payload: ChartDataPoint }) => {
                      // Store position for hover detection
                      if (props.cx && props.cy) {
                        pointPositionsRef.current.set(props.payload.index, { x: props.cx, y: props.cy });
                      }
                      const isHovered = hoveredPoint?.index === props.payload.index;
                      return (
                        <circle 
                          cx={props.cx} 
                          cy={props.cy} 
                          r={isHovered ? 10 : 5} 
                          fill={getActiveColor()} 
                          fillOpacity={isHovered ? 1 : 0.7}
                          stroke={isHovered ? colors.background : "none"}
                          strokeWidth={isHovered ? 2 : 0}
                        />
                      );
                    }}
                  />
                </>
              )}
            </ComposedChart>
          </ResponsiveContainer>
          
          {/* Custom tooltip */}
          {renderTooltip()}
        </div>
      )}
    </div>
  );
}
