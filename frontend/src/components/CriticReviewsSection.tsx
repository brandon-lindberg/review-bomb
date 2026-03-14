"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { buildEntityPath } from "@/lib/entity-paths";
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

interface CriticReviewsSectionProps {
  reviews: ReviewWithJournalist[];
}

export function CriticReviewsSection({ reviews }: CriticReviewsSectionProps) {
  const [filter, setFilter] = useState<ReviewFilter>("recent");
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    let result = [...reviews];

    // Filter by timing
    if (filter === "early" || filter === "launch_window" || filter === "late") {
      result = result.filter((r) => r.review_timing === filter);
    }

    // Sort
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

  return (
    <>
      <div className="flex justify-end mb-4">
        <select
          className="pl-4 pr-10 py-2 border border-gray-300 rounded-lg text-sm appearance-none bg-no-repeat"
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
        <p className="text-sm text-gray-500 py-6 text-center">
          No reviews found for this filter.
        </p>
      ) : (
        <>
          <div className="space-y-4">
            {paged.map((review) => (
              <div
                key={review.id}
                className="relative p-4 border border-gray-200 rounded-lg"
              >
                {/* Mobile: full-card tap target for review URL */}
                {review.review_url && (
                  <a
                    href={review.review_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="absolute inset-0 sm:hidden z-0"
                    aria-label={`Read review by ${review.journalist_name}`}
                  />
                )}
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link
                        href={buildEntityPath("journalists", review.journalist_name, review.journalist_public_id ?? review.journalist_id)}
                        className="relative z-10 font-medium text-gray-900 hover:text-blue-600"
                      >
                        {review.journalist_name}
                      </Link>
                      {review.outlet_name && (review.outlet_public_id != null || review.outlet_id != null) && (
                        <>
                          <span className="text-gray-400">at</span>
                          <Link
                            href={buildEntityPath("outlets", review.outlet_name, review.outlet_public_id ?? review.outlet_id!)}
                            className="relative z-10 text-gray-600 hover:text-blue-600"
                          >
                            {review.outlet_name}
                          </Link>
                        </>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      {review.published_at && (
                        <p className="text-sm text-gray-500">
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

                  <div className="flex items-center gap-4 sm:ml-4">
                    <div className="text-right">
                      <p className="text-2xl font-bold text-gray-900">
                        {review.score_normalized != null
                          ? Number(review.score_normalized).toFixed(0)
                          : "—"}
                      </p>
                    </div>
                    {review.review_url && (
                      <a
                        href={review.review_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="relative z-10 hidden sm:inline text-blue-600 hover:text-blue-800"
                      >
                        Read
                      </a>
                    )}
                  </div>
                </div>
                {review.snippet && (
                  <p className="mt-2 text-gray-600 text-sm italic">
                    &ldquo;{review.snippet}&rdquo;
                  </p>
                )}
              </div>
            ))}
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
              <span className="px-4 py-2 text-gray-600">
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
    </>
  );
}
