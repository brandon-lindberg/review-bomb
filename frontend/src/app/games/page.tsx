import type { Metadata } from "next";
import Link from "next/link";
import { getGames } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { GameAvatar } from "@/components/GameAvatar";
import { ScoreDisplay } from "@/components/ScoreDisplay";
import { SortSelect } from "@/components/SortSelect";
import { YearFilter } from "@/components/YearFilter";
import { SearchInput } from "@/components/SearchInput";
import { PaginationControls } from "@/components/PaginationControls";
import { getDisplayDisparity } from "@/lib/disparity-colors";
import { buildEntityPath } from "@/lib/entity-paths";

export const revalidate = 60;

export async function generateMetadata({ searchParams }: PageProps): Promise<Metadata> {
  const { page: pageParam, sort, order, year, search } = await searchParams;
  const hasFacetedState = Boolean(pageParam || sort || order || year || search?.trim());

  return {
    title: "Browse Games",
    description:
      "Browse video games and compare critic review scores vs player scores from Steam and Metacritic. Find the biggest review disparities.",
    alternates: { canonical: "/games" },
    ...(hasFacetedState && { robots: { index: false, follow: true } }),
    openGraph: {
      title: "Browse Games - ReviewDisparity",
      description:
        "Browse video games and compare critic review scores vs player scores from Steam and Metacritic.",
      url: "/games",
    },
  };
}

interface PageProps {
  searchParams: Promise<{
    page?: string;
    sort?: string;
    order?: string;
    year?: string;
    search?: string;
  }>;
}

const sortOptions = [
  { value: "release_date-desc", label: "Release Date" },
  { value: "disparity-desc", label: "Highest Disparity" },
  { value: "disparity-asc", label: "Lowest Disparity" },
  { value: "title-asc", label: "Title A - Z" },
  { value: "title-desc", label: "Title Z - A" },
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

export default async function GamesPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const page = parseInt(params.page || "1");
  const sortBy = params.sort || "release_date";
  const sortOrder = params.order || "desc";
  const year = params.year ? parseInt(params.year) : undefined;
  const search = params.search || "";
  const sortSelectValue = `${sortBy}-${sortOrder}`;
  const sortQuery =
    sortBy !== "release_date" || sortOrder !== "desc"
      ? `&sort=${sortBy}&order=${sortOrder}`
      : "";

  let games = null;
  try {
    games = await getGames(page, 20, sortBy, sortOrder, year, search || undefined);
  } catch (error) {
    console.error("Error fetching games:", error);
  }

  const currentYear = new Date().getFullYear();
  const years = Array.from(
    { length: currentYear - 2014 },
    (_, i) => currentYear - i
  );
  return (
    <div className="space-y-6">
      <section className="space-y-5 py-2 text-center">
        <div className="mx-auto max-w-4xl space-y-4">
          <h1
            className="route-hero-title mx-auto"
          >
            Track critic scores against the player curve
          </h1>
          <p
            className="mx-auto max-w-4xl text-lg leading-8 sm:text-xl"
            style={{ color: "var(--foreground-muted)" }}
          >
            Browse release-by-release disagreement between professional reviews and player response,
            then sort by recency, disparity, or title to find where the biggest score gaps live.
          </p>
        </div>

        <div className="grid w-full gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center md:gap-6">
          <div className="w-full">
            <SearchInput defaultValue={search} placeholder="Search games..." />
          </div>
          <div className="flex w-full flex-col gap-3 sm:flex-row md:w-auto md:justify-end">
            <YearFilter years={years} defaultValue={year} className="w-full sm:min-w-[10rem]" />
            <SortSelect
              options={sortOptions}
              defaultValue={sortSelectValue}
              paramName="sort"
              paramName2="order"
              className="w-full sm:min-w-[15rem]"
            />
          </div>
        </div>
      </section>

      {games ? (
        <>
          <div className="site-list">
            <div className="divide-y divide-gray-200">
              {games.items.map((game) => {
                const latestReview = game.latest_review ?? null;
                const unreleasedNow = isUnreleasedNow(latestReview?.game_release_date ?? null);
                const isPreReleaseReview = (latestReview?.review_timing === "early") || unreleasedNow;
                const latestSnippet = formatSnippet(latestReview?.snippet ?? null);
                const combinedDisparity = getDisplayDisparity(game.disparity_steam, game.disparity_metacritic);

                return (
                  <Link
                    key={game.id}
                    href={buildEntityPath("games", game.title, game.public_id)}
                    className="site-list-item block"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
                      <div className="flex min-w-0 flex-1 items-center gap-4">
                        <GameAvatar
                          title={game.title}
                          imageUrl={game.image_url}
                          width={96}
                          height={54}
                          sizes="96px"
                          className="h-[54px] w-24 shrink-0 rounded-xl object-contain"
                        />
                        <div className="min-w-0 flex-1">
                          <h2 className="text-lg font-semibold text-gray-900">
                            {game.title}
                          </h2>
                          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-gray-500">
                            {game.release_date && (
                              <span className="site-chip">
                                Release Date: {formatDate(game.release_date)}
                              </span>
                            )}
                            {game.tier && (
                              <span className="site-chip site-chip--accent">
                                {game.tier}
                              </span>
                            )}
                          </div>
                          {latestReview && (
                            <>
                              <p
                                className="mt-2 text-sm font-medium"
                                style={{ color: "var(--foreground)" }}
                              >
                                Latest review: {latestReview.journalist_name}
                                {latestReview.outlet_name ? ` at ${latestReview.outlet_name}` : ""}
                              </p>
                              <p
                                className="mt-1 text-sm"
                                style={{ color: "var(--foreground-muted)" }}
                              >
                                {formatDate(latestReview.published_at)}
                                {latestReview.score_normalized != null ? ` | Score ${Number(latestReview.score_normalized).toFixed(0)}` : ""}
                                {isPreReleaseReview ? " | Pre-release Review" : ""}
                              </p>
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

                      <div className="flex flex-col items-start gap-5 shrink-0 sm:items-end sm:gap-6">
                        <DisparityBadge
                          disparity={combinedDisparity}
                          size="lg"
                        />
                        <ScoreDisplay
                          criticScore={game.avg_critic_score}
                          steamUserScore={game.steam_user_score}
                          metacriticUserScore={game.metacritic_user_score}
                          criticDisparity={combinedDisparity}
                          steamDisparity={game.disparity_steam}
                          metacriticDisparity={game.disparity_metacritic}
                          size="xl"
                          alwaysShowAll
                          useDisparityPalette
                        />
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>

          <PaginationControls
            page={page}
            totalPages={games.total_pages}
            buildHref={(nextPage) =>
              `/games?page=${nextPage}${sortQuery}${year ? `&year=${year}` : ""}${search ? `&search=${encodeURIComponent(search)}` : ""}`
            }
          />
        </>
      ) : (
        <div className="site-empty">
          <p className="text-gray-600">
            Unable to load games. Make sure the backend API is running.
          </p>
        </div>
      )}
    </div>
  );
}
