# Similar Games Taxonomy V2

## Purpose

The current similar-games system is too shallow. It primarily matches on broad shared metadata such as:

- `action`
- `adventure`
- `single-player`

That produces false positives that are technically tag-adjacent but not actually similar in play pattern, player fantasy, world structure, combat feel, or progression loop.

This document defines the replacement model for Similar Games:

- a structured gameplay fingerprint
- a canonical archetype graph
- explicit compatibility and exclusion rules
- a curation and evaluation workflow

The goal is to produce results like:

- `Crimson Desert` -> `The Witcher 3`, `Breath of the Wild`, `Elden Ring`, `Black Desert`

and not results like:

- `Crimson Desert` -> `Resident Evil Requiem`, `REANIMAL`, `High on Life 2`, `Romeo is a Dead Man`

## Why V1 Fails

V1 is a metadata-overlap system, not a gameplay-similarity system.

Current issues:

- broad store genres are treated as identity traits
- shared mode labels like `single-player` count too much
- source tags are unioned, not interpreted
- there is no archetype-family model
- there are no hard negatives for obvious genre-family mismatches
- there is little to no curated override coverage
- the matcher reasons about tags, not about what the player is actually doing

That makes the system good at finding games that look similar in store metadata and bad at finding games that feel similar to play.

## Design Goals

Taxonomy V2 should optimize for:

- playable identity, not raw tag overlap
- high precision over high recall
- deterministic rules before heuristic weighting
- transparent debugability
- source provenance on every inferred trait
- explicit curation for anchor and edge-case titles
- versioned rollout so V2 can coexist with V1 while being evaluated

## Core Model

V2 uses two linked models:

1. `Gameplay Fingerprint`
   Describes what the game is and how it is played.

2. `Archetype Graph`
   Defines which archetypes are strong neighbors, adjacent neighbors, or invalid neighbors.

The fingerprint says:

- "What kind of game is this?"
- "How is it played?"
- "What player fantasy does it deliver?"

The graph says:

- "What kinds of games can this reasonably match?"
- "What kinds of games must never match?"

## Gameplay Fingerprint Schema

Each game should have a structured fingerprint with canonical enum values, source evidence, confidence, and curation flags.

### Primary Identity

- `primary_family`
  High-level family such as `rpg`, `action_adventure`, `shooter`, `horror`, `strategy`, `simulation`

- `primary_archetype`
  The single best canonical gameplay node for the game

- `secondary_archetypes`
  Up to 3 nearby nodes that capture meaningful adjacency

### World and Session Structure

- `world_topology`
  - `open_world`
  - `semi_open`
  - `hub_and_spoke`
  - `linear`
  - `mission_based`
  - `level_based`
  - `node_map`
  - `run_based`
  - `persistent_shared_world`

- `world_density`
  - `handcrafted_discovery`
  - `systemic_sandbox`
  - `dungeon_driven`
  - `setpiece_driven`
  - `city_dense`
  - `sparse_expanse`

- `session_shape`
  - `campaign`
  - `mission_session`
  - `match_session`
  - `roguelite_run`
  - `raid_session`
  - `sandbox_loop`
  - `seasonal_live_service`

### Camera and Combat

- `perspective`
  - `first_person`
  - `third_person`
  - `isometric`
  - `top_down`
  - `side_scrolling`
  - `tactical_overhead`
  - `fixed_camera`

- `visual_presentation`
  - `side_scrolling_2d`
  - `third_person_3d`
  - `isometric_view`
  - `top_down_view`

- `art_style`
  - `pixel_art`
  - `hand_drawn`
  - `anime`
  - `stylized`
  - `retro`
  - `photorealistic`

- `pacing`
  - `long_form_campaign`
  - `fast_arcade`
  - `methodical_tension`
  - `relaxed_sandbox`

- `interface_control`
  - `cursor_driven`
  - `deck_management`
  - `party_command`
  - `vehicle_control`
  - `timing_input`

- `combat_presence`
  - `none`
  - `light`
  - `moderate`
  - `dominant`

- `combat_style`
  - `melee`
  - `ranged`
  - `magic`
  - `hybrid`
  - `stealth`
  - `party_tactics`
  - `shooter`
  - `survival`

- `combat_tempo`
  - `deliberate`
  - `methodical`
  - `tactical`
  - `fast`
  - `combo_driven`
  - `twitch`

- `combat_structure`
  - `boss_centric`
  - `encounter_driven`
  - `crowd_control`
  - `duel_focused`
  - `systemic_emergent`
  - `cover_shooter`
  - `party_management`

### Traversal and Progression

- `traversal_verbs`
  - `horseback`
  - `climbing`
  - `gliding`
  - `grappling`
  - `driving`
  - `sailing`
  - `flying`
  - `parkour`
  - `platforming`
  - `teleportation`

- `progression_model`
  - `quest_driven`
  - `buildcraft`
  - `gear_chase`
  - `loot_rarity`
  - `craft_survive`
  - `base_growth`
  - `colony_growth`
  - `deck_growth`
  - `relationship_social`
  - `skill_tree`
  - `metaprogression`
  - `extraction_economy`

- `challenge_model`
  - `soulslike`
  - `survival_attrition`
  - `precision_platforming`
  - `tactical_optimization`
  - `puzzle_gating`
  - `sim_realism`
  - `forgiving_adventure`

### Narrative, Setting, Tone

- `narrative_structure`
  - `authored_linear`
  - `authored_branching`
  - `quest_web`
  - `emergent_systemic`
  - `sandbox_light`
  - `run_lore`

- `narrative_topic`
  - `crime_heist`
  - `detective_mystery`
  - `survival_escape`
  - `branching_choices`
  - `heroic_journey`
  - `monster_bonding`

- `keyword_layer`
  - `open_world_exploration`
  - `immersive_sim`
  - `hidden_object`
  - `point_and_click`
  - `monster_taming`
  - `deckbuilding`
  - `psychological_horror`
  - `hero_shooter`
  - `real_time_tactics`
  - `pinball`
  - `rhythm`

- `mechanics_structure`
  - `quest_exploration_loop`
  - `party_management_loop`
  - `creature_collection`
  - `deck_construction`
  - `environmental_puzzle_solving`
  - `stealth_infiltration`
  - `vehicular_racing`
  - `match_competition`
  - `settlement_building`
  - `systemic_problem_solving`
  - `platform_navigation`
  - `real_time_command`
  - `rhythm_timing`
  - `score_attack`

- `rules_goals`
  - `complete_quests`
  - `win_matches`
  - `win_races`
  - `capture_and_raise_companions`
  - `solve_mysteries`
  - `build_and_optimize`
  - `infiltrate_avoid_detection`
  - `defeat_bosses`
  - `clear_stages`
  - `hit_beats`

- `entity_interaction`
  - `party_control`
  - `dialogue_choice`
  - `creature_collection`
  - `card_play`
  - `construction_placement`
  - `vehicle_control`
  - `cursor_driven_interaction`
  - `timing_input`

- `sports_theme`
  - `soccer`
  - `baseball`
  - `basketball`

- `vehicular_theme`
  - `cars`
  - `motorcycles`
  - `spaceships`

- `setting`
  - `high_fantasy`
  - `dark_fantasy`
  - `historical`
  - `modern`
  - `military`
  - `sci_fi`
  - `cyberpunk`
  - `post_apoc`
  - `horror`
  - `mythic`
  - `urban_fantasy`
  - `whimsical`

- `tone`
  - `serious`
  - `bleak`
  - `heroic`
  - `cozy`
  - `comedic`
  - `pulpy`
  - `grotesque`
  - `melancholic`

### Modes and Product Shape

- `mode_profile`
  - `single_player`
  - `drop_in_coop`
  - `party_coop`
  - `mmo`
  - `pvp`
  - `pvpve`
  - `async_social`

- `content_model`
  - `premium_finite`
  - `premium_replayable`
  - `live_service`
  - `seasonal`
  - `mmo_persistent`

- `input_complexity`
  - `casual`
  - `moderate`
  - `mastery_heavy`

### Label Tiers

- `identity_driving`
  high-information labels and derived signals that should materially affect matching

- `supporting`
  broad or low-specificity labels that help context but should not define similarity alone

- `filter_only`
  store features, platform metadata, packaging, and other non-similarity metadata

### Match Guards

- `hard_exclusions`
  Traits that should immediately block a match

- `soft_penalties`
  Traits that should strongly demote but not always fully block

Examples:

- `fps_only`
- `pure_survival_horror`
- `mission_based_only`
- `match_based_only`
- `comedy_shooter`
- `non_combat`
- `sports_sim`

## Evidence Model

Every inferred fingerprint trait should carry provenance.

Example:

```json
{
  "field": "traversal_verbs",
  "value": "horseback",
  "confidence": 0.91,
  "sources": ["description", "steam_tags", "curated_override"],
  "evidence": ["rides across Pywel", "mount traversal"],
  "curated": false,
  "version": "taxonomy_v2"
}
```

This is necessary for:

- auditability
- debugging
- manual review
- future model improvements

## Archetype Node Schema

Each archetype node should declare:

- `id`
- `family`
- `required_axes`
- `preferred_axes`
- `strong_neighbors`
- `adjacent_neighbors`
- `blocked_neighbors`
- `hard_exclusions`

Example:

```json
{
  "id": "open_world_fantasy_action_rpg",
  "family": "rpg",
  "required_axes": {
    "world_topology": ["open_world"],
    "perspective": ["third_person"],
    "combat_presence": ["dominant"],
    "combat_style": ["melee", "hybrid", "magic"],
    "progression_model": ["quest_driven", "buildcraft", "gear_chase"],
    "setting": ["high_fantasy", "dark_fantasy"]
  },
  "preferred_axes": {
    "traversal_verbs": ["horseback", "climbing", "gliding"],
    "tone": ["serious", "heroic", "bleak"]
  },
  "strong_neighbors": [
    "western_narrative_rpg",
    "soulslike_action_rpg",
    "open_world_action_adventure"
  ],
  "adjacent_neighbors": [
    "mmo_action_rpg",
    "loot_action_rpg",
    "monster_hunter_style_action_rpg"
  ],
  "blocked_neighbors": [
    "survival_horror",
    "military_fps",
    "hero_shooter",
    "city_builder",
    "management_tycoon"
  ],
  "hard_exclusions": [
    "fps_only",
    "pure_survival_horror",
    "match_based_only",
    "comedy_shooter"
  ]
}
```

## Initial Archetype Library

The first pass should target at least these 40 nodes.

### RPG

- `open_world_fantasy_action_rpg`
- `soulslike_action_rpg`
- `western_narrative_rpg`
- `party_based_crpg`
- `jrpg_story_rpg`
- `tactical_rpg`
- `monster_collect_rpg`
- `loot_action_rpg`
- `monster_hunter_style_action_rpg`
- `mmo_action_rpg`

### Action Adventure

- `open_world_action_adventure`
- `cinematic_action_adventure`
- `stealth_action_adventure`
- `immersive_sim_action`
- `character_action`

### Horror

- `survival_horror`
- `action_horror`
- `psychological_horror`
- `co_op_horror`

### Shooters

- `military_fps`
- `arena_fps`
- `hero_shooter`
- `loot_shooter`
- `extraction_shooter`
- `tactical_shooter`
- `third_person_cover_shooter`

### Platformers

- `metroidvania`
- `precision_platformer`
- `action_platformer`
- `3d_collectathon`

### Strategy

- `rts`
- `grand_strategy`
- `4x_strategy`
- `turn_based_tactics`

### Simulation / Management

- `city_builder`
- `colony_sim`
- `factory_builder`
- `management_tycoon`
- `life_sim`
- `farming_sim`

## Archetype Graph Draft

### RPG

- `open_world_fantasy_action_rpg`
  - req: `open_world`, `third_person`, `dominant` combat, `melee/hybrid/magic`, `quest_driven/buildcraft/gear_chase`, `high_fantasy/dark_fantasy`
  - strong: `western_narrative_rpg`, `soulslike_action_rpg`, `open_world_action_adventure`
  - adjacent: `mmo_action_rpg`, `loot_action_rpg`, `monster_hunter_style_action_rpg`
  - blocked: `survival_horror`, `military_fps`, `hero_shooter`, `city_builder`, `management_tycoon`

- `soulslike_action_rpg`
  - req: `third_person`, `dominant` combat, `melee/hybrid`, `deliberate/methodical`, `soulslike`, `boss_centric`, `dark_fantasy/mythic`
  - strong: `open_world_fantasy_action_rpg`, `character_action`
  - adjacent: `western_narrative_rpg`, `action_horror`, `monster_hunter_style_action_rpg`
  - blocked: `hero_shooter`, `co_op_horror`, `life_sim`, `arcade_racer`

- `western_narrative_rpg`
  - req: `campaign`, `third_person/isometric`, `quest_driven`, `authored_branching/quest_web`, `serious/heroic/bleak`
  - strong: `open_world_fantasy_action_rpg`, `party_based_crpg`
  - adjacent: `soulslike_action_rpg`, `open_world_action_adventure`, `jrpg_story_rpg`
  - blocked: `extraction_shooter`, `survival_horror`, `sports_sim`, `party_game`

- `party_based_crpg`
  - req: `isometric/tactical_overhead`, `party_tactics`, `tactical`, `quest_driven/buildcraft`, `authored_branching/quest_web`
  - strong: `western_narrative_rpg`, `tactical_rpg`
  - adjacent: `jrpg_story_rpg`, `turn_based_tactics`
  - blocked: `arena_fps`, `character_action`, `arcade_racer`, `platformer`

- `jrpg_story_rpg`
  - req: `campaign`, `party_management/encounter_driven`, `quest_driven/skill_tree`, `authored_linear`, `heroic`
  - strong: `western_narrative_rpg`, `monster_collect_rpg`
  - adjacent: `tactical_rpg`, `party_based_crpg`
  - blocked: `military_fps`, `city_builder`, `extraction_shooter`

- `tactical_rpg`
  - req: `tactical_overhead/isometric`, `party_tactics`, `tactical`, `skill_tree/buildcraft`, `campaign`
  - strong: `turn_based_tactics`, `party_based_crpg`
  - adjacent: `jrpg_story_rpg`, `western_narrative_rpg`
  - blocked: `arena_fps`, `3d_collectathon`, `sports_sim`

- `monster_collect_rpg`
  - req: `campaign`, `party_management`, `collection/progression`, `heroic/whimsical`
  - strong: `jrpg_story_rpg`
  - adjacent: `western_narrative_rpg`, `tactical_rpg`
  - blocked: `survival_horror`, `military_fps`, `city_builder`

- `loot_action_rpg`
  - req: `dominant` combat, `gear_chase/loot_rarity/buildcraft`, `encounter_driven`, `premium_replayable/live_service`
  - strong: `mmo_action_rpg`, `monster_hunter_style_action_rpg`
  - adjacent: `open_world_fantasy_action_rpg`, `soulslike_action_rpg`, `loot_shooter`
  - blocked: `walking_sim`, `city_builder`, `deckbuilder`

- `monster_hunter_style_action_rpg`
  - req: `third_person`, `boss_centric`, `gear_chase/buildcraft`, `mission_session/hub_and_spoke`, `mastery_heavy`
  - strong: `loot_action_rpg`
  - adjacent: `open_world_fantasy_action_rpg`, `soulslike_action_rpg`, `mmo_action_rpg`
  - blocked: `military_fps`, `life_sim`, `management_tycoon`

- `mmo_action_rpg`
  - req: `persistent_shared_world`, `mmo`, `gear_chase/buildcraft`, `live_service/mmo_persistent`, `third_person`
  - strong: `loot_action_rpg`
  - adjacent: `open_world_fantasy_action_rpg`, `monster_hunter_style_action_rpg`, `western_narrative_rpg`
  - blocked: `survival_horror`, `precision_platformer`, `walking_sim`

### Action Adventure

- `open_world_action_adventure`
  - req: `open_world`, `third_person`, `moderate/dominant` combat, `quest_driven`, `handcrafted_discovery`
  - strong: `open_world_fantasy_action_rpg`, `cinematic_action_adventure`
  - adjacent: `western_narrative_rpg`, `stealth_action_adventure`, `character_action`
  - blocked: `survival_horror`, `hero_shooter`, `city_builder`

- `cinematic_action_adventure`
  - req: `linear/semi_open`, `third_person`, `setpiece_driven`, `authored_linear`, `serious/heroic`
  - strong: `open_world_action_adventure`, `character_action`
  - adjacent: `stealth_action_adventure`, `western_narrative_rpg`
  - blocked: `grand_strategy`, `city_builder`, `extraction_shooter`

- `stealth_action_adventure`
  - req: `stealth`, `third_person/first_person`, `encounter_driven/systemic_emergent`, `mission_based/semi_open`
  - strong: `immersive_sim_action`
  - adjacent: `open_world_action_adventure`, `cinematic_action_adventure`, `third_person_cover_shooter`
  - blocked: `arena_fps`, `party_game`, `sports_sim`

- `immersive_sim_action`
  - req: `systemic_emergent`, `first_person/third_person`, `stealth/hybrid`, `hub_and_spoke/semi_open`
  - strong: `stealth_action_adventure`
  - adjacent: `open_world_action_adventure`, `third_person_cover_shooter`, `western_narrative_rpg`
  - blocked: `hero_shooter`, `precision_platformer`, `card_battler`

- `character_action`
  - req: `third_person`, `combo_driven/fast`, `dominant` combat, `setpiece_driven/mission_based`, `mastery_heavy`
  - strong: `cinematic_action_adventure`, `soulslike_action_rpg`
  - adjacent: `open_world_action_adventure`, `action_horror`
  - blocked: `party_based_crpg`, `city_builder`, `life_sim`

### Horror

- `survival_horror`
  - req: `horror`, `survival`, `resource pressure`, `bleak/grotesque`, `encounter_driven`
  - strong: `psychological_horror`, `action_horror`
  - adjacent: `co_op_horror`
  - blocked: `open_world_fantasy_action_rpg`, `hero_shooter`, `life_sim`, `3d_collectathon`

- `action_horror`
  - req: `horror`, `dominant` combat, `third_person/first_person`, `encounter_driven`, `bleak/grotesque`
  - strong: `survival_horror`
  - adjacent: `soulslike_action_rpg`, `co_op_horror`, `character_action`
  - blocked: `party_game`, `farming_sim`, `sports_sim`

- `psychological_horror`
  - req: `horror`, `light/moderate` combat, `atmosphere-first`, `linear/semi_open`, `bleak/melancholic`
  - strong: `survival_horror`
  - adjacent: `action_horror`, `detective_adventure`
  - blocked: `open_world_action_adventure`, `arena_fps`, `life_sim`

- `co_op_horror`
  - req: `party_coop/drop_in_coop`, `horror`, `encounter_driven`, `run_based/mission_session`
  - strong: `action_horror`
  - adjacent: `survival_horror`, `extraction_shooter`
  - blocked: `western_narrative_rpg`, `city_builder`, `farming_sim`

### Shooters

- `military_fps`
  - req: `first_person`, `shooter`, `twitch/tactical`, `mission_based/match_session`, `military`
  - strong: `tactical_shooter`, `third_person_cover_shooter`
  - adjacent: `loot_shooter`, `extraction_shooter`
  - blocked: `party_based_crpg`, `city_builder`, `life_sim`, `survival_horror`

- `arena_fps`
  - req: `first_person`, `shooter`, `fast/twitch`, `match_session`
  - strong: `hero_shooter`
  - adjacent: `military_fps`
  - blocked: `western_narrative_rpg`, `management_tycoon`, `survival_horror`

- `hero_shooter`
  - req: `match_session`, `shooter`, `class-based`, `pvp/pvpve`, `fast/tactical`
  - strong: `arena_fps`
  - adjacent: `military_fps`, `loot_shooter`
  - blocked: `open_world_fantasy_action_rpg`, `western_narrative_rpg`, `city_builder`, `life_sim`

- `loot_shooter`
  - req: `shooter`, `gear_chase/loot_rarity/buildcraft`, `premium_replayable/live_service`, `mission_session/open_zones`
  - strong: `extraction_shooter`, `loot_action_rpg`
  - adjacent: `military_fps`, `hero_shooter`, `third_person_cover_shooter`
  - blocked: `walking_sim`, `city_builder`, `party_game`

- `extraction_shooter`
  - req: `shooter`, `extraction_economy`, `pvpve`, `mission_session`, `high tension loss loop`
  - strong: `tactical_shooter`, `loot_shooter`
  - adjacent: `military_fps`, `co_op_horror`
  - blocked: `western_narrative_rpg`, `city_builder`, `farming_sim`, `traditional_fighter`

- `tactical_shooter`
  - req: `shooter`, `tactical/methodical`, `military/modern`, `match_session/mission_session`
  - strong: `military_fps`, `extraction_shooter`
  - adjacent: `third_person_cover_shooter`, `loot_shooter`
  - blocked: `character_action`, `jrpg_story_rpg`, `life_sim`

- `third_person_cover_shooter`
  - req: `third_person`, `cover_shooter`, `ranged`, `mission_based/semi_open`, `encounter_driven`
  - strong: `military_fps`
  - adjacent: `tactical_shooter`, `loot_shooter`, `stealth_action_adventure`
  - blocked: `survival_horror`, `city_builder`, `farming_sim`

### Platformers

- `metroidvania`
  - req: `side_scrolling`, `platforming`, `ability gating`, `exploration`, `handcrafted_discovery`
  - strong: `action_platformer`, `precision_platformer`
  - adjacent: `open_world_action_adventure`
  - blocked: `military_fps`, `city_builder`, `sports_sim`

- `precision_platformer`
  - req: `side_scrolling`, `platforming`, `precision_platforming`, `fast restart`, `mastery_heavy`
  - strong: `action_platformer`, `metroidvania`
  - adjacent: `3d_collectathon`
  - blocked: `mmo_action_rpg`, `grand_strategy`, `survival_horror`

- `action_platformer`
  - req: `platforming`, `combat_presence light/moderate`, `level_based/side_scrolling`, `encounter_driven`
  - strong: `metroidvania`, `precision_platformer`
  - adjacent: `3d_collectathon`, `character_action`
  - blocked: `tactical_shooter`, `city_builder`, `sports_sim`

- `3d_collectathon`
  - req: `third_person`, `platforming`, `collectathon`, `whimsical/heroic`, `level_based/semi_open`
  - strong: `action_platformer`
  - adjacent: `precision_platformer`, `open_world_action_adventure`
  - blocked: `survival_horror`, `military_fps`, `grand_strategy`

### Strategy

- `rts`
  - req: `tactical_overhead`, `real-time`, `base_growth/army control`, `systemic_emergent`
  - strong: `4x_strategy`
  - adjacent: `grand_strategy`, `turn_based_tactics`
  - blocked: `character_action`, `military_fps`, `precision_platformer`

- `grand_strategy`
  - req: `tactical_overhead`, `systemic_emergent`, `long-form campaign`, `sim_realism/tactical_optimization`
  - strong: `4x_strategy`
  - adjacent: `rts`, `management_tycoon`
  - blocked: `character_action`, `arena_fps`, `action_platformer`

- `4x_strategy`
  - req: `tactical_overhead`, `expansion/research/economy`, `long campaign`
  - strong: `grand_strategy`, `rts`
  - adjacent: `city_builder`, `turn_based_tactics`
  - blocked: `survival_horror`, `character_action`, `hero_shooter`

- `turn_based_tactics`
  - req: `tactical_overhead/isometric`, `tactical`, `encounter-driven maps`, `squad optimization`
  - strong: `tactical_rpg`
  - adjacent: `party_based_crpg`, `4x_strategy`
  - blocked: `arena_fps`, `3d_collectathon`, `farming_sim`

### Simulation / Management

- `city_builder`
  - req: `city_dense/systemic_sandbox`, `colony_growth/base_growth`, `management`, `long-form sandbox`
  - strong: `colony_sim`, `management_tycoon`
  - adjacent: `factory_builder`, `4x_strategy`
  - blocked: `survival_horror`, `military_fps`, `character_action`, `metroidvania`

- `colony_sim`
  - req: `systemic_sandbox`, `colony_growth`, `emergent_systemic`, `long-form sandbox`, `management`
  - strong: `city_builder`, `factory_builder`
  - adjacent: `management_tycoon`, `craft_survive`
  - blocked: `cinematic_action_adventure`, `traditional_fighter`, `arena_fps`

- `factory_builder`
  - req: `systemic_sandbox`, `optimization loops`, `long-form sandbox`, `moderate/high complexity`
  - strong: `colony_sim`, `city_builder`
  - adjacent: `management_tycoon`
  - blocked: `survival_horror`, `character_action`, `hero_shooter`

- `management_tycoon`
  - req: `management`, `economy optimization`, `sandbox/campaign`, `low or no combat`
  - strong: `city_builder`, `life_sim`
  - adjacent: `colony_sim`, `farming_sim`, `grand_strategy`
  - blocked: `soulslike_action_rpg`, `military_fps`, `action_horror`

- `life_sim`
  - req: `sandbox_light/systemic_sandbox`, `relationship_social`, `cozy`, `low/no combat`, `daily routines`
  - strong: `farming_sim`
  - adjacent: `management_tycoon`
  - blocked: `survival_horror`, `military_fps`, `soulslike_action_rpg`, `extraction_shooter`

- `farming_sim`
  - req: `cozy`, `daily loop`, `relationship_social/base_growth`, `low/light combat`, `sandbox_light`
  - strong: `life_sim`
  - adjacent: `management_tycoon`, `craft_survive`
  - blocked: `survival_horror`, `hero_shooter`, `grand_strategy`

## Matching Rules

Use deterministic filtering before weighted scoring.

### Hard filter

- candidate archetype must be in anchor `strong_neighbors` or `adjacent_neighbors`
- candidate must satisfy anchor `required_axes`
- any `blocked_neighbor` immediately invalidates the match
- any anchor `hard_exclusion` immediately invalidates the match

### Weighted ranking

- same `primary_archetype`: very high boost
- `strong_neighbor`: high boost
- `adjacent_neighbor`: moderate boost
- shared `world_topology`: high boost
- shared `combat_style`: high boost
- shared `combat_structure`: medium boost
- shared `progression_model`: high boost
- shared `traversal_verbs`: medium boost
- shared `setting`: medium boost
- shared `tone`: low/medium boost
- studio lineage: low tie-breaker only

### Explicitly not qualifying

These should never be enough by themselves:

- shared `single_player`
- shared broad genres like `action` or `adventure`
- shared release window
- shared critic network

## Extraction Strategy

V2 cannot rely only on store tags. It must infer gameplay identity from multiple evidence sources.

### Source inputs

- Steam genres
- Steam categories
- Steam tags
- Steam short description
- Steam detailed description
- OpenCritic tags and blurbs
- Metacritic metadata and blurbs
- official game descriptions already stored in `games.description`

### Extraction passes

1. raw metadata normalization
2. phrase-level description parsing
3. archetype inference
4. hard exclusion inference
5. curated override merge

### Example phrase mapping

- `open world`, `vast world`, `seamless world` -> `world_topology=open_world`
- `ride across`, `mount`, `horseback` -> `traversal_verbs=horseback`
- `climb`, `scale`, `traverse vertically` -> `traversal_verbs=climbing`
- `glide`, `airborne traversal` -> `traversal_verbs=gliding`
- `quest`, `story-driven quests`, `side quests` -> `progression_model=quest_driven`
- `build`, `equipment customization`, `skill build` -> `progression_model=buildcraft`
- `loot`, `rarity`, `gear score` -> `progression_model=gear_chase/loot_rarity`
- `grim`, `nightmarish`, `terror` -> `setting/tone=horror`
- `comedic`, `irreverent`, `humorous` -> `tone=comedic`
- `first-person shooter` -> `perspective=first_person`, `combat_style=shooter`, `hard_exclusions=fps_only`

## Crimson Desert Reference Classification

Target V2 fingerprint:

- `primary_family`: `rpg`
- `primary_archetype`: `open_world_fantasy_action_rpg`
- `secondary_archetypes`: `western_narrative_rpg`, `soulslike_action_rpg`, `mmo_action_rpg`
- `world_topology`: `open_world`
- `world_density`: `handcrafted_discovery`
- `perspective`: `third_person`
- `combat_presence`: `dominant`
- `combat_style`: `hybrid`
- `combat_tempo`: `fast`
- `combat_structure`: `encounter_driven`, `boss_centric`
- `traversal_verbs`: `horseback`, `climbing`, `gliding`
- `progression_model`: `quest_driven`, `buildcraft`, `gear_chase`
- `setting`: `high_fantasy`
- `tone`: `serious`, `heroic`
- `mode_profile`: `single_player`
- `hard_exclusions`: `fps_only`, `pure_survival_horror`, `mission_based_only`, `comedy_shooter`

Expected strong neighbors:

- `The Witcher 3`
- `Elden Ring`
- `Breath of the Wild`

Expected adjacent neighbor:

- `Black Desert`

Expected blocked neighbors:

- `Resident Evil Requiem`
- `REANIMAL`
- `High on Life 2`
- `Romeo is a Dead Man`

## Storage Model

V2 should be versioned separately from V1.

Suggested storage:

- raw source labels: existing source taxonomy table
- fingerprint values: JSONB or dedicated V2 columns
- archetype assignment: canonical node ids
- evidence records: per-field provenance
- curated overrides: repo-managed file plus optional DB layer later
- taxonomy version stamp: `taxonomy_v2`

## Evaluation Standard

Do not ship V2 based on anecdotal inspection alone.

Build a gold set of 100-200 anchor games:

- 3-5 expected neighbors per anchor
- 3-5 blocked neighbors per anchor
- evaluate precision at 5
- evaluate per archetype family, not only globally

Examples:

- `Crimson Desert`
  - expected: `The Witcher 3`, `Elden Ring`, `Breath of the Wild`, `Black Desert`
  - blocked: `Resident Evil Requiem`, `High on Life 2`

- `Resident Evil`
  - expected: survival-horror peers
  - blocked: open-world fantasy RPGs, hero shooters

## Rollout Plan

### Phase 1: Ontology

- define canonical enums
- define archetype nodes
- define adjacency graph
- define hard exclusions

### Phase 2: Evaluation Set

- curate anchor games
- define expected and blocked neighbors
- establish precision targets

### Phase 3: Extraction

- add V2 source mappings
- add description-based inference
- add evidence storage
- add debug tooling

### Phase 4: Curation

- curate top anchor and edge-case titles
- patch known false positives
- patch under-specified archetypes

### Phase 5: Validation

- backfill V2
- evaluate on gold set
- compare V1 vs V2 precision

### Phase 6: Cutover

- expose V2 through debug tooling first
- then switch similar-games API to V2
- keep V1 available behind a flag during transition

## Immediate Next Artifacts

The next implementation documents should be:

1. `archetype-graph.json`
   Canonical node definitions and adjacency graph

2. `fingerprint-extraction-rules.md`
   Mapping from source metadata and description phrases into V2 axes

3. `similar-games-gold-set.md`
   Anchor titles, expected neighbors, blocked neighbors

4. `taxonomy-v2-rollout-checklist.md`
   Backfill, evaluation, and cutover steps

## Non-Goals

These are explicitly not the objective of V2:

- maximizing result count
- using only broad storefront tags
- using release date as a similarity proxy
- using critic network as a meaningful similarity signal
- matching games purely because they are in the same commercial genre bucket

## Summary

Taxonomy V2 replaces broad metadata overlap with a gameplay-identity system:

- structured fingerprint
- canonical archetype graph
- explicit hard negatives
- source evidence
- curated evaluation

That is the necessary foundation if Similar Games is expected to return results like the `Crimson Desert` examples consistently across the catalog.
