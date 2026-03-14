"use client";

import dynamic from "next/dynamic";
import { useState, useEffect, useMemo, useRef } from "react";
import { getJournalistAllReviews, getOutletAllReviews, getGameAllReviews, getGameNews } from "@/lib/api";
import type { AlignmentJournalist } from "./JournalistAlignmentSection";
import { ShareButtons } from "./ShareButtons";
import type { ReviewWithDisparity, ReviewWithJournalist, NewsArticle } from "@/types";
import { withTrendSnapshot } from "@/lib/share-url";

type ReviewData = ReviewWithDisparity | ReviewWithJournalist;

function ChartModuleFallback() {
  return (
    <div
      className="flex h-[300px] items-center justify-center rounded-[1.25rem]"
      style={{ backgroundColor: "color-mix(in srgb, var(--background-card) 92%, var(--background) 8%)" }}
    >
      <div className="text-center">
        <div
          className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-b-2"
          style={{ borderColor: "var(--color-rust)" }}
        />
        <p style={{ color: "var(--foreground-muted)" }}>Preparing chart module...</p>
      </div>
    </div>
  );
}

function PanelModuleFallback({ label }: { label: string }) {
  return (
    <section className="bg-white rounded-lg shadow p-4 sm:p-6">
      <div className="text-sm" style={{ color: "var(--foreground-muted)" }}>
        Loading {label}...
      </div>
    </section>
  );
}

const ReviewDisparityChart = dynamic(
  () => import("./ReviewDisparityChart").then((mod) => mod.ReviewDisparityChart),
  {
    ssr: false,
    loading: () => <ChartModuleFallback />,
  }
);

const ReviewTimingChart = dynamic(
  () => import("./ReviewTimingChart").then((mod) => mod.ReviewTimingChart),
  {
    ssr: false,
    loading: () => <ChartModuleFallback />,
  }
);

const GameReceptionTimeline = dynamic(
  () => import("./GameReceptionTimeline").then((mod) => mod.GameReceptionTimeline),
  {
    ssr: false,
    loading: () => <PanelModuleFallback label="reception story" />,
  }
);

const JournalistScoringHeatmap = dynamic(
  () => import("./JournalistScoringHeatmap").then((mod) => mod.JournalistScoringHeatmap),
  {
    ssr: false,
    loading: () => <PanelModuleFallback label="scoring pattern" />,
  }
);

const OutletActivityTimeline = dynamic(
  () => import("./OutletActivityTimeline").then((mod) => mod.OutletActivityTimeline),
  {
    ssr: false,
    loading: () => <PanelModuleFallback label="activity stream" />,
  }
);

const GameDetailTabs = dynamic(
  () => import("./GameDetailTabs").then((mod) => mod.GameDetailTabs),
  {
    ssr: false,
    loading: () => <PanelModuleFallback label="detail tabs" />,
  }
);

const CriticReviewsSection = dynamic(
  () => import("./CriticReviewsSection").then((mod) => mod.CriticReviewsSection),
  {
    ssr: false,
    loading: () => <PanelModuleFallback label="critic reviews" />,
  }
);

const JournalistAlignmentSection = dynamic(
  () => import("./JournalistAlignmentSection").then((mod) => mod.JournalistAlignmentSection),
  {
    ssr: false,
    loading: () => <PanelModuleFallback label="alignment view" />,
  }
);

const NewsCard = dynamic(
  () => import("./NewsCard").then((mod) => mod.NewsCard),
  {
    ssr: false,
  }
);

interface LazyChartSectionProps {
  entityType: "journalist" | "outlet" | "game";
  entityId: string | number;
  gameTitle?: string;
  newsArticles?: NewsArticle[];
  newsTotalPages?: number;
  timingCounts?: { early: number; launchWindow: number; late: number };
  disparityChartShareUrl?: string;
  disparityChartShareText?: string;
  timingChartShareUrl?: string;
  timingChartShareText?: string;
  // Game-specific props for Reception Story timeline
  releaseDate?: string | null;
  steamUserScore?: number | null;
  metacriticUserScore?: number | null;
}

export function LazyChartSection({
  entityType,
  entityId,
  gameTitle,
  newsArticles,
  newsTotalPages = 0,
  timingCounts,
  disparityChartShareUrl,
  disparityChartShareText,
  timingChartShareUrl,
  timingChartShareText,
  releaseDate,
  steamUserScore,
  metacriticUserScore,
}: LazyChartSectionProps) {
  const [reviews, setReviews] = useState<ReviewData[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const fetchedRef = useRef(false);
  const [chartTab, setChartTab] = useState<"disparity" | "timing" | "timeline">("disparity");

  // News pagination state
  const [allNews, setAllNews] = useState<NewsArticle[]>(newsArticles || []);
  const [newsPage, setNewsPage] = useState(1);
  const [newsHasMore, setNewsHasMore] = useState(newsTotalPages > 1);
  const [newsLoading, setNewsLoading] = useState(false);
  // All news for timeline (fetched once when timeline tab is opened)
  const [timelineNews, setTimelineNews] = useState<NewsArticle[] | null>(null);
  const timelineNewsFetchedRef = useRef(false);
  const [trendShareState, setTrendShareState] = useState<{
    trend: string;
    window: string;
    windowLabel: string;
    series: "steam" | "metacritic" | "combined";
    seriesLabel: string;
  } | null>(null);

  // Intersection Observer: trigger fetch when section scrolls into view
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !fetchedRef.current) {
          fetchedRef.current = true;
          observer.disconnect();
          setLoading(true);
        }
      },
      { rootMargin: "200px" } // Start loading 200px before visible
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, []);

  // Fetch data once loading is triggered
  useEffect(() => {
    if (!loading || reviews !== null || error) return;

    const fetchData = async () => {
      try {
        let data: ReviewData[];
        if (entityType === "journalist") {
          data = await getJournalistAllReviews(entityId);
        } else if (entityType === "outlet") {
          data = await getOutletAllReviews(entityId);
        } else {
          data = await getGameAllReviews(entityId);
        }
        setReviews(data);
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [loading, reviews, error, entityId, entityType]);

  // Fetch ALL news pages when timeline tab is first opened (for the full timeline)
  useEffect(() => {
    if (chartTab !== "timeline" || entityType !== "game" || timelineNewsFetchedRef.current) return;
    if (!newsArticles || newsTotalPages <= 1) {
      // Already have all news from the initial page (or no news at all)
      setTimelineNews(newsArticles || []);
      timelineNewsFetchedRef.current = true;
      return;
    }

    const fetchAllNews = async () => {
      try {
        // We already have page 1 from newsArticles, fetch remaining pages
        const remaining = Array.from({ length: newsTotalPages - 1 }, (_, i) => i + 2);
        const results = await Promise.allSettled(
          remaining.map((page) => getGameNews(entityId, page, 5))
        );
        const successfulItems = results
          .filter((r): r is PromiseFulfilledResult<Awaited<ReturnType<typeof getGameNews>>> => r.status === "fulfilled")
          .flatMap((r) => r.value.items);
        const allItems = [...newsArticles, ...successfulItems];
        setTimelineNews(allItems);
        timelineNewsFetchedRef.current = true;
      } catch {
        // Fall back to whatever we have — don't set ref so retry is possible
        setTimelineNews(newsArticles || []);
      }
    };
    fetchAllNews();
  }, [chartTab, entityType, entityId, newsArticles, newsTotalPages]);

  const loadMoreNews = async () => {
    if (newsLoading || !newsHasMore) return;
    setNewsLoading(true);
    try {
      const nextPage = newsPage + 1;
      const response = await getGameNews(entityId, nextPage, 5);
      setAllNews((prev) => [...prev, ...response.items]);
      setNewsPage(nextPage);
      setNewsHasMore(nextPage < response.total_pages);
    } catch {
      // Silently fail — existing articles remain visible
    } finally {
      setNewsLoading(false);
    }
  };

  const computedTimingCounts = reviews
    ? reviews.reduce(
        (acc, review) => {
          if (review.review_timing === "early") acc.early += 1;
          else if (review.review_timing === "launch_window") acc.launchWindow += 1;
          else if (review.review_timing === "late") acc.late += 1;
          return acc;
        },
        { early: 0, launchWindow: 0, late: 0 }
      )
    : undefined;

  const effectiveTimingCounts = timingCounts ?? computedTimingCounts;
  const hasTimingShare = Boolean(
    timingChartShareUrl
    && timingChartShareText
    && effectiveTimingCounts
  );
  const effectiveDisparityChartShareUrl = useMemo(() => {
    if (!disparityChartShareUrl || !trendShareState) return disparityChartShareUrl;
    return withTrendSnapshot(disparityChartShareUrl, {
      trend: trendShareState.trend,
      window: trendShareState.window,
      series: trendShareState.series,
    });
  }, [disparityChartShareUrl, trendShareState]);
  const effectiveDisparityChartShareText = useMemo(() => {
    if (!disparityChartShareText || !trendShareState) return disparityChartShareText;

    const details = [`Window: ${trendShareState.windowLabel}`];
    if (trendShareState.series !== "combined") {
      details.unshift(`Series: ${trendShareState.seriesLabel}`);
    }

    return `${disparityChartShareText} — ${details.join(" — ")}`;
  }, [disparityChartShareText, trendShareState]);
  const isTimingTabActive = chartTab === "timing" && hasTimingShare;
  const activeShareUrl = isTimingTabActive
    ? timingChartShareUrl
    : effectiveDisparityChartShareUrl ?? timingChartShareUrl;
  const activeShareText = isTimingTabActive
    ? timingChartShareText
    : effectiveDisparityChartShareText ?? timingChartShareText;
  const gameReviews = (reviews ?? []) as ReviewWithJournalist[];
  const latestNewsContent = allNews.length > 0 ? (
    <div>
      <div className="divide-y divide-gray-100">
        {allNews.map((article) => (
          <NewsCard key={article.id} article={article} compact />
        ))}
      </div>
      {newsHasMore && (
        <div className="mt-4 text-center">
          <button
            onClick={loadMoreNews}
            disabled={newsLoading}
            className="px-4 py-2 text-sm font-medium rounded-lg transition-colors cursor-pointer disabled:opacity-50"
            style={{
              backgroundColor: "var(--color-rust)",
              color: "white",
            }}
          >
            {newsLoading ? "Loading..." : "Load More Articles"}
          </button>
        </div>
      )}
    </div>
  ) : null;

  return (
    <div ref={sentinelRef} className="space-y-8">
      {/* Loading state */}
      {loading && !reviews && !error && (
        <section className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-center h-[300px]">
            <div className="text-center">
              <div
                className="animate-spin rounded-full h-8 w-8 border-b-2 mx-auto mb-3"
                style={{ borderColor: "var(--color-rust)" }}
              />
              <p style={{ color: "var(--foreground-muted)" }}>Loading chart data...</p>
            </div>
          </div>
        </section>
      )}

      {/* Error state */}
      {error && (
        <section className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-center h-[200px]">
            <p style={{ color: "var(--foreground-muted)" }}>Failed to load chart data.</p>
          </div>
        </section>
      )}

      {/* Chart */}
      {reviews && reviews.length > 0 && (
        <>
          <section className="bg-white rounded-lg shadow">
            {/* Tab bar for disparity and review timing */}
            {effectiveTimingCounts && (
              <div className="border-b" style={{ borderColor: "var(--border)" }}>
                <nav className="flex gap-2 sm:gap-4 px-4 sm:px-6 overflow-x-auto">
                  <button
                    onClick={() => setChartTab("disparity")}
                    className="py-3 px-1 border-b-2 font-medium text-sm transition-colors cursor-pointer whitespace-nowrap"
                    style={chartTab === "disparity"
                      ? { borderColor: "var(--color-rust)", color: "var(--color-rust)" }
                      : { borderColor: "transparent", color: "var(--foreground-muted)" }
                    }
                  >
                    Disparity Trend
                  </button>
                  <button
                    onClick={() => setChartTab("timing")}
                    className="py-3 px-1 border-b-2 font-medium text-sm transition-colors cursor-pointer whitespace-nowrap"
                    style={chartTab === "timing"
                      ? { borderColor: "var(--color-rust)", color: "var(--color-rust)" }
                      : { borderColor: "transparent", color: "var(--foreground-muted)" }
                    }
                  >
                    Review Timing
                  </button>
                  <button
                    onClick={() => setChartTab("timeline")}
                    className="py-3 px-1 border-b-2 font-medium text-sm transition-colors cursor-pointer whitespace-nowrap"
                    style={chartTab === "timeline"
                      ? { borderColor: "var(--color-rust)", color: "var(--color-rust)" }
                      : { borderColor: "transparent", color: "var(--foreground-muted)" }
                    }
                  >
                    {entityType === "game" ? "Reception Story" : entityType === "journalist" ? "Scoring Pattern" : "Activity Stream"}
                  </button>
                </nav>
              </div>
            )}

            <div className="p-4 sm:p-6">
              {activeShareUrl && activeShareText && (
                <div className="mb-4 flex justify-start sm:justify-end">
                  <div className="max-w-full overflow-x-auto">
                    <ShareButtons url={activeShareUrl} text={activeShareText} compactOnMobile />
                  </div>
                </div>
              )}

              {(!effectiveTimingCounts || chartTab === "disparity") && (
                <>
                  {entityType === "game" && (
                    <h2 className="text-xl font-semibold text-gray-900 mb-4">Review Disparities</h2>
                  )}
                  <ReviewDisparityChart
                    reviews={reviews}
                    context={entityType}
                    height={300}
                    onTrendShareStateChange={setTrendShareState}
                    {...(entityType === "game" && gameTitle ? { gameTitle } : {})}
                  />
                </>
              )}

              {chartTab === "timing" && effectiveTimingCounts && (
                <ReviewTimingChart
                  early={effectiveTimingCounts.early}
                  launchWindow={effectiveTimingCounts.launchWindow}
                  late={effectiveTimingCounts.late}
                />
              )}

              {chartTab === "timeline" && entityType === "game" && (
                <GameReceptionTimeline
                  reviews={reviews as ReviewWithJournalist[]}
                  releaseDate={releaseDate ?? null}
                  steamUserScore={steamUserScore ?? null}
                  metacriticUserScore={metacriticUserScore ?? null}
                  newsArticles={timelineNews ?? allNews}
                />
              )}

              {chartTab === "timeline" && entityType === "journalist" && (
                <JournalistScoringHeatmap
                  reviews={reviews as ReviewWithDisparity[]}
                />
              )}

              {chartTab === "timeline" && entityType === "outlet" && (
                <OutletActivityTimeline
                  reviews={reviews as ReviewWithJournalist[]}
                />
              )}
            </div>
          </section>

        </>
      )}

      {/* Game-specific: Tabbed section with critic reviews, alignment, and news */}
      {entityType === "game" && reviews && (
        <GameDetailTabs
          criticReviews={<CriticReviewsSection reviews={gameReviews} />}
          journalistAlignment={buildJournalistAlignment(gameReviews)}
          latestNews={latestNewsContent}
          defaultTab={gameReviews.length === 0 && latestNewsContent ? "news" : "reviews"}
        />
      )}
    </div>
  );
}

/** Build journalist alignment data from reviews (game page only) */
function buildJournalistAlignment(reviews: ReviewWithJournalist[]) {
  const journalistMap = new Map<number, AlignmentJournalist>();

  for (const review of reviews) {
    if (review.score_normalized == null) continue;
    if (journalistMap.has(review.journalist_id)) continue;

    const steam = review.disparity_steam != null ? Number(review.disparity_steam) : null;
    const mc = review.disparity_metacritic != null ? Number(review.disparity_metacritic) : null;
    let combined: number | null = null;
    if (steam != null && mc != null) {
      combined = (steam + mc) / 2;
    } else {
      combined = steam ?? mc ?? null;
    }

    journalistMap.set(review.journalist_id, {
      id: review.journalist_id,
      publicId: review.journalist_public_id ?? String(review.journalist_id),
      name: review.journalist_name,
      imageUrl: review.journalist_image_url,
      outletName: review.outlet_name,
      score: Number(review.score_normalized),
      disparitySteam: steam,
      disparityMetacritic: mc,
      disparityCombined: combined,
    });
  }

  const journalists = Array.from(journalistMap.values()).filter(
    (j) => j.disparityCombined !== null || j.disparitySteam !== null || j.disparityMetacritic !== null
  );

  if (journalists.length < 2) return null;

  return <JournalistAlignmentSection journalists={journalists} />;
}
