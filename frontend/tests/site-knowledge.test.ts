import assert from "node:assert/strict";
import test from "node:test";
import {
  buildAboutKnowledgeGraph,
  buildDatasetJsonLd,
  buildFaqPageJsonLd,
  buildHomePageJsonLd,
  buildSiteKnowledgeGraph,
  REVIEW_DATA_SOURCES,
  siteKnowledgeIds,
} from "../src/lib/site-knowledge";

const SITE_URL = "https://reviewdisparity.com";

test("site graph gives the publisher and website stable, connected identifiers", () => {
  const ids = siteKnowledgeIds(`${SITE_URL}/`);
  const graph = buildSiteKnowledgeGraph(`${SITE_URL}/`);
  const serialized = JSON.stringify(graph);

  assert.equal(ids.organization, `${SITE_URL}/#organization`);
  assert.equal(ids.website, `${SITE_URL}/#website`);
  assert.match(serialized, /"@id":"https:\/\/reviewdisparity\.com\/#organization"/);
  assert.match(serialized, /"@id":"https:\/\/reviewdisparity\.com\/#website"/);
  assert.match(serialized, /"publisher":\{"@id":"https:\/\/reviewdisparity\.com\/#organization"\}/);
  assert.match(serialized, /"publishingPrinciples":"https:\/\/reviewdisparity\.com\/about#editorial-principles"/);
});

test("dataset graph includes provenance, variables, access, terms, and freshness", () => {
  const dataset = buildDatasetJsonLd(SITE_URL, {
    total_games: 10,
    total_journalists: 20,
    total_outlets: 3,
    total_reviews: 100,
    avg_disparity_site: 2.5,
    last_updated: "2026-07-29T12:00:00Z",
  });
  const serialized = JSON.stringify(dataset);

  assert.equal(dataset["@type"], "Dataset");
  assert.equal(dataset.isAccessibleForFree, true);
  assert.equal(dataset.license, `${SITE_URL}/terms`);
  assert.equal(dataset.dateModified, "2026-07-29T12:00:00Z");
  assert.deepEqual(
    dataset.isBasedOn,
    REVIEW_DATA_SOURCES.map((source) => source.url),
  );
  assert.match(serialized, /"variableMeasured"/);
  assert.match(serialized, /Review disparity/);
  assert.match(serialized, /"creator":\{"@id":"https:\/\/reviewdisparity\.com\/#organization"\}/);
});

test("homepage, About, and FAQ reference the same publisher and dataset entities", () => {
  const homepage = buildHomePageJsonLd(SITE_URL);
  const about = buildAboutKnowledgeGraph(SITE_URL, null);
  const faq = buildFaqPageJsonLd(SITE_URL, [
    { question: "What is disparity?", answer: "Critic score minus user score." },
  ]);
  const combined = JSON.stringify([homepage, about, faq]);

  assert.equal(homepage["@id"], `${SITE_URL}/#webpage`);
  assert.equal(faq["@id"], `${SITE_URL}/faq#webpage`);
  assert.match(combined, /https:\/\/reviewdisparity\.com\/about#dataset/);
  assert.match(combined, /https:\/\/reviewdisparity\.com\/#organization/);
  assert.match(combined, /https:\/\/reviewdisparity\.com\/#website/);
  assert.match(combined, /"@type":"Question"/);
});
