import assert from "node:assert/strict";
import test from "node:test";
import { buildSitemapIndexXml, buildUrlSetXml } from "../src/lib/sitemap-xml";

test("buildUrlSetXml emits escaped canonicals and ISO lastmod values", () => {
  const xml = buildUrlSetXml([
    {
      url: "https://reviewdisparity.com/games/a&b--1",
      lastModified: "2026-07-21T08:30:00Z",
      changeFrequency: "weekly",
      priority: 0.7,
    },
  ]);

  assert.match(xml, /<urlset xmlns="http:\/\/www\.sitemaps\.org\/schemas\/sitemap\/0\.9">/);
  assert.match(xml, /<loc>https:\/\/reviewdisparity\.com\/games\/a&amp;b--1<\/loc>/);
  assert.match(xml, /<lastmod>2026-07-21T08:30:00\.000Z<\/lastmod>/);
  assert.match(xml, /<changefreq>weekly<\/changefreq>/);
  assert.match(xml, /<priority>0\.7<\/priority>/);
});

test("buildSitemapIndexXml lists each segmented sitemap", () => {
  const xml = buildSitemapIndexXml([
    { url: "https://reviewdisparity.com/sitemaps/static.xml" },
    { url: "https://reviewdisparity.com/sitemaps/games.xml" },
  ]);

  assert.match(xml, /<sitemapindex/);
  assert.match(xml, /<loc>https:\/\/reviewdisparity\.com\/sitemaps\/static\.xml<\/loc>/);
  assert.match(xml, /<loc>https:\/\/reviewdisparity\.com\/sitemaps\/games\.xml<\/loc>/);
});

test("XML serialization rejects invalid lastmod values", () => {
  assert.throws(
    () =>
      buildUrlSetXml([
        {
          url: "https://reviewdisparity.com/games/a--1",
          lastModified: "not-a-date",
        },
      ]),
    /Invalid sitemap lastmod value/,
  );
});
