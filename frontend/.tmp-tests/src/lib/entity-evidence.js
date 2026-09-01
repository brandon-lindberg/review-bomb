"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SERVER_EVIDENCE_REVIEW_LIMIT = void 0;
exports.buildGameEvidence = buildGameEvidence;
exports.buildJournalistEvidence = buildJournalistEvidence;
exports.buildOutletEvidence = buildOutletEvidence;
exports.buildEvidenceItemListJsonLd = buildEvidenceItemListJsonLd;
exports.buildEntityEvidenceGraphJsonLd = buildEntityEvidenceGraphJsonLd;
const entity_paths_1 = require("./entity-paths");
const freshest_date_1 = require("./freshest-date");
const site_knowledge_1 = require("./site-knowledge");
exports.SERVER_EVIDENCE_REVIEW_LIMIT = 5;
function finiteNumber(value) {
    if (value == null)
        return null;
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
}
function formatScore(value, digits = 1) {
    const numeric = finiteNumber(value);
    if (numeric == null)
        return "N/A";
    return numeric.toFixed(digits);
}
function formatReviewScore(value) {
    const numeric = finiteNumber(value);
    if (numeric == null)
        return "Score unavailable";
    return `${Number.isInteger(numeric) ? numeric.toFixed(0) : numeric.toFixed(1)}/100`;
}
function formatSigned(value) {
    const numeric = finiteNumber(value);
    if (numeric == null)
        return undefined;
    return `${numeric > 0 ? "+" : ""}${numeric.toFixed(1)}`;
}
function formatCount(value) {
    return Math.max(0, Math.trunc(finiteNumber(value) ?? 0)).toLocaleString("en-US");
}
function timingLabel(timing) {
    if (timing === "early")
        return "Early review";
    if (timing === "launch_window")
        return "Launch window";
    if (timing === "late")
        return "Late review";
    return "Release date unknown";
}
function timingSentence(early, launch, late) {
    const earlyCount = Math.max(0, Math.trunc(finiteNumber(early) ?? 0));
    const launchCount = Math.max(0, Math.trunc(finiteNumber(launch) ?? 0));
    const lateCount = Math.max(0, Math.trunc(finiteNumber(late) ?? 0));
    if (earlyCount + launchCount + lateCount === 0)
        return undefined;
    return `Reviews were published ${formatCount(earlyCount)} before release, ${formatCount(launchCount)} within the 60-day launch window, and ${formatCount(lateCount)} later.`;
}
function comparisonPhrase(source, disparity) {
    const numeric = finiteNumber(disparity);
    if (numeric == null)
        return undefined;
    if (Math.abs(numeric) < 0.05) {
        return `about the same as ${source} users`;
    }
    return `${Math.abs(numeric).toFixed(1)} points ${numeric > 0 ? "higher" : "lower"} than ${source} users`;
}
function comparisonSentence(subject, steamDisparity, metacriticDisparity) {
    const comparisons = [
        comparisonPhrase("Steam", steamDisparity),
        comparisonPhrase("Metacritic", metacriticDisparity),
    ].filter((value) => Boolean(value));
    if (comparisons.length === 0)
        return undefined;
    return `${subject} ${comparisons.join(" and ")}.`;
}
function safeSourceUrl(value) {
    if (!value)
        return undefined;
    try {
        const url = new URL(value);
        return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : undefined;
    }
    catch {
        return undefined;
    }
}
function deriveUserScore(criticScore, disparity) {
    const critic = finiteNumber(criticScore);
    const difference = finiteNumber(disparity);
    return critic == null || difference == null ? null : critic - difference;
}
function reviewComparisonLabel(score, disparity) {
    const userScore = deriveUserScore(score, disparity);
    return userScore == null ? undefined : formatReviewScore(userScore);
}
function originalScoreLabel(rawScore, normalizedScore) {
    const raw = rawScore?.trim();
    if (!raw)
        return undefined;
    const normalized = finiteNumber(normalizedScore);
    if (normalized != null && raw === normalized.toString())
        return undefined;
    return raw;
}
function sourceUrls(reviews) {
    return Array.from(new Set(reviews.map((review) => review.sourceUrl).filter((url) => Boolean(url))));
}
function gameReviewEvidence(review) {
    const outletIdentifier = review.outlet_public_id ?? review.outlet_id;
    return {
        id: review.id,
        primaryLabel: review.journalist_name,
        primaryHref: (0, entity_paths_1.buildEntityPath)("journalists", review.journalist_name, review.journalist_public_id ?? review.journalist_id),
        ...(review.outlet_name && outletIdentifier != null
            ? {
                secondaryLabel: review.outlet_name,
                secondaryHref: (0, entity_paths_1.buildEntityPath)("outlets", review.outlet_name, outletIdentifier),
                secondaryPrefix: "via",
            }
            : {}),
        scoreLabel: formatReviewScore(review.score_normalized),
        originalScoreLabel: originalScoreLabel(review.score_raw, review.score_normalized),
        publishedAt: review.published_at ?? undefined,
        timingLabel: timingLabel(review.review_timing),
        sourceUrl: safeSourceUrl(review.review_url),
        steamScoreLabel: reviewComparisonLabel(review.score_normalized, review.disparity_steam),
        metacriticScoreLabel: reviewComparisonLabel(review.score_normalized, review.disparity_metacritic),
        steamDisparityLabel: formatSigned(review.disparity_steam),
        metacriticDisparityLabel: formatSigned(review.disparity_metacritic),
    };
}
function journalistReviewEvidence(review) {
    const outletIdentifier = review.outlet_public_id ?? review.outlet_id;
    return {
        id: review.id,
        primaryLabel: review.game_title,
        primaryHref: (0, entity_paths_1.buildEntityPath)("games", review.game_title, review.game_public_id ?? review.game_id),
        ...(review.outlet_name && outletIdentifier != null
            ? {
                secondaryLabel: review.outlet_name,
                secondaryHref: (0, entity_paths_1.buildEntityPath)("outlets", review.outlet_name, outletIdentifier),
                secondaryPrefix: "via",
            }
            : {}),
        scoreLabel: formatReviewScore(review.score_normalized),
        originalScoreLabel: originalScoreLabel(review.score_raw, review.score_normalized),
        publishedAt: review.published_at ?? undefined,
        timingLabel: timingLabel(review.review_timing),
        sourceUrl: safeSourceUrl(review.review_url),
        steamScoreLabel: finiteNumber(review.steam_user_score) == null
            ? undefined
            : formatReviewScore(review.steam_user_score),
        metacriticScoreLabel: finiteNumber(review.metacritic_user_score) == null
            ? undefined
            : formatReviewScore(review.metacritic_user_score),
        steamDisparityLabel: formatSigned(review.disparity_steam),
        metacriticDisparityLabel: formatSigned(review.disparity_metacritic),
    };
}
function outletReviewEvidence(review) {
    const gameTitle = review.game_title || "Unknown game";
    return {
        id: review.id,
        primaryLabel: gameTitle,
        primaryHref: (0, entity_paths_1.buildEntityPath)("games", gameTitle, review.game_public_id ?? review.game_id),
        ...(review.journalist_name
            ? {
                secondaryLabel: review.journalist_name,
                secondaryHref: (0, entity_paths_1.buildEntityPath)("journalists", review.journalist_name, review.journalist_public_id ?? review.journalist_id),
                secondaryPrefix: "by",
            }
            : {}),
        scoreLabel: formatReviewScore(review.score_normalized),
        originalScoreLabel: originalScoreLabel(review.score_raw, review.score_normalized),
        publishedAt: review.published_at ?? undefined,
        timingLabel: timingLabel(review.review_timing),
        sourceUrl: safeSourceUrl(review.review_url),
        steamScoreLabel: reviewComparisonLabel(review.score_normalized, review.disparity_steam),
        metacriticScoreLabel: reviewComparisonLabel(review.score_normalized, review.disparity_metacritic),
        steamDisparityLabel: formatSigned(review.disparity_steam),
        metacriticDisparityLabel: formatSigned(review.disparity_metacritic),
    };
}
function buildGameEvidence(game, reviews, totalReviews) {
    const normalizedReviews = reviews.slice(0, exports.SERVER_EVIDENCE_REVIEW_LIMIT).map(gameReviewEvidence);
    const analysis = [
        `Based on ${formatCount(totalReviews)} scored critic reviews, critics give this game an average score of ${formatScore(game.avg_critic_score)}/100.`,
        comparisonSentence("Critics score this game", game.disparity_steam, game.disparity_metacritic),
        timingSentence(game.early_review_count, game.launch_window_review_count, game.late_review_count),
    ].filter((value) => Boolean(value));
    const metrics = [
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
        heading: `${game.title} review sources`,
        analysis,
        metrics,
        reviews: normalizedReviews,
        totalReviews,
        updatedAt: (0, freshest_date_1.freshestDate)(game.steam_player_stats_synced_at, game.steam_current_players_sampled_at, game.latest_review?.published_at, ...normalizedReviews.map((review) => review.publishedAt)),
        sourceUrls: sourceUrls(normalizedReviews),
    };
}
function buildJournalistEvidence(journalist, reviews, totalReviews) {
    const stats = journalist.stats;
    const normalizedReviews = reviews
        .slice(0, exports.SERVER_EVIDENCE_REVIEW_LIMIT)
        .map(journalistReviewEvidence);
    const analysis = [
        `Based on ${formatCount(totalReviews)} scored reviews, ${journalist.name} gives games an average score of ${formatScore(stats.avg_score_given)}/100.`,
        comparisonSentence(`${journalist.name} scores games`, stats.overall_disparity_steam ?? stats.avg_disparity_steam, stats.overall_disparity_metacritic ?? stats.avg_disparity_metacritic),
        timingSentence(stats.early_review_count, stats.launch_window_review_count, stats.late_review_count),
    ].filter((value) => Boolean(value));
    return {
        heading: `${journalist.name} review sources`,
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
                value: formatSigned(stats.overall_disparity_metacritic ?? stats.avg_disparity_metacritic) ?? "N/A",
                detail: "Critic score minus Metacritic user score",
            },
        ],
        reviews: normalizedReviews,
        totalReviews,
        updatedAt: (0, freshest_date_1.freshestDate)(journalist.updated_at, journalist.latest_review?.published_at, ...normalizedReviews.map((review) => review.publishedAt)),
        sourceUrls: sourceUrls(normalizedReviews),
    };
}
function buildOutletEvidence(outlet, reviews, totalReviews) {
    const normalizedReviews = reviews
        .slice(0, exports.SERVER_EVIDENCE_REVIEW_LIMIT)
        .map(outletReviewEvidence);
    const analysis = [
        `Based on ${formatCount(totalReviews)} scored reviews, ${outlet.name} gives games an average score of ${formatScore(outlet.avg_score)}/100.`,
        comparisonSentence(`${outlet.name} scores games`, outlet.avg_disparity_steam, outlet.avg_disparity_metacritic),
        timingSentence(outlet.early_review_count, outlet.launch_window_review_count, outlet.late_review_count),
    ].filter((value) => Boolean(value));
    return {
        heading: `${outlet.name} review sources`,
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
        updatedAt: (0, freshest_date_1.freshestDate)(outlet.latest_review?.published_at, ...normalizedReviews.map((review) => review.publishedAt)),
        sourceUrls: sourceUrls(normalizedReviews),
    };
}
function buildEvidenceItemListJsonLd(canonicalUrl, evidence) {
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
function buildEntityEvidenceGraphJsonLd(canonicalUrl, evidence) {
    const ids = (0, site_knowledge_1.siteKnowledgeIds)(new URL(canonicalUrl).origin);
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
