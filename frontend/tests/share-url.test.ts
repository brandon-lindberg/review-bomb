import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import {
  buildCompareShareParams,
  buildCompareShareUrl,
  buildEntitySnapshotShareUrl,
  buildRedditShareUrl,
  buildSnapshotShareParams,
  buildXIntentUrl,
  withSnapshotNonce,
} from "../src/lib/share-url";

test("buildSnapshotShareParams includes expected base metrics", () => {
  const params = buildSnapshotShareParams({
    card: "g15",
    version: "119-89.79-96.27-95.00--5.85",
    critic: 89.79,
    steam: 96.27,
    metacritic: 95,
    disparity: -5.85,
  });

  assert.equal(params.get("card"), "g15");
  assert.equal(params.get("v"), "119-89.79-96.27-95.00--5.85");
  assert.equal(params.get("critic"), "89.79");
  assert.equal(params.get("steam"), "96.27");
  assert.equal(params.get("mc"), "95.00");
  assert.equal(params.get("disp"), "-5.85");
  assert.equal(params.get("mode"), null);
});

test("buildSnapshotShareParams includes chart trend payload and nonce", () => {
  const params = buildSnapshotShareParams({
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

  assert.equal(params.get("mode"), "chart");
  assert.equal(params.get("t"), "7.5,15.0");
  assert.equal(params.get("sx"), "abcdefghijklmnopqrstuvwx");
});

test("buildSnapshotShareParams includes timing counts, including zeros", () => {
  const params = buildSnapshotShareParams({
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

  assert.equal(params.get("mode"), "timing");
  assert.equal(params.get("early"), "0");
  assert.equal(params.get("launch"), "2");
  assert.equal(params.get("late"), "0");
});

test("entity snapshot share url updates when ingested metrics change", () => {
  const siteUrl = "https://reviewdisparity.com";
  const baseInput = {
    card: "g15",
    version: "old-v",
    critic: 80,
    steam: 70,
    metacritic: 60,
    disparity: 15,
  } as const;

  const first = buildEntitySnapshotShareUrl(siteUrl, "games", "Game One", "game-1", baseInput);
  const second = buildEntitySnapshotShareUrl(siteUrl, "games", "Game One", "game-1", {
    ...baseInput,
    version: "new-v",
    critic: 81,
    disparity: 14,
  });

  const expectedSecond = buildEntitySnapshotShareUrl(siteUrl, "games", "Game One", "game-1", {
    ...baseInput,
    version: "new-v",
    critic: 81,
    disparity: 14,
  });

  assert.notEqual(first, second);
  assert.equal(second, expectedSecond);

  const firstParams = new URL(first).searchParams;
  const secondParams = new URL(second).searchParams;
  assert.equal(new URL(first).pathname, "/games/game-one--game-1");
  assert.equal(firstParams.get("v"), "old-v");
  assert.equal(secondParams.get("v"), "new-v");
  assert.equal(firstParams.get("critic"), "80.00");
  assert.equal(secondParams.get("critic"), "81.00");
  assert.equal(firstParams.get("disp"), "15.00");
  assert.equal(secondParams.get("disp"), "14.00");
});

test("entity snapshot share builder supports game, journalist, and outlet pages", () => {
  const siteUrl = "https://reviewdisparity.com";
  const entities = [
    { type: "games" as const, id: "game-1" },
    { type: "journalists" as const, id: "journalist-1" },
    { type: "outlets" as const, id: "outlet-1" },
  ];

  for (const entity of entities) {
    const url = buildEntitySnapshotShareUrl(siteUrl, entity.type, entity.id.replace(/-/g, " "), entity.id, {
      card: "x1",
      version: "v1",
      critic: 80,
      steam: null,
      metacritic: 72,
      disparity: 8,
    });
    const parsed = new URL(url);
    assert.match(parsed.pathname, new RegExp(`^/${entity.type}/.+--${entity.id}$`));
    assert.equal(parsed.searchParams.get("card"), "x1");
    assert.equal(parsed.searchParams.get("steam"), "na");
    assert.equal(parsed.searchParams.get("mc"), "72.00");
  }
});

test("buildCompareShareUrl serializes ids, labels, and snapshot payload", () => {
  const url = buildCompareShareUrl("https://reviewdisparity.com", {
    type: "games",
    card: "v5",
    ids: [1, 2, 3],
    labels: ["A", "B", "C"],
    snapshotPayload: '[{"n":"A","c":80}]',
  });
  const params = new URL(url).searchParams;

  assert.equal(params.get("type"), "games");
  assert.equal(params.get("card"), "v5");
  assert.equal(params.get("ids"), "1,2,3");
  assert.equal(params.get("labels"), "A|B|C");
  assert.equal(params.get("snap"), '[{"n":"A","c":80}]');
});

test("buildCompareShareParams omits empty optional values", () => {
  const params = buildCompareShareParams({
    type: "journalists",
    card: "v5",
    ids: [],
    labels: [],
    snapshotPayload: "   ",
  });

  assert.equal(params.get("type"), "journalists");
  assert.equal(params.get("card"), "v5");
  assert.equal(params.get("ids"), null);
  assert.equal(params.get("labels"), null);
  assert.equal(params.get("snap"), null);
});

test("reddit and X share builders create expected intent urls", () => {
  const baseUrl = "https://reviewdisparity.com/games/game-1?card=g15&v=1";
  const text = "Game snapshot";
  const nonce = "abc123";

  const reddit = buildRedditShareUrl(baseUrl, text, nonce);
  const redditParams = new URL(reddit).searchParams;
  assert.equal(new URL(redditParams.get("url") ?? "").searchParams.get("sx"), nonce);
  assert.equal(redditParams.get("title"), text);

  const urlWithNonce = withSnapshotNonce(baseUrl, nonce);
  assert.equal(new URL(urlWithNonce).searchParams.get("sx"), nonce);
  assert.equal(new URL(urlWithNonce).searchParams.get("v"), "1");

  const xIntent = buildXIntentUrl(baseUrl, text, nonce);
  const xParams = new URL(xIntent).searchParams;
  assert.equal(xParams.get("text"), text);
  assert.equal(new URL(xParams.get("url") ?? "").searchParams.get("sx"), nonce);
});

test("share surfaces use the centralized share-url builders", () => {
  const root = process.cwd();
  const expectations: Array<{ file: string; snippets: string[] }> = [
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
    const text = readFileSync(join(root, expectation.file), "utf8");
    for (const snippet of expectation.snippets) {
      assert.match(
        text,
        new RegExp(snippet.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
        `${expectation.file} should include ${snippet}`
      );
    }
  }
});

test("entity link surfaces use the shared path helper", () => {
  const root = process.cwd();
  const expectations: Array<{ file: string; snippets: string[] }> = [
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
    const text = readFileSync(join(root, expectation.file), "utf8");
    for (const snippet of expectation.snippets) {
      assert.match(
        text,
        new RegExp(snippet.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
        `${expectation.file} should include ${snippet}`
      );
    }
  }
});
