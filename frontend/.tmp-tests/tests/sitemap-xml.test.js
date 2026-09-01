"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const sitemap_xml_1 = require("../src/lib/sitemap-xml");
(0, node_test_1.default)("buildUrlSetXml emits escaped canonicals and ISO lastmod values", () => {
    const xml = (0, sitemap_xml_1.buildUrlSetXml)([
        {
            url: "https://reviewdisparity.com/games/a&b--1",
            lastModified: "2026-07-21T08:30:00Z",
            changeFrequency: "weekly",
            priority: 0.7,
        },
    ]);
    strict_1.default.match(xml, /<urlset xmlns="http:\/\/www\.sitemaps\.org\/schemas\/sitemap\/0\.9">/);
    strict_1.default.match(xml, /<loc>https:\/\/reviewdisparity\.com\/games\/a&amp;b--1<\/loc>/);
    strict_1.default.match(xml, /<lastmod>2026-07-21T08:30:00\.000Z<\/lastmod>/);
    strict_1.default.match(xml, /<changefreq>weekly<\/changefreq>/);
    strict_1.default.match(xml, /<priority>0\.7<\/priority>/);
});
(0, node_test_1.default)("buildSitemapIndexXml lists each segmented sitemap", () => {
    const xml = (0, sitemap_xml_1.buildSitemapIndexXml)([
        { url: "https://reviewdisparity.com/sitemaps/static.xml" },
        { url: "https://reviewdisparity.com/sitemaps/games.xml" },
    ]);
    strict_1.default.match(xml, /<sitemapindex/);
    strict_1.default.match(xml, /<loc>https:\/\/reviewdisparity\.com\/sitemaps\/static\.xml<\/loc>/);
    strict_1.default.match(xml, /<loc>https:\/\/reviewdisparity\.com\/sitemaps\/games\.xml<\/loc>/);
});
(0, node_test_1.default)("XML serialization rejects invalid lastmod values", () => {
    strict_1.default.throws(() => (0, sitemap_xml_1.buildUrlSetXml)([
        {
            url: "https://reviewdisparity.com/games/a--1",
            lastModified: "not-a-date",
        },
    ]), /Invalid sitemap lastmod value/);
});
