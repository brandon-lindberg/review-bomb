# GPT-5.4 Alignment Corpus

- Titles analyzed: 200
- Zero-overlap rows: 187
- Live-empty rows: 147
- Must-include-missing rows: 151

## Top Issues

- `zero_live_overlap`: 187
- `must_include_missing`: 151
- `live_empty`: 147
- `taxonomy_not_curated`: 131
- `weak_candidates_pruned`: 90
- `catalog_gap`: 83
- `live_false_positive_candidates`: 52
- `live_ranking_misaligned`: 51
- `taxonomy_mismatch`: 37

## Top Taxonomy Shifts

- `none -> none`: 49
- `none -> visual_novel`: 8
- `none -> action_platformer`: 7
- `survival_horror -> survival_horror`: 6
- `jrpg_story_rpg -> jrpg_story_rpg`: 6
- `metroidvania -> metroidvania`: 5
- `hidden_object_puzzle -> none`: 5
- `hidden_object_puzzle -> hidden_object_puzzle`: 4
- `arcade_racer -> arcade_racer`: 4
- `none -> precision_platformer`: 4
- `none -> metroidvania`: 3
- `management_tycoon -> management_tycoon`: 3

## Top Live-Only Titles

- `Dragon Quest VII Reimagined`: 2
- `Clair Obscur: Expedition 33`: 2
- `Monster Hunter Stories`: 2
- `Monster Hunter Stories 2: Wings of Ruin`: 2
- `Pyre`: 2
- `BIOMORPH`: 2
- `BIT.TRIP CORE`: 2
- `Drums Rock`: 2
- `Infinite Guitars`: 2
- `Thumper`: 2
- `Beast Breaker`: 2
- `Sonic Racing: CrossWorlds`: 2

## Top GPT-Only Titles

- `Super Meat Boy`: 4
- `Castle Crashers Remastered`: 4
- `Halls of Torment`: 4
- `Soulstone Survivors`: 4
- `Vampire Survivors`: 4
- `Maid of Sker`: 3
- `Valfaris`: 3
- `Ember Knights`: 3
- `Ravenswatch`: 3
- `Little Nightmares II`: 3
- `Balatro`: 3
- `Peglin`: 3

## Top Missing Must-Include Titles

- `Vampire Survivors`: 4
- `Dino Crisis`: 3
- `TUNIC`: 3
- `The Riftbreaker`: 3
- `Soulstone Survivors`: 3
- `Making*Lovers`: 2
- `RiME`: 2
- `Maid of Sker`: 2
- `Hades`: 2
- `Good Pizza, Great Pizza`: 2
- `Frostpunk`: 2
- `Resident Evil 2`: 2

## Worst Rows

### Resident Evil 2 (1998)

- Current taxonomy: `survival_horror`
- Target taxonomy: `survival_horror`
- Issues: taxonomy_not_curated, live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Live: none
- GPT: Resident Evil 3: Nemesis, Resident Evil (1996), Resident Evil 3
- Missing must-include: Resident Evil 3: Nemesis, Resident Evil, Resident Evil Code: Veronica X, Silent Hill, Dino Crisis

### RUBATO

- Current taxonomy: `jrpg_story_rpg`
- Target taxonomy: `metroidvania`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, catalog_gap, live_ranking_misaligned, live_false_positive_candidates
- Live: A Pixel Story, Blast Brigade vs. the Evil Legion of Dr. Cread, Rusty Rangers, Berserk Boy, Ogu and the Secret Forest
- GPT: Yoku's Island Express, Wuppo, Ori and the Blind Forest, Cavern of Dreams
- Missing must-include: Yoku's Island Express, Wuppo, Tomba!, Ori and the Blind Forest, Cavern of Dreams

### The Demon Queen's Dire Dilemma

- Current taxonomy: `hidden`
- Target taxonomy: `visual_novel`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Live: none
- GPT: Highway Blossoms, Kindred Spirits on the Roof, Nurse Love Addiction
- Missing must-include: Sweetest Monster, Kindred Spirits on the Roof, Highway Blossoms, Nurse Love Addiction, The Fairy's Song

### Fortuna Magus

- Current taxonomy: `jrpg_story_rpg`
- Target taxonomy: `jrpg_story_rpg`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing
- Live: none
- GPT: Asdivine Hearts, Revenant Saga, Rise of the Third Power, Chained Echoes, Ara Fell: Enhanced Edition
- Missing must-include: Chained Echoes, Rise of the Third Power, Ara Fell: Enhanced Edition, Asdivine Hearts II, Revenant Saga

### Mirage 7

- Current taxonomy: `hidden`
- Target taxonomy: `cinematic_action_adventure`
- Issues: taxonomy_not_curated, live_empty, zero_live_overlap, must_include_missing, weak_candidates_pruned
- Live: none
- GPT: Kena: Bridge of Spirits, Tomb Raider, ReCore
- Missing must-include: Kena: Bridge of Spirits, RiME, ReCore, A Plague Tale: Innocence, Horizon Zero Dawn

### Breath of Fire IV

- Current taxonomy: `jrpg_story_rpg`
- Target taxonomy: `jrpg_story_rpg`
- Issues: taxonomy_not_curated, taxonomy_mismatch, zero_live_overlap, must_include_missing, catalog_gap, live_ranking_misaligned, live_false_positive_candidates
- Live: Monster Hunter Stories 2: Wings of Ruin, Pyre, Robotics;Notes Elite, Monster Hunter Stories, Clair Obscur: Expedition 33
- GPT: Final Fantasy IX, Chrono Cross: The Radical Dreamers Edition
- Missing must-include: Breath of Fire III, Grandia II, Final Fantasy IX

### Resident Evil (1996)

- Current taxonomy: `hidden`
- Target taxonomy: `survival_horror`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Live: none
- GPT: Resident Evil 2 (1998), Resident Evil 3: Nemesis, Resident Evil 2, Alone in the Dark
- Missing must-include: Resident Evil (2002), Resident Evil 2 (1998), Dino Crisis

### Royal Vermin

- Current taxonomy: `traditional_fighter`
- Target taxonomy: `traditional_fighter`
- Issues: taxonomy_not_curated, taxonomy_mismatch, zero_live_overlap, must_include_missing, catalog_gap, live_ranking_misaligned, live_false_positive_candidates
- Live: Stick Fight: The Game, Domiverse, Hyper Mirror Run, Sonic Mania, Runbow
- GPT: Super Smash Bros. Ultimate, Brawlhalla, Rivals of Aether, Nickelodeon All-Star Brawl 2
- Missing must-include: Super Smash Bros. Ultimate, Brawlhalla, Rivals of Aether

### Stitched Together

- Current taxonomy: `jrpg_story_rpg`
- Target taxonomy: `jrpg_story_rpg`
- Issues: taxonomy_not_curated, taxonomy_mismatch, zero_live_overlap, must_include_missing, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Live: Dragon Quest VII Reimagined, Path of the Midnight Sun, Clair Obscur: Expedition 33, Phoenix Springs, Bearnard
- GPT: Bug Fables: The Everlasting Sapling, Ikenfell, Omori, Persona 4 Golden
- Missing must-include: OMORI, EarthBound, Persona 4 Golden

### Aether & Iron

- Current taxonomy: `turn_based_tactics`
- Target taxonomy: `turn_based_tactics`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Live: Dragon Quest XI S: Echoes of an Elusive Age - Definitive Edition, Death Trick: Double Blind, Mato Anomalies, Dragon Age: The Veilguard, Dragon Quest XI: Echoes of an Elusive Age
- GPT: Shadowrun: Hong Kong, Shadowrun: Dragonfall - Director's Cut, Wasteland 3, The Lamplighters League
- Missing must-include: Sovereign Syndicate, Shadowrun: Dragonfall - Director's Cut, Wasteland 3

### Afterplace

- Current taxonomy: `open_world_action_adventure`
- Target taxonomy: `open_world_action_adventure`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Live: S.T.A.L.K.E.R. 2: Heart of Chornobyl, Rhell: Warped Worlds & Troubled Times, Haven Park, Dungeons of Hinterberg, Ruffy and the Riverside
- GPT: Tunic, Anodyne, Hyper Light Drifter, Death's Door
- Missing must-include: TUNIC, Hyper Light Drifter, UNSIGHTED

### Collector's Cove

- Current taxonomy: `hidden`
- Target taxonomy: `farming_sim`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Live: none
- GPT: Summer in Mara, Stardew Valley, Animal Crossing: New Horizons, Moonglow Bay
- Missing must-include: Summer in Mara, Havendock, Moonglow Bay

### Copa City

- Current taxonomy: `sports_sim`
- Target taxonomy: `management_tycoon`
- Issues: taxonomy_not_curated, live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Live: none
- GPT: Planet Coaster, Parkitect, Jurassic World Evolution 2, Two Point Campus
- Missing must-include: Planet Coaster, Cities: Skylines, Football Manager 2024

### Cursed Words: The Word Game That Isn't

- Current taxonomy: `pending`
- Target taxonomy: `word_puzzle_strategy`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Live: none
- GPT: Balatro, Letter Quest: Grimm's Journey Remastered
- Missing must-include: Balatro, Letter Quest: Grimm's Journey Remastered, Bookworm Adventures Deluxe

### Fatal Frame II: Crimson Butterfly Remake

- Current taxonomy: `hidden`
- Target taxonomy: `survival_horror`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Live: none
- GPT: Fatal Frame: Mask of the Lunar Eclipse, Fatal Frame: Maiden of the Black Water, DreadOut
- Missing must-include: Fatal Frame II: Crimson Butterfly, Fatal Frame: Maiden of Black Water, Fatal Frame: Mask of the Lunar Eclipse

### GRIDbeat!

- Current taxonomy: `sports_sim`
- Target taxonomy: `rhythm_game`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Live: Ella Stars, BIT.TRIP CORE, Thumper, Infinite Guitars, Drums Rock
- GPT: Crypt of the NecroDancer, Cadence of Hyrule: Crypt of the NecroDancer Featuring The Legend of Zelda, Soundfall
- Missing must-include: Crypt of the NecroDancer, Cadence of Hyrule, BPM: Bullets Per Minute

### Kritter: Defend Together

- Current taxonomy: `hidden`
- Target taxonomy: `co_op_action_roguelite`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, weak_candidates_pruned
- Live: none
- GPT: Endless Dungeon, Orcs Must Die! Deathtrap, Tribes of Midgard, Dungeon Defenders II
- Missing must-include: Endless Dungeon, Tribes of Midgard, The Riftbreaker

### Little Nemo and the Guardians of Slumberland

- Current taxonomy: `metroidvania`
- Target taxonomy: `metroidvania`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Live: Arzette: The Jewel of Faramore, SteamWorld Dig, BIOMORPH, Crypt Custodian, Astalon: Tears of the Earth
- GPT: Shantae and the Seven Sirens, Monster Boy and the Cursed Kingdom, Wonder Boy: The Dragon's Trap, Ori and the Will of the Wisps
- Missing must-include: Monster Boy and the Cursed Kingdom, Shantae and the Seven Sirens, Ori and the Will of the Wisps

### Mr. Sleepy Man

- Current taxonomy: `3d_collectathon`
- Target taxonomy: `3d_collectathon`
- Issues: taxonomy_not_curated, taxonomy_mismatch, zero_live_overlap, must_include_missing, live_ranking_misaligned, live_false_positive_candidates
- Live: Strider, Romancelvania, Bō: Path of the Teal Lotus, Hollow Knight, Makis Adventure
- GPT: Super Mario Odyssey, A Hat in Time, Psychonauts 2, SpongeBob SquarePants: Battle For Bikini Bottom - Rehydrated, Goat Simulator 3
- Missing must-include: A Hat in Time, Super Mario Odyssey, Yooka-Laylee

### Pax Autocratica

- Current taxonomy: `rts`
- Target taxonomy: `colony_sim`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, catalog_gap, live_ranking_misaligned, live_false_positive_candidates
- Live: StarRupture, Conan Unconquered, BattleGroupVR2, Survivalist: Invisible Strain, Farworld Pioneers
- GPT: The Riftbreaker
- Missing must-include: Executive Assault 2, Silica, The Riftbreaker

### Project Songbird

- Current taxonomy: `survival_horror`
- Target taxonomy: `survival_horror`
- Issues: taxonomy_not_curated, live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Live: none
- GPT: In Sound Mind, Amnesia: The Bunker, Fobia - St. Dinfna Hotel, The Beast Inside
- Missing must-include: Resident Evil 7: Biohazard, Amnesia: The Bunker, In Sound Mind

### Ratcheteer DX

- Current taxonomy: `hidden`
- Target taxonomy: `metroidvania`
- Issues: taxonomy_not_curated, live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Live: none
- GPT: Iconoclasts, SteamWorld Dig 2, Anodyne, Tunic
- Missing must-include: Ratcheteer, The Legend of Zelda: Link's Awakening, TUNIC

### Tombwater

- Current taxonomy: `metroidvania`
- Target taxonomy: `soulslike_action_rpg`
- Issues: taxonomy_not_curated, taxonomy_mismatch, zero_live_overlap, must_include_missing, live_ranking_misaligned, live_false_positive_candidates
- Live: Timespinner, Death's Gambit: Afterlife, Zexion, BIOMORPH, Bleak Faith: Forsaken
- GPT: Morbid: The Seven Acolytes, Unsighted, Death's Door, Tunic, Hyper Light Drifter
- Missing must-include: Morbid: The Seven Acolytes, TUNIC, Death's Door

### Basketball Classics

- Current taxonomy: `party_game`
- Target taxonomy: `sports_sim`
- Issues: taxonomy_not_curated, live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Live: none
- GPT: NBA 2K Playgrounds 2, NBA Playgrounds
- Missing must-include: NBA Jam, Double Dribble, NBA Playgrounds 2

### Cupiclaw

- Current taxonomy: `sports_sim`
- Target taxonomy: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Live: none
- GPT: Ballionaire, Luck be a Landlord, Balatro, Peglin
- Missing must-include: Peglin, Luck be a Landlord, Ballionaire
