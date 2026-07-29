const JSON_LD_SCRIPT_RE =
  /<script\b[^>]*type\s*=\s*(?:"application\/ld\+json"|'application\/ld\+json')[^>]*>([\s\S]*?)<\/script>/gi;

function hasType(node, expectedType) {
  const types = Array.isArray(node?.["@type"])
    ? node["@type"]
    : [node?.["@type"]];
  return types.includes(expectedType);
}

export function validateSitemapSource(path, source, requireFresh) {
  if (!requireFresh) return null;

  const expected = path === "/sitemaps/static.xml" ? "static" : "fresh";
  if (!source) {
    return `${path}: missing X-Sitemap-Source header (expected ${expected})`;
  }
  if (source !== expected) {
    return `${path}: expected X-Sitemap-Source=${expected}, got ${source}`;
  }
  return null;
}

export function parseJsonLdNodes(html) {
  const nodes = [];

  for (const match of html.matchAll(JSON_LD_SCRIPT_RE)) {
    let parsed;
    try {
      parsed = JSON.parse(match[1]);
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      throw new Error(`invalid application/ld+json: ${detail}`);
    }

    const values = Array.isArray(parsed) ? parsed : [parsed];
    for (const value of values) {
      if (!value || typeof value !== "object") continue;
      nodes.push(value);
      if (Array.isArray(value["@graph"])) {
        nodes.push(
          ...value["@graph"].filter(
            (node) => node && typeof node === "object",
          ),
        );
      }
    }
  }

  return nodes;
}

export function validateDatasetFreshness(
  nodes,
  maxAgeHours,
  nowMs = Date.now(),
) {
  if (!(maxAgeHours > 0)) return null;

  const dataset = nodes.find((node) => hasType(node, "Dataset"));
  if (!dataset) {
    return "GEO knowledge graph: missing Dataset node";
  }

  const modified = dataset.dateModified;
  const modifiedMs =
    typeof modified === "string" || typeof modified === "number"
      ? new Date(modified).getTime()
      : Number.NaN;
  if (!Number.isFinite(modifiedMs)) {
    return "GEO Dataset: missing or invalid dateModified";
  }

  const futureToleranceMs = 60 * 60 * 1000;
  if (modifiedMs > nowMs + futureToleranceMs) {
    return `GEO Dataset: dateModified is more than 1 hour in the future (${new Date(modifiedMs).toISOString()})`;
  }

  const ageHours = (nowMs - modifiedMs) / (60 * 60 * 1000);
  if (ageHours > maxAgeHours) {
    return `GEO Dataset: dateModified is ${ageHours.toFixed(1)} hours old (limit ${maxAgeHours} hours)`;
  }
  return null;
}
