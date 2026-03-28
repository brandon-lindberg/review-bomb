# Taxonomy V2 Steam Label Parity

## Purpose

This document defines the minimum label-bank baseline for Similar Games Taxonomy V2.

The requirement is:

- at minimum, V2 must cover the same gameplay-relevant label space that Steam exposes
- above that baseline, V2 should infer a smaller set of stronger internal labels that are more useful for similarity than raw storefront tags

This is not a code patch. It is the reference for the next round of taxonomy expansion.

## Decision

V2 should adopt a two-layer label model:

1. Steam-parity label bank
2. Derived internal labels

The Steam-parity label bank is the minimum interoperability layer.

The derived internal labels are the higher-signal layer used for actual similar-game matching.

## Why Steam Must Be The Baseline

Steam is the strongest practical public label vocabulary available to us because:

- Valve already maintains a large approved tag system for genres, sub-genres, viewpoints, themes, features, and player modes
- Steam explicitly uses tags to determine browse placement and which games are "most like" each other
- many of the lanes currently missing in V2 already exist as official Steam tags

Examples that the current V2 system is missing or underusing:

- `Pinball`
- `Minigames`
- `2D Platformer`
- `3D Platformer`
- `Precision Platformer`
- `Soccer`
- `Automobile Sim`
- `Real Time Tactics`
- `Metroidvania`
- `Life Sim`
- `Hidden Object`
- `Card Battler`
- `Immersive Sim`
- `Heist`
- `Crime`
- `Job Simulator`
- `2D Fighter`
- `3D Fighter`
- `Beat 'em up`
- `Survival Horror`

## Steam-Parity Scope

The minimum parity target should cover all gameplay-relevant approved Steam tags in these families:

- top-level genres
- genres
- sub-genres
- visuals and viewpoint
- themes and moods
- features
- players
- other game-relevant tags

The parity target does not need to include software-only tags such as:

- `Web Publishing`
- `Audio Production`
- `Utilities`

It also does not need to use ratings/content tags like `Nudity` or `Violent` as similarity drivers, though we may still store them.

## Official Steam Label Families

The official Steam tag table already contains the missing lanes we need.

### Core gameplay labels

- `Pinball`
- `Platformer`
- `Rhythm`
- `RTS`
- `Soccer`
- `Stealth`
- `Hidden Object`
- `Management`
- `Walking Simulator`
- `Action-Adventure`
- `Party-Based RPG`

### Sub-genres

- `2D Fighter`
- `3D Fighter`
- `2D Platformer`
- `3D Platformer`
- `Beat 'em up`
- `Card Battler`
- `City Builder`
- `Colony Sim`
- `CRPG`
- `Immersive Sim`
- `JRPG`
- `Life Sim`
- `Metroidvania`
- `Open World Survival Craft`
- `Precision Platformer`
- `Real Time Tactics`
- `Roguelite`
- `Runner`
- `Souls-like`
- `Spectacle fighter`
- `Survival Horror`
- `Tactical RPG`
- `Third-Person Shooter`
- `Time Management`
- `Trading Card Game`
- `Turn-Based Tactics`
- `Wargame`

### Viewpoint / presentation

- `First-Person`
- `Third Person`
- `Top-Down`
- `Isometric`
- `Side Scroller`
- `2D`
- `2.5D`
- `3D`

### Themes / moods / subject matter

- `Crime`
- `Heist`
- `Fantasy`
- `Dark Fantasy`
- `Horror`
- `Mystery`
- `Investigation`
- `Logic`
- `Management`
- `Stealth`
- `Survival`
- `Swordplay`
- `Tactical`
- `Horses`
- `Cats`
- `Superhero`

### Features / mechanics

- `Deckbuilding`
- `Driving`
- `Building`
- `Crafting`
- `Inventory Management`
- `Physics`
- `Procedural Generation`
- `Resource Management`
- `Score Attack`
- `Turn-Based Tactics`
- `Combat`
- `Character Customization`
- `Minigames`

### Player support

- `Singleplayer`
- `Co-op`
- `Local Co-Op`
- `Online Co-Op`
- `Local Multiplayer`
- `Multiplayer`
- `Massively Multiplayer`
- `PvP`
- `4 Player Local`

## Current Gap Categories

Based on the recent backfill samples, the main missing lanes are:

- pinball / table games
- party / minigame / collection games
- platformers
- sports and racers
- RTS / real-time tactics / wargames
- metroidvania
- life sim / virtual pet / job sim
- hidden object / puzzle
- card battler / deckbuilder / trading card game
- stealth / immersive sim / crime / heist
- horror-adventure / narrative horror
- beat-'em-up / fighters

## Required Crosswalk Strategy

Every incoming source label should be resolved in this order:

1. exact Steam-approved tag
2. Steam-equivalent normalized tag
3. ambiguous source label requiring multi-tag expansion
4. no direct Steam equivalent, so map to derived internal labels only

## Missing Label Crosswalk

These are the minimum crosswalks we should add next.

### Pinball / party / collection

- `Pinball` -> `Pinball`
- `Party` -> `Party`, `Minigames`, or `Party Game` depending description
- `Party Game` -> `Party Game`
- `Minigame Collection` -> `Minigames`, `Party`
- `Compilation` -> store/package metadata only, not a similarity label

### Platformers

- `2D Platformer` -> `2D Platformer`
- `3D Platformer` -> `3D Platformer`
- `Platformer` -> `Platformer`
- `Precision Platformer` -> `Precision Platformer`
- `Side Scroller` -> `Side Scroller`
- `Collectathon` -> `Collectathon`
- `Runner` -> `Runner`
- `Puzzle Platformer` -> `Puzzle Platformer`
- `Metroidvania` -> `Metroidvania`
- `Roguevania` -> `Roguevania`

### Sports / racing

- `Soccer` -> `Soccer`
- `Football (Soccer)` -> `Soccer`
- `Sports` -> `Sports`
- `Auto Racing` -> `Racing`
- `Auto Racing Sim` -> `Automobile Sim`, `Racing`
- `Automobile Sim` -> `Automobile Sim`
- `Combat Racing` -> `Combat Racing`
- `Driving` -> `Driving`
- `Vehicular Combat` -> `Vehicular Combat`
- `Offroad` -> `Offroad`

### Strategy / tactics

- `RTS` -> `RTS`
- `Real-Time Strategy` -> `RTS`
- `Real Time Strategy` -> `RTS`
- `Real-Time Tactics` -> `Real Time Tactics`
- `Real Time Tactics` -> `Real Time Tactics`
- `Wargame` -> `Wargame`
- `Grand Strategy` -> `Grand Strategy`
- `4X` -> `4X`
- `Turn-Based Tactics` -> `Turn-Based Tactics`
- `Strategy RPG` -> `Strategy RPG`
- `Tactical RPG` -> `Tactical RPG`
- `Tower Defense` -> `Tower Defense`
- `City Builder` -> `City Builder`
- `Colony Sim` -> `Colony Sim`

### Life sim / job sim / pet sim

- `Life Sim` -> `Life Sim`
- `Virtual Pet` -> `Life Sim` plus derived `pet_sim`
- `Job Simulator` -> `Job Simulator`
- `Virtual Career` -> no exact Steam-equivalent tag; map by description into `Job Simulator`, `Time Management`, `Management`, `Building`, `Life Sim`
- `Time Management` -> `Time Management`
- `Management` -> `Management`
- `Building` -> `Building`
- `Shop Keeper` -> `Shop Keeper`
- `Medical Sim` -> `Medical Sim`
- `Farming Sim` -> `Farming Sim`
- `God Game` -> `God Game`

### Hidden object / puzzle / card

- `Hidden Object` -> `Hidden Object`
- `Logic Puzzle` -> `Logic`, `Puzzle`
- `Puzzle` -> `Puzzle`
- `Match 3` -> `Match 3`
- `Sokoban` -> `Sokoban`
- `Card Battle` -> `Card Battler`
- `Card Battler` -> `Card Battler`
- `Deckbuilder` -> `Deckbuilding`
- `Deck Builder` -> `Deckbuilding`
- `Deckbuilding` -> `Deckbuilding`
- `Trading Card Game` -> `Trading Card Game`
- `Card Game` -> `Card Game`
- `Solitaire` -> `Solitaire`

### Stealth / immersive / crime / horror

- `Stealth` -> `Stealth`
- `Immersive Sim` -> `Immersive Sim`
- `Crime` -> `Crime`
- `Heist` -> `Heist`
- `Investigation` -> `Investigation`
- `Horror` -> `Horror`
- `Psychological Horror` -> `Psychological Horror`
- `Survival Horror` -> `Survival Horror`
- `Walking Simulator` -> `Walking Simulator`
- `First-Person` -> `First-Person`
- `Third-Person Adventure` -> `Third Person`, `Adventure`
- `Open-World Action` -> `Action-Adventure`, `Open World`

### Fighters / brawlers

- `2D Fighting` -> `2D Fighter`
- `3D Fighting` -> `3D Fighter`
- `Fighting` -> `Fighting`
- `Beat-'Em-Up` -> `Beat 'em up`
- `Beat 'em up` -> `Beat 'em up`
- `Spectacle Fighter` -> `Spectacle fighter`
- `Character Action Game` -> `Character Action Game`

## Derived Internal Labels

Steam parity is necessary but not sufficient.

The real similarity engine should infer higher-signal internal labels from combinations of Steam-equivalent tags plus description evidence.

These derived labels should be smaller in number than the raw tag bank and more useful for actual similarity.

### Recommended derived label families

- `open_world_survival_crafting_action_rpg`
- `open_world_driving_racer`
- `narrative_horror_adventure`
- `crime_heist_immersive_sim`
- `house_design_management_sim`
- `party_minigame_collection`
- `precision_platformer_metroidvania`
- `deckbuilder_tactics_roguelite`
- `fighter_arcade_competitive`
- `life_pet_collection_sim`
- `real_time_tactics_wargame`
- `hidden_object_relaxing_puzzle`

### Why derived labels matter

Raw Steam tags are broad and overlapping.

Examples:

- `Crime Simulator` should not just be `Simulation + Crime + Co-op`
  It should become a stronger internal label like `crime_heist_immersive_sim`

- `Architect Life` should not just be `Simulation + Building`
  It should become `house_design_management_sim`

- `Len's Island` should not just be `Action + RPG`
  It should become `open_world_survival_crafting_action_rpg`

- `Still Wakes the Deep: Siren's Rest` should not just be `Action + Horror`
  It should become `narrative_horror_adventure`

## Implementation Rules

### 1. Steam tags must be ingested directly

V2 should not depend only on Steam genres and Steam categories.

We should ingest:

- Steam genres
- Steam categories
- Steam developer/publisher
- Steam user-defined tags or the accessible store-tag surface when available
- Steam short and long descriptions

### 2. Steam-equivalent normalization comes before archetype inference

Every source label from Metacritic and OpenCritic should be normalized into a Steam-equivalent tag whenever possible before we assign archetypes.

### 3. Ambiguous labels should not overfire

Labels like:

- `Action RPG`
- `Action Adventure`
- `Simulation`
- `Strategy`

should never be enough on their own to compute a strong archetype like `loot_action_rpg`.

### 4. Package-format labels should be separated

These should not drive similarity:

- `Compilation`
- `Remaster collection`
- `Deluxe edition`
- DLC / bundle packaging metadata

### 5. Derived labels should use combinations, not single tags

Examples:

- `Open World` + `Driving` + `Automobile Sim` + `PvP` -> `open_world_driving_racer`
- `Crime` + `Heist` + `Immersive Sim` + `Stealth` -> `crime_heist_immersive_sim`
- `Building` + `Management` + `First-Person` + `Life Sim` -> `house_design_management_sim`

## Immediate Priority List

The next round of taxonomy work should prioritize these additions first:

1. ingest Steam tags directly
2. add Steam-equivalent crosswalks for:
   - `2D Fighting`
   - `3D Fighting`
   - `Beat-'Em-Up`
   - `2D Platformer`
   - `3D Platformer`
   - `Auto Racing Sim`
   - `Real-Time Tactics`
   - `Card Battle`
   - `Logic Puzzle`
   - `Virtual Career`
   - `Virtual Pet`
   - `Third-Person Adventure`
   - `Open-World Action`
3. prevent `Massively Multiplayer` from forcing racer titles into MMO archetypes
4. tighten `loot_action_rpg` so generic `Action/RPG/Single-player` cannot auto-compute
5. add derived-label inference for the lanes above

## Research Examples

These Steam pages show the richer label surface we are currently missing:

- `Len's Island` explicitly presents itself as an open-world survival crafting game with dungeon crawling, ARPG combat, farming, building, quests, and procedural world discovery
- `Architect Life` explicitly presents building, management, first-person exploration, and architectural design play
- `Crime Simulator` is tagged with `Crime`, `Heist`, `Online Co-Op`, `Immersive Sim`, `Stealth`, and `First-Person`
- `Battle Train` explicitly describes a run-based roguelite deck-and-track builder with deck-building and tactical combat
- `CarX Street` explicitly focuses on mountain roads, highways, city streets, realistic driving, tuning, and racing
- `Still Wakes the Deep: Siren's Rest` explicitly presents first-person narrative horror-adventure, survival pressure, exploration, and forensic investigation
- `Hidden Cats & Pandas` explicitly describes itself as a hidden object game

## Sources

- Steam Tags docs: https://partner.steamgames.com/doc/store/tags?l=english
- Steam Popular Tags: https://store.steampowered.com/tag/browse/
- Architect Life: A House Design Simulator: https://store.steampowered.com/app/1296400/Architect_Life_A_House_Design_Simulator/
- Len's Island: https://store.steampowered.com/app/1335830/Lens_Island/
- Crime Simulator: https://store.steampowered.com/app/2737070/Crime_Simulator/
- Battle Train: https://store.steampowered.com/app/1708950/Battle_Train/
- CarX Street: https://store.steampowered.com/app/1114150/CarX_Street/
- Still Wakes the Deep: Siren’s Rest: https://store.steampowered.com/app/3465690/Still_Wakes_the_Deep_Sirens_Rest/
- Hidden Cats & Pandas: https://store.steampowered.com/app/3786560/Hidden_Cats__Pandas/
