# Google Indexing Recovery Runbook

This runbook starts after the SEO/GEO remediation is deployed. It separates
technical eligibility from Google's discretionary indexing decision: a valid,
crawlable URL can still remain unindexed.

## 1. Establish a dated baseline

Export the following from Search Console before requesting validation:

- Page indexing totals by reason, including Indexed, Crawled – currently not
  indexed, Discovered – currently not indexed, duplicate/canonical groups,
  soft 404, blocked, and server-error groups;
- submitted-versus-indexed totals for the sitemap;
- the last 28 days of search clicks, impressions, average position, queries,
  pages, countries, and devices.

Save the export date with the files. The supplied screenshot showed 376 indexed
and approximately 27,300 not indexed, but use a fresh export—not the
screenshot—as the operational baseline.

Google states that not every known URL is expected to be indexed. Treat the
exclusion reasons and eligible URL cohort as more useful than the site's raw
known-URL total.

## 2. Confirm production health

Before touching Search Console:

1. Deploy the completed indexing phases.
2. Run **Production SEO and GEO Monitor** manually.
3. Require both workflow steps to pass, including fresh entity sitemaps,
   Dataset freshness, and all nine sampled entity details.
4. Confirm the latest review-data pipeline and its public-surface revalidation
   step succeeded.

Stop here if the workflow is red. Search Console validation should verify a
stable fix, not act as a production test.

## 3. Submit the sitemap index

In Search Console, submit:

```text
https://reviewdisparity.com/sitemap.xml
```

Submit the sitemap index once; it lists the static, games, journalists, and
outlets sitemap files. Verify that the status becomes **Success**, the last-read
date advances, and discovered counts are plausible relative to the production
monitor. Do not repeatedly remove and resubmit a healthy sitemap.

## 4. Inspect a representative URL matrix

Use URL Inspection's **Test live URL** on:

- three sitemap-listed eligible games;
- three sitemap-listed eligible journalists;
- three sitemap-listed eligible outlets;
- two or three intentionally thin entity pages omitted from sitemaps;
- one legacy ID-only detail URL.

For every eligible canonical URL, require:

- live HTTP 200;
- crawl allowed and no `noindex`;
- the declared canonical equals the tested URL;
- Google's selected canonical does not show a conflicting URL once recrawled;
- a descriptive title and description;
- visible, server-rendered “What the data shows” evidence;
- valid entity, WebPage, BreadcrumbList, publisher, and Dataset connections.

For intentionally thin pages, require `noindex, follow` and absence from the XML
sitemaps. For the legacy URL, require a permanent redirect to the canonical
`slug--id` URL.

If any eligible sample fails, stop and remediate before proceeding.

## 5. Request indexing and validate the fix

Request indexing for a small, representative high-priority set: the homepage,
key directory/about pages, and a few eligible entities from each type. Do not
attempt to submit thousands of URLs manually. The sitemap and internal links
are the scalable discovery mechanisms.

Once live inspection is clean and the deployment has remained healthy, start
**Validate Fix** for the relevant Page indexing issue. For the supplied failure,
that is **Crawled – currently not indexed**.

Fix validation samples URLs and can take roughly two weeks or longer. A
successful validation means Google confirmed the issue state on its samples; it
does not guarantee that every eligible URL will be indexed. Search Console can
also update issue counts as Google recrawls even when validation is not started.

## 6. Recovery checkpoints

Record these checkpoints against the baseline:

| Checkpoint | What to verify |
| --- | --- |
| Deployment day | Production monitor green; sitemap status and counts healthy; representative live tests pass |
| 24–48 hours | Sitemap last-read advances; no sitewide robots, canonical, 5xx, or freshness regression |
| Day 7 | Eligible samples are being recrawled; Crawled/Discovered exclusions are not accelerating |
| Day 14 | Validation status and sampled outcomes; indexed eligible cohort begins moving directionally upward |
| Day 28 | Indexed eligible pages, impressions, clicks, and exclusion reasons compared with baseline |

Success is not “100% of known URLs indexed.” Use these realistic conditions:

- 100% of the representative eligible samples remain technically indexable;
- sitemap counts stay above safety floors and all entity sitemaps remain fresh;
- Dataset freshness remains under 24 hours;
- indexed eligible URLs trend upward and Crawled – currently not indexed trends
  downward over multiple checkpoints;
- organic impressions stabilize and then improve without a new exclusion spike.

## 7. Incident and rollback thresholds

Treat any of these as a release incident:

- an eligible template gains `noindex`, loses its self-canonical, or returns 5xx;
- an entity sitemap falls below its floor or serves `last-known-good`;
- sitemap URLs no longer match the canonical `slug--id` form;
- server-rendered evidence or structured data disappears from eligible details;
- the public Dataset timestamp exceeds 24 hours.

Pause further indexing requests, restore production health, rerun the monitor,
and retest the representative matrix. Do not lower inventory floors merely to
make monitoring green; first determine whether eligibility legitimately changed
or data access failed.

## Google references

- [Manage sitemaps using the Sitemaps report](https://support.google.com/webmasters/answer/7451001)
- [Sitemap index processing in Search Console](https://support.google.com/webmasters/answer/12818558)
- [Page indexing report and fix validation](https://support.google.com/webmasters/answer/7440203)
- [URL Inspection tool](https://support.google.com/webmasters/answer/12482179)
