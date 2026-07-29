import { buildEntityPath } from "./entity-paths";
import { freshestDate } from "./freshest-date";
import { siteKnowledgeIds } from "./site-knowledge";
import type {
  GameWithScores,
  JournalistDetail,
  OutletWithStats,
  ReviewTiming,
  ReviewWithDisparity,
  ReviewWithJournalist,
} from "../types";

export const SERVER_EVIDENCE_REVIEW_LIMIT = 5;

export interface EvidenceMetric {
  label: string;
  value: string;
  detail?: string;
}

export interface EvidenceReview {
  id: number;
  primaryLabel: string;
  primaryHref: string;
  secondaryLabel?: string;
  secondaryHref?: string;
  secondaryPrefix?: "by" | "via";
  scoreLabel: string;
  originalScoreLabel?: string;
  publishedAt?: string;
  timingLabel: string;
  sourceUrl?: string;
  steamScoreLabel?: string;
  metacriticScoreLabel?: string;
  steamDisparityLabel?: string;
  metacriticDisparityLabel?: string;
}

export interface EntityEvidence {
  heading: string;
  analysis: string[];
  metrics: EvidenceMetric[];
  reviews: EvidenceReview[];
  totalReviews: number;
  updatedAt?: string;
  sourceUrls: string[];
}

function finiteNumber(value: number | null | undefined): number | null {
  if (value == null) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function formatScore(value: number | null | undefined, digits = 1): string {
  const numeric = finiteNumber(value);
  if (numeric == null) return "N/A";
  return numeric.toFixed(digits);
}

function formatReviewScore(value: number | null | undefined): string {
  const numeric = finiteNumber(value);
  if (numeric == null) return "Score unavailable";
  return `${Number.isInteger(numeric) ? numeric.toFixed(0) : numeric.toFixed(1)}/100`;
}

function formatSigned(value: number | null | undefined): string | undefined {
  const numeric = finiteNumber(value);
  if (numeric == null) return undefined;
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(1)}`;
}

function formatCount(value: number | null | undefined): string {
  return Math.max(0, Math.trunc(finiteNumber(value) ?? 0)).toLocaleString("en-US");
}

function timingLabel(timing: ReviewTiming): string {
  if (timing === "early") return "Early review";
  if (timing === "launch_window") return "Launch window";
  if (timing === "late") return "Late review";
  return "Release date unknown";
}

function timingSentence(
  early: number | null | undefined,
  launch: number | null | undefined,
  late: number | null | undefined,
): string | undefined {
  const earlyCount = Math.max(0, Math.trunc(finiteNumber(early) ?? 0));
  const launchCount = Math.max(0, Math.trunc(finiteNumber(launch) ?? 0));
  const lateCount = Math.max(0, Math.trunc(finiteNumber(late) ?? 0));
  if (earlyCount + launchCount + lateCount === 0) return undefined;
  return `Review timing is ${formatCount(earlyCount)} early, ${formatCount(launchCount)} in the launch window, and ${formatCount(lateCount)} late.`;
}

function comparisonSentence(
  subject: string,
  source: "Steam" | "Metacritic",
  disparity: number | null | undefined,
): string | undefined {
  const numeric = finiteNumber(disparity);
  if (numeric == null) return undefined;
  if (Math.abs(numeric) < 0.05) {
    return `${subject} is effectively even with ${source} users.`;
  }
  return `${subject} is ${Math.abs(numeric).toFixed(1)} points ${numeric > 0 ? "higher" : "lower"} than ${source} users.`;
}

function safeSourceUrl(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : undefined;
  } catch {
    return undefined;
  }
}

function deriveUserScore(
  criticScore: number | null | undefined,
  disparity: number | null | undefined,
): number | null {
  const critic = finiteNumber(criticScore);
  const difference = finiteNumber(disparity);
  return critic == null || difference == null ? null : critic - difference;
}

function reviewComparisonLabel(
  score: number | null | undefined,
  disparity: number | null | undefined,
): string | undefined {
  const userScore = deriveUserScore(score, disparity);
  return userScore == null ? undefined : formatReviewScore(userScore);
}

function originalScoreLabel(
  rawScore: string | null | undefined,
  normalizedScore: number | null | undefined,
): string | undefined {
  const raw = rawScore?.trim();
  if (!raw) return undefined;
  const normalized = finiteNumber(normalizedScore);
  if (normalized != null && raw === normalized.toString()) return undefined;
  return raw;
}

function sourceUrls(reviews: EvidenceReview[]): string[] {
  return Array.from(
    new Set(reviews.map((review) => review.sourceUrl).filter((url): url is string => Boolean(url))),
  );
}

function gameReviewEvidence(review: ReviewWithJournalist): EvidenceReview {
  const outletIdentifier = review.outlet_public_id ?? review.outlet_id;
  return {
    id: review.id,
    primaryLabel: review.journalist_name,
    primaryHref: buildEntityPath(
      "journalists",
      review.journalist_name,
      review.journalist_public_id ?? review.journalist_id,
    ),
    ...(review.outlet_name && outletIdentifier != null
      ? {
          secondaryLabel: review.outlet_name,
          secondaryHref: buildEntityPath("outlets", review.outlet_name, outletIdentifier),
          secondaryPrefix: "via" as const,
        }
      : {}),
    scoreLabel: formatReviewScore(review.score_normalized),
    originalScoreLabel: originalScoreLabel(review.score_raw, review.score_normalized),
    publishedAt: review.published_at ?? undefined,
    timingLabel: timingLabel(review.review_timing),
    sourceUrl: safeSourceUrl(review.review_url),
    steamScoreLabel: reviewComparisonLabel(review.score_normalized, review.disparity_steam),
    metacriticScoreLabel: reviewComparisonLabel(
      review.score_normalized,
      review.disparity_metacritic,
    ),
    steamDisparityLabel: formatSigned(review.disparity_steam),
    metacriticDisparityLabel: formatSigned(review.disparity_metacritic),
  };
}

function journalistReviewEvidence(review: ReviewWithDisparity): EvidenceReview {
  const outletIdentifier = review.outlet_public_id ?? review.outlet_id;
  return {
    id: review.id,
    primaryLabel: review.game_title,
    primaryHref: buildEntityPath(
      "games",
      review.game_title,
      review.game_public_id ?? review.game_id,
    ),
    ...(review.outlet_name && outletIdentifier != null
      ? {
          secondaryLabel: review.outlet_name,
          secondaryHref: buildEntityPath("outlets", review.outlet_name, outletIdentifier),
          secondaryPrefix: "via" as const,
        }
      : {}),
    scoreLabel: formatReviewScore(review.score_normalized),
    originalScoreLabel: originalScoreLabel(review.score_raw, review.score_normalized),
    publishedAt: review.published_at ?? undefined,
    timingLabel: timingLabel(review.review_timing),
    sourceUrl: safeSourceUrl(review.review_url),
    steamScoreLabel:
      finiteNumber(review.steam_user_score) == null
        ? undefined
        : formatReviewScore(review.steam_user_score),
    metacriticScoreLabel:
      finiteNumber(review.metacritic_user_score) == null
        ? undefined
        : formatReviewScore(review.metacritic_user_score),
    steamDisparityLabel: formatSigned(review.disparity_steam),
    metacriticDisparityLabel: formatSigned(review.disparity_metacritic),
  };
}

function outletReviewEvidence(review: ReviewWithJournalist): EvidenceReview {
  const gameTitle = review.game_title || "Unknown game";
  return {
    id: review.id,
    primaryLabel: gameTitle,
    primaryHref: buildEntityPath("games", gameTitle, review.game_public_id ?? review.game_id),
    ...(review.journalist_name
      ? {
          secondaryLabel: review.journalist_name,
          secondaryHref: buildEntityPath(
            "journalists",
            review.journalist_name,
            review.journalist_public_id ?? review.journalist_id,
          ),
          secondaryPrefix: "by" as const,
        }
      : {}),
    scoreLabel: formatReviewScore(review.score_normalized),
    originalScoreLabel: originalScoreLabel(review.score_raw, review.score_normalized),
    publishedAt: review.published_at ?? undefined,
    timingLabel: timingLabel(review.review_timing),
    sourceUrl: safeSourceUrl(review.review_url),
    steamScoreLabel: reviewComparisonLabel(review.score_normalized, review.disparity_steam),
    metacriticScoreLabel: reviewComparisonLabel(
      review.score_normalized,
      review.disparity_metacritic,
    ),
    steamDisparityLabel: formatSigned(review.disparity_steam),
    metacriticDisparityLabel: formatSigned(review.disparity_metacritic),
  };
}

export function buildGameEvidence(
  game: GameWithScores,
  reviews: ReviewWithJournalist[],
  totalReviews: number,
): EntityEvidence {
  const normalizedReviews = reviews.slice(0, SERVER_EVIDENCE_REVIEW_LIMIT).map(gameReviewEvidence);
  const analysis = [
    `Across ${formatCount(totalReviews)} scored critic reviews, the critic average is ${formatScore(game.avg_critic_score)}/100.`,
    comparisonSentence("The critic average", "Steam", game.disparity_steam),
    comparisonSentence("The critic average", "Metacritic", game.disparity_metacritic),
    timingSentence(
      game.early_review_count,
      game.launch_window_review_count,
      game.late_review_count,
    ),
  ].filter((value): value is string => Boolean(value));

  const metrics: EvidenceMetric[] = [
    {
      label: "Scored critic reviews",
      value: formatCount(totalReviews),
    },
    ...(finiteNumber(game.steam_user_score) != null
      ? [{
          label: "Steam user score",
          value: `${formatScore(game.steam_user_score, 0)}/100`,
          detail: game.steam_sample_size
            ? `${formatCount(game.steam_sample_size)} user reviews`
            : "Sample size unavailable",
        }]
      : []),
    ...(finiteNumber(game.metacritic_user_score) != null
      ? [{
          label: "Metacritic user score",
          value: `${formatScore(game.metacritic_user_score, 0)}/100`,
          detail: game.metacritic_sample_size
            ? `${formatCount(game.metacritic_sample_size)} user reviews`
            : "Sample size unavailable",
        }]
      : []),
    {
      label: "Review timing",
      value: `${formatCount(game.early_review_count)} early · ${formatCount(game.launch_window_review_count)} launch · ${formatCount(game.late_review_count)} late`,
    },
  ];

  return {
    heading: `${game.title} evidence snapshot`,
    analysis,
    metrics,
    reviews: normalizedReviews,
    totalReviews,
    updatedAt: freshestDate(
      game.steam_player_stats_synced_at,
      game.steam_current_players_sampled_at,
      game.latest_review?.published_at,
      ...normalizedReviews.map((review) => review.publishedAt),
    ),
    sourceUrls: sourceUrls(normalizedReviews),
  };
}

export function buildJournalistEvidence(
  journalist: JournalistDetail,
  reviews: ReviewWithDisparity[],
  totalReviews: number,
): EntityEvidence {
  const stats = journalist.stats;
  const normalizedReviews = reviews
    .slice(0, SERVER_EVIDENCE_REVIEW_LIMIT)
    .map(journalistReviewEvidence);
  const analysis = [
    `Across ${formatCount(totalReviews)} scored reviews, ${journalist.name}'s average score is ${formatScore(stats.avg_score_given)}/100.`,
    comparisonSentence(
      "That average",
      "Steam",
      stats.overall_disparity_steam ?? stats.avg_disparity_steam,
    ),
    comparisonSentence(
      "That average",
      "Metacritic",
      stats.overall_disparity_metacritic ?? stats.avg_disparity_metacritic,
    ),
    timingSentence(
      stats.early_review_count,
      stats.launch_window_review_count,
      stats.late_review_count,
    ),
  ].filter((value): value is string => Boolean(value));

  return {
    heading: `${journalist.name} evidence snapshot`,
    analysis,
    metrics: [
      { label: "Scored reviews", value: formatCount(totalReviews) },
      { label: "Average score given", value: `${formatScore(stats.avg_score_given)}/100` },
      {
        label: "Steam disparity",
        value: formatSigned(stats.overall_disparity_steam ?? stats.avg_disparity_steam) ?? "N/A",
        detail: "Critic score minus Steam user score",
      },
      {
        label: "Metacritic disparity",
        value:
          formatSigned(
            stats.overall_disparity_metacritic ?? stats.avg_disparity_metacritic,
          ) ?? "N/A",
        detail: "Critic score minus Metacritic user score",
      },
    ],
    reviews: normalizedReviews,
    totalReviews,
    updatedAt: freshestDate(
      journalist.updated_at,
      journalist.latest_review?.published_at,
      ...normalizedReviews.map((review) => review.publishedAt),
    ),
    sourceUrls: sourceUrls(normalizedReviews),
  };
}

export function buildOutletEvidence(
  outlet: OutletWithStats,
  reviews: ReviewWithJournalist[],
  totalReviews: number,
): EntityEvidence {
  const normalizedReviews = reviews
    .slice(0, SERVER_EVIDENCE_REVIEW_LIMIT)
    .map(outletReviewEvidence);
  const analysis = [
    `Across ${formatCount(totalReviews)} scored reviews, ${outlet.name}'s average score is ${formatScore(outlet.avg_score)}/100.`,
    comparisonSentence("That average", "Steam", outlet.avg_disparity_steam),
    comparisonSentence("That average", "Metacritic", outlet.avg_disparity_metacritic),
    timingSentence(
      outlet.early_review_count,
      outlet.launch_window_review_count,
      outlet.late_review_count,
    ),
  ].filter((value): value is string => Boolean(value));

  return {
    heading: `${outlet.name} evidence snapshot`,
    analysis,
    metrics: [
      { label: "Scored reviews", value: formatCount(totalReviews) },
      { label: "Average score given", value: `${formatScore(outlet.avg_score)}/100` },
      {
        label: "Steam disparity",
        value: formatSigned(outlet.avg_disparity_steam) ?? "N/A",
        detail: "Critic score minus Steam user score",
      },
      {
        label: "Metacritic disparity",
        value: formatSigned(outlet.avg_disparity_metacritic) ?? "N/A",
        detail: "Critic score minus Metacritic user score",
      },
    ],
    reviews: normalizedReviews,
    totalReviews,
    updatedAt: freshestDate(
      outlet.latest_review?.published_at,
      ...normalizedReviews.map((review) => review.publishedAt),
    ),
    sourceUrls: sourceUrls(normalizedReviews),
  };
}

export function buildEvidenceItemListJsonLd(
  canonicalUrl: string,
  evidence: EntityEvidence,
): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "ItemList",
    "@id": `${canonicalUrl}#recent-review-evidence`,
    name: evidence.heading,
    url: `${canonicalUrl}#evidence`,
    numberOfItems: evidence.reviews.length,
    ...(evidence.updatedAt && { dateModified: evidence.updatedAt }),
    itemListElement: evidence.reviews.map((review, index) => ({
      "@type": "ListItem",
      position: index + 1,
      item: {
        "@type": "CreativeWork",
        name: `${review.primaryLabel} — ${review.scoreLabel}`,
        ...(review.sourceUrl && { url: review.sourceUrl }),
        ...(review.publishedAt && { datePublished: review.publishedAt }),
      },
    })),
  };
}

export function buildEntityEvidenceGraphJsonLd(
  canonicalUrl: string,
  evidence: EntityEvidence,
): Record<string, unknown> {
  const ids = siteKnowledgeIds(new URL(canonicalUrl).origin);
  const itemList = buildEvidenceItemListJsonLd(canonicalUrl, evidence);
  const itemListNode = { ...itemList };
  delete itemListNode["@context"];
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebPage",
        "@id": `${canonicalUrl}#webpage`,
        url: canonicalUrl,
        name: evidence.heading,
        isPartOf: { "@id": ids.website },
        about: [
          { "@id": `${canonicalUrl}#entity` },
          { "@id": ids.dataset },
        ],
        mainEntity: { "@id": `${canonicalUrl}#entity` },
        publisher: { "@id": ids.organization },
        mentions: { "@id": `${canonicalUrl}#recent-review-evidence` },
        ...(evidence.updatedAt && { dateModified: evidence.updatedAt }),
        ...(evidence.sourceUrls.length > 0 && { isBasedOn: evidence.sourceUrls }),
      },
      itemListNode,
    ],
  };
}
