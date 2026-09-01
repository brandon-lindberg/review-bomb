"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const entity_evidence_1 = require("../src/lib/entity-evidence");
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
};
(0, node_test_1.default)("game evidence explains separate user-score comparisons and sample sizes", () => {
    const game = {
        title: "Example Game",
        avg_critic_score: 81.5,
        disparity_steam: 10.5,
        disparity_metacritic: -2.5,
        steam_user_score: 71,
        steam_sample_size: 24567,
        metacritic_user_score: 84,
        metacritic_sample_size: 321,
        early_review_count: 5,
        launch_window_review_count: 30,
        late_review_count: 7,
        steam_player_stats_synced_at: "2026-07-21T00:00:00Z",
        steam_current_players_sampled_at: null,
        latest_review: null,
    };
    const evidence = (0, entity_evidence_1.buildGameEvidence)(game, [gameReview], 42);
    strict_1.default.equal(evidence.reviews.length, 1);
    strict_1.default.match(evidence.analysis.join(" "), /critics give this game an average score of 81\.5\/100/);
    strict_1.default.match(evidence.analysis.join(" "), /10\.5 points higher than Steam users/);
    strict_1.default.match(evidence.analysis.join(" "), /2\.5 points lower than Metacritic users/);
    strict_1.default.equal(evidence.metrics.find((metric) => metric.label === "Steam user score")?.detail, "24,567 user reviews");
    strict_1.default.equal(evidence.reviews[0].steamScoreLabel, "71/100");
    strict_1.default.equal(evidence.reviews[0].steamDisparityLabel, "+14.0");
    strict_1.default.equal(evidence.updatedAt, "2026-07-21T00:00:00.000Z");
    strict_1.default.deepEqual(evidence.sourceUrls, [
        "https://publisher.example/reviews/example",
    ]);
});
(0, node_test_1.default)("unsafe review URLs are excluded from visible evidence and structured citations", () => {
    const evidence = (0, entity_evidence_1.buildGameEvidence)({
        title: "Example Game",
        avg_critic_score: 80,
        disparity_steam: 5,
        disparity_metacritic: null,
    }, [{ ...gameReview, review_url: "javascript:alert(1)" }], 1);
    const jsonLd = (0, entity_evidence_1.buildEvidenceItemListJsonLd)("https://reviewdisparity.com/games/example--game-public-id", evidence);
    strict_1.default.equal(evidence.reviews[0].sourceUrl, undefined);
    strict_1.default.deepEqual(evidence.sourceUrls, []);
    strict_1.default.ok(!JSON.stringify(jsonLd).includes("javascript:"));
    strict_1.default.equal(jsonLd.numberOfItems, 1);
});
(0, node_test_1.default)("journalist evidence uses actual per-review user scores and overall disparities", () => {
    const review = {
        ...gameReview,
        steam_user_score: 71,
        metacritic_user_score: 65,
    };
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
    };
    const evidence = (0, entity_evidence_1.buildJournalistEvidence)(journalist, [review], 120);
    strict_1.default.match(evidence.analysis.join(" "), /3\.4 points higher than Steam users/);
    strict_1.default.equal(evidence.reviews[0].steamScoreLabel, "71/100");
    strict_1.default.match(evidence.reviews[0].primaryHref, /^\/games\/example-game--/);
    strict_1.default.equal(evidence.updatedAt, "2026-07-20T12:00:00.000Z");
});
(0, node_test_1.default)("outlet evidence links both games and journalists and emits source ItemList data", () => {
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
    };
    const evidence = (0, entity_evidence_1.buildOutletEvidence)(outlet, [gameReview], 300);
    const jsonLd = (0, entity_evidence_1.buildEvidenceItemListJsonLd)("https://reviewdisparity.com/outlets/example-outlet--outlet-public-id", evidence);
    const serialized = JSON.stringify(jsonLd);
    strict_1.default.match(evidence.analysis.join(" "), /1\.5 points lower than Steam users/);
    strict_1.default.match(evidence.reviews[0].primaryHref, /^\/games\/example-game--/);
    strict_1.default.match(evidence.reviews[0].secondaryHref || "", /^\/journalists\/kira-laib--/);
    strict_1.default.match(serialized, /"@type":"ItemList"/);
    strict_1.default.match(serialized, /https:\/\/publisher\.example\/reviews\/example/);
    strict_1.default.match(serialized, /"dateModified":"2026-07-20T12:00:00\.000Z"/);
});
(0, node_test_1.default)("entity evidence graph connects the page, entity, publisher, dataset, and sources", () => {
    const evidence = (0, entity_evidence_1.buildGameEvidence)({
        title: "Example Game",
        avg_critic_score: 80,
        disparity_steam: 5,
        disparity_metacritic: 10,
    }, [gameReview], 1);
    const canonicalUrl = "https://reviewdisparity.com/games/example-game--game-public-id";
    const graph = (0, entity_evidence_1.buildEntityEvidenceGraphJsonLd)(canonicalUrl, evidence);
    const serialized = JSON.stringify(graph);
    strict_1.default.match(serialized, /"@type":"WebPage"/);
    strict_1.default.match(serialized, /example-game--game-public-id#entity/);
    strict_1.default.match(serialized, /example-game--game-public-id#recent-review-evidence/);
    strict_1.default.match(serialized, /https:\/\/reviewdisparity\.com\/#organization/);
    strict_1.default.match(serialized, /https:\/\/reviewdisparity\.com\/about#dataset/);
    strict_1.default.match(serialized, /"isBasedOn":\["https:\/\/publisher\.example\/reviews\/example"\]/);
});
