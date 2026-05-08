from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Text

from app.models.models import Game, GameSourceTaxonomyLabel
from app.services.game_taxonomy_v2 import (
    FINGERPRINT_AXES,
    TAXONOMY_V2_STATUS_COMPUTED,
    TAXONOMY_V2_STATUS_HIDDEN,
    ArchetypeCandidate,
    _prefer_primary_archetype_candidate,
    _title_parent_edition_keys,
    analyze_taxonomy_v2_label,
    assign_taxonomy_v2_archetypes,
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


def test_extract_v2_evidence_from_description_detects_explicit_metroidvania_language():
    evidence = extract_v2_evidence_from_description(
        (
            "Take to the sky and reunite a fragmented world in this surprisingly wholesome metroidvania. "
            "Adventure across beautiful islands, uncover secrets, and unlock new abilities as you backtrack through an interconnected world."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("world_topology", "semi_open") in pairs
    assert ("world_density", "handcrafted_discovery") in pairs
    assert ("traversal_verbs", "platforming") in pairs
    assert ("progression_model", "metaprogression") in pairs


def test_build_game_taxonomy_v2_assigns_dice_deckbuilding_roguelike_to_card_battler():
    game = Game(
        title="Dice A Million",
        description=(
            "A roguelike deckbuilder about rolling dice. Build a dice pool, discover powerful synergies, "
            "equip passive items, and beat bosses through tactical optimization."
        ),
    )

    result = build_game_taxonomy_v2(game, [])

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "card_battler"


def test_build_game_taxonomy_v2_assigns_mlb_baseball_text_to_sports_sim():
    game = Game(
        title="MLB The Show 25",
        description=(
            "Swing for the fences and live out your baseball dreams. Reach the big leagues, "
            "win the World Series champions title, and play authentic stadium matches."
        ),
    )

    result = build_game_taxonomy_v2(game, [])

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "sports_sim"
    assert "baseball" in result.fingerprint["sports_theme"]


def test_build_game_taxonomy_v2_assigns_retro_2d_platformer_before_beat_em_up():
    game = Game(
        title="The New Zealand Story: Untold Adventure",
        description=(
            "An official remake of the iconic 1988 platformer from TAITO. "
            "Play a colorful 2D platformer where the hero clears stages, jumps, and fights bosses."
        ),
    )

    result = build_game_taxonomy_v2(game, [])

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "action_platformer"


def test_build_game_taxonomy_v2_assigns_platform_fighter_identity():
    game = Game(
        title="Royal Vermin",
        description=(
            "A chaotic local platform fighter for 2 to 4 players. Knock your opponents out of the level "
            "in fast PvP arena matches with simple controls and evolving stages."
        ),
    )

    result = build_game_taxonomy_v2(game, [])

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "traditional_fighter"
    assert "platforming" in result.fingerprint["traversal_verbs"]


def test_extract_v2_evidence_from_description_detects_compact_metroidvania_exploration_language():
    evidence = extract_v2_evidence_from_description(
        (
            "An interstellar drifter embarks on a mission of exploration across a small cluster of four planets. "
            "Collect special powers, squeeze through tight passages, and defeat menacing bosses."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("world_topology", "semi_open") in pairs
    assert ("progression_model", "metaprogression") in pairs
    assert ("combat_structure", "boss_centric") in pairs
    assert ("traversal_verbs", "platforming") in pairs


def test_extract_v2_evidence_from_description_detects_farm_inheritance_cozy_life_language():
    evidence = extract_v2_evidence_from_description(
        (
            "You've inherited your grandfather's old farm plot. Armed with hand-me-down tools, you set out to begin your new life, "
            "raise animals, and help rebuild the community while you fish and harvest your own crops."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("session_shape", "sandbox_loop") in pairs
    assert ("progression_model", "base_growth") in pairs
    assert ("progression_model", "relationship_social") in pairs
    assert ("tone", "cozy") in pairs


def test_extract_v2_evidence_from_description_detects_psychological_horror_dual_reality_language():
    evidence = extract_v2_evidence_from_description(
        (
            "A third-person psychological horror game where you explore both the real world and the spirit realm. "
            "Drawn to a deserted resort, you'll uncover dark secrets and survive the horrors that haunt it."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("setting", "horror") in pairs
    assert ("tone", "bleak") in pairs
    assert ("perspective", "third_person") in pairs
    assert ("world_topology", "level_based") in pairs
    assert ("combat_presence", "none") in pairs


def test_extract_v2_evidence_from_description_detects_detective_vn_clue_hunting_language():
    evidence = extract_v2_evidence_from_description(
        (
            "Interrogate suspects and hunt for clues to piece together chilling conundrums "
            "plaguing a high school in Japan."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("combat_presence", "none") in pairs
    assert ("interface_control", "cursor_driven") in pairs
    assert ("challenge_model", "puzzle_gating") in pairs
    assert ("rules_goals", "solve_mysteries") in pairs
    assert ("narrative_topic", "detective_mystery") in pairs


def test_extract_v2_evidence_from_description_detects_kingdom_decision_sim_language():
    evidence = extract_v2_evidence_from_description(
        (
            "Sit on the throne as a benevolent monarch and swipe your royal controller either left or right "
            "to impose your will upon the kingdom. Survive the gauntlet of requests from your advisors."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("combat_presence", "none") in pairs
    assert ("session_shape", "campaign") in pairs
    assert ("narrative_structure", "authored_branching") in pairs
    assert ("interface_control", "cursor_driven") in pairs
    assert ("entity_interaction", "dialogue_choice") in pairs
    assert ("progression_model", "base_growth") in pairs
    assert ("rules_goals", "build_and_optimize") in pairs


def test_extract_v2_evidence_from_description_detects_kingdom_decision_sim_series_tagline_language():
    evidence = extract_v2_evidence_from_description(
        (
            "Reigns: Her Majesty is the revolutionary follow-up to the smash swipe 'em up hit Reigns. "
            "Claim the Iron Throne and face branching consequences across your reign."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("combat_presence", "none") in pairs
    assert ("narrative_structure", "authored_branching") in pairs
    assert ("interface_control", "cursor_driven") in pairs
    assert ("progression_model", "base_growth") in pairs


def test_extract_v2_evidence_from_description_detects_organization_puzzle_language():
    evidence = extract_v2_evidence_from_description(
        (
            "Wilmot's Warehouse is a puzzle game about keeping a warehouse running in tip-top shape. "
            "Just remember where you put everything, organize the stock, and fit items before the service hatch opens."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("challenge_model", "puzzle_gating") in pairs
    assert ("combat_presence", "none") in pairs
    assert ("mechanics_structure", "environmental_puzzle_solving") in pairs
    assert ("mechanics_structure", "systemic_problem_solving") in pairs


def test_extract_v2_evidence_from_description_detects_packing_order_organization_language():
    evidence = extract_v2_evidence_from_description(
        (
            "A cozy puzzle-simulation game where you play a warehouse worker with a knack for perfectly organizing "
            "and packing orders."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("challenge_model", "puzzle_gating") in pairs
    assert ("mechanics_structure", "systemic_problem_solving") in pairs
    assert ("rules_goals", "build_and_optimize") in pairs


def test_extract_v2_evidence_from_description_detects_unpacking_home_organization_language():
    evidence = extract_v2_evidence_from_description(
        (
            "A zen puzzle game about pulling possessions out of boxes and fitting them into a new home. "
            "Part block-fitting puzzle, part home decoration."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("challenge_model", "puzzle_gating") in pairs
    assert ("mechanics_structure", "environmental_puzzle_solving") in pairs
    assert ("mechanics_structure", "systemic_problem_solving") in pairs
    assert ("rules_goals", "build_and_optimize") in pairs
    assert ("entity_interaction", "inventory_loot") in pairs


def test_extract_v2_evidence_from_description_detects_parkour_platforming_time_trial_language():
    evidence = extract_v2_evidence_from_description(
        (
            "A VR platforming game that gives you the freedom to move across the environment with superhuman abilities. "
            "Conquer dozens of levels, chase fastest times, and master your parkour routes."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("world_topology", "level_based") in pairs
    assert ("traversal_verbs", "parkour") in pairs
    assert ("traversal_verbs", "platforming") in pairs
    assert ("perspective", "first_person") in pairs
    assert ("combat_presence", "none") in pairs


def test_extract_v2_evidence_from_description_detects_first_person_platformer_language():
    evidence = extract_v2_evidence_from_description(
        (
            "The world's only competitive heavy metal first-person platformer focused on speed and fast reactions. "
            "Race and blast your way through deadly arenas."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("perspective", "first_person") in pairs
    assert ("traversal_verbs", "parkour") in pairs
    assert ("traversal_verbs", "platforming") in pairs
    assert ("world_topology", "level_based") in pairs


def test_extract_v2_evidence_from_description_detects_first_person_free_runner_language():
    evidence = extract_v2_evidence_from_description(
        (
            "Follow Faith, a daring free runner, through fluid first-person action as she fights for freedom. "
            "Explore every corner of the city."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("perspective", "first_person") in pairs
    assert ("traversal_verbs", "parkour") in pairs
    assert ("traversal_verbs", "platforming") in pairs
    assert ("world_topology", "open_world") in pairs


def test_build_game_taxonomy_v2_prefers_3d_collectathon_for_first_person_parkour_runner_profile():
    game = Game(
        id=24670,
        title="City Runner",
        steam_short_description=(
            "A daring free runner races across the skyline through fluid first-person action. "
            "Explore every corner of the city and keep your momentum."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24670, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=24670, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=24670, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "3d_collectathon"
    assert "first_person" in result.fingerprint["perspective"]
    assert "parkour" in result.fingerprint["traversal_verbs"]


def test_build_game_taxonomy_v2_assigns_cozy_exploration_for_open_world_movement_adventure():
    game = Game(
        title="Lil Gator Style Adventure",
        description=(
            "There's a buddy atop every hill in this open-world, movement-focused adventure. "
            "Bop cardboard baddies, brave serene hills and forests, and scale sheer rocks. "
            "Embark on an adorable adventure, discover new friends, and uncover everything the island has to offer."
        ),
        steam_short_description=(
            "Climb, Swim, Glide and slide your way into the hearts of the many different characters "
            "you meet on your travels!"
        ),
    )

    result = build_game_taxonomy_v2(game, [])

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "cozy_exploration_adventure"
    assert "cozy" in result.fingerprint["tone"]
    assert "platforming" in result.fingerprint["traversal_verbs"]


def test_build_game_taxonomy_v2_assigns_cozy_exploration_for_nature_hiking_adventure():
    game = Game(
        title="Peaceful Mountain Hike",
        description=(
            "Hike, climb, and soar through the peaceful mountainside landscapes of Hawk Peak Provincial Park. "
            "Follow the marked trails or explore the backcountry as you make your way to the summit. "
            "Along the way, meet other hikers and discover hidden treasures."
        ),
    )

    result = build_game_taxonomy_v2(game, [])

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "cozy_exploration_adventure"
    assert "climbing" in result.fingerprint["traversal_verbs"]


def test_build_game_taxonomy_v2_assigns_cozy_exploration_for_wildlife_island_adventure():
    game = Game(
        title="Wildlife Island",
        description=(
            "Join Alba on a Mediterranean island for a peaceful summer of wildlife exploration. "
            "Set out to save her beautiful island and its wildlife while meeting people across the island."
        ),
    )

    result = build_game_taxonomy_v2(game, [])

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "cozy_exploration_adventure"
    assert "cozy" in result.fingerprint["tone"]
    assert "platforming" not in result.fingerprint.get("traversal_verbs", [])


def test_title_parent_edition_keys_extracts_exact_goty_parent_titles():
    assert _title_parent_edition_keys("Lil Gator Game: Gator of the Year") == ["lil gator game"]
    assert _title_parent_edition_keys("Example Game Game of the Year Edition") == ["example game"]


def test_build_game_taxonomy_v2_assigns_action_platformer_from_retro_2d_action_language():
    game = Game(
        id=24671,
        title="Retro Moon",
        steam_short_description=(
            "Retro sword-and-whip action returns with classic 2D action and a dark, 8-bit aesthetic."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24671, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=24671, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "action_platformer"
    assert "side_scrolling" in result.fingerprint["perspective"]
    assert "platforming" in result.fingerprint["traversal_verbs"]
    assert "retro" in result.fingerprint["art_style"]


def test_build_game_taxonomy_v2_strips_crafting_noise_from_retro_horror_platformer_profile():
    game = Game(
        id=24672,
        title="Hell Knight",
        steam_short_description=(
            "A heavy metal inspired arcade combat adventure set in a Gothic world full of cursed realms, "
            "gore galore, and pixel art foes."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24672, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=24672, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "action_platformer"
    assert "buildcraft" not in result.fingerprint["progression_model"]
    assert "systemic_sandbox" not in result.fingerprint["world_density"]
    assert "retro" in result.fingerprint["art_style"]
    assert "horror" in result.fingerprint["setting"]


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


def test_extract_v2_evidence_from_description_detects_baseball_match_signals():
    evidence = extract_v2_evidence_from_description(
        (
            "A baseball game with pick-up games, batting practice, lineup selection, "
            "and arcade-style baseball power-ups."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("sports_theme", "baseball") in pairs
    assert ("session_shape", "match_session") in pairs
    assert ("mechanics_structure", "match_competition") in pairs
    assert ("rules_goals", "win_matches") in pairs


def test_prefer_primary_archetype_candidate_prefers_first_person_western_narrative_rpg():
    fingerprint = {field: [] for field in FINGERPRINT_AXES}
    fingerprint["session_shape"] = ["campaign"]
    fingerprint["perspective"] = ["first_person"]
    fingerprint["progression_model"] = ["quest_driven"]
    fingerprint["narrative_structure"] = ["authored_branching", "quest_web"]
    fingerprint["entity_interaction"] = ["dialogue_choice", "inventory_loot"]
    fingerprint["combat_style"] = ["stealth", "shooter"]
    fingerprint["combat_structure"] = ["systemic_emergent", "encounter_driven"]
    fingerprint["world_topology"] = ["semi_open", "open_world"]
    fingerprint["setting"] = ["sci_fi"]
    fingerprint["rules_goals"] = ["complete_quests"]

    confidence_by_field_value = {
        field: {value: 0.95 for value in values}
        for field, values in fingerprint.items()
        if values
    }
    candidates = assign_taxonomy_v2_archetypes(fingerprint, confidence_by_field_value)

    assert {candidate.archetype for candidate in candidates} >= {
        "western_narrative_rpg",
        "stealth_action_adventure",
    }

    preferred = _prefer_primary_archetype_candidate(candidates, fingerprint)

    assert preferred[0].archetype == "western_narrative_rpg"


def test_prefer_primary_archetype_candidate_prefers_sports_sim_over_party_game_without_party_coop():
    fingerprint = {field: [] for field in FINGERPRINT_AXES}
    fingerprint["session_shape"] = ["match_session"]
    fingerprint["mode_profile"] = ["single_player", "pvp"]
    fingerprint["mechanics_structure"] = ["match_competition"]
    fingerprint["rules_goals"] = ["win_matches"]
    fingerprint["tone"] = ["comedic"]
    fingerprint["input_complexity"] = ["casual"]

    confidence_by_field_value = {
        field: {value: 0.95 for value in values}
        for field, values in fingerprint.items()
        if values
    }
    candidates = assign_taxonomy_v2_archetypes(fingerprint, confidence_by_field_value)

    assert {candidate.archetype for candidate in candidates} >= {
        "sports_sim",
        "party_game",
    }

    preferred = _prefer_primary_archetype_candidate(candidates, fingerprint)

    assert preferred[0].archetype == "sports_sim"


def test_prefer_primary_archetype_candidate_prefers_rhythm_game_over_sports_sim_for_timing_profiles():
    fingerprint = {field: [] for field in FINGERPRINT_AXES}
    fingerprint["session_shape"] = ["match_session"]
    fingerprint["mode_profile"] = ["single_player", "pvp"]
    fingerprint["mechanics_structure"] = ["rhythm_timing"]
    fingerprint["rules_goals"] = ["hit_beats"]
    fingerprint["interface_control"] = ["timing_input"]
    fingerprint["keyword_layer"] = ["rhythm"]
    fingerprint["input_complexity"] = ["moderate"]

    confidence_by_field_value = {
        field: {value: 0.95 for value in values}
        for field, values in fingerprint.items()
        if values
    }
    candidates = assign_taxonomy_v2_archetypes(fingerprint, confidence_by_field_value)

    assert {candidate.archetype for candidate in candidates} >= {
        "sports_sim",
        "rhythm_game",
    }

    preferred = _prefer_primary_archetype_candidate(candidates, fingerprint)

    assert preferred[0].archetype == "rhythm_game"


def test_prefer_primary_archetype_candidate_prefers_survival_horror_for_stealth_puzzle_evasion_profiles():
    fingerprint = {field: [] for field in FINGERPRINT_AXES}
    fingerprint["world_topology"] = ["linear"]
    fingerprint["world_density"] = ["handcrafted_discovery", "setpiece_driven"]
    fingerprint["session_shape"] = ["campaign"]
    fingerprint["perspective"] = ["first_person"]
    fingerprint["pacing"] = ["long_form_campaign"]
    fingerprint["combat_presence"] = ["light"]
    fingerprint["combat_style"] = ["stealth", "survival"]
    fingerprint["combat_structure"] = ["encounter_driven"]
    fingerprint["progression_model"] = ["quest_driven"]
    fingerprint["challenge_model"] = ["puzzle_gating"]
    fingerprint["narrative_structure"] = ["authored_linear"]
    fingerprint["narrative_topic"] = ["detective_mystery", "survival_escape"]
    fingerprint["mechanics_structure"] = ["environmental_puzzle_solving", "stealth_infiltration"]
    fingerprint["rules_goals"] = ["complete_quests", "infiltrate_avoid_detection", "solve_mysteries"]
    fingerprint["setting"] = ["horror", "modern"]
    fingerprint["tone"] = ["bleak", "serious"]
    fingerprint["mode_profile"] = ["single_player"]

    confidence_by_field_value = {
        field: {value: 0.95 for value in values}
        for field, values in fingerprint.items()
        if values
    }
    candidates = assign_taxonomy_v2_archetypes(fingerprint, confidence_by_field_value)

    assert {candidate.archetype for candidate in candidates} >= {
        "survival_horror",
        "psychological_horror",
    }

    preferred = _prefer_primary_archetype_candidate(candidates, fingerprint)

    assert preferred[0].archetype == "survival_horror"


def test_prefer_primary_archetype_candidate_prefers_life_sim_over_farming_sim_for_relationship_drama_profiles():
    fingerprint = {field: [] for field in FINGERPRINT_AXES}
    fingerprint["world_topology"] = ["hub_and_spoke"]
    fingerprint["world_density"] = ["sandbox_light"]
    fingerprint["session_shape"] = ["campaign", "sandbox_loop"]
    fingerprint["perspective"] = ["fixed_camera"]
    fingerprint["art_style"] = ["anime", "stylized"]
    fingerprint["interface_control"] = ["cursor_driven"]
    fingerprint["combat_presence"] = ["none"]
    fingerprint["progression_model"] = ["relationship_social"]
    fingerprint["narrative_structure"] = ["authored_branching"]
    fingerprint["narrative_topic"] = ["interpersonal_drama"]
    fingerprint["entity_interaction"] = ["cursor_driven_interaction", "dialogue_choice"]
    fingerprint["tone"] = ["cozy", "whimsical"]
    fingerprint["mode_profile"] = ["single_player"]
    fingerprint["content_model"] = ["premium_replayable"]
    fingerprint["input_complexity"] = ["casual"]

    confidence_by_field_value = {
        field: {value: 0.95 for value in values}
        for field, values in fingerprint.items()
        if values
    }
    candidates = assign_taxonomy_v2_archetypes(fingerprint, confidence_by_field_value)

    assert {candidate.archetype for candidate in candidates} >= {
        "life_sim",
        "farming_sim",
    }

    preferred = _prefer_primary_archetype_candidate(candidates, fingerprint)

    assert preferred[0].archetype == "life_sim"


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


def test_build_game_taxonomy_v2_assigns_cinematic_action_adventure_from_historical_knight_profile():
    game = Game(
        id=1741,
        title="Medieval Knight Adventure",
        steam_short_description=(
            "Journey through a tumultuous Medieval Italy as a young knight errant on a brutal quest. "
            "A cinematic action-adventure inspired by chivalric tales and the late medieval period."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=1741, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=1741, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=1741, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "cinematic_action_adventure"
    assert "historical" in result.fingerprint["setting"]
    assert "historical_first" in result.hard_exclusions


def test_build_game_taxonomy_v2_assigns_cinematic_action_adventure_from_roman_soldier_profile():
    game = Game(
        id=1742,
        title="Roman Soldier Adventure",
        steam_short_description=(
            "Fight as a soldier. Lead as a general. A young Roman soldier travels with the Roman army to Britannia "
            "during the late Roman Empire to seek revenge."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=1742, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=1742, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "cinematic_action_adventure"
    assert "historical" in result.fingerprint["setting"]
    assert "authored_linear" in result.fingerprint["narrative_structure"]


def test_build_game_taxonomy_v2_assigns_cinematic_action_adventure_from_plague_history_profile():
    game = Game(
        id=1743,
        title="Plague History Adventure",
        steam_short_description=(
            "Follow the grim tale of a sister and her little brother in a heartrending journey through the darkest hours of history. "
            "Hunted by Inquisition soldiers, the adventure blends action, adventure and stealth phases."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=1743, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=1743, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=1743, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "cinematic_action_adventure"
    assert "historical" in result.fingerprint["setting"]
    assert "bleak" in result.fingerprint["tone"]


def test_build_game_taxonomy_v2_assigns_cinematic_action_adventure_from_viking_myth_profile():
    game = Game(
        id=1744,
        title="Viking Myth Adventure",
        steam_short_description=(
            "A warrior's brutal journey into myth and madness. Set in the Viking age, "
            "a Celtic warrior embarks on a haunting vision quest through a nightmarish realm."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=1744, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=1744, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=1744, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "cinematic_action_adventure"
    assert "mythic" in result.fingerprint["setting"]
    assert "bleak" in result.fingerprint["tone"]


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


def test_extract_v2_evidence_from_description_detects_word_puzzle_strategy_signals():
    evidence = extract_v2_evidence_from_description(
        (
            "A roguelike strategy and word-crafting game where every letter matters. "
            "Build word combos, adapt to shifting rules, tackle time-attack boards, "
            "and push deeper through seeded runs."
        )
    )

    pairs = {(record.field, record.value) for record in evidence}

    assert ("world_topology", "run_based") in pairs
    assert ("session_shape", "roguelite_run") in pairs
    assert ("challenge_model", "puzzle_gating") in pairs
    assert ("challenge_model", "tactical_optimization") in pairs
    assert ("mechanics_structure", "score_attack") in pairs


def test_build_game_taxonomy_v2_assigns_word_puzzle_strategy_from_word_roguelite_text():
    game = Game(
        id=241,
        title="Beyond Words",
        steam_detailed_description=(
            "A roguelike strategy and word-crafting game where every letter matters. "
            "Build powerful word combos, unlock upgrades, adapt to shifting rules and layouts, "
            "and push through seeded runs, boss challenges, and optional time-attack boards."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=241, source="metacritic", facet="genre", raw_label="Logic Puzzle", normalized_label="logic puzzle"),
        GameSourceTaxonomyLabel(game_id=241, source="steam", facet="genre", raw_label="Strategy", normalized_label="strategy"),
        GameSourceTaxonomyLabel(game_id=241, source="steam", facet="category", raw_label="Mouse only option", normalized_label="mouse only option"),
        GameSourceTaxonomyLabel(game_id=241, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "word_puzzle_strategy"
    assert "run_based" in result.fingerprint["world_topology"]
    assert "roguelite_run" in result.fingerprint["session_shape"]
    assert "puzzle_gating" in result.fingerprint["challenge_model"]
    assert "none" in result.fingerprint["combat_presence"]


def test_build_game_taxonomy_v2_assigns_word_puzzle_strategy_from_word_game_synergy_text():
    game = Game(
        id=242,
        title="Cursed Words",
        steam_detailed_description=(
            "A word game where you write words, chain letter synergies, and adapt your run to shifting rules. "
            "Build stronger letter combos and push deeper through each run."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=242, source="steam", facet="genre", raw_label="Strategy", normalized_label="strategy"),
        GameSourceTaxonomyLabel(game_id=242, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "word_puzzle_strategy"
    assert "run_based" in result.fingerprint["world_topology"]
    assert "roguelite_run" in result.fingerprint["session_shape"]
    assert "none" in result.fingerprint["combat_presence"]


def test_build_game_taxonomy_v2_assigns_farming_sim_from_cozy_farming_text():
    game = Game(
        id=243,
        title="Collector's Cove",
        steam_detailed_description=(
            "A cozy farming adventure where you cultivate your floating farm, grow crops, catch fish, "
            "and discover peaceful islands at your own pace."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=243, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "farming_sim"
    assert "sandbox_light" in result.fingerprint["world_density"]
    assert "base_growth" in result.fingerprint["progression_model"]
    assert "cozy" in result.fingerprint["tone"]


def test_build_game_taxonomy_v2_assigns_military_fps_from_modern_shooter_package():
    game = Game(
        id=244,
        title="Call of Duty Style",
        steam_detailed_description=(
            "Fight through a co-op campaign, competitive multiplayer, and round-based zombies in a "
            "first-person shooter built around modern warfare special ops missions."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=244, source="steam", facet="genre", raw_label="Shooter", normalized_label="shooter"),
        GameSourceTaxonomyLabel(game_id=244, source="steam", facet="tag", raw_label="First-Person", normalized_label="first-person"),
        GameSourceTaxonomyLabel(game_id=244, source="steam", facet="category", raw_label="Online PvP", normalized_label="online pvp"),
        GameSourceTaxonomyLabel(game_id=244, source="steam", facet="category", raw_label="Online Co-op", normalized_label="online co-op"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "military_fps"
    assert "mission_based" in result.fingerprint["world_topology"]
    assert "military" in result.fingerprint["setting"]
    assert "twitch" in result.fingerprint["combat_tempo"]


def test_build_game_taxonomy_v2_assigns_management_tycoon_from_restaurant_management_profile():
    game = Game(
        id=2441,
        title="Pizza Business",
        steam_detailed_description=(
            "A restaurant management game where you manage your family pizzeria, fulfill pizza orders, "
            "upgrade your restaurant, design unique menus, and compete against your pizza rival."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2441, source="steam", facet="genre", raw_label="Simulation", normalized_label="simulation"),
        GameSourceTaxonomyLabel(game_id=2441, source="steam", facet="genre", raw_label="Strategy", normalized_label="strategy"),
        GameSourceTaxonomyLabel(game_id=2441, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "management_tycoon"
    assert "build_and_optimize" in result.fingerprint["rules_goals"]
    assert "systemic_sandbox" in result.fingerprint["world_density"]
    assert "restaurant_management" in result.fingerprint["keyword_layer"]


def test_build_game_taxonomy_v2_assigns_management_tycoon_from_retail_management_profile():
    game = Game(
        id=2442,
        title="Discount Market",
        steam_detailed_description=(
            "A narrative-driven management sim where you manage a discount supermarket, restock shelves, "
            "plan your shop layout, strike trade deals, and grow your local business."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2442, source="steam", facet="genre", raw_label="Simulation", normalized_label="simulation"),
        GameSourceTaxonomyLabel(game_id=2442, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "management_tycoon"
    assert "base_growth" in result.fingerprint["progression_model"]
    assert "systemic_sandbox" in result.fingerprint["world_density"]
    assert "build_and_optimize" in result.fingerprint["rules_goals"]


def test_build_game_taxonomy_v2_assigns_visual_novel_from_dating_sim_profile():
    game = Game(
        id=2443,
        title="Holiday Hearts",
        steam_short_description=(
            "A branching romance visual novel and dating sim with character routes, cursor-driven choices, "
            "and no combat."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2443, source="steam", facet="genre", raw_label="Casual", normalized_label="casual"),
        GameSourceTaxonomyLabel(game_id=2443, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "visual_novel"
    assert "none" in result.fingerprint["combat_presence"]
    assert "cursor_driven" in result.fingerprint["interface_control"]
    assert "authored_branching" in result.fingerprint["narrative_structure"]


def test_build_game_taxonomy_v2_assigns_jrpg_story_rpg_from_console_style_rpg_profile():
    game = Game(
        id=2444,
        title="Rise Style JRPG",
        steam_detailed_description=(
            "A retro-themed, console-style role playing game with a turn-based battle system and a party-based "
            "adventure across a war-torn continent."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2444, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=2444, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "jrpg_story_rpg"
    assert "campaign" in result.fingerprint["session_shape"]
    assert "tactical" in result.fingerprint["combat_tempo"]
    assert "party_management" in result.fingerprint["combat_structure"]


def test_build_game_taxonomy_v2_assigns_visual_novel_from_detective_mystery_adventure_profile():
    game = Game(
        id=2445,
        title="Murder Manor",
        steam_detailed_description=(
            "A live-action mystery-adventure where you re-examine a murder, establish a hypothesis, use logic "
            "to break through lies, and uncover new clues."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2445, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "visual_novel"
    assert "cursor_driven" in result.fingerprint["interface_control"]
    assert "detective_mystery" in result.fingerprint["narrative_topic"]
    assert "solve_mysteries" in result.fingerprint["rules_goals"]


def test_build_game_taxonomy_v2_prefers_jrpg_story_rpg_for_party_based_authored_linear_jrpg_profile():
    game = Game(
        id=24455,
        title="Floating Kingdom JRPG",
        steam_detailed_description=(
            "A 16-bit era Japanese-style RPG where a party of heroes explores a world above the clouds. "
            "Experience turn-based battles, new character classes and skills, side quests, and a story-driven campaign."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24455, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=24455, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=24455, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "jrpg_story_rpg"
    assert "party_management" in result.fingerprint["combat_structure"]
    assert "authored_linear" in result.fingerprint["narrative_structure"]
    assert "skill_tree" in result.fingerprint["progression_model"]


def test_build_game_taxonomy_v2_assigns_co_op_horror_from_horde_shooter_campaign_profile():
    game = Game(
        id=2446,
        title="Zombie Crew",
        steam_short_description=(
            "A co-op first-person shooter for four-player cooperative teams. Fight massive swarms of zombies "
            "across a narrative campaign."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2446, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2446, source="steam", facet="genre", raw_label="FPS", normalized_label="fps"),
        GameSourceTaxonomyLabel(game_id=2446, source="steam", facet="category", raw_label="Online Co-op", normalized_label="online co-op"),
        GameSourceTaxonomyLabel(game_id=2446, source="steam", facet="category", raw_label="Online PvP", normalized_label="online pvp"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "co_op_horror"
    assert "match_session" not in result.fingerprint["session_shape"]
    assert "drop_in_coop" in result.fingerprint["mode_profile"]


def test_build_game_taxonomy_v2_assigns_kingdom_decision_sim_from_reigns_style_profile():
    game = Game(
        id=2447,
        title="Royal Swipe",
        steam_detailed_description=(
            "Sit on the throne as a benevolent monarch and swipe your royal controller either left or right "
            "to impose your will upon the kingdom. Survive the gauntlet of requests from your advisors, "
            "balance the church, the people, the army and the treasury, and face branching consequences."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2447, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=2447, source="steam", facet="genre", raw_label="Simulation", normalized_label="simulation"),
        GameSourceTaxonomyLabel(game_id=2447, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "kingdom_decision_sim"
    assert "none" in result.fingerprint["combat_presence"]
    assert "cursor_driven" in result.fingerprint["interface_control"]
    assert "build_and_optimize" in result.fingerprint["rules_goals"]
    assert "dominant" not in result.fingerprint["combat_presence"]
    assert "melee" not in result.fingerprint["combat_style"]


def test_build_game_taxonomy_v2_assigns_beat_em_up_from_side_scrolling_brawler_text():
    game = Game(
        id=245,
        title="Towerborne Style",
        steam_detailed_description=(
            "A side-scrolling action RPG brawler with drop-in co-op where you smash through levels, "
            "battle monsters, and unleash combo-heavy melee attacks."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=245, source="steam", facet="category", raw_label="Online Co-op", normalized_label="online co-op"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "beat_em_up"
    assert "melee" in result.fingerprint["combat_style"]
    assert "level_based" in result.fingerprint["world_topology"]


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


def test_build_game_taxonomy_v2_assigns_rhythm_game_from_rhythm_action_text_despite_casual_tag():
    game = Game(
        id=26,
        title="GRIDbeat",
        steam_detailed_description=(
            "A rhythm-fueled cyber-dungeon crawler where every move must match the music. "
            "Hit beats, solve combat puzzles, and survive boss battles through timing-based action."
        ),
        metacritic_description=(
            "Rhythm action with timing-based encounters and boss fights."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=26, source="steam", facet="genre", raw_label="Casual", normalized_label="casual"),
        GameSourceTaxonomyLabel(game_id=26, source="metacritic", facet="genre", raw_label="Rhythm", normalized_label="rhythm"),
        GameSourceTaxonomyLabel(game_id=26, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "rhythm_game"
    assert "moderate" in result.fingerprint["input_complexity"]
    assert "match_session" in result.fingerprint["session_shape"]


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


def test_build_similarity_breakdown_v2_allows_low_combat_sports_same_lane_matches_via_session_and_theme():
    anchor = Game(
        title="WWE 2K26",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="sports_sim",
        taxonomy_v2_fingerprint={
            "session_shape": ["match_session"],
            "mode_profile": ["single_player", "pvp"],
            "sports_theme": ["wrestling"],
            "mechanics_structure": ["match_competition"],
            "rules_goals": ["win_matches"],
            "interface_control": ["timing_input"],
            "combat_presence": ["none"],
        },
    )
    candidate = Game(
        title="WWE 2K25",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="sports_sim",
        taxonomy_v2_fingerprint={
            "session_shape": ["match_session"],
            "mode_profile": ["single_player", "pvp"],
            "sports_theme": ["wrestling"],
            "mechanics_structure": ["match_competition"],
            "rules_goals": ["win_matches"],
            "interface_control": ["timing_input"],
            "combat_presence": ["none"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None
    assert breakdown.relationship == "same"
    assert breakdown.shared_session_shape == ["match_session"]
    assert breakdown.shared_mode_profile == ["pvp", "single_player"]
    assert breakdown.shared_sports_theme == ["wrestling"]


def test_build_similarity_breakdown_v2_allows_low_combat_narrative_matches_via_interface_and_story_signals():
    anchor = Game(
        title="Mystery Anchor",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="visual_novel",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "interface_control": ["cursor_driven"],
            "narrative_topic": ["mystery"],
            "visual_presentation": ["static_2d"],
            "art_style": ["anime"],
            "combat_presence": ["none"],
        },
    )
    candidate = Game(
        title="Mystery Peer",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="visual_novel",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "interface_control": ["cursor_driven"],
            "narrative_topic": ["mystery"],
            "visual_presentation": ["static_2d"],
            "art_style": ["anime"],
            "combat_presence": ["none"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None
    assert breakdown.relationship == "same"
    assert breakdown.shared_session_shape == ["campaign"]
    assert breakdown.shared_interface_control == ["cursor_driven"]
    assert breakdown.shared_narrative_topic == ["mystery"]


def test_build_similarity_breakdown_v2_allows_loot_action_rpg_same_lane_matches_via_buildcraft_bridge():
    anchor = Game(
        title="Dragonkin: The Banished",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="loot_action_rpg",
        taxonomy_v2_fingerprint={
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "combat_structure": ["crowd_control", "encounter_driven"],
            "progression_model": ["base_growth", "buildcraft", "skill_tree"],
            "rules_goals": ["build_and_optimize", "defeat_bosses"],
            "entity_interaction": ["construction_placement"],
            "mode_profile": ["drop_in_coop", "party_coop", "single_player"],
            "content_model": ["premium_replayable"],
        },
    )
    candidate = Game(
        title="Rotwood",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="loot_action_rpg",
        taxonomy_v2_fingerprint={
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "melee"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["buildcraft"],
            "rules_goals": ["defeat_bosses"],
            "mode_profile": ["drop_in_coop", "party_coop", "single_player"],
            "content_model": ["premium_replayable"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None
    assert breakdown.relationship == "same"
    assert breakdown.shared_mode_profile == ["drop_in_coop", "party_coop", "single_player"]
    assert breakdown.shared_progression_model == ["buildcraft"]


def test_build_similarity_breakdown_v2_allows_farming_sim_same_lane_matches_via_cozy_sim_bridge():
    anchor = Game(
        title="Collector's Cove",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="farming_sim",
        taxonomy_v2_fingerprint={
            "tone": ["cozy"],
            "session_shape": ["sandbox_loop"],
            "world_density": ["sandbox_light"],
            "challenge_model": ["sim_realism"],
            "combat_presence": ["none"],
            "input_complexity": ["casual"],
            "mode_profile": ["single_player"],
            "progression_model": ["base_growth"],
        },
    )
    candidate = Game(
        title="Little Friends: Puppy Island",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="farming_sim",
        taxonomy_v2_fingerprint={
            "tone": ["cozy"],
            "challenge_model": ["sim_realism"],
            "combat_presence": ["none"],
            "combat_style": ["party_tactics"],
            "combat_structure": ["party_management"],
            "mode_profile": ["single_player"],
            "progression_model": ["relationship_social"],
            "entity_interaction": ["party_control"],
            "mechanics_structure": ["party_management_loop"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None
    assert breakdown.relationship == "same"
    assert breakdown.shared_mode_profile == ["single_player"]
    assert breakdown.shared_tone == ["cozy"]
    assert breakdown.shared_challenge_model == ["sim_realism"]


def test_build_similarity_breakdown_v2_allows_survival_horror_same_lane_matches_via_horror_identity_bridge():
    anchor = Game(
        title="Resident Evil Requiem",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="survival_horror",
        taxonomy_v2_fingerprint={
            "tone": ["bleak"],
            "setting": ["horror"],
            "rules_goals": ["solve_mysteries"],
            "combat_style": ["survival"],
            "mode_profile": ["single_player"],
            "session_shape": ["campaign"],
            "challenge_model": ["puzzle_gating"],
            "narrative_topic": ["detective_mystery", "survival_escape"],
            "narrative_structure": ["authored_linear"],
        },
    )
    candidate = Game(
        title="Resident Evil 4",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="survival_horror",
        taxonomy_v2_fingerprint={
            "tone": ["bleak", "grotesque"],
            "setting": ["horror"],
            "rules_goals": ["solve_mysteries"],
            "combat_style": ["survival"],
            "mode_profile": ["single_player"],
            "session_shape": ["campaign"],
            "challenge_model": ["puzzle_gating"],
            "narrative_topic": ["detective_mystery", "survival_escape"],
            "narrative_structure": ["authored_linear"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None
    assert breakdown.relationship == "same"
    assert breakdown.shared_setting == ["horror"]
    assert breakdown.shared_mode_profile == ["single_player"]
    assert breakdown.shared_session_shape == ["campaign"]
    assert breakdown.shared_combat_style == ["survival"]


def test_build_similarity_breakdown_v2_allows_metroidvania_same_lane_matches_via_platforming_bridge():
    anchor = Game(
        title="Adventurous Slime",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based", "semi_open"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
        },
    )
    candidate = Game(
        title="Ori and the Blind Forest",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based", "semi_open"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None
    assert breakdown.relationship == "same"
    assert breakdown.shared_traversal_verbs == ["platforming"]
    assert breakdown.shared_world_topology == ["level_based", "semi_open"]


def test_build_similarity_breakdown_v2_allows_precision_platformer_same_lane_matches():
    anchor = Game(
        title="LOVE",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="precision_platformer",
        taxonomy_v2_fingerprint={
            "world_topology": ["level_based"],
            "perspective": ["side_scrolling"],
            "traversal_verbs": ["platforming"],
            "challenge_model": ["precision_platforming"],
            "input_complexity": ["mastery_heavy"],
            "mode_profile": ["single_player"],
            "combat_presence": ["none"],
        },
    )
    candidate = Game(
        title="Celeste",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="precision_platformer",
        taxonomy_v2_fingerprint={
            "world_topology": ["level_based"],
            "perspective": ["side_scrolling"],
            "traversal_verbs": ["platforming"],
            "challenge_model": ["precision_platforming"],
            "input_complexity": ["mastery_heavy"],
            "mode_profile": ["single_player"],
            "combat_presence": ["none"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None
    assert breakdown.relationship == "same"
    assert breakdown.shared_traversal_verbs == ["platforming"]
    assert breakdown.shared_challenge_model == ["precision_platforming"]


def test_build_similarity_breakdown_v2_allows_hidden_object_same_lane_matches_via_puzzle_bridge():
    anchor = Game(
        title="Packing Life",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="hidden_object_puzzle",
        taxonomy_v2_fingerprint={
            "challenge_model": ["puzzle_gating", "sim_realism"],
            "combat_presence": ["none"],
            "mode_profile": ["single_player"],
        },
    )
    candidate = Game(
        title="Thimbleweed Park",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="hidden_object_puzzle",
        taxonomy_v2_fingerprint={
            "challenge_model": ["puzzle_gating"],
            "combat_presence": ["none"],
            "mode_profile": ["single_player"],
            "interface_control": ["cursor_driven"],
            "mechanics_structure": ["environmental_puzzle_solving"],
            "entity_interaction": ["cursor_driven_interaction"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None
    assert breakdown.relationship == "same"
    assert breakdown.shared_challenge_model == ["puzzle_gating"]
    assert breakdown.shared_mode_profile == ["single_player"]


def test_build_similarity_breakdown_v2_allows_collectathon_same_lane_matches_via_traversal_bridge():
    anchor = Game(
        title="Parkour Labs",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="3d_collectathon",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "mode_profile": ["party_coop", "pvp", "single_player"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["parkour", "platforming"],
        },
    )
    candidate = Game(
        title="Astro Bot",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="3d_collectathon",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["platforming"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None
    assert breakdown.relationship == "same"
    assert "Shared traversal" in " ".join(breakdown.match_reasons)
    assert breakdown.shared_traversal_verbs == ["platforming"]


def test_build_similarity_breakdown_v2_allows_visual_novel_same_lane_matches_via_campaign_bridge():
    anchor = Game(
        title="Eve of the 12 Months",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="visual_novel",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["none"],
            "interface_control": ["cursor_driven"],
            "narrative_structure": ["authored_linear"],
        },
    )
    candidate = Game(
        title="Path of Mystery: A Brush with Death",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="visual_novel",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["none"],
            "rules_goals": ["solve_mysteries"],
            "narrative_topic": ["detective_mystery"],
            "narrative_structure": ["authored_linear"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None
    assert breakdown.relationship == "same"
    assert breakdown.shared_session_shape == ["campaign"]


def test_build_similarity_breakdown_v2_allows_action_horror_same_lane_matches_via_horror_action_bridge():
    anchor = Game(
        title="Welcome to Doll Town",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="action_horror",
        taxonomy_v2_fingerprint={
            "tone": ["bleak", "grotesque"],
            "setting": ["horror"],
            "perspective": ["third_person"],
            "mode_profile": ["single_player"],
            "narrative_topic": ["survival_escape"],
        },
    )
    candidate = Game(
        title="Evil West",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="action_horror",
        taxonomy_v2_fingerprint={
            "tone": ["grotesque"],
            "setting": ["horror"],
            "perspective": ["third_person"],
            "mode_profile": ["drop_in_coop", "single_player"],
            "combat_style": ["shooter"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None
    assert breakdown.relationship == "same"
    assert breakdown.shared_setting == ["horror"]
    assert breakdown.shared_tone == ["grotesque"]


def test_build_similarity_breakdown_v2_allows_co_op_horror_same_lane_matches_via_horde_identity_bridge():
    anchor = Game(
        title="John Carpenter's Toxic Commando",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="co_op_horror",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "perspective": ["first_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["shooter"],
            "combat_structure": ["crowd_control", "encounter_driven"],
            "setting": ["horror"],
            "mode_profile": ["drop_in_coop", "party_coop", "single_player"],
        },
    )
    candidate = Game(
        title="Back 4 Blood",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="co_op_horror",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "perspective": ["first_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["shooter"],
            "combat_structure": ["crowd_control", "encounter_driven"],
            "setting": ["horror"],
            "mode_profile": ["drop_in_coop", "party_coop", "pvp", "single_player"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None
    assert breakdown.relationship == "same"
    assert breakdown.shared_mode_profile == ["drop_in_coop", "party_coop", "single_player"]
    assert breakdown.shared_combat_style == ["shooter"]
    assert breakdown.shared_combat_structure == ["crowd_control", "encounter_driven"]


def test_build_similarity_breakdown_v2_allows_kingdom_decision_sim_same_lane_matches_via_choice_bridge():
    anchor = Game(
        title="Reigns",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="kingdom_decision_sim",
        taxonomy_v2_fingerprint={
            "combat_presence": ["none"],
            "session_shape": ["campaign"],
            "narrative_structure": ["authored_branching"],
            "interface_control": ["cursor_driven"],
            "entity_interaction": ["dialogue_choice"],
            "progression_model": ["base_growth"],
            "mechanics_structure": ["systemic_problem_solving"],
            "rules_goals": ["build_and_optimize"],
            "mode_profile": ["single_player"],
        },
    )
    candidate = Game(
        title="Reigns: Her Majesty",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="kingdom_decision_sim",
        taxonomy_v2_fingerprint={
            "combat_presence": ["none"],
            "session_shape": ["campaign"],
            "narrative_structure": ["authored_branching"],
            "interface_control": ["cursor_driven"],
            "entity_interaction": ["dialogue_choice"],
            "progression_model": ["base_growth"],
            "mechanics_structure": ["systemic_problem_solving"],
            "rules_goals": ["build_and_optimize"],
            "mode_profile": ["single_player"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None
    assert breakdown.relationship == "same"
    assert breakdown.shared_interface_control == ["cursor_driven"]
    assert breakdown.shared_entity_interaction == ["dialogue_choice"]
    assert breakdown.shared_rules_goals == ["build_and_optimize"]


def test_build_similarity_breakdown_v2_allows_action_horror_to_psychological_horror_bridge():
    anchor = Game(
        title="Welcome to Doll Town",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="action_horror",
        taxonomy_v2_fingerprint={
            "tone": ["bleak", "grotesque"],
            "setting": ["horror"],
            "perspective": ["third_person"],
            "mode_profile": ["single_player"],
            "narrative_topic": ["survival_escape"],
        },
    )
    candidate = Game(
        title="The Medium",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="psychological_horror",
        taxonomy_v2_fingerprint={
            "tone": ["bleak", "melancholic"],
            "setting": ["horror"],
            "perspective": ["third_person"],
            "mode_profile": ["single_player"],
            "session_shape": ["campaign"],
            "combat_presence": ["light", "none"],
            "narrative_topic": ["survival_escape", "detective_mystery"],
            "keyword_layer": ["psychological_horror"],
            "world_topology": ["linear"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None
    assert breakdown.relationship.startswith("bridge")
    assert breakdown.shared_setting == ["horror"]
    assert breakdown.shared_narrative_topic == ["survival_escape"]


def test_prefer_primary_archetype_candidate_prefers_loot_action_rpg_over_party_game_for_diablo_like_profile():
    fingerprint = {field: [] for field in FINGERPRINT_AXES}
    fingerprint["world_topology"] = ["semi_open"]
    fingerprint["combat_presence"] = ["dominant"]
    fingerprint["combat_style"] = ["hybrid", "melee", "magic"]
    fingerprint["combat_structure"] = ["crowd_control", "encounter_driven"]
    fingerprint["progression_model"] = ["buildcraft", "gear_chase", "loot_rarity", "skill_tree", "base_growth"]
    fingerprint["rules_goals"] = ["build_and_optimize", "complete_quests", "defeat_bosses"]
    fingerprint["entity_interaction"] = ["inventory_loot", "construction_placement"]
    fingerprint["mode_profile"] = ["single_player", "drop_in_coop", "party_coop"]
    fingerprint["setting"] = ["high_fantasy"]
    fingerprint["content_model"] = ["premium_replayable"]

    confidence_by_field_value = {
        field: {value: 0.95 for value in values}
        for field, values in fingerprint.items()
        if values
    }
    candidates = assign_taxonomy_v2_archetypes(fingerprint, confidence_by_field_value)
    candidates.append(
        ArchetypeCandidate(
            archetype="party_game",
            family="sports_racing",
            score=220,
            required_hits=2,
            required_total=2,
            preferred_hits=0,
            preferred_total=1,
            confidence=0.84,
        )
    )

    preferred = _prefer_primary_archetype_candidate(candidates, fingerprint)

    assert preferred[0].archetype == "loot_action_rpg"


def test_build_game_taxonomy_v2_assigns_loot_action_rpg_from_replayable_buildcraft_profile():
    game = Game(
        id=246,
        title="Dragonkin Style",
        steam_detailed_description=(
            "A dark fantasy action RPG where you fight hordes of enemies, adapt your build, chase powerful loot, "
            "defeat bosses, and improve your city in solo or drop-in co-op."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=246, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=246, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=246, source="steam", facet="category", raw_label="Online Co-op", normalized_label="online co-op"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "loot_action_rpg"
    assert "premium_replayable" in result.fingerprint["content_model"]


def test_build_game_taxonomy_v2_assigns_loot_action_rpg_from_last_epoch_style_profile_with_generic_multiplayer_noise():
    game = Game(
        id=2463,
        title="Epoch Style",
        steam_detailed_description=(
            "An action RPG with endless replayability, dungeon crawling, character customization, and mastery classes. "
            "Ascend into mastery classes, hunt epic loot, and wield transformative skill trees."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2463, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2463, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=2463, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=2463, source="steam", facet="category", raw_label="Online Co-op", normalized_label="online co-op"),
        GameSourceTaxonomyLabel(game_id=2463, source="steam", facet="category", raw_label="Multi-player", normalized_label="multi-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "loot_action_rpg"
    assert "premium_replayable" in result.fingerprint["content_model"]
    assert "pvp" not in result.fingerprint["mode_profile"]


def test_build_game_taxonomy_v2_prefers_loot_action_rpg_over_action_horror_for_diablo_style_profile():
    game = Game(
        id=2464,
        title="Sanctuary Style",
        steam_detailed_description=(
            "The next-gen action RPG experience with endless evil to slaughter, countless abilities to master, "
            "nightmarish dungeons, legendary loot, and new seasonal content. Embark on the campaign solo or with friends."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2464, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2464, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=2464, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=2464, source="steam", facet="category", raw_label="Online Co-op", normalized_label="online co-op"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "loot_action_rpg"
    assert "horror" in result.fingerprint["setting"]


def test_build_game_taxonomy_v2_assigns_loot_action_rpg_from_randomized_world_and_class_choice_profile():
    game = Game(
        id=2465,
        title="Torch Style",
        steam_detailed_description=(
            "An action RPG filled with epic battles, bountiful treasure, and a fully randomized world. "
            "With four classes to choose from, level randomization, new game plus, and character customization, "
            "you can keep chasing better loot in solo or co-op."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2465, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2465, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=2465, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=2465, source="steam", facet="category", raw_label="Online Co-op", normalized_label="online co-op"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "loot_action_rpg"
    assert "premium_replayable" in result.fingerprint["content_model"]
    assert "gear_chase" in result.fingerprint["progression_model"]


def test_build_game_taxonomy_v2_assigns_loot_action_rpg_from_hack_and_slash_horde_profile():
    game = Game(
        id=2466,
        title="Chaos Style",
        steam_detailed_description=(
            "The first hack and slash in a dark fantasy setting where you choose a hero from four character classes, "
            "fight through monster hordes using over 180 different powers, and chase powerful artefacts in solo or co-op."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2466, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2466, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=2466, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=2466, source="steam", facet="category", raw_label="Online Co-op", normalized_label="online co-op"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "loot_action_rpg"
    assert "inventory_loot" in result.fingerprint["entity_interaction"]
    assert "premium_replayable" in result.fingerprint["content_model"]


def test_extract_v2_evidence_from_description_detects_rogue_lite_spacing_variants():
    hits = extract_v2_evidence_from_description(
        "A fast-paced action rogue-lite where you clear combat rooms, build synergies, and fight through ever-changing runs."
    )
    pairs = {(hit.field, hit.value) for hit in hits}

    assert ("world_topology", "run_based") in pairs
    assert ("session_shape", "roguelite_run") in pairs
    assert ("progression_model", "metaprogression") in pairs


def test_extract_v2_evidence_from_description_detects_roguelite_fps_profile():
    hits = extract_v2_evidence_from_description(
        "Build your weapon to its full potential in a fast-paced FPS roguelite with endless upgrade combinations."
    )
    pairs = {(hit.field, hit.value) for hit in hits}

    assert ("perspective", "first_person") in pairs
    assert ("combat_style", "shooter") in pairs
    assert ("world_topology", "run_based") in pairs
    assert ("session_shape", "roguelite_run") in pairs


def test_build_game_taxonomy_v2_assigns_roguelite_fps_without_coop_requirement():
    game = Game(
        id=24661,
        title="Galactic Vault Style",
        steam_short_description=(
            "Build your weapon to its full potential in this fast-paced FPS roguelite. "
            "Discover endless upgrade combinations, craft diverse builds, and infiltrate high-security vaults."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24661, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=24661, source="steam", facet="genre", raw_label="FPS", normalized_label="fps"),
        GameSourceTaxonomyLabel(game_id=24661, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "roguelite_fps"
    assert "run_based" in result.fingerprint["world_topology"]
    assert "roguelite_run" in result.fingerprint["session_shape"]


def test_build_game_taxonomy_v2_assigns_shoot_em_up_from_arcade_shooter_profile():
    game = Game(
        id=24662,
        title="Raiden Style",
        steam_detailed_description=(
            "A classic arcade shoot 'em up with vertical screen play and high-octane aerial action. "
            "Blast through these shooters in TATE mode and chase the highest score."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24662, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=24662, source="steam", facet="genre", raw_label="Shoot 'Em Up", normalized_label="shoot 'em up"),
        GameSourceTaxonomyLabel(game_id=24662, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "shoot_em_up"
    assert "shooter" in result.fingerprint["combat_style"]
    assert "twitch" in result.fingerprint["combat_tempo"]
    assert "match_session" in result.fingerprint["session_shape"]


def test_build_game_taxonomy_v2_prefers_jrpg_story_for_turn_based_party_rpg_with_puzzles():
    game = Game(
        id=24663,
        title="Stitched Style",
        steam_detailed_description=(
            "An RPG adventure with a deep story, party members, turn based battles, new abilities, "
            "and environmental puzzles to solve while investigating a strange world."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24663, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=24663, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=24663, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "jrpg_story_rpg"
    assert "none" not in result.fingerprint["combat_presence"]
    assert "turn_based_tactics" in result.secondary_archetypes


def test_build_game_taxonomy_v2_prefers_co_op_action_roguelite_for_run_based_coop_hack_and_slash():
    game = Game(
        id=2467,
        title="Ember Style",
        steam_detailed_description=(
            "In this fast-paced action rogue-lite, play solo or co-op with up to 4 players. "
            "Hack-and-slash deadly hordes through combat rooms, build synergies with game-changing relics, "
            "and push through each run with powerful weapons and skills."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2467, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2467, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=2467, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=2467, source="steam", facet="category", raw_label="Online Co-op", normalized_label="online co-op"),
        GameSourceTaxonomyLabel(game_id=2467, source="steam", facet="category", raw_label="Shared/Split Screen Co-op", normalized_label="shared/split screen co-op"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "co_op_action_roguelite"
    assert "run_based" in result.fingerprint["world_topology"]
    assert "roguelite_run" in result.fingerprint["session_shape"]


def test_build_game_taxonomy_v2_prefers_co_op_action_roguelite_for_roguelike_dungeon_crawler_with_coop():
    game = Game(
        id=2468,
        title="Rotwood Style",
        steam_detailed_description=(
            "A 1-4 player hack-and-slash dungeon crawler where you battle through ever-increasing challenges "
            "in a rogue-like dungeon crawler, gather spoils, and forge a safe haven with your friends."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2468, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2468, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=2468, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=2468, source="steam", facet="category", raw_label="Online Co-op", normalized_label="online co-op"),
        GameSourceTaxonomyLabel(game_id=2468, source="steam", facet="category", raw_label="Shared/Split Screen Co-op", normalized_label="shared/split screen co-op"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "co_op_action_roguelite"
    assert "run_based" in result.fingerprint["world_topology"]
    assert "roguelite_run" in result.fingerprint["session_shape"]


def test_build_game_taxonomy_v2_assigns_merge_puzzle_from_drop_stack_merge_profile():
    game = Game(
        id=2469,
        title="Pan Dulce Style",
        steam_detailed_description=(
            "Drop, stack, and merge colorful treats into bigger desserts in this cozy puzzle game. "
            "Aim for the highest score possible and keep the pastries from overflowing from the box."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2469, source="steam", facet="genre", raw_label="Puzzle", normalized_label="puzzle"),
        GameSourceTaxonomyLabel(game_id=2469, source="steam", facet="genre", raw_label="Casual", normalized_label="casual"),
        GameSourceTaxonomyLabel(game_id=2469, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "merge_puzzle"
    assert "match_session" in result.fingerprint["session_shape"]
    assert "build_and_optimize" in result.fingerprint["rules_goals"]


def test_build_game_taxonomy_v2_assigns_merge_puzzle_from_suika_style_profile():
    game = Game(
        id=2470,
        title="Watermelon Style",
        steam_detailed_description=(
            "Combine two small fruits to make them larger, collide the same kind of fruit, "
            "and create big watermelons before the fruit starts overflowing from the box."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2470, source="steam", facet="genre", raw_label="Puzzle", normalized_label="puzzle"),
        GameSourceTaxonomyLabel(game_id=2470, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "merge_puzzle"
    assert "systemic_problem_solving" in result.fingerprint["mechanics_structure"]


def test_build_game_taxonomy_v2_assigns_physics_roguelite_strategy_from_pachinko_profile():
    game = Game(
        id=2471,
        title="Peg Style",
        steam_detailed_description=(
            "A pachinko roguelike where powerful orbs and relics radically change each run. "
            "Press your luck, build powerful combos, and defeat enemies with physics-driven shots."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2471, source="steam", facet="genre", raw_label="Strategy", normalized_label="strategy"),
        GameSourceTaxonomyLabel(game_id=2471, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=2471, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "physics_roguelite_strategy"
    assert "run_based" in result.fingerprint["world_topology"]
    assert "roguelite_run" in result.fingerprint["session_shape"]


def test_build_game_taxonomy_v2_assigns_physics_roguelite_strategy_from_slot_machine_combo_profile():
    game = Game(
        id=2472,
        title="Landlord Style",
        steam_detailed_description=(
            "A roguelike deckbuilder about using a slot machine to earn rent money. "
            "The symbols are different every time, leading to build strategies and procedural runs."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2472, source="steam", facet="genre", raw_label="Strategy", normalized_label="strategy"),
        GameSourceTaxonomyLabel(game_id=2472, source="steam", facet="genre", raw_label="Simulation", normalized_label="simulation"),
        GameSourceTaxonomyLabel(game_id=2472, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "physics_roguelite_strategy"
    assert "buildcraft" in result.fingerprint["progression_model"]


def test_build_game_taxonomy_v2_assigns_metroidvania_from_explicit_identity_language():
    game = Game(
        id=2461,
        title="Sky Isles",
        steam_short_description=(
            "Take to the sky and reunite a fragmented world in this surprisingly wholesome metroidvania. "
            "Adventure across beautiful islands, uncover secrets, and unlock new abilities as you backtrack through an interconnected world."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2461, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2461, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=2461, source="steam", facet="genre", raw_label="Indie", normalized_label="indie"),
        GameSourceTaxonomyLabel(game_id=2461, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "metroidvania"


def test_build_game_taxonomy_v2_assigns_metroidvania_from_wholesome_fragmented_islands_profile():
    game = Game(
        id=2466,
        title="Sky Fragments",
        steam_short_description=(
            "Take to the sky and reunite a fragmented world in this surprisingly wholesome metroidvania. "
            "Help a curious hero explore floating islands and uncover secrets."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2466, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2466, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=2466, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "metroidvania"


def test_build_game_taxonomy_v2_assigns_metroidvania_from_compact_space_exploration_profile():
    game = Game(
        id=2469,
        title="Star Drifter",
        steam_short_description=(
            "An interstellar drifter embarks on a mission of exploration across a small cluster of four planets. "
            "Collect special powers, squeeze through tight passages, and defeat menacing bosses."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2469, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2469, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=2469, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "metroidvania"


def test_build_game_taxonomy_v2_assigns_farming_sim_from_farm_inheritance_profile():
    game = Game(
        id=2462,
        title="Cozy Farm",
        steam_short_description=(
            "You've inherited your grandfather's old farm plot. Set out to begin your new life, raise animals, "
            "help rebuild the community, fish, and harvest your own crops in a cozy farming adventure."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2462, source="steam", facet="genre", raw_label="Simulation", normalized_label="simulation"),
        GameSourceTaxonomyLabel(game_id=2462, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=2462, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "farming_sim"


def test_build_game_taxonomy_v2_assigns_farming_sim_from_cozy_fishing_town_restoration_profile():
    game = Game(
        id=2470,
        title="Harbor Life",
        steam_short_description=(
            "A slice-of-life fishing RPG where a rookie angler hones their fishing skills, nourishes relationships, "
            "and helps restore a remote town's fractured community."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2470, source="steam", facet="genre", raw_label="Casual", normalized_label="casual"),
        GameSourceTaxonomyLabel(game_id=2470, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "farming_sim"
    assert "base_growth" in result.fingerprint["progression_model"]
    assert "relationship_social" in result.fingerprint["progression_model"]


def test_build_game_taxonomy_v2_assigns_psychological_horror_from_dual_reality_profile():
    game = Game(
        id=2463,
        title="Dual Realm",
        steam_short_description=(
            "A third-person psychological horror game where you explore both the real world and the spirit realm. "
            "Drawn to a deserted resort, you'll uncover dark secrets and survive the horrors that haunt it."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2463, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=2463, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "psychological_horror"


def test_build_game_taxonomy_v2_assigns_survival_horror_from_fixed_camera_escape_profile():
    game = Game(
        id=24631,
        title="Fixed Camera Terror",
        steam_short_description=(
            "A fixed-camera survival horror adventure where you cannot fight. "
            "Stay alert, hide, breathe slowly, explore cursed places, and solve puzzles while disturbing monsters stalk you."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24631, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=24631, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "survival_horror"
    assert "survival" in result.fingerprint["combat_style"]
    assert "encounter_driven" in result.fingerprint["combat_structure"]


def test_build_game_taxonomy_v2_assigns_survival_horror_from_haunted_village_puzzle_profile():
    game = Game(
        id=24632,
        title="Doll Town Terror",
        steam_short_description=(
            "Explore a cursed village of haunted dollhouses, solve eerie puzzles, and escape a twisted nightmare."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24632, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=24632, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "survival_horror"
    assert "puzzle_gating" in result.fingerprint["challenge_model"]
    assert "survival" in result.fingerprint["combat_style"]


def test_build_game_taxonomy_v2_assigns_survival_horror_from_supernatural_village_profile():
    game = Game(
        id=24633,
        title="Crimson Butterfly Village",
        steam_short_description=(
            "When twin sisters find themselves lost in a village that has vanished from the map, "
            "they fight to unravel the mysteries of the supernatural phenomena surrounding them."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24633, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=24633, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "survival_horror"
    assert "horror" in result.fingerprint["setting"]


def test_build_game_taxonomy_v2_assigns_survival_horror_from_hotel_cult_investigation_profile():
    game = Game(
        id=24634,
        title="Hotel Cult Horror",
        steam_short_description=(
            "An amateur journalist explores a decadent hotel after mysterious disappearances and paranormal activity. "
            "Uncover the dark history of a fanatical cult while solving mysteries across the hotel."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24634, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=24634, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "survival_horror"
    assert "puzzle_gating" in result.fingerprint["challenge_model"]
    assert "solve_mysteries" in result.fingerprint["rules_goals"]


def test_build_game_taxonomy_v2_assigns_survival_horror_from_thriller_survival_horror_profile():
    game = Game(
        id=24635,
        title="Family Attic Horror",
        steam_short_description=(
            "A story-driven adventure with a unique twist on thriller and survival horror. "
            "Uncover long-buried secrets, personal tragedies, and madness as you combat the enemies and solve riddles."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24635, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=24635, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "survival_horror"
    assert "survival" in result.fingerprint["combat_style"]
    assert "encounter_driven" in result.fingerprint["combat_structure"]


def test_build_game_taxonomy_v2_assigns_hidden_object_puzzle_from_organization_profile():
    game = Game(
        id=2464,
        title="Warehouse Order",
        steam_short_description=(
            "A puzzle game about keeping a warehouse running in tip-top shape. Remember where you put everything, "
            "organize the stock, and fit items before the service hatch opens."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2464, source="steam", facet="genre", raw_label="Casual", normalized_label="casual"),
        GameSourceTaxonomyLabel(game_id=2464, source="steam", facet="genre", raw_label="Simulation", normalized_label="simulation"),
        GameSourceTaxonomyLabel(game_id=2464, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "hidden_object_puzzle"


def test_build_game_taxonomy_v2_assigns_hidden_object_puzzle_from_bento_pattern_puzzle_profile():
    game = Game(
        id=24641,
        title="Bento Logic",
        steam_short_description=(
            "A cooking puzzle game about arranging beautiful bento lunches. "
            "Prepare tasty bento dishes, recreate over 120 puzzling recipes, and fit everything into an elaborate lunchbox while sticking to the recipe."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24641, source="steam", facet="genre", raw_label="Casual", normalized_label="casual"),
        GameSourceTaxonomyLabel(game_id=24641, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "hidden_object_puzzle"
    assert "puzzle_gating" in result.fingerprint["challenge_model"]
    assert "none" in result.fingerprint["combat_presence"]


def test_build_game_taxonomy_v2_assigns_hidden_object_puzzle_from_repair_restoration_profile():
    game = Game(
        id=24642,
        title="Repair Story",
        steam_short_description=(
            "Repair old-school objects in this cozy puzzle game. Join a globe-trotting antique restorer "
            "as she helps townsfolk save their most beloved possessions."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24642, source="steam", facet="genre", raw_label="Casual", normalized_label="casual"),
        GameSourceTaxonomyLabel(game_id=24642, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "hidden_object_puzzle"
    assert "systemic_problem_solving" in result.fingerprint["mechanics_structure"]


def test_build_game_taxonomy_v2_strips_false_racing_signals_from_first_person_parkour_profile():
    game = Game(
        id=2467,
        title="Speed Tower",
        steam_short_description=(
            "The world's only competitive heavy metal first-person platformer focused on speed and fast reactions. "
            "Race and blast your way through deadly arenas and chase fastest times."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2467, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2467, source="steam", facet="genre", raw_label="Racing", normalized_label="racing"),
        GameSourceTaxonomyLabel(game_id=2467, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert "driving" not in result.fingerprint["traversal_verbs"]
    assert "cars" not in result.fingerprint["vehicular_theme"]
    assert "vehicle_control" not in result.fingerprint["interface_control"]
    assert "vehicular_racing" not in result.fingerprint["mechanics_structure"]
    assert "win_races" not in result.fingerprint["rules_goals"]


def test_build_game_taxonomy_v2_assigns_co_op_action_roguelite_from_twin_stick_base_defense_profile():
    game = Game(
        id=24671,
        title="Ship Defense Kritters",
        steam_short_description=(
            "Explore, loot, and rush back to defend your spaceship against alien hordes in this frantic "
            "twin-stick shooter action roguelite. Solo or 4-player co-op, grow stronger run after run."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24671, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=24671, source="steam", facet="category", raw_label="Online Co-op", normalized_label="online co-op"),
        GameSourceTaxonomyLabel(game_id=24671, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "co_op_action_roguelite"
    assert "roguelite_run" in result.fingerprint["session_shape"]


def test_build_game_taxonomy_v2_strips_party_and_horror_noise_from_wholesome_metroidvania_profile():
    game = Game(
        id=2468,
        title="Skybound Isles",
        steam_short_description=(
            "Take to the sky and reunite a fragmented world in this surprisingly wholesome metroidvania. "
            "Adventure across hand-painted islands, receive letters from a quirky cast of characters, "
            "and face powerful monstrous adversaries."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2468, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2468, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=2468, source="steam", facet="genre", raw_label="Metroidvania", normalized_label="metroidvania"),
        GameSourceTaxonomyLabel(game_id=2468, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.primary_archetype == "metroidvania"
    assert "party_management" not in result.fingerprint["combat_structure"]
    assert "party_tactics" not in result.fingerprint["combat_style"]
    assert "party_control" not in result.fingerprint["entity_interaction"]
    assert "horror" not in result.fingerprint["setting"]
    assert "side_scrolling" in result.fingerprint["perspective"]


def test_build_game_taxonomy_v2_assigns_precision_platformer_from_respawn_score_attack_profile():
    game = Game(
        id=24681,
        title="LOVE",
        steam_short_description=(
            "A reductive platforming game with a retro aesthetic and a focus on challenging difficulty. "
            "It has a custom respawn system, competitive scoring, and 16 levels."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24681, source="opencritic", facet="genre", raw_label="Platformer", normalized_label="platformer"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "precision_platformer"
    assert "precision_platforming" in result.fingerprint["challenge_model"]


def test_build_game_taxonomy_v2_assigns_precision_platformer_from_tough_as_nails_profile():
    game = Game(
        id=24682,
        title="Super Meat Boy",
        steam_short_description=(
            "A tough-as-nails platformer where you leap from walls, avoid deadly saw blades, and chase competitive scoring."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24682, source="metacritic", facet="genre", raw_label="2D Platformer", normalized_label="2d platformer"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "precision_platformer"
    assert "first_person" not in result.fingerprint["perspective"]


def test_build_game_taxonomy_v2_assigns_metroidvania_from_mech_tight_passage_profile():
    game = Game(
        id=2470,
        title="Mech Cat",
        steam_short_description=(
            "Pounce inside your armored mech and set off on a dangerous trek through an alien underworld. "
            "Squeeze through tight passages, save your stranded captain, and blast suspicious beasts."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2470, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2470, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=2470, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "metroidvania"


def test_build_game_taxonomy_v2_assigns_western_narrative_rpg_from_isometric_crpg_profile():
    game = Game(
        id=24701,
        title="Arcane Ebb",
        steam_short_description=(
            "Esoteric Ebb is a single-player CRPG inspired by the freedom of tabletop adventures. "
            "Unravel a political conspiracy, roll dice in tense encounters, and shape a Disco-like story."
        ),
        steam_detailed_description=(
            "An isometric, TTRPG-turned-CRPG where choices matter and you can completely ruin the campaign."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24701, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=24701, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "western_narrative_rpg"
    assert "isometric" in result.fingerprint["perspective"]


def test_build_game_taxonomy_v2_assigns_western_narrative_rpg_from_detective_cityblock_profile():
    game = Game(
        id=24702,
        title="Disco Elysium",
        steam_short_description=(
            "You are a detective with a unique skill system at your disposal and a whole city block to carve your path across. "
            "Interrogate unforgettable characters, crack murders or take bribes."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24702, source="opencritic", facet="genre", raw_label="Role-Playing", normalized_label="role-playing"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "western_narrative_rpg"
    assert "open_world" not in result.fingerprint["world_topology"]
    assert "dominant" not in result.fingerprint["combat_presence"]


def test_build_game_taxonomy_v2_assigns_co_op_action_roguelite_from_tactical_tower_defense_profile():
    game = Game(
        id=24703,
        title="Endless Dungeon",
        steam_short_description=(
            "A unique blend of roguelite, tactical action, and tower defense. Protect your crystal against never-ending waves of monsters."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24703, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=24703, source="steam", facet="category", raw_label="Online Co-op", normalized_label="online co-op"),
        GameSourceTaxonomyLabel(game_id=24703, source="opencritic", facet="genre", raw_label="Real-Time Strategy", normalized_label="real-time strategy"),
        GameSourceTaxonomyLabel(game_id=24703, source="metacritic", facet="genre", raw_label="Real-Time Tactics", normalized_label="real-time tactics"),
        GameSourceTaxonomyLabel(game_id=24703, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "co_op_action_roguelite"
    assert "overhead_strategy_first" not in result.fingerprint["hard_exclusions"]


def test_build_game_taxonomy_v2_assigns_survival_horror_from_forest_suicide_profile():
    game = Game(
        id=24704,
        title="Fatal Frame",
        steam_short_description=(
            "Three interconnected stories converge to uncover the truth behind tragic deaths in a forest marred by a history of suicides."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=24704, source="opencritic", facet="genre", raw_label="Adventure", normalized_label="adventure"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "survival_horror"


def test_build_game_taxonomy_v2_strips_jrpg_noise_from_card_battler_story_profile():
    game = Game(
        id=2471,
        title="Card Detective",
        steam_short_description=(
            "A story-driven roguelite card battler with online PvP. Build your deck, battle head-to-head, "
            "and solve a digital mystery across a full campaign."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2471, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=2471, source="steam", facet="genre", raw_label="Strategy", normalized_label="strategy"),
        GameSourceTaxonomyLabel(game_id=2471, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=2471, source="steam", facet="category", raw_label="PvP", normalized_label="pvp"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert "party_management" not in result.fingerprint["combat_structure"]
    assert "party_control" not in result.fingerprint["entity_interaction"]
    assert "jrpg_first" not in result.hard_exclusions


def test_build_game_taxonomy_v2_strips_jrpg_noise_from_colony_tactical_profile():
    game = Game(
        id=2472,
        title="Demon Colony",
        steam_short_description=(
            "Rebuild a doomed colony, craft defenses, and send squads on tactical missions in a demon apocalypse."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2472, source="steam", facet="genre", raw_label="Simulation", normalized_label="simulation"),
        GameSourceTaxonomyLabel(game_id=2472, source="steam", facet="genre", raw_label="Strategy", normalized_label="strategy"),
        GameSourceTaxonomyLabel(game_id=2472, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=2472, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert "party_management" not in result.fingerprint["combat_structure"]
    assert "party_control" not in result.fingerprint["entity_interaction"]
    assert "jrpg_first" not in result.hard_exclusions


def test_build_game_taxonomy_v2_strips_jrpg_noise_from_action_horror_rpg_profile():
    game = Game(
        id=2473,
        title="Devil Pact",
        steam_short_description=(
            "A dark fantasy dungeon crawler where you make a pact with the devil, chase loot, "
            "and fight nightmarish bosses in third-person combat."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2473, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2473, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=2473, source="steam", facet="genre", raw_label="Strategy", normalized_label="strategy"),
        GameSourceTaxonomyLabel(game_id=2473, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert "party_management" not in result.fingerprint["combat_structure"]
    assert "jrpg_first" not in result.hard_exclusions


def test_build_game_taxonomy_v2_strips_horror_and_sim_noise_from_console_party_jrpg_profile():
    game = Game(
        id=2474,
        title="Console Party RPG",
        steam_short_description=(
            "A fantasy RPG featuring turn-based battles, skill customization, and a rich story about a missing father. "
            "Follow a party of heroes through a full single-player campaign."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2474, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=2474, source="steam", facet="genre", raw_label="Strategy", normalized_label="strategy"),
        GameSourceTaxonomyLabel(game_id=2474, source="steam", facet="genre", raw_label="Simulation", normalized_label="simulation"),
        GameSourceTaxonomyLabel(game_id=2474, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert "sim_realism" not in result.fingerprint["challenge_model"]
    assert "horror" not in result.fingerprint["setting"]


def test_build_game_taxonomy_v2_strips_jrpg_noise_from_co_op_horror_tactical_profile():
    game = Game(
        id=2475,
        title="Zombie Squad Tactics",
        steam_short_description=(
            "Survive hordes of zombies in turn-based shooter battles with drop-in co-op. "
            "Build your squad and fight through a horror campaign with friends."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2475, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=2475, source="steam", facet="genre", raw_label="Strategy", normalized_label="strategy"),
        GameSourceTaxonomyLabel(game_id=2475, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2475, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=2475, source="steam", facet="category", raw_label="Co-op", normalized_label="co-op"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert "party_management" not in result.fingerprint["combat_structure"]
    assert "party_control" not in result.fingerprint["entity_interaction"]
    assert "skill_tree" not in result.fingerprint["progression_model"]
    assert "jrpg_first" not in result.hard_exclusions


def test_prefer_primary_archetype_candidate_prefers_co_op_horror_for_horde_shooter_profile():
    fingerprint = {field: [] for field in FINGERPRINT_AXES}
    fingerprint["world_topology"] = ["mission_based"]
    fingerprint["session_shape"] = ["campaign"]
    fingerprint["perspective"] = ["first_person"]
    fingerprint["combat_presence"] = ["dominant"]
    fingerprint["combat_style"] = ["shooter", "survival"]
    fingerprint["combat_structure"] = ["crowd_control", "encounter_driven"]
    fingerprint["setting"] = ["horror", "modern"]
    fingerprint["mode_profile"] = ["single_player", "drop_in_coop", "party_coop"]

    candidates = [
        ArchetypeCandidate("co_op_horror", "horror", 260, 3, 3, 1, 1, 0.9),
        ArchetypeCandidate("action_horror", "horror", 250, 2, 2, 1, 1, 0.88),
        ArchetypeCandidate("jrpg_story_rpg", "rpg", 300, 4, 4, 1, 1, 0.95),
    ]

    preferred = _prefer_primary_archetype_candidate(candidates, fingerprint)

    assert preferred[0].archetype == "co_op_horror"


def test_prefer_primary_archetype_candidate_prefers_tactical_rpg_for_bleak_horror_party_tactics_profile():
    fingerprint = {field: [] for field in FINGERPRINT_AXES}
    fingerprint["session_shape"] = ["campaign"]
    fingerprint["combat_style"] = ["party_tactics"]
    fingerprint["combat_tempo"] = ["tactical"]
    fingerprint["combat_structure"] = ["party_management"]
    fingerprint["narrative_structure"] = ["authored_linear"]
    fingerprint["setting"] = ["horror"]
    fingerprint["tone"] = ["bleak"]
    fingerprint["mode_profile"] = ["single_player"]

    candidates = [
        ArchetypeCandidate("jrpg_story_rpg", "rpg", 332, 3, 4, 1, 1, 0.86),
        ArchetypeCandidate("tactical_rpg", "rpg", 307, 3, 4, 0, 1, 0.76),
        ArchetypeCandidate("turn_based_tactics", "strategy", 307, 3, 4, 0, 1, 0.76),
    ]

    preferred = _prefer_primary_archetype_candidate(candidates, fingerprint)

    assert preferred[0].archetype == "tactical_rpg"


def test_prefer_primary_archetype_candidate_filters_match_only_candidates_for_deckbuilding_arcade_profiles():
    fingerprint = {field: [] for field in FINGERPRINT_AXES}
    fingerprint["session_shape"] = ["match_session"]
    fingerprint["mode_profile"] = ["single_player"]
    fingerprint["progression_model"] = ["deck_growth"]
    fingerprint["interface_control"] = ["deck_management"]
    fingerprint["keyword_layer"] = ["deckbuilding"]
    fingerprint["mechanics_structure"] = ["deck_construction"]
    fingerprint["input_complexity"] = ["casual"]

    candidates = [
        ArchetypeCandidate("sports_sim", "sports_racing", 232, 2, 2, 1, 3, 0.87),
        ArchetypeCandidate("realistic_racer", "sports_racing", 232, 2, 3, 1, 1, 0.82),
        ArchetypeCandidate("pinball", "sports_racing", 207, 2, 2, 0, 1, 0.83),
    ]

    preferred = _prefer_primary_archetype_candidate(candidates, fingerprint)

    assert preferred == []


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


def test_build_game_taxonomy_v2_assigns_precision_platformer_from_super_tight_climb_profile():
    game = Game(
        id=2801,
        title="Mountain Climber",
        steam_detailed_description=(
            "Help the hero survive a super-tight platformer packed with hundreds of hand-crafted challenges. "
            "If they have the stamina, they can climb any surface for a few seconds."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(
            game_id=2801,
            source="steam",
            facet="genre",
            raw_label="Action",
            normalized_label="action",
        ),
        GameSourceTaxonomyLabel(
            game_id=2801,
            source="metacritic",
            facet="genre",
            raw_label="2D Platformer",
            normalized_label="2d platformer",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.primary_archetype == "precision_platformer"


def test_build_game_taxonomy_v2_assigns_precision_platformer_from_die_a_lot_profile():
    game = Game(
        id=2802,
        title="Ashfall",
        steam_short_description=(
            "A sprawling adventure platformer where you die a lot, but that is part of mastering the run."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(
            game_id=2802,
            source="steam",
            facet="genre",
            raw_label="Action",
            normalized_label="action",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.primary_archetype == "precision_platformer"


def test_build_game_taxonomy_v2_assigns_survival_horror_from_camera_town_horror_profile():
    game = Game(
        id=2803,
        title="Town Camera Horror",
        steam_detailed_description=(
            "A third person supernatural horror game where a student is trapped in an old abandoned town. "
            "Armed with a trusty smart-phone and an SLR camera, they survive terrifying encounters and solve mysterious puzzles."
        ),
    )

    result = build_game_taxonomy_v2(game, [])

    assert result.primary_archetype == "survival_horror"


def test_build_game_taxonomy_v2_prefers_loot_action_rpg_for_base_defense_action_rpg_profile():
    game = Game(
        id=2804,
        title="Planet Defender",
        steam_detailed_description=(
            "A solo or co-op base-building survival game with Action-RPG elements. "
            "Hack and slash hordes of enemies, build up your base, craft weapons, and research new inventions."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(
            game_id=2804,
            source="metacritic",
            facet="genre",
            raw_label="Action RPG",
            normalized_label="action rpg",
        ),
        GameSourceTaxonomyLabel(
            game_id=2804,
            source="steam",
            facet="genre",
            raw_label="Strategy",
            normalized_label="strategy",
        ),
        GameSourceTaxonomyLabel(
            game_id=2804,
            source="steam",
            facet="category",
            raw_label="Online Co-op",
            normalized_label="online co-op",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.primary_archetype == "loot_action_rpg"


def test_build_game_taxonomy_v2_assigns_creative_sandbox_adventure_from_online_builder_profile():
    game = Game(
        id=2805,
        title="Altiros",
        steam_detailed_description=(
            "A creative online sandbox adventure where you build impressive architectural structures. "
            "Explore worlds of skybound islands, reshape or destroy anything, and build your homebase with friends."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(
            game_id=2805,
            source="steam",
            facet="category",
            raw_label="Online Co-op",
            normalized_label="online co-op",
        ),
        GameSourceTaxonomyLabel(
            game_id=2805,
            source="metacritic",
            facet="genre",
            raw_label="Sandbox",
            normalized_label="sandbox",
        ),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.primary_archetype == "creative_sandbox_adventure"


def test_build_game_taxonomy_v2_assigns_creative_sandbox_adventure_from_block_building_profile():
    game = Game(
        id=2806,
        title="Block Maker",
        opencritic_description=(
            "Players create and destroy various types of blocks in a three dimensional environment, "
            "forming fantastic structures, creations and artwork across the world."
        ),
    )

    result = build_game_taxonomy_v2(game, [])

    assert result.primary_archetype == "creative_sandbox_adventure"


def test_build_game_taxonomy_v2_assigns_creative_sandbox_adventure_from_block_building_rpg_profile():
    game = Game(
        id=28061,
        title="Builder Quest Style",
        steam_short_description=(
            "A block-building RPG with a charming single-player campaign and a robust multiplayer building mode. "
            "Explore, battle, build big projects, and restore the ruined realm."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=28061, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=28061, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=28061, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "creative_sandbox_adventure"
    assert "construction_placement" in result.fingerprint["entity_interaction"]


def test_build_game_taxonomy_v2_assigns_creative_sandbox_adventure_from_cozy_life_builder_profile():
    game = Game(
        id=28062,
        title="Pokopia Style",
        metacritic_description=(
            "Shape the world and build a cozy new life with friends. "
            "Rebuild a desolate world into a charming utopia one step at a time."
        ),
    )

    result = build_game_taxonomy_v2(game, [])

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "creative_sandbox_adventure"
    assert "build_and_optimize" in result.fingerprint["rules_goals"]


def test_build_game_taxonomy_v2_assigns_solo_action_roguelite_from_run_based_action_profile():
    game = Game(
        id=28063,
        title="Eko Style",
        steam_detailed_description=(
            "A randomly generated action RPG with rogue-like elements. "
            "Fast paced action asks you to dodge at the perfect time, find old relics, "
            "and grow stronger across each run."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=28063, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=28063, source="steam", facet="genre", raw_label="RPG", normalized_label="rpg"),
        GameSourceTaxonomyLabel(game_id=28063, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "co_op_action_roguelite"
    assert "roguelite_run" in result.fingerprint["session_shape"]


def test_build_game_taxonomy_v2_assigns_rhythm_game_from_rhythm_combat_profile():
    game = Game(
        id=280631,
        title="Hi-Fi Style",
        steam_detailed_description=(
            "A music-based action game with raucous rhythm combat where the world syncs to the music."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=280631, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=280631, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "rhythm_game"
    assert "rhythm_timing" in result.fingerprint["mechanics_structure"]


def test_build_game_taxonomy_v2_assigns_topdown_action_adventure_from_zelda_like_profile():
    game = Game(
        id=280632,
        title="Tunic Style",
        steam_detailed_description=(
            "An isometric action game about a small fox. Explore ancient ruins, hidden secrets, "
            "and lost legends in a handcrafted world."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=280632, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=280632, source="steam", facet="genre", raw_label="Adventure", normalized_label="adventure"),
        GameSourceTaxonomyLabel(game_id=280632, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "open_world_action_adventure"
    assert "isometric" in result.fingerprint["perspective"]


def test_build_game_taxonomy_v2_assigns_retail_management_before_creative_sandbox():
    game = Game(
        id=28064,
        title="Walking Trade Style",
        steam_detailed_description=(
            "A zombie apocalypse store management game. Design your shop, organize shelves, "
            "set prices, hire survivors, and keep customers happy."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=28064, source="steam", facet="genre", raw_label="Simulation", normalized_label="simulation"),
        GameSourceTaxonomyLabel(game_id=28064, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "management_tycoon"
    assert "retail_management" in result.fingerprint["keyword_layer"]


def test_build_game_taxonomy_v2_assigns_transport_sim_from_heavy_machinery_logistics_profile():
    game = Game(
        id=28065,
        title="Docked Style",
        steam_detailed_description=(
            "Operate heavy machinery, restore port infrastructure, use cranes and heavy trucks, "
            "and complete logistics missions in a realistic simulator."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=28065, source="steam", facet="genre", raw_label="Simulation", normalized_label="simulation"),
        GameSourceTaxonomyLabel(game_id=28065, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "transport_sim"
    assert "vehicle_control" in result.fingerprint["interface_control"]


def test_build_game_taxonomy_v2_assigns_mischief_sandbox_from_pet_demolition_profile():
    game = Game(
        id=2807,
        title="Messy Pet Style",
        opencritic_description=(
            "A cute multiplayer game where pets destroy homes to grab the owner's attention. "
            "Players control the pets in a delightful demolition game with casual sandbox chaos."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2807, source="steam", facet="genre", raw_label="Simulation", normalized_label="simulation"),
        GameSourceTaxonomyLabel(game_id=2807, source="steam", facet="genre", raw_label="Casual", normalized_label="casual"),
        GameSourceTaxonomyLabel(game_id=2807, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
        GameSourceTaxonomyLabel(game_id=2807, source="steam", facet="category", raw_label="Online Co-op", normalized_label="online co-op"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "mischief_sandbox_sim"
    assert "cause_mischief" in result.fingerprint["rules_goals"]
    assert "party_management" not in result.fingerprint["combat_structure"]


def test_build_game_taxonomy_v2_assigns_mischief_sandbox_from_goose_profile():
    game = Game(
        id=2808,
        title="Goose Style",
        steam_detailed_description=(
            "It is a lovely morning and you are a horrible goose. "
            "A slapstick-stealth-sandbox where you are a goose let loose on an unsuspecting village."
        ),
    )
    rows = [
        GameSourceTaxonomyLabel(game_id=2808, source="steam", facet="genre", raw_label="Action", normalized_label="action"),
        GameSourceTaxonomyLabel(game_id=2808, source="steam", facet="category", raw_label="Single-player", normalized_label="single-player"),
    ]

    result = build_game_taxonomy_v2(game, rows)

    assert result.status == TAXONOMY_V2_STATUS_COMPUTED
    assert result.primary_archetype == "mischief_sandbox_sim"


def test_build_similarity_breakdown_v2_allows_creative_sandbox_same_lane_matches():
    anchor = Game(
        title="Altiros",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="creative_sandbox_adventure",
        taxonomy_v2_fingerprint={
            "world_density": ["systemic_sandbox"],
            "progression_model": ["buildcraft"],
            "entity_interaction": ["construction_placement"],
            "mechanics_structure": ["settlement_building"],
            "rules_goals": ["build_and_optimize"],
            "mode_profile": ["drop_in_coop"],
        },
    )
    candidate = Game(
        title="Portal Knights",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="creative_sandbox_adventure",
        taxonomy_v2_fingerprint={
            "world_density": ["systemic_sandbox"],
            "progression_model": ["buildcraft"],
            "entity_interaction": ["construction_placement"],
            "mechanics_structure": ["settlement_building"],
            "rules_goals": ["build_and_optimize"],
            "mode_profile": ["single_player", "drop_in_coop"],
        },
    )

    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    assert breakdown is not None
    assert breakdown.relationship == "same"
    assert breakdown.shared_progression_model == ["buildcraft"]
    assert breakdown.shared_entity_interaction == ["construction_placement"]
