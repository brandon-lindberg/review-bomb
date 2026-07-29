import Link from "next/link";
import { JsonLd } from "@/components/JsonLd";
import {
  buildEntityEvidenceGraphJsonLd,
  type EntityEvidence,
  type EvidenceReview,
} from "@/lib/entity-evidence";

function formatDate(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return undefined;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

function ReviewSourceRow({ review }: { review: EvidenceReview }) {
  const publishedLabel = formatDate(review.publishedAt);
  return (
    <li className="p-3 sm:p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <Link
              href={review.primaryHref}
              className="text-sm font-semibold hover:opacity-80"
              style={{ color: "var(--foreground)" }}
            >
              {review.primaryLabel}
            </Link>
            {review.secondaryLabel && review.secondaryHref && (
              <>
                <span className="text-sm" style={{ color: "var(--foreground-muted)" }}>
                  {review.secondaryPrefix}
                </span>
                <Link
                  href={review.secondaryHref}
                  className="text-sm hover:opacity-80"
                  style={{ color: "var(--foreground-muted)" }}
                >
                  {review.secondaryLabel}
                </Link>
              </>
            )}
          </div>
          <div
            className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs leading-5"
            style={{ color: "var(--foreground-muted)" }}
          >
            {publishedLabel && <time dateTime={review.publishedAt}>{publishedLabel}</time>}
            {publishedLabel && <span aria-hidden="true">·</span>}
            <span>{review.timingLabel}</span>
            {review.originalScoreLabel && (
              <>
                <span aria-hidden="true">·</span>
                <span>Published score: {review.originalScoreLabel}</span>
              </>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3 sm:justify-end">
          <span className="text-sm font-bold" style={{ color: "var(--foreground)" }}>
            {review.scoreLabel}
          </span>
          {review.sourceUrl && (
            <a
              href={review.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-medium underline underline-offset-2 hover:opacity-80"
              style={{ color: "var(--color-rust)" }}
            >
              View review
            </a>
          )}
        </div>
      </div>
      {(review.steamScoreLabel || review.metacriticScoreLabel) && (
        <div
          className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs"
          style={{ color: "var(--foreground-muted)" }}
        >
          {review.steamScoreLabel && (
            <span>
              Steam {review.steamScoreLabel}
              {review.steamDisparityLabel && ` · ${review.steamDisparityLabel} pts`}
            </span>
          )}
          {review.metacriticScoreLabel && (
            <span>
              Metacritic {review.metacriticScoreLabel}
              {review.metacriticDisparityLabel &&
                ` · ${review.metacriticDisparityLabel} pts`}
            </span>
          )}
        </div>
      )}
    </li>
  );
}

export function ServerEvidenceSummary({
  canonicalUrl,
  evidence,
}: {
  canonicalUrl: string;
  evidence: EntityEvidence;
}) {
  const updatedLabel = formatDate(evidence.updatedAt);
  return (
    <section
      id="evidence"
      data-server-rendered-evidence="true"
      className="mt-6 border-t pt-6"
      style={{ borderColor: "var(--border)" }}
      aria-labelledby="evidence-heading"
    >
      <JsonLd data={buildEntityEvidenceGraphJsonLd(canonicalUrl, evidence)} />
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2
          id="evidence-heading"
          className="text-lg font-semibold"
          style={{ color: "var(--foreground)" }}
        >
          Review summary
        </h2>
        {updatedLabel && (
          <p className="shrink-0 text-xs" style={{ color: "var(--foreground-muted)" }}>
            Updated <time dateTime={evidence.updatedAt}>{updatedLabel}</time>
          </p>
        )}
      </div>

      <div
        className="mt-3 rounded-lg border-l-4 px-4 py-3"
        style={{
          borderColor: "var(--color-rust)",
          backgroundColor: "var(--background-card)",
        }}
      >
        <p
          className="text-sm leading-6"
          style={{ color: "var(--foreground-muted)" }}
        >
          {evidence.analysis.slice(0, 2).join(" ")}
        </p>
        <Link
          href="/about#dataset"
          className="mt-2 inline-block text-xs font-medium underline underline-offset-2 hover:opacity-80"
          style={{ color: "var(--foreground-muted)" }}
        >
          How these comparisons are calculated
        </Link>
      </div>

      {evidence.reviews.length > 0 && (
        <details className="group mt-3">
          <summary
            className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm hover:opacity-80"
            style={{
              color: "var(--foreground-muted)",
              backgroundColor: "var(--background-card)",
            }}
          >
            <span>
              Sources behind this summary
              <span className="ml-1 text-xs">
                ({evidence.reviews.length} recent of{" "}
                {evidence.totalReviews.toLocaleString("en-US")})
              </span>
            </span>
            <span
              aria-hidden="true"
              className="text-lg leading-none transition-transform group-open:rotate-45"
            >
              +
            </span>
          </summary>
          <ol
            className="mt-2 divide-y overflow-hidden rounded-lg border"
            style={{
              borderColor: "var(--border)",
              backgroundColor: "var(--background-card)",
            }}
          >
            {evidence.reviews.map((review) => (
              <ReviewSourceRow key={review.id} review={review} />
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}
