import assert from "node:assert/strict";
import test from "node:test";
import { shouldIndexEntityPage } from "../src/lib/index-eligibility";

test("eligible canonical entity pages remain indexable", () => {
  assert.equal(
    shouldIndexEntityPage({
      indexEligible: true,
      isShareVariant: false,
      page: 1,
    }),
    true,
  );
});

test("thin entities remain followable but are not indexable", () => {
  assert.equal(shouldIndexEntityPage({ indexEligible: false }), false);
  assert.equal(shouldIndexEntityPage({ indexEligible: undefined }), false);
});

test("share variants and paginated detail views are not indexable", () => {
  assert.equal(
    shouldIndexEntityPage({ indexEligible: true, isShareVariant: true }),
    false,
  );
  assert.equal(
    shouldIndexEntityPage({ indexEligible: true, page: 2 }),
    false,
  );
  assert.equal(
    shouldIndexEntityPage({ indexEligible: true, page: Number.NaN }),
    false,
  );
});
