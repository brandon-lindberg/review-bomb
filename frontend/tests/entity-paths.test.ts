import assert from "node:assert/strict";
import test from "node:test";
import {
  buildEntityPath,
  buildPathWithQuery,
  normalizeEntityRouteSegment,
  parseEntityRouteSegment,
  slugifyEntityLabel,
} from "../src/lib/entity-paths";

test("slugifyEntityLabel builds lowercase hyphenated slugs", () => {
  assert.equal(slugifyEntityLabel("High Guard"), "high-guard");
  assert.equal(slugifyEntityLabel("Joe's Terrible Review"), "joes-terrible-review");
  assert.equal(slugifyEntityLabel("  IGN   &  Friends "), "ign-and-friends");
});

test("buildEntityPath produces slug plus stable id canonicals", () => {
  assert.equal(
    buildEntityPath("games", "High Guard", "abc123"),
    "/games/high-guard--abc123",
  );
  assert.equal(
    buildEntityPath(
      "games",
      "Pokémon FireRed Version and Pokémon LeafGreen Version",
      "poke123",
    ),
    "/games/pokémon-firered-version-and-pokémon-leafgreen-version--poke123",
  );
  assert.equal(
    buildEntityPath("journalists", "Joe Terrible", "crit42"),
    "/journalists/joe-terrible--crit42",
  );
});

test("parseEntityRouteSegment handles canonical, bare id, and numeric legacy routes", () => {
  assert.deepEqual(parseEntityRouteSegment("high-guard--abc123"), {
    identifier: "abc123",
    slug: "high-guard",
    isSlugged: true,
  });
  assert.deepEqual(parseEntityRouteSegment("abc123"), {
    identifier: "abc123",
    slug: null,
    isSlugged: false,
  });
  assert.deepEqual(parseEntityRouteSegment("18971"), {
    identifier: "18971",
    slug: null,
    isSlugged: false,
  });
  assert.deepEqual(
    parseEntityRouteSegment(
      "pok%C3%A9mon-firered-version-and-pok%C3%A9mon-leafgreen-version--abc123",
    ),
    {
      identifier: "abc123",
      slug: "pokémon-firered-version-and-pokémon-leafgreen-version",
      isSlugged: true,
    },
  );
});

test("normalizeEntityRouteSegment decodes percent-encoded slugs for canonical comparisons", () => {
  assert.equal(
    normalizeEntityRouteSegment(
      "pok%C3%A9mon-firered-version-and-pok%C3%A9mon-leafgreen-version--abc123",
    ),
    "pokémon-firered-version-and-pokémon-leafgreen-version--abc123",
  );
});

test("stale slugs can be rebuilt into the current canonical segment", () => {
  const parsed = parseEntityRouteSegment("old-title--abc123");

  assert.equal(parsed.identifier, "abc123");
  assert.equal(
    buildEntityPath("games", "New Title", parsed.identifier),
    "/games/new-title--abc123",
  );
});

test("buildPathWithQuery preserves snapshot/share parameters on redirect targets", () => {
  assert.equal(
    buildPathWithQuery("/games/high-guard--abc123", {
      card: "g15",
      mode: "chart",
      sx: "nonce42",
    }),
    "/games/high-guard--abc123?card=g15&mode=chart&sx=nonce42",
  );
});
