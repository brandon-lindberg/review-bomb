# Similar Games Gold Set

## Purpose

This document defines the initial evaluation set for Similar Games Taxonomy V2.

The gold set exists to answer one question:

> Does the system return the kinds of neighbors a human would actually expect for a given game?

This file is intentionally curated. It is not meant to be exhaustive or crowd-sourced from raw tags.

Each anchor game should have:

- `expected_neighbors`
- `acceptable_neighbors`
- `blocked_neighbors`
- optional `notes`

This set should be used for:

- precision-at-5 evaluation
- regression testing during taxonomy changes
- curation prioritization
- debugging bad matches

## Evaluation Rules

### Expected neighbors

Games that should normally appear in the top results.

### Acceptable neighbors

Games that are not perfect peers but are valid adjacency matches.

### Blocked neighbors

Games that should never appear as similar even if broad tags overlap.

## Anchor Set V1

This is the first-pass starter set. It should grow over time to at least 100-200 anchors across all families.

## Open-World Fantasy / Action RPG

### Crimson Desert

- expected_neighbors
  - The Witcher 3: Wild Hunt
  - The Legend of Zelda: Breath of the Wild
  - Elden Ring
- acceptable_neighbors
  - Black Desert
  - Dragon's Dogma 2
- blocked_neighbors
  - Resident Evil Requiem
  - REANIMAL
  - High on Life 2
  - Romeo is a Dead Man
- notes
  - Open-world fantasy action RPG with traversal-heavy exploration, third-person hybrid combat, quest-driven progression, and serious heroic tone.

### The Witcher 3: Wild Hunt

- expected_neighbors
  - Crimson Desert
  - Dragon Age: The Veilguard
  - Dragon's Dogma 2
- acceptable_neighbors
  - Elden Ring
  - Kingdom Come: Deliverance II
- blocked_neighbors
  - DOOM
  - Resident Evil Village
  - Civilization VII
- notes
  - Narrative-heavy western fantasy RPG with exploration, quests, and third-person combat.

### Elden Ring

- expected_neighbors
  - Dark Souls III
  - Crimson Desert
  - Lies of P
- acceptable_neighbors
  - Black Myth: Wukong
  - The Witcher 3: Wild Hunt
- blocked_neighbors
  - Borderlands 4
  - Resident Evil Requiem
  - Stardew Valley
- notes
  - Open-world-adjacent soulslike action RPG with deliberate combat, boss-centric progression, and dark fantasy setting.

### Black Desert

- expected_neighbors
  - Crimson Desert
  - The Elder Scrolls Online
  - Lost Ark
- acceptable_neighbors
  - Elden Ring
  - Dragon's Dogma 2
- blocked_neighbors
  - Resident Evil Requiem
  - Counter-Strike 2
  - Cities: Skylines II
- notes
  - MMO action RPG with strong combat/world DNA overlap to fantasy action RPGs, but mode profile differs.

## Survival Horror

### Resident Evil Requiem

- expected_neighbors
  - Resident Evil Village
  - Dead Space
  - The Callisto Protocol
- acceptable_neighbors
  - Alan Wake II
  - Silent Hill 2
- blocked_neighbors
  - Crimson Desert
  - Breath of the Wild
  - High on Life 2
- notes
  - Survival-horror identity should block broad action-adventure matches.

### Dead Space

- expected_neighbors
  - Resident Evil Requiem
  - The Callisto Protocol
  - Resident Evil Village
- acceptable_neighbors
  - Alan Wake II
- blocked_neighbors
  - Elden Ring
  - Halo Infinite
  - Stardew Valley

## Shooters

### High on Life 2

- expected_neighbors
  - High on Life
  - Borderlands 4
  - Atomic Heart 2
- acceptable_neighbors
  - The Outer Worlds 2
- blocked_neighbors
  - Crimson Desert
  - Elden Ring
  - Resident Evil Requiem
- notes
  - First-person comedic sci-fi shooter should not leak into fantasy action RPGs.

### Borderlands 4

- expected_neighbors
  - Borderlands 3
  - High on Life 2
  - Destiny 2
- acceptable_neighbors
  - The Outer Worlds 2
- blocked_neighbors
  - The Witcher 3
  - Silent Hill 2
  - Cities: Skylines II

### Counter-Strike 2

- expected_neighbors
  - VALORANT
  - Rainbow Six Siege
- acceptable_neighbors
  - Escape from Tarkov
- blocked_neighbors
  - Crimson Desert
  - Dragon Age: The Veilguard
  - Metaphor: ReFantazio
- notes
  - Match-based tactical FPS should be strongly isolated.

## Character Action / Action Adventure

### Devil May Cry 5

- expected_neighbors
  - Bayonetta 3
  - Ninja Gaiden 4
  - Stellar Blade
- acceptable_neighbors
  - Final Fantasy XVI
- blocked_neighbors
  - Civilization VII
  - Resident Evil Requiem
  - Stardew Valley

### Metal Gear Solid Delta: Snake Eater

- expected_neighbors
  - Metal Gear Solid V: The Phantom Pain
  - Splinter Cell remake
  - Dishonored 2
- acceptable_neighbors
  - Hitman World of Assassination
- blocked_neighbors
  - Diablo IV
  - Resident Evil Requiem
  - Mario Kart World

## CRPG / Tactical RPG

### Baldur's Gate 3

- expected_neighbors
  - Divinity: Original Sin 2
  - Pillars of Eternity II
  - Dragon Age: Origins
- acceptable_neighbors
  - Pathfinder: Wrath of the Righteous
- blocked_neighbors
  - Call of Duty
  - Resident Evil Requiem
  - Forza Horizon 6

### Metaphor: ReFantazio

- expected_neighbors
  - Persona 5 Royal
  - Final Fantasy VII Rebirth
  - Dragon Quest XI
- acceptable_neighbors
  - Fire Emblem: Three Houses
- blocked_neighbors
  - Counter-Strike 2
  - Dead Space
  - Cities: Skylines II

## Platformers / Metroidvania

### Hollow Knight

- expected_neighbors
  - Ender Magnolia
  - Ori and the Will of the Wisps
  - Prince of Persia: The Lost Crown
- acceptable_neighbors
  - Animal Well
- blocked_neighbors
  - Destiny 2
  - Crimson Desert
  - Football Manager 2026

### Celeste

- expected_neighbors
  - Super Meat Boy
  - The End Is Nigh
  - Pizza Tower
- acceptable_neighbors
  - Hollow Knight
- blocked_neighbors
  - Diablo IV
  - Silent Hill 2
  - Europa Universalis V

## Strategy / Simulation

### Civilization VII

- expected_neighbors
  - Humankind
  - Age of Wonders 4
  - Old World
- acceptable_neighbors
  - Stellaris
- blocked_neighbors
  - Crimson Desert
  - Resident Evil Requiem
  - Mario Wonder

### Cities: Skylines II

- expected_neighbors
  - SimCity 4
  - Manor Lords
  - Frostpunk 2
- acceptable_neighbors
  - Workers & Resources: Soviet Republic
- blocked_neighbors
  - Counter-Strike 2
  - Elden Ring
  - Resident Evil Requiem

### Stardew Valley

- expected_neighbors
  - Story of Seasons
  - Coral Island
  - Fields of Mistria
- acceptable_neighbors
  - Animal Crossing: New Horizons
- blocked_neighbors
  - Dark Souls III
  - Resident Evil Requiem
  - Call of Duty

## Evaluation Procedure

For each anchor:

1. Generate top 5 similar games from V2.
2. Count how many are in `expected_neighbors`.
3. Count how many are in `acceptable_neighbors`.
4. Ensure none are in `blocked_neighbors`.

Suggested scoring:

- expected hit: `+1.0`
- acceptable hit: `+0.5`
- blocked hit: automatic failure for that anchor

## Precision Targets

Suggested initial thresholds:

- no blocked neighbors in top 5 for anchor set
- average precision@5 >= 0.70 on initial anchor set
- flagship anchors like `Crimson Desert`, `Resident Evil`, `Counter-Strike`, `Baldur's Gate 3`, `Cities: Skylines II` should each have at least 2 expected hits in top 5

## Expansion Plan

This starter file should be expanded in the following order:

1. flagship games with obvious identity
2. archetype-edge cases
3. hard-to-classify hybrids
4. yearly new releases

The eventual target should cover:

- RPG
- action-adventure
- survival horror
- tactical FPS
- hero/loot/extraction shooters
- metroidvania / platformers
- CRPG / JRPG / tactical RPG
- strategy / simulation / management
- sports / racing
- narrative / visual novel
- party / fighting

## Notes

This is not a recommendation list. It is an evaluation list.

If the matcher cannot satisfy this file reliably, it is not ready for production cutover.
