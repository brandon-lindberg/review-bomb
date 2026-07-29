# SEO and GEO Verification

The frontend includes one smoke suite for indexability, server-rendered evidence,
structured data, agent-facing representations, redirects, and XML sitemap
integrity. The same suite runs locally and against production.

## Automated production monitor

`.github/workflows/sitemap-monitor.yml` defines the **Production SEO and GEO
Monitor**. It runs at 04:15 and 16:15 UTC, after the two review-data pipeline
windows, and can also be dispatched manually.

The production job fails when any of these conditions is detected:

- an indexable route returns a non-200 response, loses its title, description,
  self-canonical, or `index, follow` directive;
- a deliberately excluded search, filter, sort, share, or combined-query route
  loses `noindex, follow`;
- a detail page lacks server-rendered evidence, breadcrumb markup, connected
  entity JSON-LD, public caching, Markdown representation, or its legacy
  redirect;
- `robots.txt`, `llms.txt`, Markdown negotiation, the GEO knowledge graph, or a
  real entity 404 regresses;
- an entity sitemap drops below its safety floor, contains invalid URLs or
  `lastmod` values, exceeds protocol limits, or is served from the
  `last-known-good` fallback instead of fresh backend data;
- the public Dataset `dateModified` value is missing, invalid, or more than 24
  hours old.

GitHub Actions failure notifications are the alerting channel. Do not start a
Search Console validation while this workflow is failing.

The review-data pipeline explicitly revalidates the homepage, `/about`, entity
directories, leaderboards, the sitemap index, and all entity sitemaps after a
successful refresh. If the frontend URL or shared secret is not configured, the
pipeline emits a warning; if configured revalidation fails, the pipeline fails.

## Local commands

Run these from `frontend/`.

Build and run the production server:

```bash
npm run build
npm start
```

In another terminal, with the backend available:

```bash
npm run test:seo
```

Require three eligible examples from every entity sitemap:

```bash
SEO_REQUIRE_DETAIL_PAGES=1 \
SEO_DETAIL_SAMPLES_PER_TYPE=3 \
npm run test:seo
```

Run the complete production policy manually:

```bash
SEO_BASE_URL=https://reviewdisparity.com \
SEO_EXPECTED_CANONICAL_ORIGIN=https://reviewdisparity.com \
SEO_REQUIRE_DETAIL_PAGES=1 \
SEO_DETAIL_SAMPLES_PER_TYPE=3 \
SEO_REQUIRE_FRESH_SITEMAPS=1 \
SEO_MAX_DATA_AGE_HOURS=24 \
npm run test:seo
```

Run sitemap inventory checks only:

```bash
SEO_SITEMAP_ONLY=1 \
SEO_REQUIRE_FRESH_SITEMAPS=1 \
npm run test:seo
```

Run the unit and snapshot suite:

```bash
npm run test:share-snapshots
```

## Policy controls

- `SEO_BASE_URL`: target site; defaults to `http://127.0.0.1:3000`.
- `SEO_EXPECTED_CANONICAL_ORIGIN`: required canonical origin; defaults to
  `https://reviewdisparity.com`.
- `SEO_REQUIRE_DETAIL_PAGES=1`: fail if no eligible detail URLs can be sampled.
- `SEO_DETAIL_SAMPLES_PER_TYPE`: number sampled from each of games,
  journalists, and outlets.
- `SEO_DETAIL_PATHS`: optional comma-separated detail paths to add to the
  sitemap-derived samples.
- `SEO_SITEMAP_ONLY=1`: skip non-sitemap checks.
- `SEO_REQUIRE_FRESH_SITEMAPS=1`: require `X-Sitemap-Source: fresh` on entity
  sitemaps and `static` on the static sitemap.
- `SEO_MAX_DATA_AGE_HOURS`: enforce the Dataset JSON-LD `dateModified` age; `0`
  disables the policy.
- `SITEMAP_MIN_GAMES`, `SITEMAP_MIN_JOURNALISTS`, and
  `SITEMAP_MIN_OUTLETS`: inventory-collapse safety floors.

Local smoke tests leave production-only freshness policies disabled unless they
are explicitly enabled. Production automation enables them.

## Agent and GEO surfaces

- `/robots.txt` advertises the canonical sitemap, blocks `/api/`, and declares
  the site's content-use signals.
- `/llms.txt` explains the public dataset, its limitations, and the private API
  boundary.
- Public HTML responses link to `/llms.txt` with `rel="describedby"`.
- The homepage and entity detail pages provide Markdown when the request
  explicitly accepts `text/markdown`; normal requests continue to receive HTML.
- `/about` publishes the connected Organization, WebSite, AboutPage, and
  Dataset knowledge graph with visible provenance and methodology.
- Entity HTML includes data-derived, server-rendered evidence and connected
  entity/WebPage/BreadcrumbList JSON-LD.

If HTML is ever cached at the CDN, keep negotiated Markdown routes outside any
cache rule that ignores `Vary: Accept`.

## Incident triage

1. Open the failed workflow step and identify whether the failure is transport,
   indexability, sitemap inventory/source, rendered evidence, or data freshness.
2. Check the same URL with the URL Inspection live test and a direct `curl`
   request. CDN and deployment state can differ from repository state.
3. For `last-known-good` sitemap failures, inspect backend availability before
   changing sitemap floors. The fallback preserves discovery temporarily but is
   not considered a healthy steady state.
4. For stale Dataset failures, inspect the review-data pipeline and the
   post-pipeline revalidation step.
5. Re-run the production workflow after remediation. Only then use Search
   Console's fix validation process described in
   `docs/indexing-recovery-runbook.md`.
