"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const entity_paths_1 = require("../src/lib/entity-paths");
(0, node_test_1.default)("slugifyEntityLabel builds lowercase hyphenated slugs", () => {
    strict_1.default.equal((0, entity_paths_1.slugifyEntityLabel)("High Guard"), "high-guard");
    strict_1.default.equal((0, entity_paths_1.slugifyEntityLabel)("Joe's Terrible Review"), "joes-terrible-review");
    strict_1.default.equal((0, entity_paths_1.slugifyEntityLabel)("  IGN   &  Friends "), "ign-and-friends");
});
(0, node_test_1.default)("buildEntityPath produces slug plus stable id canonicals", () => {
    strict_1.default.equal((0, entity_paths_1.buildEntityPath)("games", "High Guard", "abc123"), "/games/high-guard--abc123");
    strict_1.default.equal((0, entity_paths_1.buildEntityPath)("journalists", "Joe Terrible", "crit42"), "/journalists/joe-terrible--crit42");
});
(0, node_test_1.default)("parseEntityRouteSegment handles canonical, bare id, and numeric legacy routes", () => {
    strict_1.default.deepEqual((0, entity_paths_1.parseEntityRouteSegment)("high-guard--abc123"), {
        identifier: "abc123",
        slug: "high-guard",
        isSlugged: true,
    });
    strict_1.default.deepEqual((0, entity_paths_1.parseEntityRouteSegment)("abc123"), {
        identifier: "abc123",
        slug: null,
        isSlugged: false,
    });
    strict_1.default.deepEqual((0, entity_paths_1.parseEntityRouteSegment)("18971"), {
        identifier: "18971",
        slug: null,
        isSlugged: false,
    });
});
(0, node_test_1.default)("stale slugs can be rebuilt into the current canonical segment", () => {
    const parsed = (0, entity_paths_1.parseEntityRouteSegment)("old-title--abc123");
    strict_1.default.equal(parsed.identifier, "abc123");
    strict_1.default.equal((0, entity_paths_1.buildEntityPath)("games", "New Title", parsed.identifier), "/games/new-title--abc123");
});
(0, node_test_1.default)("buildPathWithQuery preserves snapshot/share parameters on redirect targets", () => {
    strict_1.default.equal((0, entity_paths_1.buildPathWithQuery)("/games/high-guard--abc123", {
        card: "g15",
        mode: "chart",
        sx: "nonce42",
    }), "/games/high-guard--abc123?card=g15&mode=chart&sx=nonce42");
});
