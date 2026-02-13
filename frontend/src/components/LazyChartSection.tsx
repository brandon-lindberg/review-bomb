"use client";

import { useState, useEffect, useRef } from "react";
import { getJournalistAllReviews, getOutletAllReviews, getGameAllReviews } from "@/lib/api";
import { ReviewDisparityChart } from "./ReviewDisparityChart";
import { GameDetailTabs } from "./GameDetailTabs";
import { CriticReviewsSection } from "./CriticReviewsSection";
import { JournalistAlignmentSection } from "./JournalistAlignmentSection";
import type { AlignmentJournalist } from "./JournalistAlignmentSection";
import { NewsCard } from "./NewsCard";
import type { ReviewWithDisparity, ReviewWithJournalist, NewsArticle } from "@/types";

type ReviewData = ReviewWithDisparity | ReviewWithJournalist;

interface LazyChartSectionProps {
  entityType: "journalist" | "outlet" | "game";
  entityId: number;
  gameTitle?: string;
  newsArticles?: NewsArticle[];
}

export function LazyChartSection({ entityType, entityId, gameTitle, newsArticles }: LazyChartSectionProps) {
  const [reviews, setReviews] = useState<ReviewData[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const fetchedRef = useRef(false);

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
          <section className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              {entityType === "game" ? "Review Disparities" : "Disparity Over Time"}
            </h2>
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
          </section>

          {/* Game-specific: Tabbed section with critic reviews and journalist alignment */}
          {entityType === "game" && (
            <GameDetailTabs
              criticReviews={
                <CriticReviewsSection reviews={reviews as ReviewWithJournalist[]} />
              }
              journalistAlignment={buildJournalistAlignment(reviews as ReviewWithJournalist[])}
              latestNews={newsArticles && newsArticles.length > 0 ? (
                <div className="divide-y divide-gray-100">
                  {newsArticles.map((article) => (
                    <NewsCard key={article.id} article={article} compact />
                  ))}
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
