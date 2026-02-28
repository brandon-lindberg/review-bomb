import type { Metadata } from "next";
import Link from "next/link";
import { search } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";

export const revalidate = 30;

export const metadata: Metadata = {
  title: "Search",
  description:
    "Search for game journalists, outlets, and games to see their review scores and disparity data.",
  alternates: { canonical: "/search" },
  openGraph: {
    title: "Search - ReviewDisparity",
    description:
      "Search for game journalists, outlets, and games to see their review scores and disparity data.",
    url: "/search",
  },
};

interface PageProps {
  searchParams: Promise<{
    q?: string;
  }>;
}

export default async function SearchPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const query = params.q || "";

  let results = null;

  if (query.length >= 2) {
    try {
      results = await search(query, 20);
    } catch (error) {
      console.error("Error searching:", error);
    }
  }

  const hasResults =
    results &&
    (results.journalists.length > 0 ||
      results.outlets.length > 0 ||
      results.games.length > 0);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold" style={{ color: "var(--foreground)" }}>Search</h1>

      {/* Search Form */}
      <form action="/search" method="GET" className="max-w-xl">
        <div className="relative">
          <input
            type="text"
            name="q"
            defaultValue={query}
            placeholder="Search journalists, outlets, or games..."
            className="w-full px-4 py-3 border rounded-lg focus:ring-2 focus:outline-none"
            style={{ borderColor: "var(--border)" }}
          />
          <button
            type="submit"
            className="absolute right-2 top-1/2 -translate-y-1/2 px-4 py-1.5 text-white rounded-md hover:opacity-90"
            style={{ backgroundColor: "var(--color-rust)" }}
          >
            Search
          </button>
        </div>
      </form>

      {query.length >= 2 && results && (
        <div className="space-y-8">
          {/* Journalists */}
          {results.journalists.length > 0 && (
            <section>
              <h2 className="text-xl font-semibold text-gray-900 mb-4">
                Journalists ({results.journalists.length})
              </h2>
              <div className="bg-white rounded-lg shadow divide-y divide-gray-200">
                {results.journalists.map((journalist) => (
                  <Link
                    key={journalist.id}
                    href={`/journalists/${journalist.public_id}`}
                    className="block p-4 hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        {journalist.image_url ? (
                          <img
                            src={journalist.image_url}
                            alt={journalist.name}
                            className="w-10 h-10 rounded-full object-cover"
                          />
                        ) : (
                          <div className="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center">
                            <span className="text-gray-500 font-medium">
                              {journalist.name.charAt(0)}
                            </span>
                          </div>
                        )}
                        <div>
                          <p className="font-medium text-gray-900">
                            {journalist.name}
                          </p>
                          <p className="text-sm text-gray-500">
                            {journalist.review_count} reviews
                          </p>
                        </div>
                      </div>
                      <DisparityBadge disparity={journalist.avg_disparity} />
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* Outlets */}
          {results.outlets.length > 0 && (
            <section>
              <h2 className="text-xl font-semibold text-gray-900 mb-4">
                Outlets ({results.outlets.length})
              </h2>
              <div className="bg-white rounded-lg shadow divide-y divide-gray-200">
                {results.outlets.map((outlet) => (
                  <Link
                    key={outlet.id}
                    href={`/outlets/${outlet.public_id}`}
                    className="block p-4 hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        {outlet.logo_url ? (
                          <img
                            src={outlet.logo_url}
                            alt={outlet.name}
                            className="w-10 h-10 rounded object-contain bg-gray-100"
                          />
                        ) : (
                          <div className="w-10 h-10 rounded bg-gray-200 flex items-center justify-center">
                            <span className="text-gray-500 font-medium">
                              {outlet.name.charAt(0)}
                            </span>
                          </div>
                        )}
                        <div>
                          <p className="font-medium text-gray-900">
                            {outlet.name}
                          </p>
                          <p className="text-sm text-gray-500">
                            {outlet.review_count} reviews
                          </p>
                        </div>
                      </div>
                      <DisparityBadge disparity={outlet.avg_disparity} />
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* Games */}
          {results.games.length > 0 && (
            <section>
              <h2 className="text-xl font-semibold text-gray-900 mb-4">
                Games ({results.games.length})
              </h2>
              <div className="bg-white rounded-lg shadow divide-y divide-gray-200">
                {results.games.map((game) => (
                  <Link
                    key={game.id}
                    href={`/games/${game.public_id}`}
                    className="block p-4 hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium text-gray-900">{game.title}</p>
                        {game.release_date && (
                          <p className="text-sm text-gray-500">
                            {new Date(game.release_date).toLocaleDateString()}
                          </p>
                        )}
                      </div>
                      <DisparityBadge disparity={game.disparity} />
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* No results */}
          {!hasResults && (
            <div className="text-center py-12 bg-white rounded-lg shadow">
              <p className="text-gray-600">
                No results found for &ldquo;{query}&rdquo;
              </p>
            </div>
          )}
        </div>
      )}

      {query.length > 0 && query.length < 2 && (
        <div className="text-center py-12 bg-white rounded-lg shadow">
          <p className="text-gray-600">
            Please enter at least 2 characters to search.
          </p>
        </div>
      )}

      {!query && (
        <div className="text-center py-12 bg-white rounded-lg shadow">
          <p className="text-gray-600">
            Enter a search term to find journalists, outlets, or games.
          </p>
        </div>
      )}
    </div>
  );
}
