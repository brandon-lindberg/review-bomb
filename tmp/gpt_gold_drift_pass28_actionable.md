# GPT Gold Drift Report

- Rows: 116
- Min overlap threshold: 2
- Actionable rows: 116
- Validation actionable rows: 29
- Live unsafe rows: 3
- Worsened rows: 1
- Live-empty expected-computed rows: 40

## Bucket Summary

- `must_include_gap`: 59
- `taxonomy_backlog`: 22
- `similarity_status_drift`: 17
- `low_overlap_live`: 12
- `false_positive_suppression`: 3
- `catalog_gap_risk`: 2
- `regression`: 1

## Action Summary

- `must_include_gap`: 100
- `similarity_status_drift`: 40
- `live_empty`: 40
- `taxonomy_backlog`: 22
- `low_overlap_live`: 16
- `catalog_gap_risk`: 4
- `false_positive_suppression`: 3
- `regression`: 1

## Top Taxonomy Shifts

- `hidden -> none`: 26
- `hidden -> monster_collect_rpg`: 3
- `hidden -> character_action`: 3
- `hidden -> precision_platformer`: 3
- `hidden -> cinematic_action_adventure`: 2
- `hidden -> sports_sim`: 2
- `pending -> none`: 2
- `rts -> colony_sim`: 1
- `hidden -> metroidvania`: 1
- `hidden -> jrpg_story_rpg`: 1
- `hidden -> farming_sim`: 1
- `hidden -> life_sim`: 1
- `hidden -> beat_em_up`: 1
- `hidden -> military_fps`: 1
- `hidden -> 4x_strategy`: 1

## Top Missing Must-Include Titles

- `Dino Crisis`: 3
- `The Riftbreaker`: 2
- `Rise of the Third Power`: 2
- `Fatal Frame: Maiden of Black Water`: 2
- `Resident Evil`: 2
- `Resident Evil 7: Biohazard`: 2
- `Executive Assault 2`: 1
- `Silica`: 1
- `Pokémon HeartGold Version and Pokémon SoulSilver Version`: 1
- `Pokémon Ruby Version and Pokémon Sapphire Version`: 1
- `Pokémon Red Version and Pokémon Blue Version`: 1
- `Star Wars Jedi: Fallen Order`: 1
- `Ryse: Son of Rome`: 1
- `Kena: Bridge of Spirits`: 1
- `RiME`: 1

## Top Must-Avoid Hits

- `God of War Ragnarök`: 1
- `Indiana Jones and the Great Circle`: 1
- `Reach`: 1
- `Trek to Yomi`: 1
- `Devil's Hideout`: 1
- `Inmost`: 1
- `Nightmare Frames`: 1
- `The Bunker`: 1
- `Aven Colony`: 1
- `Highrise City`: 1
- `Mountaincore`: 1
- `Tropico 5`: 1

## false_positive_suppression

### 1348 Ex Voto

- Priority: `206`
- Action: `tighten_or_suppress_live_candidates`
- Taxonomy: current `cinematic_action_adventure` vs gold `cinematic_action_adventure`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: God of War, Indiana Jones and the Great Circle, Trek to Yomi, Reach, God of War Ragnarök, Tomb Raider, JETT: The Far Shore, Tribes of Midgard, Elden Ring, Etrange Overlord
- Gold: God of War, Star Wars Jedi: Fallen Order, Kena: Bridge of Spirits, Black Myth: Wukong
- Missing must-include: Star Wars Jedi: Fallen Order, Ryse: Son of Rome
- Must-avoid hits: God of War Ragnarök, Indiana Jones and the Great Circle, Reach, Trek to Yomi

### Bulb Boy 2: Jar of Despair

- Priority: `188`
- Action: `tighten_or_suppress_live_candidates`
- Taxonomy: current `hidden_object_puzzle` vs gold `hidden_object_puzzle`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: Bulb Boy, Devil's Hideout, The Bunker, Nightmare Frames, Inmost, Jester and the Madman, Rainbow Gate, Tales from Candleforth, Edgar Allan Poe's Interactive Horror: 1995 Edition, Bubumbu
- Gold: Bulb Boy, Children Of Silentown, Fran Bow, Bad Dream: Coma
- Missing must-include: Fran Bow
- Must-avoid hits: Devil's Hideout, Inmost, Nightmare Frames, The Bunker

### Laysara: Summit Kingdom

- Priority: `156`
- Action: `tighten_or_suppress_live_candidates`
- Taxonomy: current `city_builder` vs gold `city_builder`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `2`
- Live: Highrise City, Against The Storm, Tropico 5, Mountaincore, Aven Colony, Teeny Tiny Town, Settlement Survival, Pax Augusta, Bulwark: Falconeer Chronicles, Workers & Resources: Soviet Republic
- Gold: Against The Storm, Timberborn, Workers & Resources: Soviet Republic, Anno 1800, Banished
- Missing must-include: Frostpunk, Banished
- Must-avoid hits: Aven Colony, Highrise City, Mountaincore, Tropico 5


## regression

### Pax Autocratica

- Priority: `229`
- Action: `inspect_recent_change_before_more_repairs`
- Taxonomy: current `rts` vs gold `colony_sim`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: The Riftbreaker
- Missing must-include: Executive Assault 2, Silica, The Riftbreaker


## taxonomy_backlog

### Pokémon FireRed Version and Pokémon LeafGreen Version

- Priority: `219`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `monster_collect_rpg`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Pokemon Brilliant Diamond and Shining Pearl
- Missing must-include: Pokémon HeartGold Version and Pokémon SoulSilver Version, Pokémon Ruby Version and Pokémon Sapphire Version, Pokémon Red Version and Pokémon Blue Version

### Mirage 7

- Priority: `202`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `cinematic_action_adventure`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Kena: Bridge of Spirits, Tomb Raider, ReCore
- Missing must-include: Kena: Bridge of Spirits, RiME, ReCore, A Plague Tale: Innocence, Horizon Zero Dawn

### Homura Hime

- Priority: `194`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `character_action`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Furi, Bayonetta, Assault Spy, Nier: Automata, Scarlet Nexus
- Missing must-include: NieR:Automata, Scarlet Nexus, Furi

### Ratcheteer DX

- Priority: `194`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `metroidvania`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Iconoclasts, SteamWorld Dig 2, Anodyne, Tunic
- Missing must-include: Ratcheteer, The Legend of Zelda: Link's Awakening, TUNIC

### Street Soccer

- Priority: `194`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `sports_sim`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Street Power Football, Mario Strikers: Battle League, Super Arcade Football
- Missing must-include: Mario Strikers: Battle League Football, FIFA Street, Street Power Football

### Tales of Berseria Remastered

- Priority: `194`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `jrpg_story_rpg`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Tales of Berseria, Tales of Arise, Tales of Zestiria, Tales of Vesperia: Definitive Edition, Scarlet Nexus
- Missing must-include: Tales of Berseria, Tales of Arise, Tales of Zestiria

### The Abbess Garden

- Priority: `194`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `farming_sim`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Garden Life: A Cozy Simulator, GROW: Song of the Evertree, Wylde Flowers, Botany Manor
- Missing must-include: Garden Life: A Cozy Simulator, Strange Horticulture, Botany Manor

### MLB The Show 26

- Priority: `186`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `sports_sim`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: MLB The Show 25, MLB The Show 24, MLB The Show 23, MLB The Show 22, Super Mega Baseball 4
- Missing must-include: MLB The Show 25, MLB The Show 24

### Monster Hunter Stories 3: Twisted Reflection

- Priority: `186`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `monster_collect_rpg`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Monster Hunter Stories 2: Wings of Ruin, Monster Hunter Stories, Dragon Quest Monsters: The Dark Prince, Shin Megami Tensei V: Vengeance, World of Final Fantasy
- Missing must-include: Monster Hunter Stories 2: Wings of Ruin, Monster Hunter Stories

### Piece By Piece

- Priority: `186`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `life_sim`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Assemble With Care, The Repair House: Restoration Sim, Potion Craft: Alchemist Simulator, Garden Paws
- Missing must-include: Assemble with Care, FixFox

### Scott Pilgrim EX

- Priority: `186`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `beat_em_up`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: River City Girls 2, Teenage Mutant Ninja Turtles: Shredder's Revenge, Streets of Rage 4, Castle Crashers Remastered
- Missing must-include: Scott Pilgrim vs. The World: The Game – Complete Edition, River City Girls 2

### Starship Troopers: Ultimate Bug War!

- Priority: `186`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `military_fps`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Warhammer 40,000: Boltgun, Prodeus, Serious Sam 4, Ion Fury, Doom + Doom II
- Missing must-include: Warhammer 40,000: Boltgun, Prodeus

### Age of Wonders 4: Rise from Ruin

- Priority: `178`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `4x_strategy`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Age of Wonders 4, Age of Wonders III, Age of Wonders: Planetfall, Endless Legend, SpellForce: Conquest of Eo
- Missing must-include: Age of Wonders 4

### Legacy of Kain: Defiance Remastered

- Priority: `178`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `cinematic_action_adventure`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Legacy of Kain: Soul Reaver 1 & 2 Remastered, Castlevania: Lords of Shadow, Darksiders III
- Missing must-include: Legacy of Kain: Defiance

### NINJA GAIDEN 4 The Two Masters

- Priority: `178`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `character_action`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Ninja Gaiden 4, Devil May Cry 5, Bayonetta
- Missing must-include: NINJA GAIDEN 4

### Utawarerumono: ZAN 2

- Priority: `178`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `character_action`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Utawarerumono: Zan, Fate/Extella Link, Persona 5 Strikers, Fire Emblem Warriors: Three Hopes
- Missing must-include: Utawarerumono: ZAN

### 1 CatLine

- Priority: `170`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `precision_platformer`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: N++, Super Meat Boy, VVVVVV, The End Is Nigh

### Bonnie Bear Saves Frogtime

- Priority: `170`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `monster_collect_rpg`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Cassette Beasts, Coromon, Pokémon Scarlet & Violet, Monster Sanctuary

### DRACU-RIOT!

- Priority: `170`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `visual_novel`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Riddle Joker, Café Stella and the Reaper's Butterflies, Senren＊Banka, Aokana - Four Rhythms Across the Blue

### Go! Go! Mister Chickums

- Priority: `170`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `action_platformer`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Bubble Bobble 4 Friends

### Pogui

- Priority: `170`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `precision_platformer`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Celeste, Super Meat Boy, The End Is Nigh, Kaze and the Wild Masks, Rayman Legends

### Soulshard

- Priority: `170`
- Action: `add_scalable_phrase_or_taxonomy_rule`
- Taxonomy: current `hidden` vs gold `precision_platformer`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: ibb & obb, Unravel Two, Kalimba, Never Alone


## catalog_gap_risk

### Eve of the 12 Months

- Priority: `91`
- Action: `seed_missing_catalog_neighbors_or_keep_hidden`
- Taxonomy: current `visual_novel` vs gold `visual_novel`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: The Demon Queen's Dire Dilemma, Highway Blossoms, Harmonia, Nurse Love Addiction, Too Many Santas!, Path of Mystery: A Brush with Death, PARANORMASIGHT: The Seven Mysteries of Honjo, TOMAK: Save the Earth Regeneration, AI: The Somnium Files, The Centennial Case: A Shijima Story
- Gold: Harmonia
- Missing must-include: eden*, ef - the first tale.

### Poker Night at the Inventory

- Priority: `73`
- Action: `seed_missing_catalog_neighbors_or_keep_hidden`
- Taxonomy: current `card_battler` vs gold `none`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: Prominence Poker, Poker Club, Strip Poker Night at the Inventory, Grand Poker Casino
- Gold: Prominence Poker
- Missing must-include: Poker Night 2


## similarity_status_drift

### SealChain: Call of Blood

- Priority: `124`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: God of Weapons, Backpack Hero, The Binding of Isaac: Rebirth
- Missing must-include: Backpack Hero, God of Weapons, Brotato

### Stellar Wanderer DX

- Priority: `124`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Rebel Galaxy Outlaw, EVERSPACE 2
- Missing must-include: Stellar Wanderer, Freelancer, Galaxy on Fire 2 HD

### Ultra Bonk Survivors

- Priority: `124`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Vampire Survivors, Soulstone Survivors, Halls of Torment, Brotato
- Missing must-include: Vampire Survivors, Soulstone Survivors, Halls of Torment

### Avenue Escape

- Priority: `116`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Urban Flow, Mini Motorways, Train Valley 2: Community Edition
- Missing must-include: Urban Flow, Does not Commute

### Fly for Fly

- Priority: `116`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Mister Mosquito, Rain on Your Parade, Untitled Goose Game
- Missing must-include: Mr. Moskeeto, Untitled Goose Game

### Ghost of Yōtei: Legends

- Priority: `116`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Ghost of Tsushima: Legends, Ghost of Yotei, Stranger of Paradise: Final Fantasy Origin, Warhammer: Vermintide 2
- Missing must-include: Ghost of Yōtei, Ghost of Tsushima: Legends

### Oceanhorn 3: Legend of the Shadow Sea

- Priority: `116`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Oceanhorn 2: Knights of the Lost Realm, Oceanhorn: Monster of Uncharted Seas, The Legend of Zelda: Breath of the Wild, Immortals Fenyx Rising
- Missing must-include: Oceanhorn 2: Knights of the Lost Realm, The Legend of Zelda: The Wind Waker

### Stillborn Slayer

- Priority: `116`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Warm Snow, Curse of the Dead Gods, Hades, Dreamscaper
- Missing must-include: Hades, Curse of the Dead Gods

### Lil Gator Game: Gator of the Year

- Priority: `108`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Lil Gator Game, A Short Hike, Smushi Come Home, Alba: A Wildlife Adventure, Haven Park
- Missing must-include: Lil Gator Game

### Planet of Lana II: Children of the Leaf

- Priority: `108`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Planet of Lana, Inside, Somerville, LIMBO, Little Nightmares II
- Missing must-include: Planet of Lana

### Supernova

- Priority: `108`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Suika Game, Fruit Mountain, Puyo Puyo Champions, Tetris Effect: Connected
- Missing must-include: Suika Game

### World of Warcraft: Midnight

- Priority: `108`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: World of Warcraft: The War Within, Final Fantasy XIV: Dawntrail, World of Warcraft Classic, Star Wars: The Old Republic – Onslaught
- Missing must-include: World of Warcraft

### Apopia: Sugar Coated Tale

- Priority: `100`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Wandersong, Night in the Woods, Psychonauts 2, Beacon Pines

### Don't Mess With Bober

- Priority: `100`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Blair Witch, The Suicide of Rachel Foster, The Vanishing of Ethan Carter, Firewatch

### Subsequence

- Priority: `100`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Tacoma, The Bradwell Conspiracy, What Remains of Edith Finch, Lifeless Moon

### Sushi Cat - Tower Defense

- Priority: `100`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Isle of Arrows

### Thysiastery

- Priority: `100`
- Action: `rebuild_publish_after_taxonomy_fix`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `computed`
- Overlap: `0`
- Gold: Darkest Dungeon, Mistover, Iratus: Lord of the Dead, Tangledeep


## low_overlap_live

### Fortuna Magus

- Priority: `82`
- Action: `improve_ranking_without_broadening_weak_matches`
- Taxonomy: current `jrpg_story_rpg` vs gold `jrpg_story_rpg`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: Grimshade, Bravely Default: Flying Fairy HD Remaster, Asdivine Hearts, The Legend of Heroes: Trails Beyond the Horizon, Heroes of Drakemire, Dragon Spira, The Banner Saga 2, FANTASIAN Neo Dimension, Dragon Takers, Clair Obscur: Expedition 33
- Gold: Asdivine Hearts, Revenant Saga, Rise of the Third Power, Chained Echoes, Ara Fell: Enhanced Edition
- Missing must-include: Chained Echoes, Rise of the Third Power, Ara Fell: Enhanced Edition, Asdivine Hearts II, Revenant Saga

### Fatal Frame II: Crimson Butterfly Remake

- Priority: `74`
- Action: `improve_ranking_without_broadening_weak_matches`
- Taxonomy: current `survival_horror` vs gold `survival_horror`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: DreadOut, The Occultist, Hellpoint, Them and Us, Silent Hill 2, Until Dawn, The Evil Within 2, Resident Evil Requiem, Resident Evil 7 Biohazard, The Evil Within
- Gold: Fatal Frame: Mask of the Lunar Eclipse, Fatal Frame: Maiden of the Black Water, DreadOut
- Missing must-include: Fatal Frame II: Crimson Butterfly, Fatal Frame: Maiden of Black Water, Fatal Frame: Mask of the Lunar Eclipse

### Kritter: Defend Together

- Priority: `66`
- Action: `improve_ranking_without_broadening_weak_matches`
- Taxonomy: current `co_op_action_roguelite` vs gold `co_op_action_roguelite`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: Endless Dungeon, Royal Revolt Survivors, Last Man Sitting
- Gold: Endless Dungeon, Orcs Must Die! Deathtrap, Tribes of Midgard, Dungeon Defenders II
- Missing must-include: Tribes of Midgard, The Riftbreaker

### Esoteric Ebb

- Priority: `58`
- Action: `improve_ranking_without_broadening_weak_matches`
- Taxonomy: current `western_narrative_rpg` vs gold `western_narrative_rpg`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: The Necromancer's Tale, Hellenica, Sunset High, Tesla Effect: A Tex Murphy Adventure, Elea - Episode 1, Disco Elysium, Beat Cop, Death Park, Strange Antiquities, The Forgotten City
- Gold: Disco Elysium, Torment: Tides of Numenera, Planescape: Torment Enhanced Edition, Citizen Sleeper, Pentiment
- Missing must-include: Planescape: Torment

### Cupiclaw

- Priority: `56`
- Action: `improve_ranking_without_broadening_weak_matches`
- Taxonomy: current `physics_roguelite_strategy` vs gold `none`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: Roundguard, Shattered Heaven, Peglin, Stacklands, Three Kingdom: The Journey, Card Crawl Adventure, Heroes Wanted, Alina of the Arena, Pyrene, Fairy Tail: Dungeons
- Gold: Ballionaire, Luck be a Landlord, Balatro, Peglin
- Missing must-include: Luck be a Landlord, Ballionaire

### Wayblazer Dämmerung

- Priority: `56`
- Action: `improve_ranking_without_broadening_weak_matches`
- Taxonomy: current `jrpg_story_rpg` vs gold `jrpg_story_rpg`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: Dragon Quest I & II HD-2D Remake, Bug Fables: The Everlasting Sapling, Bravely Default: Flying Fairy HD Remaster, Tactical Breach Wizards, Chained Echoes, Loop Hero, Clair Obscur: Expedition 33, Moss: Book II, Dragon Quest VII Reimagined, SteamWorld Quest: Hand of Gilgamech
- Gold: Chained Echoes, Eiyuden Chronicles: Hundred Heroes, Rise of the Third Power, Octopath Traveler II
- Missing must-include: Rise of the Third Power, Eiyuden Chronicle: Hundred Heroes

### Solateria

- Priority: `48`
- Action: `improve_ranking_without_broadening_weak_matches`
- Taxonomy: current `metroidvania` vs gold `metroidvania`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: Nine Sols, Mandragora: Whispers of the Witch Tree
- Gold: Nine Sols, Prince of Persia: The Lost Crown, Hollow Knight, ENDER LILIES: Quietus of the Knights, Blasphemous 2
- Missing must-include: Hollow Knight

### Adventurous Slime

- Priority: `40`
- Action: `improve_ranking_without_broadening_weak_matches`
- Taxonomy: current `metroidvania` vs gold `metroidvania`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: Genopanic, Xeodrifter, Mini Ghost, Beaked Buccaneer, Samurai Kento, Ori and the Blind Forest, Öoo, Everdeep Aurora, Bahamut and the Waqwaq Tree, Dogworld
- Gold: Xeodrifter, Islets, Gato Roboto, Wonder Boy: The Dragon's Trap, Haiku, the Robot

### PancitoMerge

- Priority: `40`
- Action: `improve_ranking_without_broadening_weak_matches`
- Taxonomy: current `merge_puzzle` vs gold `none`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: Suika Game, A Little to the Left, Pieced Together, Unpacking, Wilmot's Warehouse, Annalynn, Packing Life, Near-Mage, ODDADA, Instants
- Gold: Suika Game, Fruit Mountain, Tetris Effect: Connected

### Parkour Labs

- Priority: `40`
- Action: `improve_ranking_without_broadening_weak_matches`
- Taxonomy: current `3d_collectathon` vs gold `precision_platformer`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: Only Up!, Cyber Hook, Shady Knight, Sonic Colors: Ultimate, Carly and the Reaperman - Escape from the Underworld, Snow Bros. Wonderland, Pecker, Shadow Puppeteer, The Smurfs: Mission Vileaf, Boti: Byteland Overclocked
- Gold: TO THE TOP, Cyber Hook, SEUM: Speedrunners from Hell, Refunct

### Rotwood

- Priority: `40`
- Action: `improve_ranking_without_broadening_weak_matches`
- Taxonomy: current `co_op_action_roguelite` vs gold `co_op_action_roguelite`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: Royal Revolt Survivors, Ember Knights, Never Grave: The Witch and the Curse, Madshot, Eko and the Bewitched Lands, Last Man Sitting, Iratus: Lord of the Dead
- Gold: Ember Knights, Lost Castle, Castle Crashers Remastered, Ravenswatch

### The Walking Trade

- Priority: `40`
- Action: `improve_ranking_without_broadening_weak_matches`
- Taxonomy: current `management_tycoon` vs gold `management_tycoon`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `1`
- Live: Winkeltje: The Little Shop, Chef: A Restaurant Tycoon Game, Discounty
- Gold: Winkeltje: The Little Shop, Moonlighter, No Umbrellas Allowed, Survivalist: Invisible Strain


## must_include_gap

### Samson

- Priority: `42`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `open_world_action_adventure` vs gold `open_world_action_adventure`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `3`
- Live: Sleeping Dogs: Definitive Edition, Mad Max, Grand Theft Auto IV
- Gold: Sleeping Dogs: Definitive Edition, Mad Max, Grand Theft Auto IV
- Missing must-include: Sleeping Dogs, Mafia III, Driver: Parallel Lines, The Getaway

### Mythmatch

- Priority: `34`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `hidden`
- Overlap: `0`
- Missing must-include: Merge Mayor, Love & Pies, EverMerge

### RAIDEN FIGHTERS REMIX COLLECTION

- Priority: `34`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `shoot_em_up` vs gold `none`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `5`
- Live: Raiden IV: OverKill, Raiden III x MIKADO MANIAX, Psikyo Shooting Stars Bravo, Raiden IV X Mikado Remix, DoDonPachi SaiDaiOuJou, DoDonPachi Resurrection, Psikyo Shooting Stars Alpha
- Gold: Raiden IV X Mikado Remix, Raiden III x MIKADO MANIAX, Psikyo Shooting Stars Alpha, Psikyo Shooting Stars Bravo, DoDonPachi Resurrection
- Missing must-include: Raiden Fighters, Raiden Fighters 2: Operation Hell Dive, Raiden Fighters Jet

### The Demon Queen's Dire Dilemma

- Priority: `34`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `visual_novel` vs gold `visual_novel`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `2`
- Live: Highway Blossoms, Too Many Santas!, Harmonia, Nurse Love Addiction, Famicom Detective Club: The Missing Heir + Famicom Detective Club: The Girl Who Stands Behind, Eve of the 12 Months, PARANORMASIGHT: The Seven Mysteries of Honjo, AI: The Somnium Files, The Centennial Case: A Shijima Story, Karigurashi Ren'ai: Living on Borrowed Love
- Gold: Highway Blossoms, Kindred Spirits on the Roof, Nurse Love Addiction
- Missing must-include: Sweetest Monster, Kindred Spirits on the Roof, The Fairy's Song

### Resident Evil 2 (1998)

- Priority: `32`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `survival_horror` vs gold `survival_horror`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `3`
- Live: Resident Evil 3: Nemesis, Resident Evil (1996), Resident Evil 3
- Gold: Resident Evil 3: Nemesis, Resident Evil (1996), Resident Evil 3
- Missing must-include: Resident Evil, Resident Evil Code: Veronica X, Silent Hill, Dino Crisis

### Breath of Fire IV

- Priority: `26`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `jrpg_story_rpg` vs gold `jrpg_story_rpg`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `2`
- Live: Final Fantasy IX, Chrono Cross: The Radical Dreamers Edition
- Gold: Final Fantasy IX, Chrono Cross: The Radical Dreamers Edition
- Missing must-include: Breath of Fire III, Grandia II

### Etrange Overlord

- Priority: `26`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `character_action` vs gold `character_action`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `4`
- Live: Soundfall, Hi-Fi Rush, Dragon's Crown Pro, Castle Crashers Remastered
- Gold: Soundfall, Hi-Fi Rush, Dragon's Crown Pro, Castle Crashers Remastered
- Missing must-include: Crypt of the NecroDancer, Patapon 3

### GRIDbeat!

- Priority: `26`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `rhythm_game` vs gold `rhythm_game`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `3`
- Live: Crypt of the NecroDancer, Cadence of Hyrule: Crypt of the NecroDancer Featuring The Legend of Zelda, Soundfall
- Gold: Crypt of the NecroDancer, Cadence of Hyrule: Crypt of the NecroDancer Featuring The Legend of Zelda, Soundfall
- Missing must-include: Cadence of Hyrule, BPM: Bullets Per Minute

### Resident Evil (1996)

- Priority: `26`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `survival_horror` vs gold `survival_horror`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `4`
- Live: Resident Evil 2 (1998), Resident Evil 3: Nemesis, Resident Evil 2, Alone in the Dark
- Gold: Resident Evil 2 (1998), Resident Evil 3: Nemesis, Resident Evil 2, Alone in the Dark
- Missing must-include: Resident Evil (2002), Dino Crisis

### Basketball Classics

- Priority: `24`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `sports_sim` vs gold `sports_sim`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `2`
- Live: NBA 2K Playgrounds 2, NBA Playgrounds
- Gold: NBA 2K Playgrounds 2, NBA Playgrounds
- Missing must-include: NBA Jam, Double Dribble, NBA Playgrounds 2

### Pokemon Champions

- Priority: `24`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `4`
- Live: Pokémon Stadium, Pokémon Sword and Shield, Pokémon Sun and Moon, Pokémon Scarlet & Violet
- Gold: Pokémon Stadium, Pokémon Sword and Shield, Pokémon Sun and Moon, Pokémon Scarlet & Violet
- Missing must-include: Pokémon Battle Revolution, Pokémon Stadium 2, Pokémon Scarlet and Violet

### Welcome to Doll Town

- Priority: `24`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `survival_horror` vs gold `psychological_horror`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `2`
- Live: Song of Horror Complete, Resident Evil 3: Nemesis, The Medium, Escape from Naraka, Until Dawn, Fear The Spotlight, The Evil Within 2, Decarnation, Dementium: The Ward, The Shore
- Gold: The Medium, Silent Hill 2, Song of Horror Complete, Fatal Frame: Maiden of the Black Water
- Missing must-include: DreadOut 2, Fatal Frame: Maiden of Black Water, Silent Hill 2

### Aether & Iron

- Priority: `18`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `turn_based_tactics` vs gold `turn_based_tactics`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `4`
- Live: Shadowrun: Hong Kong, Shadowrun: Dragonfall - Director's Cut, Wasteland 3, The Lamplighters League
- Gold: Shadowrun: Hong Kong, Shadowrun: Dragonfall - Director's Cut, Wasteland 3, The Lamplighters League
- Missing must-include: Sovereign Syndicate

### ARC Raiders

- Priority: `18`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `extraction_shooter` vs gold `extraction_shooter`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `5`
- Live: The Cycle: Frontier, SYNDUALITY: Echo of Ada, Escape from Tarkov, Vigor, Hunt: Showdown 1896
- Gold: The Cycle: Frontier, SYNDUALITY: Echo of Ada, Escape from Tarkov, Vigor, Hunt: Showdown 1896
- Missing must-include: Tom Clancy's The Division 2

### Collector's Cove

- Priority: `18`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `farming_sim` vs gold `farming_sim`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `3`
- Live: Summer in Mara, Moonglow Bay, Stardew Valley, Aqua Pals, Tiny Aquarium: Social Fishkeeping, Little Aviary, Nanomon Virtual Pet, My Cozy Aquarium, Tiny Pasture, Animal Shelter 2
- Gold: Summer in Mara, Stardew Valley, Animal Crossing: New Horizons, Moonglow Bay
- Missing must-include: Havendock

### Crimson Desert

- Priority: `18`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `open_world_fantasy_action_rpg` vs gold `open_world_fantasy_action_rpg`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `5`
- Live: Dragon's Dogma 2, Elden Ring, Dragon's Dogma: Dark Arisen, Black Myth: Wukong, The Witcher 3: Wild Hunt
- Gold: Dragon's Dogma 2, Elden Ring, Dragon's Dogma: Dark Arisen, Black Myth: Wukong, The Witcher 3: Wild Hunt
- Missing must-include: Black Desert

### Cursed Words: The Word Game That Isn't

- Priority: `18`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `word_puzzle_strategy` vs gold `word_puzzle_strategy`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `2`
- Live: Balatro, Letter Quest: Grimm's Journey Remastered
- Gold: Balatro, Letter Quest: Grimm's Journey Remastered
- Missing must-include: Bookworm Adventures Deluxe

### Ghost Master: Resurrection

- Priority: `18`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `hidden` vs gold `none`
- Similarity status: current `hidden` vs expected `hidden`
- Overlap: `0`
- Missing must-include: Ghost Master

### Granblue Fantasy

- Priority: `18`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `jrpg_story_rpg` vs gold `jrpg_story_rpg`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `2`
- Live: Another Eden: The Cat Beyond Time and Space, FANTASIAN Neo Dimension, Honkai: Star Rail, Last Dream: World Unknown, Beyond Galaxyland, Clair Obscur: Expedition 33, Dragon Quest VII Reimagined, Breath of Fire IV, Chrono Trigger, No More Heroes 3
- Gold: Honkai: Star Rail, Another Eden: The Cat Beyond Time and Space
- Missing must-include: Epic Seven

### Karigurashi Ren'ai: Living on Borrowed Love

- Priority: `18`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `visual_novel` vs gold `visual_novel`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `5`
- Live: Fureraba ~Friend to Lover~, Making*Lovers, Renai Karichaimashita: Koikari - Love For Hire, Sugar * Style, Sankaku Renai: Love Triangle Trouble
- Gold: Fureraba ~Friend to Lover~, Making*Lovers, Renai Karichaimashita: Koikari - Love For Hire, Sugar * Style, Sankaku Renai: Love Triangle Trouble
- Missing must-include: Sankaku Ren'ai: Love Triangle Trouble!

### Last Man Sitting

- Priority: `18`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `co_op_action_roguelite` vs gold `co_op_action_roguelite`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `4`
- Live: Risk of Rain 2, Gunfire Reborn, Roboquest, Alienation
- Gold: Risk of Rain 2, Gunfire Reborn, Roboquest, Alienation
- Missing must-include: Crab Champions

### Mr. Sleepy Man

- Priority: `18`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `3d_collectathon` vs gold `3d_collectathon`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `2`
- Live: Super Mario Odyssey, A Hat in Time, ILA: A Frosty Glide, Super Meat Boy 3D, Sonic Frontiers, Islands of Insight, Cavern of Dreams, Astral Ascent, Stick it to the Man!, Smushi Come Home
- Gold: Super Mario Odyssey, A Hat in Time, Psychonauts 2, SpongeBob SquarePants: Battle For Bikini Bottom - Rehydrated, Goat Simulator 3
- Missing must-include: Yooka-Laylee

### People of Note

- Priority: `18`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `jrpg_story_rpg` vs gold `jrpg_story_rpg`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `5`
- Live: Super Mario RPG, Mario & Luigi: Superstar Saga + Bowser's Minions, Clair Obscur: Expedition 33, Paper Mario: The Thousand-Year Door, Persona 5 Royal
- Gold: Super Mario RPG, Mario & Luigi: Superstar Saga + Bowser's Minions, Clair Obscur: Expedition 33, Paper Mario: The Thousand-Year Door, Persona 5 Royal
- Missing must-include: Rhapsody: A Musical Adventure

### RUBATO

- Priority: `18`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `metroidvania` vs gold `metroidvania`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `4`
- Live: Yoku's Island Express, Wuppo, Ori and the Blind Forest, Cavern of Dreams
- Gold: Yoku's Island Express, Wuppo, Ori and the Blind Forest, Cavern of Dreams
- Missing must-include: Tomba!

### Stitched Together

- Priority: `18`
- Action: `boost_canonical_neighbors`
- Taxonomy: current `jrpg_story_rpg` vs gold `jrpg_story_rpg`
- Similarity status: current `computed` vs expected `computed`
- Overlap: `3`
- Live: Omori, Bug Fables: The Everlasting Sapling, Persona 4 Golden
- Gold: Bug Fables: The Everlasting Sapling, Ikenfell, Omori, Persona 4 Golden
- Missing must-include: EarthBound
