import http from "node:http";

const BASE_URL = process.env.SEO_BASE_URL || "http://127.0.0.1:3000";
const EXPECTED_CANONICAL_ORIGIN =
  process.env.SEO_EXPECTED_CANONICAL_ORIGIN || "https://reviewdisparity.com";

const INDEXABLE_PAGES = [
  "/",
  "/games",
  "/news",
  "/journalists",
  "/outlets",
  "/leaderboards",
  "/compare",
  "/about",
  "/privacy",
  "/terms",
  "/search",
];

const NOINDEX_PAGINATED_PAGES = [
  "/games?page=2",
  "/news?page=2",
  "/journalists?page=2",
  "/outlets?page=2",
];

const DETAIL_SAMPLES_PER_TYPE = Math.max(
  1,
  Number.parseInt(process.env.SEO_DETAIL_SAMPLES_PER_TYPE || "1", 10) || 1,
);
const REQUIRE_DETAIL_PAGES = process.env.SEO_REQUIRE_DETAIL_PAGES === "1";

function fail(message) {
  throw new Error(message);
}

function ok(condition, message) {
  if (!condition) fail(message);
}

function normalizeRobotsContent(content) {
  return (content || "")
    .toLowerCase()
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function getAttr(tag, attr) {
  const re = new RegExp(`${attr}\\s*=\\s*("([^"]*)"|'([^']*)')`, "i");
  const match = tag.match(re);
  if (!match) return null;
  return match[2] ?? match[3] ?? null;
}

function getMetaContent(html, name) {
  const metaTags = html.match(/<meta\b[^>]*>/gi) || [];
  for (const tag of metaTags) {
    const tagName = (getAttr(tag, "name") || "").toLowerCase();
    if (tagName === name.toLowerCase()) {
      return getAttr(tag, "content");
    }
  }
  return null;
}

function getCanonicalHref(html) {
  const linkTags = html.match(/<link\b[^>]*>/gi) || [];
  for (const tag of linkTags) {
    const rel = (getAttr(tag, "rel") || "").toLowerCase();
    if (rel === "canonical") {
      return getAttr(tag, "href");
    }
  }
  return null;
}

function getTitle(html) {
  const match = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  return match ? match[1].trim() : null;
}

async function fetchText(path, init = {}) {
  const url = new URL(path, BASE_URL).toString();
  const response = await fetch(url, {
    redirect: "manual",
    ...init,
  });
  const text = await response.text();
  return { response, text, url };
}

function canonicalForPath(pathWithQuery) {
  const url = new URL(pathWithQuery, EXPECTED_CANONICAL_ORIGIN);
  url.search = "";
  url.hash = "";
  return url.toString();
}

function normalizeCanonicalUrl(urlString) {
  try {
    const url = new URL(urlString, EXPECTED_CANONICAL_ORIGIN);
    url.hash = "";
    if (url.pathname !== "/" && url.pathname.endsWith("/")) {
      url.pathname = url.pathname.replace(/\/+$/, "");
    }
    return url.toString();
  } catch {
    return urlString;
  }
}

async function assertIndexablePage(path) {
  const { response, text, url } = await fetchText(path, { redirect: "follow" });
  ok(response.ok, `${path}: expected 200, got ${response.status} (${url})`);

  const title = getTitle(text);
  ok(title && title.length > 0, `${path}: missing <title>`);

  const description = getMetaContent(text, "description");
  ok(description && description.length > 0, `${path}: missing meta description`);

  const canonical = getCanonicalHref(text);
  const expectedCanonical = canonicalForPath(path);
  ok(canonical, `${path}: missing canonical link`);
  ok(
    normalizeCanonicalUrl(canonical) === normalizeCanonicalUrl(expectedCanonical),
    `${path}: canonical mismatch (expected ${expectedCanonical}, got ${canonical})`,
  );

  const robots = normalizeRobotsContent(getMetaContent(text, "robots"));
  ok(robots.includes("index"), `${path}: expected robots meta to include index`);
  ok(robots.includes("follow"), `${path}: expected robots meta to include follow`);
  ok(!robots.includes("noindex"), `${path}: should not be noindex`);
}

async function assertNoindexPage(path) {
  const { response, text, url } = await fetchText(path, { redirect: "follow" });
  ok(response.ok, `${path}: expected 200, got ${response.status} (${url})`);

  const canonical = getCanonicalHref(text);
  const expectedCanonical = canonicalForPath(path);
  ok(canonical, `${path}: missing canonical link`);
  ok(
    normalizeCanonicalUrl(canonical) === normalizeCanonicalUrl(expectedCanonical),
    `${path}: canonical mismatch (expected ${expectedCanonical}, got ${canonical})`,
  );

  const robots = normalizeRobotsContent(getMetaContent(text, "robots"));
  ok(robots.includes("noindex"), `${path}: expected robots meta to include noindex`);
  ok(robots.includes("follow"), `${path}: expected robots meta to include follow`);
}

function assertServerRenderedDetailContent(path, text) {
  ok(
    !text.includes('aria-label="Loading home page"'),
    `${path}: should not stream the global loading fallback`,
  );
  ok(
    !text.includes('aria-label="Loading detail page"'),
    `${path}: should not stream the detail loading fallback`,
  );
  ok(/<h1\b/i.test(text), `${path}: expected a server-rendered <h1>`);
}

async function assertRobotsTxt() {
  const { response, text } = await fetchText("/robots.txt", { redirect: "follow" });
  ok(response.ok, `/robots.txt: expected 200, got ${response.status}`);
  ok(
    text.includes(`Sitemap: ${EXPECTED_CANONICAL_ORIGIN}/sitemap.xml`),
    "/robots.txt: missing canonical sitemap URL",
  );
  ok(!text.includes("http://reviewdisparity.com"), "/robots.txt: should not reference http://reviewdisparity.com");
  ok(!text.includes("https://www.reviewdisparity.com"), "/robots.txt: should not reference https://www.reviewdisparity.com");
}

async function assertSitemapXml() {
  const { response, text } = await fetchText("/sitemap.xml", { redirect: "follow" });
  ok(response.ok, `/sitemap.xml: expected 200, got ${response.status}`);

  const locs = [...text.matchAll(/<loc>([^<]+)<\/loc>/gi)].map((m) => m[1].trim());
  ok(locs.length > 0, "/sitemap.xml: no <loc> entries found");

  for (const loc of locs) {
    ok(
      loc.startsWith(`${EXPECTED_CANONICAL_ORIGIN}/`) || loc === `${EXPECTED_CANONICAL_ORIGIN}/`,
      `/sitemap.xml: non-canonical URL found (${loc})`,
    );
    ok(!loc.startsWith("http://"), `/sitemap.xml: found http URL (${loc})`);
    ok(!loc.startsWith("https://www."), `/sitemap.xml: found www URL (${loc})`);
    ok(!loc.includes("?page="), `/sitemap.xml: paginated URL should not be listed (${loc})`);
  }

  return locs;
}

function requestWithHostHeader(path, { host, xForwardedProto } = {}) {
  const base = new URL(BASE_URL);
  if (base.protocol !== "http:") {
    fail(`Redirect host-header tests require http base URL, got ${BASE_URL}`);
  }

  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        protocol: base.protocol,
        hostname: base.hostname,
        port: base.port,
        path,
        method: "GET",
        headers: {
          host,
          ...(xForwardedProto ? { "x-forwarded-proto": xForwardedProto } : {}),
        },
      },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          resolve({
            status: res.statusCode ?? 0,
            headers: res.headers,
            body: Buffer.concat(chunks).toString("utf8"),
          });
        });
      },
    );
    req.on("error", reject);
    req.end();
  });
}

async function assertCanonicalRedirectsViaHostHeader() {
  const cases = [
    {
      label: "https://www -> https://canonical",
      host: "www.reviewdisparity.com",
      xForwardedProto: "https",
      path: "/",
      expectedLocation: `${EXPECTED_CANONICAL_ORIGIN}/`,
    },
    {
      label: "http://canonical -> https://canonical",
      host: "reviewdisparity.com",
      xForwardedProto: "http",
      path: "/",
      expectedLocation: `${EXPECTED_CANONICAL_ORIGIN}/`,
    },
    {
      label: "http://www -> https://canonical",
      host: "www.reviewdisparity.com",
      xForwardedProto: "http",
      path: "/",
      expectedLocation: `${EXPECTED_CANONICAL_ORIGIN}/`,
    },
  ];

  for (const c of cases) {
    const res = await requestWithHostHeader(c.path, {
      host: c.host,
      xForwardedProto: c.xForwardedProto,
    });
    ok(
      [301, 308].includes(res.status),
      `${c.label}: expected 301/308 redirect, got ${res.status}`,
    );
    const location = res.headers.location;
    ok(location, `${c.label}: missing Location header`);
    ok(
      normalizeCanonicalUrl(String(location)) === normalizeCanonicalUrl(c.expectedLocation),
      `${c.label}: expected Location=${c.expectedLocation}, got ${location}`,
    );
    ok(
      !String(location).includes("www.reviewdisparity.com"),
      `${c.label}: redirect should not point to www variant`,
    );
    ok(
      String(location).startsWith("https://"),
      `${c.label}: redirect should upgrade to https`,
    );
  }
}

async function assertCanonicalRedirectsLive() {
  const canonical = new URL(EXPECTED_CANONICAL_ORIGIN);
  const host = canonical.hostname;
  const bareHost = host.replace(/^www\./i, "");
  const wwwHost = `www.${bareHost}`;

  const cases = [
    {
      label: "https://www -> https://canonical",
      url: `https://${wwwHost}/`,
      expectedLocation: `${canonical.protocol}//${bareHost}/`,
    },
    {
      label: "http://canonical -> https://canonical",
      url: `http://${bareHost}/`,
      expectedLocation: `${canonical.protocol}//${bareHost}/`,
    },
    {
      label: "http://www -> https://canonical",
      url: `http://${wwwHost}/`,
      expectedLocation: `${canonical.protocol}//${bareHost}/`,
    },
  ];

  for (const c of cases) {
    const response = await fetch(c.url, { redirect: "manual" });
    ok(
      [301, 308].includes(response.status),
      `${c.label}: expected 301/308 redirect, got ${response.status}`,
    );
    const location = response.headers.get("location");
    ok(location, `${c.label}: missing Location header`);
    ok(
      normalizeCanonicalUrl(String(location)) === normalizeCanonicalUrl(c.expectedLocation),
      `${c.label}: expected Location=${c.expectedLocation}, got ${location}`,
    );
    ok(
      !String(location).includes("www.reviewdisparity.com"),
      `${c.label}: redirect should not point to www variant`,
    );
    ok(
      String(location).startsWith("https://"),
      `${c.label}: redirect should upgrade to https`,
    );
  }
}

async function assertCanonicalRedirects() {
  const base = new URL(BASE_URL);
  if (base.hostname === "127.0.0.1" || base.hostname === "localhost") {
    return assertCanonicalRedirectsViaHostHeader();
  }
  return assertCanonicalRedirectsLive();
}

function getOptionalDetailPaths() {
  const raw = process.env.SEO_DETAIL_PATHS;
  if (!raw) return [];
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .filter((s) => s.startsWith("/"));
}

function getAutoDetailPathsFromSitemap(locs) {
  const byType = {
    games: [],
    journalists: [],
    outlets: [],
  };

  for (const loc of locs) {
    let pathname;
    try {
      pathname = new URL(loc).pathname;
    } catch {
      continue;
    }

    if (/^\/games\/[^/]+\/?$/.test(pathname)) {
      byType.games.push(pathname);
      continue;
    }
    if (/^\/journalists\/[^/]+\/?$/.test(pathname)) {
      byType.journalists.push(pathname);
      continue;
    }
    if (/^\/outlets\/[^/]+\/?$/.test(pathname)) {
      byType.outlets.push(pathname);
      continue;
    }
  }

  return [
    ...byType.games.slice(0, DETAIL_SAMPLES_PER_TYPE),
    ...byType.journalists.slice(0, DETAIL_SAMPLES_PER_TYPE),
    ...byType.outlets.slice(0, DETAIL_SAMPLES_PER_TYPE),
  ];
}

function getDetailPathsToTest(sitemapLocs) {
  const combined = [
    ...getAutoDetailPathsFromSitemap(sitemapLocs),
    ...getOptionalDetailPaths(),
  ];

  const seen = new Set();
  const unique = [];
  for (const path of combined) {
    const normalized = path === "/" ? path : path.replace(/\/+$/, "");
    if (!seen.has(normalized)) {
      seen.add(normalized);
      unique.push(normalized);
    }
  }
  return unique;
}

async function run() {
  console.log(`SEO smoke checks against ${BASE_URL}`);
  console.log(`Expected canonical origin: ${EXPECTED_CANONICAL_ORIGIN}`);

  for (const path of INDEXABLE_PAGES) {
    await assertIndexablePage(path);
    console.log(`PASS indexable ${path}`);
  }

  for (const path of NOINDEX_PAGINATED_PAGES) {
    await assertNoindexPage(path);
    console.log(`PASS noindex ${path}`);
  }

  await assertRobotsTxt();
  console.log("PASS /robots.txt");

  const sitemapLocs = await assertSitemapXml();
  console.log("PASS /sitemap.xml");

  await assertCanonicalRedirects();
  console.log("PASS canonical redirects");

  const detailPaths = getDetailPathsToTest(sitemapLocs);
  if (detailPaths.length === 0) {
    if (REQUIRE_DETAIL_PAGES) {
      fail("No detail pages found for SEO testing (sitemap contained no detail URLs and SEO_DETAIL_PATHS was empty)");
    }
    console.log("SKIP detail pages (no detail URLs found in sitemap and no SEO_DETAIL_PATHS provided)");
  } else {
    for (const path of detailPaths) {
      const { response, text, url } = await fetchText(path, { redirect: "follow" });
      ok(response.ok, `${path}: expected 200, got ${response.status} (${url})`);
      const title = getTitle(text);
      ok(title && title.length > 0, `${path}: missing <title>`);
      const description = getMetaContent(text, "description");
      ok(description && description.length > 0, `${path}: missing meta description`);
      const canonical = getCanonicalHref(text);
      const expectedCanonical = canonicalForPath(path);
      ok(canonical, `${path}: missing canonical link`);
      ok(
        normalizeCanonicalUrl(canonical) === normalizeCanonicalUrl(expectedCanonical),
        `${path}: canonical mismatch (expected ${expectedCanonical}, got ${canonical})`,
      );
      const robots = normalizeRobotsContent(getMetaContent(text, "robots"));
      ok(robots.includes("index"), `${path}: expected robots meta to include index`);
      ok(robots.includes("follow"), `${path}: expected robots meta to include follow`);
      ok(!robots.includes("noindex"), `${path}: should not be noindex`);
      assertServerRenderedDetailContent(path, text);
      console.log(`PASS detail ${path}`);
    }
  }

  console.log("SEO smoke checks passed");
}

run().catch((error) => {
  console.error("SEO smoke checks failed");
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
