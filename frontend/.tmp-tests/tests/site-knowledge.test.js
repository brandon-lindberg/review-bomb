"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const site_knowledge_1 = require("../src/lib/site-knowledge");
const SITE_URL = "https://reviewdisparity.com";
(0, node_test_1.default)("site graph gives the publisher and website stable, connected identifiers", () => {
    const ids = (0, site_knowledge_1.siteKnowledgeIds)(`${SITE_URL}/`);
    const graph = (0, site_knowledge_1.buildSiteKnowledgeGraph)(`${SITE_URL}/`);
    const serialized = JSON.stringify(graph);
    strict_1.default.equal(ids.organization, `${SITE_URL}/#organization`);
    strict_1.default.equal(ids.website, `${SITE_URL}/#website`);
    strict_1.default.match(serialized, /"@id":"https:\/\/reviewdisparity\.com\/#organization"/);
    strict_1.default.match(serialized, /"@id":"https:\/\/reviewdisparity\.com\/#website"/);
    strict_1.default.match(serialized, /"publisher":\{"@id":"https:\/\/reviewdisparity\.com\/#organization"\}/);
    strict_1.default.match(serialized, /"publishingPrinciples":"https:\/\/reviewdisparity\.com\/about#editorial-principles"/);
});
(0, node_test_1.default)("dataset graph includes provenance, variables, access, terms, and freshness", () => {
    const dataset = (0, site_knowledge_1.buildDatasetJsonLd)(SITE_URL, {
        total_games: 10,
        total_journalists: 20,
        total_outlets: 3,
        total_reviews: 100,
        avg_disparity_site: 2.5,
        last_updated: "2026-07-29T12:00:00Z",
    });
    const serialized = JSON.stringify(dataset);
    strict_1.default.equal(dataset["@type"], "Dataset");
    strict_1.default.equal(dataset.isAccessibleForFree, true);
    strict_1.default.equal(dataset.license, `${SITE_URL}/terms`);
    strict_1.default.equal(dataset.dateModified, "2026-07-29T12:00:00Z");
    strict_1.default.deepEqual(dataset.isBasedOn, site_knowledge_1.REVIEW_DATA_SOURCES.map((source) => source.url));
    strict_1.default.match(serialized, /"variableMeasured"/);
    strict_1.default.match(serialized, /Review disparity/);
    strict_1.default.match(serialized, /"creator":\{"@id":"https:\/\/reviewdisparity\.com\/#organization"\}/);
});
(0, node_test_1.default)("homepage, About, and FAQ reference the same publisher and dataset entities", () => {
    const homepage = (0, site_knowledge_1.buildHomePageJsonLd)(SITE_URL);
    const about = (0, site_knowledge_1.buildAboutKnowledgeGraph)(SITE_URL, null);
    const faq = (0, site_knowledge_1.buildFaqPageJsonLd)(SITE_URL, [
        { question: "What is disparity?", answer: "Critic score minus user score." },
    ]);
    const combined = JSON.stringify([homepage, about, faq]);
    strict_1.default.equal(homepage["@id"], `${SITE_URL}/#webpage`);
    strict_1.default.equal(faq["@id"], `${SITE_URL}/faq#webpage`);
    strict_1.default.match(combined, /https:\/\/reviewdisparity\.com\/about#dataset/);
    strict_1.default.match(combined, /https:\/\/reviewdisparity\.com\/#organization/);
    strict_1.default.match(combined, /https:\/\/reviewdisparity\.com\/#website/);
    strict_1.default.match(combined, /"@type":"Question"/);
});
