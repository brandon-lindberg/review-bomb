import assert from "node:assert/strict";
import test from "node:test";
import {
  buildEntityEvidenceGraphJsonLd,
  buildEvidenceItemListJsonLd,
  buildGameEvidence,
  buildJournalistEvidence,
  buildOutletEvidence,
} from "../src/lib/entity-evidence";
import type {
  GameWithScores,
  JournalistDetail,
  OutletWithStats,
  ReviewWithDisparity,
  ReviewWithJournalist,
} from "../src/types";

const gameReview = {
  id: 10,
  journalist_id: 3,
  journalist_public_id: "journalist-public-id",
  journalist_name: "Kira Laib",
  journalist_image_url: null,
  game_id: 1,
  game_public_id: "game-public-id",
  game_title: "Example Game",
  game_release_date: "2024-04-18",
  outlet_id: 7,
  outlet_public_id: "outlet-public-id",
  outlet_name: "Example Outlet",
  score_raw: "8.5/10",
  score_scale: "0-10",
  score_normalized: 85,
  review_url: "https://publisher.example/reviews/example",
  snippet: null,
  published_at: "2026-07-20T12:00:00Z",
  disparity: 12,
  disparity_steam: 14,
  disparity_metacritic: 20,
  is_launch_window: true,
  review_timing: "launch_window",
} as ReviewWithJournalist;

test("game evidence explains separate user-score comparisons and sample sizes", () => {
  const game = {
    title: "Example Game",
    avg_critic_score: 81.5,
    disparity_steam: 10.5,
    disparity_metacritic: -2.5,
    steam_user_score: 71,
    steam_sample_size: 24_567,
    metacritic_user_score: 84,
    metacritic_sample_size: 321,
    early_review_count: 5,
    launch_window_review_count: 30,
    late_review_count: 7,
    steam_player_stats_synced_at: "2026-07-21T00:00:00Z",
    steam_current_players_sampled_at: null,
    latest_review: null,
  } as GameWithScores;

  const evidence = buildGameEvidence(game, [gameReview], 42);

  assert.equal(evidence.reviews.length, 1);
  assert.match(evidence.analysis.join(" "), /critic average is 81\.5\/100/);
  assert.match(evidence.analysis.join(" "), /10\.5 points higher than Steam users/);
  assert.match(evidence.analysis.join(" "), /2\.5 points lower than Metacritic users/);
  assert.equal(
    evidence.metrics.find((metric) => metric.label === "Steam user score")?.detail,
    "24,567 user reviews",
  );
  assert.equal(evidence.reviews[0].steamScoreLabel, "71/100");
  assert.equal(evidence.reviews[0].steamDisparityLabel, "+14.0");
  assert.equal(evidence.updatedAt, "2026-07-21T00:00:00.000Z");
  assert.deepEqual(evidence.sourceUrls, [
    "https://publisher.example/reviews/example",
  ]);
});

test("unsafe review URLs are excluded from visible evidence and structured citations", () => {
  const evidence = buildGameEvidence(
    {
      title: "Example Game",
      avg_critic_score: 80,
      disparity_steam: 5,
      disparity_metacritic: null,
    } as GameWithScores,
    [{ ...gameReview, review_url: "javascript:alert(1)" }],
    1,
  );
  const jsonLd = buildEvidenceItemListJsonLd(
    "https://reviewdisparity.com/games/example--game-public-id",
    evidence,
  );

  assert.equal(evidence.reviews[0].sourceUrl, undefined);
  assert.deepEqual(evidence.sourceUrls, []);
  assert.ok(!JSON.stringify(jsonLd).includes("javascript:"));
  assert.equal(jsonLd.numberOfItems, 1);
});

test("journalist evidence uses actual per-review user scores and overall disparities", () => {
  const review = {
    ...gameReview,
    steam_user_score: 71,
    metacritic_user_score: 65,
  } as ReviewWithDisparity;
  const journalist = {
    name: "Kira Laib",
    review_count: 120,
    updated_at: "2026-07-19T00:00:00Z",
    latest_review: null,
    stats: {
      total_reviews: 120,
      avg_score_given: 78.4,
      avg_disparity_steam: 3.1,
      avg_disparity_metacritic: 5.3,
      overall_disparity_steam: 3.4,
      overall_disparity_metacritic: 5.6,
      early_review_count: 10,
      launch_window_review_count: 90,
      late_review_count: 20,
    },
  } as JournalistDetail;

  const evidence = buildJournalistEvidence(journalist, [review], 120);

  assert.match(evidence.analysis.join(" "), /3\.4 points higher than Steam users/);
  assert.equal(evidence.reviews[0].steamScoreLabel, "71/100");
  assert.match(evidence.reviews[0].primaryHref, /^\/games\/example-game--/);
  assert.equal(evidence.updatedAt, "2026-07-20T12:00:00.000Z");
});

test("outlet evidence links both games and journalists and emits source ItemList data", () => {
  const outlet = {
    name: "Example Outlet",
    review_count: 300,
    avg_score: 76.2,
    avg_disparity_steam: -1.5,
    avg_disparity_metacritic: 4.5,
    early_review_count: 12,
    launch_window_review_count: 250,
    late_review_count: 38,
    latest_review: null,
  } as OutletWithStats;
  const evidence = buildOutletEvidence(outlet, [gameReview], 300);
  const jsonLd = buildEvidenceItemListJsonLd(
    "https://reviewdisparity.com/outlets/example-outlet--outlet-public-id",
    evidence,
  );
  const serialized = JSON.stringify(jsonLd);

  assert.match(evidence.analysis.join(" "), /1\.5 points lower than Steam users/);
  assert.match(evidence.reviews[0].primaryHref, /^\/games\/example-game--/);
  assert.match(evidence.reviews[0].secondaryHref || "", /^\/journalists\/kira-laib--/);
  assert.match(serialized, /"@type":"ItemList"/);
  assert.match(serialized, /https:\/\/publisher\.example\/reviews\/example/);
  assert.match(serialized, /"dateModified":"2026-07-20T12:00:00\.000Z"/);
});

test("entity evidence graph connects the page, entity, publisher, dataset, and sources", () => {
  const evidence = buildGameEvidence(
    {
      title: "Example Game",
      avg_critic_score: 80,
      disparity_steam: 5,
      disparity_metacritic: 10,
    } as GameWithScores,
    [gameReview],
    1,
  );
  const canonicalUrl =
    "https://reviewdisparity.com/games/example-game--game-public-id";
  const graph = buildEntityEvidenceGraphJsonLd(canonicalUrl, evidence);
  const serialized = JSON.stringify(graph);

  assert.match(serialized, /"@type":"WebPage"/);
  assert.match(serialized, /example-game--game-public-id#entity/);
  assert.match(serialized, /example-game--game-public-id#recent-review-evidence/);
  assert.match(serialized, /https:\/\/reviewdisparity\.com\/#organization/);
  assert.match(serialized, /https:\/\/reviewdisparity\.com\/about#dataset/);
  assert.match(serialized, /"isBasedOn":\["https:\/\/publisher\.example\/reviews\/example"\]/);
});
