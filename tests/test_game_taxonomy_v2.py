from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Text

from app.models.models import Game, GameSourceTaxonomyLabel
from app.services.game_taxonomy_v2 import (
    TAXONOMY_V2_STATUS_COMPUTED,
    TAXONOMY_V2_STATUS_HIDDEN,
    ArchetypeCandidate,
    _prefer_primary_archetype_candidate,
    analyze_taxonomy_v2_label,
    apply_taxonomy_v2_result_to_game,
    build_similarity_breakdown_v2,
    build_taxonomy_v2_text_corpus,
    build_game_taxonomy_v2,
    detect_taxonomy_v2_boilerplate_segments,
    extract_v2_evidence_from_description,
    extract_v2_evidence_from_source_labels,
    extract_taxonomy_v2_text_phrases,
    strip_taxonomy_v2_noise_segments,
    rank_taxonomy_v2_near_misses,
    refresh_game_taxonomy_v2_text,
)


def test_taxonomy_v2_model_fields_exist_with_expected_types():
    assert isinstance(Game.__table__.c.taxonomy_v2_secondary_archetypes.type.item_type, Text)
    assert isinstance(Game.__table__.c.taxonomy_v2_hard_exclusions.type.item_type, Text)
    assert isinstance(Game.__table__.c.taxonomy_v2_soft_penalties.type.item_type, Text)
    assert isinstance(Game.__table__.c.taxonomy_v2_text_sources.type.item_type, Text)
    assert "taxonomy_v2_fingerprint" in Game.__table__.c
    assert "taxonomy_v2_debug_payload" in Game.__table__.c
    assert "opencritic_description" in Game.__table__.c
    assert "steam_short_description" in Game.__table__.c
    assert "steam_detailed_description" in Game.__table__.c
    assert "metacritic_description" in Game.__table__.c
    assert "taxonomy_v2_text_corpus" in Game.__table__.c


def test_extract_v2_evidence_from_description_detects_open_world_fantasy_traversal():
    evidence = extract_v2_evidence_from_description(
        (
            "Explore a vast open world fantasy kingdom. Ride horseback, climb cliffs, "
            "glide across the skies, and embark on story quests while you customize your build."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("world_topology", "open_world") in pairs
    assert ("traversal_verbs", "horseback") in pairs
    assert ("traversal_verbs", "climbing") in pairs
    assert ("traversal_verbs", "gliding") in pairs
    assert ("progression_model", "quest_driven") in pairs
    assert ("progression_model", "buildcraft") in pairs
    assert ("setting", "high_fantasy") in pairs


def test_extract_v2_evidence_from_description_detects_open_air_adventure_language():
    evidence = extract_v2_evidence_from_description(
        (
            "Step into a world of discovery, exploration, and adventure in this stunning open-air adventure. "
            "Set your own path as the world waits to be explored."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("world_topology", "open_world") in pairs
    assert ("world_density", "handcrafted_discovery") in pairs
    assert ("session_shape", "campaign") in pairs


def test_extract_v2_evidence_from_description_detects_hyrule_style_open_air_signals():
    evidence = extract_v2_evidence_from_description(
        (
            "An open-air adventure across the land and skies of Hyrule. "
            "Use your powerful new abilities to fight back against enemies, climb cliffs, "
            "glide between floating islands, and discover special items and rewards."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("world_topology", "open_world") in pairs
    assert ("perspective", "third_person") in pairs
    assert ("setting", "high_fantasy") in pairs
    assert ("combat_presence", "dominant") in pairs
    assert ("combat_style", "hybrid") in pairs
    assert ("traversal_verbs", "gliding") in pairs
    assert ("progression_model", "gear_chase") in pairs


def test_extract_v2_evidence_from_description_detects_witcher_style_fantasy_narrative_signals():
    evidence = extract_v2_evidence_from_description(
        (
            "The Witcher is a story-driven, next-generation open world role-playing game set in a visually stunning "
            "fantasy universe full of meaningful choices and impactful consequences. You play as the professional "
            "monster hunter, Geralt of Rivia, tasked with finding a child of prophecy in a vast open world."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("world_topology", "open_world") in pairs
    assert ("setting", "high_fantasy") in pairs
    assert ("perspective", "third_person") in pairs
    assert ("combat_presence", "dominant") in pairs
    assert ("narrative_structure", "authored_branching") in pairs


def test_extract_v2_evidence_from_description_detects_elden_ring_style_world_and_boss_signals():
    evidence = extract_v2_evidence_from_description(
        (
            "The new fantasy action RPG. Rise, Tarnished, and be guided by grace to brandish the power of the Elden Ring "
            "and become an Elden Lord in the Lands Between. A vast world where open fields and huge dungeons are seamlessly "
            "connected. As you explore, challenging enemies and bosses await."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("setting", "dark_fantasy") in pairs
    assert ("setting", "mythic") in pairs
    assert ("world_topology", "open_world") in pairs
    assert ("combat_presence", "dominant") in pairs
    assert ("combat_structure", "boss_centric") in pairs
    assert ("challenge_model", "soulslike") in pairs


def test_extract_v2_evidence_from_description_does_not_promote_open_fields_alone_into_boss_world_profile():
    evidence = extract_v2_evidence_from_description(
        "Gallop on horseback across cobbled streets and open fields as rival families feud across Sicily."
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("world_topology", "open_world") not in pairs
    assert ("combat_structure", "boss_centric") not in pairs
    assert ("rules_goals", "defeat_bosses") not in pairs
    assert ("setting", "mythic") not in pairs


def test_extract_v2_evidence_from_description_treats_behind_the_wheel_as_driving_not_racing():
    evidence = extract_v2_evidence_from_description(
        "Mafiosi patrolled their protection rackets on foot, horseback, or behind the wheel of turn-of-the-century motorcars."
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("traversal_verbs", "driving") in pairs
    assert ("vehicular_theme", "cars") in pairs
    assert ("mechanics_structure", "vehicular_racing") not in pairs
    assert ("rules_goals", "win_races") not in pairs


def test_extract_v2_evidence_from_description_detects_paraglider_as_gliding():
    evidence = extract_v2_evidence_from_description(
        "Use your paraglider to cross the skies and explore distant cliffs."
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("traversal_verbs", "gliding") in pairs


def test_extract_v2_evidence_from_description_treats_hyrule_alone_as_setting_not_full_open_world_profile():
    evidence = extract_v2_evidence_from_description(
        "A legend returns to Hyrule in a new tale of courage and wisdom."
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("setting", "high_fantasy") in pairs
    assert ("setting", "mythic") in pairs
    assert ("world_topology", "open_world") not in pairs
    assert ("perspective", "third_person") not in pairs
    assert ("combat_style", "hybrid") not in pairs


def test_extract_v2_evidence_from_description_does_not_treat_shrines_alone_as_fantasy():
    evidence = extract_v2_evidence_from_description(
        "Explore historical villages, temples, and shrines across feudal provinces."
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("setting", "high_fantasy") not in pairs


def test_extract_v2_evidence_from_description_detects_historical_samurai_signals():
    evidence = extract_v2_evidence_from_description(
        "In feudal Japan, a samurai and shinobi fight through a historical open world during the Mongol invasion."
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("setting", "historical") in pairs


def test_build_game_taxonomy_v2_assigns_open_world_fantasy_action_rpg():
    game = Game(
        id=1,
        title="Crimson Desert Style",
        description=(
            "Explore a vast open world fantasy kingdom. Ride horseback, climb cliffs, "
            "glide through the sky, and embark on story quests while you customize your build."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(
            game_id=1,
            source="steam",
            facet="theme",
            raw_label="Action RPG",
            normalized_label="action rpg",
        ),
        GameSourceTaxonomyLabel(
            game_id=1,
            source="steam",
            facet="perspective",
            raw_label="Third Person",
            normalized_label="third person",
        ),
        GameSourceTaxonomyLabel(
            game_id=1,
            source="steam",
            facet="category",
            raw_label="Single-player",
            normalized_label="single-player",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_family == "rpg"
    assert result.primary_archetype == "open_world_fantasy_action_rpg"
    assert "open_world" in result.fingerprint["world_topology"]
    assert "third_person" in result.fingerprint["perspective"]
    assert "single_player" in result.fingerprint["mode_profile"]
    assert result.confidence is not None
    assert result.confidence >= 0.7


def test_build_game_taxonomy_v2_assigns_open_world_fantasy_action_rpg_from_crimson_desert_style_text():
    game = Game(
        id=15,
        title="Crimson Desert Style 2",
        steam_detailed_description=(
            "Crimson Desert is an open-world action-adventure set on the continent of Pywel. "
            "Explore a war-torn realm of medieval fantasy where the world is yours to explore. "
            "Experience the continent's stories and tales through quests, encounters, challenges, and battles. "
            "Roam the lands on various mounts from horses to even a dragon, and scale cliffsides and walls which you can leap from to glide. "
            "Each character has their own combat style, as well as unique skills and weapons, allowing you to experience the world and its battles in different ways."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(
            game_id=15,
            source="steam",
            facet="genre",
            raw_label="Action",
            normalized_label="action",
        ),
        GameSourceTaxonomyLabel(
            game_id=15,
            source="steam",
            facet="genre",
            raw_label="Adventure",
            normalized_label="adventure",
        ),
        GameSourceTaxonomyLabel(
            game_id=15,
            source="steam",
            facet="category",
            raw_label="Single-player",
            normalized_label="single-player",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "open_world_fantasy_action_rpg"
    assert "high_fantasy" in result.fingerprint["setting"]
    assert "quest_driven" in result.fingerprint["progression_model"]
    assert "horseback" in result.fingerprint["traversal_verbs"]
    assert "hybrid" in result.fingerprint["combat_style"]


def test_build_game_taxonomy_v2_assigns_witcher_like_profile_from_text():
    game = Game(
        id=196,
        title="Witcher Like",
        description=(
            "The Witcher is a story-driven, next-generation open world role-playing game set in a visually stunning "
            "fantasy universe full of meaningful choices and impactful consequences. In The Witcher you play as the "
            "professional monster hunter, Geralt of Rivia, tasked with finding a child of prophecy in a vast open world."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=196, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=196, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(
            game_id=196,
            source="steam",
            facet="category",
            raw_label="Single-player",
            normalized_label="single-player",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype in {"western_narrative_rpg", "open_world_fantasy_action_rpg"}
    assert "high_fantasy" in result.fingerprint["setting"]
    assert "third_person" in result.fingerprint["perspective"]
    assert "dominant" in result.fingerprint["combat_presence"]


def test_build_game_taxonomy_v2_assigns_soulslike_from_elden_style_text():
    game = Game(
        id=197,
        title="Elden Style",
        description=(
            "The new fantasy action RPG. Rise, Tarnished, and become an Elden Lord in the Lands Between. "
            "A vast world where open fields and huge dungeons with complex and three-dimensional designs are "
            "seamlessly connected. As you explore, challenging enemies and bosses await."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=197, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=197, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(
            game_id=197,
            source="steam",
            facet="category",
            raw_label="Single-player",
            normalized_label="single-player",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "soulslike_action_rpg"
    assert "dark_fantasy" in result.fingerprint["setting"]
    assert "boss_centric" in result.fingerprint["combat_structure"]


def test_build_game_taxonomy_v2_does_not_assign_open_world_fantasy_action_rpg_without_setting():
    game = Game(
        id=16,
        title="Historic Open World Adventure",
        steam_detailed_description=(
            "Explore a vast open world kingdom and forge your path through battles and discovery. "
            "Customize your build, improve your gear, and follow a story-driven campaign."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=16, source="steam", facet="tag", raw_label="Third Person", normalized_label="third person"),
        GameSourceTaxonomyLabel(game_id=16, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=16, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=16, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=16, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.primary_archetype != "open_world_fantasy_action_rpg"


def test_build_game_taxonomy_v2_rejects_platformer_first_for_open_world_fantasy_action_rpg():
    game = Game(
        id=17,
        title="Platforming Open World Hybrid",
        steam_detailed_description=(
            "Explore a fantasy world in a third-person adventure. "
            "Leap across platforming challenges in open zones, master skill trees, and race through level-based stages."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=17, source="steam", facet="tag", raw_label="Fantasy", normalized_label="fantasy"),
        GameSourceTaxonomyLabel(game_id=17, source="steam", facet="tag", raw_label="3D Platformer", normalized_label="3d platformer"),
        GameSourceTaxonomyLabel(game_id=17, source="steam", facet="tag", raw_label="Third Person", normalized_label="third person"),
        GameSourceTaxonomyLabel(game_id=17, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=17, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.primary_archetype != "open_world_fantasy_action_rpg"


def test_build_game_taxonomy_v2_rejects_historical_first_for_open_world_fantasy_action_rpg():
    game = Game(
        id=171,
        title="Historical Open World Warrior",
        steam_detailed_description=(
            "Explore an open world in feudal Japan as a samurai and shinobi during a historical conflict. "
            "Take on story quests, use stealth, and master melee combat."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=171, source="steam", facet="tag", raw_label="Open World", normalized_label="open world"),
        GameSourceTaxonomyLabel(game_id=171, source="steam", facet="tag", raw_label="Third Person", normalized_label="third person"),
        GameSourceTaxonomyLabel(game_id=171, source="steam", facet="tag", raw_label="Stealth", normalized_label="stealth"),
        GameSourceTaxonomyLabel(game_id=171, source="steam", facet="tag", raw_label="Singleplayer", normalized_label="singleplayer"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert "historical_first" in result.hard_exclusions
    assert result.primary_archetype != "open_world_fantasy_action_rpg"


def test_build_game_taxonomy_v2_rejects_tactical_overhead_profile_for_open_world_fantasy_action_rpg():
    game = Game(
        id=172,
        title="Overhead Fantasy War",
        steam_detailed_description=(
            "Command vast armies in an open world of dark fantasy. Build your empire, upgrade your factions, "
            "and direct battles from a tactical overhead viewpoint across a sprawling war-torn realm."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=172, source="steam", facet="tag", raw_label="Strategy", normalized_label="strategy"),
        GameSourceTaxonomyLabel(game_id=172, source="steam", facet="tag", raw_label="Open World", normalized_label="open world"),
        GameSourceTaxonomyLabel(game_id=172, source="steam", facet="tag", raw_label="Fantasy", normalized_label="fantasy"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert "overhead_strategy_first" in result.hard_exclusions
    assert result.primary_archetype != "open_world_fantasy_action_rpg"


def test_build_game_taxonomy_v2_rejects_cinematic_linear_profile_for_open_world_fantasy_action_rpg():
    game = Game(
        id=173,
        title="Cinematic Mythic Action",
        steam_detailed_description=(
            "A third-person mythic saga with an authored linear story, brutal boss battles, and new abilities. "
            "Fight through a focused journey across a high fantasy world."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=173, source="steam", facet="tag", raw_label="Third Person", normalized_label="third person"),
        GameSourceTaxonomyLabel(game_id=173, source="steam", facet="tag", raw_label="Fantasy", normalized_label="fantasy"),
        GameSourceTaxonomyLabel(game_id=173, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert "cinematic_linear_first" in result.hard_exclusions
    assert result.primary_archetype != "open_world_fantasy_action_rpg"


def test_build_game_taxonomy_v2_assigns_cinematic_action_adventure_from_mythic_linear_text():
    game = Game(
        id=174,
        title="Mythic Cinematic Adventure",
        steam_detailed_description=(
            "A cinematic action-adventure and mythic saga through the Norse realms. "
            "Follow the story of a father and son on an authored linear journey with brutal combat and epic boss battles."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=174, source="steam", facet="tag", raw_label="Third Person", normalized_label="third person"),
        GameSourceTaxonomyLabel(game_id=174, source="steam", facet="tag", raw_label="Cinematic", normalized_label="cinematic"),
        GameSourceTaxonomyLabel(game_id=174, source="steam", facet="tag", raw_label="Story Rich", normalized_label="story rich"),
        GameSourceTaxonomyLabel(game_id=174, source="steam", facet="tag", raw_label="Fantasy", normalized_label="fantasy"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "cinematic_action_adventure"
    assert "semi_open" in result.fingerprint["world_topology"]
    assert "setpiece_driven" in result.fingerprint["world_density"]
    assert "authored_linear" in result.fingerprint["narrative_structure"]


def test_build_game_taxonomy_v2_assigns_mmo_action_rpg_from_sandbox_mmorpg_text():
    game = Game(
        id=18,
        title="Sandbox MMORPG",
        opencritic_description=(
            "Black Desert Online is a sandbox MMORPG that features castle sieging, trading, crafting, "
            "player housing, parkour, and more. Players will enjoy intuitive skill-based combat in an expansive world."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=18, source="steam", facet="tag", raw_label="Third Person", normalized_label="third person"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "mmo_action_rpg"
    assert "mmo" in result.fingerprint["mode_profile"]
    assert "persistent_shared_world" in result.fingerprint["world_topology"]


def test_build_game_taxonomy_v2_enriches_black_desert_style_world_identity():
    game = Game(
        id=181,
        title="Black Desert Style",
        opencritic_description=(
            "Black Desert Online is a sandbox MMORPG featuring castle sieging, trading, crafting, player housing, "
            "parkour, and intuitive skill-based combat in an expansive world just waiting to be explored. "
            "Harness the Black Spirit and the power of Black Stones in a mythic fantasy realm."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=181, source="steam", facet="tag", raw_label="Third Person", normalized_label="third person"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "mmo_action_rpg"
    assert "open_world" in result.fingerprint["world_topology"]
    assert "high_fantasy" in result.fingerprint["setting"]


def test_prefer_primary_archetype_candidate_promotes_open_world_soulslike_profiles():
    candidates = [
        ArchetypeCandidate(
            archetype="open_world_fantasy_action_rpg",
            family="rpg",
            score=515,
            required_hits=5,
            required_total=6,
            preferred_hits=2,
            preferred_total=4,
            confidence=0.91,
        ),
        ArchetypeCandidate(
            archetype="soulslike_action_rpg",
            family="rpg",
            score=502,
            required_hits=5,
            required_total=6,
            preferred_hits=2,
            preferred_total=4,
            confidence=0.9,
        ),
    ]

    preferred = _prefer_primary_archetype_candidate(
        candidates,
        {
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_structure": ["boss_centric"],
            "challenge_model": ["soulslike"],
            "setting": ["dark_fantasy"],
            "rules_goals": ["defeat_bosses"],
        },
    )

    assert preferred[0].archetype == "soulslike_action_rpg"


def test_prefer_primary_archetype_candidate_avoids_soulslike_for_mythic_linear_action_profiles():
    candidates = [
        ArchetypeCandidate(
            archetype="open_world_fantasy_action_rpg",
            family="rpg",
            score=505,
            required_hits=5,
            required_total=6,
            preferred_hits=2,
            preferred_total=4,
            confidence=0.9,
        ),
        ArchetypeCandidate(
            archetype="soulslike_action_rpg",
            family="rpg",
            score=498,
            required_hits=5,
            required_total=6,
            preferred_hits=2,
            preferred_total=4,
            confidence=0.89,
        ),
        ArchetypeCandidate(
            archetype="open_world_action_adventure",
            family="action_adventure",
            score=492,
            required_hits=5,
            required_total=6,
            preferred_hits=3,
            preferred_total=4,
            confidence=0.88,
        ),
    ]

    preferred = _prefer_primary_archetype_candidate(
        candidates,
        {
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_structure": ["boss_centric"],
            "challenge_model": ["soulslike"],
            "setting": ["high_fantasy", "mythic"],
            "narrative_structure": ["authored_linear"],
            "rules_goals": ["defeat_bosses"],
        },
    )

    assert preferred[0].archetype == "open_world_action_adventure"


def test_prefer_primary_archetype_candidate_moves_open_world_platforming_profiles_out_of_fantasy_rpg():
    candidates = [
        ArchetypeCandidate(
            archetype="open_world_fantasy_action_rpg",
            family="rpg",
            score=505,
            required_hits=5,
            required_total=6,
            preferred_hits=2,
            preferred_total=4,
            confidence=0.9,
        ),
        ArchetypeCandidate(
            archetype="3d_collectathon",
            family="platformer",
            score=488,
            required_hits=4,
            required_total=5,
            preferred_hits=2,
            preferred_total=4,
            confidence=0.87,
        ),
    ]

    preferred = _prefer_primary_archetype_candidate(
        candidates,
        {
            "world_topology": ["open_world", "level_based"],
            "perspective": ["third_person"],
            "traversal_verbs": ["platforming"],
            "tone": ["comedic"],
            "setting": ["high_fantasy"],
        },
    )

    assert preferred[0].archetype == "3d_collectathon"


def test_prefer_primary_archetype_candidate_keeps_crimson_like_profiles_in_open_world_fantasy_lane():
    candidates = [
        ArchetypeCandidate(
            archetype="open_world_action_adventure",
            family="action_adventure",
            score=433,
            required_hits=4,
            required_total=4,
            preferred_hits=1,
            preferred_total=1,
            confidence=0.95,
        ),
        ArchetypeCandidate(
            archetype="open_world_fantasy_action_rpg",
            family="rpg",
            score=633,
            required_hits=6,
            required_total=6,
            preferred_hits=1,
            preferred_total=2,
            confidence=0.91,
        ),
    ]

    preferred = _prefer_primary_archetype_candidate(
        candidates,
        {
            "world_topology": ["open_world"],
            "world_density": ["handcrafted_discovery"],
            "session_shape": ["campaign"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "melee"],
            "combat_structure": ["boss_centric"],
            "traversal_verbs": ["gliding", "horseback"],
            "progression_model": ["quest_driven", "buildcraft", "skill_tree"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
            "rules_goals": ["complete_quests", "defeat_bosses"],
        },
    )

    assert preferred[0].archetype == "open_world_fantasy_action_rpg"


def test_build_game_taxonomy_v2_assigns_jrpg_story_rpg_from_turn_based_party_language():
    game = Game(
        id=19,
        title="Classic JRPG",
        steam_detailed_description=(
            "A classic JRPG adventure with turn-based combat, a cast of characters, Japanese voice acting, "
            "and an epic quest to save the world."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=19, source="steam", facet="tag", raw_label="JRPG", normalized_label="jrpg"),
        GameSourceTaxonomyLabel(game_id=19, source="steam", facet="tag", raw_label="Singleplayer", normalized_label="singleplayer"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "jrpg_story_rpg"
    assert "party_management" in result.fingerprint["combat_structure"]
    assert "authored_linear" in result.fingerprint["narrative_structure"]


def test_build_game_taxonomy_v2_marks_jrpg_first_and_blocks_open_world_fantasy_overfire():
    game = Game(
        id=191,
        title="Anime Open World Party RPG",
        steam_detailed_description=(
            "Explore an open world fantasy realm with a party of heroes in this classic JRPG adventure. "
            "Turn-based combat, Japanese voice acting, a cast of characters, and an epic quest to save the world await."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=191, source="steam", facet="tag", raw_label="Anime", normalized_label="anime"),
        GameSourceTaxonomyLabel(game_id=191, source="steam", facet="tag", raw_label="JRPG", normalized_label="jrpg"),
        GameSourceTaxonomyLabel(game_id=191, source="steam", facet="tag", raw_label="Open World", normalized_label="open world"),
        GameSourceTaxonomyLabel(game_id=191, source="steam", facet="tag", raw_label="Singleplayer", normalized_label="singleplayer"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "jrpg_story_rpg"
    assert "jrpg_first" in result.hard_exclusions
    assert result.primary_archetype != "open_world_fantasy_action_rpg"


def test_build_game_taxonomy_v2_treats_one_on_one_duels_as_boss_centric_not_pvp():
    game = Game(
        id=192,
        title="Boss Duel Fantasy Adventure",
        steam_detailed_description=(
            "Explore a war-torn realm of medieval fantasy, ride horseback, and embark on story quests. "
            "Encounter a diverse array of challenging enemies and bosses in brutal one-on-one duels."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=192, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=192, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=192, source="steam", facet="tag", raw_label="Third Person", normalized_label="third person"),
        GameSourceTaxonomyLabel(game_id=192, source="steam", facet="tag", raw_label="Singleplayer", normalized_label="singleplayer"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "open_world_fantasy_action_rpg"
    assert "boss_centric" in result.fingerprint["combat_structure"]
    assert "defeat_bosses" in result.fingerprint["rules_goals"]
    assert "pvp" not in result.fingerprint["mode_profile"]
    assert "traditional_fighter" not in result.secondary_archetypes


def test_build_game_taxonomy_v2_assigns_open_world_fantasy_action_rpg_from_hyrule_style_text():
    game = Game(
        id=193,
        title="Hyrule Style Adventure",
        opencritic_description=(
            "In this open-air adventure across the land and skies of Hyrule, use your powerful new abilities to fight back "
            "against enemies, climb cliffs, glide between floating islands, and uncover special items and rewards."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=193, source="opencritic", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=193, source="opencritic", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=193, source="steam", facet="tag", raw_label="Singleplayer", normalized_label="singleplayer"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "open_world_fantasy_action_rpg"
    assert "third_person" in result.fingerprint["perspective"]
    assert "high_fantasy" in result.fingerprint["setting"]
    assert "hybrid" in result.fingerprint["combat_style"]


def test_build_game_taxonomy_v2_prefers_western_narrative_rpg_primary_for_quest_and_dialogue_heavy_open_world_fantasy_profiles():
    game = Game(
        id=194,
        title="Quest Heavy Fantasy RPG",
        steam_detailed_description=(
            "Explore a third-person open world fantasy kingdom, ride horseback across the realm, and take on story quests. "
            "Shape the fate of the kingdom through dialogue choices in a branching story where choices matter."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=194, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=194, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=194, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=194, source="steam", facet="tag", raw_label="Third Person", normalized_label="third person"),
        GameSourceTaxonomyLabel(game_id=194, source="steam", facet="tag", raw_label="Fantasy", normalized_label="fantasy"),
        GameSourceTaxonomyLabel(game_id=194, source="steam", facet="tag", raw_label="Singleplayer", normalized_label="singleplayer"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "western_narrative_rpg"
    assert "open_world_fantasy_action_rpg" in result.secondary_archetypes
    assert "dialogue_choice" in result.fingerprint["entity_interaction"]
    assert "complete_quests" in result.fingerprint["rules_goals"]


def test_build_game_taxonomy_v2_prefers_soulslike_primary_for_boss_centric_open_world_dark_fantasy_profiles():
    game = Game(
        id=195,
        title="Soulslike Wasteland",
        steam_detailed_description=(
            "Venture through a third-person open world of dark fantasy in a punishing soulslike action RPG. "
            "Master brutal boss battles, refine your build, and survive a bleak realm where every duel can kill you."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=195, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=195, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=195, source="steam", facet="tag", raw_label="Third Person", normalized_label="third person"),
        GameSourceTaxonomyLabel(game_id=195, source="steam", facet="tag", raw_label="Dark Fantasy", normalized_label="dark fantasy"),
        GameSourceTaxonomyLabel(game_id=195, source="steam", facet="tag", raw_label="Souls-like", normalized_label="souls-like"),
        GameSourceTaxonomyLabel(game_id=195, source="steam", facet="tag", raw_label="Singleplayer", normalized_label="singleplayer"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "soulslike_action_rpg"
    assert "open_world_fantasy_action_rpg" in result.secondary_archetypes
    assert "soulslike" in result.fingerprint["challenge_model"]
    assert "boss_centric" in result.fingerprint["combat_structure"]


def test_build_game_taxonomy_v2_assigns_monster_collect_rpg_from_monster_taming_language():
    game = Game(
        id=20,
        title="Monster Tamer",
        steam_detailed_description=(
            "Capture monsters, tame monsters, and befriend creatures as you build your party for an epic campaign."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=20, source="steam", facet="tag", raw_label="Monster Taming", normalized_label="monster taming"),
        GameSourceTaxonomyLabel(game_id=20, source="steam", facet="tag", raw_label="Singleplayer", normalized_label="singleplayer"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "monster_collect_rpg"
    assert "whimsical" in result.fingerprint["tone"]
    assert "party_management" in result.fingerprint["combat_structure"]


def test_build_game_taxonomy_v2_assigns_hero_shooter_from_team_based_hero_language():
    game = Game(
        id=21,
        title="Hero Shooter",
        steam_detailed_description=(
            "A team-based shooter where unique heroes face off in online multiplayer matches."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=21, source="steam", facet="tag", raw_label="First-Person", normalized_label="first-person"),
        GameSourceTaxonomyLabel(game_id=21, source="steam", facet="tag", raw_label="Shooter", normalized_label="shooter"),
        GameSourceTaxonomyLabel(game_id=21, source="steam", facet="category", raw_label="Online PvP", normalized_label="online pvp"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "hero_shooter"
    assert "match_session" in result.fingerprint["session_shape"]
    assert "crowd_control" in result.fingerprint["combat_structure"]


def test_build_game_taxonomy_v2_does_not_assign_arena_fps_to_campaign_only_shooter():
    game = Game(
        id=22,
        title="Campaign Shooter",
        steam_detailed_description=(
            "A first-person shooter single-player campaign with an arsenal of weapons and a story-driven campaign."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=22, source="steam", facet="tag", raw_label="Shooter", normalized_label="shooter"),
        GameSourceTaxonomyLabel(game_id=22, source="steam", facet="tag", raw_label="First-Person", normalized_label="first-person"),
        GameSourceTaxonomyLabel(game_id=22, source="steam", facet="tag", raw_label="Singleplayer", normalized_label="singleplayer"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert "campaign_only" in result.hard_exclusions
    assert result.primary_archetype not in {"arena_fps", "hero_shooter"}


def test_build_game_taxonomy_v2_assigns_action_platformer_from_side_scrolling_action_text():
    game = Game(
        id=23,
        title="Action Platformer",
        steam_detailed_description=(
            "A side-scrolling action game where you jump and slash through levels and battle enemies and bosses."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=23, source="steam", facet="tag", raw_label="2D Platformer", normalized_label="2d platformer"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "action_platformer"
    assert "platforming" in result.fingerprint["traversal_verbs"]
    assert "encounter_driven" in result.fingerprint["combat_structure"]


def test_build_game_taxonomy_v2_assigns_hidden_object_puzzle_from_point_and_click_mystery():
    game = Game(
        id=24,
        title="Hidden Object Mystery",
        steam_detailed_description=(
            "A point-and-click mystery where you search for clues, solve environmental puzzles, and uncover the mystery."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24, source="steam", facet="tag", raw_label="Hidden Object", normalized_label="hidden object"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "hidden_object_puzzle"
    assert "puzzle_gating" in result.fingerprint["challenge_model"]
    assert "none" in result.fingerprint["combat_presence"]


def test_build_game_taxonomy_v2_assigns_sports_sim_from_soccer_and_simulation_labels():
    game = Game(id=25, title="Football Sim")
    rows = [
        GameSourceTaxonomyLabel(game_id=25, source="steam", facet="tag", raw_label="Soccer", normalized_label="soccer"),
        GameSourceTaxonomyLabel(game_id=25, source="steam", facet="genre", raw_label="Simulation", normalized_label="simulation"),
        GameSourceTaxonomyLabel(game_id=25, source="steam", facet="tag", raw_label="Singleplayer", normalized_label="singleplayer"),
        GameSourceTaxonomyLabel(game_id=25, source="steam", facet="category", raw_label="Online PvP", normalized_label="online pvp"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "sports_sim"
    assert "match_session" in result.fingerprint["session_shape"]
    assert "sim_realism" in result.fingerprint["challenge_model"]


def test_build_similarity_breakdown_v2_filters_generic_buildcraft_only_same_bucket_matches():
    anchor = Game(
        id=100,
        title="Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft"],
            "setting": ["high_fantasy"],
            "traversal_verbs": ["horseback"],
            "tone": ["melancholic"],
            "mode_profile": ["single_player"],
        },
    )
    generic = Game(
        id=101,
        title="Generic",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft", "quest_driven"],
            "mode_profile": ["single_player"],
        },
    )
    identity_rich = Game(
        id=102,
        title="Identity Rich",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft"],
            "setting": ["high_fantasy"],
            "traversal_verbs": ["horseback"],
            "tone": ["melancholic"],
            "mode_profile": ["single_player"],
        },
    )

    identity_breakdown = build_similarity_breakdown_v2(anchor, identity_rich)

    assert build_similarity_breakdown_v2(anchor, generic) is None
    assert identity_breakdown is not None


def test_build_similarity_breakdown_v2_filters_survival_sandbox_same_bucket_matches_for_authored_fantasy_anchor():
    anchor = Game(
        id=1002,
        title="Authored Fantasy Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_style": ["hybrid"],
            "traversal_verbs": ["horseback", "gliding"],
            "progression_model": ["base_growth", "buildcraft", "quest_driven"],
            "rules_goals": ["build_and_optimize", "complete_quests"],
            "entity_interaction": ["construction_placement"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )
    sandbox_candidate = Game(
        id=1003,
        title="Sandbox Candidate",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_style": ["melee"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["buildcraft"],
            "session_shape": ["campaign", "sandbox_loop"],
            "world_density": ["handcrafted_discovery", "systemic_sandbox"],
            "mode_profile": ["drop_in_coop", "single_player"],
            "setting": ["dark_fantasy", "high_fantasy"],
            "rules_goals": ["defeat_bosses", "solve_mysteries"],
            "entity_interaction": ["dialogue_choice"],
        },
    )

    assert build_similarity_breakdown_v2(anchor, sandbox_candidate) is None


def test_build_similarity_breakdown_v2_filters_jrpg_first_candidates_from_open_world_fantasy_matches():
    anchor = Game(
        id=106,
        title="Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "traversal_verbs": ["horseback"],
            "progression_model": ["quest_driven", "gear_chase"],
            "setting": ["high_fantasy"],
            "mode_profile": ["single_player"],
        },
    )
    jrpg_candidate = Game(
        id=107,
        title="Anime Party Candidate",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_hard_exclusions=["jrpg_first"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "combat_structure": ["party_management"],
            "progression_model": ["quest_driven", "buildcraft"],
            "setting": ["high_fantasy"],
            "art_style": ["anime"],
            "mode_profile": ["single_player"],
        },
    )

    assert build_similarity_breakdown_v2(anchor, jrpg_candidate) is None


def test_build_similarity_breakdown_v2_filters_isometric_candidates_from_open_world_fantasy_matches():
    anchor = Game(
        id=1071,
        title="Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "traversal_verbs": ["horseback", "gliding"],
            "progression_model": ["quest_driven", "skill_tree"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )
    isometric_candidate = Game(
        id=1072,
        title="Isometric Candidate",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["isometric", "third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "traversal_verbs": ["gliding"],
            "progression_model": ["buildcraft", "skill_tree"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )

    assert build_similarity_breakdown_v2(anchor, isometric_candidate) is None


def test_build_similarity_breakdown_v2_keeps_mmo_first_adjacent_candidates_eligible():
    anchor = Game(
        id=108,
        title="Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft", "quest_driven"],
            "setting": ["high_fantasy"],
            "mode_profile": ["single_player"],
        },
    )
    mmo_candidate = Game(
        id=109,
        title="MMO Candidate",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="mmo_action_rpg",
        taxonomy_v2_hard_exclusions=["mmo_first"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world", "persistent_shared_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft"],
            "setting": ["high_fantasy"],
            "mode_profile": ["mmo"],
            "content_model": ["mmo_persistent"],
        },
        taxonomy_studios=["pearl abyss"],
    )
    anchor.taxonomy_studios = ["pearl abyss"]

    breakdown = build_similarity_breakdown_v2(anchor, mmo_candidate)

    assert breakdown is not None
    assert breakdown.relationship == "adjacent_neighbor"


def test_build_similarity_breakdown_v2_rewards_strict_studio_bridge_for_adjacent_mmo_matches():
    anchor = Game(
        id=110,
        title="Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft", "quest_driven"],
            "rules_goals": ["complete_quests"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
        taxonomy_studios=["pearl abyss"],
    )
    weak_adjacent = Game(
        id=111,
        title="Weak Adjacent",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="mmo_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world", "persistent_shared_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["mmo"],
            "content_model": ["mmo_persistent"],
        },
        taxonomy_studios=["other studio"],
    )
    bridged_adjacent = Game(
        id=112,
        title="Bridged Adjacent",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="mmo_action_rpg",
        taxonomy_v2_fingerprint=weak_adjacent.taxonomy_v2_fingerprint,
        taxonomy_studios=["pearl abyss"],
    )

    weak_breakdown = build_similarity_breakdown_v2(anchor, weak_adjacent)
    bridged_breakdown = build_similarity_breakdown_v2(anchor, bridged_adjacent)

    assert weak_breakdown is not None
    assert bridged_breakdown is not None
    assert bridged_breakdown.score > weak_breakdown.score


def test_build_similarity_breakdown_v2_prefers_adjacent_mmo_world_dna_over_generic_same_bucket():
    anchor = Game(
        id=1121,
        title="Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["base_growth", "buildcraft", "quest_driven", "skill_tree"],
            "traversal_verbs": ["horseback", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
            "mechanics_structure": ["quest_exploration_loop", "settlement_building"],
            "rules_goals": ["build_and_optimize", "complete_quests", "defeat_bosses"],
            "entity_interaction": ["construction_placement"],
        },
        taxonomy_studios=["pearl abyss"],
    )
    generic_same_bucket = Game(
        id=1122,
        title="Generic Same Bucket",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft", "skill_tree"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
            "keyword_layer": ["open_world_exploration"],
            "mechanics_structure": ["quest_exploration_loop"],
        },
    )
    bridged_adjacent = Game(
        id=1123,
        title="Bridged Adjacent",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="mmo_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world", "persistent_shared_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["base_growth", "buildcraft", "colony_growth"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["mmo"],
            "content_model": ["mmo_persistent"],
            "mechanics_structure": ["quest_exploration_loop", "settlement_building", "systemic_problem_solving"],
            "rules_goals": ["build_and_optimize"],
            "entity_interaction": ["construction_placement"],
        },
        taxonomy_studios=["pearl abyss"],
    )

    generic_breakdown = build_similarity_breakdown_v2(anchor, generic_same_bucket)
    bridged_breakdown = build_similarity_breakdown_v2(anchor, bridged_adjacent)

    assert generic_breakdown is None
    assert bridged_breakdown is not None


def test_build_similarity_breakdown_v2_rewards_traversal_identity_bridge_for_open_world_fantasy_matches():
    anchor = Game(
        id=1124,
        title="Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft", "quest_driven"],
            "traversal_verbs": ["horseback", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )
    no_traversal = Game(
        id=1125,
        title="No Traversal",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft", "quest_driven"],
            "rules_goals": ["complete_quests"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )
    traversal_peer = Game(
        id=1126,
        title="Traversal Peer",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["gear_chase"],
            "traversal_verbs": ["climbing"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )

    no_traversal_breakdown = build_similarity_breakdown_v2(anchor, no_traversal)
    traversal_breakdown = build_similarity_breakdown_v2(anchor, traversal_peer)

    assert no_traversal_breakdown is None
    assert traversal_breakdown is not None


def test_build_similarity_breakdown_v2_penalizes_soulslike_detours_without_traversal_or_quests():
    anchor = Game(
        id=1127,
        title="Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["buildcraft", "quest_driven"],
            "traversal_verbs": ["horseback", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
            "rules_goals": ["complete_quests", "defeat_bosses"],
        },
    )
    traversal_peer = Game(
        id=1128,
        title="Traversal Peer",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["gear_chase"],
            "traversal_verbs": ["climbing"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )
    soulslike_detour = Game(
        id=1129,
        title="Soulslike Detour",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft", "skill_tree"],
            "challenge_model": ["soulslike"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
            "rules_goals": ["defeat_bosses"],
        },
    )

    traversal_breakdown = build_similarity_breakdown_v2(anchor, traversal_peer)
    soulslike_breakdown = build_similarity_breakdown_v2(anchor, soulslike_detour)

    assert traversal_breakdown is not None
    assert soulslike_breakdown is not None
    assert traversal_breakdown.score > soulslike_breakdown.score


def test_build_similarity_breakdown_v2_rewards_adjacent_persistent_world_identity_bridge():
    anchor = Game(
        id=113,
        title="Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )
    base_adjacent = Game(
        id=114,
        title="Base Adjacent",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="mmo_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["persistent_shared_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["mmo"],
            "content_model": ["mmo_persistent"],
        },
    )
    bridged_adjacent = Game(
        id=115,
        title="Open World MMO Adjacent",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="mmo_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world", "persistent_shared_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["mmo"],
            "content_model": ["mmo_persistent"],
        },
    )

    base_breakdown = build_similarity_breakdown_v2(anchor, base_adjacent)
    bridged_breakdown = build_similarity_breakdown_v2(anchor, bridged_adjacent)

    assert base_breakdown is None
    assert bridged_breakdown is not None


def test_build_similarity_breakdown_v2_does_not_overreward_extra_combat_style_overlap_for_western_neighbors():
    anchor = Game(
        id=116,
        title="Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "melee"],
            "progression_model": ["quest_driven", "buildcraft"],
            "traversal_verbs": ["horseback"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )
    witcher_like = Game(
        id=117,
        title="Witcher Like",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="western_narrative_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["quest_driven", "buildcraft"],
            "setting": ["high_fantasy", "dark_fantasy"],
            "narrative_structure": ["authored_branching"],
            "entity_interaction": ["dialogue_choice"],
            "mode_profile": ["single_player"],
        },
    )
    amalur_like = Game(
        id=118,
        title="Amalur Like",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="western_narrative_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "melee"],
            "progression_model": ["quest_driven", "buildcraft", "skill_tree"],
            "setting": ["high_fantasy"],
            "narrative_structure": ["authored_branching"],
            "entity_interaction": ["dialogue_choice"],
            "mode_profile": ["single_player"],
        },
    )

    witcher_breakdown = build_similarity_breakdown_v2(anchor, witcher_like)
    amalur_breakdown = build_similarity_breakdown_v2(anchor, amalur_like)

    assert witcher_breakdown is not None
    assert amalur_breakdown is not None
    assert (amalur_breakdown.score - witcher_breakdown.score) < 20


def test_build_similarity_breakdown_v2_filters_generic_open_world_action_adventure_detours_for_fantasy_rpg_anchor():
    anchor = Game(
        id=122,
        title="Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "melee"],
            "progression_model": ["quest_driven", "buildcraft"],
            "traversal_verbs": ["horseback", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )
    detour = Game(
        id=123,
        title="Generic Open World Adventure",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_action_adventure",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["quest_driven", "buildcraft"],
            "rules_goals": ["complete_quests"],
            "setting": ["modern"],
            "mode_profile": ["single_player"],
        },
    )

    assert build_similarity_breakdown_v2(anchor, detour) is None


def test_build_similarity_breakdown_v2_allows_cinematic_action_adventure_bridge_for_fantasy_anchor():
    anchor = Game(
        id=124,
        title="The Legend of Zelda: Tears of the Kingdom",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "world_density": ["handcrafted_discovery"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft", "quest_driven"],
            "traversal_verbs": ["climbing", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "rules_goals": ["complete_quests", "defeat_bosses"],
            "narrative_topic": ["heroic_journey"],
            "mode_profile": ["single_player"],
        },
    )
    god_of_war_like = Game(
        id=125,
        title="God of War",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="cinematic_action_adventure",
        taxonomy_v2_fingerprint={
            "world_topology": ["semi_open"],
            "world_density": ["setpiece_driven"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "melee"],
            "combat_structure": ["boss_centric"],
            "narrative_structure": ["authored_linear"],
            "setting": ["high_fantasy", "mythic"],
            "tone": ["heroic"],
            "rules_goals": ["defeat_bosses"],
            "narrative_topic": ["heroic_journey"],
            "mode_profile": ["single_player"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, god_of_war_like)

    assert breakdown is not None
    assert breakdown.relationship in {"adjacent_neighbor", "adjacent_secondary", "strong_secondary"}


def test_build_similarity_breakdown_v2_allows_cinematic_action_anchor_to_open_world_fantasy_bridge():
    anchor = Game(
        id=126,
        title="God of War",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="cinematic_action_adventure",
        taxonomy_v2_fingerprint={
            "world_topology": ["semi_open"],
            "world_density": ["setpiece_driven"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["buildcraft", "skill_tree"],
            "narrative_structure": ["authored_linear"],
            "setting": ["mythic"],
            "tone": ["heroic"],
            "mode_profile": ["single_player"],
        },
    )
    totk_like = Game(
        id=127,
        title="The Legend of Zelda: Tears of the Kingdom",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft", "skill_tree"],
            "traversal_verbs": ["climbing", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "rules_goals": ["defeat_bosses"],
            "mode_profile": ["single_player"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, totk_like)

    assert breakdown is not None
    assert breakdown.score >= 220


def test_build_similarity_breakdown_v2_does_not_treat_cinematic_linear_first_as_pair_blocker():
    anchor = Game(
        id=128,
        title="The Legend of Zelda: Tears of the Kingdom",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_hard_exclusions=[],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft", "skill_tree"],
            "traversal_verbs": ["climbing", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "rules_goals": ["defeat_bosses"],
            "mode_profile": ["single_player"],
        },
    )
    candidate = Game(
        id=129,
        title="God of War",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="cinematic_action_adventure",
        taxonomy_v2_hard_exclusions=["cinematic_linear_first"],
        taxonomy_v2_fingerprint={
            "world_topology": ["semi_open"],
            "world_density": ["setpiece_driven"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["buildcraft", "skill_tree"],
            "narrative_structure": ["authored_linear"],
            "setting": ["mythic"],
            "tone": ["heroic"],
            "rules_goals": ["defeat_bosses"],
            "mode_profile": ["single_player"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None


def test_build_similarity_breakdown_v2_filters_beat_em_up_and_collectathon_detours_for_fantasy_rpg_anchor():
    anchor = Game(
        id=500,
        title="Crimson Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["melee", "hybrid"],
            "progression_model": ["quest_driven", "buildcraft"],
            "traversal_verbs": ["horseback", "climbing", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "tone": ["heroic"],
            "rules_goals": ["complete_quests", "defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
    )
    detour = Game(
        id=501,
        title="Pathless Detour",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="beat_em_up",
        taxonomy_v2_secondary_archetypes=["open_world_action_adventure", "3d_collectathon"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world", "level_based"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["melee"],
            "combat_structure": ["boss_centric"],
            "traversal_verbs": ["gliding", "platforming"],
            "setting": ["high_fantasy"],
            "rules_goals": ["defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
    )

    assert build_similarity_breakdown_v2(anchor, detour) is None


def test_build_similarity_breakdown_v2_penalizes_puzzle_noncombat_detours_for_combat_rpg_anchor():
    anchor = Game(
        id=119,
        title="Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft", "quest_driven"],
            "rules_goals": ["complete_quests"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )
    clean_candidate = Game(
        id=120,
        title="Clean Candidate",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft", "quest_driven"],
            "rules_goals": ["complete_quests"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )
    puzzle_candidate = Game(
        id=121,
        title="Puzzle Candidate",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant", "none"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft", "quest_driven"],
            "rules_goals": ["complete_quests"],
            "challenge_model": ["puzzle_gating"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )

    clean_breakdown = build_similarity_breakdown_v2(anchor, clean_candidate)
    puzzle_breakdown = build_similarity_breakdown_v2(anchor, puzzle_candidate)

    assert clean_breakdown is not None
    assert puzzle_breakdown is not None
    assert clean_breakdown.score > puzzle_breakdown.score


def test_build_similarity_breakdown_v2_allows_sparse_open_world_fantasy_same_lane_when_traversal_and_quests_match():
    anchor = Game(
        id=122,
        title="Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["horseback", "gliding"],
            "rules_goals": ["complete_quests", "defeat_bosses"],
            "setting": ["high_fantasy", "mythic"],
            "progression_model": ["quest_driven"],
        },
    )
    candidate = Game(
        id=123,
        title="Candidate",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["climbing", "gliding"],
            "rules_goals": ["complete_quests", "defeat_bosses"],
            "setting": ["high_fantasy", "mythic"],
            "progression_model": ["buildcraft"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None


def test_build_similarity_breakdown_v2_allows_sparse_zelda_like_anchor_to_soulslike_bridge():
    anchor = Game(
        id=124,
        title="TOTK-like Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["climbing", "gliding"],
            "rules_goals": ["defeat_bosses"],
            "setting": ["high_fantasy", "mythic"],
        },
    )
    candidate = Game(
        id=125,
        title="Soulslike Candidate",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_style": ["melee"],
            "combat_structure": ["boss_centric"],
            "challenge_model": ["soulslike"],
            "rules_goals": ["defeat_bosses"],
            "setting": ["high_fantasy", "mythic"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None


def test_build_similarity_breakdown_v2_rejects_under_specified_soulslike_bridge_candidate():
    anchor = Game(
        id=126,
        title="TOTK-like Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["climbing", "gliding"],
            "rules_goals": ["defeat_bosses"],
            "setting": ["high_fantasy", "mythic"],
        },
    )
    weak_candidate = Game(
        id=127,
        title="Weak Soulslike Candidate",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "setting": ["mythic"],
        },
    )

    assert build_similarity_breakdown_v2(anchor, weak_candidate) is None


def test_build_similarity_breakdown_v2_rejects_fake_soulslike_bridge_with_only_boss_goal_and_melee():
    anchor = Game(
        id=128,
        title="TOTK-like Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["climbing", "gliding"],
            "rules_goals": ["defeat_bosses"],
            "setting": ["high_fantasy", "mythic"],
        },
    )
    fake_candidate = Game(
        id=129,
        title="Fake Soulslike Candidate",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_style": ["melee"],
            "rules_goals": ["defeat_bosses"],
            "setting": ["high_fantasy", "mythic"],
        },
    )

    assert build_similarity_breakdown_v2(anchor, fake_candidate) is None


def test_build_similarity_breakdown_v2_rejects_perspective_ambiguous_soulslike_for_third_person_anchor():
    anchor = Game(
        id=130,
        title="Elden-Like Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "combat_structure": ["boss_centric"],
            "challenge_model": ["soulslike"],
            "rules_goals": ["defeat_bosses"],
            "setting": ["dark_fantasy", "mythic"],
        },
    )
    candidate = Game(
        id=131,
        title="Perspective-Ambiguous Soulslike",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "combat_structure": ["boss_centric"],
            "challenge_model": ["soulslike"],
            "rules_goals": ["defeat_bosses"],
            "setting": ["dark_fantasy", "mythic"],
            "visual_presentation": ["side_scrolling_2d"],
        },
    )

    assert build_similarity_breakdown_v2(anchor, candidate) is None


def test_build_game_taxonomy_v2_infers_defeat_bosses_from_soulslike_profile():
    game = Game(id=194, title="Soulslike Test")
    rows = [
        GameSourceTaxonomyLabel(game_id=194, source="steam", facet="tag", raw_label="Souls-like", normalized_label="souls-like"),
        GameSourceTaxonomyLabel(game_id=194, source="steam", facet="tag", raw_label="Third Person", normalized_label="third person"),
        GameSourceTaxonomyLabel(game_id=194, source="steam", facet="tag", raw_label="Dark Fantasy", normalized_label="dark fantasy"),
        GameSourceTaxonomyLabel(game_id=194, source="steam", facet="tag", raw_label="Open World", normalized_label="open world"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert "defeat_bosses" in result.fingerprint["rules_goals"]


def test_build_similarity_breakdown_v2_uses_derived_keyword_and_mechanics_similarity():
    anchor = Game(
        id=103,
        title="Anchor",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="monster_collect_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "world_topology": ["semi_open"],
            "combat_structure": ["party_management"],
            "progression_model": ["buildcraft", "skill_tree"],
            "tone": ["whimsical"],
            "keyword_layer": ["monster_taming"],
            "mechanics_structure": ["creature_collection"],
            "rules_goals": ["capture_and_raise_companions"],
            "entity_interaction": ["creature_collection"],
        },
    )
    weak = Game(
        id=104,
        title="Weak Match",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="monster_collect_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "world_topology": ["semi_open"],
            "combat_structure": ["party_management"],
            "progression_model": ["buildcraft"],
            "tone": ["whimsical"],
        },
    )
    rich = Game(
        id=105,
        title="Rich Match",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="monster_collect_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "world_topology": ["semi_open"],
            "combat_structure": ["party_management"],
            "progression_model": ["buildcraft", "skill_tree"],
            "tone": ["whimsical"],
            "keyword_layer": ["monster_taming"],
            "mechanics_structure": ["creature_collection"],
            "rules_goals": ["capture_and_raise_companions"],
            "entity_interaction": ["creature_collection"],
        },
    )

    weak_breakdown = build_similarity_breakdown_v2(anchor, weak)
    rich_breakdown = build_similarity_breakdown_v2(anchor, rich)

    assert weak_breakdown is not None
    assert rich_breakdown is not None
    assert rich_breakdown.derived_similarity_score > weak_breakdown.derived_similarity_score
    assert rich_breakdown.score > weak_breakdown.score


def test_build_taxonomy_v2_text_corpus_merges_source_specific_descriptions():
    game = Game(
        id=11,
        title="Corpus Test",
        description="A short generic blurb about an adventure across a ruined world.",
        opencritic_description="A short generic blurb about an adventure across a ruined world.",
        steam_detailed_description=(
            "The Digital Deluxe Edition includes the full game and soundtrack. "
            "Explore a vast open world kingdom, climb cliffs, and ride horseback through ruined forts."
        ),
        steam_short_description="Open-world fantasy adventure.",
    )

    corpus, sources = build_taxonomy_v2_text_corpus(game)

    assert corpus is not None
    assert "Explore a vast open world kingdom" in corpus
    assert "A short generic blurb" in corpus
    assert "Digital Deluxe Edition" not in corpus
    assert sources == ["steam_detailed", "opencritic"]




def test_refresh_game_taxonomy_v2_text_persists_corpus_on_game():
    game = Game(
        id=12,
        title="Refresh Text",
        steam_detailed_description="Explore a vast open world kingdom and ride horseback across the frontier.",
    )

    corpus, sources = refresh_game_taxonomy_v2_text(game)

    assert game.taxonomy_v2_text_corpus == corpus
    assert game.taxonomy_v2_text_sources == sources
    assert game.taxonomy_v2_text_synced_at is not None


def test_build_game_taxonomy_v2_infers_hard_exclusions_for_fps_horror_profiles():
    game = Game(id=2, title="Horror Shooter")
    rows = [
        GameSourceTaxonomyLabel(
            game_id=2,
            source="steam",
            facet="theme",
            raw_label="Survival Horror",
            normalized_label="survival horror",
        ),
        GameSourceTaxonomyLabel(
            game_id=2,
            source="steam",
            facet="theme",
            raw_label="First-Person Shooter",
            normalized_label="first person shooter",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert "fps_only" in result.hard_exclusions
    assert "pure_survival_horror" in result.hard_exclusions


def test_extract_v2_evidence_from_source_labels_uses_steam_parity_crosswalk():
    rows = [
        GameSourceTaxonomyLabel(
            game_id=4,
            source="metacritic",
            facet="genre",
            raw_label="2D Fighting",
            normalized_label="2d fighting",
        )
    ]

    evidence = extract_v2_evidence_from_source_labels(rows)
    pairs = {(record.field, record.value) for record in evidence}

    assert ("combat_structure", "duel_focused") in pairs
    assert ("mode_profile", "pvp") in pairs
    assert ("perspective", "side_scrolling") in pairs


def test_build_game_taxonomy_v2_assigns_realistic_racer_from_auto_racing_sim_labels():
    game = Game(id=5, title="Street Racer")
    rows = [
        GameSourceTaxonomyLabel(
            game_id=5,
            source="metacritic",
            facet="genre",
            raw_label="Auto Racing Sim",
            normalized_label="auto racing sim",
        ),
        GameSourceTaxonomyLabel(
            game_id=5,
            source="steam",
            facet="tag",
            raw_label="Singleplayer",
            normalized_label="singleplayer",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_family == "sports_racing"
    assert result.primary_archetype == "realistic_racer"
    assert "driving" in result.fingerprint["traversal_verbs"]
    assert "sim_realism" in result.fingerprint["challenge_model"]
    assert "single_player" in result.fingerprint["mode_profile"]


def test_build_game_taxonomy_v2_drops_open_world_when_it_only_comes_from_steam_tag():
    game = Game(id=55, title="Tag-Only Open World")
    rows = [
        GameSourceTaxonomyLabel(
            game_id=55,
            source="steam",
            facet="tag",
            raw_label="Open World",
            normalized_label="open world",
        ),
        GameSourceTaxonomyLabel(
            game_id=55,
            source="steam",
            facet="tag",
            raw_label="Exploration",
            normalized_label="exploration",
        ),
        GameSourceTaxonomyLabel(
            game_id=55,
            source="steam",
            facet="tag",
            raw_label="Souls-like",
            normalized_label="souls like",
        ),
        GameSourceTaxonomyLabel(
            game_id=55,
            source="steam",
            facet="tag",
            raw_label="Dark Fantasy",
            normalized_label="dark fantasy",
        ),
        GameSourceTaxonomyLabel(
            game_id=55,
            source="steam",
            facet="tag",
            raw_label="Third Person",
            normalized_label="third person",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert "open_world" not in result.fingerprint["world_topology"]


def test_build_game_taxonomy_v2_does_not_overfire_loot_action_rpg_on_generic_labels():
    game = Game(id=6, title="Generic Action RPG")
    rows = [
        GameSourceTaxonomyLabel(
            game_id=6,
            source="steam",
            facet="genre",
            raw_label="Action",
            normalized_label="action",
        ),
        GameSourceTaxonomyLabel(
            game_id=6,
            source="steam",
            facet="genre",
            raw_label="RPG",
            normalized_label="rpg",
        ),
        GameSourceTaxonomyLabel(
            game_id=6,
            source="steam",
            facet="tag",
            raw_label="Singleplayer",
            normalized_label="singleplayer",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.primary_archetype != "loot_action_rpg"
    assert result.status == TAXONOMY_V2_STATUS_HIDDEN


def test_build_game_taxonomy_v2_uses_source_specific_text_corpus_when_description_missing():
    game = Game(
        id=13,
        title="Text Corpus Only",
        steam_detailed_description=(
            "Explore a vast open world fantasy kingdom. Ride horseback, climb cliffs, "
            "and embark on story quests while you customize your build."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(
            game_id=13,
            source="steam",
            facet="theme",
            raw_label="Action RPG",
            normalized_label="action rpg",
        ),
        GameSourceTaxonomyLabel(
            game_id=13,
            source="steam",
            facet="tag",
            raw_label="Third Person",
            normalized_label="third person",
        ),
        GameSourceTaxonomyLabel(
            game_id=13,
            source="steam",
            facet="tag",
            raw_label="Singleplayer",
            normalized_label="singleplayer",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "open_world_fantasy_action_rpg"
    assert result.debug_payload["text_sources"] == ["steam_detailed"]


def test_build_game_taxonomy_v2_assigns_hidden_with_provider_gap_audit_state():
    game = Game(
        id=14,
        title="Provider Gap Anchor",
    )
    rows = [
        GameSourceTaxonomyLabel(
            game_id=14,
            source="opencritic",
            facet="theme",
            raw_label="6699556a534cfd6134a078d8",
            normalized_label="6699556a534cfd6134a078d8",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_HIDDEN
    assert result.primary_archetype is None
    assert result.debug_payload["audit_state"] == "provider_gap"


def test_analyze_taxonomy_v2_label_reports_resolved_tokens_and_emitted_signals():
    analysis = analyze_taxonomy_v2_label(
        source="metacritic",
        facet="genre",
        raw_label="Auto Racing Sim",
    )

    assert analysis.mapped is True
    assert "automobile_sim" in analysis.resolved_tokens
    assert "racing" in analysis.resolved_tokens
    assert "traversal_verbs=driving" in analysis.emitted_signals
    assert "challenge_model=sim_realism" in analysis.emitted_signals


def test_analyze_taxonomy_v2_label_marks_store_feature_labels_as_suppressed():
    analysis = analyze_taxonomy_v2_label(
        source="steam",
        facet="category",
        raw_label="Steam Achievements",
    )

    assert analysis.suppressed is True
    assert analysis.suppression_reason is not None
    assert analysis.mapped is False
    assert analysis.emitted_signals == ()


def test_analyze_taxonomy_v2_label_suppresses_platform_labels_via_wildcard_source_rules():
    analysis = analyze_taxonomy_v2_label(
        source="metacritic",
        facet="platform",
        raw_label="PC",
    )

    assert analysis.classification == "suppressed"
    assert analysis.mapped is False


def test_analyze_taxonomy_v2_label_marks_soft_identity_labels_as_ignored():
    analysis = analyze_taxonomy_v2_label(
        source="steam",
        facet="tag",
        raw_label="Female Protagonist",
    )

    assert analysis.classification == "ignored"
    assert analysis.mapped is False
    assert analysis.suppressed is False


def test_analyze_taxonomy_v2_label_marks_unresolved_opencritic_theme_as_provider_gap():
    analysis = analyze_taxonomy_v2_label(
        source="opencritic",
        facet="theme",
        raw_label="6699556a534cfd6134a078d8",
    )

    assert analysis.classification == "provider_gap"
    assert analysis.mapped is False


def test_extract_v2_evidence_from_description_detects_card_battler_mechanics_and_goals():
    evidence = extract_v2_evidence_from_description(
        "Build your deck, draft cards, and deploy combos to outplay rivals in tactical battles."
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("keyword_layer", "deckbuilding") in pairs
    assert ("mechanics_structure", "deck_construction") in pairs
    assert ("rules_goals", "card_play") in pairs


def test_analyze_taxonomy_v2_label_maps_choose_your_own_adventure_to_branching_signals():
    analysis = analyze_taxonomy_v2_label(
        source="steam",
        facet="tag",
        raw_label="Choose Your Own Adventure",
    )

    assert analysis.mapped is True
    assert "narrative_structure=authored_branching" in analysis.emitted_signals
    assert "entity_interaction=dialogue_choice" in analysis.emitted_signals


def test_detect_taxonomy_v2_boilerplate_segments_flags_deluxe_and_preorder_copy():
    hits = detect_taxonomy_v2_boilerplate_segments(
        (
            "The Digital Deluxe Edition includes the full game, digital artbook, and soundtrack. "
            "Pre-order now to receive bonus outfits. "
            "Explore a vast open world kingdom and embark on story quests."
        )
    )

    categories = {hit.category for hit in hits}
    assert "edition_marketing" in categories
    assert "preorder_bonus" in categories


def test_strip_taxonomy_v2_noise_segments_removes_boilerplate_and_low_signal_copy():
    cleaned = strip_taxonomy_v2_noise_segments(
        (
            "About the game. "
            "The Digital Deluxe Edition includes the full game, soundtrack, and artbook. "
            "Explore a vast open world fantasy kingdom, ride horseback, and embark on story quests."
        )
    )

    assert cleaned is not None
    assert "About the game" not in cleaned
    assert "Digital Deluxe Edition" not in cleaned
    assert "open world fantasy kingdom" in cleaned


def test_strip_taxonomy_v2_noise_segments_discards_bonus_item_preamble_before_about_the_game():
    cleaned = strip_taxonomy_v2_noise_segments(
        (
            "COMPARE EDITIONS. Deluxe Edition includes the full base game. "
            "Cosimo Horse and Accessories. Carozella Nero Race Car. Bonus materials. Original Score. "
            "About the Game Uncover the origins of organized crime in Sicily and fight to survive."
        )
    )

    assert cleaned is not None
    assert "Cosimo Horse and Accessories" not in cleaned
    assert "Carozella Nero Race Car" not in cleaned
    assert "Original Score" not in cleaned
    assert "Uncover the origins of organized crime in Sicily" in cleaned


def test_extract_taxonomy_v2_text_phrases_skips_boilerplate_segments_by_default():
    phrases = extract_taxonomy_v2_text_phrases(
        (
            "The Digital Deluxe Edition includes the full game, digital artbook, and soundtrack. "
            "Explore a vast open world fantasy kingdom and embark on story quests."
        ),
        ngram=3,
    )

    assert "open world fantasy" in phrases
    assert "digital deluxe edition" not in phrases


def test_extract_taxonomy_v2_text_phrases_skips_low_signal_segments_by_default():
    phrases = extract_taxonomy_v2_text_phrases(
        (
            "About the game. "
            "Along the way, everything is up to you. "
            "Explore a vast open world fantasy kingdom and embark on story quests."
        ),
        ngram=3,
    )

    assert "open world fantasy" in phrases
    assert "about the game" not in phrases
    assert "along the way" not in phrases


def test_extract_v2_evidence_from_source_labels_ignores_platform_rows_and_maps_story_rich():
    rows = [
        GameSourceTaxonomyLabel(
            game_id=14,
            source="opencritic",
            facet="platform",
            raw_label="PC",
            normalized_label="pc",
        ),
        GameSourceTaxonomyLabel(
            game_id=14,
            source="steam",
            facet="tag",
            raw_label="Story Rich",
            normalized_label="story rich",
        ),
    ]

    evidence = extract_v2_evidence_from_source_labels(rows)
    pairs = {(record.field, record.value) for record in evidence}

    assert ("session_shape", "campaign") in pairs
    assert ("narrative_structure", "authored_linear") in pairs
    assert all(record.source_field != "platform" for record in evidence)


def test_extract_v2_evidence_from_source_labels_maps_keyword_interface_and_art_style_axes():
    rows = [
        GameSourceTaxonomyLabel(
            game_id=26,
            source="steam",
            facet="tag",
            raw_label="Point-and-Click",
            normalized_label="point-and-click",
        ),
        GameSourceTaxonomyLabel(
            game_id=26,
            source="steam",
            facet="tag",
            raw_label="Pixel Graphics",
            normalized_label="pixel graphics",
        ),
    ]

    evidence = extract_v2_evidence_from_source_labels(rows)
    pairs = {(record.field, record.value) for record in evidence}

    assert ("keyword_layer", "point_and_click") in pairs
    assert ("interface_control", "cursor_driven") in pairs
    assert ("mechanics_structure", "environmental_puzzle_solving") in pairs
    assert ("art_style", "pixel_art") in pairs


def test_build_game_taxonomy_v2_extracts_survival_crafting_coop_sandbox_signals():
    game = Game(
        id=2601,
        title="Realmwalker Survival",
        description=(
            "Nightingale is a PVE open-world survival crafting game played solo or cooperatively with friends. "
            "Build, craft, fight and explore as you venture through mystical portals into a variety of fantastical realms."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(
            game_id=2601,
            source="steam",
            facet="genre",
            raw_label="Action RPG",
            normalized_label="action rpg",
        ),
        GameSourceTaxonomyLabel(
            game_id=2601,
            source="steam",
            facet="perspective",
            raw_label="Third Person",
            normalized_label="third person",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert "systemic_sandbox" in result.fingerprint["world_density"]
    assert "sandbox_loop" in result.fingerprint["session_shape"]
    assert "drop_in_coop" in result.fingerprint["mode_profile"]


def test_rank_taxonomy_v2_near_misses_reports_missing_axes_for_open_world_rpg():
    fingerprint = {
        "world_topology": ["open_world"],
        "world_density": ["handcrafted_discovery"],
        "combat_presence": ["dominant"],
        "traversal_verbs": ["gliding"],
        "mode_profile": ["single_player"],
        "hard_exclusions": [],
        "soft_penalties": [],
    }

    near_misses = rank_taxonomy_v2_near_misses(fingerprint, limit=3)

    assert near_misses
    assert near_misses[0].archetype == "open_world_action_adventure"
    assert "perspective" in near_misses[0].missing_required_axes
    assert "progression_model" in near_misses[0].missing_required_axes


def test_apply_taxonomy_v2_result_to_game_updates_game_fields():
    game = Game(id=3, title="Apply Result")
    result = build_game_taxonomy_v2(
        Game(
            id=3,
            title="Apply Result",
            description=(
                "Explore a vast open world fantasy kingdom. Ride horseback and embark on quests "
                "while you customize your build."
            ),
        ),
        [
            GameSourceTaxonomyLabel(
                game_id=3,
                source="steam",
                facet="theme",
                raw_label="Action RPG",
                normalized_label="action rpg",
            ),
            GameSourceTaxonomyLabel(
                game_id=3,
                source="steam",
                facet="perspective",
                raw_label="Third Person",
                normalized_label="third person",
            ),
        ],
    )

    apply_taxonomy_v2_result_to_game(game, result)

    assert game.taxonomy_v2_version == result.version
    assert game.taxonomy_v2_primary_archetype == result.primary_archetype
    assert game.taxonomy_v2_secondary_archetypes == result.secondary_archetypes
    assert game.taxonomy_v2_hard_exclusions == result.hard_exclusions
    assert game.taxonomy_v2_fingerprint == result.fingerprint
    assert game.taxonomy_v2_confidence == Decimal(str(result.confidence)).quantize(Decimal("0.01"))
    assert game.taxonomy_v2_computed_at is not None


def test_build_game_taxonomy_v2_debug_payload_includes_signal_tiers():
    game = Game(
        id=27,
        title="Signal Tier Test",
        steam_detailed_description="A point-and-click mystery where you solve the mystery and search for clues.",
    )
    rows = [
        GameSourceTaxonomyLabel(
            game_id=27,
            source="steam",
            facet="tag",
            raw_label="Point-and-Click",
            normalized_label="point-and-click",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    tiers = result.debug_payload["signal_tiers"]
    assert tiers["keyword_layer"]["point_and_click"] == "identity_driving"
    assert tiers["interface_control"]["cursor_driven"] == "supporting"
