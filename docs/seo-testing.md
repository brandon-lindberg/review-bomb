# SEO Testing

This project has automated SEO/indexability checks for build-time regressions and live production monitoring.

## Workflows

- `SEO Smoke Tests`
  - CI workflow that builds the frontend, starts `next start`, and checks canonical tags, robots meta, `robots.txt`, `sitemap.xml`, redirects, and sampled detail pages (when available).
- `SEO Smoke Tests (Live)`
  - Scheduled/manual workflow that runs the same checks directly against `https://reviewdisparity.com` and requires detail-page coverage.
- `Lighthouse SEO`
  - CI workflow that runs Lighthouse SEO audits on key pages against a production build.

## Local Commands

Run from `frontend/`.

### 1) SEO smoke tests (local app)

Terminal A:

```bash
yarn build
yarn start -p 3000
```

Terminal B:

```bash
yarn test:seo
```

### 2) Require detail-page indexability checks (`/games/[id]`, `/journalists/[id]`, `/outlets/[id]`)

Use this when backend is running and `sitemap.xml` includes detail URLs.

```bash
SEO_REQUIRE_DETAIL_PAGES=1 SEO_DETAIL_SAMPLES_PER_TYPE=3 yarn test:seo
```

### 3) Add explicit detail pages (optional)

```bash
SEO_DETAIL_PATHS="/games/18971,/journalists/477,/outlets/24252" yarn test:seo
```

### 4) Run SEO smoke against production (optional local check)

```bash
SEO_BASE_URL=https://reviewdisparity.com \
SEO_EXPECTED_CANONICAL_ORIGIN=https://reviewdisparity.com \
SEO_REQUIRE_DETAIL_PAGES=1 \
SEO_DETAIL_SAMPLES_PER_TYPE=3 \
yarn test:seo
```

### 5) Lighthouse SEO checks (local)

Terminal A:

```bash
yarn build
yarn start -p 3000
```

Terminal B:

```bash
npx @lhci/cli@0.15.x collect --config=.lighthouserc.json
npx @lhci/cli@0.15.x assert --config=.lighthouserc.json
```

## Branch Protection (Master)

Set branch protection on `master` and require these status checks before merge:

- `SEO Smoke Tests`
- `Lighthouse SEO`

Recommended settings:

- Require a pull request before merging
- Require status checks to pass before merging
- Require branches to be up to date before merging
- Do not allow force pushes
- Do not allow deletions

Note: branch protection is configured in GitHub repository settings (not in this repo). Use:

- GitHub UI: `Settings` -> `Branches` -> `Add branch protection rule` -> branch pattern `master`
- Required status checks: add the workflow names above

