# GPT-5.4 Native Fix Backlog

- Rows: 200

## Bucket Summary

- `taxonomy_backlog`: 97
- `must_include_gap`: 50
- `taxonomy_drift`: 37
- `ranking_alignment`: 16

## Top Taxonomy Shifts

- `hidden -> none`: 43
- `hidden -> visual_novel`: 7
- `jrpg_story_rpg -> jrpg_story_rpg`: 6
- `hidden -> action_platformer`: 6
- `survival_horror -> survival_horror`: 6
- `pending -> none`: 6
- `metroidvania -> metroidvania`: 5
- `hidden_object_puzzle -> none`: 5
- `hidden -> precision_platformer`: 4
- `arcade_racer -> arcade_racer`: 4
- `hidden_object_puzzle -> hidden_object_puzzle`: 4
- `sports_sim -> rhythm_game`: 3
- `management_tycoon -> management_tycoon`: 3
- `hidden -> character_action`: 3
- `hidden -> monster_collect_rpg`: 3

## Top Missing Must-Include Titles

- `Vampire Survivors`: 4
- `Dino Crisis`: 3
- `TUNIC`: 3
- `The Riftbreaker`: 3
- `Soulstone Survivors`: 3
- `MLB The Show 24`: 2
- `MLB The Show 25`: 2
- `Fatal Frame: Maiden of Black Water`: 2
- `Making*Lovers`: 2
- `Chained Echoes`: 2
- `Rise of the Third Power`: 2
- `Hakuoki: Kyoto Winds`: 2
- `Nightshade`: 2
- `Birushana: Rising Flower of Genpei`: 2
- `Super Meat Boy`: 2

## Top False-Positive Live Titles

- `Clair Obscur: Expedition 33`: 2
- `Monster Hunter Stories`: 2
- `Monster Hunter Stories 2: Wings of Ruin`: 2
- `Pyre`: 2
- `Dragon Quest VII Reimagined`: 2
- `BIOMORPH`: 2
- `Sonic Racing: CrossWorlds`: 2
- `Rusty Rangers`: 2
- `Ruffy and the Riverside`: 2
- `S.T.A.L.K.E.R. 2: Heart of Chornobyl`: 2
- `BIT.TRIP CORE`: 2
- `Drums Rock`: 2
- `Infinite Guitars`: 2
- `Thumper`: 2
- `Beast Breaker`: 2

## Top Catalog Gaps


## taxonomy_drift

### The New Zealand Story: Untold Adventure

- Priority: `150`
- Current: `beat_em_up`
- Target: `action_platformer`
- Issues: taxonomy_not_curated, taxonomy_mismatch, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: The NewZealand Story
- Live-only: Doodle World Deluxe, MagiCat, Princess of the Water Lilies, Shotgun Cop Man, Songbird Symphony
- GPT-only: Alex Kidd in Miracle World DX, Disney DuckTales Remastered, Rayman Legends, Toki

### Breath of Fire IV

- Priority: `145`
- Current: `jrpg_story_rpg`
- Target: `jrpg_story_rpg`
- Issues: taxonomy_not_curated, taxonomy_mismatch, zero_live_overlap, must_include_missing, catalog_gap, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Breath of Fire III, Grandia II, Final Fantasy IX
- Live-only: Clair Obscur: Expedition 33, Monster Hunter Stories, Monster Hunter Stories 2: Wings of Ruin, Pyre, Robotics;Notes Elite
- GPT-only: Chrono Cross: The Radical Dreamers Edition, Final Fantasy IX

### Granblue Fantasy

- Priority: `145`
- Current: `jrpg_story_rpg`
- Target: `jrpg_story_rpg`
- Issues: taxonomy_not_curated, taxonomy_mismatch, zero_live_overlap, must_include_missing, catalog_gap, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Honkai: Star Rail, Epic Seven
- Live-only: Card-en-Ciel, Monster Hunter Stories, Monster Hunter Stories 2: Wings of Ruin, Puzzle Quest 3, Pyre
- GPT-only: Another Eden: The Cat Beyond Time and Space, Honkai: Star Rail

### Royal Vermin

- Priority: `145`
- Current: `traditional_fighter`
- Target: `traditional_fighter`
- Issues: taxonomy_not_curated, taxonomy_mismatch, zero_live_overlap, must_include_missing, catalog_gap, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Super Smash Bros. Ultimate, Brawlhalla, Rivals of Aether
- Live-only: Domiverse, Hyper Mirror Run, Runbow, Sonic Mania, Stick Fight: The Game
- GPT-only: Brawlhalla, Nickelodeon All-Star Brawl 2, Rivals of Aether, Super Smash Bros. Ultimate

### Stitched Together

- Priority: `140`
- Current: `jrpg_story_rpg`
- Target: `jrpg_story_rpg`
- Issues: taxonomy_not_curated, taxonomy_mismatch, zero_live_overlap, must_include_missing, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: OMORI, EarthBound, Persona 4 Golden
- Live-only: Bearnard, Clair Obscur: Expedition 33, Dragon Quest VII Reimagined, Path of the Midnight Sun, Phoenix Springs
- GPT-only: Bug Fables: The Everlasting Sapling, Ikenfell, Omori, Persona 4 Golden

### Last Man Sitting

- Priority: `135`
- Current: `arena_fps`
- Target: `co_op_action_roguelite`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Missing must-include: Risk of Rain 2, Crab Champions
- GPT-only: Alienation, Gunfire Reborn, Risk of Rain 2, Roboquest

### Mr. Sleepy Man

- Priority: `135`
- Current: `3d_collectathon`
- Target: `3d_collectathon`
- Issues: taxonomy_not_curated, taxonomy_mismatch, zero_live_overlap, must_include_missing, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: A Hat in Time, Super Mario Odyssey, Yooka-Laylee
- Live-only: Bō: Path of the Teal Lotus, Hollow Knight, Makis Adventure, Romancelvania, Strider
- GPT-only: A Hat in Time, Goat Simulator 3, Psychonauts 2, SpongeBob SquarePants: Battle For Bikini Bottom - Rehydrated, Super Mario Odyssey

### Prop Sumo

- Priority: `135`
- Current: `traditional_fighter`
- Target: `traditional_fighter`
- Issues: taxonomy_not_curated, taxonomy_mismatch, zero_live_overlap, must_include_missing, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Gang Beasts, Party Animals
- Live-only: Agnostiko VS, Blade Arcus From Shining: Battle Arena, Runbow Pocket, STEEL RIVALS, Super Mario Party
- GPT-only: Boomerang Fu, Brawlhalla, Gang Beasts, Party Animals, Super Smash Bros. Ultimate

### Resident Evil (1996)

- Priority: `135`
- Current: `hidden`
- Target: `survival_horror`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Missing must-include: Resident Evil (2002), Resident Evil 2 (1998), Dino Crisis
- GPT-only: Alone in the Dark, Resident Evil 2, Resident Evil 2 (1998), Resident Evil 3: Nemesis

### Tombwater

- Priority: `135`
- Current: `metroidvania`
- Target: `soulslike_action_rpg`
- Issues: taxonomy_not_curated, taxonomy_mismatch, zero_live_overlap, must_include_missing, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Morbid: The Seven Acolytes, TUNIC, Death's Door
- Live-only: BIOMORPH, Bleak Faith: Forsaken, Death's Gambit: Afterlife, Timespinner, Zexion
- GPT-only: Death's Door, Hyper Light Drifter, Morbid: The Seven Acolytes, Tunic, Unsighted

### Call of Duty: Black Ops 7

- Priority: `130`
- Current: `action_horror`
- Target: `military_fps`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: Call of Duty: Black Ops 6, Call of Duty: Black Ops Cold War
- GPT-only: Call of Duty: Black Ops 6, Call of Duty: Black Ops Cold War, Call of Duty: Black Ops III, Call of Duty: Modern Warfare III

### Collector's Cove

- Priority: `130`
- Current: `hidden`
- Target: `farming_sim`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: Summer in Mara, Havendock, Moonglow Bay
- GPT-only: Animal Crossing: New Horizons, Moonglow Bay, Stardew Valley, Summer in Mara

### Cursed Words: The Word Game That Isn't

- Priority: `130`
- Current: `pending`
- Target: `word_puzzle_strategy`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: Balatro, Letter Quest: Grimm's Journey Remastered, Bookworm Adventures Deluxe
- GPT-only: Balatro, Letter Quest: Grimm's Journey Remastered

### eBaseball: PRO SPIRIT

- Priority: `130`
- Current: `party_game`
- Target: `sports_sim`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: MLB The Show 24, MLB The Show 25
- GPT-only: MLB The Show 24, MLB The Show 25, Super Mega Baseball 4

### Eve of the 12 Months

- Priority: `130`
- Current: `hidden`
- Target: `visual_novel`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: eden*, ef - the first tale.
- GPT-only: Harmonia

### Fatal Frame II: Crimson Butterfly Remake

- Priority: `130`
- Current: `hidden`
- Target: `survival_horror`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: Fatal Frame II: Crimson Butterfly, Fatal Frame: Maiden of Black Water, Fatal Frame: Mask of the Lunar Eclipse
- GPT-only: DreadOut, Fatal Frame: Maiden of the Black Water, Fatal Frame: Mask of the Lunar Eclipse

### Making*Lovers: First Blush

- Priority: `130`
- Current: `pending`
- Target: `visual_novel`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: Making*Lovers
- GPT-only: Fureraba ~Friend to Lover~, Kinkoi: Golden Loveriche, Making*Lovers, Sugar * Style

### The Demon Queen's Dire Dilemma

- Priority: `130`
- Current: `hidden`
- Target: `visual_novel`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: Sweetest Monster, Kindred Spirits on the Roof, Highway Blossoms, Nurse Love Addiction, The Fairy's Song
- GPT-only: Highway Blossoms, Kindred Spirits on the Roof, Nurse Love Addiction

### Thomas & Friends: Wonders of Sodor

- Priority: `130`
- Current: `hidden`
- Target: `transport_sim`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: Train Sim World 5
- GPT-only: Train Sim World 4, Train Sim World 5

### Dice A Million

- Priority: `125`
- Current: `hidden`
- Target: `card_battler`
- Issues: taxonomy_not_curated, taxonomy_mismatch, live_empty, zero_live_overlap, must_include_missing, weak_candidates_pruned
- Missing must-include: Dicey Dungeons, Astrea: Six-Sided Oracles
- GPT-only: Astrea: Six-Sided Oracles, Dicey Dungeons, Die in the Dungeon, SpellRogue


## taxonomy_backlog

### Etrange Overlord

- Priority: `110`
- Current: `party_game`
- Target: `character_action`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Patapon 3, Hi-Fi Rush
- Live-only: Crypt of the NecroDancer, Date Night Bowling, Super Crazy Rhythm Castle, Taiko No Tatsujin: Rhythm Festival, Wonder Wickets
- GPT-only: Castle Crashers Remastered, Dragon's Crown Pro, Hi-Fi Rush, Soundfall

### iRacing Arcade

- Priority: `110`
- Current: `arcade_racer`
- Target: `arcade_racer`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: New Star GP, GRID Legends
- Live-only: Formula Retro Racing, Kinetic Edge, Smurfs Kart, Sonic Racing: CrossWorlds, Team Sonic Racing
- GPT-only: Circuit Superstars, GRID Legends, New Star GP, Super Woden GP 2

### All Will Fall

- Priority: `105`
- Current: `rts`
- Target: `city_builder`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, catalog_gap, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Frostpunk, Flotsam
- Live-only: MEMORIAPOLIS, Manor Lords, Nebuchadnezzar, Pioneers of Pagonia, Ratropolis
- GPT-only: Frostpunk, IXION, Surviving the Aftermath, Timberborn

### Pax Autocratica

- Priority: `105`
- Current: `rts`
- Target: `colony_sim`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, catalog_gap, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Executive Assault 2, Silica, The Riftbreaker
- Live-only: BattleGroupVR2, Conan Unconquered, Farworld Pioneers, StarRupture, Survivalist: Invisible Strain
- GPT-only: The Riftbreaker

### RUBATO

- Priority: `105`
- Current: `jrpg_story_rpg`
- Target: `metroidvania`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, catalog_gap, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Yoku's Island Express, Wuppo, Tomba!, Ori and the Blind Forest, Cavern of Dreams
- Live-only: A Pixel Story, Berserk Boy, Blast Brigade vs. the Evil Legion of Dr. Cread, Ogu and the Secret Forest, Rusty Rangers
- GPT-only: Cavern of Dreams, Ori and the Blind Forest, Wuppo, Yoku's Island Express

### Towerborne

- Priority: `105`
- Current: `action_platformer`
- Target: `beat_em_up`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, catalog_gap, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Dragon's Crown Pro, Castle Crashers Remastered
- Live-only: Abyss Odyssey, BADLAND: Game of the Year Edition, Grim Guardians: Demon Purge, Mighty No. 9, TEVI
- GPT-only: Castle Crashers Remastered, Dragon's Crown Pro, River City Girls 2, Young Souls

### Aether & Iron

- Priority: `100`
- Current: `turn_based_tactics`
- Target: `turn_based_tactics`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Sovereign Syndicate, Shadowrun: Dragonfall - Director's Cut, Wasteland 3
- Live-only: Death Trick: Double Blind, Dragon Age: The Veilguard, Dragon Quest XI S: Echoes of an Elusive Age - Definitive Edition, Dragon Quest XI: Echoes of an Elusive Age, Mato Anomalies
- GPT-only: Shadowrun: Dragonfall - Director's Cut, Shadowrun: Hong Kong, The Lamplighters League, Wasteland 3

### Afterplace

- Priority: `100`
- Current: `open_world_action_adventure`
- Target: `open_world_action_adventure`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: TUNIC, Hyper Light Drifter, UNSIGHTED
- Live-only: Dungeons of Hinterberg, Haven Park, Rhell: Warped Worlds & Troubled Times, Ruffy and the Riverside, S.T.A.L.K.E.R. 2: Heart of Chornobyl
- GPT-only: Anodyne, Death's Door, Hyper Light Drifter, Tunic

### GRIDbeat!

- Priority: `100`
- Current: `sports_sim`
- Target: `rhythm_game`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Crypt of the NecroDancer, Cadence of Hyrule, BPM: Bullets Per Minute
- Live-only: BIT.TRIP CORE, Drums Rock, Ella Stars, Infinite Guitars, Thumper
- GPT-only: Cadence of Hyrule: Crypt of the NecroDancer Featuring The Legend of Zelda, Crypt of the NecroDancer, Soundfall

### Little Nemo and the Guardians of Slumberland

- Priority: `100`
- Current: `metroidvania`
- Target: `metroidvania`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Monster Boy and the Cursed Kingdom, Shantae and the Seven Sirens, Ori and the Will of the Wisps
- Live-only: Arzette: The Jewel of Faramore, Astalon: Tears of the Earth, BIOMORPH, Crypt Custodian, SteamWorld Dig
- GPT-only: Monster Boy and the Cursed Kingdom, Ori and the Will of the Wisps, Shantae and the Seven Sirens, Wonder Boy: The Dragon's Trap

### Chico's Rebound

- Priority: `95`
- Current: `jrpg_story_rpg`
- Target: `pinball`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Yoku's Island Express, Wizorb
- Live-only: Beast Breaker, Neptunia: Sisters VS Sisters, RE:CALL, Tangle Tower, Vampire: The Masquerade - Coteries of New York
- GPT-only: Creature in the Well, Shatter Remastered Deluxe, Twin Breaker: A Sacred Symbols Adventure, Wizorb, Yoku's Island Express

### Copa City

- Priority: `95`
- Current: `sports_sim`
- Target: `management_tycoon`
- Issues: taxonomy_not_curated, live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Missing must-include: Planet Coaster, Cities: Skylines, Football Manager 2024
- GPT-only: Jurassic World Evolution 2, Parkitect, Planet Coaster, Two Point Campus

### KuloNiku: Bowl Up!

- Priority: `95`
- Current: `management_tycoon`
- Target: `management_tycoon`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Good Pizza, Great Pizza, Lemon Cake, Touhou Mystia's Izakaya
- Live-only: Café Paris, City Tales - Medieval Era, Discounty, The Lord of the Rings: Return to Moria, The Lost Legends of Redwall: Feasts & Friends
- GPT-only: Cat Cafe Manager, Chef Life: A Restaurant Simulator, Good Pizza, Great Pizza, Lemon Cake, Touhou Mystia's Izakaya

### Morkull Ascend to the Gods

- Priority: `95`
- Current: `beat_em_up`
- Target: `action_platformer`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Morkull Ragast's Rage
- Live-only: Blasphemous 2, Chronicles of Teddy: Harmony of Exidus, Goodboy Galaxy, ReSetna, Skelethrone: The Chronicles of Ericona
- GPT-only: Cuphead, Death's Gambit: Afterlife, Guacamelee! 2, Hollow Knight, Morkull Ragast's Rage

### Project Songbird

- Priority: `95`
- Current: `survival_horror`
- Target: `survival_horror`
- Issues: taxonomy_not_curated, live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Missing must-include: Resident Evil 7: Biohazard, Amnesia: The Bunker, In Sound Mind
- GPT-only: Amnesia: The Bunker, Fobia - St. Dinfna Hotel, In Sound Mind, The Beast Inside

### Ratcheteer DX

- Priority: `95`
- Current: `hidden`
- Target: `metroidvania`
- Issues: taxonomy_not_curated, live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Missing must-include: Ratcheteer, The Legend of Zelda: Link's Awakening, TUNIC
- GPT-only: Anodyne, Iconoclasts, SteamWorld Dig 2, Tunic

### Resident Evil 2 (1998)

- Priority: `95`
- Current: `survival_horror`
- Target: `survival_horror`
- Issues: taxonomy_not_curated, live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Missing must-include: Resident Evil 3: Nemesis, Resident Evil, Resident Evil Code: Veronica X, Silent Hill, Dino Crisis
- GPT-only: Resident Evil (1996), Resident Evil 3, Resident Evil 3: Nemesis

### Solasta II

- Priority: `95`
- Current: `turn_based_tactics`
- Target: `party_based_crpg`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Solasta: Crown of the Magister, Baldur's Gate 3
- Live-only: Beast Breaker, Demonschool, Jagged Alliance 3, Labyrinth of Galleria: The Moon Society, Mortal Glory
- GPT-only: Baldur's Gate 3, Divinity: Original Sin 2, Pathfinder: Wrath of the Righteous, Solasta: Crown of the Magister, Warhammer 40,000: Rogue Trader

### Solateria

- Priority: `95`
- Current: `jrpg_story_rpg`
- Target: `metroidvania`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Nine Sols, Hollow Knight
- Live-only: Arcadia: Colony, GINSHA, Rusty Rangers, Tales of Arise, Twilight Monk
- GPT-only: Blasphemous 2, ENDER LILIES: Quietus of the Knights, Hollow Knight, Nine Sols, Prince of Persia: The Lost Crown

### The Ratline

- Priority: `95`
- Current: `hidden_object_puzzle`
- Target: `hidden_object_puzzle`
- Issues: taxonomy_not_curated, zero_live_overlap, must_include_missing, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: The Case of the Golden Idol, The Roottrees are Dead, Return of the Obra Dinn
- Live-only: Arcane Investigations, Detective From The Crypt, Harold Rabbit - Finder of Lost Things, Rusty Lake: Roots, is THIS a game?
- GPT-only: Her Story, Return of the Obra Dinn, The Case of the Golden Idol, The Rise of the Golden Idol, The Roottrees Are Dead


## must_include_gap

### Aquamarine: Explorer's Edition

- Priority: `75`
- Current: `management_tycoon`
- Target: `none`
- Issues: zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Out There: Ω Edition, Curious Expedition 2
- Live-only: Colossal Cave, Criminal Expert, Lucid Dream, Night Lights, The Mystery of Woolley Mountain
- GPT-only: Curious Expedition 2, Subnautica, The Oregon Trail

### Poker Night at the Inventory

- Priority: `70`
- Current: `hidden_object_puzzle`
- Target: `none`
- Issues: zero_live_overlap, must_include_missing, catalog_gap, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Poker Night 2
- Live-only: Four Last Things, Old Skies, The Dream Machine, There's No Dinosaurs 2, Thimbleweed Park
- GPT-only: Prominence Poker

### The Coin Game

- Priority: `70`
- Current: `sports_sim`
- Target: `none`
- Issues: zero_live_overlap, must_include_missing, catalog_gap, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: Arcade Paradise, Tower Unite
- Live-only: Barton Lynch Pro Surfing, Call of the Wild: The Angler, My Name is Mayo, Way of the Hunter, theHunter: Call of the Wild
- GPT-only: Arcade Paradise, Carnival Games, Go Vacation

### Crabmeat

- Priority: `65`
- Current: `hidden_object_puzzle`
- Target: `none`
- Issues: zero_live_overlap, must_include_missing, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Missing must-include: DREDGE, Iron Lung
- Live-only: Harold Rabbit - Finder of Lost Things, Midnight Girl, The Order of the Thorne - The King's Challenge, Unicorn Dungeon, Watch Over Christmas
- GPT-only: Dredge, Iron Lung, Stories Untold, The Last Door: Complete Edition

### Cupiclaw

- Priority: `60`
- Current: `sports_sim`
- Target: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Missing must-include: Peglin, Luck be a Landlord, Ballionaire
- GPT-only: Balatro, Ballionaire, Luck be a Landlord, Peglin

### DigDigDrill

- Priority: `60`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Missing must-include: SteamWorld Dig 2, Dome Keeper, Wall World
- GPT-only: A Game About Digging A Hole, SteamWorld Dig, SteamWorld Dig 2, Super Motherload

### Fly for Fly

- Priority: `60`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Missing must-include: Mr. Moskeeto, Untitled Goose Game
- GPT-only: Mister Mosquito, Rain on Your Parade, Untitled Goose Game

### Ghost Master: Resurrection

- Priority: `60`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Missing must-include: Ghost Master

### Mythmatch

- Priority: `60`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Missing must-include: Merge Mayor, Love & Pies, EverMerge

### PancitoMerge

- Priority: `60`
- Current: `hidden_object_puzzle`
- Target: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Missing must-include: Suika Game
- GPT-only: Fruit Mountain, Suika Game, Tetris Effect: Connected

### Supernova

- Priority: `60`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap, weak_candidates_pruned
- Missing must-include: Suika Game
- GPT-only: Fruit Mountain, Puyo Puyo Champions, Suika Game, Tetris Effect: Connected

### Avenue Escape

- Priority: `55`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: Urban Flow, Does not Commute
- GPT-only: Mini Motorways, Train Valley 2: Community Edition, Urban Flow

### Defending Camelot

- Priority: `55`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: Plants vs. Zombies
- GPT-only: Kingdom Rush, Kingdom Rush Frontiers, PixelJunk Monsters 2, Plants vs. Zombies: Replanted

### Mega Man Star Force Legacy Collection

- Priority: `55`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: Mega Man Battle Network Legacy Collection
- GPT-only: Mega Man Battle Network Legacy Collection, One Step From Eden

### Oceanhorn 3: Legend of the Shadow Sea

- Priority: `55`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: Oceanhorn 2: Knights of the Lost Realm, The Legend of Zelda: The Wind Waker
- GPT-only: Immortals Fenyx Rising, Oceanhorn 2: Knights of the Lost Realm, Oceanhorn: Monster of Uncharted Seas, The Legend of Zelda: Breath of the Wild

### Pokemon Champions

- Priority: `55`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: Pokémon Battle Revolution, Pokémon Stadium 2, Pokémon Scarlet and Violet
- GPT-only: Pokémon Scarlet & Violet, Pokémon Stadium, Pokémon Sun and Moon, Pokémon Sword and Shield

### Reigns: The Witcher

- Priority: `55`
- Current: `soulslike_action_rpg`
- Target: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: Reigns
- GPT-only: Reigns, Reigns: Game of Thrones, Reigns: Her Majesty, Reigns: Three Kingdoms

### Samson

- Priority: `55`
- Current: `open_world_action_adventure`
- Target: `open_world_action_adventure`
- Issues: must_include_missing, catalog_gap, weak_candidates_pruned, live_false_positive_candidates
- Missing must-include: Driver: Parallel Lines, The Getaway
- Live-only: Batman: Arkham Knight, Mafia III: Stones Unturned

### Sigma Star Saga DX

- Priority: `55`
- Current: `western_narrative_rpg`
- Target: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: Sigma Star Saga
- GPT-only: Blaster Master Zero, CrossCode, The Knight Witch

### Stellar Wanderer DX

- Priority: `55`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, must_include_missing, catalog_gap
- Missing must-include: Stellar Wanderer, Freelancer, Galaxy on Fire 2 HD
- GPT-only: EVERSPACE 2, Rebel Galaxy Outlaw


## ranking_alignment

### DAMON and BABY

- Priority: `50`
- Current: `beat_em_up`
- Target: `none`
- Issues: zero_live_overlap, catalog_gap, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Live-only: Cassiodora, Costume Kingdom, Daemon X Machina: Titanic Scion, Guild Wars 2: Heart of Thorns, The Pathless
- GPT-only: Alienation, Darksiders Genesis, Lara Croft and the Temple of Osiris, The Ascent

### Rhell: Warped Worlds & Troubled Times

- Priority: `40`
- Current: `open_world_action_adventure`
- Target: `none`
- Issues: zero_live_overlap, weak_candidates_pruned, live_ranking_misaligned, live_false_positive_candidates
- Live-only: Afterplace, Keep Driving, Ruffy and the Riverside, S.T.A.L.K.E.R. 2: Heart of Chornobyl, VORON: Raven's Story
- GPT-only: Mages of Mystralia, Supraland, The Forgotten City, The Legend of Zelda: Tears of the Kingdom

### City Hunter

- Priority: `35`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, catalog_gap, weak_candidates_pruned

### Nutmeg!

- Priority: `35`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, catalog_gap, weak_candidates_pruned

### The Artisan of Glimmith

- Priority: `35`
- Current: `hidden_object_puzzle`
- Target: `none`
- Issues: live_empty, zero_live_overlap, catalog_gap, weak_candidates_pruned
- GPT-only: A Monster's Expedition, Tametsi, The Witness, stitch.

### Don't Mess With Bober

- Priority: `30`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, catalog_gap
- GPT-only: Blair Witch, Firewatch, The Suicide of Rachel Foster, The Vanishing of Ethan Carter

### Sushi Cat - Tower Defense

- Priority: `30`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, catalog_gap
- GPT-only: Isle of Arrows

### Apopia: Sugar Coated Tale

- Priority: `25`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, weak_candidates_pruned
- GPT-only: Beacon Pines, Night in the Woods, Psychonauts 2, Wandersong

### I Am Jesus Christ

- Priority: `25`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, weak_candidates_pruned
- GPT-only: Everybody's Gone to the Rapture, Firewatch, The Invisible Hours, What Remains of Edith Finch

### Missing The Point

- Priority: `25`
- Current: `pending`
- Target: `none`
- Issues: live_empty, zero_live_overlap, weak_candidates_pruned
- GPT-only: Dredge, Fishing Paradiso, Luna's Fishing Garden, Moonglow Bay

### Subsequence

- Priority: `25`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, weak_candidates_pruned
- GPT-only: Lifeless Moon, Tacoma, The Bradwell Conspiracy, What Remains of Edith Finch

### Thysiastery

- Priority: `25`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap, weak_candidates_pruned
- GPT-only: Darkest Dungeon, Iratus: Lord of the Dead, Mistover, Tangledeep

### MARVEL MaXimum Collection

- Priority: `20`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap
- GPT-only: Atari 50: The Anniversary Celebration, Disney Classic Games Collection, Jurassic Park Classic Games Collection, Teenage Mutant Ninja Turtles: The Cowabunga Collection, The Disney Afternoon Collection

### Neopets - Mega Mini Games Collection - The Neopian Arcade Odyssey

- Priority: `20`
- Current: `arena_fps`
- Target: `none`
- Issues: live_empty, zero_live_overlap
- GPT-only: Atari 50: The Anniversary Celebration, Capcom Arcade Stadium, Namco Museum, Nintendo World Championships: NES Edition, WarioWare: Get It Together!

### The Posthumous Investigation

- Priority: `20`
- Current: `hidden`
- Target: `none`
- Issues: live_empty, zero_live_overlap
- GPT-only: Paradise Killer, Return of the Obra Dinn, The Case of the Golden Idol, The Forgotten City, The Sexy Brutale

### ARC Raiders

- Priority: `15`
- Current: `extraction_shooter`
- Target: `extraction_shooter`
- Issues: live_ranking_misaligned, live_false_positive_candidates
- Live-only: Tom Clancy's The Division 2
- GPT-only: SYNDUALITY: Echo of Ada, The Cycle: Frontier
