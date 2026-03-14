"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";
import {
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  ComposedChart,
} from "recharts";
import type { ReviewWithJournalist } from "@/types";
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

type Granularity = "monthly" | "quarterly";
type BandName = "generous" | "aligned" | "critical";

interface MonthBucket {
  key: string; // "2024-01" or "2024-Q1"
  label: string;
  generous: number;
  aligned: number;
  critical: number;
  total: number;
  avgDisparity: number | null;
  journalistCount: number;
  startDate: Date;
  endDate: Date;
}

function getMonthKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function getQuarterKey(date: Date): string {
  const q = Math.floor(date.getMonth() / 3) + 1;
  return `${date.getFullYear()}-Q${q}`;
}

function formatMonthLabel(key: string): string {
  if (key.includes("Q")) {
    const [year, q] = key.split("-");
    return `${q} ${year}`;
  }
  const [year, month] = key.split("-");
  const date = new Date(Number(year), Number(month) - 1);
  return date.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

function classifyDisparity(review: ReviewWithJournalist): BandName {
  const steam = review.disparity_steam != null ? Number(review.disparity_steam) : null;
  const mc = review.disparity_metacritic != null ? Number(review.disparity_metacritic) : null;
  let combined: number | null = null;
  if (steam != null && mc != null) combined = (steam + mc) / 2;
  else combined = steam ?? mc ?? null;

  if (combined == null) return "aligned"; // no data -> assume aligned
  if (combined > 5) return "generous";
  if (combined < -5) return "critical";
  return "aligned";
}

function getReviewCombinedDisparity(review: ReviewWithJournalist): number | null {
  const steam = review.disparity_steam != null ? Number(review.disparity_steam) : null;
  const mc = review.disparity_metacritic != null ? Number(review.disparity_metacritic) : null;
  if (steam != null && mc != null) return (steam + mc) / 2;
  return steam ?? mc ?? null;
}

interface OutletActivityTimelineProps {
  reviews: ReviewWithJournalist[];
  height?: number;
}

export function OutletActivityTimeline({
  reviews,
  height = 280,
}: OutletActivityTimelineProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);

  const [granularity, setGranularity] = useState<Granularity>("monthly");
  const [visibleBands, setVisibleBands] = useState<Record<BandName, boolean>>({
    generous: true,
    aligned: true,
    critical: true,
  });
  const [selectedJournalist, setSelectedJournalist] = useState<string | "all">("all");
  const [selectedRange, setSelectedRange] = useState<[string, string] | null>(null);
  const [dragStart, setDragStart] = useState<string | null>(null);

  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 640);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  // Extract unique journalists
  const journalists = useMemo(() => {
    const map = new Map<string, string>();
    for (const r of reviews) {
      if (r.journalist_name && !map.has(r.journalist_name)) {
        map.set(r.journalist_name, r.journalist_public_id ?? String(r.journalist_id));
      }
    }
    return [...map.entries()]
      .map(([name, id]) => ({ name, id }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [reviews]);

  // Filter reviews by journalist
  const filteredReviews = useMemo(() => {
    if (selectedJournalist === "all") return reviews;
    return reviews.filter((r) => r.journalist_name === selectedJournalist);
  }, [reviews, selectedJournalist]);

  // Build monthly/quarterly buckets
  const buckets = useMemo(() => {
    const reviewsWithDates = filteredReviews
      .filter((r) => r.published_at != null)
      .map((r) => ({ ...r, pubDate: new Date(r.published_at!) }))
      .sort((a, b) => a.pubDate.getTime() - b.pubDate.getTime());

    if (reviewsWithDates.length === 0) return [];

    const bucketMap = new Map<string, {
      reviews: typeof reviewsWithDates;
      startDate: Date;
      endDate: Date;
    }>();

    for (const r of reviewsWithDates) {
      const key = granularity === "monthly" ? getMonthKey(r.pubDate) : getQuarterKey(r.pubDate);
      if (!bucketMap.has(key)) {
        bucketMap.set(key, { reviews: [], startDate: r.pubDate, endDate: r.pubDate });
      }
      const bucket = bucketMap.get(key)!;
      bucket.reviews.push(r);
      if (r.pubDate < bucket.startDate) bucket.startDate = r.pubDate;
      if (r.pubDate > bucket.endDate) bucket.endDate = r.pubDate;
    }

    const result: MonthBucket[] = [];
    for (const [key, { reviews: bucketReviews, startDate, endDate }] of bucketMap) {
      let generous = 0, aligned = 0, critical = 0;
      const disparities: number[] = [];
      const journalistSet = new Set<string>();

      for (const r of bucketReviews) {
        const band = classifyDisparity(r);
        if (band === "generous") generous++;
        else if (band === "critical") critical++;
        else aligned++;

        const disp = getReviewCombinedDisparity(r);
        if (disp != null) disparities.push(disp);
        if (r.journalist_name) journalistSet.add(r.journalist_name);
      }

      result.push({
        key,
        label: formatMonthLabel(key),
        generous,
        aligned,
        critical,
        total: bucketReviews.length,
        avgDisparity: disparities.length > 0 ? disparities.reduce((a, b) => a + b, 0) / disparities.length : null,
        journalistCount: journalistSet.size,
        startDate,
        endDate,
      });
    }

    return result.sort((a, b) => a.key.localeCompare(b.key));
  }, [filteredReviews, granularity]);

  // Reviews in selected range for the stream
  const streamReviews = useMemo(() => {
    const source = filteredReviews
      .filter((r) => r.published_at != null)
      .sort((a, b) => new Date(b.published_at!).getTime() - new Date(a.published_at!).getTime());

    if (!selectedRange) {
      return source.slice(0, 15);
    }

    const [startKey, endKey] = selectedRange;
    return source.filter((r) => {
      const date = new Date(r.published_at!);
      const key = granularity === "monthly" ? getMonthKey(date) : getQuarterKey(date);
      return key >= startKey && key <= endKey;
    });
  }, [filteredReviews, selectedRange, granularity]);

  // Range selection summary
  const rangeSummary = useMemo(() => {
    if (!selectedRange || streamReviews.length === 0) return null;
    const start = buckets.find((b) => b.key === selectedRange[0]);
    const end = buckets.find((b) => b.key === selectedRange[1]);
    const journalistSet = new Set(streamReviews.map((r) => r.journalist_name));
    const disparities = streamReviews
      .map(getReviewCombinedDisparity)
      .filter((d): d is number => d != null);
    const avgDisp = disparities.length > 0 ? disparities.reduce((a, b) => a + b, 0) / disparities.length : null;
    return {
      label: start && end ? `${start.label} — ${end.label}` : "",
      reviewCount: streamReviews.length,
      journalistCount: journalistSet.size,
      avgDisparity: avgDisp,
    };
  }, [selectedRange, streamReviews, buckets]);

  // Handle chart click for range selection
  const handleChartClick = useCallback(
    (data: { activeLabel?: string | number | undefined }) => {
      if (!data.activeLabel) return;
      const key = String(data.activeLabel);

      if (!dragStart) {
        setDragStart(key);
        setSelectedRange([key, key]);
      } else {
        const range: [string, string] = dragStart <= key ? [dragStart, key] : [key, dragStart];
        setSelectedRange(range);
        setDragStart(null);
      }
    },
    [dragStart]
  );

  const clearSelection = useCallback(() => {
    setSelectedRange(null);
    setDragStart(null);
  }, []);

  const toggleBand = (band: BandName) => {
    setVisibleBands((prev) => ({ ...prev, [band]: !prev[band] }));
  };

  if (buckets.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px]" style={{ color: colors.text }}>
        No review data available
      </div>
    );
  }

  // Build chart data with only visible bands
  const chartData = buckets.map((b) => ({
    name: b.label,
    key: b.key,
    generous: visibleBands.generous ? b.generous : 0,
    aligned: visibleBands.aligned ? b.aligned : 0,
    critical: visibleBands.critical ? b.critical : 0,
    avgDisparity: b.avgDisparity,
    total: b.total,
    journalistCount: b.journalistCount,
  }));

  return (
    <div>
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {/* Band toggles */}
        <div className="flex gap-1">
          <button
            onClick={() => toggleBand("generous")}
            className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg transition-all hover:opacity-80"
            style={{
              backgroundColor: visibleBands.generous ? colors.rust : isDark ? "#3D3A35" : "#f3f4f6",
              color: visibleBands.generous ? "white" : colors.text,
              border: `2px solid ${colors.rust}`,
            }}
          >
            <span
              className="w-3.5 h-3.5 rounded-sm flex items-center justify-center text-xs"
              style={{
                backgroundColor: visibleBands.generous ? "rgba(255,255,255,0.3)" : "transparent",
                border: visibleBands.generous ? "none" : `1.5px solid ${colors.rust}`,
              }}
            >
              {visibleBands.generous && "✓"}
            </span>
            Generous
          </button>
          <button
            onClick={() => toggleBand("aligned")}
            className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg transition-all hover:opacity-80"
            style={{
              backgroundColor: visibleBands.aligned ? colors.tan : isDark ? "#3D3A35" : "#f3f4f6",
              color: visibleBands.aligned ? (isDark ? "#2D2A26" : "#374151") : colors.text,
              border: `2px solid ${colors.tan}`,
            }}
          >
            <span
              className="w-3.5 h-3.5 rounded-sm flex items-center justify-center text-xs"
              style={{
                backgroundColor: visibleBands.aligned ? "rgba(0,0,0,0.15)" : "transparent",
                border: visibleBands.aligned ? "none" : `1.5px solid ${colors.tan}`,
              }}
            >
              {visibleBands.aligned && "✓"}
            </span>
            Aligned
          </button>
          <button
            onClick={() => toggleBand("critical")}
            className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg transition-all hover:opacity-80"
            style={{
              backgroundColor: visibleBands.critical ? colors.sage : isDark ? "#3D3A35" : "#f3f4f6",
              color: visibleBands.critical ? "white" : colors.text,
              border: `2px solid ${colors.sage}`,
            }}
          >
            <span
              className="w-3.5 h-3.5 rounded-sm flex items-center justify-center text-xs"
              style={{
                backgroundColor: visibleBands.critical ? "rgba(255,255,255,0.3)" : "transparent",
                border: visibleBands.critical ? "none" : `1.5px solid ${colors.sage}`,
              }}
            >
              {visibleBands.critical && "✓"}
            </span>
            Critical
          </button>
        </div>

        {/* Granularity toggle */}
        <div className="flex gap-1 text-xs ml-auto">
          <button
            onClick={() => setGranularity("monthly")}
            className={`px-2 py-1 rounded transition-colors ${
              granularity === "monthly"
                ? "bg-gray-700 text-white dark:bg-gray-200 dark:text-gray-900"
                : "bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600"
            }`}
            style={granularity !== "monthly" ? { color: colors.text } : {}}
          >
            Monthly
          </button>
          <button
            onClick={() => setGranularity("quarterly")}
            className={`px-2 py-1 rounded transition-colors ${
              granularity === "quarterly"
                ? "bg-gray-700 text-white dark:bg-gray-200 dark:text-gray-900"
                : "bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600"
            }`}
            style={granularity !== "quarterly" ? { color: colors.text } : {}}
          >
            Quarterly
          </button>
        </div>
      </div>

      {/* Journalist spotlight */}
      {journalists.length > 1 && (
        <div className="mb-4">
          <select
            value={selectedJournalist}
            onChange={(e) => {
              setSelectedJournalist(e.target.value);
              clearSelection();
            }}
            className="text-sm rounded-lg px-3 py-1.5 border"
            style={{
              backgroundColor: colors.background,
              color: colors.text,
              borderColor: colors.border,
            }}
          >
            <option value="all">All Journalists ({journalists.length})</option>
            {journalists.map((j) => (
              <option key={j.id} value={j.name}>
                {j.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Stacked area chart */}
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart
          data={chartData}
          margin={isMobile ? { top: 5, right: 10, left: 5, bottom: 5 } : { top: 10, right: 15, left: 10, bottom: 5 }}
          onClick={handleChartClick}
          style={{ cursor: "pointer" }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
          <XAxis
            dataKey="name"
            tick={{ fontSize: isMobile ? 9 : 11, fill: colors.text }}
            tickLine={{ stroke: colors.axis }}
            axisLine={{ stroke: colors.axis }}
            interval={isMobile ? Math.max(0, Math.floor(chartData.length / 6)) : "preserveStartEnd"}
            angle={isMobile ? -45 : 0}
            textAnchor={isMobile ? "end" : "middle"}
          />
          <YAxis
            tick={{ fontSize: isMobile ? 10 : 12, fill: colors.text }}
            tickLine={{ stroke: colors.axis }}
            axisLine={{ stroke: colors.axis }}
            width={isMobile ? 30 : 40}
            label={
              isMobile
                ? undefined
                : {
                    value: "Reviews",
                    angle: -90,
                    position: "insideLeft",
                    style: { textAnchor: "middle", fill: colors.text, fontSize: 12 },
                  }
            }
          />
          <Tooltip
            contentStyle={{
              backgroundColor: colors.background,
              border: `1px solid ${colors.border}`,
              borderRadius: "8px",
              boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
              color: colors.text,
            }}
            formatter={(value, name) => {
              const label =
                name === "generous"
                  ? "Generous (>+5)"
                  : name === "critical"
                    ? "Critical (<-5)"
                    : name === "aligned"
                      ? "Aligned (±5)"
                      : String(name);
              return [value, label];
            }}
            labelFormatter={(label, payload) => {
              if (payload && payload[0]?.payload) {
                const d = payload[0].payload;
                return `${label} — ${d.total} reviews, ${d.journalistCount} journalist${d.journalistCount !== 1 ? "s" : ""}`;
              }
              return String(label);
            }}
          />

          <Area
            type="monotone"
            dataKey="critical"
            stackId="1"
            fill={colors.sage}
            fillOpacity={0.7}
            stroke={colors.sage}
            strokeWidth={1}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="aligned"
            stackId="1"
            fill={colors.tan}
            fillOpacity={0.7}
            stroke={colors.tan}
            strokeWidth={1}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="generous"
            stackId="1"
            fill={colors.rust}
            fillOpacity={0.7}
            stroke={colors.rust}
            strokeWidth={1}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Click instruction */}
      <p className="mt-2 text-xs text-center" style={{ color: colors.axis }}>
        Click a bar to select a time range. Click a second bar to complete the range.
        {selectedRange && (
          <button
            onClick={clearSelection}
            className="ml-2 underline hover:no-underline"
            style={{ color: colors.rust }}
          >
            Clear selection
          </button>
        )}
      </p>

      {/* Range summary bar */}
      {rangeSummary && (
        <div
          className="mt-3 p-3 rounded-lg flex flex-wrap items-center gap-x-4 gap-y-1 text-sm"
          style={{ backgroundColor: isDark ? "#1F1D1A" : "#f9fafb", border: `1px solid ${colors.border}` }}
        >
          <span className="font-medium" style={{ color: colors.text }}>
            {rangeSummary.label}
          </span>
          <span style={{ color: colors.axis }}>
            {rangeSummary.reviewCount} review{rangeSummary.reviewCount !== 1 ? "s" : ""}
          </span>
          <span style={{ color: colors.axis }}>
            {rangeSummary.journalistCount} journalist{rangeSummary.journalistCount !== 1 ? "s" : ""}
          </span>
          {rangeSummary.avgDisparity != null && (
            <span
              className="font-medium"
              style={{ color: rangeSummary.avgDisparity > 0 ? colors.rust : colors.sage }}
            >
              Avg {rangeSummary.avgDisparity > 0 ? "+" : ""}
              {rangeSummary.avgDisparity.toFixed(1)}
            </span>
          )}
        </div>
      )}

      {/* Review stream */}
      <div className="mt-4">
        <h3 className="text-sm font-medium mb-2" style={{ color: colors.text }}>
          {selectedRange ? "Reviews in Selected Range" : "Recent Reviews"}
          <span className="font-normal ml-1" style={{ color: colors.axis }}>
            ({streamReviews.length})
          </span>
        </h3>

        {streamReviews.length === 0 ? (
          <p className="text-sm py-4 text-center" style={{ color: colors.axis }}>
            No reviews in this range
          </p>
        ) : (
          <div className="space-y-1 max-h-[400px] overflow-y-auto">
            {streamReviews.map((review) => {
              const disp = getReviewCombinedDisparity(review);
              return (
                <div
                  key={review.id}
                  className="flex items-center justify-between gap-3 p-2.5 rounded-lg text-sm transition-colors"
                  style={{
                    backgroundColor: isDark ? "#1F1D1A" : "#f9fafb",
                    border: `1px solid ${colors.border}`,
                  }}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      {review.game_title && review.game_public_id ? (
                        <Link
                          href={buildEntityPath("games", review.game_title, review.game_public_id)}
                          className="font-medium truncate hover:underline"
                          style={{ color: colors.text }}
                        >
                          {review.game_title}
                        </Link>
                      ) : (
                        <span className="font-medium truncate" style={{ color: colors.text }}>
                          {review.game_title ?? "Unknown Game"}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5 text-xs" style={{ color: colors.axis }}>
                      {review.journalist_public_id ? (
                        <Link
                          href={buildEntityPath("journalists", review.journalist_name, review.journalist_public_id)}
                          className="hover:underline"
                        >
                          {review.journalist_name}
                        </Link>
                      ) : (
                        <span>{review.journalist_name}</span>
                      )}
                      <span>
                        {review.published_at
                          ? new Date(review.published_at).toLocaleDateString("en-US", {
                              month: "short",
                              day: "numeric",
                              year: "numeric",
                            })
                          : ""}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <span className="text-sm font-medium" style={{ color: colors.text }}>
                      {review.score_normalized != null ? Number(review.score_normalized).toFixed(0) : "—"}
                    </span>
                    {disp != null && (
                      <span
                        className="text-xs font-medium px-1.5 py-0.5 rounded"
                        style={{
                          color: "white",
                          backgroundColor: disp > 5 ? colors.rust : disp < -5 ? colors.sage : colors.tan,
                        }}
                      >
                        {disp > 0 ? "+" : ""}
                        {disp.toFixed(0)}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
