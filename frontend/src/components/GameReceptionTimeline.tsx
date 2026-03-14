"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import type { ReviewWithJournalist, NewsArticle } from "@/types";
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
  cardBg: isDark ? "#1F1D1A" : "#f9fafb",
});

// ── Event types ──────────────────────────────────────────────

type EventType = "release" | "review" | "milestone" | "news";

interface TimelineEvent {
  id: string;
  type: EventType;
  date: Date;
  dateLabel: string;
  // Review fields
  journalistName?: string;
  journalistPublicId?: string;
  outletName?: string | null;
  score?: number;
  disparity?: number | null;
  reviewTiming?: string;
  // Milestone fields
  milestoneLabel?: string;
  milestoneDetail?: string;
  // News fields
  newsTitle?: string;
  newsUrl?: string;
  newsSource?: string;
}

type FilterType = "all" | "reviews" | "milestones" | "news";

interface GameReceptionTimelineProps {
  reviews: ReviewWithJournalist[];
  releaseDate: string | null;
  steamUserScore: number | null;
  metacriticUserScore: number | null;
  newsArticles?: NewsArticle[];
}

export function GameReceptionTimeline({
  reviews,
  releaseDate,
  steamUserScore,
  metacriticUserScore,
  newsArticles,
}: GameReceptionTimelineProps) {
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);

  const [filter, setFilter] = useState<FilterType>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showCount, setShowCount] = useState(30);

  const steamScore = steamUserScore != null ? Number(steamUserScore) : null;
  const metacriticScore = metacriticUserScore != null ? Number(metacriticUserScore) : null;

  // Build all timeline events
  const allEvents = useMemo(() => {
    const events: TimelineEvent[] = [];

    // 1. Release date event
    if (releaseDate) {
      const rd = new Date(releaseDate + "T00:00:00");
      events.push({
        id: "release",
        type: "release",
        date: rd,
        dateLabel: rd.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" }),
        milestoneLabel: "Game Released",
      });
    }

    // 2. Review events
    const scored = reviews
      .filter((r) => r.published_at != null && r.score_normalized != null)
      .map((r) => ({
        ...r,
        pubDate: new Date(r.published_at!),
        scoreNum: Number(r.score_normalized),
      }))
      .sort((a, b) => a.pubDate.getTime() - b.pubDate.getTime());

    let runningSum = 0;
    for (let i = 0; i < scored.length; i++) {
      const r = scored[i];
      runningSum += r.scoreNum;
      const runningAvg = runningSum / (i + 1);

      // Combined disparity
      const steam = r.disparity_steam != null ? Number(r.disparity_steam) : null;
      const mc = r.disparity_metacritic != null ? Number(r.disparity_metacritic) : null;
      let disp: number | null = null;
      if (steam != null && mc != null) disp = (steam + mc) / 2;
      else disp = steam ?? mc ?? null;

      events.push({
        id: `review-${r.id}`,
        type: "review",
        date: r.pubDate,
        dateLabel: r.pubDate.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
        journalistName: r.journalist_name,
        journalistPublicId: r.journalist_public_id ?? undefined,
        outletName: r.outlet_name,
        score: r.scoreNum,
        disparity: disp,
        reviewTiming: r.review_timing,
      });

      // 3. Milestone events (generated from review stream)
      const count = i + 1;

      // First review
      if (count === 1) {
        events.push({
          id: `milestone-first`,
          type: "milestone",
          date: r.pubDate,
          dateLabel: r.pubDate.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
          milestoneLabel: "First Review Published",
          milestoneDetail: `${r.journalist_name}${r.outlet_name ? ` (${r.outlet_name})` : ""} — ${r.scoreNum.toFixed(0)}/100`,
        });
      }

      // Review count milestones
      if (count === 10 || count === 25 || count === 50 || count === 100) {
        events.push({
          id: `milestone-${count}`,
          type: "milestone",
          date: r.pubDate,
          dateLabel: r.pubDate.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
          milestoneLabel: `${count} Reviews Published`,
          milestoneDetail: `Critic average: ${runningAvg.toFixed(1)}`,
        });
      }
    }

    // Score milestones: highest and lowest scoring reviews
    if (scored.length >= 5) {
      const sorted = [...scored].sort((a, b) => a.scoreNum - b.scoreNum);
      const lowest = sorted[0];
      const highest = sorted[sorted.length - 1];

      // Only add if they're notably different from avg
      const avg = runningSum / scored.length;
      if (highest.scoreNum - avg > 10) {
        events.push({
          id: `milestone-highest`,
          type: "milestone",
          date: highest.pubDate,
          dateLabel: highest.pubDate.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
          milestoneLabel: `Highest Score: ${highest.scoreNum.toFixed(0)}`,
          milestoneDetail: `${highest.journalist_name}${highest.outlet_name ? ` (${highest.outlet_name})` : ""}`,
        });
      }
      if (avg - lowest.scoreNum > 10) {
        events.push({
          id: `milestone-lowest`,
          type: "milestone",
          date: lowest.pubDate,
          dateLabel: lowest.pubDate.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
          milestoneLabel: `Lowest Score: ${lowest.scoreNum.toFixed(0)}`,
          milestoneDetail: `${lowest.journalist_name}${lowest.outlet_name ? ` (${lowest.outlet_name})` : ""}`,
        });
      }
    }

    // 4. News article events
    if (newsArticles) {
      for (const article of newsArticles) {
        if (!article.published_at) continue;
        const d = new Date(article.published_at);
        events.push({
          id: `news-${article.id}`,
          type: "news",
          date: d,
          dateLabel: d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
          newsTitle: article.title,
          newsUrl: article.url,
          newsSource: article.source_name,
        });
      }
    }

    // Sort all events chronologically
    events.sort((a, b) => a.date.getTime() - b.date.getTime());
    return events;
  }, [reviews, releaseDate, newsArticles]);

  // Filter events
  const filteredEvents = useMemo(() => {
    if (filter === "all") return allEvents;
    if (filter === "reviews") return allEvents.filter((e) => e.type === "review");
    if (filter === "milestones") return allEvents.filter((e) => e.type === "milestone" || e.type === "release");
    if (filter === "news") return allEvents.filter((e) => e.type === "news");
    return allEvents;
  }, [allEvents, filter]);

  const visibleEvents = filteredEvents.slice(0, showCount);
  const hasMore = filteredEvents.length > showCount;

  // Count by type for filter badges
  const counts = useMemo(() => ({
    reviews: allEvents.filter((e) => e.type === "review").length,
    milestones: allEvents.filter((e) => e.type === "milestone" || e.type === "release").length,
    news: allEvents.filter((e) => e.type === "news").length,
  }), [allEvents]);

  // Summary stats
  const summary = useMemo(() => {
    const reviewEvents = allEvents.filter((e) => e.type === "review" && e.score != null);
    if (reviewEvents.length === 0) return null;
    const scores = reviewEvents.map((e) => e.score!);
    const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
    const first = allEvents.find((e) => e.type === "review");
    const last = [...allEvents].reverse().find((e) => e.type === "review");
    return {
      reviewCount: reviewEvents.length,
      avgScore: avg,
      firstDate: first?.dateLabel,
      lastDate: last?.dateLabel,
      steamScore,
      metacriticScore,
    };
  }, [allEvents, steamScore, metacriticScore]);

  if (allEvents.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px]" style={{ color: colors.text }}>
        No timeline events available
      </div>
    );
  }

  const getEventColor = (type: EventType) => {
    switch (type) {
      case "release": return colors.tan;
      case "review": return colors.rust;
      case "milestone": return colors.sage;
      case "news": return colors.orange;
    }
  };

  const getTimingBadge = (timing?: string) => {
    if (!timing || timing === "unknown") return null;
    const label = timing === "early" ? "Early" : timing === "launch_window" ? "Launch" : "Late";
    const badgeColor = timing === "early" ? "#3b82f6" : timing === "launch_window" ? "#22c55e" : "#f59e0b";
    return (
      <span
        className="text-[10px] px-1.5 py-0.5 rounded font-medium"
        style={{ backgroundColor: badgeColor, color: "white" }}
      >
        {label}
      </span>
    );
  };

  const getDisparityBadge = (disparity: number | null) => {
    if (disparity == null) return null;
    const color = disparity > 5 ? colors.rust : disparity < -5 ? colors.sage : colors.tan;
    return (
      <span
        className="text-xs font-medium px-1.5 py-0.5 rounded"
        style={{ backgroundColor: color, color: "white" }}
      >
        {disparity > 0 ? "+" : ""}{disparity.toFixed(0)}
      </span>
    );
  };

  return (
    <div>
      {/* Summary bar */}
      {summary && (
        <div
          className="mb-4 p-3 rounded-lg flex flex-wrap items-center gap-x-4 gap-y-1 text-sm"
          style={{ backgroundColor: colors.cardBg, border: `1px solid ${colors.border}` }}
        >
          <span style={{ color: colors.text }}>
            <span className="font-medium">{summary.reviewCount}</span> reviews
          </span>
          <span style={{ color: colors.text }}>
            Avg: <span className="font-medium">{summary.avgScore.toFixed(1)}</span>
          </span>
          {summary.steamScore != null && (
            <span style={{ color: colors.sage }}>
              Steam: <span className="font-medium">{summary.steamScore.toFixed(0)}</span>
            </span>
          )}
          {summary.metacriticScore != null && (
            <span style={{ color: colors.orange }}>
              MC: <span className="font-medium">{summary.metacriticScore.toFixed(0)}</span>
            </span>
          )}
          <span className="text-xs" style={{ color: colors.axis }}>
            {summary.firstDate} — {summary.lastDate}
          </span>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 mb-5">
        {(
          [
            { key: "all" as FilterType, label: "All", count: allEvents.length },
            { key: "reviews" as FilterType, label: "Reviews", count: counts.reviews },
            { key: "milestones" as FilterType, label: "Milestones", count: counts.milestones },
            { key: "news" as FilterType, label: "News", count: counts.news },
          ] as const
        )
          .filter((f) => f.count > 0 || f.key === "all")
          .map((f) => (
            <button
              key={f.key}
              onClick={() => { setFilter(f.key); setShowCount(30); }}
              className="px-3 py-1.5 text-sm rounded-lg transition-all"
              style={{
                backgroundColor: filter === f.key
                  ? (f.key === "reviews" ? colors.rust : f.key === "milestones" ? colors.sage : f.key === "news" ? colors.orange : (isDark ? "#4A4640" : "#d1d5db"))
                  : (isDark ? "#3D3A35" : "#f3f4f6"),
                color: filter === f.key ? "white" : colors.text,
                border: `1px solid ${colors.border}`,
              }}
            >
              {f.label}
              <span className="ml-1.5 text-xs opacity-75">
                {f.count}
              </span>
            </button>
          ))}
      </div>

      {/* Timeline */}
      <div className="relative pl-6 sm:pl-8">
        {/* Vertical line */}
        <div
          className="absolute left-[11px] sm:left-[15px] top-0 bottom-0 w-0.5"
          style={{ backgroundColor: colors.border }}
        />

        <div className="space-y-1">
          {visibleEvents.map((event, idx) => {
            // Show date separator when date changes
            const prevEvent = idx > 0 ? visibleEvents[idx - 1] : null;
            const showDateSep = !prevEvent || event.dateLabel !== prevEvent.dateLabel;
            const isExpanded = expandedId === event.id;
            const eventColor = getEventColor(event.type);

            return (
              <div key={event.id}>
                {/* Date separator */}
                {showDateSep && (
                  <div className="flex items-center gap-2 py-2">
                    {/* Dot on the line */}
                    <div
                      className="absolute left-[8px] sm:left-[12px] w-[7px] h-[7px] rounded-full"
                      style={{ backgroundColor: colors.axis }}
                    />
                    <span
                      className="text-xs font-medium"
                      style={{ color: colors.axis }}
                    >
                      {event.dateLabel}
                    </span>
                  </div>
                )}

                {/* Event card */}
                <div
                  className="relative ml-0 group"
                  onClick={() => setExpandedId(isExpanded ? null : event.id)}
                >
                  {/* Colored dot on the line */}
                  <div
                    className="absolute -left-6 sm:-left-8 top-3 w-3 h-3 rounded-full border-2 z-10"
                    style={{
                      backgroundColor: eventColor,
                      borderColor: colors.background,
                    }}
                  />

                  {/* Card content */}
                  {event.type === "release" ? (
                    <div
                      className="p-3 rounded-lg border-l-4 cursor-default"
                      style={{
                        backgroundColor: colors.cardBg,
                        borderLeftColor: colors.tan,
                        border: `1px solid ${colors.border}`,
                        borderLeft: `4px solid ${colors.tan}`,
                      }}
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-base font-semibold" style={{ color: colors.tan }}>
                          Game Released
                        </span>
                      </div>
                    </div>
                  ) : event.type === "milestone" ? (
                    <div
                      className="p-3 rounded-lg cursor-default"
                      style={{
                        backgroundColor: colors.cardBg,
                        border: `1px solid ${colors.border}`,
                        borderLeft: `4px solid ${colors.sage}`,
                      }}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium" style={{ color: colors.sage }}>
                          {event.milestoneLabel}
                        </span>
                      </div>
                      {event.milestoneDetail && (
                        <p className="text-xs mt-1" style={{ color: colors.axis }}>
                          {event.milestoneDetail}
                        </p>
                      )}
                    </div>
                  ) : event.type === "news" ? (
                    <div
                      className="p-3 rounded-lg cursor-pointer hover:opacity-90 transition-opacity"
                      style={{
                        backgroundColor: colors.cardBg,
                        border: `1px solid ${colors.border}`,
                        borderLeft: `4px solid ${colors.orange}`,
                      }}
                      onClick={(e) => {
                        if (event.newsUrl) {
                          e.stopPropagation();
                          window.open(event.newsUrl, "_blank", "noopener,noreferrer");
                        }
                      }}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate" style={{ color: colors.text }}>
                            {event.newsTitle}
                          </p>
                          {event.newsSource && (
                            <p className="text-xs mt-0.5" style={{ color: colors.orange }}>
                              {event.newsSource}
                            </p>
                          )}
                        </div>
                        <span className="text-xs flex-shrink-0" style={{ color: colors.axis }}>
                          ↗
                        </span>
                      </div>
                    </div>
                  ) : (
                    /* Review event */
                    <div
                      className="p-3 rounded-lg cursor-pointer hover:opacity-90 transition-opacity"
                      style={{
                        backgroundColor: colors.cardBg,
                        border: `1px solid ${colors.border}`,
                        borderLeft: `4px solid ${colors.rust}`,
                      }}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 flex-1 min-w-0">
                          <span className="text-sm font-medium truncate" style={{ color: colors.text }}>
                            {event.journalistName}
                          </span>
                          {event.outletName && (
                            <span className="text-xs truncate hidden sm:inline" style={{ color: colors.axis }}>
                              {event.outletName}
                            </span>
                          )}
                          {getTimingBadge(event.reviewTiming)}
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <span
                            className="text-lg font-bold"
                            style={{ color: colors.rust }}
                          >
                            {event.score?.toFixed(0)}
                          </span>
                          {getDisparityBadge(event.disparity ?? null)}
                        </div>
                      </div>

                      {/* Expanded details */}
                      {isExpanded && (
                        <div className="mt-2 pt-2 border-t space-y-1.5 text-xs" style={{ borderColor: colors.border }}>
                          {event.outletName && (
                            <p style={{ color: colors.axis }}>
                              Published at <span className="font-medium" style={{ color: colors.text }}>{event.outletName}</span>
                            </p>
                          )}
                          {steamScore != null && (
                            <div className="flex justify-between">
                              <span style={{ color: colors.sage }}>Steam User Score</span>
                              <span className="font-medium" style={{ color: colors.sage }}>{steamScore.toFixed(0)}</span>
                            </div>
                          )}
                          {metacriticScore != null && (
                            <div className="flex justify-between">
                              <span style={{ color: colors.orange }}>Metacritic User Score</span>
                              <span className="font-medium" style={{ color: colors.orange }}>{metacriticScore.toFixed(0)}</span>
                            </div>
                          )}
                          {event.disparity != null && (
                            <div className="flex justify-between">
                              <span style={{ color: colors.text }}>Disparity from Users</span>
                              <span
                                className="font-medium"
                                style={{ color: event.disparity > 0 ? colors.rust : colors.sage }}
                              >
                                {event.disparity > 0 ? "+" : ""}{event.disparity.toFixed(1)}
                              </span>
                            </div>
                          )}
                          <div className="pt-1">
                            {event.journalistPublicId ? (
                              <Link
                                href={buildEntityPath("journalists", event.journalistName ?? null, event.journalistPublicId)}
                                className="text-xs underline hover:no-underline"
                                style={{ color: colors.rust }}
                                onClick={(e) => e.stopPropagation()}
                              >
                                View journalist profile →
                              </Link>
                            ) : null}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Load more */}
        {hasMore && (
          <div className="mt-4 text-center">
            <button
              onClick={() => setShowCount((prev) => prev + 30)}
              className="px-4 py-2 text-sm rounded-lg transition-colors"
              style={{
                backgroundColor: colors.cardBg,
                color: colors.text,
                border: `1px solid ${colors.border}`,
              }}
            >
              Show more ({filteredEvents.length - showCount} remaining)
            </button>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="mt-4 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs" style={{ color: colors.axis }}>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colors.tan }}></span>
          Release
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colors.rust }}></span>
          Review
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colors.sage }}></span>
          Milestone
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colors.orange }}></span>
          News
        </span>
        <span className="ml-2">Click a review to expand</span>
      </div>
    </div>
  );
}
