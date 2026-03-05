"use client";

import { useState, useEffect, useRef } from "react";
import { getJournalistAllReviews, getOutletAllReviews, getGameAllReviews, getGameNews } from "@/lib/api";
import { ReviewDisparityChart } from "./ReviewDisparityChart";
import { ReviewTimingChart } from "./ReviewTimingChart";
import { GameDetailTabs } from "./GameDetailTabs";
import { CriticReviewsSection } from "./CriticReviewsSection";
import { JournalistAlignmentSection } from "./JournalistAlignmentSection";
import type { AlignmentJournalist } from "./JournalistAlignmentSection";
import { NewsCard } from "./NewsCard";
import { ShareButtons } from "./ShareButtons";
import type { ReviewWithDisparity, ReviewWithJournalist, NewsArticle } from "@/types";

type ReviewData = ReviewWithDisparity | ReviewWithJournalist;

interface LazyChartSectionProps {
  entityType: "journalist" | "outlet" | "game";
  entityId: string | number;
  gameTitle?: string;
  newsArticles?: NewsArticle[];
  newsTotalPages?: number;
  timingCounts?: { early: number; launchWindow: number; late: number };
  chartShareUrl?: string;
  chartShareText?: string;
}

export function LazyChartSection({
  entityType,
  entityId,
  gameTitle,
  newsArticles,
  newsTotalPages = 0,
  timingCounts,
  chartShareUrl,
  chartShareText,
}: LazyChartSectionProps) {
  const [reviews, setReviews] = useState<ReviewData[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const fetchedRef = useRef(false);
  const [chartTab, setChartTab] = useState<"disparity" | "timing">("disparity");

  // News pagination state
  const [allNews, setAllNews] = useState<NewsArticle[]>(newsArticles || []);
  const [newsPage, setNewsPage] = useState(1);
  const [newsHasMore, setNewsHasMore] = useState(newsTotalPages > 1);
  const [newsLoading, setNewsLoading] = useState(false);

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
                </nav>
              </div>
            )}

            <div className="p-6">
              {chartShareUrl && chartShareText && (
                <div className="mb-5 flex justify-end">
                  <ShareButtons url={chartShareUrl} text={chartShareText} />
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
                    {...(entityType === "game" && gameTitle ? { gameTitle } : {})}
                  />
                  <p className="mt-4 text-sm text-gray-500 text-center">
                    Each point represents a {entityType === "game" ? "critic " : ""}review. Hover for details.
                    Positive = critic higher than users. Negative = critic lower.
                  </p>
                </>
              )}

              {chartTab === "timing" && effectiveTimingCounts && (
                <ReviewTimingChart
                  early={effectiveTimingCounts.early}
                  launchWindow={effectiveTimingCounts.launchWindow}
                  late={effectiveTimingCounts.late}
                />
              )}
            </div>
          </section>

          {/* Game-specific: Tabbed section with critic reviews and journalist alignment */}
          {entityType === "game" && (
            <GameDetailTabs
              criticReviews={
                <CriticReviewsSection reviews={reviews as ReviewWithJournalist[]} />
              }
              journalistAlignment={buildJournalistAlignment(reviews as ReviewWithJournalist[])}
              latestNews={allNews.length > 0 ? (
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
              ) : null}
            />
          )}
        </>
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
