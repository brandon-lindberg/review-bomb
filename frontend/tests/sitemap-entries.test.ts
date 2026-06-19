import assert from "node:assert/strict";
import test from "node:test";
import { buildSitemapEntityPages } from "../src/lib/sitemap-entries";

test("buildSitemapEntityPages emits canonical slug plus stable id URLs", () => {
  const { pages, skippedCount } = buildSitemapEntityPages({
    siteUrl: "https://reviewdisparity.com",
    entityType: "journalists",
    labelKey: "name",
    entries: [
      {
        public_id: "386b4f96fd55433584965a34e195a07a",
        name: "Kira Laib",
      },
    ],
  });

  assert.equal(skippedCount, 0);
  assert.equal(pages.length, 1);
  assert.equal(
    pages[0].url,
    "https://reviewdisparity.com/journalists/kira-laib--386b4f96fd55433584965a34e195a07a",
  );
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
