import assert from "node:assert/strict";
import test from "node:test";
import { getIndexablePaginationPage } from "../src/lib/pagination-metadata";

test("plain ?page=N pagination of the default view is indexable", () => {
  assert.equal(getIndexablePaginationPage("2", false), 2);
  assert.equal(getIndexablePaginationPage("37", false), 37);
});

test("base page and page 1 are not treated as paginated states", () => {
  assert.equal(getIndexablePaginationPage(undefined, false), null);
  assert.equal(getIndexablePaginationPage("", false), null);
  assert.equal(getIndexablePaginationPage("1", false), null);
});

test("faceted views stay noindex even when paginated", () => {
  assert.equal(getIndexablePaginationPage("2", true), null);
});

test("junk page values are rejected", () => {
  assert.equal(getIndexablePaginationPage("0", false), null);
  assert.equal(getIndexablePaginationPage("-3", false), null);
  assert.equal(getIndexablePaginationPage("2abc", false), null);
  assert.equal(getIndexablePaginationPage("abc", false), null);
  assert.equal(getIndexablePaginationPage("2.5", false), null);
  assert.equal(getIndexablePaginationPage("999999999999999999999", false), null);
});
