# Similar Games Fingerprint Extraction Rules

## Purpose

This document defines how raw source data is transformed into the Similar Games Taxonomy V2 gameplay fingerprint.

It is the operational companion to:

- [similar-games-taxonomy-v2.md](/Users/lindbergbrandon/backend/docs/similar-games-taxonomy-v2.md)

Taxonomy V2 defines the target ontology. This document defines:

- which fields are extracted from each source
- how raw labels map into canonical fingerprint traits
- how description phrases are interpreted
- how evidence is scored
- how conflicting evidence is resolved
- how archetypes are assigned from the final fingerprint

## Current Source Inputs

These are the source inputs already available in the codebase today.

### Steam

Current extracted raw facets:

- `genres`
- `categories`
- `developers`
- `publishers`

Relevant implementation:

- [game_taxonomy.py](/Users/lindbergbrandon/backend/app/services/game_taxonomy.py)
- [steam.py](/Users/lindbergbrandon/backend/app/services/steam.py)

Currently available high-value Steam fields for V2:

- genre labels
- category labels
- app tags
- developer / publisher
- short description
- detailed game description if added

### OpenCritic

Current extracted raw facets:

- `genres`
- `platforms`
- `developers`
- `publishers`
- `tags` / `themes`

Relevant implementation:

- [game_taxonomy.py](/Users/lindbergbrandon/backend/app/services/game_taxonomy.py)
- [opencritic.py](/Users/lindbergbrandon/backend/app/services/opencritic.py)

Currently useful OpenCritic inputs:

- genre labels
- tag labels
- game description
- platform list

### Metacritic

Current extracted raw facets:

- `genres`
- `platforms`
- `developers`
- `publishers`
- `themes`

Relevant implementation:

- [game_taxonomy.py](/Users/lindbergbrandon/backend/app/services/game_taxonomy.py)
- [metacritic.py](/Users/lindbergbrandon/backend/app/services/metacritic.py)

Currently useful Metacritic inputs:

- genre labels
- platform labels
- theme-like labels from JSON-LD / keywords
- developer / publisher

### Internal Stored Description

The `games.description` field is already available and should be treated as a first-class input.

Relevant model:

- [models.py](/Users/lindbergbrandon/backend/app/models/models.py)

This field should become one of the highest-value inputs for gameplay identity because it often contains:

- world structure clues
- traversal verbs
- combat descriptors
- quest/progression framing
- setting and tone language

## Source Reliability Tiers

Not all evidence should be treated equally.

### Tier 1: Official gameplay identity evidence

Use with highest confidence.

- official game descriptions
- official gameplay feature copy
- Steam short / detailed descriptions
- publisher-owned site copy

This is the best source for:

- world topology
- traversal verbs
- progression model
- setting
- tone
- combat structure

### Tier 2: Explicit structured metadata

Use with high confidence, but below direct descriptive prose.

- Steam genres
- Steam categories
- OpenCritic genres
- OpenCritic tags
- Metacritic genres
- platform labels

This is best for:

- mode profile
- broad family assignment
- perspective when explicit
- challenge model if directly labeled

### Tier 3: Weak commercial labels

Use only as supporting evidence.

- broad tags like `action`
- broad tags like `adventure`
- generic platform labels
- weak marketing descriptors

These should never define similarity on their own.

### Label Role Tiers

Every normalized label should also be classified into a role tier:

- `identity_driving`
  labels and derived signals that should materially affect similarity

- `supporting`
  broad descriptors that help context but should not dominate ranking

- `filter_only`
  store features, platform metadata, service labels, edition/package labels, and other non-similarity metadata

## Extraction Pipeline

V2 extraction should happen in this order:

1. Collect raw source fields.
2. Normalize text and remove junk fragments.
3. Convert explicit source labels into canonical evidence.
4. Parse descriptions for gameplay phrases.
5. Aggregate evidence into axis-level confidence scores.
6. Infer hard exclusions and soft penalties.
7. Assign primary and secondary archetypes.
8. Merge curated overrides.
9. Store the final fingerprint with evidence provenance.

## Canonical Evidence Rules

Each raw input becomes one or more evidence records.

An evidence record should contain:

- `field`
- `value`
- `source`
- `source_field`
- `confidence`
- `evidence_text`
- `curated`
- `version`

## Direct Label Mapping Rules

These rules apply when the source label is explicit enough to map directly.

### World Topology

Direct mappings:

- `open world` -> `world_topology=open_world`
- `open-world` -> `world_topology=open_world`
- `sandbox` -> `world_density=systemic_sandbox`
- `mission based` -> `world_topology=mission_based`
- `mission-based` -> `world_topology=mission_based`
- `hub` -> `world_topology=hub_and_spoke`
- `roguelike` / `roguelite` -> `world_topology=run_based`, `session_shape=roguelite_run`
- `mmo` -> `world_topology=persistent_shared_world`

### Perspective

Direct mappings:

- `first-person shooter` -> `perspective=first_person`, `combat_style=shooter`
- `third-person shooter` -> `perspective=third_person`, `combat_style=shooter`
- `isometric` -> `perspective=isometric`
- `top-down` -> `perspective=top_down`
- `side-scrolling` -> `perspective=side_scrolling`
- `fixed camera` -> `perspective=fixed_camera`

### Combat Style

Direct mappings:

- `action rpg` -> `combat_style=hybrid`
- `soulslike` -> `challenge_model=soulslike`, `combat_tempo=deliberate`
- `stealth` -> `combat_style=stealth`
- `fps` -> `combat_style=shooter`, `perspective=first_person`
- `turn-based tactics` -> `combat_style=party_tactics`, `combat_tempo=tactical`
- `survival horror` -> `combat_style=survival`, `setting=horror`

### Mode Profile

Steam category style mappings:

- `single-player` -> `mode_profile=single_player`
- `co-op` / `online co-op` / `local co-op` -> `mode_profile=drop_in_coop` or `party_coop`
- `multiplayer` -> `mode_profile=pvp` or generic multiplayer evidence
- `mmo` -> `mode_profile=mmo`
- `pvp` / `online pvp` -> `mode_profile=pvp`
- `pvpve` -> `mode_profile=pvpve`

### Product Shape

Mappings:

- `live service` -> `content_model=live_service`
- `seasonal` -> `content_model=seasonal`
- `persistent world` -> `content_model=mmo_persistent`
- `premium` campaign language -> `content_model=premium_finite`

## Description Phrase Rules

Description parsing is the main upgrade over V1. It should drive identity traits.

Rules should be phrase-pattern based, not just keyword-only.

### World Topology Phrases

Map phrases like:

- `vast open world`
- `seamless world`
- `explore a sprawling land`
- `across the kingdom`
- `venture across`

To:

- `world_topology=open_world`
- `world_density=handcrafted_discovery`

Map phrases like:

- `mission-based action`
- `take on contracts`
- `select missions`

To:

- `world_topology=mission_based`
- `session_shape=mission_session`

### Traversal Phrase Rules

Map phrases like:

- `ride horseback`
- `mounted travel`
- `on horseback`

To:

- `traversal_verbs=horseback`

Map phrases like:

- `climb cliffs`
- `scale walls`
- `vertical traversal`

To:

- `traversal_verbs=climbing`

Map phrases like:

- `glide`
- `take to the skies`
- `airborne traversal`

To:

- `traversal_verbs=gliding`

Map phrases like:

- `parkour`
- `free-run`
- `wall-run`

To:

- `traversal_verbs=parkour`

### Combat Phrase Rules

Map phrases like:

- `sword and sorcery`
- `melee and magic`
- `mix of melee and ranged combat`

To:

- `combat_style=hybrid`

Map phrases like:

- `precise timing`
- `punishing combat`
- `stamina-based combat`

To:

- `challenge_model=soulslike`
- `combat_tempo=deliberate`

Map phrases like:

- `cover-based combat`
- `take cover`

To:

- `combat_structure=cover_shooter`

Map phrases like:

- `squad-based battles`
- `command your party`

To:

- `combat_style=party_tactics`
- `combat_structure=party_management`

### Progression Phrase Rules

Map phrases like:

- `embark on quests`
- `story quests and side quests`
- `choice-driven quests`

To:

- `progression_model=quest_driven`
- `narrative_structure=quest_web` or `authored_branching`

Map phrases like:

- `customize your build`
- `tailor your playstyle`
- `skill tree`

To:

- `progression_model=buildcraft`
- `progression_model=skill_tree`

Map phrases like:

- `collect gear`
- `loot rare items`
- `upgrade equipment`

To:

- `progression_model=gear_chase`
- `progression_model=loot_rarity`

Map phrases like:

- `build your base`
- `grow your settlement`
- `manage colonists`

To:

- `progression_model=base_growth`
- `progression_model=colony_growth`

### Setting and Tone Phrase Rules

Map phrases like:

- `fantasy realm`
- `mythic kingdom`
- `ancient magic`

To:

- `setting=high_fantasy` or `mythic`

Map phrases like:

- `grim`
- `ruined world`
- `bleak`
- `despair`

To:

- `tone=bleak`

Map phrases like:

- `lighthearted`
- `wacky`
- `irreverent`
- `humorous`

To:

- `tone=comedic`

Map phrases like:

- `terror`
- `nightmarish`
- `grotesque creatures`

To:

- `setting=horror`
- `tone=grotesque`

## Hard Exclusion Inference

Some extracted traits should create direct blocks.

### Hard exclusion examples

- `first-person shooter only` -> `hard_exclusions=fps_only`
- `survival horror` -> `hard_exclusions=pure_survival_horror`
- `comedic shooter` -> `hard_exclusions=comedy_shooter`
- `mission-based action only` -> `hard_exclusions=mission_based_only`
- `match-based arena` -> `hard_exclusions=match_based_only`
- `non-combat narrative game` -> `hard_exclusions=non_combat`
- `sports simulation` -> `hard_exclusions=sports_sim`

These should never be inferred from a single weak commercial tag. They need either:

- explicit structured labels
- strong descriptive phrases
- manual override

## Confidence Model

Each inferred trait should carry a confidence score.

Suggested confidence guide:

- `0.95-1.00`
  Explicit official gameplay description or curated override

- `0.80-0.94`
  Strong structured metadata, or repeated corroborated description phrases

- `0.60-0.79`
  Weak but plausible inference from generic labels plus description support

- `<0.60`
  Should not determine archetype assignment alone

### Confidence promotion

Increase confidence when:

- multiple sources agree
- structured labels agree with description phrases
- curated override confirms the same trait

### Confidence suppression

Decrease confidence when:

- evidence comes only from generic tags
- wording is highly ambiguous
- another source strongly contradicts the trait

## Conflict Resolution

Conflicts are expected and must be deterministic.

### Precedence

Use this precedence order:

1. curated override
2. official description / internal stored description
3. explicit structured metadata
4. weak commercial tags

### Conflict examples

- `single-player` + `mmo`
  Resolve by checking source reliability and product shape. `mmo` should win if official description indicates a shared persistent world.

- `action adventure` + `survival horror`
  `survival_horror` should dominate because it is more specific and should generate a hard exclusion for fantasy-RPG style neighbors.

- `open world` + `mission-based`
  Allow both if evidence indicates an open zone structure, otherwise use the higher-confidence source and demote the weaker one.

### Specificity wins

When two values conflict, prefer the more specific one:

- `survival_horror` over `action`
- `soulslike` over generic `action_rpg`
- `extraction_shooter` over generic `shooter`

## Archetype Assignment Rules

After axis extraction, assign archetypes from the final fingerprint.

### Assignment order

1. assign `primary_family`
2. score all archetype nodes in that family
3. require all node `required_axes`
4. score node matches by `preferred_axes`
5. subtract score for soft penalties
6. block any node invalidated by hard exclusions
7. choose best node as `primary_archetype`
8. keep close valid runners-up as `secondary_archetypes`

### Secondary archetype policy

Secondary archetypes should only be kept when they are meaningful neighbors, not because the model is uncertain.

Good example:

- `Crimson Desert`
  - primary: `open_world_fantasy_action_rpg`
  - secondary: `western_narrative_rpg`, `soulslike_action_rpg`, `mmo_action_rpg`

Bad example:

- adding `survival_horror` just because a game is dark and has combat

## Example: Crimson Desert

This is the kind of extraction V2 should produce.

### Evidence

- world phrases indicating a large traversable world
- traversal phrases indicating horseback travel, climbing, gliding
- combat language indicating third-person melee/ranged hybrid action
- quest / story language indicating quest-driven progression
- fantasy language indicating `high_fantasy`
- serious heroic framing

### Fingerprint

- `primary_family=rpg`
- `primary_archetype=open_world_fantasy_action_rpg`
- `secondary_archetypes=western_narrative_rpg,soulslike_action_rpg,mmo_action_rpg`
- `world_topology=open_world`
- `world_density=handcrafted_discovery`
- `perspective=third_person`
- `combat_presence=dominant`
- `combat_style=hybrid`
- `combat_tempo=fast`
- `combat_structure=encounter_driven,boss_centric`
- `traversal_verbs=horseback,climbing,gliding`
- `progression_model=quest_driven,buildcraft,gear_chase`
- `setting=high_fantasy`
- `tone=serious,heroic`
- `mode_profile=single_player`
- `hard_exclusions=fps_only,pure_survival_horror,mission_based_only,comedy_shooter`

### Expected neighbors

- `The Witcher 3`
- `Breath of the Wild`
- `Elden Ring`
- `Black Desert` as an adjacent rather than identical neighbor

### Blocked

- `Resident Evil Requiem`
- `REANIMAL`
- `High on Life 2`
- `Romeo is a Dead Man`

## Debug Output Requirements

V2 debug tooling should explain:

- which traits were inferred
- where they came from
- which archetype won
- why the candidate archetype qualified
- why rejected candidates failed

Example reject messages:

- `rejected: blocked neighbor (survival_horror vs open_world_fantasy_action_rpg)`
- `rejected: perspective mismatch (first_person vs required third_person)`
- `rejected: mission_based_only hard exclusion`
- `rejected: no overlap in progression or traversal profile`

## Curation Workflow

Extraction rules alone will not be sufficient.

Use three curation layers:

1. ontology rules
2. source extraction rules
3. game-specific overrides

Overrides should be used for:

- flagship anchors
- ambiguous multi-genre titles
- known false positives
- series entries that differ from genre assumptions

## Rollout Notes

This ruleset should be implemented only as part of Taxonomy V2.

Do not continue patching V1 heuristics with more broad tags. The extraction rules in this document assume:

- archetype-family matching
- explicit hard negatives
- evidence provenance
- versioned fingerprint storage

## Immediate Next Artifacts

After this document, the next useful design docs are:

1. `similar-games-gold-set.md`
   Anchor games with expected and blocked neighbors

2. `taxonomy-v2-rollout-checklist.md`
   Storage, backfill, validation, and cutover checklist

3. `archetype-graph.json`
   Machine-readable version of the archetype graph
