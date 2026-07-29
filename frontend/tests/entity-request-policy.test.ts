import assert from "node:assert/strict";
import test from "node:test";
import { resolveEntityRequest } from "../src/lib/entity-request-policy";

const API_URL = "https://api.example.test/api/v1";

function jsonResponse(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("entity request policy resolves canonical and legacy URLs from stable IDs", async () => {
  let requestedUrl = "";
  const fetchImpl: typeof fetch = async (input) => {
    requestedUrl = String(input);
    return jsonResponse(200, {
      public_id: "abc123",
      title: "Current Game Title",
    });
  };

  const result = await resolveEntityRequest({
    apiUrl: API_URL,
    entityType: "games",
    entitySegment: "old-title--abc123",
    fetchImpl,
  });

  assert.equal(requestedUrl, `${API_URL}/games/abc123`);
  assert.deepEqual(result, {
    kind: "found",
    canonicalPath: "/games/current-game-title--abc123",
  });
});

test("entity request policy preserves confirmed API 404s", async () => {
  const result = await resolveEntityRequest({
    apiUrl: API_URL,
    entityType: "outlets",
    entitySegment: "missing--deadbeef",
    fetchImpl: async () => jsonResponse(404, { detail: "Not found" }),
  });

  assert.deepEqual(result, { kind: "not_found" });
});

test("entity request policy treats upstream errors as temporary unavailability", async () => {
  for (const fetchImpl of [
    async () => jsonResponse(500, { detail: "Database unavailable" }),
    async () => {
      throw new TypeError("network failure");
    },
  ]) {
    const result = await resolveEntityRequest({
      apiUrl: API_URL,
      entityType: "journalists",
      entitySegment: "abc123",
      fetchImpl,
    });

    assert.deepEqual(result, { kind: "unavailable" });
  }
});

test("entity request policy rejects malformed success payloads", async () => {
  const result = await resolveEntityRequest({
    apiUrl: API_URL,
    entityType: "games",
    entitySegment: "abc123",
    fetchImpl: async () => jsonResponse(200, { public_id: "abc123" }),
  });

  assert.deepEqual(result, { kind: "unavailable" });
});
