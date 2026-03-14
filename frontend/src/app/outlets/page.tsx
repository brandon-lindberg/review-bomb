import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { getOutlets } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { SortSelect } from "@/components/SortSelect";
import { SearchInput } from "@/components/SearchInput";
import { PaginationControls } from "@/components/PaginationControls";
import { buildEntityPath } from "@/lib/entity-paths";

export const revalidate = 60;

export async function generateMetadata({ searchParams }: PageProps): Promise<Metadata> {
  const { page: pageParam, sort, order, search } = await searchParams;
  const hasFacetedState = Boolean(pageParam || sort || order || search?.trim());

  return {
    title: "Gaming Outlets",
    description:
      "Browse gaming publications and see how their review scores compare to player opinions. Track outlet-level critic-to-user disparity.",
    alternates: { canonical: "/outlets" },
    ...(hasFacetedState && { robots: { index: false, follow: true } }),
    openGraph: {
      title: "Gaming Outlets - ReviewDisparity",
      description:
        "Browse gaming publications and see how their review scores compare to player opinions.",
      url: "/outlets",
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

export default async function OutletsPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const page = parseInt(params.page || "1");
  const sortBy = params.sort || "latest_review";
  const sortOrder = params.order || "desc";
  const search = params.search || "";

  let outlets = null;
  try {
    outlets = await getOutlets(page, 20, sortBy, sortOrder, search || undefined);
  } catch (error) {
    console.error("Error fetching outlets:", error);
  }

  return (
    <div className="space-y-6">
      <section className="space-y-5 py-2 text-center">
        <div className="mx-auto max-w-4xl space-y-4">
          <h1
            className="route-hero-title mx-auto"
          >
            See how publications score against the audience baseline
          </h1>
          <p
            className="mx-auto max-w-4xl text-lg leading-8 sm:text-xl"
            style={{ color: "var(--foreground-muted)" }}
          >
            Track which gaming outlets consistently move with players, which ones diverge, and where
            review volume might be amplifying a pattern instead of representing consensus.
          </p>
        </div>

        <div className="grid w-full gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center md:gap-6">
          <div className="w-full">
            <SearchInput defaultValue={search} placeholder="Search outlets..." />
          </div>
          <SortSelect
            options={sortOptions}
            defaultValue={`${sortBy}-${sortOrder}`}
            paramName="sort"
            paramName2="order"
            className="w-full md:min-w-[18rem]"
          />
        </div>
      </section>

      {outlets ? (
        <>
          <div className="site-list">
            <div className="divide-y divide-gray-200">
              {outlets.items.map((outlet) => {
                const latestReview = outlet.latest_review ?? null;
                const unreleasedNow = isUnreleasedNow(latestReview?.game_release_date ?? null);
                const isPreReleaseReview = (latestReview?.review_timing === "early") || unreleasedNow;
                const latestSnippet = formatSnippet(latestReview?.snippet ?? null);

                return (
                  <Link
                    key={outlet.id}
                    href={buildEntityPath("outlets", outlet.name, outlet.public_id)}
                    className="site-list-item block"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-4 min-w-0 flex-1">
                        {outlet.logo_url ? (
                          <Image
                            src={outlet.logo_url}
                            alt={outlet.name}
                            width={48}
                            height={48}
                            sizes="48px"
                            className="w-12 h-12 shrink-0 rounded object-contain bg-gray-100"
                          />
                        ) : (
                          <div className="w-12 h-12 shrink-0 rounded bg-gray-200 flex items-center justify-center">
                            <span className="text-gray-500 text-lg font-medium">
                              {outlet.name.charAt(0)}
                            </span>
                          </div>
                        )}
                        <div className="min-w-0">
                          <h2 className="text-lg font-medium text-gray-900">
                            {outlet.name}
                          </h2>
                          <p className="text-sm text-gray-500">
                            {outlet.review_count} reviews |{" "}
                            {outlet.journalist_count} journalists
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
                                {latestReview.journalist_name && (
                                  <span className="site-chip">
                                    {latestReview.journalist_name}
                                  </span>
                                )}
                                <span className="site-chip">
                                  {formatDate(latestReview.published_at)}
                                </span>
                                {latestReview.score_normalized != null && (
                                  <span className="site-chip">
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

                      <DisparityBadge disparity={outlet.avg_disparity_combined ?? outlet.avg_disparity} />
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>

          <PaginationControls
            page={page}
            totalPages={outlets.total_pages}
            buildHref={(nextPage) =>
              `/outlets?page=${nextPage}&sort=${sortBy}&order=${sortOrder}${search ? `&search=${encodeURIComponent(search)}` : ""}`
            }
          />
        </>
      ) : (
        <div className="site-empty">
          <p className="text-gray-600">
            Unable to load outlets. Make sure the backend API is running.
          </p>
        </div>
      )}
    </div>
  );
}
