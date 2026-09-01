"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const entity_request_policy_1 = require("../src/lib/entity-request-policy");
const API_URL = "https://api.example.test/api/v1";
function jsonResponse(status, body) {
    return new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });
}
(0, node_test_1.default)("entity request policy resolves canonical and legacy URLs from stable IDs", async () => {
    let requestedUrl = "";
    const fetchImpl = async (input) => {
        requestedUrl = String(input);
        return jsonResponse(200, {
            public_id: "abc123",
            title: "Current Game Title",
        });
    };
    const result = await (0, entity_request_policy_1.resolveEntityRequest)({
        apiUrl: API_URL,
        entityType: "games",
        entitySegment: "old-title--abc123",
        fetchImpl,
    });
    strict_1.default.equal(requestedUrl, `${API_URL}/games/abc123`);
    strict_1.default.deepEqual(result, {
        kind: "found",
        canonicalPath: "/games/current-game-title--abc123",
    });
});
(0, node_test_1.default)("entity request policy preserves confirmed API 404s", async () => {
    const result = await (0, entity_request_policy_1.resolveEntityRequest)({
        apiUrl: API_URL,
        entityType: "outlets",
        entitySegment: "missing--deadbeef",
        fetchImpl: async () => jsonResponse(404, { detail: "Not found" }),
    });
    strict_1.default.deepEqual(result, { kind: "not_found" });
});
(0, node_test_1.default)("entity request policy treats upstream errors as temporary unavailability", async () => {
    for (const fetchImpl of [
        async () => jsonResponse(500, { detail: "Database unavailable" }),
        async () => {
            throw new TypeError("network failure");
        },
    ]) {
        const result = await (0, entity_request_policy_1.resolveEntityRequest)({
            apiUrl: API_URL,
            entityType: "journalists",
            entitySegment: "abc123",
            fetchImpl,
        });
        strict_1.default.deepEqual(result, { kind: "unavailable" });
    }
});
(0, node_test_1.default)("entity request policy rejects malformed success payloads", async () => {
    const result = await (0, entity_request_policy_1.resolveEntityRequest)({
        apiUrl: API_URL,
        entityType: "games",
        entitySegment: "abc123",
        fetchImpl: async () => jsonResponse(200, { public_id: "abc123" }),
    });
    strict_1.default.deepEqual(result, { kind: "unavailable" });
});
(0, node_test_1.default)("entity request policy retries a transient upstream failure before giving up", async () => {
    const statuses = [503, 500];
    let calls = 0;
    const fetchImpl = async () => {
        calls += 1;
        const status = statuses.shift();
        if (status)
            return jsonResponse(status, { detail: "upstream busy" });
        return jsonResponse(200, { public_id: "abc123", name: "Eurogamer" });
    };
    const result = await (0, entity_request_policy_1.resolveEntityRequest)({
        apiUrl: API_URL,
        entityType: "outlets",
        entitySegment: "eurogamer--abc123",
        fetchImpl,
        delayImpl: async () => { },
    });
    strict_1.default.equal(calls, 3);
    strict_1.default.deepEqual(result, {
        kind: "found",
        canonicalPath: "/outlets/eurogamer--abc123",
    });
});
(0, node_test_1.default)("entity request policy retries a dropped connection", async () => {
    let calls = 0;
    const fetchImpl = async () => {
        calls += 1;
        if (calls === 1)
            throw new TypeError("network failure");
        return jsonResponse(200, { public_id: "abc123", name: "IGN" });
    };
    const result = await (0, entity_request_policy_1.resolveEntityRequest)({
        apiUrl: API_URL,
        entityType: "outlets",
        entitySegment: "ign--abc123",
        fetchImpl,
        delayImpl: async () => { },
    });
    strict_1.default.equal(calls, 2);
    strict_1.default.equal(result.kind, "found");
});
(0, node_test_1.default)("entity request policy never retries a definitive 404", async () => {
    let calls = 0;
    const result = await (0, entity_request_policy_1.resolveEntityRequest)({
        apiUrl: API_URL,
        entityType: "games",
        entitySegment: "missing--abc123",
        fetchImpl: async () => {
            calls += 1;
            return jsonResponse(404, { detail: "Not found" });
        },
        delayImpl: async () => { },
    });
    strict_1.default.equal(calls, 1);
    strict_1.default.deepEqual(result, { kind: "not_found" });
});
(0, node_test_1.default)("entity request policy gives up after the attempt budget", async () => {
    let calls = 0;
    const result = await (0, entity_request_policy_1.resolveEntityRequest)({
        apiUrl: API_URL,
        entityType: "journalists",
        entitySegment: "abc123",
        fetchImpl: async () => {
            calls += 1;
            return jsonResponse(503, { detail: "upstream busy" });
        },
        attempts: 2,
        delayImpl: async () => { },
    });
    strict_1.default.equal(calls, 2);
    strict_1.default.deepEqual(result, { kind: "unavailable" });
});
(0, node_test_1.default)("entity request policy stops retrying once the caller's budget is spent", async () => {
    const controller = new AbortController();
    let calls = 0;
    const result = await (0, entity_request_policy_1.resolveEntityRequest)({
        apiUrl: API_URL,
        entityType: "outlets",
        entitySegment: "abc123",
        fetchImpl: async () => {
            calls += 1;
            controller.abort();
            return jsonResponse(503, { detail: "upstream busy" });
        },
        signal: controller.signal,
        delayImpl: async () => { },
    });
    strict_1.default.equal(calls, 1);
    strict_1.default.deepEqual(result, { kind: "unavailable" });
});
