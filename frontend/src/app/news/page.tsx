import type { Metadata } from "next";
import { getNews, getNewsSources } from "@/lib/api";
import { NewsCard } from "@/components/NewsCard";
import { SourceFilter } from "@/components/SourceFilter";
import { PaginationControls } from "@/components/PaginationControls";

export const revalidate = 60;

export async function generateMetadata({ searchParams }: PageProps): Promise<Metadata> {
  const { page: pageParam, source } = await searchParams;
  const hasFacetedState = Boolean(pageParam || source?.trim());

  return {
    title: "Gaming News",
    description:
      "Latest gaming news from top gaming outlets, industry newsletters, and independent games media.",
    alternates: { canonical: "/news" },
    ...(hasFacetedState && { robots: { index: false, follow: true } }),
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
      <section className="route-header">
        <div className="route-header__row">
          <div className="space-y-2">
            <span className="site-eyebrow">News</span>
            <h1 className="route-header__title">Gaming News</h1>
          </div>

          <div className="route-toolbar">
            <SourceFilter sources={sources} defaultValue={source} />
          </div>
        </div>
      </section>

      {news && news.items.length > 0 ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {news.items.map((article) => (
              <NewsCard key={article.id} article={article} />
            ))}
          </div>

          <PaginationControls
            page={page}
            totalPages={news.total_pages}
            buildHref={(nextPage) =>
              `/news?page=${nextPage}${source ? `&source=${encodeURIComponent(source)}` : ""}`
            }
          />
        </>
      ) : news && news.items.length === 0 ? (
        <div className="site-empty">
          <p style={{ color: "var(--foreground-muted)" }}>
            No news articles found.{source ? " Try a different source filter." : " Run the news sync to populate articles."}
          </p>
        </div>
      ) : (
        <div className="site-empty">
          <p style={{ color: "var(--foreground-muted)" }}>
            Unable to load news. Make sure the backend API is running.
          </p>
        </div>
      )}
    </div>
  );
}
