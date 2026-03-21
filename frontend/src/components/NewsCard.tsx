import Image from "@/components/AppImage";
import type { NewsArticle } from "@/types";

interface NewsCardProps {
  article: NewsArticle;
  compact?: boolean;
}

function shouldBypassImageOptimizer(article: NewsArticle): boolean {
  if (article.source_name === "Kotaku") {
    return true;
  }

  if (!article.image_url) {
    return false;
  }

  try {
    const hostname = new URL(article.image_url).hostname.toLowerCase();
    return hostname === "kotaku.com" || hostname.endsWith(".kotaku.com") || hostname.endsWith(".kinja-img.com");
  } catch {
    return false;
  }
}

export function NewsCard({ article, compact = false }: NewsCardProps) {
  const formattedDate = article.published_at
    ? new Date(article.published_at).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : null;
  const unoptimized = shouldBypassImageOptimizer(article);

  if (compact) {
    return (
      <a
        href={article.url}
        target="_blank"
        rel="noopener noreferrer"
        className="site-list-item flex w-full items-start justify-between gap-4 rounded-2xl border-0 px-0 py-3 first:pt-0 last:pb-0 hover:bg-transparent"
      >
        <div className="flex min-w-0 flex-1 items-start gap-3">
          {article.image_url && (
            <div className="h-12 w-16 shrink-0 overflow-hidden rounded sm:h-16 sm:w-20">
              <Image
                src={article.image_url}
                alt=""
                width={80}
                height={64}
                sizes="(max-width: 640px) 64px, 80px"
                unoptimized={unoptimized}
                className="h-full w-full object-cover"
              />
            </div>
          )}
          <div className="min-w-0 flex-1">
            <p
              className="line-clamp-2 text-sm font-medium"
              style={{ color: "var(--foreground)" }}
            >
              {article.title}
            </p>
            <div
              className="mt-1 flex items-center gap-1.5 text-xs"
              style={{ color: "var(--foreground-muted)" }}
            >
              <span className="font-medium">{article.source_name}</span>
              {formattedDate && (
                <>
                  <span>·</span>
                  <span>{formattedDate}</span>
                </>
              )}
            </div>
            {article.description && (
              <p
                className="mt-1 hidden line-clamp-1 text-xs sm:block"
                style={{ color: "var(--foreground-muted)" }}
              >
                {article.description}
              </p>
            )}
          </div>
        </div>
      </a>
    );
  }

  return (
    <a
      href={article.url}
      target="_blank"
      rel="noopener noreferrer"
      className="site-panel site-panel-interactive group overflow-hidden rounded-[1.5rem]"
    >
      {article.image_url && (
        <div className="relative h-48 w-full overflow-hidden">
          <Image
            src={article.image_url}
            alt=""
            fill
            sizes="(max-width: 768px) 100vw, (max-width: 1280px) 50vw, 33vw"
            unoptimized={unoptimized}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        </div>
      )}
      <div className="p-5">
        <div
          className="mb-3 flex flex-wrap items-center gap-2 text-xs"
          style={{ color: "var(--foreground-muted)" }}
        >
          <span
            className="site-chip site-chip--accent font-semibold uppercase tracking-wide"
            style={{ color: "var(--color-rust)" }}
          >
            {article.source_name}
          </span>
          {formattedDate && (
            <>
              <span>·</span>
              <span>{formattedDate}</span>
            </>
          )}
          {article.author && (
            <>
              <span>·</span>
              <span>{article.author}</span>
            </>
          )}
        </div>
        <h3
          className="mb-3 text-lg font-semibold line-clamp-2"
          style={{ color: "var(--foreground)" }}
        >
          {article.title}
        </h3>
        {article.description && (
          <p
            className="text-sm line-clamp-3"
            style={{ color: "var(--foreground-muted)" }}
          >
            {article.description}
          </p>
        )}
      </div>
    </a>
  );
}
