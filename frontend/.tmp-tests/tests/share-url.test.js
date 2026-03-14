"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_fs_1 = require("node:fs");
const node_path_1 = require("node:path");
const node_test_1 = __importDefault(require("node:test"));
const share_url_1 = require("../src/lib/share-url");
(0, node_test_1.default)("buildSnapshotShareParams includes expected base metrics", () => {
    const params = (0, share_url_1.buildSnapshotShareParams)({
        card: "g15",
        version: "119-89.79-96.27-95.00--5.85",
        critic: 89.79,
        steam: 96.27,
        metacritic: 95,
        disparity: -5.85,
    });
    strict_1.default.equal(params.get("card"), "g15");
    strict_1.default.equal(params.get("v"), "119-89.79-96.27-95.00--5.85");
    strict_1.default.equal(params.get("critic"), "89.79");
    strict_1.default.equal(params.get("steam"), "96.27");
    strict_1.default.equal(params.get("mc"), "95.00");
    strict_1.default.equal(params.get("disp"), "-5.85");
    strict_1.default.equal(params.get("mode"), null);
});
(0, node_test_1.default)("buildSnapshotShareParams includes chart trend payload and nonce", () => {
    const params = (0, share_url_1.buildSnapshotShareParams)({
        card: "gc1",
        version: "2-79.50-63.33-na-13.14",
        critic: 79.5,
        steam: 63.33,
        metacritic: null,
        disparity: 13.14,
        mode: "chart",
        trend: "7.5,15.0",
        nonce: "abcdefghijklmnopqrstuvwxyz123",
    });
    strict_1.default.equal(params.get("mode"), "chart");
    strict_1.default.equal(params.get("t"), "7.5,15.0");
    strict_1.default.equal(params.get("sx"), "abcdefghijklmnopqrstuvwx");
});
(0, node_test_1.default)("buildSnapshotShareParams includes timing counts, including zeros", () => {
    const params = (0, share_url_1.buildSnapshotShareParams)({
        card: "gc1",
        version: "2-79.50-63.33-na-13.14",
        critic: 79.5,
        steam: 63.33,
        metacritic: null,
        disparity: 13.14,
        mode: "timing",
        early: 0,
        launch: 2,
        late: 0,
    });
    strict_1.default.equal(params.get("mode"), "timing");
    strict_1.default.equal(params.get("early"), "0");
    strict_1.default.equal(params.get("launch"), "2");
    strict_1.default.equal(params.get("late"), "0");
});
(0, node_test_1.default)("entity snapshot share url updates when ingested metrics change", () => {
    const siteUrl = "https://reviewdisparity.com";
    const baseInput = {
        card: "g15",
        version: "old-v",
        critic: 80,
        steam: 70,
        metacritic: 60,
        disparity: 15,
    };
    const first = (0, share_url_1.buildEntitySnapshotShareUrl)(siteUrl, "games", "Game One", "game-1", baseInput);
    const second = (0, share_url_1.buildEntitySnapshotShareUrl)(siteUrl, "games", "Game One", "game-1", {
        ...baseInput,
        version: "new-v",
        critic: 81,
        disparity: 14,
    });
    const expectedSecond = (0, share_url_1.buildEntitySnapshotShareUrl)(siteUrl, "games", "Game One", "game-1", {
        ...baseInput,
        version: "new-v",
        critic: 81,
        disparity: 14,
    });
    strict_1.default.notEqual(first, second);
    strict_1.default.equal(second, expectedSecond);
    const firstParams = new URL(first).searchParams;
    const secondParams = new URL(second).searchParams;
    strict_1.default.equal(new URL(first).pathname, "/games/game-one--game-1");
    strict_1.default.equal(firstParams.get("v"), "old-v");
    strict_1.default.equal(secondParams.get("v"), "new-v");
    strict_1.default.equal(firstParams.get("critic"), "80.00");
    strict_1.default.equal(secondParams.get("critic"), "81.00");
    strict_1.default.equal(firstParams.get("disp"), "15.00");
    strict_1.default.equal(secondParams.get("disp"), "14.00");
});
(0, node_test_1.default)("entity snapshot share builder supports game, journalist, and outlet pages", () => {
    const siteUrl = "https://reviewdisparity.com";
    const entities = [
        { type: "games", id: "game-1" },
        { type: "journalists", id: "journalist-1" },
        { type: "outlets", id: "outlet-1" },
    ];
    for (const entity of entities) {
        const url = (0, share_url_1.buildEntitySnapshotShareUrl)(siteUrl, entity.type, entity.id.replace(/-/g, " "), entity.id, {
            card: "x1",
            version: "v1",
            critic: 80,
            steam: null,
            metacritic: 72,
            disparity: 8,
        });
        const parsed = new URL(url);
        strict_1.default.match(parsed.pathname, new RegExp(`^/${entity.type}/.+--${entity.id}$`));
        strict_1.default.equal(parsed.searchParams.get("card"), "x1");
        strict_1.default.equal(parsed.searchParams.get("steam"), "na");
        strict_1.default.equal(parsed.searchParams.get("mc"), "72.00");
    }
});
(0, node_test_1.default)("buildCompareShareUrl serializes ids, labels, and snapshot payload", () => {
    const url = (0, share_url_1.buildCompareShareUrl)("https://reviewdisparity.com", {
        type: "games",
        card: "v5",
        ids: [1, 2, 3],
        labels: ["A", "B", "C"],
        snapshotPayload: '[{"n":"A","c":80}]',
    });
    const params = new URL(url).searchParams;
    strict_1.default.equal(params.get("type"), "games");
    strict_1.default.equal(params.get("card"), "v5");
    strict_1.default.equal(params.get("ids"), "1,2,3");
    strict_1.default.equal(params.get("labels"), "A|B|C");
    strict_1.default.equal(params.get("snap"), '[{"n":"A","c":80}]');
});
(0, node_test_1.default)("buildCompareShareParams omits empty optional values", () => {
    const params = (0, share_url_1.buildCompareShareParams)({
        type: "journalists",
        card: "v5",
        ids: [],
        labels: [],
        snapshotPayload: "   ",
    });
    strict_1.default.equal(params.get("type"), "journalists");
    strict_1.default.equal(params.get("card"), "v5");
    strict_1.default.equal(params.get("ids"), null);
    strict_1.default.equal(params.get("labels"), null);
    strict_1.default.equal(params.get("snap"), null);
});
(0, node_test_1.default)("reddit and X share builders create expected intent urls", () => {
    const baseUrl = "https://reviewdisparity.com/games/game-1?card=g15&v=1";
    const text = "Game snapshot";
    const nonce = "abc123";
    const reddit = (0, share_url_1.buildRedditShareUrl)(baseUrl, text, nonce);
    const redditParams = new URL(reddit).searchParams;
    strict_1.default.equal(new URL(redditParams.get("url") ?? "").searchParams.get("sx"), nonce);
    strict_1.default.equal(redditParams.get("title"), text);
    const urlWithNonce = (0, share_url_1.withSnapshotNonce)(baseUrl, nonce);
    strict_1.default.equal(new URL(urlWithNonce).searchParams.get("sx"), nonce);
    strict_1.default.equal(new URL(urlWithNonce).searchParams.get("v"), "1");
    const xIntent = (0, share_url_1.buildXIntentUrl)(baseUrl, text, nonce);
    const xParams = new URL(xIntent).searchParams;
    strict_1.default.equal(xParams.get("text"), text);
    strict_1.default.equal(new URL(xParams.get("url") ?? "").searchParams.get("sx"), nonce);
});
(0, node_test_1.default)("withTrendSnapshot replaces trend payload and trend labels", () => {
    const baseUrl = "https://reviewdisparity.com/games/game-1?card=g15&v=1&mode=chart&t=1.0,2.0";
    const updated = (0, share_url_1.withTrendSnapshot)(baseUrl, {
        trend: "3.0,4.0,5.0",
        window: "1m",
        series: "steam",
    });
    const params = new URL(updated).searchParams;
    strict_1.default.equal(params.get("t"), "3.0,4.0,5.0");
    strict_1.default.equal(params.get("tw"), "1m");
    strict_1.default.equal(params.get("ts"), "steam");
});
(0, node_test_1.default)("share surfaces use the centralized share-url builders", () => {
    const root = process.cwd();
    const expectations = [
        {
            file: "src/components/ShareButtons.tsx",
            snippets: ["buildRedditShareUrl", "buildXIntentShareUrl", "withSnapshotNonce"],
        },
        {
            file: "src/app/games/[id]/page.tsx",
            snippets: ["buildEntitySnapshotShareUrl(", "Review Timing Snapshot"],
        },
        {
            file: "src/app/journalists/[id]/page.tsx",
            snippets: ["buildEntitySnapshotShareUrl(", "Review Timing Snapshot"],
        },
        {
            file: "src/app/outlets/[id]/page.tsx",
            snippets: ["buildEntitySnapshotShareUrl(", "Review Timing Snapshot"],
        },
        {
            file: "src/app/compare/page.tsx",
            snippets: ["buildCompareShareUrl(", "queryParams.set(\"sx\""],
        },
    ];
    for (const expectation of expectations) {
        const text = (0, node_fs_1.readFileSync)((0, node_path_1.join)(root, expectation.file), "utf8");
        for (const snippet of expectation.snippets) {
            strict_1.default.match(text, new RegExp(snippet.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")), `${expectation.file} should include ${snippet}`);
        }
    }
});
(0, node_test_1.default)("entity link surfaces use the shared path helper", () => {
    const root = process.cwd();
    const expectations = [
        {
            file: "src/app/page.tsx",
            snippets: ["buildEntityPath(", 'buildEntityPath("games"', 'buildEntityPath("journalists"'],
        },
        {
            file: "src/app/search/page.tsx",
            snippets: ["buildEntityPath(", 'buildEntityPath("outlets"'],
        },
        {
            file: "src/app/leaderboards/page.tsx",
            snippets: ["buildEntityPath(", 'buildEntityPath("games"'],
        },
        {
            file: "src/app/compare/page.tsx",
            snippets: ["buildEntityPath(", 'buildEntityPath("journalists"'],
        },
        {
            file: "src/components/OutletReviewsSection.tsx",
            snippets: ["buildEntityPath(", 'buildEntityPath("journalists"'],
        },
        {
            file: "src/components/JournalistReviewsSection.tsx",
            snippets: ["buildEntityPath(", 'buildEntityPath("outlets"'],
        },
    ];
    for (const expectation of expectations) {
        const text = (0, node_fs_1.readFileSync)((0, node_path_1.join)(root, expectation.file), "utf8");
        for (const snippet of expectation.snippets) {
            strict_1.default.match(text, new RegExp(snippet.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")), `${expectation.file} should include ${snippet}`);
        }
    }
});
