import type { Metadata } from "next";
import Link from "next/link";
import { getNews, getNewsSources } from "@/lib/api";
import { NewsCard } from "@/components/NewsCard";
import { SourceFilter } from "@/components/SourceFilter";

export const dynamic = "force-dynamic";

export async function generateMetadata({ searchParams }: PageProps): Promise<Metadata> {
  const { page: pageParam } = await searchParams;
  const page = parseInt(pageParam || "1");

  return {
    title: "Gaming News",
    description:
      "Latest gaming news from IGN, GameSpot, Kotaku, PC Gamer, Polygon, Eurogamer, and more.",
    alternates: { canonical: "/news" },
    ...(page > 1 && { robots: { index: false, follow: true } }),
    openGraph: {
      title: "Gaming News - ReviewDisparity",
      description:
        "Latest gaming news aggregated from top gaming outlets.",
      url: "/news",
    },
  };
}

interface PageProps {
  searchParams: Promise<{
    page?: string;
    source?: string;
  }>;
}

export default async function NewsPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const page = parseInt(params.page || "1");
  const source = params.source || undefined;

  let news = null;
  let sources: string[] = [];

  try {
    [news, sources] = await Promise.all([
      getNews(page, 18, source),
      getNewsSources(),
    ]);
  } catch (error) {
    console.error("Error fetching news:", error);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h1 className="text-3xl font-bold" style={{ color: "var(--foreground)" }}>
          Gaming News
        </h1>

        <div className="flex flex-wrap gap-2 items-center">
          <SourceFilter sources={sources} defaultValue={source} />
        </div>
      </div>

      {news && news.items.length > 0 ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {news.items.map((article) => (
              <NewsCard key={article.id} article={article} />
            ))}
          </div>

          {/* Pagination */}
          {news.total_pages > 1 && (
            <div className="flex justify-center gap-2">
              {page > 1 && (
                <Link
                  href={`/news?page=${page - 1}${source ? `&source=${encodeURIComponent(source)}` : ""}`}
                  prefetch={false}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Previous
                </Link>
              )}
              <span className="px-4 py-2 text-gray-600">
                Page {page} of {news.total_pages}
              </span>
              {page < news.total_pages && (
                <Link
                  href={`/news?page=${page + 1}${source ? `&source=${encodeURIComponent(source)}` : ""}`}
                  prefetch={false}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Next
                </Link>
              )}
            </div>
          )}
        </>
      ) : news && news.items.length === 0 ? (
        <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-lg shadow">
          <p style={{ color: "var(--foreground-muted)" }}>
            No news articles found.{source ? " Try a different source filter." : " Run the news sync to populate articles."}
          </p>
        </div>
      ) : (
        <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-lg shadow">
          <p style={{ color: "var(--foreground-muted)" }}>
            Unable to load news. Make sure the backend API is running.
          </p>
        </div>
      )}
    </div>
  );
}
