# Taxonomy V2 Storage Model

## Purpose

This document defines how Similar Games Taxonomy V2 should be stored in the database and in repo-managed data files.

It answers:

- what belongs on `games`
- what belongs in evidence tables
- what stays as repo-managed ontology data
- how V1 and V2 coexist during rollout

This is a design decision document, not an implementation patch.

## Decision Summary

Use a hybrid storage model:

- canonical V2 similarity fields on `games`
- full fingerprint payload on `games` as JSONB
- evidence and provenance in a dedicated table
- curated overrides in repo-managed files first
- archetype graph in repo-managed JSON

This gives:

- fast API queries
- explainable debug output
- versioned rollout
- room to iterate on the fingerprint without constant migrations

## Recommended Storage Split

### 1. Repo-managed ontology data

Keep these in versioned files:

- `archetype-graph-v2.json`
- fingerprint enum vocabulary
- phrase extraction rule sets
- curated gold set
- curated game overrides

Reason:

- these are logic artifacts, not runtime user content
- they need reviewable diffs
- they should be deploy-versioned

### 2. Canonical query fields on `games`

Add the smallest set of fields needed for fast similar-game queries and debugging:

- `taxonomy_v2_version`
- `taxonomy_v2_status`
- `taxonomy_v2_primary_family`
- `taxonomy_v2_primary_archetype`
- `taxonomy_v2_secondary_archetypes` as `text[]`
- `taxonomy_v2_hard_exclusions` as `text[]`
- `taxonomy_v2_soft_penalties` as `text[]`
- `taxonomy_v2_confidence` numeric or short text bucket
- `taxonomy_v2_computed_at`

These should be indexed because they are needed for:

- candidate generation
- API filtering
- debug queries

### 3. Full fingerprint on `games`

Store the complete resolved fingerprint as JSONB:

- `taxonomy_v2_fingerprint`

This should include the axis-level canonical values:

- `world_topology`
- `world_density`
- `session_shape`
- `perspective`
- `visual_presentation`
- `art_style`
- `pacing`
- `interface_control`
- `combat_presence`
- `combat_style`
- `combat_tempo`
- `combat_structure`
- `traversal_verbs`
- `progression_model`
- `challenge_model`
- `narrative_structure`
- `narrative_topic`
- `sports_theme`
- `vehicular_theme`
- `keyword_layer`
- `mechanics_structure`
- `rules_goals`
- `entity_interaction`
- `setting`
- `tone`
- `mode_profile`
- `content_model`
- `input_complexity`
- `hard_exclusions`
- `soft_penalties`

Reason:

- the schema will evolve
- some fields are arrays and multi-valued
- storing the whole fingerprint in JSONB avoids over-fragmenting the table
- debug tools can show the exact resolved fingerprint

### 4. Evidence table

Create a dedicated evidence table for provenance:

- `game_taxonomy_v2_evidence`

Suggested columns:

- `id`
- `game_id`
- `taxonomy_version`
- `field`
- `value`
- `source`
- `source_field`
- `confidence`
- `evidence_text`
- `curated`
- `created_at`

Optional columns:

- `weight`
- `conflict_group`
- `suppressed_by_rule`

Reason:

- debug output must explain where traits came from
- JSONB alone is awkward for evidence-level auditing
- audit commands will need to inspect evidence row by row

### 5. Optional materialized explanation payload

If debug latency becomes a problem, add:

- `taxonomy_v2_debug_payload` JSONB on `games`

This would be denormalized and optional. It is not required for phase 1.

## Why This Hybrid Model

### Why not only dedicated columns

That would create too much migration churn because the fingerprint is still evolving.

Problems:

- too many columns
- harder iteration
- brittle schema changes
- awkward storage for multi-valued fields

### Why not only JSONB

That would make query performance and filtering worse for the actual matcher.

Problems:

- harder to index effectively for candidate generation
- harder to keep core query paths simple
- poorer ergonomics for archetype-level filtering

### Why not only repo-managed docs

Because the API needs runtime-computed results and evidence-backed fingerprints for the whole catalog.

## Proposed DB Fields

### On `games`

Required:

- `taxonomy_v2_version text`
- `taxonomy_v2_status text`
- `taxonomy_v2_primary_family text`
- `taxonomy_v2_primary_archetype text`
- `taxonomy_v2_secondary_archetypes text[]`
- `taxonomy_v2_hard_exclusions text[]`
- `taxonomy_v2_soft_penalties text[]`
- `taxonomy_v2_confidence numeric`
- `taxonomy_v2_fingerprint jsonb`
- `taxonomy_v2_computed_at timestamptz`

Optional:

- `taxonomy_v2_curated boolean`
- `taxonomy_v2_debug_payload jsonb`

### Evidence table

Required:

- `game_taxonomy_v2_evidence`

Suggested indexes:

- `(game_id)`
- `(taxonomy_version, field, value)`
- `(source, source_field)`
- `(game_id, field)`

## Candidate Query Strategy

The similar-game API should not query deep JSONB for the hot path.

Use this general flow:

1. use `taxonomy_v2_primary_archetype` to find strong and adjacent candidate families
2. filter on indexed array fields like `taxonomy_v2_hard_exclusions`
3. load `taxonomy_v2_fingerprint` for the remaining candidate set
4. apply detailed compatibility rules in Python or SQL

That implies these indexed fields matter most:

- `taxonomy_v2_primary_archetype`
- `taxonomy_v2_secondary_archetypes`
- `taxonomy_v2_hard_exclusions`
- `taxonomy_v2_status`

## Versioning Model

Do not replace V1 in place.

Use explicit versioning:

- V1 remains live during migration
- V2 fields are added separately
- API can switch by version flag
- cache keys should include taxonomy version

Suggested statuses:

- `pending`
- `computed`
- `curated`
- `failed`
- `needs_review`

## Override Strategy

Phase 1 recommendation:

- keep overrides repo-managed
- key by `public_id`, `opencritic_id`, `steam_app_id`, `metacritic_slug`, or normalized title

Override data should support:

- add/replace fingerprint traits
- add/remove hard exclusions
- force primary archetype
- force secondary archetypes
- attach rationale text

Suggested file:

- `app/data/taxonomy_v2_overrides.json`

Reason:

- auditable diffs
- simple deployment
- enough for initial curated anchors

## Backfill Model

Backfill should be a separate CLI path:

- `taxonomy-v2-backfill`

It should:

1. gather source data
2. compute evidence
3. resolve conflicts
4. assign fingerprint
5. assign archetype
6. store canonical fields
7. store evidence rows

The backfill must be idempotent.

It should fully replace V2 rows for a given game on each recompute rather than trying to patch evidence incrementally.

## Debug Model

Debug tooling should read from:

- `games.taxonomy_v2_primary_archetype`
- `games.taxonomy_v2_fingerprint`
- `game_taxonomy_v2_evidence`

This enables:

- "why did this game get this archetype?"
- "why did candidate X match?"
- "which evidence caused this hard exclusion?"
- "what conflicting traits were suppressed?"

## Migration Phases

### Phase 1

Add:

- V2 fields on `games`
- evidence table

No cutover yet.

### Phase 2

Backfill a small anchor set only.

### Phase 3

Backfill full catalog.

### Phase 4

Switch debug tooling to V2.

### Phase 5

Switch Similar Games API to V2 after evaluation passes.

## Non-Goals

This design does not aim to:

- fully normalize every single axis into separate relational tables
- expose editorial management UI in phase 1
- allow arbitrary runtime ontology editing from the admin side

Those can be revisited later if taxonomy operations become too large for repo-managed files.

## Recommendation

Use:

- indexed canonical fields on `games`
- JSONB fingerprint on `games`
- dedicated evidence table
- repo-managed ontology and override files

That is the most pragmatic storage model for getting Taxonomy V2 built and validated without overengineering the first rollout.
