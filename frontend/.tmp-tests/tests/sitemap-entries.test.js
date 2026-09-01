"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const sitemap_entries_1 = require("../src/lib/sitemap-entries");
(0, node_test_1.default)("buildSitemapEntityPages emits canonical slug plus stable id URLs", () => {
    const { pages, skippedCount } = (0, sitemap_entries_1.buildSitemapEntityPages)({
        siteUrl: "https://reviewdisparity.com",
        entityType: "journalists",
        labelKey: "name",
        entries: [
            {
                public_id: "386b4f96fd55433584965a34e195a07a",
                name: "Kira Laib",
                last_modified: "2026-07-21T08:30:00Z",
            },
        ],
    });
    strict_1.default.equal(skippedCount, 0);
    strict_1.default.equal(pages.length, 1);
    strict_1.default.equal(pages[0].url, "https://reviewdisparity.com/journalists/kira-laib--386b4f96fd55433584965a34e195a07a");
    strict_1.default.equal(pages[0].lastModified, "2026-07-21T08:30:00.000Z");
});
(0, node_test_1.default)("buildSitemapEntityPages skips entries that would produce redirecting placeholder URLs", () => {
    const { pages, skippedCount } = (0, sitemap_entries_1.buildSitemapEntityPages)({
        siteUrl: "https://reviewdisparity.com",
        entityType: "games",
        labelKey: "title",
        entries: [
            {
                public_id: "game-1",
                title: "High Guard",
            },
            {
                public_id: "game-2",
                title: "",
            },
            {
                public_id: "",
                title: "Missing Stable ID",
            },
            {
                public_id: "game-3",
            },
        ],
    });
    strict_1.default.equal(skippedCount, 3);
    strict_1.default.deepEqual(pages.map((page) => page.url), ["https://reviewdisparity.com/games/high-guard--game-1"]);
    strict_1.default.ok(pages.every((page) => /--[^/]+$/.test(new URL(page.url).pathname)));
});
(0, node_test_1.default)("buildSitemapEntityPages reports invalid lastmod without dropping the canonical URL", () => {
    const { pages, invalidLastModifiedCount } = (0, sitemap_entries_1.buildSitemapEntityPages)({
        siteUrl: "https://reviewdisparity.com",
        entityType: "outlets",
        labelKey: "name",
        entries: [
            {
                public_id: "outlet-1",
                name: "Example & Games",
                last_modified: "not-a-date",
            },
        ],
    });
    strict_1.default.equal(pages.length, 1);
    strict_1.default.equal(pages[0].lastModified, undefined);
    strict_1.default.equal(invalidLastModifiedCount, 1);
});
(0, node_test_1.default)("validateSitemapInventory rejects count collapses and duplicate canonicals", () => {
    strict_1.default.throws(() => (0, sitemap_entries_1.validateSitemapInventory)({ pages: [], minimumCount: 1, label: "games" }), /below safety floor/);
    strict_1.default.throws(() => (0, sitemap_entries_1.validateSitemapInventory)({
        pages: [
            { url: "https://reviewdisparity.com/games/a--1" },
            { url: "https://reviewdisparity.com/games/a--1" },
        ],
        minimumCount: 1,
        label: "games",
    }), /duplicate canonical URLs/);
});
(0, node_test_1.default)("static sitemap includes indexable news and excludes noindex search", () => {
    const urls = (0, sitemap_entries_1.buildStaticSitemapPages)("https://reviewdisparity.com").map((page) => page.url);
    strict_1.default.ok(urls.includes("https://reviewdisparity.com/news"));
    strict_1.default.ok(!urls.includes("https://reviewdisparity.com/search"));
});
