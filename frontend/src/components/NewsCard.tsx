import type { NewsArticle } from "@/types";

interface NewsCardProps {
  article: NewsArticle;
  compact?: boolean;
}

export function NewsCard({ article, compact = false }: NewsCardProps) {
  const formattedDate = article.published_at
    ? new Date(article.published_at).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : null;

  if (compact) {
    return (
      <a
        href={article.url}
        target="_blank"
        rel="noopener noreferrer"
        className="flex gap-3 p-3 rounded hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
      >
        {article.image_url && (
          <div className="flex-shrink-0 w-16 h-12 sm:w-20 sm:h-16 rounded overflow-hidden">
            <img
              src={article.image_url}
              alt=""
              className="w-full h-full object-cover"
            />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p
            className="font-medium text-sm line-clamp-2"
            style={{ color: "var(--foreground)" }}
          >
            {article.title}
          </p>
          <div
            className="flex items-center gap-1.5 text-xs mt-1"
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
              className="hidden sm:block text-xs mt-1 line-clamp-1"
              style={{ color: "var(--foreground-muted)" }}
            >
              {article.description}
            </p>
          )}
        </div>
        <span
          className="hidden sm:inline-flex flex-shrink-0 text-sm px-3 py-1 rounded hover:opacity-80 whitespace-nowrap self-center"
          style={{ backgroundColor: "var(--color-rust)", color: "white" }}
        >
          Read Article
        </span>
      </a>
    );
  }

  return (
    <a
      href={article.url}
      target="_blank"
      rel="noopener noreferrer"
      className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden hover:shadow-md transition-shadow group"
    >
      {article.image_url && (
        <div className="w-full h-44 overflow-hidden">
          <img
            src={article.image_url}
            alt=""
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
          />
        </div>
      )}
      <div className="p-4">
        <div
          className="flex items-center gap-2 text-xs mb-2"
          style={{ color: "var(--foreground-muted)" }}
        >
          <span
            className="font-semibold uppercase tracking-wide"
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
          className="font-semibold text-base line-clamp-2 mb-2"
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
        <div className="flex items-center gap-1 mt-3 text-xs" style={{ color: "var(--color-rust)" }}>
          <span>Read article</span>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
            <polyline points="15 3 21 3 21 9" />
            <line x1="10" y1="14" x2="21" y2="3" />
          </svg>
        </div>
      </div>
    </a>
  );
}
