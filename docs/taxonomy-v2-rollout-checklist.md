# Taxonomy V2 Rollout Checklist

## Goal

This checklist defines the implementation and rollout path for Similar Games Taxonomy V2.

It assumes the design docs already exist:

- [similar-games-taxonomy-v2.md](/Users/lindbergbrandon/backend/docs/similar-games-taxonomy-v2.md)
- [fingerprint-extraction-rules.md](/Users/lindbergbrandon/backend/docs/fingerprint-extraction-rules.md)
- [similar-games-gold-set.md](/Users/lindbergbrandon/backend/docs/similar-games-gold-set.md)

## Phase 1: Ontology Lock

- [ ] Freeze canonical fingerprint fields and enum values
- [ ] Freeze initial archetype node list
- [ ] Freeze archetype adjacency graph
- [ ] Freeze hard exclusion vocabulary
- [ ] Decide JSONB vs dedicated-column storage for fingerprint v2
- [ ] Decide whether evidence records live in DB table, JSONB, or both

Exit criteria:

- Taxonomy schema is stable enough that extraction work can begin without churn

## Phase 2: Storage Model

- [ ] Add V2 storage to the database
- [ ] Add taxonomy version field
- [ ] Add evidence/provenance storage
- [ ] Add indexes for queryable archetype / fingerprint fields
- [ ] Keep V1 and V2 side by side during migration

Recommended storage split:

- canonical V2 fingerprint on `games`
- evidence in a dedicated table or JSONB payload
- archetype graph in repo-managed data

Exit criteria:

- DB can store V2 fingerprints and evidence without breaking V1

## Phase 3: Extraction Engine

- [ ] Build source-to-fingerprint mapping layer for Steam
- [ ] Build source-to-fingerprint mapping layer for OpenCritic
- [ ] Build source-to-fingerprint mapping layer for Metacritic
- [ ] Add description phrase extraction
- [ ] Add hard exclusion inference
- [ ] Add confidence scoring
- [ ] Add conflict resolution logic
- [ ] Add archetype assignment pass

Exit criteria:

- A single game can be classified into a V2 fingerprint with evidence and confidence

## Phase 4: Curation Layer

- [ ] Create curated override format for V2 fields
- [ ] Add anchor-game override support
- [ ] Add blocked-neighbor override support if needed
- [ ] Define editorial workflow for updating overrides
- [ ] Seed overrides for flagship anchors

Priority anchors:

- Crimson Desert
- The Witcher 3
- Breath of the Wild
- Elden Ring
- Black Desert
- Resident Evil
- Counter-Strike 2
- Baldur's Gate 3
- Cities: Skylines II
- Stardew Valley

Exit criteria:

- Top anchor titles have trustworthy fingerprints even if automated extraction is incomplete

## Phase 5: Tooling

- [ ] Add `taxonomy-v2-backfill` CLI command
- [ ] Add `taxonomy-v2-audit` CLI command
- [ ] Add `similar-v2-debug` CLI command
- [ ] Add debug output for:
  - inferred traits
  - evidence sources
  - chosen archetype
  - rejected candidates and reasons
- [ ] Add unmapped-phrase audit
- [ ] Add low-confidence-anchor audit

Exit criteria:

- It is easy to understand why a game matched or failed

## Phase 6: Gold Set Evaluation

- [ ] Formalize the starter gold set
- [ ] Expand gold set to 100-200 anchors
- [ ] Add automated evaluation runner
- [ ] Compute precision@5
- [ ] Track blocked-neighbor violations
- [ ] Track family-level performance

Flagship acceptance criteria:

- [ ] Crimson Desert returns expected fantasy action RPG peers
- [ ] Survival horror anchors do not leak into fantasy action RPGs
- [ ] Tactical FPS anchors do not leak into action adventure
- [ ] Strategy/sim anchors do not leak into RPG/shooter results

Global acceptance criteria:

- [ ] No blocked neighbors in top 5 for anchor set
- [ ] Precision@5 meets launch threshold

Exit criteria:

- V2 is measurably better than V1 on curated anchors

## Phase 7: API and Query Layer

- [ ] Add V2 matcher alongside V1
- [ ] Expose a debug endpoint or CLI path for side-by-side comparison
- [ ] Add cache versioning for V2 result sets
- [ ] Keep V1 available behind a flag during validation

Exit criteria:

- V2 can be exercised without replacing production behavior immediately

## Phase 8: UI Validation

- [ ] Point internal/staging UI at V2 results
- [ ] Review flagship pages manually
- [ ] Verify that Similar Games reasons reflect archetype logic, not raw tags
- [ ] Verify that user-facing labels do not expose internal uncertainty jargon

Manual review set:

- Crimson Desert
- Elden Ring
- The Witcher 3
- Resident Evil anchor
- Counter-Strike anchor
- Cities: Skylines anchor
- Stardew Valley anchor

Exit criteria:

- UI output is understandable and human-plausible for reviewed anchors

## Phase 9: Production Cutover

- [ ] Switch Similar Games API from V1 to V2
- [ ] Bump cache keys
- [ ] Keep rollback switch available
- [ ] Monitor bad-match reports
- [ ] Expand curated override coverage for outliers

Exit criteria:

- V2 is stable in production and no major family-level regressions are observed

## Phase 10: Post-Cutover Improvements

- [ ] Expand archetype library beyond initial 40 nodes
- [ ] Improve phrase extraction coverage
- [ ] Add more cross-source description ingestion
- [ ] Add franchise-aware rules where appropriate
- [ ] Add more gold-set anchors for newly released games

## Non-Negotiables

These are the constraints that should not be compromised during implementation:

- [ ] Broad labels like `action`, `adventure`, or `single-player` must never qualify a match on their own
- [ ] Release timing must not be a similarity signal
- [ ] Critic network must not be a meaningful user-facing similarity reason
- [ ] Horror, sports, match-based shooters, and management sims must be protected by hard negatives
- [ ] V2 must be evaluated against a gold set before cutover

## Deliverables

Minimum deliverables before production switch:

- [ ] ontology doc
- [ ] extraction rules doc
- [ ] gold set doc
- [ ] rollout checklist
- [ ] V2 storage
- [ ] V2 extraction engine
- [ ] V2 debug tooling
- [ ] gold-set evaluator
- [ ] curated anchor overrides
- [ ] V2 API path

## Suggested Order of Work

1. finalize docs
2. implement storage
3. implement extraction
4. implement debug tooling
5. seed curation
6. run backfill
7. evaluate against gold set
8. iterate on failures
9. switch UI/API

## Done Definition

Taxonomy V2 is only "done" when:

- flagship anchors produce human-plausible matches
- blocked neighbors do not appear in the top 5
- results are explainable in debug tooling
- the system is measurably better than V1 on the gold set
