"use client";

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { getOutletAllReviews } from "@/lib/api";
import { buildEntityPath } from "@/lib/entity-paths";
import { ReviewScoreCards } from "./ReviewScoreTable";
import type { ReviewWithJournalist } from "@/types";

type ReviewFilter = "recent" | "oldest" | "early" | "launch_window" | "late";

const FILTER_OPTIONS: { value: ReviewFilter; label: string }[] = [
  { value: "recent", label: "Most Recent" },
  { value: "oldest", label: "Oldest First" },
  { value: "early", label: "Early Reviews" },
  { value: "launch_window", label: "Launch Window" },
  { value: "late", label: "Late Reviews" },
];

const PER_PAGE = 20;

interface OutletReviewsSectionProps {
  outletId: string | number;
}

export function OutletReviewsSection({ outletId }: OutletReviewsSectionProps) {
  const [reviews, setReviews] = useState<ReviewWithJournalist[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<ReviewFilter>("recent");
  const [page, setPage] = useState(1);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getOutletAllReviews(outletId)
      .then((data) => {
        if (!cancelled) setReviews(data);
      })
      .catch(() => {
        if (!cancelled) setReviews([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [outletId]);

  const filtered = useMemo(() => {
    if (!reviews) return [];
    let result = [...reviews];

    if (filter === "early" || filter === "launch_window" || filter === "late") {
      result = result.filter((r) => r.review_timing === filter);
    }

    result.sort((a, b) => {
      const dateA = a.published_at ? new Date(a.published_at).getTime() : 0;
      const dateB = b.published_at ? new Date(b.published_at).getTime() : 0;
      return filter === "oldest" ? dateA - dateB : dateB - dateA;
    });

    return result;
  }, [reviews, filter]);

  const totalPages = Math.ceil(filtered.length / PER_PAGE);
  const paged = filtered.slice((page - 1) * PER_PAGE, page * PER_PAGE);

  const handleFilterChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setFilter(e.target.value as ReviewFilter);
    setPage(1);
  };

  if (loading) {
    return (
      <section className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>Reviews</h2>
        <div className="flex items-center justify-center h-[200px]">
          <div className="text-center">
            <div
              className="animate-spin rounded-full h-8 w-8 border-b-2 mx-auto mb-3"
              style={{ borderColor: "var(--color-rust)" }}
            />
            <p style={{ color: "var(--foreground-muted)" }}>Loading reviews...</p>
          </div>
        </div>
      </section>
    );
  }

  if (!reviews || reviews.length === 0) return null;

  return (
    <section className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>Reviews</h2>
        <select
          className="site-field site-select py-2 border border-gray-300 rounded-lg text-sm appearance-none bg-no-repeat"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%235C574F' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`,
            backgroundPosition: "right 0.75rem center",
            backgroundSize: "1rem",
          }}
          value={filter}
          onChange={handleFilterChange}
        >
          {FILTER_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {paged.length === 0 ? (
        <p className="text-sm py-6 text-center" style={{ color: "var(--foreground-muted)" }}>
          No reviews found for this filter.
        </p>
      ) : (
        <>
          <div className="space-y-4">
            {paged.map((review) => {
              // Outlet review payloads include disparities but not raw user scores.
              const steamScore =
                review.score_normalized != null && review.disparity_steam != null
                  ? Number(review.score_normalized) - Number(review.disparity_steam)
                  : null;
              const metacriticScore =
                review.score_normalized != null && review.disparity_metacritic != null
                  ? Number(review.score_normalized) - Number(review.disparity_metacritic)
                  : null;

              return (
                <div
                  key={review.id}
                  className="relative p-4 border rounded-lg"
                  style={{ borderColor: "var(--border)" }}
                >
                  {review.review_url && (
                    <a
                      href={review.review_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="absolute inset-0 sm:hidden z-0"
                      aria-label={`Read review of ${review.game_title || "game"}`}
                    />
                  )}
                  <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Link
                          href={buildEntityPath("games", review.game_title, review.game_public_id ?? review.game_id)}
                          className="relative z-10 font-medium hover:opacity-80"
                          style={{ color: "var(--foreground)" }}
                        >
                          {review.game_title || "Unknown Game"}
                        </Link>
                        {review.journalist_id && review.journalist_name && (
                          <>
                            <span style={{ color: "var(--foreground-muted)" }}>by</span>
                            <Link
                              href={buildEntityPath("journalists", review.journalist_name, review.journalist_public_id ?? review.journalist_id)}
                              className="relative z-10 hover:opacity-80"
                              style={{ color: "var(--foreground-muted)" }}
                            >
                              {review.journalist_name}
                            </Link>
                          </>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-1 flex-wrap">
                        {review.published_at && (
                          <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
                            {new Date(review.published_at).toLocaleDateString()}
                          </p>
                        )}
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium cursor-help ${
                            review.review_timing === "early"
                              ? "bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300"
                              : review.review_timing === "launch_window"
                              ? "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300"
                              : review.review_timing === "late"
                              ? "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
                              : "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"
                          }`}
                          title={review.game_release_date
                            ? `Game released: ${new Date(review.game_release_date).toLocaleDateString()}${
                                review.review_timing === "early" ? " (before release)" :
                                review.review_timing === "launch_window" ? " (within 60 days)" :
                                review.review_timing === "late" ? " (more than 60 days ago)" : ""
                              }`
                            : "Release date unknown"}
                        >
                          {review.review_timing === "early" ? "Early Review" :
                           review.review_timing === "launch_window" ? "Launch Window" :
                           review.review_timing === "late" ? "Late Review" : "Release Date Unknown"}
                        </span>
                      </div>
                    </div>
                    {review.review_url && (
                      <a
                        href={review.review_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="relative z-10 hidden sm:inline-block text-sm px-3 py-1 rounded hover:opacity-80"
                        style={{ backgroundColor: "var(--color-rust)", color: "white" }}
                      >
                        Read Review
                      </a>
                    )}
                  </div>

                  {review.snippet && (
                    <p className="mb-3 text-sm italic" style={{ color: "var(--foreground-muted)" }}>
                      &ldquo;{review.snippet}&rdquo;
                    </p>
                  )}

                  <ReviewScoreCards
                    criticScore={review.score_normalized}
                    steamScore={steamScore}
                    steamDisparity={review.disparity_steam}
                    metacriticScore={metacriticScore}
                    metacriticDisparity={review.disparity_metacritic}
                    combinedDisparity={
                      review.disparity_steam != null && review.disparity_metacritic != null
                        ? (Number(review.disparity_steam) + Number(review.disparity_metacritic)) / 2
                        : review.disparity_steam ?? review.disparity_metacritic
                    }
                  />
                </div>
              );
            })}
          </div>

          {totalPages > 1 && (
            <div className="mt-6 flex justify-center gap-2">
              {page > 1 && (
                <button
                  onClick={() => setPage(page - 1)}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 cursor-pointer"
                >
                  Previous
                </button>
              )}
              <span className="px-4 py-2" style={{ color: "var(--foreground-muted)" }}>
                Page {page} of {totalPages}
              </span>
              {page < totalPages && (
                <button
                  onClick={() => setPage(page + 1)}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 cursor-pointer"
                >
                  Next
                </button>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
