import assert from "node:assert/strict";
import test from "node:test";

import {
  fetchWithRetry,
  isTransientStatus,
  parseJsonLdNodes,
  validateDatasetFreshness,
  validateSitemapSource,
} from "./seo-monitor-policy.mjs";

test("fresh sitemap policy accepts expected production sources", () => {
  assert.equal(
    validateSitemapSource("/sitemaps/static.xml", "static", true),
    null,
  );
  assert.equal(
    validateSitemapSource("/sitemaps/games.xml", "fresh", true),
    null,
  );
});

test("fresh sitemap policy rejects fallbacks and missing source headers", () => {
  assert.match(
    validateSitemapSource(
      "/sitemaps/games.xml",
      "last-known-good",
      true,
    ),
    /expected X-Sitemap-Source=fresh/,
  );
  assert.match(
    validateSitemapSource("/sitemaps/outlets.xml", null, true),
    /missing X-Sitemap-Source/,
  );
});

test("fresh sitemap policy can be disabled for local smoke tests", () => {
  assert.equal(
    validateSitemapSource(
      "/sitemaps/games.xml",
      "last-known-good",
      false,
    ),
    null,
  );
});

test("JSON-LD parser returns top-level and graph nodes", () => {
  const nodes = parseJsonLdNodes(`
    <script type="application/ld+json">
      {"@context":"https://schema.org","@graph":[
        {"@type":"Organization"},
        {"@type":"Dataset","dateModified":"2026-07-29T00:00:00Z"}
      ]}
    </script>
  `);

  assert.equal(nodes.length, 3);
  assert.equal(nodes[1]["@type"], "Organization");
  assert.equal(nodes[2]["@type"], "Dataset");
});

test("JSON-LD parser rejects invalid structured data", () => {
  assert.throws(
    () =>
      parseJsonLdNodes(
        '<script type="application/ld+json">{"@type":}</script>',
      ),
    /invalid application\/ld\+json/,
  );
});

test("dataset freshness accepts a recent dateModified", () => {
  const now = Date.parse("2026-07-29T12:00:00Z");
  const nodes = [
    { "@type": "Dataset", dateModified: "2026-07-29T00:30:00Z" },
  ];
  assert.equal(validateDatasetFreshness(nodes, 24, now), null);
});

test("dataset freshness rejects missing, invalid, stale, and future data", () => {
  const now = Date.parse("2026-07-29T12:00:00Z");

  assert.match(validateDatasetFreshness([], 24, now), /missing Dataset/);
  assert.match(
    validateDatasetFreshness([{ "@type": "Dataset" }], 24, now),
    /missing or invalid dateModified/,
  );
  assert.match(
    validateDatasetFreshness(
      [{ "@type": "Dataset", dateModified: "not-a-date" }],
      24,
      now,
    ),
    /missing or invalid dateModified/,
  );
  assert.match(
    validateDatasetFreshness(
      [{ "@type": "Dataset", dateModified: "2026-07-28T10:59:00Z" }],
      24,
      now,
    ),
    /25\.0 hours old/,
  );
  assert.match(
    validateDatasetFreshness(
      [{ "@type": "Dataset", dateModified: "2026-07-29T13:01:00Z" }],
      24,
      now,
    ),
    /more than 1 hour in the future/,
  );
});

test("dataset freshness policy can be disabled", () => {
  assert.equal(validateDatasetFreshness([], 0), null);
});

test("transient status policy retries only server-side failures", () => {
  assert.equal(isTransientStatus(503), true);
  assert.equal(isTransientStatus(500), true);
  assert.equal(isTransientStatus(502), true);
  assert.equal(isTransientStatus(200), false);
  assert.equal(isTransientStatus(308), false);
  assert.equal(isTransientStatus(404), false);
});

test("fetchWithRetry retries a 503 and returns the eventual success", async () => {
  const statuses = [503, 200];
  let calls = 0;
  const response = await fetchWithRetry(
    async () => {
      calls += 1;
      return { status: statuses.shift() };
    },
    { delayImpl: async () => {} },
  );

  assert.equal(calls, 2);
  assert.equal(response.status, 200);
});

test("fetchWithRetry retries a thrown network error", async () => {
  let calls = 0;
  const response = await fetchWithRetry(
    async () => {
      calls += 1;
      if (calls < 3) throw new TypeError("network failure");
      return { status: 200 };
    },
    { delayImpl: async () => {} },
  );

  assert.equal(calls, 3);
  assert.equal(response.status, 200);
});

test("fetchWithRetry does not retry a definitive response", async () => {
  let calls = 0;
  const response = await fetchWithRetry(
    async () => {
      calls += 1;
      return { status: 404 };
    },
    { delayImpl: async () => {} },
  );

  assert.equal(calls, 1);
  assert.equal(response.status, 404);
});

test("fetchWithRetry surfaces the last failure once the budget is spent", async () => {
  let calls = 0;
  const response = await fetchWithRetry(
    async () => {
      calls += 1;
      return { status: 503 };
    },
    { attempts: 2, delayImpl: async () => {} },
  );

  assert.equal(calls, 2);
  assert.equal(response.status, 503);
});

test("fetchWithRetry rethrows when every attempt throws", async () => {
  await assert.rejects(
    fetchWithRetry(
      async () => {
        throw new TypeError("network failure");
      },
      { attempts: 2, delayImpl: async () => {} },
    ),
    /network failure/,
  );
});
