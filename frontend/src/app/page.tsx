import Link from "next/link";
import { getStats, getJournalistLeaderboard, getGameLeaderboard } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";

export const dynamic = "force-dynamic";

export default async function Home() {
  let stats = null;
  let topJournalists = null;
  let topGames = null;

  try {
    [stats, topJournalists, topGames] = await Promise.all([
      getStats(),
      getJournalistLeaderboard(1, 5, "highest"),
      getGameLeaderboard(1, 5, "highest"),
    ]);
  } catch (error) {
    console.error("Error fetching data:", error);
  }

  return (
    <div className="space-y-12">
      {/* Hero Section */}
      <section className="text-center py-12">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">
          Review Disparity Tracker
        </h1>
        <p className="text-xl text-gray-600 max-w-2xl mx-auto">
          Track the gap between game journalist scores and player opinions.
          See which critics align with audiences and which diverge.
        </p>
      </section>

      {/* Stats Grid */}
      {stats && (
        <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Journalists" value={stats.total_journalists} />
          <StatCard label="Outlets" value={stats.total_outlets} />
          <StatCard label="Games" value={stats.total_games} />
          <StatCard label="Reviews" value={stats.total_reviews} />
        </section>
      )}

      {/* Leaderboards Preview */}
      <div className="grid md:grid-cols-2 gap-8">
        {/* Top Journalists by Disparity */}
        {topJournalists && topJournalists.items.length > 0 && (
          <section className="bg-white rounded-lg shadow p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold text-gray-900">
                Highest Disparity Critics
              </h2>
              <Link
                href="/leaderboards?tab=journalists"
                className="text-sm text-blue-600 hover:underline"
              >
                View All
              </Link>
            </div>
            <div className="space-y-3">
              {topJournalists.items.map((journalist, index) => (
                <Link
                  key={journalist.journalist_id}
                  href={`/journalists/${journalist.journalist_id}`}
                  className="flex items-center justify-between p-3 rounded hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-lg font-medium text-gray-400 w-6">
                      {index + 1}
                    </span>
                    <div>
                      <p className="font-medium text-gray-900">
                        {journalist.journalist_name}
                      </p>
                      <p className="text-sm text-gray-500">
                        {journalist.review_count} reviews
                      </p>
                    </div>
                  </div>
                  <DisparityBadge disparity={journalist.avg_disparity} />
                </Link>
              ))}
            </div>
          </section>
        )}

        {/* Most Divisive Games */}
        {topGames && topGames.items.length > 0 && (
          <section className="bg-white rounded-lg shadow p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold text-gray-900">
                Most Divisive Games
              </h2>
              <Link
                href="/leaderboards?tab=games"
                className="text-sm text-blue-600 hover:underline"
              >
                View All
              </Link>
            </div>
            <div className="space-y-3">
              {topGames.items.map((game, index) => (
                <Link
                  key={game.game_id}
                  href={`/games/${game.game_id}`}
                  className="flex items-center justify-between p-3 rounded hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-lg font-medium text-gray-400 w-6">
                      {index + 1}
                    </span>
                    <div>
                      <p className="font-medium text-gray-900">{game.game_title}</p>
                      <p className="text-sm text-gray-500">
                        Critics: {game.avg_critic_score != null ? Number(game.avg_critic_score).toFixed(0) : "N/A"} | Users:{" "}
                        {game.steam_user_score != null
                          ? Number(game.steam_user_score).toFixed(0)
                          : game.metacritic_user_score != null
                            ? Number(game.metacritic_user_score).toFixed(0)
                            : "N/A"}
                      </p>
                    </div>
                  </div>
                  <DisparityBadge disparity={game.disparity} />
                </Link>
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Call to Action */}
      <section className="text-center py-8">
        <div className="flex flex-wrap justify-center gap-4">
          <Link
            href="/journalists"
            className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
          >
            Browse Journalists
          </Link>
          <Link
            href="/games"
            className="px-6 py-3 bg-gray-200 text-gray-800 rounded-lg font-medium hover:bg-gray-300 transition-colors"
          >
            Browse Games
          </Link>
          <Link
            href="/leaderboards"
            className="px-6 py-3 bg-gray-200 text-gray-800 rounded-lg font-medium hover:bg-gray-300 transition-colors"
          >
            View Leaderboards
          </Link>
        </div>
      </section>

      {/* Empty state if no data */}
      {!stats && (
        <div className="text-center py-12 bg-white rounded-lg shadow">
          <p className="text-gray-600">
            Unable to load data. Make sure the backend API is running.
          </p>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="bg-white rounded-lg shadow p-6 text-center">
      <p className="text-3xl font-bold text-gray-900">
        {value != null ? value.toLocaleString() : "—"}
      </p>
      <p className="text-gray-600">{label}</p>
    </div>
  );
}
