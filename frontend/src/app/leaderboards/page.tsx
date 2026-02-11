import type { Metadata } from "next";
import Link from "next/link";
import {
  getJournalistLeaderboard,
  getOutletLeaderboard,
  getGameLeaderboard,
} from "@/lib/api";
import { DisparityScores } from "@/components/DisparityScores";
import { SortSelect } from "@/components/SortSelect";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Leaderboards",
  description:
    "See which game journalists, outlets, and games have the highest and lowest review disparity. Rankings based on critic vs user score differences.",
  alternates: { canonical: "/leaderboards" },
  openGraph: {
    title: "Leaderboards - ReviewDisparity",
    description:
      "See which game journalists, outlets, and games have the highest and lowest review disparity.",
    url: "/leaderboards",
  },
};

interface PageProps {
  searchParams: Promise<{
    tab?: string;
    sort?: string;
    page?: string;
  }>;
}

export default async function LeaderboardsPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const tab = params.tab || "journalists";
  const sort = (params.sort || "recent") as "recent" | "highest" | "lowest";
  const page = parseInt(params.page || "1");

  let data = null;

  try {
    if (tab === "journalists") {
      data = await getJournalistLeaderboard(page, 20, sort);
    } else if (tab === "outlets") {
      data = await getOutletLeaderboard(page, 20, sort);
    } else if (tab === "games") {
      data = await getGameLeaderboard(page, 20, sort);
    }
  } catch (error) {
    console.error("Error fetching leaderboard:", error);
  }

  const tabs = [
    { id: "journalists", label: "Journalists" },
    { id: "outlets", label: "Outlets" },
    { id: "games", label: "Games" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h1 className="text-3xl font-bold" style={{ color: "var(--foreground)" }}>Leaderboards</h1>

        <div className="flex gap-2">
          <SortSelect
            options={[
              { value: "recent", label: "Most Recent" },
              { value: "highest", label: "Highest Disparity" },
              { value: "lowest", label: "Lowest Disparity" },
            ]}
            defaultValue={sort}
            paramName="sort"
          />
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="border-b" style={{ borderColor: "var(--border)" }}>
        <nav className="flex gap-4">
          {tabs.map((t) => (
            <Link
              key={t.id}
              href={`/leaderboards?tab=${t.id}&sort=${sort}`}
              className="py-3 px-1 border-b-2 font-medium text-sm transition-colors"
              style={tab === t.id
                ? { borderColor: "var(--color-rust)", color: "var(--color-rust)" }
                : { borderColor: "transparent", color: "var(--foreground-muted)" }
              }
            >
              {t.label}
            </Link>
          ))}
        </nav>
      </div>

      {/* Leaderboard Content */}
      {data ? (
        <>
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 w-16">
                    {sort === "recent" ? "#" : "Rank"}
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">
                    {tab === "games" ? "Game" : "Name"}
                  </th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-gray-500 w-24">
                    Reviews
                  </th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-gray-500 whitespace-nowrap">
                    {tab === "games" ? (
                      <div className="flex items-center justify-end gap-2">
                        <span className="min-w-[70px] text-center" style={{ color: "#708160" }}>Steam</span>
                        <span className="min-w-[70px] text-center" style={{ color: "#DD7631" }}>MC</span>
                        <span className="min-w-[70px] text-center" style={{ color: "#5C574F" }}>Combined</span>
                      </div>
                    ) : "Avg Disparity"}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {data.items.map((item, index) => {
                  const rank = (page - 1) * 20 + index + 1;

                  // Extract fields based on leaderboard type
                  let id: number;
                  let linkHref: string;
                  let name: string;
                  let subtitle: string | null = null;
                  let imageUrl: string | null = null;
                  let reviewCount: number;
                  let steamDisparity: number | null = null;
                  let metacriticDisparity: number | null = null;
                  let combinedDisparity: number | null = null;

                  if (tab === "journalists" && "journalist_id" in item) {
                    id = item.journalist_id;
                    linkHref = `/journalists/${id}`;
                    name = item.journalist_name;
                    subtitle = item.outlet_name || null;
                    imageUrl = item.journalist_image_url;
                    reviewCount = item.review_count;
                    steamDisparity = item.avg_disparity_steam ?? null;
                    metacriticDisparity = item.avg_disparity_metacritic ?? null;
                    combinedDisparity = item.avg_disparity_combined ?? item.avg_disparity;
                  } else if (tab === "outlets" && "outlet_id" in item) {
                    id = item.outlet_id;
                    linkHref = `/outlets/${id}`;
                    name = item.outlet_name;
                    imageUrl = item.outlet_logo_url;
                    reviewCount = item.review_count;
                    steamDisparity = item.avg_disparity_steam ?? null;
                    metacriticDisparity = item.avg_disparity_metacritic ?? null;
                    combinedDisparity = item.avg_disparity_combined ?? item.avg_disparity;
                  } else if (tab === "games" && "game_id" in item) {
                    id = item.game_id;
                    linkHref = `/games/${id}`;
                    name = item.game_title;
                    subtitle = item.release_date
                      ? new Date(item.release_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
                      : null;
                    imageUrl = item.game_image_url;
                    reviewCount = item.critic_review_count;
                    steamDisparity = item.disparity_steam ?? null;
                    metacriticDisparity = item.disparity_metacritic ?? null;
                    combinedDisparity = item.disparity;
                  } else {
                    return null;
                  }

                  return (
                    <tr key={id} className="hover:bg-gray-50">
                      <td className="px-4 py-4 text-sm text-gray-500 w-16">
                        {rank}
                      </td>
                      <td className="px-4 py-4">
                        <Link
                          href={linkHref}
                          className="flex items-center gap-3 font-medium hover:opacity-80"
                          style={{ color: "var(--foreground)" }}
                        >
                          {tab !== "games" && (
                            imageUrl ? (
                              <img
                                src={imageUrl}
                                alt={name}
                                className={`flex-shrink-0 ${
                                  tab === "journalists"
                                    ? "w-8 h-8 rounded-full object-cover"
                                    : "w-8 h-8 rounded object-contain bg-gray-100"
                                }`}
                              />
                            ) : (
                              <div
                                className={`flex-shrink-0 flex items-center justify-center bg-gray-200 ${
                                  tab === "journalists"
                                    ? "w-8 h-8 rounded-full"
                                    : "w-8 h-8 rounded"
                                }`}
                              >
                                <span className="text-gray-500 text-xs font-medium">
                                  {name.charAt(0)}
                                </span>
                              </div>
                            )
                          )}
                          <div>
                            <span>{name}</span>
                            {subtitle && (
                              <span className="block text-xs font-normal" style={{ color: "var(--foreground-muted)" }}>
                                {subtitle}
                              </span>
                            )}
                          </div>
                        </Link>
                      </td>
                      <td className="px-4 py-4 text-sm text-gray-500 text-right w-24">
                        {reviewCount}
                      </td>
                      <td className="px-4 py-4 text-right whitespace-nowrap">
                        {tab === "games" ? (
                          <DisparityScores
                            steamDisparity={steamDisparity}
                            metacriticDisparity={metacriticDisparity}
                            combinedDisparity={combinedDisparity}
                            layout="compact"
                            showLabels={false}
                          />
                        ) : (
                          <span
                            className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold ${
                              combinedDisparity !== null && Number(combinedDisparity) > 0
                                ? "bg-red-100 text-red-800"
                                : combinedDisparity !== null && Number(combinedDisparity) < 0
                                ? "bg-blue-100 text-blue-800"
                                : "bg-gray-100 text-gray-800"
                            }`}
                          >
                            {combinedDisparity !== null
                              ? `${Number(combinedDisparity) > 0 ? "+" : ""}${Number(combinedDisparity).toFixed(1)}`
                              : "N/A"}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {data.total_pages > 1 && (
            <div className="flex justify-center gap-2">
              {page > 1 && (
                <Link
                  href={`/leaderboards?tab=${tab}&sort=${sort}&page=${page - 1}`}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Previous
                </Link>
              )}
              <span className="px-4 py-2 text-gray-600">
                Page {page} of {data.total_pages}
              </span>
              {page < data.total_pages && (
                <Link
                  href={`/leaderboards?tab=${tab}&sort=${sort}&page=${page + 1}`}
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
            Unable to load leaderboard. Make sure the backend API is running.
          </p>
        </div>
      )}
    </div>
  );
}
