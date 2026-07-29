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
];

const NOINDEX_PAGES = [
  "/search",
  "/games?search=halo",
  "/games?page=2&sort=title&order=asc",
  "/news?page=2",
  "/news?source=IGN",
  "/journalists?search=smith",
  "/journalists?page=2&search=smith",
  "/outlets?sort=name&order=asc",
  "/compare?type=games&ids=1,2",
  "/search?q=halo",
];

// Plain default-view pagination is indexable with self-referencing canonicals
// so entity detail pages keep followed internal links.
const PAGINATED_INDEXABLE_PAGES = [
  "/games?page=2",
  "/journalists?page=2",
  "/outlets?page=2",
];

const DETAIL_SAMPLES_PER_TYPE = Math.max(
  1,
  Number.parseInt(process.env.SEO_DETAIL_SAMPLES_PER_TYPE || "1", 10) || 1,
);
const REQUIRE_DETAIL_PAGES = process.env.SEO_REQUIRE_DETAIL_PAGES === "1";
const SITEMAP_ONLY = process.env.SEO_SITEMAP_ONLY === "1";
const SITEMAP_MIN_COUNTS = {
  games: Number.parseInt(process.env.SITEMAP_MIN_GAMES || "3500", 10),
  journalists: Number.parseInt(process.env.SITEMAP_MIN_JOURNALISTS || "4000", 10),
  outlets: Number.parseInt(process.env.SITEMAP_MIN_OUTLETS || "600", 10),
};

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
  ok(
    text.includes('data-server-rendered-evidence="true"'),
    `${path}: expected a server-rendered evidence snapshot`,
  );
  ok(
    text.includes("What the data shows"),
    `${path}: expected data-derived analysis in initial HTML`,
  );
  ok(
    text.includes('"@type":"ItemList"') &&
      text.includes("#recent-review-evidence"),
    `${path}: expected recent-review evidence structured data`,
  );
  ok(
    text.includes(`${EXPECTED_CANONICAL_ORIGIN}/#organization`) &&
      text.includes(`${EXPECTED_CANONICAL_ORIGIN}/about#dataset`),
    `${path}: expected publisher and dataset knowledge-graph references`,
  );
  ok(
    text.includes("#entity") &&
      text.includes("#webpage") &&
      text.includes('"mainEntityOfPage"'),
    `${path}: expected connected entity and WebPage identifiers`,
  );
}

function assertBreadcrumbContent(path, text) {
  ok(text.includes('aria-label="Breadcrumb"'), `${path}: expected visible breadcrumb nav`);
  ok(text.includes('"BreadcrumbList"'), `${path}: expected breadcrumb structured data`);
}

async function assertRobotsTxt() {
  const { response, text } = await fetchText("/robots.txt", { redirect: "follow" });
  ok(response.ok, `/robots.txt: expected 200, got ${response.status}`);
  const contentType = response.headers.get("content-type") || "";
  ok(
    contentType.startsWith("text/plain"),
    `/robots.txt: expected text/plain content-type, got ${contentType}`,
  );
  ok(
    text.includes(`Sitemap: ${EXPECTED_CANONICAL_ORIGIN}/sitemap.xml`),
    "/robots.txt: missing canonical sitemap URL",
  );
  ok(text.includes("Disallow: /api/"), "/robots.txt: missing Disallow: /api/");
  ok(
    text.includes("Content-Signal: ai-train=no, search=yes, ai-input=yes"),
    "/robots.txt: missing Content-Signal directive",
  );
  ok(!text.includes("http://reviewdisparity.com"), "/robots.txt: should not reference http://reviewdisparity.com");
  ok(!text.includes("https://www.reviewdisparity.com"), "/robots.txt: should not reference https://www.reviewdisparity.com");
}

async function assertLlmsTxt() {
  const { response, text } = await fetchText("/llms.txt", { redirect: "follow" });
  ok(response.ok, `/llms.txt: expected 200, got ${response.status}`);
  const contentType = response.headers.get("content-type") || "";
  ok(
    contentType.startsWith("text/plain"),
    `/llms.txt: expected text/plain content-type, got ${contentType}`,
  );
  ok(text.startsWith("# ReviewDisparity"), "/llms.txt: unexpected leading content");
  ok(
    text.includes("`/api/` path is private"),
    "/llms.txt: must state that /api/ is private",
  );
  ok(text.includes("/sitemap.xml"), "/llms.txt: missing sitemap link");
  ok(
    text.includes("Disparity measures score disagreement") &&
      text.includes("does not by itself establish motive"),
    "/llms.txt: missing interpretation limits",
  );
  ok(
    text.includes("/about#dataset") &&
      text.includes("/about#editorial-principles"),
    "/llms.txt: missing dataset and publishing-principles links",
  );
}

async function assertGeoKnowledgePages() {
  const [home, about, faq] = await Promise.all([
    fetchText("/", { redirect: "follow" }),
    fetchText("/about", { redirect: "follow" }),
    fetchText("/faq", { redirect: "follow" }),
  ]);

  for (const [path, result] of [["/", home], ["/about", about], ["/faq", faq]]) {
    ok(result.response.ok, `${path}: expected 200 for GEO knowledge check`);
    ok(
      result.text.includes(`${EXPECTED_CANONICAL_ORIGIN}/#organization`) &&
        result.text.includes(`${EXPECTED_CANONICAL_ORIGIN}/#website`),
      `${path}: missing stable publisher or website identifier`,
    );
  }

  ok(
    home.text.includes("What ReviewDisparity measures") &&
      home.text.includes("It measures disagreement"),
    "/: missing answer-first definition and limitation",
  );
  ok(
    about.text.includes('"@type":"Dataset"') &&
      about.text.includes('"isBasedOn"') &&
      about.text.includes('"variableMeasured"'),
    "/about: missing Dataset provenance or measured variables",
  );
  ok(
    about.text.includes("Dataset Scope and Provenance") &&
      about.text.includes("Publisher and creator") &&
      about.text.includes("Publishing Principles and Limitations"),
    "/about: structured dataset claims must have matching visible content",
  );
  ok(
    faq.text.includes("Disparity alone does not establish motive"),
    "/faq: missing neutral interpretation limit",
  );
}

async function assertLlmsLinkHeader(path) {
  const { response } = await fetchText(path, { redirect: "follow" });
  const linkHeader = response.headers.get("link") || "";
  ok(
    linkHeader.includes("</llms.txt>") && linkHeader.includes('rel="describedby"'),
    `${path}: missing Link: </llms.txt>; rel="describedby" header (got: ${linkHeader || "none"})`,
  );
}

async function assertPaginatedIndexablePage(path) {
  const { response, text, url } = await fetchText(path, { redirect: "follow" });
  ok(response.ok, `${path}: expected 200, got ${response.status} (${url})`);

  const canonical = getCanonicalHref(text);
  const expectedCanonical = new URL(path, EXPECTED_CANONICAL_ORIGIN).toString();
  ok(canonical, `${path}: missing canonical link`);
  ok(
    normalizeCanonicalUrl(canonical) === normalizeCanonicalUrl(expectedCanonical),
    `${path}: canonical mismatch (expected ${expectedCanonical}, got ${canonical})`,
  );

  const robots = normalizeRobotsContent(getMetaContent(text, "robots"));
  ok(robots.includes("index"), `${path}: expected robots meta to include index`);
  ok(robots.includes("follow"), `${path}: expected robots meta to include follow`);
  ok(!robots.includes("noindex"), `${path}: paginated default view should not be noindex`);
}

async function assertMarkdownNegotiation(path) {
  // Default request keeps returning HTML.
  const htmlResult = await fetchText(path, { redirect: "follow" });
  ok(htmlResult.response.ok, `${path}: expected 200 for HTML request, got ${htmlResult.response.status}`);
  const htmlType = htmlResult.response.headers.get("content-type") || "";
  ok(htmlType.includes("text/html"), `${path}: default request should return text/html, got ${htmlType}`);

  // Explicit Accept: text/markdown returns the Markdown variant.
  const mdResult = await fetchText(path, {
    redirect: "follow",
    headers: { Accept: "text/markdown" },
  });
  ok(mdResult.response.ok, `${path}: expected 200 for markdown request, got ${mdResult.response.status}`);
  const mdType = mdResult.response.headers.get("content-type") || "";
  ok(
    mdType.startsWith("text/markdown"),
    `${path}: Accept: text/markdown should return text/markdown, got ${mdType}`,
  );
  const varyHeader = (mdResult.response.headers.get("vary") || "").toLowerCase();
  ok(
    varyHeader.split(",").map((v) => v.trim()).includes("accept"),
    `${path}: markdown response must include Vary: Accept (got: ${varyHeader || "none"})`,
  );
  ok(mdResult.text.startsWith("# "), `${path}: markdown body should start with an H1`);
  ok(
    mdResult.text.includes(`Canonical URL: ${EXPECTED_CANONICAL_ORIGIN}`),
    `${path}: markdown body should state its canonical URL`,
  );
  ok(
    !mdResult.text.includes("onrender.com") && !/\/api\/v1/.test(mdResult.text),
    `${path}: markdown body must not leak private API endpoints`,
  );
}

async function assertUnknownEntity404() {
  const path = "/games/index-safety-probe--00000000000000000000000000000000";
  const { response, text } = await fetchText(path, { redirect: "manual" });

  ok(response.status === 404, `${path}: expected a real 404, got ${response.status}`);
  const xRobots = normalizeRobotsContent(response.headers.get("x-robots-tag"));
  ok(xRobots.includes("noindex"), `${path}: missing noindex X-Robots-Tag`);

  const robotsTags = text.match(/<meta\b[^>]*name=["']robots["'][^>]*>/gi) || [];
  ok(robotsTags.length === 1, `${path}: expected one robots meta tag, got ${robotsTags.length}`);
  const robots = normalizeRobotsContent(getMetaContent(text, "robots"));
  ok(robots.includes("noindex"), `${path}: robots meta must include noindex`);
  ok(!robots.includes("index"), `${path}: robots meta must not conflict with index`);
  ok(!getCanonicalHref(text), `${path}: a missing entity must not inherit the homepage canonical`);
}

async function assertSitemapXml() {
  const indexResult = await fetchText("/sitemap.xml", { redirect: "follow" });
  ok(indexResult.response.ok, `/sitemap.xml: expected 200, got ${indexResult.response.status}`);
  ok(indexResult.text.includes("<sitemapindex"), "/sitemap.xml: expected a sitemap index");

  const expectedChildren = [
    "/sitemaps/static.xml",
    "/sitemaps/games.xml",
    "/sitemaps/journalists.xml",
    "/sitemaps/outlets.xml",
  ];
  const indexLocs = [...indexResult.text.matchAll(/<loc>([^<]+)<\/loc>/gi)]
    .map((match) => match[1].trim());
  ok(indexLocs.length === expectedChildren.length, `/sitemap.xml: expected ${expectedChildren.length} child sitemaps, got ${indexLocs.length}`);

  for (const childPath of expectedChildren) {
    const expectedUrl = new URL(childPath, EXPECTED_CANONICAL_ORIGIN).toString();
    ok(indexLocs.includes(expectedUrl), `/sitemap.xml: missing ${expectedUrl}`);
  }

  const allPageLocs = [];
  const seenPageLocs = new Set();
  for (const childPath of expectedChildren) {
    const { response, text } = await fetchText(childPath, { redirect: "follow" });
    ok(response.ok, `${childPath}: expected 200, got ${response.status}`);
    ok(text.includes("<urlset"), `${childPath}: expected a URL set`);
    ok(Buffer.byteLength(text, "utf8") < 50_000_000, `${childPath}: exceeds 50 MB sitemap limit`);

    const locs = [...text.matchAll(/<loc>([^<]+)<\/loc>/gi)].map((match) => match[1].trim());
    const headerCount = Number.parseInt(response.headers.get("x-sitemap-url-count") || "", 10);
    ok(headerCount === locs.length, `${childPath}: X-Sitemap-Url-Count ${headerCount} does not match ${locs.length} URLs`);
    ok(locs.length <= 50_000, `${childPath}: exceeds 50,000 URL sitemap limit`);

    const typeMatch = childPath.match(/^\/sitemaps\/(games|journalists|outlets)\.xml$/);
    if (typeMatch) {
      const type = typeMatch[1];
      ok(locs.length >= SITEMAP_MIN_COUNTS[type], `${childPath}: ${locs.length} URLs is below safety floor ${SITEMAP_MIN_COUNTS[type]}`);
      const lastmods = [...text.matchAll(/<lastmod>([^<]+)<\/lastmod>/gi)]
        .map((match) => match[1].trim());
      ok(lastmods.length === locs.length, `${childPath}: expected lastmod for every entity URL`);
      ok(lastmods.every((value) => !Number.isNaN(new Date(value).getTime())), `${childPath}: contains invalid lastmod values`);
    }

    for (const loc of locs) {
      ok(
        loc.startsWith(`${EXPECTED_CANONICAL_ORIGIN}/`) || loc === `${EXPECTED_CANONICAL_ORIGIN}/`,
        `${childPath}: non-canonical URL found (${loc})`,
      );
      ok(!loc.startsWith("http://"), `${childPath}: found http URL (${loc})`);
      ok(!loc.startsWith("https://www."), `${childPath}: found www URL (${loc})`);
      ok(!loc.includes("?page="), `${childPath}: paginated URL should not be listed (${loc})`);
      ok(!seenPageLocs.has(loc), `${childPath}: duplicate URL across sitemap files (${loc})`);
      seenPageLocs.add(loc);

      const pathname = new URL(loc).pathname;
      const detailMatch = pathname.match(/^\/(games|journalists|outlets)\/([^/]+)\/?$/);
      if (detailMatch) {
        ok(
          detailMatch[2].includes("--"),
          `${childPath}: detail URL should use slug--id canonical format (${loc})`,
        );
      }
    }
    allPageLocs.push(...locs);
  }

  ok(allPageLocs.includes(`${EXPECTED_CANONICAL_ORIGIN}/news`), "static sitemap must include /news");
  ok(!allPageLocs.includes(`${EXPECTED_CANONICAL_ORIGIN}/search`), "sitemaps must exclude noindex /search");
  return allPageLocs;
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

function getLegacyDetailPath(path) {
  const match = path.match(/^\/(games|journalists|outlets)\/([^/]+)$/);
  if (!match) return null;

  const segment = match[2];
  const separatorIndex = segment.lastIndexOf("--");
  if (separatorIndex <= 0 || separatorIndex === segment.length - 2) return null;

  const identifier = segment.slice(separatorIndex + 2);
  return `/${match[1]}/${identifier}`;
}

async function assertLegacyDetailRedirect(path) {
  const legacyPath = getLegacyDetailPath(path);
  if (!legacyPath) return;

  const probePath = `${legacyPath}?legacy_probe=1`;
  const expectedLocation = `${path}?legacy_probe=1`;
  const { response, url } = await fetchText(probePath, { redirect: "manual" });

  ok(
    [301, 308].includes(response.status),
    `${legacyPath}: expected 301/308 redirect, got ${response.status} (${url})`,
  );

  const location = response.headers.get("location");
  ok(location, `${legacyPath}: missing Location header`);
  ok(
    normalizeCanonicalUrl(String(location)) === normalizeCanonicalUrl(new URL(expectedLocation, EXPECTED_CANONICAL_ORIGIN).toString()),
    `${legacyPath}: expected redirect to ${expectedLocation}, got ${location}`,
  );
}

async function run() {
  console.log(`SEO smoke checks against ${BASE_URL}`);
  console.log(`Expected canonical origin: ${EXPECTED_CANONICAL_ORIGIN}`);

  if (SITEMAP_ONLY) {
    const sitemapLocs = await assertSitemapXml();
    console.log(`PASS sitemap inventory (${sitemapLocs.length} URLs)`);
    return;
  }

  for (const path of INDEXABLE_PAGES) {
    await assertIndexablePage(path);
    console.log(`PASS indexable ${path}`);
  }

  for (const path of NOINDEX_PAGES) {
    await assertNoindexPage(path);
    console.log(`PASS noindex ${path}`);
  }

  for (const path of PAGINATED_INDEXABLE_PAGES) {
    await assertPaginatedIndexablePage(path);
    console.log(`PASS paginated-indexable ${path}`);
  }

  await assertRobotsTxt();
  console.log("PASS /robots.txt");

  await assertLlmsTxt();
  console.log("PASS /llms.txt");

  await assertGeoKnowledgePages();
  console.log("PASS GEO knowledge graph and visible authority content");

  await assertLlmsLinkHeader("/");
  console.log("PASS llms.txt Link header /");

  await assertMarkdownNegotiation("/");
  console.log("PASS markdown negotiation /");

  await assertUnknownEntity404();
  console.log("PASS unknown entity 404");

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
      const cacheControl = (response.headers.get("cache-control") || "").toLowerCase();
      ok(cacheControl.includes("public"), `${path}: canonical HTML should be publicly cacheable`);
      ok(cacheControl.includes("s-maxage="), `${path}: canonical HTML should set an edge-cache TTL`);
      ok(!cacheControl.includes("no-store"), `${path}: canonical HTML must not use no-store`);
      ok(!cacheControl.includes("private"), `${path}: canonical HTML must not use private caching`);
      assertServerRenderedDetailContent(path, text);
      assertBreadcrumbContent(path, text);
      await assertLegacyDetailRedirect(path);
      await assertMarkdownNegotiation(path);
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
