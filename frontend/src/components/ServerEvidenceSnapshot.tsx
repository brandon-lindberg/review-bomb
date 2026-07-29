import Link from "next/link";
import { JsonLd } from "@/components/JsonLd";
import {
  buildEvidenceItemListJsonLd,
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

function ReviewEvidenceRow({ review }: { review: EvidenceReview }) {
  const publishedLabel = formatDate(review.publishedAt);
  return (
    <li className="p-4 border rounded-lg" style={{ borderColor: "var(--border)" }}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <Link
              href={review.primaryHref}
              className="font-semibold hover:opacity-80"
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
            className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs"
            style={{ color: "var(--foreground-muted)" }}
          >
            {publishedLabel && <time dateTime={review.publishedAt}>{publishedLabel}</time>}
            <span aria-hidden="true">·</span>
            <span>{review.timingLabel}</span>
            {review.originalScoreLabel && (
              <>
                <span aria-hidden="true">·</span>
                <span>Published score: {review.originalScoreLabel}</span>
              </>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <span className="text-lg font-bold" style={{ color: "var(--foreground)" }}>
            {review.scoreLabel}
          </span>
          {review.sourceUrl && (
            <a
              href={review.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded px-3 py-1.5 text-sm font-medium hover:opacity-80"
              style={{ backgroundColor: "var(--color-rust)", color: "white" }}
            >
              Original review
            </a>
          )}
        </div>
      </div>
      {(review.steamScoreLabel || review.metacriticScoreLabel) && (
        <div
          className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t pt-3 text-sm"
          style={{ borderColor: "var(--border)", color: "var(--foreground-muted)" }}
        >
          {review.steamScoreLabel && (
            <span>
              Steam {review.steamScoreLabel}
              {review.steamDisparityLabel && ` (Δ ${review.steamDisparityLabel})`}
            </span>
          )}
          {review.metacriticScoreLabel && (
            <span>
              Metacritic {review.metacriticScoreLabel}
              {review.metacriticDisparityLabel &&
                ` (Δ ${review.metacriticDisparityLabel})`}
            </span>
          )}
        </div>
      )}
    </li>
  );
}

export function ServerEvidenceSnapshot({
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
      className="bg-white rounded-lg shadow p-6"
      aria-labelledby="evidence-heading"
    >
      <JsonLd data={buildEvidenceItemListJsonLd(canonicalUrl, evidence)} />
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2
            id="evidence-heading"
            className="text-xl font-semibold"
            style={{ color: "var(--foreground)" }}
          >
            Evidence snapshot
          </h2>
          <p className="mt-1 text-sm" style={{ color: "var(--foreground-muted)" }}>
            Aggregate findings and the five most recent scored review records available at
            render time.
          </p>
        </div>
        {updatedLabel && (
          <p className="shrink-0 text-xs" style={{ color: "var(--foreground-muted)" }}>
            Data updated <time dateTime={evidence.updatedAt}>{updatedLabel}</time>
          </p>
        )}
      </div>

      <div
        className="mt-5 rounded-lg border p-4"
        style={{
          borderColor: "var(--border)",
          backgroundColor: "var(--background-card)",
        }}
      >
        <h3 className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>
          What the data shows
        </h3>
        <div className="mt-2 space-y-1 text-sm leading-6" style={{ color: "var(--foreground-muted)" }}>
          {evidence.analysis.map((sentence) => (
            <p key={sentence}>{sentence}</p>
          ))}
        </div>
      </div>

      <dl className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {evidence.metrics.map((metric) => (
          <div
            key={metric.label}
            className="rounded-lg border p-3"
            style={{ borderColor: "var(--border)" }}
          >
            <dt className="text-xs" style={{ color: "var(--foreground-muted)" }}>
              {metric.label}
            </dt>
            <dd className="mt-1 font-semibold" style={{ color: "var(--foreground)" }}>
              {metric.value}
            </dd>
            {metric.detail && (
              <dd className="mt-1 text-xs" style={{ color: "var(--foreground-muted)" }}>
                {metric.detail}
              </dd>
            )}
          </div>
        ))}
      </dl>

      {evidence.reviews.length > 0 && (
        <div className="mt-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>
              Recent scored reviews
            </h3>
            <p className="text-xs" style={{ color: "var(--foreground-muted)" }}>
              Showing {evidence.reviews.length} of {evidence.totalReviews.toLocaleString("en-US")}
            </p>
          </div>
          <ol className="mt-3 space-y-3">
            {evidence.reviews.map((review) => (
              <ReviewEvidenceRow key={review.id} review={review} />
            ))}
          </ol>
        </div>
      )}

      <p className="mt-5 border-t pt-4 text-xs leading-5" style={{ borderColor: "var(--border)", color: "var(--foreground-muted)" }}>
        Disparity is critic score minus player score on a 0–100 scale. Positive values mean
        the critic score is higher. Review records link to their original publisher when a
        source URL is available.{" "}
        <Link href="/about" className="underline hover:opacity-80">
          Read the methodology and data-source notes.
        </Link>
      </p>
    </section>
  );
}
