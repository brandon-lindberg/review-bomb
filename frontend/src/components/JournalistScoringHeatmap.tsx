"use client";

import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import type { ReviewWithDisparity } from "@/types";
import { buildEntityPath } from "@/lib/entity-paths";

function useIsDarkMode() {
  const [isDark, setIsDark] = useState(false);
  useEffect(() => {
    const check = () => setIsDark(document.documentElement.classList.contains("dark"));
    check();
    const observer = new MutationObserver(check);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
  return isDark;
}

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

type DisparityPlatform = "combined" | "steam" | "metacritic";
type SortOrder = "chronological" | "disparity";

interface HeatmapCell {
  review: ReviewWithDisparity;
  disparity: number | null;
  year: number;
  publishedAt: Date;
}

function getDisparityValue(review: ReviewWithDisparity, platform: DisparityPlatform): number | null {
  if (platform === "steam") {
    return review.disparity_steam != null ? Number(review.disparity_steam) : null;
  }
  if (platform === "metacritic") {
    return review.disparity_metacritic != null ? Number(review.disparity_metacritic) : null;
  }
  // combined
  const steam = review.disparity_steam != null ? Number(review.disparity_steam) : null;
  const mc = review.disparity_metacritic != null ? Number(review.disparity_metacritic) : null;
  if (steam != null && mc != null) return (steam + mc) / 2;
  return steam ?? mc ?? null;
}

function disparityToColor(
  disparity: number | null,
  isDark: boolean
): string {
  if (disparity == null) return isDark ? "#3D3A35" : "#e5e7eb";

  const abs = Math.abs(disparity);
  // Clamp to [-40, 40] for color intensity
  const intensity = Math.min(abs / 30, 1);

  if (disparity > 0) {
    // Critic higher than users -> rust/red spectrum
    if (isDark) {
      const r = Math.round(45 + intensity * 179); // 45 -> 224
      const g = Math.round(42 + intensity * 48);  // 42 -> 90
      const b = Math.round(38 + intensity * 5);   // 38 -> 43
      return `rgb(${r},${g},${b})`;
    }
    const r = Math.round(245 - intensity * 58);  // 245 -> 187
    const g = Math.round(235 - intensity * 176); // 235 -> 59
    const b = Math.round(220 - intensity * 206); // 220 -> 14
    return `rgb(${r},${g},${b})`;
  }

  // Critic lower than users -> sage/green spectrum
  if (isDark) {
    const r = Math.round(45 + intensity * 98);  // 45 -> 143
    const g = Math.round(42 + intensity * 126); // 42 -> 168
    const b = Math.round(38 + intensity * 84);  // 38 -> 122
    return `rgb(${r},${g},${b})`;
  }
  const r = Math.round(245 - intensity * 133); // 245 -> 112
  const g = Math.round(235 - intensity * 106); // 235 -> 129
  const b = Math.round(220 - intensity * 124); // 220 -> 96
  return `rgb(${r},${g},${b})`;
}

interface JournalistScoringHeatmapProps {
  reviews: ReviewWithDisparity[];
}

export function JournalistScoringHeatmap({ reviews }: JournalistScoringHeatmapProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);

  const [platform, setPlatform] = useState<DisparityPlatform>("combined");
  const [sortOrder, setSortOrder] = useState<SortOrder>("chronological");
  const [yearFilter, setYearFilter] = useState<number | "all">("all");
  const [hoveredCell, setHoveredCell] = useState<HeatmapCell | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null);

  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 640);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  // Build heatmap data
  const { cells, years } = useMemo(() => {
    const allCells: HeatmapCell[] = reviews
      .filter((r) => r.published_at != null)
      .map((r) => {
        const pub = new Date(r.published_at!);
        return {
          review: r,
          disparity: getDisparityValue(r, platform),
          year: pub.getFullYear(),
          publishedAt: pub,
        };
      })
      .sort((a, b) => a.publishedAt.getTime() - b.publishedAt.getTime());

    const uniqueYears = [...new Set(allCells.map((c) => c.year))].sort();
    return { cells: allCells, years: uniqueYears };
  }, [reviews, platform]);

  // Filter and sort
  const filteredCells = useMemo(() => {
    let result = yearFilter === "all" ? cells : cells.filter((c) => c.year === yearFilter);
    if (sortOrder === "disparity") {
      result = [...result].sort((a, b) => {
        if (a.disparity == null && b.disparity == null) return 0;
        if (a.disparity == null) return 1;
        if (b.disparity == null) return -1;
        return Math.abs(b.disparity) - Math.abs(a.disparity);
      });
    }
    return result;
  }, [cells, yearFilter, sortOrder]);

  // Summary stats
  const summary = useMemo(() => {
    const withDisparity = filteredCells.filter((c) => c.disparity != null);
    const generous = withDisparity.filter((c) => c.disparity! > 5).length;
    const aligned = withDisparity.filter((c) => Math.abs(c.disparity!) <= 5).length;
    const critical = withDisparity.filter((c) => c.disparity! < -5).length;
    const total = withDisparity.length;
    return { generous, aligned, critical, total };
  }, [filteredCells]);

  // Cell sizing
  const cellSize = isMobile ? 12 : 16;
  const cellGap = 2;
  const cellStep = cellSize + cellGap;

  // Calculate container width to determine cells per row
  const [containerWidth, setContainerWidth] = useState(600);
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver(([entry]) => {
      setContainerWidth(entry.contentRect.width);
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const cellsPerRow = Math.max(1, Math.floor(containerWidth / cellStep));
  const rowCount = Math.ceil(filteredCells.length / cellsPerRow);
  const svgHeight = rowCount * cellStep + 10;

  const handleCellHover = useCallback(
    (cell: HeatmapCell, e: React.MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      setHoveredCell(cell);
      setTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    },
    []
  );

  const handleCellClick = useCallback(
    (cell: HeatmapCell) => {
      if (cell.review.game_public_id) {
        router.push(buildEntityPath("games", cell.review.game_title, cell.review.game_public_id));
      }
    },
    [router]
  );

  if (filteredCells.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px]" style={{ color: colors.text }}>
        No reviews with disparity data available
      </div>
    );
  }

  return (
    <div>
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {/* Platform toggle */}
        <div className="flex gap-1">
          {(["combined", "steam", "metacritic"] as DisparityPlatform[]).map((p) => {
            const label = p === "combined" ? "Combined" : p === "steam" ? "Steam" : "Metacritic";
            const isActive = platform === p;
            const typeColor = p === "steam" ? colors.sage : p === "metacritic" ? colors.orange : colors.rust;
            return (
              <button
                key={p}
                onClick={() => setPlatform(p)}
                className="px-3 py-1.5 text-sm rounded-lg transition-all hover:opacity-80"
                style={{
                  backgroundColor: isActive ? typeColor : isDark ? "#3D3A35" : "#f3f4f6",
                  color: isActive ? "white" : colors.text,
                  border: `2px solid ${typeColor}`,
                }}
              >
                {label}
              </button>
            );
          })}
        </div>

        {/* Sort toggle */}
        <div className="flex gap-1 text-xs ml-auto">
          <button
            onClick={() => setSortOrder("chronological")}
            className={`px-2 py-1 rounded transition-colors ${
              sortOrder === "chronological"
                ? "bg-gray-700 text-white dark:bg-gray-200 dark:text-gray-900"
                : "bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600"
            }`}
            style={sortOrder !== "chronological" ? { color: colors.text } : {}}
          >
            Chronological
          </button>
          <button
            onClick={() => setSortOrder("disparity")}
            className={`px-2 py-1 rounded transition-colors ${
              sortOrder === "disparity"
                ? "bg-gray-700 text-white dark:bg-gray-200 dark:text-gray-900"
                : "bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600"
            }`}
            style={sortOrder !== "disparity" ? { color: colors.text } : {}}
          >
            By Disparity
          </button>
        </div>
      </div>

      {/* Year filter */}
      {years.length > 1 && (
        <div className="flex flex-wrap gap-1 mb-4">
          <button
            onClick={() => setYearFilter("all")}
            className="px-2.5 py-1 text-xs rounded-md transition-colors"
            style={{
              backgroundColor: yearFilter === "all" ? (isDark ? "#4A4640" : "#d1d5db") : "transparent",
              color: yearFilter === "all" ? (isDark ? "#E5E2DD" : "#374151") : colors.axis,
              border: `1px solid ${colors.border}`,
            }}
          >
            All Time
          </button>
          {years.map((y) => (
            <button
              key={y}
              onClick={() => setYearFilter(y)}
              className="px-2.5 py-1 text-xs rounded-md transition-colors"
              style={{
                backgroundColor: yearFilter === y ? (isDark ? "#4A4640" : "#d1d5db") : "transparent",
                color: yearFilter === y ? (isDark ? "#E5E2DD" : "#374151") : colors.axis,
                border: `1px solid ${colors.border}`,
              }}
            >
              {y}
            </button>
          ))}
        </div>
      )}

      {/* Heatmap grid */}
      <div ref={containerRef} className="relative">
        <svg
          width="100%"
          height={svgHeight}
          viewBox={`0 0 ${containerWidth} ${svgHeight}`}
          className="select-none"
        >
          {filteredCells.map((cell, idx) => {
            const col = idx % cellsPerRow;
            const row = Math.floor(idx / cellsPerRow);
            const x = col * cellStep;
            const y = row * cellStep;
            const isOutlier = cell.disparity != null && Math.abs(cell.disparity) > 20;
            const isHovered = hoveredCell === cell;

            return (
              <g key={`${cell.review.id}-${idx}`}>
                <rect
                  x={x}
                  y={y}
                  width={cellSize}
                  height={cellSize}
                  rx={2}
                  fill={disparityToColor(cell.disparity, isDark)}
                  stroke={
                    isHovered
                      ? isDark ? "#E5E2DD" : "#374151"
                      : isOutlier
                        ? isDark ? "#E5D9B3" : "#D8C593"
                        : "none"
                  }
                  strokeWidth={isHovered ? 2 : isOutlier ? 1 : 0}
                  style={{ cursor: cell.review.game_public_id ? "pointer" : "default" }}
                  onMouseEnter={(e) => handleCellHover(cell, e)}
                  onMouseMove={(e) => handleCellHover(cell, e)}
                  onMouseLeave={() => {
                    setHoveredCell(null);
                    setTooltipPos(null);
                  }}
                  onClick={() => handleCellClick(cell)}
                />
              </g>
            );
          })}
        </svg>

        {/* Tooltip */}
        {hoveredCell && tooltipPos && (
          <div
            className="absolute z-50 p-3 rounded-lg shadow-lg text-sm pointer-events-none"
            style={{
              left: Math.min(tooltipPos.x + 15, containerWidth - 220),
              top: tooltipPos.y - 10,
              backgroundColor: colors.background,
              border: `1px solid ${colors.border}`,
              maxWidth: 220,
            }}
          >
            <p className="font-medium" style={{ color: colors.text }}>
              {hoveredCell.review.game_title}
            </p>
            {hoveredCell.review.outlet_name && (
              <p className="text-xs" style={{ color: colors.axis }}>
                at {hoveredCell.review.outlet_name}
              </p>
            )}
            <p className="text-xs mt-1" style={{ color: colors.axis }}>
              {hoveredCell.publishedAt.toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </p>
            <div className="mt-2 pt-2 border-t space-y-1" style={{ borderColor: colors.border }}>
              <div className="flex justify-between">
                <span style={{ color: colors.text }}>Score Given</span>
                <span className="font-medium" style={{ color: colors.text }}>
                  {hoveredCell.review.score_normalized != null
                    ? Number(hoveredCell.review.score_normalized).toFixed(0)
                    : "N/A"}
                </span>
              </div>
              {hoveredCell.review.steam_user_score != null && (
                <div className="flex justify-between">
                  <span style={{ color: colors.sage }}>Steam Users</span>
                  <span className="font-medium" style={{ color: colors.sage }}>
                    {Number(hoveredCell.review.steam_user_score).toFixed(0)}
                  </span>
                </div>
              )}
              {hoveredCell.review.metacritic_user_score != null && (
                <div className="flex justify-between">
                  <span style={{ color: colors.orange }}>MC Users</span>
                  <span className="font-medium" style={{ color: colors.orange }}>
                    {Number(hoveredCell.review.metacritic_user_score).toFixed(0)}
                  </span>
                </div>
              )}
              {hoveredCell.disparity != null && (
                <div className="flex justify-between pt-1 border-t" style={{ borderColor: colors.border }}>
                  <span style={{ color: colors.text }}>Disparity</span>
                  <span
                    className="font-bold"
                    style={{
                      color: hoveredCell.disparity > 0 ? colors.rust : colors.sage,
                    }}
                  >
                    {hoveredCell.disparity > 0 ? "+" : ""}
                    {hoveredCell.disparity.toFixed(1)}
                  </span>
                </div>
              )}
            </div>
            {hoveredCell.review.game_public_id && (
              <p className="mt-2 text-[10px]" style={{ color: colors.axis }}>
                Click to view game
              </p>
            )}
          </div>
        )}
      </div>

      {/* Summary strip */}
      {summary.total > 0 && (
        <div className="mt-4">
          {/* Bar */}
          <div className="flex rounded-full overflow-hidden h-3" style={{ backgroundColor: colors.grid }}>
            {summary.critical > 0 && (
              <div
                style={{
                  width: `${(summary.critical / summary.total) * 100}%`,
                  backgroundColor: colors.sage,
                }}
                title={`Critical: ${summary.critical} reviews`}
              />
            )}
            {summary.aligned > 0 && (
              <div
                style={{
                  width: `${(summary.aligned / summary.total) * 100}%`,
                  backgroundColor: colors.tan,
                }}
                title={`Aligned: ${summary.aligned} reviews`}
              />
            )}
            {summary.generous > 0 && (
              <div
                style={{
                  width: `${(summary.generous / summary.total) * 100}%`,
                  backgroundColor: colors.rust,
                }}
                title={`Generous: ${summary.generous} reviews`}
              />
            )}
          </div>

          {/* Labels */}
          <div className="flex justify-between mt-1.5 text-xs" style={{ color: colors.axis }}>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-sm inline-block" style={{ backgroundColor: colors.sage }}></span>
              Critical ({summary.critical}) — scored below users
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-sm inline-block" style={{ backgroundColor: colors.tan }}></span>
              Aligned ({summary.aligned})
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-sm inline-block" style={{ backgroundColor: colors.rust }}></span>
              Generous ({summary.generous}) — scored above users
            </span>
          </div>
        </div>
      )}

      {/* Color scale legend */}
      <div className="mt-4 flex items-center justify-center gap-2 text-xs" style={{ color: colors.axis }}>
        <span>Lower than users</span>
        <div className="flex">
          {[-25, -15, -5, 0, 5, 15, 25].map((d) => (
            <div
              key={d}
              className="w-4 h-3"
              style={{ backgroundColor: disparityToColor(d, isDark) }}
              title={`${d > 0 ? "+" : ""}${d}`}
            />
          ))}
        </div>
        <span>Higher than users</span>
      </div>
    </div>
  );
}
