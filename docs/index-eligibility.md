# Entity Index Eligibility

Entity pages remain publicly accessible regardless of eligibility. Pages below
the thresholds use `noindex, follow` and are omitted from XML sitemaps so links
and historical URLs continue to work without asking Google to index thin pages.

The canonical policy lives in `app/services/index_eligibility.py`.

## Current thresholds

- Games: at least 20 scored critic reviews, a non-empty description, at least
  one qualified player-score source, and at least one calculated disparity.
  Steam requires 50 user reviews; Metacritic requires 20 when a sample count is
  available.
- Journalists: at least 10 scored reviews and a calculated average disparity.
- Outlets: at least 10 scored reviews and a calculated average disparity.

The backend applies the same policy to detail API `index_eligible` flags and
sitemap queries. Frontend metadata combines that flag with URL state: share
variants and paginated detail views remain `noindex, follow`.

When eligibility rules change, update the policy version in
`frontend/src/lib/index-eligibility.ts` and review the sitemap count floors in
`frontend/src/lib/server-sitemaps.ts`, `frontend/scripts/seo-smoke.mjs`, and the
production sitemap-monitor workflow.
