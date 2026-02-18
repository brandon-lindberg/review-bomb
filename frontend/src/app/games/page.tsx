import type { Metadata } from "next";
import Link from "next/link";
import { getGames } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { ScoreDisplay } from "@/components/ScoreDisplay";
import { SortSelect } from "@/components/SortSelect";
import { YearFilter } from "@/components/YearFilter";
import { SearchInput } from "@/components/SearchInput";
import { getDisplayDisparity } from "@/lib/disparity-colors";

export const dynamic = "force-dynamic";

export async function generateMetadata({ searchParams }: PageProps): Promise<Metadata> {
  const { page: pageParam } = await searchParams;
  const page = parseInt(pageParam || "1");

  return {
    title: "Browse Games",
    description:
      "Browse video games and compare critic review scores vs player scores from Steam and Metacritic. Find the biggest review disparities.",
    alternates: { canonical: "/games" },
    ...(page > 1 && { robots: { index: false, follow: true } }),
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
    year?: string;
    search?: string;
  }>;
}

const sortOptions = [
  { value: "release_date", label: "Release Date" },
  { value: "disparity", label: "Disparity" },
  { value: "title", label: "Title" },
];

export default async function GamesPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const page = parseInt(params.page || "1");
  const sortBy = params.sort || "release_date";
  const year = params.year ? parseInt(params.year) : undefined;
  const search = params.search || "";

  let games = null;
  try {
    games = await getGames(page, 20, sortBy, "desc", year, search || undefined);
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
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h1 className="text-3xl font-bold" style={{ color: "var(--foreground)" }}>Games</h1>

        <div className="flex flex-wrap gap-2 items-center">
          <SearchInput defaultValue={search} placeholder="Search games..." />
          <YearFilter years={years} defaultValue={year} />
          <SortSelect
            options={sortOptions}
            defaultValue={sortBy}
            paramName="sort"
          />
        </div>
      </div>

      {games ? (
        <>
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="divide-y divide-gray-200">
              {games.items.map((game) => (
                <Link
                  key={game.id}
                  href={`/games/${game.id}`}
                  className="block p-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                    <div className="flex-1">
                      <h2 className="text-lg font-medium text-gray-900">
                        {game.title}
                      </h2>
                      <div className="mt-1 flex items-center gap-4 text-sm text-gray-500">
                        {game.release_date && (
                          <span>
                            {new Date(game.release_date).toLocaleDateString()}
                          </span>
                        )}
                        {game.tier && (
                          <span className="px-2 py-0.5 bg-gray-100 rounded text-xs">
                            {game.tier}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center justify-between sm:justify-end gap-4 sm:gap-6">
                      <ScoreDisplay
                        criticScore={game.avg_critic_score}
                        steamUserScore={game.steam_user_score}
                        metacriticUserScore={game.metacritic_user_score}
                        size="sm"
                      />
                      <DisparityBadge
                        disparity={getDisplayDisparity(game.disparity_steam, game.disparity_metacritic)}
                      />
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </div>

          {/* Pagination */}
          {games.total_pages > 1 && (
            <div className="flex justify-center gap-2">
              {page > 1 && (
                <Link
                  href={`/games?page=${page - 1}${sortBy !== "release_date" ? `&sort=${sortBy}` : ""}${year ? `&year=${year}` : ""}${search ? `&search=${encodeURIComponent(search)}` : ""}`}
                  prefetch={false}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Previous
                </Link>
              )}
              <span className="px-4 py-2 text-gray-600">
                Page {page} of {games.total_pages}
              </span>
              {page < games.total_pages && (
                <Link
                  href={`/games?page=${page + 1}${sortBy !== "release_date" ? `&sort=${sortBy}` : ""}${year ? `&year=${year}` : ""}${search ? `&search=${encodeURIComponent(search)}` : ""}`}
                  prefetch={false}
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
            Unable to load games. Make sure the backend API is running.
          </p>
        </div>
      )}
    </div>
  );
}
