import Link from "next/link";
import {
  getJournalistLeaderboard,
  getOutletLeaderboard,
  getGameLeaderboard,
} from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { SortSelect } from "@/components/SortSelect";

export const dynamic = "force-dynamic";

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
  const sort = (params.sort || "highest") as "highest" | "lowest";
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
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">
                    Rank
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">
                    {tab === "games" ? "Game" : "Name"}
                  </th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">
                    Reviews
                  </th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">
                    Avg Score
                  </th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">
                    Disparity
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
                  let reviewCount: number;
                  let avgScore: number | null = null;
                  let disparity: number | null = null;

                  if (tab === "journalists" && "journalist_id" in item) {
                    id = item.journalist_id;
                    linkHref = `/journalists/${id}`;
                    name = item.journalist_name;
                    reviewCount = item.review_count;
                    disparity = item.avg_disparity;
                  } else if (tab === "outlets" && "outlet_id" in item) {
                    id = item.outlet_id;
                    linkHref = `/outlets/${id}`;
                    name = item.outlet_name;
                    reviewCount = item.review_count;
                    disparity = item.avg_disparity;
                  } else if (tab === "games" && "game_id" in item) {
                    id = item.game_id;
                    linkHref = `/games/${id}`;
                    name = item.game_title;
                    reviewCount = item.critic_review_count;
                    avgScore = item.avg_critic_score;
                    disparity = item.disparity;
                  } else {
                    return null;
                  }

                  return (
                    <tr key={id} className="hover:bg-gray-50">
                      <td className="px-4 py-4 text-sm text-gray-500">
                        {rank}
                      </td>
                      <td className="px-4 py-4">
                        <Link
                          href={linkHref}
                          className="font-medium hover:opacity-80"
                          style={{ color: "var(--foreground)" }}
                        >
                          {name}
                        </Link>
                      </td>
                      <td className="px-4 py-4 text-sm text-gray-500 text-right">
                        {reviewCount}
                      </td>
                      <td className="px-4 py-4 text-sm text-gray-500 text-right">
                        {avgScore != null ? Number(avgScore).toFixed(1) : "—"}
                      </td>
                      <td className="px-4 py-4 text-right">
                        <DisparityBadge disparity={disparity} />
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
