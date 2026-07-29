import assert from "node:assert/strict";
import test from "node:test";
import {
  buildStaticSitemapPages,
  buildSitemapEntityPages,
  validateSitemapInventory,
} from "../src/lib/sitemap-entries";

test("buildSitemapEntityPages emits canonical slug plus stable id URLs", () => {
  const { pages, skippedCount } = buildSitemapEntityPages({
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

  assert.equal(skippedCount, 0);
  assert.equal(pages.length, 1);
  assert.equal(
    pages[0].url,
    "https://reviewdisparity.com/journalists/kira-laib--386b4f96fd55433584965a34e195a07a",
  );
  assert.equal(pages[0].lastModified, "2026-07-21T08:30:00.000Z");
});

test("buildSitemapEntityPages skips entries that would produce redirecting placeholder URLs", () => {
  const { pages, skippedCount } = buildSitemapEntityPages({
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

  assert.equal(skippedCount, 3);
  assert.deepEqual(
    pages.map((page) => page.url),
    ["https://reviewdisparity.com/games/high-guard--game-1"],
  );
  assert.ok(pages.every((page) => /--[^/]+$/.test(new URL(page.url).pathname)));
});

test("buildSitemapEntityPages reports invalid lastmod without dropping the canonical URL", () => {
  const { pages, invalidLastModifiedCount } = buildSitemapEntityPages({
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

  assert.equal(pages.length, 1);
  assert.equal(pages[0].lastModified, undefined);
  assert.equal(invalidLastModifiedCount, 1);
});

test("validateSitemapInventory rejects count collapses and duplicate canonicals", () => {
  assert.throws(
    () => validateSitemapInventory({ pages: [], minimumCount: 1, label: "games" }),
    /below safety floor/,
  );
  assert.throws(
    () =>
      validateSitemapInventory({
        pages: [
          { url: "https://reviewdisparity.com/games/a--1" },
          { url: "https://reviewdisparity.com/games/a--1" },
        ],
        minimumCount: 1,
        label: "games",
      }),
    /duplicate canonical URLs/,
  );
});

test("static sitemap includes indexable news and excludes noindex search", () => {
  const urls = buildStaticSitemapPages("https://reviewdisparity.com").map(
    (page) => page.url,
  );

  assert.ok(urls.includes("https://reviewdisparity.com/news"));
  assert.ok(!urls.includes("https://reviewdisparity.com/search"));
});
