import assert from "node:assert/strict";
import test from "node:test";
import {
  buildGameMarkdown,
  buildHomeMarkdown,
  buildJournalistMarkdown,
  buildOutletMarkdown,
} from "../src/lib/markdown-pages";
import type {
  GameWithScores,
  JournalistDetail,
  OutletWithStats,
  ReviewWithDisparity,
  ReviewWithJournalist,
} from "../src/types";

const SITE_URL = "https://reviewdisparity.com";

function makeGame(overrides: Partial<GameWithScores> = {}): GameWithScores {
  return {
    id: 1,
    public_id: "27aa5d6482fe4f888b337e9aac63cd14",
    title: "No Rest for the Wicked",
    release_date: "2024-04-18",
    description: "An action RPG.",
    image_url: null,
    opencritic_id: null,
    steam_app_id: 1371980,
    opencritic_score: null,
    steam_user_score: 71,
    steam_sample_size: 24567,
    steam_current_players: null,
    steam_current_players_sampled_at: null,
    steam_activity_preview: [],
    steam_player_24h_peak: null,
    steam_player_24h_low_observed: null,
    steam_player_all_time_peak: null,
    steam_player_all_time_peak_at: null,
    steam_player_stats_synced_at: null,
    steam_achievement_count: null,
    steam_achievement_count_synced_at: null,
    metacritic_user_score: 65,
    metacritic_sample_size: 321,
    avg_critic_score: 81.5,
    disparity_steam: 10.5,
    disparity_metacritic: 16.5,
    tier: null,
    percent_recommended: null,
    critic_review_count: 42,
    early_review_count: 5,
    launch_window_review_count: 30,
    late_review_count: 7,
    ...overrides,
  };
}

function makeGameReview(overrides: Partial<ReviewWithJournalist> = {}): ReviewWithJournalist {
  return {
    id: 10,
    journalist_id: 3,
    journalist_public_id: "386b4f96fd55433584965a34e195a07a",
    journalist_name: "Kira Laib",
    journalist_image_url: null,
    game_id: 1,
    game_public_id: "27aa5d6482fe4f888b337e9aac63cd14",
    game_title: "No Rest for the Wicked",
    game_release_date: "2024-04-18",
    outlet_id: 7,
    outlet_public_id: "9f2c1f0b4a614d3e8a5b0c7d6e5f4a3b",
    outlet_name: "Game Informer",
    score_raw: "8.5/10",
    score_scale: "0-10",
    score_normalized: 85,
    review_url: "https://example.com/review",
    snippet: "Great game.",
    published_at: "2024-04-20T12:00:00Z",
    disparity: 14,
    disparity_steam: 14,
    disparity_metacritic: 20,
    is_launch_window: true,
    review_timing: "launch_window",
    ...overrides,
  };
}

test("buildGameMarkdown includes title, canonical URL, scores, and review links", () => {
  const markdown = buildGameMarkdown({
    siteUrl: SITE_URL,
    game: makeGame(),
    reviews: [makeGameReview()],
    totalReviewCount: 42,
    similarGames: [
      {
        id: 2,
        public_id: "b5d3f1df00cf483da5dffea8c254146b",
        title: "Skald: Against the Black Priory",
        release_date: null,
        image_url: null,
        avg_critic_score: 80,
        steam_user_score: 90,
        metacritic_user_score: null,
        critic_review_count: 12,
        match_reasons: [],
        similarity_score: 0.9,
        confidence: "high",
      },
    ],
  });

  assert.match(markdown, /^# No Rest for the Wicked — Critic vs User Scores/m);
  assert.match(
    markdown,
    /Canonical URL: https:\/\/reviewdisparity\.com\/games\/no-rest-for-the-wicked--27aa5d6482fe4f888b337e9aac63cd14/
  );
  assert.match(markdown, /Critic average: 81\.5 \(42 reviews\)/);
  assert.match(markdown, /Steam user score: 71/);
  assert.match(markdown, /Disparity \(critic minus player\): \+13\.5/);
  assert.match(markdown, /Review timing: 5 early, 30 launch window, 7 late/);
  assert.match(markdown, /## Critic reviews \(showing 1 most recent of 42\)/);
  assert.match(
    markdown,
    /\[Kira Laib\]\(https:\/\/reviewdisparity\.com\/journalists\/kira-laib--386b4f96fd55433584965a34e195a07a\)/
  );
  assert.match(
    markdown,
    /\[Skald: Against the Black Priory\]\(https:\/\/reviewdisparity\.com\/games\/skald-against-the-black-priory--b5d3f1df00cf483da5dffea8c254146b\)/
  );
  // No private API surface should leak into agent-facing output.
  assert.ok(!markdown.includes("/api/"));
  assert.ok(!markdown.includes("onrender.com"));
});

test("buildGameMarkdown omits empty sections and handles missing scores", () => {
  const markdown = buildGameMarkdown({
    siteUrl: SITE_URL,
    game: makeGame({
      description: null,
      steam_user_score: null,
      steam_sample_size: null,
      metacritic_user_score: null,
      metacritic_sample_size: null,
      disparity_steam: null,
      disparity_metacritic: null,
      early_review_count: 0,
      launch_window_review_count: 0,
      late_review_count: 0,
    }),
    reviews: [],
    totalReviewCount: 0,
    similarGames: [],
  });

  assert.match(markdown, /Steam user score: N\/A/);
  assert.match(markdown, /Disparity \(critic minus player\): N\/A/);
  assert.ok(!markdown.includes("## About"));
  assert.ok(!markdown.includes("## Critic reviews"));
  assert.ok(!markdown.includes("## Similar games"));
  assert.ok(!markdown.includes("Review timing:"));
});

test("buildJournalistMarkdown includes stats, outlets, and game links", () => {
  const journalist: JournalistDetail = {
    id: 3,
    public_id: "386b4f96fd55433584965a34e195a07a",
    name: "Kira Laib",
    image_url: null,
    bio: "Reviews RPGs.",
    opencritic_id: null,
    review_count: 120,
    avg_disparity: 4.2,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    std_deviation: null,
    outlet_breakdown: [
      {
        outlet_id: 7,
        outlet_public_id: "9f2c1f0b4a614d3e8a5b0c7d6e5f4a3b",
        outlet_name: "Game Informer",
        review_count: 120,
        avg_disparity: 4.2,
        date_range_start: null,
        date_range_end: null,
      },
    ],
    stats: {
      total_reviews: 120,
      avg_score_given: 78.4,
      avg_disparity_steam: 3.1,
      avg_disparity_metacritic: 5.3,
      avg_disparity_combined: 4.2,
      overall_disparity_steam: 3.4,
      overall_disparity_metacritic: 5.6,
      overall_disparity_combined: 4.5,
      std_deviation: null,
      alignment_rating: null,
      early_review_count: 10,
      launch_window_review_count: 90,
      late_review_count: 20,
      min_score_given: 40,
      max_score_given: 100,
      score_std_deviation: null,
    },
  };

  const review: ReviewWithDisparity = {
    id: 11,
    journalist_id: 3,
    journalist_public_id: "386b4f96fd55433584965a34e195a07a",
    game_id: 1,
    game_public_id: "27aa5d6482fe4f888b337e9aac63cd14",
    game_title: "No Rest for the Wicked",
    game_release_date: "2024-04-18",
    outlet_id: 7,
    outlet_public_id: null,
    outlet_name: "Game Informer",
    score_raw: "9/10",
    score_scale: "0-10",
    score_normalized: 90,
    review_url: null,
    snippet: null,
    published_at: "2024-04-20T12:00:00Z",
    steam_user_score: 71,
    metacritic_user_score: 65,
    disparity: 19,
    disparity_steam: 19,
    disparity_metacritic: 25,
    is_launch_window: true,
    review_timing: "launch_window",
  };

  const markdown = buildJournalistMarkdown({
    siteUrl: SITE_URL,
    journalist,
    reviews: [review],
    totalReviewCount: 120,
  });

  assert.match(markdown, /^# Kira Laib — Critic Score Alignment/m);
  assert.match(
    markdown,
    /Canonical URL: https:\/\/reviewdisparity\.com\/journalists\/kira-laib--386b4f96fd55433584965a34e195a07a/
  );
  assert.match(markdown, /Reviews tracked: 120/);
  assert.match(markdown, /Launch-window disparity vs players: \+4\.2/);
  assert.match(markdown, /- Game Informer: 120 reviews/);
  assert.match(
    markdown,
    /\[No Rest for the Wicked\]\(https:\/\/reviewdisparity\.com\/games\/no-rest-for-the-wicked--27aa5d6482fe4f888b337e9aac63cd14\)/
  );
});

test("buildOutletMarkdown includes aggregate stats and review table", () => {
  const outlet: OutletWithStats = {
    id: 7,
    public_id: "9f2c1f0b4a614d3e8a5b0c7d6e5f4a3b",
    name: "Game Informer",
    website_url: "https://gameinformer.com",
    logo_url: null,
    opencritic_id: null,
    journalist_count: 14,
    review_count: 800,
    avg_disparity: 6.1,
    avg_disparity_steam: 5.2,
    avg_disparity_metacritic: 7.0,
    avg_disparity_combined: 6.1,
    avg_score: 79.3,
    min_score_given: 20,
    max_score_given: 100,
    score_std_deviation: null,
  };

  const markdown = buildOutletMarkdown({
    siteUrl: SITE_URL,
    outlet,
    reviews: [makeGameReview()],
    totalReviewCount: 800,
  });

  assert.match(markdown, /^# Game Informer — Outlet Score Alignment/m);
  assert.match(
    markdown,
    /Canonical URL: https:\/\/reviewdisparity\.com\/outlets\/game-informer--9f2c1f0b4a614d3e8a5b0c7d6e5f4a3b/
  );
  assert.match(markdown, /Journalists tracked: 14/);
  assert.match(markdown, /Average disparity vs players: \+6\.1/);
  assert.match(markdown, /## Recent reviews \(showing 1 most recent of 800\)/);
});

test("buildHomeMarkdown includes coverage stats, recent reviews, and section links", () => {
  const markdown = buildHomeMarkdown({
    siteUrl: SITE_URL,
    stats: {
      total_journalists: 1200,
      total_outlets: 300,
      total_games: 29000,
      total_reviews: 250000,
      avg_disparity_site: 4.4,
      last_updated: "2026-07-11T00:00:00Z",
    },
    recentReviews: [makeGameReview()],
  });

  assert.match(markdown, /^# ReviewDisparity — Game Critic vs User Score Tracker/m);
  assert.match(markdown, /Games tracked: 29,000/);
  assert.match(markdown, /## Latest critic reviews/);
  assert.match(markdown, /\[Games\]\(https:\/\/reviewdisparity\.com\/games\)/);
  assert.match(markdown, /Accept: text\/markdown/);
});

test("markdown escapes pipe characters so tables stay intact", () => {
  const markdown = buildGameMarkdown({
    siteUrl: SITE_URL,
    game: makeGame(),
    reviews: [makeGameReview({ journalist_name: "Weird | Name", journalist_public_id: null })],
    totalReviewCount: 1,
    similarGames: [],
  });

  assert.ok(markdown.includes("Weird \\| Name"));
});
