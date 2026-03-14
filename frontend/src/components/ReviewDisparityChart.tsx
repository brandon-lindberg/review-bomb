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
type PointPosition = { x: number; y: number };
type PointPositionsByType = Partial<Record<DisparityType, PointPosition>>;

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
  index: number; // unique index for identification
  // All disparity values
  steamDisparity: number | null;
  metacriticDisparity: number | null;
  combinedDisparity: number | null;
  // Rolling averages for each type
  steamRollingAvg?: number | null;
  metacriticRollingAvg?: number | null;
  combinedRollingAvg?: number | null;
  // Context info for tooltip
  gameName?: string;
  journalistName?: string;
  outletName?: string | null;
  criticScore?: number | null;
}

function isFiniteChartNumber(value: number | null | undefined): value is number {
  return value != null && Number.isFinite(value);
}

// Calculate rolling average for a specific field
function calculateRollingAverageForField(
  data: ChartDataPoint[],
  windowSize: number,
  getValue: (p: ChartDataPoint) => number | null,
  setValue: (p: ChartDataPoint, val: number | null) => void
): void {
  data.forEach((point, index) => {
    const value = getValue(point);
    if (value === null) {
      setValue(point, null);
      return;
    }

    // Get window of points (up to windowSize previous points including current)
    const start = Math.max(0, index - windowSize + 1);
    const window = data.slice(start, index + 1).filter(p => getValue(p) !== null);

    if (window.length === 0) {
      setValue(point, null);
      return;
    }

    const sum = window.reduce((acc, p) => acc + (getValue(p) || 0), 0);
    setValue(point, sum / window.length);
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

  // Track which lines are visible (all enabled by default if they have data)
  const [visibleLines, setVisibleLines] = useState<Record<DisparityType, boolean>>({
    combined: true,
    steam: true,
    metacritic: true,
  });

  const [chartMode, setChartMode] = useState<ChartMode>("trend");
  const [hoveredPoint, setHoveredPoint] = useState<ChartDataPoint | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState<{ x: number; y: number; containerWidth: number } | null>(null);
  const chartContainerRef = useRef<HTMLDivElement>(null);

  // Responsive margins - smaller on mobile
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 640);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  // Calculate rolling window size based on data volume
  const rollingWindowSize = useMemo(() => {
    const count = reviews.length;
    if (count > 500) return 30;
    if (count > 200) return 20;
    if (count > 50) return 10;
    return 5;
  }, [reviews.length]);

  // Transform reviews into chart data points with all disparity types
  const chartData = useMemo(() => {
    const data = reviews
      .filter((review) => review.published_at != null)
      .map((review, idx) => {
        const date = new Date(review.published_at!);
        const steamDisp = review.disparity_steam != null ? Number(review.disparity_steam) : null;
        const mcDisp = review.disparity_metacritic != null ? Number(review.disparity_metacritic) : null;

        // Calculate combined disparity
        let combinedDisp: number | null = null;
        if (steamDisp != null && mcDisp != null) {
          combinedDisp = (steamDisp + mcDisp) / 2;
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
          index: idx,
          steamDisparity: steamDisp,
          metacriticDisparity: mcDisp,
          combinedDisparity: combinedDisp,
          criticScore: review.score_normalized != null ? Number(review.score_normalized) : null,
          outletName: review.outlet_name,
        };

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

    // Calculate rolling averages for each disparity type
    calculateRollingAverageForField(
      data, rollingWindowSize,
      p => p.steamDisparity,
      (p, val) => { p.steamRollingAvg = val; }
    );
    calculateRollingAverageForField(
      data, rollingWindowSize,
      p => p.metacriticDisparity,
      (p, val) => { p.metacriticRollingAvg = val; }
    );
    calculateRollingAverageForField(
      data, rollingWindowSize,
      p => p.combinedDisparity,
      (p, val) => { p.combinedRollingAvg = val; }
    );

    return data;
  }, [reviews, context, gameTitle, rollingWindowSize]);

  // Check which disparity types have data
  const hasData = useMemo(() => ({
    steam: chartData.some((p) => p.steamDisparity != null),
    metacritic: chartData.some((p) => p.metacriticDisparity != null),
    combined: chartData.some((p) => p.combinedDisparity != null),
  }), [chartData]);

  const visibleTypeCount = useMemo(
    () =>
      (visibleLines.steam && hasData.steam ? 1 : 0)
      + (visibleLines.metacritic && hasData.metacritic ? 1 : 0)
      + (visibleLines.combined && hasData.combined ? 1 : 0),
    [hasData, visibleLines]
  );

  const allPointsStyle = useMemo(() => {
    const pointLoad = chartData.length * Math.max(1, visibleTypeCount);

    if (pointLoad > 2500) {
      return { pointRadius: 1.75, pointOpacity: 0.18, hoverRadius: 6, lineWidth: 2 };
    }
    if (pointLoad > 1200) {
      return { pointRadius: 2.25, pointOpacity: 0.22, hoverRadius: 6.5, lineWidth: 2.25 };
    }
    if (pointLoad > 500) {
      return { pointRadius: 2.75, pointOpacity: 0.28, hoverRadius: 7, lineWidth: 2.5 };
    }

    return { pointRadius: 3.25, pointOpacity: 0.38, hoverRadius: 7.5, lineWidth: 2.75 };
  }, [chartData.length, visibleTypeCount]);

  // Calculate domain bounds for scaling
  const { xDomain, yDomain } = useMemo(() => {
    if (chartData.length === 0) return { xDomain: [0, 1], yDomain: [-10, 10] };

    const dates = chartData.map(d => d.date);

    // Collect all visible disparities for y-domain calculation
    const disparities: number[] = [];
    chartData.forEach(d => {
      if (visibleLines.steam && d.steamDisparity != null) disparities.push(d.steamDisparity);
      if (visibleLines.metacritic && d.metacriticDisparity != null) disparities.push(d.metacriticDisparity);
      if (visibleLines.combined && d.combinedDisparity != null) disparities.push(d.combinedDisparity);
    });

    if (disparities.length === 0) return { xDomain: [0, 1], yDomain: [-10, 10] };

    const minDate = Math.min(...dates);
    const maxDate = Math.max(...dates);
    const minDisp = Math.min(...disparities);
    const maxDisp = Math.max(...disparities);

    const dateRange = maxDate - minDate || 86400000;
    const xPadding = Math.max(dateRange * 0.05, 86400000);
    const yRange = maxDisp - minDisp || 20;
    const yPadding = Math.max(yRange * 0.12, 8);

    return {
      xDomain: [minDate - xPadding, maxDate + xPadding],
      yDomain: [minDisp - yPadding, maxDisp + yPadding],
    };
  }, [chartData, visibleLines]);

  // Store point positions after rendering
  const pointPositionsRef = useRef<Map<number, PointPositionsByType>>(new Map());

  const setPointPosition = useCallback((index: number, type: DisparityType, x?: number, y?: number) => {
    if (!isFiniteChartNumber(x) || !isFiniteChartNumber(y)) return;

    const existing = pointPositionsRef.current.get(index) ?? {};
    existing[type] = { x, y };
    pointPositionsRef.current.set(index, existing);
  }, []);

  // Handle mouse move to find closest point
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!chartContainerRef.current || chartData.length === 0) return;

    const rect = chartContainerRef.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    let closestPoint: ChartDataPoint | null = null;
    let closestDistance = Infinity;

    for (const point of chartData) {
      // Only consider points that have at least one visible disparity
      const hasVisibleData =
        (visibleLines.steam && point.steamDisparity !== null) ||
        (visibleLines.metacritic && point.metacriticDisparity !== null) ||
        (visibleLines.combined && point.combinedDisparity !== null);

      if (!hasVisibleData) continue;

      const positions = pointPositionsRef.current.get(point.index);
      if (!positions) continue;

      for (const type of ["steam", "metacritic", "combined"] as DisparityType[]) {
        if (!visibleLines[type]) continue;
        const pos = positions[type];
        if (!pos) continue;

        const dx = mouseX - pos.x;
        const dy = mouseY - pos.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance < closestDistance) {
          closestDistance = distance;
          closestPoint = point;
        }
      }
    }

    if (closestPoint && closestDistance < 50) {
      setHoveredPoint(closestPoint);
      setTooltipPosition({ x: mouseX, y: mouseY, containerWidth: rect.width });
    } else {
      setHoveredPoint(null);
      setTooltipPosition(null);
    }
  }, [chartData, visibleLines]);

  const handleMouseLeave = useCallback(() => {
    setHoveredPoint(null);
    setTooltipPosition(null);
  }, []);

  // Toggle line visibility
  const toggleLine = (type: DisparityType) => {
    if (!hasData[type]) return;
    setVisibleLines(prev => ({ ...prev, [type]: !prev[type] }));
  };

  if (!reviews || reviews.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px] text-gray-500">
        No review data available for chart
      </div>
    );
  }

  const hasAnyData = hasData.steam || hasData.metacritic || hasData.combined;
  if (!hasAnyData) {
    return (
      <div className="flex items-center justify-center h-[200px] text-gray-500">
        No disparity data available for chart
      </div>
    );
  }

  // Check if at least one line is visible
  const hasVisibleLine =
    (visibleLines.steam && hasData.steam) ||
    (visibleLines.metacritic && hasData.metacritic) ||
    (visibleLines.combined && hasData.combined);

  // Render custom tooltip
  const renderTooltip = () => {
    if (!hoveredPoint || !tooltipPosition) return null;

    const data = hoveredPoint;

    const tooltipWidth = 220;
    let tooltipX = tooltipPosition.x + 15;
    const tooltipY = tooltipPosition.y - 10;

    if (tooltipX > tooltipPosition.containerWidth - tooltipWidth) {
      tooltipX = tooltipPosition.x - (tooltipWidth + 15);
    }

    return (
      <div
        className="absolute z-50 p-3 rounded-lg shadow-lg text-sm pointer-events-none"
        style={{
          left: tooltipX,
          top: tooltipY,
          backgroundColor: colors.background,
          border: `1px solid ${colors.border}`,
          maxWidth: 220,
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

          {/* All disparity values (only show visible ones) */}
          <div className="mt-2 space-y-1">
            {visibleLines.steam && data.steamDisparity != null && (
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colors.sage }}></span>
                  <span style={{ color: colors.sage }}>Steam</span>
                </span>
                <span className="font-medium" style={{ color: colors.sage }}>
                  {data.steamDisparity > 0 ? "+" : ""}{data.steamDisparity.toFixed(1)}
                </span>
              </div>
            )}
            {visibleLines.metacritic && data.metacriticDisparity != null && (
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colors.orange }}></span>
                  <span style={{ color: colors.orange }}>Metacritic</span>
                </span>
                <span className="font-medium" style={{ color: colors.orange }}>
                  {data.metacriticDisparity > 0 ? "+" : ""}{data.metacriticDisparity.toFixed(1)}
                </span>
              </div>
            )}
            {visibleLines.combined && data.combinedDisparity != null && (
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colors.rust }}></span>
                  <span style={{ color: colors.rust }}>Combined</span>
                </span>
                <span className="font-medium" style={{ color: colors.rust }}>
                  {data.combinedDisparity > 0 ? "+" : ""}{data.combinedDisparity.toFixed(1)}
                </span>
              </div>
            )}
          </div>

          {/* Rolling averages in trend mode */}
          {chartMode === "trend" && (
            <div className="mt-2 pt-2 border-t text-xs" style={{ borderColor: colors.border }}>
              <p className="mb-1" style={{ color: colors.axis }}>{rollingWindowSize}-review trend:</p>
              <div className="space-y-0.5">
                {visibleLines.steam && data.steamRollingAvg != null && (
                  <p style={{ color: colors.sage }}>
                    Steam: {data.steamRollingAvg > 0 ? "+" : ""}{data.steamRollingAvg.toFixed(1)}
                  </p>
                )}
                {visibleLines.metacritic && data.metacriticRollingAvg != null && (
                  <p style={{ color: colors.orange }}>
                    MC: {data.metacriticRollingAvg > 0 ? "+" : ""}{data.metacriticRollingAvg.toFixed(1)}
                  </p>
                )}
                {visibleLines.combined && data.combinedRollingAvg != null && (
                  <p style={{ color: colors.rust }}>
                    Combined: {data.combinedRollingAvg > 0 ? "+" : ""}{data.combinedRollingAvg.toFixed(1)}
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div>
      {/* Toggle buttons */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        {/* Disparity type toggles - now checkboxes */}
        <div className="flex gap-2">
          {(["steam", "metacritic", "combined"] as DisparityType[]).map((type) => {
            const typeHasData = hasData[type];
            const isVisible = visibleLines[type] && typeHasData;
            const typeColor = type === "steam" ? colors.sage : type === "metacritic" ? colors.orange : colors.rust;

            return (
              <button
                key={type}
                onClick={() => toggleLine(type)}
                disabled={!typeHasData}
                className={`flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg transition-all ${
                  !typeHasData
                    ? "bg-gray-100 dark:bg-gray-800 opacity-40 cursor-not-allowed"
                    : "hover:opacity-80"
                }`}
                style={{
                  backgroundColor: isVisible ? typeColor : isDark ? "#3D3A35" : "#f3f4f6",
                  color: isVisible ? "white" : colors.text,
                  border: `2px solid ${typeHasData ? typeColor : "transparent"}`,
                }}
              >
                {/* Checkbox indicator */}
                <span
                  className="w-3.5 h-3.5 rounded-sm flex items-center justify-center text-xs"
                  style={{
                    backgroundColor: isVisible ? "rgba(255,255,255,0.3)" : "transparent",
                    border: isVisible ? "none" : `1.5px solid ${typeHasData ? typeColor : colors.axis}`,
                  }}
                >
                  {isVisible && "✓"}
                </span>
                {type.charAt(0).toUpperCase() + type.slice(1)}
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

      {!hasVisibleLine ? (
        <div
          className="flex items-center justify-center text-gray-500"
          style={{ height }}
        >
          Select at least one disparity type to display
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
              margin={isMobile ? { top: 5, right: 10, left: 5, bottom: 20 } : { top: 10, right: 15, left: 10, bottom: 25 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
              <XAxis
                dataKey="date"
                type="number"
                domain={xDomain as [number, number]}
                tick={{ fontSize: isMobile ? 10 : 12, fill: colors.text }}
                tickLine={{ stroke: colors.axis }}
                axisLine={{ stroke: colors.axis }}
                tickFormatter={(value) => {
                  const date = new Date(value);
                  return date.toLocaleDateString("en-US", { month: "short", year: isMobile ? "2-digit" : "numeric" });
                }}
              />
              <YAxis
                tick={{ fontSize: isMobile ? 10 : 12, fill: colors.text }}
                tickLine={{ stroke: colors.axis }}
                axisLine={{ stroke: colors.axis }}
                domain={yDomain as [number, number]}
                width={isMobile ? 35 : 45}
                tickFormatter={(value) => `${value > 0 ? "+" : ""}${Math.round(value)}`}
                label={isMobile ? undefined : {
                  value: "Disparity",
                  angle: -90,
                  position: "insideLeft",
                  style: { textAnchor: "middle", fill: colors.text, fontSize: 12 },
                }}
              />
              <ReferenceLine y={0} stroke={colors.tan} strokeWidth={2} strokeDasharray="5 5" />

              {chartMode === "trend" ? (
                <>
                  {/* Steam trend line */}
                  {visibleLines.steam && hasData.steam && (
                    <Line
                      type="monotone"
                      dataKey="steamRollingAvg"
                      stroke={colors.sage}
                      strokeWidth={3}
                      dot={false}
                      activeDot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  )}
                  {/* Metacritic trend line */}
                  {visibleLines.metacritic && hasData.metacritic && (
                    <Line
                      type="monotone"
                      dataKey="metacriticRollingAvg"
                      stroke={colors.orange}
                      strokeWidth={3}
                      dot={false}
                      activeDot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  )}
                  {/* Combined trend line */}
                  {visibleLines.combined && hasData.combined && (
                    <Line
                      type="monotone"
                      dataKey="combinedRollingAvg"
                      stroke={colors.rust}
                      strokeWidth={3}
                      dot={false}
                      activeDot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  )}
                  {visibleLines.steam && hasData.steam && (
                    <Scatter
                      dataKey="steamDisparity"
                      fill="transparent"
                      isAnimationActive={false}
                      shape={(props: { cx?: number; cy?: number; payload?: ChartDataPoint }) => {
                        if (
                          !props.payload
                          || !isFiniteChartNumber(props.payload.steamDisparity)
                          || !isFiniteChartNumber(props.cx)
                          || !isFiniteChartNumber(props.cy)
                        ) {
                          return <circle r={0} />;
                        }

                        setPointPosition(props.payload.index, "steam", props.cx, props.cy);

                        const isHovered = hoveredPoint?.index === props.payload.index;
                        if (!isHovered) return <circle cx={props.cx} cy={props.cy} r={0} fill="transparent" />;

                        return (
                          <circle
                            cx={props.cx}
                            cy={props.cy}
                            r={7}
                            fill={colors.sage}
                            stroke={colors.background}
                            strokeWidth={2}
                          />
                        );
                      }}
                    />
                  )}
                  {visibleLines.metacritic && hasData.metacritic && (
                    <Scatter
                      dataKey="metacriticDisparity"
                      fill="transparent"
                      isAnimationActive={false}
                      shape={(props: { cx?: number; cy?: number; payload?: ChartDataPoint }) => {
                        if (
                          !props.payload
                          || !isFiniteChartNumber(props.payload.metacriticDisparity)
                          || !isFiniteChartNumber(props.cx)
                          || !isFiniteChartNumber(props.cy)
                        ) {
                          return <circle r={0} />;
                        }

                        setPointPosition(props.payload.index, "metacritic", props.cx, props.cy);

                        const isHovered = hoveredPoint?.index === props.payload.index;
                        if (!isHovered) return <circle cx={props.cx} cy={props.cy} r={0} fill="transparent" />;

                        return (
                          <circle
                            cx={props.cx}
                            cy={props.cy}
                            r={7}
                            fill={colors.orange}
                            stroke={colors.background}
                            strokeWidth={2}
                          />
                        );
                      }}
                    />
                  )}
                  {visibleLines.combined && hasData.combined && (
                    <Scatter
                      dataKey="combinedDisparity"
                      fill="transparent"
                      isAnimationActive={false}
                      shape={(props: { cx?: number; cy?: number; payload?: ChartDataPoint }) => {
                        if (
                          !props.payload
                          || !isFiniteChartNumber(props.payload.combinedDisparity)
                          || !isFiniteChartNumber(props.cx)
                          || !isFiniteChartNumber(props.cy)
                        ) {
                          return <circle r={0} />;
                        }

                        setPointPosition(props.payload.index, "combined", props.cx, props.cy);

                        const isHovered = hoveredPoint?.index === props.payload.index;
                        if (!isHovered) return <circle cx={props.cx} cy={props.cy} r={0} fill="transparent" />;

                        return (
                          <circle
                            cx={props.cx}
                            cy={props.cy}
                            r={7}
                            fill={colors.rust}
                            stroke={colors.background}
                            strokeWidth={2}
                          />
                        );
                      }}
                    />
                  )}
                </>
              ) : (
                <>
                  {/* Steam trend line and review points */}
                  {visibleLines.steam && hasData.steam && (
                    <>
                      <Line
                        type="monotone"
                        dataKey="steamRollingAvg"
                        stroke={colors.sage}
                        strokeWidth={allPointsStyle.lineWidth}
                        strokeOpacity={0.9}
                        dot={false}
                        activeDot={false}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <Scatter
                        dataKey="steamDisparity"
                        fill={colors.sage}
                        fillOpacity={0.7}
                        isAnimationActive={false}
                        shape={(props: { cx?: number; cy?: number; payload?: ChartDataPoint }) => {
                          if (
                            !props.payload
                            || !isFiniteChartNumber(props.payload.steamDisparity)
                            || !isFiniteChartNumber(props.cx)
                            || !isFiniteChartNumber(props.cy)
                          ) {
                            return <circle r={0} />;
                          }

                          setPointPosition(props.payload.index, "steam", props.cx, props.cy);

                          const isHovered = hoveredPoint?.index === props.payload.index;
                          return (
                            <circle
                              cx={props.cx}
                              cy={props.cy}
                              r={isHovered ? allPointsStyle.hoverRadius : allPointsStyle.pointRadius}
                              fill={colors.sage}
                              fillOpacity={isHovered ? 0.95 : allPointsStyle.pointOpacity}
                              stroke={isHovered ? colors.background : "none"}
                              strokeWidth={isHovered ? 2 : 0}
                            />
                          );
                        }}
                      />
                    </>
                  )}
                  {/* Metacritic trend line and review points */}
                  {visibleLines.metacritic && hasData.metacritic && (
                    <>
                      <Line
                        type="monotone"
                        dataKey="metacriticRollingAvg"
                        stroke={colors.orange}
                        strokeWidth={allPointsStyle.lineWidth}
                        strokeOpacity={0.9}
                        dot={false}
                        activeDot={false}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <Scatter
                        dataKey="metacriticDisparity"
                        fill={colors.orange}
                        fillOpacity={0.7}
                        isAnimationActive={false}
                        shape={(props: { cx?: number; cy?: number; payload?: ChartDataPoint }) => {
                          if (
                            !props.payload
                            || !isFiniteChartNumber(props.payload.metacriticDisparity)
                            || !isFiniteChartNumber(props.cx)
                            || !isFiniteChartNumber(props.cy)
                          ) {
                            return <circle r={0} />;
                          }

                          setPointPosition(props.payload.index, "metacritic", props.cx, props.cy);

                          const isHovered = hoveredPoint?.index === props.payload.index;
                          return (
                            <circle
                              cx={props.cx}
                              cy={props.cy}
                              r={isHovered ? allPointsStyle.hoverRadius : allPointsStyle.pointRadius}
                              fill={colors.orange}
                              fillOpacity={isHovered ? 0.95 : allPointsStyle.pointOpacity}
                              stroke={isHovered ? colors.background : "none"}
                              strokeWidth={isHovered ? 2 : 0}
                            />
                          );
                        }}
                      />
                    </>
                  )}
                  {/* Combined trend line and review points */}
                  {visibleLines.combined && hasData.combined && (
                    <>
                      <Line
                        type="monotone"
                        dataKey="combinedRollingAvg"
                        stroke={colors.rust}
                        strokeWidth={allPointsStyle.lineWidth}
                        strokeOpacity={0.9}
                        dot={false}
                        activeDot={false}
                        connectNulls
                        isAnimationActive={false}
                      />
                      <Scatter
                        dataKey="combinedDisparity"
                        fill={colors.rust}
                        fillOpacity={0.7}
                        isAnimationActive={false}
                        shape={(props: { cx?: number; cy?: number; payload?: ChartDataPoint }) => {
                          if (
                            !props.payload
                            || !isFiniteChartNumber(props.payload.combinedDisparity)
                            || !isFiniteChartNumber(props.cx)
                            || !isFiniteChartNumber(props.cy)
                          ) {
                            return <circle r={0} />;
                          }

                          setPointPosition(props.payload.index, "combined", props.cx, props.cy);

                          const isHovered = hoveredPoint?.index === props.payload.index;
                          return (
                            <circle
                              cx={props.cx}
                              cy={props.cy}
                              r={isHovered ? allPointsStyle.hoverRadius : allPointsStyle.pointRadius}
                              fill={colors.rust}
                              fillOpacity={isHovered ? 0.95 : allPointsStyle.pointOpacity}
                              stroke={isHovered ? colors.background : "none"}
                              strokeWidth={isHovered ? 2 : 0}
                            />
                          );
                        }}
                      />
                    </>
                  )}
                </>
              )}
            </ComposedChart>
          </ResponsiveContainer>

          {/* Custom tooltip */}
          {renderTooltip()}
        </div>
      )}

      {/* Legend */}
      <div className="mt-3 flex items-center justify-center gap-4 text-xs" style={{ color: colors.axis }}>
        <span>Positive = critic higher than users</span>
        <span className="w-1 h-1 rounded-full" style={{ backgroundColor: colors.axis }}></span>
        <span>Negative = critic lower than users</span>
      </div>
    </div>
  );
}
