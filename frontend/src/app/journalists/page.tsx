import type { Metadata } from "next";
import Link from "next/link";
import { getJournalists } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { SortSelect } from "@/components/SortSelect";
import { SearchInput } from "@/components/SearchInput";
import { buildEntityPath } from "@/lib/entity-paths";

export const revalidate = 60;

export async function generateMetadata({ searchParams }: PageProps): Promise<Metadata> {
  const { page: pageParam, sort, order, search } = await searchParams;
  const hasFacetedState = Boolean(pageParam || sort || order || search?.trim());

  return {
    title: "Game Journalists",
    description:
      "Browse game journalists and see how their review scores compare to player opinions. Track critic-to-user score disparity.",
    alternates: { canonical: "/journalists" },
    ...(hasFacetedState && { robots: { index: false, follow: true } }),
    openGraph: {
      title: "Game Journalists - ReviewDisparity",
      description:
        "Browse game journalists and see how their review scores compare to player opinions.",
      url: "/journalists",
    },
  };
}

interface PageProps {
  searchParams: Promise<{
    page?: string;
    sort?: string;
    order?: string;
    search?: string;
  }>;
}

const sortOptions = [
  { value: "latest_review-desc", label: "Most Recent" },
  { value: "review_count-desc", label: "Most Reviews" },
  { value: "review_count-asc", label: "Fewest Reviews" },
  { value: "disparity-desc", label: "Highest Disparity" },
  { value: "disparity-asc", label: "Lowest Disparity" },
  { value: "name-asc", label: "Name (A-Z)" },
  { value: "name-desc", label: "Name (Z-A)" },
];

function formatDate(value: string | null): string {
  if (!value) return "Unknown date";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown date";
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function isUnreleasedNow(gameReleaseDate: string | null): boolean {
  if (!gameReleaseDate) return false;
  const releaseDate = new Date(`${gameReleaseDate}T00:00:00`);
  if (Number.isNaN(releaseDate.getTime())) return false;
  return releaseDate.getTime() > Date.now();
}

function formatSnippet(value: string | null): string | null {
  if (!value) return null;
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > 0 ? normalized : null;
}

export default async function JournalistsPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const page = parseInt(params.page || "1");
  const sortBy = params.sort || "latest_review";
  const sortOrder = params.order || "desc";
  const search = params.search || "";

  let journalists = null;
  try {
    journalists = await getJournalists(page, 20, sortBy, sortOrder, search || undefined);
  } catch (error) {
    console.error("Error fetching journalists:", error);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h1 className="text-3xl font-bold" style={{ color: "var(--foreground)" }}>Journalists</h1>

        <div className="flex gap-2 items-center">
          <SearchInput defaultValue={search} placeholder="Search journalists..." />
          <SortSelect
            options={sortOptions}
            defaultValue={`${sortBy}-${sortOrder}`}
            paramName="sort"
            paramName2="order"
          />
        </div>
      </div>

      {journalists ? (
        <>
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="divide-y divide-gray-200">
              {journalists.items.map((journalist) => {
                const latestReview = journalist.latest_review ?? null;
                const unreleasedNow = isUnreleasedNow(latestReview?.game_release_date ?? null);
                const isPreReleaseReview = (latestReview?.review_timing === "early") || unreleasedNow;
                const latestSnippet = formatSnippet(latestReview?.snippet ?? null);

                return (
                  <Link
                    key={journalist.id}
                    href={buildEntityPath("journalists", journalist.name, journalist.public_id)}
                    className="block p-4 hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-4 min-w-0 flex-1">
                        <div
                          className="w-12 h-12 shrink-0 rounded-full overflow-hidden border flex items-center justify-center"
                          style={{
                            borderColor: "var(--border)",
                            backgroundColor: "rgba(128, 128, 128, 0.18)",
                          }}
                        >
                          {journalist.image_url ? (
                            <img
                              src={journalist.image_url}
                              alt={journalist.name}
                              className="w-full h-full object-cover"
                              loading="lazy"
                            />
                          ) : (
                            <span
                              className="text-lg font-medium leading-none"
                              style={{ color: "var(--foreground-muted)" }}
                            >
                              {journalist.name.charAt(0)}
                            </span>
                          )}
                        </div>
                        <div className="min-w-0">
                          <h2 className="text-lg font-medium text-gray-900">
                            {journalist.name}
                          </h2>
                          <p className="text-sm text-gray-500">
                            {journalist.review_count} reviews
                          </p>
                          {latestReview && (
                            <>
                              <p
                                className="mt-1 text-sm font-medium"
                                style={{ color: "var(--foreground)" }}
                              >
                                Latest: {latestReview.game_title}
                              </p>
                              <div className="mt-1 flex flex-wrap items-center gap-2">
                                {latestReview.outlet_name && (
                                  <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium border bg-gray-100 text-gray-700 border-gray-200 dark:bg-gray-700/60 dark:text-gray-200 dark:border-gray-600">
                                    {latestReview.outlet_name}
                                  </span>
                                )}
                                <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium border bg-gray-100 text-gray-700 border-gray-200 dark:bg-gray-700/60 dark:text-gray-200 dark:border-gray-600">
                                  {formatDate(latestReview.published_at)}
                                </span>
                                {latestReview.score_normalized != null && (
                                  <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium border bg-gray-100 text-gray-700 border-gray-200 dark:bg-gray-700/60 dark:text-gray-200 dark:border-gray-600">
                                    Score {Number(latestReview.score_normalized).toFixed(0)}
                                  </span>
                                )}
                                {isPreReleaseReview && (
                                  <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium border bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-200/20 dark:text-amber-200 dark:border-amber-300/50">
                                    Pre-release Review
                                  </span>
                                )}
                              </div>
                              {latestSnippet && (
                                <p
                                  className="mt-1 text-sm italic"
                                  style={{
                                    color: "var(--foreground-muted)",
                                    display: "-webkit-box",
                                    WebkitLineClamp: 2,
                                    WebkitBoxOrient: "vertical",
                                    overflow: "hidden",
                                  }}
                                >
                                  &ldquo;{latestSnippet}&rdquo;
                                </p>
                              )}
                            </>
                          )}
                        </div>
                      </div>

                      <DisparityBadge disparity={journalist.avg_disparity} />
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>

          {/* Pagination */}
          {journalists.total_pages > 1 && (
            <div className="flex justify-center gap-2">
              {page > 1 && (
                <Link
                  href={`/journalists?page=${page - 1}&sort=${sortBy}&order=${sortOrder}${search ? `&search=${encodeURIComponent(search)}` : ""}`}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Previous
                </Link>
              )}
              <span className="px-4 py-2 text-gray-600">
                Page {page} of {journalists.total_pages}
              </span>
              {page < journalists.total_pages && (
                <Link
                  href={`/journalists?page=${page + 1}&sort=${sortBy}&order=${sortOrder}${search ? `&search=${encodeURIComponent(search)}` : ""}`}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Next
                </Link>
              )}
            </div>
          )}
        </>
      ) : (
        <div className="text-center py-12 bg-white rounded-lg shadow">
          <p className="text-gray-600">
            Unable to load journalists. Make sure the backend API is running.
          </p>
        </div>
      )}
    </div>
  );
}
