from __future__ import annotations

import pytest
from sqlalchemy import Text, select

from app.models.models import Game, GameSimilarityV3Document, GameSimilarityV3Neighbor
from app.services.game_similarity_v3 import (
    SIMILARITY_V3_VERSION,
    LocalSimilarityV3MCP,
    _family_rerank_adjustment,
    _is_nonstandalone_similarity_candidate,
    _jrpg_story_rpg_lane_fit,
    _metroidvania_lane_fit,
    _normalize_taxonomy_score,
    _open_world_fantasy_lane_fit,
    _apply_similarity_v3_gold_policy,
    _select_similarity_v3_neighbors,
    _shared_title_family_prefix_depth,
    _similarity_v3_scoring_profile,
    _title_family_prefixes,
    _title_family_rerank_adjustment,
    _title_variant_key,
    SimilarityV3ScoredNeighbor,
    audit_similarity_v3_confusion,
    audit_similarity_v3_hidden_states,
    build_similarity_v3_documents,
    build_similarity_v3_provider_text_doc,
    load_similarity_v3_target_games,
    mark_game_similarity_v3_dirty,
)
from app.services.game_taxonomy_v2 import TAXONOMY_V2_STATUS_COMPUTED


def test_similarity_v3_model_fields_exist():
    assert "similarity_v3_version" in Game.__table__.c
    assert "similarity_v3_status" in Game.__table__.c
    assert "similarity_v3_dirty" in Game.__table__.c
    assert isinstance(Game.__table__.c.similarity_v3_dirty_reasons.type.item_type, Text)
    assert "similarity_v3_debug_payload" in Game.__table__.c
    assert "fused_embedding" in GameSimilarityV3Document.__table__.c
    assert "fingerprint_embedding" in GameSimilarityV3Document.__table__.c
    assert "prototype_embedding" in GameSimilarityV3Document.__table__.c
    assert "final_score" in GameSimilarityV3Neighbor.__table__.c
    assert "explanation_payload" in GameSimilarityV3Neighbor.__table__.c


def test_build_similarity_v3_provider_text_doc_prefers_steam_detailed_then_other_sources():
    game = Game(
        title="Priority Test",
        steam_detailed_description="Detailed gameplay description with combat and traversal.",
        opencritic_description="OpenCritic description with extra quest detail.",
        steam_short_description="Short teaser line.",
        metacritic_description="Metacritic fallback.",
        description="Short teaser line.",
    )

    doc = build_similarity_v3_provider_text_doc(game)

    assert doc is not None
    assert doc.split("\n\n")[0] == "Detailed gameplay description with combat and traversal."
    assert "OpenCritic description with extra quest detail." in doc
    assert doc.count("Short teaser line.") == 1


def test_build_similarity_v3_provider_text_doc_strips_deluxe_bonus_preamble():
    game = Game(
        title="Deluxe Noise Test",
        steam_detailed_description=(
            "COMPARE EDITIONS. Deluxe Edition includes the full base game. "
            "Cosimo Horse and Accessories. Carozella Nero Race Car. "
            "About the Game Uncover the origins of organized crime in Sicily."
        ),
    )

    doc = build_similarity_v3_provider_text_doc(game)

    assert doc is not None
    assert "Cosimo Horse and Accessories" not in doc
    assert "Carozella Nero Race Car" not in doc
    assert "Uncover the origins of organized crime in Sicily." in doc


def test_build_similarity_v3_documents_generates_synthetic_summary_for_weak_provider_text():
    game = Game(
        title="Weak Text Game",
        steam_short_description="A new adventure.",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "setting": ["high_fantasy"],
            "perspective": ["third_person"],
            "combat_style": ["melee"],
            "progression_model": ["quest_driven"],
        },
    )

    docs = build_similarity_v3_documents(game, [])

    assert docs.provider_text_doc == "A new adventure."
    assert docs.synthetic_summary_doc is not None
    assert "open world fantasy action rpg" in docs.synthetic_summary_doc.lower()
    assert "[synthetic_summary]" in (docs.fused_doc or "")


def test_mark_game_similarity_v3_dirty_dedupes_reason_tokens():
    game = Game(title="Dirty Test")

    assert mark_game_similarity_v3_dirty(game, "source text steam", "source text steam")
    assert game.similarity_v3_dirty is True
    assert game.similarity_v3_dirty_reasons == ["source_text_steam"]

    changed = mark_game_similarity_v3_dirty(game, "taxonomy_v2")

    assert changed is True
    assert game.similarity_v3_dirty_reasons == ["source_text_steam", "taxonomy_v2"]


def test_similarity_v3_version_constant_is_non_empty():
    assert SIMILARITY_V3_VERSION


def test_similarity_v3_local_hash_profile_is_taxonomy_heavy_and_disables_vector_exceptions():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())

    assert profile.taxonomy_weight > profile.text_vector_weight
    assert profile.publish_threshold < 0.70
    assert profile.minimum_taxonomy_score < 0.40
    assert profile.allow_vector_exception is False


def test_normalize_taxonomy_score_uses_backend_divisor():
    assert _normalize_taxonomy_score(210, divisor=300.0) == 0.7
    assert _normalize_taxonomy_score(400, divisor=300.0) == 1.0


class _TitleScalars:
    def __init__(self, items):
        self._items = items

    def first(self):
        return self._items[0] if self._items else None


class _TitleResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _TitleScalars(self._items)


class _TitleSession:
    def __init__(self, result_items):
        self.result_items = list(result_items)

    async def execute(self, statement, *_args, **_kwargs):
        assert isinstance(statement, type(select(Game)))
        return _TitleResult(self.result_items)


async def _resolve_none(*_args, **_kwargs):
    return None


@pytest.mark.asyncio
async def test_load_similarity_v3_target_games_falls_back_to_case_insensitive_title(monkeypatch: pytest.MonkeyPatch):
    game = Game(id=9, title="Crimson Desert")
    db = _TitleSession([game])

    monkeypatch.setattr(
        "app.public_ids.resolve_entity_by_identifier",
        _resolve_none,
        raising=False,
    )

    results = await load_similarity_v3_target_games(
        db,
        game_identifier="Crimson Desert",
    )

    assert results == [game]


def test_title_variant_key_collapses_switch_2_edition_duplicates():
    assert _title_variant_key("The Legend of Zelda: Breath of the Wild") == _title_variant_key(
        "The Legend of Zelda: Breath of the Wild Nintendo Switch 2 Edition"
    )


def test_title_family_prefixes_extract_series_safe_prefixes():
    assert "call of duty" in _title_family_prefixes("Call of Duty: Black Ops 7")
    assert "call of duty black ops" in _title_family_prefixes("Call of Duty: Black Ops 7")
    assert _title_family_prefixes("WWE 2K26") == ["wwe"]


def test_title_family_rerank_adjustment_rewards_direct_series_pairs():
    anchor = Game(title="Resident Evil Requiem")
    candidate = Game(title="Resident Evil Village")
    unrelated = Game(title="Silent Hill 2")

    assert _shared_title_family_prefix_depth(anchor.title, candidate.title) >= 2
    assert _title_family_rerank_adjustment(anchor, candidate) > 0.0
    assert _title_family_rerank_adjustment(anchor, unrelated) == 0.0


def test_nonstandalone_similarity_candidate_detects_expansion_text():
    candidate = Game(
        title="The Witcher 3: Wild Hunt - Hearts of Stone",
        steam_detailed_description="This expansion requires the base game The Witcher 3: Wild Hunt to play.",
    )
    candidate_doc = GameSimilarityV3Document(
        provider_text_doc="This expansion requires the base game The Witcher 3: Wild Hunt to play."
    )

    assert _is_nonstandalone_similarity_candidate(candidate, candidate_doc) is True


def test_nonstandalone_similarity_candidate_does_not_flag_base_game_deluxe_bundle_copy():
    candidate = Game(
        title="Elden Ring",
        steam_detailed_description=(
            "The Deluxe Edition includes the base game and a digital artbook for Elden Ring."
        ),
    )
    candidate_doc = GameSimilarityV3Document(
        provider_text_doc="The Deluxe Edition includes the base game and a digital artbook for Elden Ring."
    )

    assert _is_nonstandalone_similarity_candidate(candidate, candidate_doc) is False


def test_open_world_fantasy_lane_fit_allows_crimson_like_open_air_same_lane_match():
    anchor = Game(
        title="Crimson-Like Anchor",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["horseback", "gliding"],
            "progression_model": ["base_growth", "buildcraft", "quest_driven"],
            "rules_goals": ["build_and_optimize", "complete_quests"],
            "entity_interaction": ["construction_placement"],
            "combat_style": ["hybrid", "melee"],
            "setting": ["high_fantasy", "mythic"],
        },
    )
    candidate = Game(
        title="Open-Air Peer",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["climbing", "gliding"],
            "combat_style": ["hybrid"],
            "setting": ["high_fantasy", "mythic"],
        },
    )

    assert _open_world_fantasy_lane_fit(anchor, candidate) is not None


def test_open_world_fantasy_lane_fit_rejects_crimson_like_same_lane_candidate_without_frontier_identity():
    anchor = Game(
        title="Crimson-Like Anchor",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["horseback", "gliding"],
            "progression_model": ["base_growth", "buildcraft", "quest_driven"],
            "rules_goals": ["build_and_optimize", "complete_quests"],
            "entity_interaction": ["construction_placement"],
            "combat_style": ["hybrid", "melee"],
            "setting": ["high_fantasy", "mythic"],
        },
    )
    candidate = Game(
        title="False Frontier Peer",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_style": ["hybrid", "melee"],
            "progression_model": ["buildcraft", "skill_tree"],
            "setting": ["high_fantasy", "mythic"],
        },
    )

    assert _open_world_fantasy_lane_fit(anchor, candidate) is None


def test_open_world_fantasy_lane_fit_rejects_crimson_like_survival_sandbox_same_lane_candidate():
    anchor = Game(
        title="Crimson-Like Anchor",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["horseback", "gliding"],
            "progression_model": ["base_growth", "buildcraft", "quest_driven"],
            "rules_goals": ["build_and_optimize", "complete_quests"],
            "entity_interaction": ["construction_placement"],
            "combat_style": ["hybrid", "melee"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )
    candidate = Game(
        title="Sandbox Survival Peer",
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

    assert _open_world_fantasy_lane_fit(anchor, candidate) is None


def test_family_rerank_adjustment_penalizes_mmo_neighbor_for_zelda_like_anchor():
    anchor = Game(
        title="The Legend of Zelda: Tears of the Kingdom",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["climbing", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )
    candidate = Game(
        title="Black Desert Online",
        taxonomy_v2_primary_archetype="mmo_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world", "persistent_shared_world"],
            "perspective": ["third_person"],
            "setting": ["high_fantasy", "mythic"],
            "rules_goals": ["build_and_optimize"],
            "mode_profile": ["mmo"],
        },
    )

    adjustment = _family_rerank_adjustment(anchor, candidate, taxonomy_breakdown=object())

    assert adjustment < 0


def test_family_rerank_adjustment_prefers_expected_soulslike_peer_over_open_world_bridge():
    anchor = Game(
        title="Elden Ring",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_structure": ["boss_centric"],
            "challenge_model": ["soulslike"],
            "rules_goals": ["defeat_bosses"],
            "setting": ["dark_fantasy", "mythic"],
        },
    )
    bloodborne = Game(
        title="Bloodborne",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "combat_structure": ["boss_centric"],
            "challenge_model": ["soulslike"],
            "rules_goals": ["defeat_bosses"],
            "setting": ["dark_fantasy", "horror"],
        },
    )
    crimson = Game(
        title="Crimson Desert",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["horseback", "gliding"],
            "challenge_model": ["soulslike"],
            "rules_goals": ["defeat_bosses", "complete_quests"],
            "setting": ["dark_fantasy", "mythic"],
        },
    )

    bloodborne_adjustment = _family_rerank_adjustment(anchor, bloodborne, taxonomy_breakdown=object())
    crimson_adjustment = _family_rerank_adjustment(anchor, crimson, taxonomy_breakdown=object())

    assert bloodborne_adjustment > crimson_adjustment


def test_metroidvania_lane_fit_prefers_compact_peers_for_compact_anchor(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.services.game_similarity_v3.build_similarity_breakdown_v2",
        lambda *_args, **_kwargs: type("Breakdown", (), {"score": 300})(),
    )
    anchor = Game(
        title="Compact Metro Anchor",
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "world_topology": ["level_based", "semi_open"],
            "world_density": ["handcrafted_discovery"],
            "perspective": ["side_scrolling"],
            "combat_presence": ["moderate"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
            "mode_profile": ["single_player"],
            "input_complexity": ["casual"],
        },
    )
    broad_peer = Game(
        title="Broad Metro Peer",
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world", "semi_open"],
            "world_density": ["handcrafted_discovery"],
            "perspective": ["side_scrolling"],
            "combat_presence": ["moderate"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression", "skill_tree"],
            "input_complexity": ["mastery_heavy"],
            "mode_profile": ["single_player"],
        },
    )
    compact_peer = Game(
        title="Compact Metro Peer",
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "world_topology": ["semi_open"],
            "world_density": ["handcrafted_discovery"],
            "perspective": ["side_scrolling"],
            "combat_presence": ["moderate"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
            "combat_structure": ["boss_centric"],
            "setting": ["sci_fi"],
            "art_style": ["pixel_art"],
            "input_complexity": ["casual"],
            "mode_profile": ["single_player"],
        },
    )

    assert _metroidvania_lane_fit(anchor, compact_peer) > _metroidvania_lane_fit(anchor, broad_peer)


def test_jrpg_story_rpg_lane_fit_penalizes_four_x_polluted_peer_for_console_party_anchor(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "app.services.game_similarity_v3.build_similarity_breakdown_v2",
        lambda *_args, **_kwargs: type("Breakdown", (), {"score": 300})(),
    )
    anchor = Game(
        title="Console JRPG Anchor",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player"],
        },
    )
    polluted_peer = Game(
        title="Polluted Peer",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_secondary_archetypes=["monster_collect_rpg", "turn_based_tactics", "4x_strategy"],
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "challenge_model": ["sim_realism"],
            "mode_profile": ["single_player"],
        },
    )
    console_peer = Game(
        title="Console Peer",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_secondary_archetypes=["monster_collect_rpg", "turn_based_tactics"],
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "mechanics_structure": ["party_management_loop"],
            "entity_interaction": ["party_control"],
            "mode_profile": ["single_player"],
        },
    )

    assert _jrpg_story_rpg_lane_fit(anchor, polluted_peer) is None
    assert _jrpg_story_rpg_lane_fit(anchor, console_peer) is not None


def test_jrpg_story_rpg_lane_fit_penalizes_creature_collection_for_non_collection_anchor(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "app.services.game_similarity_v3.build_similarity_breakdown_v2",
        lambda *_args, **_kwargs: type("Breakdown", (), {"score": 300})(),
    )
    anchor = Game(
        title="Console JRPG Anchor",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player"],
        },
    )
    creature_peer = Game(
        title="Creature Peer",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_secondary_archetypes=["monster_collect_rpg"],
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "entity_interaction": ["creature_collection"],
            "mode_profile": ["single_player"],
        },
    )
    plain_peer = Game(
        title="Plain Peer",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_secondary_archetypes=["turn_based_tactics"],
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player"],
        },
    )

    assert _jrpg_story_rpg_lane_fit(anchor, creature_peer) is None
    assert _jrpg_story_rpg_lane_fit(anchor, plain_peer) is not None


def test_jrpg_story_rpg_lane_fit_filters_sandbox_and_coop_shooter_peers_for_console_party_anchor(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "app.services.game_similarity_v3.build_similarity_breakdown_v2",
        lambda *_args, **_kwargs: type("Breakdown", (), {"score": 300})(),
    )
    anchor = Game(
        title="Console JRPG Anchor",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player"],
        },
    )
    sandbox_peer = Game(
        title="Sandbox Peer",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree", "buildcraft"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player"],
            "world_density": ["systemic_sandbox"],
        },
    )
    coop_shooter_peer = Game(
        title="Co-op Shooter Peer",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management", "crowd_control"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player", "drop_in_coop", "party_coop"],
            "combat_style": ["shooter"],
        },
    )
    quest_only_peer = Game(
        title="Quest-only Peer",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["quest_driven"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player"],
        },
    )
    console_peer = Game(
        title="Console Peer",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player"],
        },
    )

    assert _jrpg_story_rpg_lane_fit(anchor, sandbox_peer) is None
    assert _jrpg_story_rpg_lane_fit(anchor, coop_shooter_peer) is None
    assert _jrpg_story_rpg_lane_fit(anchor, quest_only_peer) is None
    assert _jrpg_story_rpg_lane_fit(anchor, console_peer) is not None


def test_jrpg_story_rpg_lane_fit_prefers_quirky_puzzle_story_peers_over_broad_fantasy_jrpg(
    monkeypatch: pytest.MonkeyPatch,
):
    def _breakdown(_anchor, candidate):
        scores = {
            "Broad Fantasy Quest RPG": 520,
            "OMORI-like Peer": 330,
            "Bug Fables-like Peer": 335,
        }
        return type("Breakdown", (), {"score": scores.get(candidate.title, 300)})()

    monkeypatch.setattr("app.services.game_similarity_v3.build_similarity_breakdown_v2", _breakdown)
    anchor = Game(
        title="Stitched Together",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["dominant"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "challenge_model": ["puzzle_gating"],
            "mechanics_structure": ["environmental_puzzle_solving"],
            "narrative_topic": ["interpersonal_drama"],
            "tone": ["serious"],
            "mode_profile": ["single_player"],
        },
    )
    broad_fantasy = Game(
        title="Broad Fantasy Quest RPG",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["dominant"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree", "quest_driven"],
            "narrative_structure": ["authored_linear"],
            "rules_goals": ["complete_quests"],
            "traversal_verbs": ["horseback"],
            "setting": ["high_fantasy"],
            "mode_profile": ["single_player"],
        },
    )
    omori_like = Game(
        title="OMORI-like Peer",
        description=(
            "Explore a strange world full of colorful friends and foes, uncover a forgotten past, "
            "and determine your fate."
        ),
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["dominant"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "narrative_topic": ["interpersonal_drama"],
            "tone": ["serious"],
            "mode_profile": ["single_player"],
        },
    )
    bug_fables_like = Game(
        title="Bug Fables-like Peer",
        description="Three heroes explore the world while turn-based battles use action commands.",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["dominant"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "challenge_model": ["puzzle_gating"],
            "mechanics_structure": ["environmental_puzzle_solving"],
            "tone": ["whimsical"],
            "mode_profile": ["single_player"],
        },
    )

    fantasy_fit = _jrpg_story_rpg_lane_fit(anchor, broad_fantasy)
    omori_fit = _jrpg_story_rpg_lane_fit(anchor, omori_like)
    bug_fables_fit = _jrpg_story_rpg_lane_fit(anchor, bug_fables_like)

    assert omori_fit is not None
    assert bug_fables_fit is not None
    assert fantasy_fit is None


def test_jrpg_story_rpg_lane_fit_prefers_mobile_live_service_story_peers_over_monster_and_deck_spillover(
    monkeypatch: pytest.MonkeyPatch,
):
    def _breakdown(_anchor, candidate):
        scores = {
            "Monster Spillover": 430,
            "Deck Spillover": 420,
            "Another Eden-like Peer": 330,
            "Honkai-like Peer": 325,
        }
        return type("Breakdown", (), {"score": scores.get(candidate.title, 300)})()

    monkeypatch.setattr("app.services.game_similarity_v3.build_similarity_breakdown_v2", _breakdown)
    anchor = Game(
        title="Granblue Fantasy",
        description=(
            "Granblue Fantasy is a classic JRPG that first launched in Japan for mobile devices "
            "and web browsers. Join fellow skyfarers in real-time co-op raids with more than 70 "
            "distinctive characters."
        ),
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["dominant"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player", "pvp", "drop_in_coop"],
        },
    )
    another_eden = Game(
        title="Another Eden-like Peer",
        description="A modern yet classic RPG across space and time with a turn-based battle system.",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
        },
    )
    honkai = Game(
        title="Honkai-like Peer",
        description="Board the Astral Express, visit unique worlds with companions, and use strategic turn-based combat.",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "entity_interaction": ["party_control"],
        },
    )
    monster_spillover = Game(
        title="Monster Spillover",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management", "duel_focused"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["pvp"],
            "entity_interaction": ["creature_collection"],
            "mechanics_structure": ["creature_collection", "match_competition"],
        },
    )
    deck_spillover = Game(
        title="Deck Spillover",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["pvp"],
            "entity_interaction": ["card_play"],
            "mechanics_structure": ["deck_construction", "match_competition"],
        },
    )

    another_fit = _jrpg_story_rpg_lane_fit(anchor, another_eden)
    honkai_fit = _jrpg_story_rpg_lane_fit(anchor, honkai)
    monster_fit = _jrpg_story_rpg_lane_fit(anchor, monster_spillover)
    deck_fit = _jrpg_story_rpg_lane_fit(anchor, deck_spillover)

    assert another_fit is not None
    assert honkai_fit is not None
    assert monster_fit is None or another_fit > monster_fit
    assert deck_fit is None or honkai_fit > deck_fit


def _scored_neighbor(candidate: Game, score: float = 0.9) -> SimilarityV3ScoredNeighbor:
    return SimilarityV3ScoredNeighbor(
        candidate=candidate,
        final_score=score,
        taxonomy_score=score,
        text_vector_score=0.1,
        facet_vector_score=0.1,
        prototype_score=0.0,
        rerank_score=0.1,
        quality_prior=0.0,
        relationship_type="same",
        used_vector_exception=False,
        explanation_payload={},
    )


def test_apply_similarity_v3_gold_policy_blocks_must_avoid_and_boosts_expected(monkeypatch):
    import app.services.game_similarity_v3 as similarity_v3

    anchor = Game(title="Gold Anchor", public_id="anchor-1")
    expected = Game(id=2, title="Expected Neighbor")
    neutral = Game(id=3, title="Neutral Neighbor")
    blocked = Game(id=4, title="Blocked Neighbor")

    monkeypatch.setattr(
        similarity_v3,
        "_similarity_v3_gold_policy_for_anchor",
        lambda _anchor: {
            "expected": {similarity_v3._title_key("Expected Neighbor")},
            "expected_public_ids": set(),
            "blocked": {similarity_v3._title_key("Blocked Neighbor")},
        },
    )

    adjusted = _apply_similarity_v3_gold_policy(
        anchor,
        [
            _scored_neighbor(blocked, 0.99),
            _scored_neighbor(neutral, 0.90),
            _scored_neighbor(expected, 0.80),
        ],
    )

    assert [item.candidate.title for item in adjusted] == ["Expected Neighbor", "Neutral Neighbor"]
    assert adjusted[0].final_score > adjusted[1].final_score
    assert adjusted[0].explanation_payload["gold_corpus_expected_neighbor"] is True


def test_select_similarity_v3_neighbors_pins_gold_expected_before_lane_fillers():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Street Soccer",
        taxonomy_v2_primary_archetype="sports_sim",
        taxonomy_v2_fingerprint={"sports_theme": ["soccer"], "mode_profile": ["single_player"]},
    )
    generic_soccer = Game(
        id=2,
        title="Generic Soccer Sim",
        taxonomy_v2_primary_archetype="sports_sim",
        taxonomy_v2_fingerprint={"sports_theme": ["soccer"], "mode_profile": ["single_player"]},
    )
    gold_arcade = Game(
        id=3,
        title="Street Power Football",
        taxonomy_v2_primary_archetype="arcade_sports",
        taxonomy_v2_fingerprint={"sports_theme": ["soccer"], "mode_profile": ["single_player"]},
    )

    gold_item = _scored_neighbor(gold_arcade, 0.75)
    gold_item.explanation_payload["gold_corpus_expected_neighbor"] = True
    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(generic_soccer, 0.95),
            gold_item,
        ],
        limit=1,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == ["Street Power Football"]


def test_select_similarity_v3_neighbors_prefers_crimson_family_lanes():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Crimson Desert",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["horseback", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "entity_interaction": ["construction_placement"],
            "rules_goals": ["build_and_optimize"],
            "progression_model": ["base_growth", "quest_driven"],
        },
    )
    totk = Game(
        id=2,
        title="TOTK",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["climbing", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "rules_goals": ["complete_quests", "defeat_bosses"],
        },
    )
    witcher = Game(
        id=3,
        title="Witcher 3",
        taxonomy_v2_primary_archetype="western_narrative_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "setting": ["high_fantasy", "mythic"],
            "rules_goals": ["complete_quests"],
            "entity_interaction": ["dialogue_choice"],
            "progression_model": ["quest_driven"],
        },
    )
    elden = Game(
        id=4,
        title="Elden Ring",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "setting": ["high_fantasy", "mythic"],
            "rules_goals": ["defeat_bosses"],
            "combat_style": ["melee"],
            "combat_structure": ["boss_centric"],
            "challenge_model": ["soulslike"],
        },
    )
    black_desert = Game(
        id=5,
        title="Black Desert Online",
        taxonomy_v2_primary_archetype="mmo_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world", "persistent_shared_world"],
            "perspective": ["third_person"],
            "setting": ["high_fantasy", "mythic"],
            "rules_goals": ["build_and_optimize"],
            "entity_interaction": ["construction_placement"],
            "progression_model": ["base_growth"],
            "combat_style": ["melee"],
            "traversal_verbs": ["horseback"],
        },
    )
    god_of_war = Game(
        id=6,
        title="God of War",
        taxonomy_v2_primary_archetype="cinematic_action_adventure",
        taxonomy_v2_fingerprint={
            "world_topology": ["semi_open"],
            "perspective": ["third_person"],
            "setting": ["mythic"],
            "rules_goals": ["defeat_bosses", "complete_quests"],
            "combat_style": ["melee"],
            "progression_model": ["buildcraft"],
        },
    )
    indiana = Game(
        id=7,
        title="Indiana Jones",
        taxonomy_v2_primary_archetype="open_world_action_adventure",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["first_person"],
            "setting": ["historical"],
        },
    )
    gloomhaven_like = Game(
        id=8,
        title="Gloomhaven",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "setting": ["high_fantasy", "mythic"],
            "combat_structure": ["party_management"],
            "rules_goals": ["complete_quests"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(god_of_war, 0.95),
            _scored_neighbor(indiana, 0.94),
            _scored_neighbor(gloomhaven_like, 0.935),
            _scored_neighbor(totk, 0.93),
            _scored_neighbor(witcher, 0.92),
            _scored_neighbor(elden, 0.91),
            _scored_neighbor(black_desert, 0.90),
        ],
        limit=5,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == [
        "TOTK",
        "Witcher 3",
        "Elden Ring",
        "Black Desert Online",
    ]


def test_select_similarity_v3_neighbors_prefers_totk_family_lanes():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="The Legend of Zelda: Tears of the Kingdom",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["climbing", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )
    botw = Game(
        id=11,
        title="The Legend of Zelda: Breath of the Wild",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["climbing", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "rules_goals": ["complete_quests", "defeat_bosses"],
        },
    )
    crimson = Game(
        id=12,
        title="Crimson Desert",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["horseback", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "rules_goals": ["defeat_bosses", "complete_quests"],
        },
    )
    god_of_war = Game(
        id=13,
        title="God of War",
        taxonomy_v2_primary_archetype="cinematic_action_adventure",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "setting": ["mythic"],
            "rules_goals": ["defeat_bosses", "complete_quests"],
            "combat_style": ["melee"],
            "progression_model": ["buildcraft"],
        },
    )
    elden = Game(
        id=14,
        title="Elden Ring",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "setting": ["high_fantasy", "mythic"],
            "rules_goals": ["defeat_bosses"],
            "combat_style": ["melee"],
            "combat_structure": ["boss_centric"],
            "challenge_model": ["soulslike"],
        },
    )
    witcher = Game(
        id=15,
        title="Witcher 3",
        taxonomy_v2_primary_archetype="western_narrative_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "setting": ["high_fantasy", "mythic"],
            "rules_goals": ["complete_quests"],
            "entity_interaction": ["dialogue_choice"],
            "progression_model": ["quest_driven"],
        },
    )
    jett = Game(
        id=16,
        title="JETT",
        taxonomy_v2_primary_archetype="open_world_action_adventure",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "setting": ["sci_fi"],
        },
    )
    dq = Game(
        id=17,
        title="Dragon Quest Treasures",
        taxonomy_v2_primary_archetype="monster_collect_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "setting": ["high_fantasy"],
        },
    )
    mafia = Game(
        id=18,
        title="Mafia: The Old Country",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "setting": ["mythic"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(jett, 0.96),
            _scored_neighbor(dq, 0.95),
            _scored_neighbor(mafia, 0.945),
            _scored_neighbor(botw, 0.94),
            _scored_neighbor(crimson, 0.93),
            _scored_neighbor(god_of_war, 0.92),
            _scored_neighbor(elden, 0.91),
            _scored_neighbor(witcher, 0.90),
        ],
        limit=5,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == [
        "The Legend of Zelda: Breath of the Wild",
        "Crimson Desert",
        "God of War",
        "Elden Ring",
        "Witcher 3",
    ]


def test_select_similarity_v3_neighbors_is_structure_driven_not_title_driven():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Skybound Kingdom",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["climbing", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
        },
    )
    open_air_peer = Game(
        id=21,
        title="Wild Frontier",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "traversal_verbs": ["climbing", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "rules_goals": ["complete_quests", "defeat_bosses"],
        },
    )
    cinematic_peer = Game(
        id=22,
        title="Saga of the Wolf",
        taxonomy_v2_primary_archetype="cinematic_action_adventure",
        taxonomy_v2_fingerprint={
            "world_topology": ["semi_open"],
            "perspective": ["third_person"],
            "setting": ["mythic"],
            "rules_goals": ["defeat_bosses", "complete_quests"],
            "combat_style": ["melee"],
            "progression_model": ["buildcraft"],
        },
    )
    soulslike_peer = Game(
        id=23,
        title="Ashen Crown",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "setting": ["high_fantasy", "mythic"],
            "rules_goals": ["defeat_bosses"],
            "combat_style": ["melee"],
            "combat_structure": ["boss_centric"],
            "challenge_model": ["soulslike"],
        },
    )
    western_peer = Game(
        id=24,
        title="King's Road Chronicles",
        taxonomy_v2_primary_archetype="western_narrative_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "setting": ["high_fantasy", "mythic"],
            "rules_goals": ["complete_quests"],
            "entity_interaction": ["dialogue_choice"],
            "progression_model": ["quest_driven"],
        },
    )
    weak_false_positive = Game(
        id=25,
        title="Mythic Crime Story",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "setting": ["mythic"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(weak_false_positive, 0.98),
            _scored_neighbor(open_air_peer, 0.94),
            _scored_neighbor(cinematic_peer, 0.93),
            _scored_neighbor(soulslike_peer, 0.92),
            _scored_neighbor(western_peer, 0.91),
        ],
        limit=5,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == [
        "Wild Frontier",
        "Saga of the Wolf",
        "Ashen Crown",
        "King's Road Chronicles",
    ]


def test_select_similarity_v3_neighbors_prefers_third_person_soulslike_peers():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Elden-Like Anchor",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_structure": ["boss_centric"],
            "challenge_model": ["soulslike"],
            "rules_goals": ["defeat_bosses"],
            "setting": ["dark_fantasy", "mythic"],
        },
    )
    dark_souls = Game(
        id=31,
        title="Dark Souls Peer",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "combat_structure": ["boss_centric"],
            "challenge_model": ["soulslike"],
            "rules_goals": ["defeat_bosses"],
            "setting": ["dark_fantasy"],
        },
    )
    bloodborne = Game(
        id=32,
        title="Bloodborne Peer",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "combat_structure": ["boss_centric"],
            "challenge_model": ["soulslike"],
            "rules_goals": ["defeat_bosses"],
            "setting": ["dark_fantasy", "horror"],
        },
    )
    sekiro = Game(
        id=33,
        title="Sekiro Peer",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "combat_structure": ["boss_centric"],
            "challenge_model": ["soulslike"],
            "rules_goals": ["defeat_bosses"],
            "setting": ["mythic"],
        },
    )
    juxtia_like = Game(
        id=34,
        title="2D Soulslike False Positive",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "combat_structure": ["boss_centric"],
            "challenge_model": ["soulslike"],
            "rules_goals": ["defeat_bosses"],
            "setting": ["dark_fantasy", "mythic"],
            "visual_presentation": ["side_scrolling_2d"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(juxtia_like, 0.99),
            _scored_neighbor(dark_souls, 0.94),
            _scored_neighbor(bloodborne, 0.90),
            _scored_neighbor(sekiro, 0.89),
        ],
        limit=3,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == [
        "Dark Souls Peer",
        "Bloodborne Peer",
        "Sekiro Peer",
    ]


def test_select_similarity_v3_neighbors_prefers_organization_puzzle_peers_for_hidden_object_anchor():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Packing Life",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="hidden_object_puzzle",
        taxonomy_v2_fingerprint={
            "challenge_model": ["puzzle_gating", "sim_realism"],
            "combat_presence": ["none"],
            "mode_profile": ["single_player"],
            "rules_goals": ["build_and_optimize"],
            "mechanics_structure": ["environmental_puzzle_solving", "systemic_problem_solving"],
            "entity_interaction": ["cursor_driven_interaction", "inventory_loot"],
            "interface_control": ["cursor_driven"],
        },
    )
    wilmot = Game(
        id=41,
        title="Wilmot's Warehouse",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="hidden_object_puzzle",
        taxonomy_v2_fingerprint={
            "challenge_model": ["puzzle_gating"],
            "combat_presence": ["none"],
            "mode_profile": ["single_player"],
            "rules_goals": ["build_and_optimize"],
            "mechanics_structure": ["environmental_puzzle_solving", "systemic_problem_solving"],
            "entity_interaction": ["cursor_driven_interaction", "inventory_loot"],
            "interface_control": ["cursor_driven"],
        },
    )
    unpacking = Game(
        id=42,
        title="Unpacking",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="hidden_object_puzzle",
        taxonomy_v2_fingerprint={
            "challenge_model": ["puzzle_gating", "sim_realism"],
            "combat_presence": ["none"],
            "mode_profile": ["single_player"],
            "rules_goals": ["build_and_optimize"],
            "mechanics_structure": ["environmental_puzzle_solving"],
            "entity_interaction": ["cursor_driven_interaction", "inventory_loot"],
            "interface_control": ["cursor_driven"],
        },
    )
    little_to_left = Game(
        id=43,
        title="A Little to the Left",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="hidden_object_puzzle",
        taxonomy_v2_fingerprint={
            "challenge_model": ["puzzle_gating"],
            "combat_presence": ["none"],
            "mode_profile": ["single_player"],
            "rules_goals": ["build_and_optimize"],
            "mechanics_structure": ["environmental_puzzle_solving"],
            "entity_interaction": ["cursor_driven_interaction"],
            "interface_control": ["cursor_driven"],
        },
    )
    dreaming_diorama = Game(
        id=44,
        title="Dreaming Diorama",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="hidden_object_puzzle",
        taxonomy_v2_fingerprint={
            "challenge_model": ["puzzle_gating"],
            "combat_presence": ["none"],
            "mode_profile": ["single_player"],
            "rules_goals": ["solve_mysteries"],
            "narrative_topic": ["detective_mystery"],
        },
    )
    eyes = Game(
        id=45,
        title="Eyes That Hypnotise",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="hidden_object_puzzle",
        taxonomy_v2_fingerprint={
            "challenge_model": ["puzzle_gating"],
            "combat_presence": ["none"],
            "mode_profile": ["single_player"],
            "rules_goals": ["solve_mysteries"],
            "narrative_topic": ["psychological_horror"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(dreaming_diorama, 0.99),
            _scored_neighbor(eyes, 0.98),
            _scored_neighbor(unpacking, 0.95),
            _scored_neighbor(little_to_left, 0.94),
            _scored_neighbor(wilmot, 0.93),
        ],
        limit=3,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == [
        "Wilmot's Warehouse",
        "Unpacking",
        "A Little to the Left",
    ]


def test_select_similarity_v3_neighbors_reserves_psychological_horror_bridge_for_action_horror_anchor():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
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
            "session_shape": ["campaign"],
        },
    )
    little_hope = Game(
        id=46,
        title="Little Hope",
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
    dementium = Game(
        id=47,
        title="Dementium: The Ward",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="action_horror",
        taxonomy_v2_fingerprint={
            "tone": ["grotesque"],
            "setting": ["horror"],
            "perspective": ["third_person"],
            "mode_profile": ["single_player"],
            "narrative_topic": ["survival_escape"],
        },
    )
    the_medium = Game(
        id=48,
        title="The Medium",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="psychological_horror",
        taxonomy_v2_fingerprint={
            "tone": ["bleak", "melancholic"],
            "setting": ["horror"],
            "perspective": ["third_person"],
            "mode_profile": ["single_player"],
            "session_shape": ["campaign"],
            "narrative_topic": ["survival_escape", "detective_mystery"],
            "keyword_layer": ["psychological_horror"],
        },
    )
    resident_evil = Game(
        id=49,
        title="Resident Evil 7",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="survival_horror",
        taxonomy_v2_fingerprint={
            "tone": ["bleak", "grotesque"],
            "setting": ["horror"],
            "perspective": ["first_person", "third_person"],
            "mode_profile": ["single_player"],
            "session_shape": ["campaign"],
            "narrative_topic": ["survival_escape"],
            "combat_style": ["survival"],
        },
    )
    evil_west = Game(
        id=50,
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

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(evil_west, 0.99),
            _scored_neighbor(little_hope, 0.96),
            _scored_neighbor(dementium, 0.95),
            _scored_neighbor(resident_evil, 0.94),
            _scored_neighbor(the_medium, 0.90),
        ],
        limit=4,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == [
        "Little Hope",
        "Dementium: The Ward",
        "The Medium",
        "Resident Evil 7",
    ]


def test_select_similarity_v3_neighbors_prefers_co_op_horror_peers_for_horde_anchor():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
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
    back_4_blood = Game(
        id=55,
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
    world_war_z = Game(
        id=56,
        title="World War Z",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="co_op_horror",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["dominant"],
            "combat_style": ["shooter"],
            "combat_structure": ["crowd_control", "encounter_driven"],
            "setting": ["horror"],
            "mode_profile": ["drop_in_coop", "party_coop", "single_player"],
        },
    )
    sker_ritual = Game(
        id=57,
        title="Sker Ritual",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="action_horror",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "perspective": ["first_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["shooter"],
            "combat_structure": ["encounter_driven"],
            "setting": ["horror"],
            "mode_profile": ["drop_in_coop", "single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(sker_ritual, 0.99),
            _scored_neighbor(back_4_blood, 0.97),
            _scored_neighbor(world_war_z, 0.96),
        ],
        limit=3,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == [
        "Back 4 Blood",
        "World War Z",
    ]


def test_select_similarity_v3_neighbors_prefers_kingdom_decision_sim_series_peers():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Reigns: The Witcher",
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
            "setting": ["high_fantasy", "dark_fantasy"],
            "mode_profile": ["single_player"],
        },
    )
    reigns = Game(
        id=70,
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
    her_majesty = Game(
        id=71,
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
    unrelated = Game(
        id=72,
        title="Darkest Dungeon",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="turn_based_tactics",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["dominant"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "challenge_model": ["tactical_optimization"],
            "mode_profile": ["single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(unrelated, 0.99),
            _scored_neighbor(her_majesty, 0.95),
            _scored_neighbor(reigns, 0.94),
        ],
        limit=2,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == ["Reigns: Her Majesty", "Reigns"]


def test_select_similarity_v3_neighbors_treats_jrpg_secondaries_as_same_lane_candidates():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Fortuna Magus",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player"],
        },
    )
    ara_fell = Game(
        id=73,
        title="Ara Fell: Enhanced Edition",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="exploration_survival_adventure",
        taxonomy_v2_secondary_archetypes=["jrpg_story_rpg", "monster_collect_rpg"],
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["dominant"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management", "boss_centric"],
            "progression_model": ["skill_tree", "quest_driven"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player"],
        },
    )
    chained_echoes = Game(
        id=74,
        title="Chained Echoes",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["dominant"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player"],
        },
    )
    unrelated = Game(
        id=75,
        title="Deathtrap",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="loot_action_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft", "gear_chase"],
            "mode_profile": ["single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(unrelated, 0.99),
            _scored_neighbor(ara_fell, 0.95),
            _scored_neighbor(chained_echoes, 0.94),
        ],
        limit=2,
        profile=profile,
    )

    assert {item.candidate.title for item in selected} == {"Ara Fell: Enhanced Edition", "Chained Echoes"}


def test_select_similarity_v3_neighbors_reserves_console_jrpg_slots_for_core_peers():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Fortuna Magus",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["dominant"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player"],
        },
    )
    beast_breaker = Game(
        id=760,
        title="Beast Breaker",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["dominant"],
            "combat_style": ["party_tactics"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["quest_driven", "skill_tree"],
            "narrative_structure": ["authored_linear"],
            "entity_interaction": ["party_control"],
            "mechanics_structure": ["party_management_loop"],
            "mode_profile": ["single_player"],
        },
    )
    chained_echoes = Game(
        id=761,
        title="Chained Echoes",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["dominant"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player"],
        },
    )
    rise = Game(
        id=762,
        title="Rise of the Third Power",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(beast_breaker, 0.99),
            _scored_neighbor(chained_echoes, 0.92),
            _scored_neighbor(rise, 0.91),
        ],
        limit=2,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == ["Chained Echoes", "Rise of the Third Power"]


def test_select_similarity_v3_neighbors_prefers_cozy_growth_peers_for_farming_sim_anchor():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Collector's Cove",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="farming_sim",
        taxonomy_v2_fingerprint={
            "tone": ["cozy"],
            "challenge_model": ["sim_realism"],
            "combat_presence": ["none"],
            "mode_profile": ["single_player"],
            "progression_model": ["base_growth"],
            "rules_goals": ["build_and_optimize"],
        },
    )
    summer_in_mara = Game(
        id=60,
        title="Summer in Mara",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="farming_sim",
        taxonomy_v2_fingerprint={
            "tone": ["cozy"],
            "challenge_model": ["sim_realism"],
            "combat_presence": ["none"],
            "mode_profile": ["single_player"],
            "progression_model": ["base_growth"],
            "rules_goals": ["build_and_optimize"],
        },
    )
    stardew = Game(
        id=61,
        title="Stardew Valley",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="farming_sim",
        taxonomy_v2_fingerprint={
            "tone": ["cozy"],
            "challenge_model": ["sim_realism"],
            "combat_presence": ["none"],
            "mode_profile": ["single_player", "drop_in_coop"],
            "progression_model": ["base_growth", "relationship_social"],
            "rules_goals": ["build_and_optimize"],
        },
    )
    moonglow = Game(
        id=62,
        title="Moonglow Bay",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="farming_sim",
        taxonomy_v2_fingerprint={
            "tone": ["cozy"],
            "challenge_model": ["sim_realism"],
            "combat_presence": ["none"],
            "mode_profile": ["single_player"],
            "progression_model": ["base_growth"],
            "rules_goals": ["build_and_optimize"],
        },
    )
    aquarium = Game(
        id=63,
        title="Tiny Aquarium",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="farming_sim",
        taxonomy_v2_fingerprint={
            "challenge_model": ["sim_realism"],
            "combat_presence": ["none"],
            "mode_profile": ["single_player"],
        },
    )
    aviary = Game(
        id=64,
        title="Little Aviary",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="farming_sim",
        taxonomy_v2_fingerprint={
            "challenge_model": ["sim_realism"],
            "combat_presence": ["none"],
            "mode_profile": ["single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(aquarium, 0.99),
            _scored_neighbor(aviary, 0.98),
            _scored_neighbor(moonglow, 0.95),
            _scored_neighbor(stardew, 0.94),
            _scored_neighbor(summer_in_mara, 0.93),
        ],
        limit=3,
        profile=profile,
    )

    assert {item.candidate.title for item in selected} == {
        "Stardew Valley",
        "Summer in Mara",
        "Moonglow Bay",
    }


def test_select_similarity_v3_neighbors_prefers_parkour_collectathon_peers_for_parkour_anchor():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Parkour Labs",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="3d_collectathon",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "mode_profile": ["party_coop", "pvp", "single_player"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["parkour", "platforming"],
            "visual_presentation": ["third_person_3d"],
        },
    )
    cyber_hook = Game(
        id=65,
        title="Cyber Hook",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="3d_collectathon",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["parkour", "platforming"],
            "visual_presentation": ["third_person_3d"],
        },
    )
    toss = Game(
        id=66,
        title="TOSS!",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="3d_collectathon",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["parkour", "platforming"],
            "visual_presentation": ["third_person_3d"],
        },
    )
    shady_knight = Game(
        id=67,
        title="Shady Knight",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="3d_collectathon",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["parkour", "platforming"],
            "visual_presentation": ["third_person_3d"],
        },
    )
    sonic = Game(
        id=68,
        title="Sonic Colors: Ultimate",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="3d_collectathon",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["platforming"],
            "visual_presentation": ["third_person_3d"],
        },
    )
    snow_bros = Game(
        id=69,
        title="Snow Bros. Wonderland",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="3d_collectathon",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["platforming"],
            "visual_presentation": ["third_person_3d"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(sonic, 0.99),
            _scored_neighbor(snow_bros, 0.98),
            _scored_neighbor(shady_knight, 0.95),
            _scored_neighbor(toss, 0.94),
            _scored_neighbor(cyber_hook, 0.93),
        ],
        limit=3,
        profile=profile,
    )

    assert {item.candidate.title for item in selected} == {
        "Shady Knight",
        "TOSS!",
        "Cyber Hook",
    }


def test_select_similarity_v3_neighbors_prefers_same_lane_metroidvania_peers_over_higher_scored_false_bridges():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Adventurous Slime",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based", "semi_open"],
            "traversal_verbs": ["platforming", "double_jump"],
            "progression_model": ["metaprogression"],
            "visual_presentation": ["side_scrolling_2d"],
        },
    )
    islets = Game(
        id=51,
        title="Islets",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["semi_open"],
            "traversal_verbs": ["platforming", "gliding"],
            "progression_model": ["metaprogression"],
            "visual_presentation": ["side_scrolling_2d"],
        },
    )
    haiku = Game(
        id=52,
        title="Haiku, the Robot",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based", "semi_open"],
            "traversal_verbs": ["platforming", "double_jump"],
            "progression_model": ["metaprogression"],
            "visual_presentation": ["side_scrolling_2d"],
        },
    )
    ori = Game(
        id=53,
        title="Ori and the Blind Forest",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based", "semi_open"],
            "traversal_verbs": ["platforming", "double_jump"],
            "progression_model": ["metaprogression"],
            "visual_presentation": ["side_scrolling_2d"],
        },
    )
    neon_runner = Game(
        id=54,
        title="Neon Runner",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="action_platformer",
        taxonomy_v2_fingerprint={
            "perspective": ["first_person"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["parkour", "platforming"],
            "visual_presentation": ["first_person_3d"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(neon_runner, 0.99),
            _scored_neighbor(ori, 0.95),
            _scored_neighbor(haiku, 0.94),
            _scored_neighbor(islets, 0.93),
        ],
        limit=3,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == [
        "Ori and the Blind Forest",
        "Haiku, the Robot",
        "Islets",
    ]


def test_select_similarity_v3_neighbors_treats_collectathon_secondaries_as_same_lane_candidates():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Parkour Labs",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="3d_collectathon",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["parkour", "platforming"],
            "visual_presentation": ["third_person_3d"],
        },
    )
    same_lane_secondary = Game(
        id=71,
        title="Rooftops Secondary",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="sports_sim",
        taxonomy_v2_secondary_archetypes=["3d_collectathon", "action_platformer"],
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["parkour", "platforming"],
            "visual_presentation": ["third_person_3d"],
        },
    )
    pure_same_lane = Game(
        id=72,
        title="Cyber Hook",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="3d_collectathon",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["parkour", "platforming"],
            "visual_presentation": ["third_person_3d"],
        },
    )
    false_bridge = Game(
        id=73,
        title="Sports Noise",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="sports_sim",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["parkour", "platforming"],
            "visual_presentation": ["third_person_3d"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(false_bridge, 0.99),
            _scored_neighbor(pure_same_lane, 0.95),
            _scored_neighbor(same_lane_secondary, 0.94),
        ],
        limit=2,
        profile=profile,
    )

    assert {item.candidate.title for item in selected} == {
        "Cyber Hook",
        "Rooftops Secondary",
    }


def test_select_similarity_v3_neighbors_blocks_2d_action_platformer_bridge_for_third_person_collectathon():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Mr. Sleepy Man",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="3d_collectathon",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "world_topology": ["level_based", "semi_open"],
            "traversal_verbs": ["gliding", "platforming"],
            "mode_profile": ["single_player"],
        },
    )
    mario = Game(
        id=751,
        title="Super Mario Odyssey",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="3d_collectathon",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "visual_presentation": ["third_person_3d"],
            "world_topology": ["level_based", "semi_open"],
            "traversal_verbs": ["platforming"],
            "mode_profile": ["single_player"],
        },
    )
    a_hat = Game(
        id=752,
        title="A Hat in Time",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="3d_collectathon",
        taxonomy_v2_fingerprint={
            "perspective": ["third_person"],
            "visual_presentation": ["third_person_3d"],
            "world_topology": ["level_based", "semi_open"],
            "traversal_verbs": ["platforming"],
            "mode_profile": ["single_player"],
        },
    )
    side_scroller = Game(
        id=753,
        title="Bō: Path of the Teal Lotus",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="action_platformer",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "visual_presentation": ["side_scrolling_2d"],
            "world_topology": ["level_based", "semi_open"],
            "traversal_verbs": ["gliding", "platforming"],
            "mode_profile": ["single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(side_scroller, 0.99),
            _scored_neighbor(mario, 0.94),
            _scored_neighbor(a_hat, 0.93),
        ],
        limit=3,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == [
        "Super Mario Odyssey",
        "A Hat in Time",
    ]


def test_select_similarity_v3_neighbors_prefers_explicit_platform_fighters():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Royal Vermin",
        description="A chaotic local platform fighter where players knock opponents out of arenas.",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="traditional_fighter",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["platforming"],
            "combat_presence": ["dominant"],
            "combat_structure": ["duel_focused"],
            "mode_profile": ["party_coop", "pvp"],
            "mechanics_structure": ["match_competition"],
            "rules_goals": ["win_matches"],
        },
    )
    smash = Game(
        id=761,
        title="Super Smash Bros. Ultimate",
        description="Legendary fighters collide in a platform fighting showdown.",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="traditional_fighter",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["platforming"],
            "combat_presence": ["dominant"],
            "combat_structure": ["duel_focused"],
            "mode_profile": ["party_coop", "pvp"],
            "mechanics_structure": ["match_competition"],
            "rules_goals": ["win_matches"],
        },
    )
    brawlhalla = Game(
        id=762,
        title="Brawlhalla",
        description="A 2D platform fighting game with local and online multiplayer.",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="traditional_fighter",
        taxonomy_v2_fingerprint=smash.taxonomy_v2_fingerprint,
    )
    platform_noise = Game(
        id=763,
        title="Sonic Mania",
        description="A fast side-scrolling platform adventure.",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="traditional_fighter",
        taxonomy_v2_fingerprint=smash.taxonomy_v2_fingerprint,
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(platform_noise, 0.99),
            _scored_neighbor(smash, 0.94),
            _scored_neighbor(brawlhalla, 0.93),
        ],
        limit=3,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == [
        "Super Smash Bros. Ultimate",
        "Brawlhalla",
    ]


def test_select_similarity_v3_neighbors_keeps_baseball_sports_sim_on_baseball_lane():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="eBaseball: PRO SPIRIT",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="sports_sim",
        taxonomy_v2_fingerprint={
            "session_shape": ["match_session"],
            "mode_profile": ["single_player", "pvp"],
            "sports_theme": ["baseball"],
            "mechanics_structure": ["match_competition"],
            "rules_goals": ["win_matches"],
        },
    )
    mlb = Game(
        id=771,
        title="MLB The Show 24",
        description="Swing for the fences and live out your baseball dreams.",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="sports_sim",
        taxonomy_v2_fingerprint={
            "session_shape": ["match_session"],
            "mode_profile": ["single_player"],
            "sports_theme": ["baseball"],
            "mechanics_structure": ["match_competition"],
            "rules_goals": ["win_matches"],
        },
    )
    super_mega = Game(
        id=772,
        title="Super Mega Baseball 4",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="sports_sim",
        taxonomy_v2_fingerprint=mlb.taxonomy_v2_fingerprint,
    )
    surf = Game(
        id=773,
        title="Surf World Series",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="sports_sim",
        taxonomy_v2_fingerprint={
            "session_shape": ["match_session"],
            "mode_profile": ["single_player"],
            "mechanics_structure": ["match_competition"],
            "rules_goals": ["win_matches"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(surf, 0.99),
            _scored_neighbor(mlb, 0.94),
            _scored_neighbor(super_mega, 0.93),
        ],
        limit=3,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == [
        "MLB The Show 24",
        "Super Mega Baseball 4",
    ]


def test_select_similarity_v3_neighbors_prefers_horror_action_platformer_peers_for_horror_anchor():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Haunted Lands",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="action_platformer",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["platforming"],
            "combat_presence": ["dominant"],
            "combat_structure": ["encounter_driven"],
            "setting": ["horror"],
            "tone": ["bleak", "grotesque"],
            "art_style": ["retro"],
            "mode_profile": ["single_player"],
        },
    )
    bloodstained = Game(
        id=74,
        title="Bloodstained: Curse of the Moon 2",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="action_platformer",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["platforming"],
            "combat_presence": ["dominant"],
            "combat_structure": ["encounter_driven"],
            "setting": ["horror"],
            "tone": ["bleak"],
            "art_style": ["retro"],
            "mode_profile": ["single_player"],
        },
    )
    valfaris = Game(
        id=75,
        title="Valfaris",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="action_platformer",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["platforming"],
            "combat_presence": ["dominant"],
            "combat_structure": ["encounter_driven"],
            "tone": ["bleak"],
            "art_style": ["retro"],
            "mode_profile": ["single_player"],
        },
    )
    generic = Game(
        id=76,
        title="Color Runner",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="action_platformer",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["platforming"],
            "combat_presence": ["dominant"],
            "combat_structure": ["encounter_driven"],
            "tone": ["heroic"],
            "mode_profile": ["single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(generic, 0.99),
            _scored_neighbor(valfaris, 0.95),
            _scored_neighbor(bloodstained, 0.94),
        ],
        limit=2,
        profile=profile,
    )

    assert {item.candidate.title for item in selected} == {
        "Bloodstained: Curse of the Moon 2",
        "Valfaris",
    }


def test_select_similarity_v3_neighbors_prefers_restaurant_management_peers_for_restaurant_tycoon_anchor():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Pizza Slice",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="management_tycoon",
        taxonomy_v2_fingerprint={
            "world_density": ["systemic_sandbox"],
            "session_shape": ["sandbox_loop"],
            "combat_presence": ["none"],
            "progression_model": ["base_growth"],
            "challenge_model": ["sim_realism", "tactical_optimization"],
            "rules_goals": ["build_and_optimize"],
            "keyword_layer": ["restaurant_management"],
            "mode_profile": ["single_player"],
        },
    )
    generic_sim = Game(
        id=71,
        title="Generic Tycoon",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="management_tycoon",
        taxonomy_v2_fingerprint={
            "world_density": ["systemic_sandbox"],
            "session_shape": ["sandbox_loop"],
            "combat_presence": ["none"],
            "progression_model": ["base_growth"],
            "challenge_model": ["sim_realism"],
            "rules_goals": ["build_and_optimize"],
            "mode_profile": ["single_player"],
        },
    )
    restaurant_peer = Game(
        id=72,
        title="Restaurant Peer",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="management_tycoon",
        taxonomy_v2_fingerprint={
            "world_density": ["systemic_sandbox"],
            "session_shape": ["sandbox_loop"],
            "combat_presence": ["none"],
            "progression_model": ["base_growth"],
            "challenge_model": ["sim_realism", "tactical_optimization"],
            "rules_goals": ["build_and_optimize"],
            "keyword_layer": ["restaurant_management"],
            "mode_profile": ["single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(generic_sim, 0.98),
            _scored_neighbor(restaurant_peer, 0.93),
        ],
        limit=1,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == ["Restaurant Peer"]


def test_select_similarity_v3_neighbors_rejects_non_combat_jrpg_impostor_for_party_rpg_anchor():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Fortuna Magus",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["dominant"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "setting": ["high_fantasy"],
            "mode_profile": ["single_player"],
        },
    )
    impostor = Game(
        id=73,
        title="Discounty",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign", "sandbox_loop"],
            "combat_presence": ["none"],
            "progression_model": ["base_growth"],
            "narrative_structure": ["authored_linear"],
            "mode_profile": ["single_player"],
        },
    )
    real_peer = Game(
        id=74,
        title="Chained Echoes",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["dominant"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["skill_tree"],
            "narrative_structure": ["authored_linear"],
            "setting": ["high_fantasy"],
            "mode_profile": ["single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(impostor, 0.99),
            _scored_neighbor(real_peer, 0.92),
        ],
        limit=1,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == ["Chained Echoes"]


def test_select_similarity_v3_neighbors_prefers_detective_visual_novel_peers_for_mystery_anchor():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Path of Mystery",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="visual_novel",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["none"],
            "challenge_model": ["puzzle_gating"],
            "interface_control": ["cursor_driven"],
            "narrative_structure": ["authored_linear"],
            "narrative_topic": ["detective_mystery"],
            "rules_goals": ["solve_mysteries"],
            "mode_profile": ["single_player"],
        },
    )
    romance_vn = Game(
        id=75,
        title="Holiday Hearts",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="visual_novel",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["none"],
            "interface_control": ["cursor_driven"],
            "narrative_structure": ["authored_branching"],
            "narrative_topic": ["interpersonal_drama"],
            "mode_profile": ["single_player"],
        },
    )
    detective_vn = Game(
        id=76,
        title="Paranormasight",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="visual_novel",
        taxonomy_v2_fingerprint={
            "session_shape": ["campaign"],
            "combat_presence": ["none"],
            "challenge_model": ["puzzle_gating"],
            "interface_control": ["cursor_driven"],
            "narrative_structure": ["authored_linear"],
            "narrative_topic": ["detective_mystery"],
            "rules_goals": ["solve_mysteries"],
            "mode_profile": ["single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(romance_vn, 0.99),
            _scored_neighbor(detective_vn, 0.92),
        ],
        limit=1,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == ["Paranormasight"]


def test_select_similarity_v3_neighbors_treats_metroidvania_secondary_candidates_as_same_lane_slots():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Compact Explorer",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based", "semi_open"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
            "visual_presentation": ["side_scrolling_2d"],
        },
    )
    stale_same_lane = Game(
        id=61,
        title="Haiku-Like Secondary",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="action_platformer",
        taxonomy_v2_secondary_archetypes=["metroidvania", "precision_platformer"],
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based", "semi_open"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
            "visual_presentation": ["side_scrolling_2d"],
        },
    )
    same_lane = Game(
        id=62,
        title="Pure Metroidvania",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based", "semi_open"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
            "visual_presentation": ["side_scrolling_2d"],
        },
    )
    bridge = Game(
        id=63,
        title="Generic Bridge",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="action_platformer",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based"],
            "traversal_verbs": ["platforming"],
            "visual_presentation": ["side_scrolling_2d"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(bridge, 0.99),
            _scored_neighbor(stale_same_lane, 0.94),
            _scored_neighbor(same_lane, 0.93),
        ],
        limit=2,
        profile=profile,
    )

    assert {item.candidate.title for item in selected} == {
        "Haiku-Like Secondary",
        "Pure Metroidvania",
    }


def test_select_similarity_v3_neighbors_prefers_metroidvania_peers_with_shared_handcrafted_discovery_density():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Compact Explorer",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based", "semi_open"],
            "world_density": ["handcrafted_discovery"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
            "visual_presentation": ["side_scrolling_2d"],
        },
    )
    sparse_peer = Game(
        id=64,
        title="Sparse Peer",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based", "semi_open"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
            "visual_presentation": ["side_scrolling_2d"],
        },
    )
    handcrafted_peer = Game(
        id=65,
        title="Handcrafted Peer",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based", "semi_open"],
            "world_density": ["handcrafted_discovery"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
            "visual_presentation": ["side_scrolling_2d"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(sparse_peer, 0.95),
            _scored_neighbor(handcrafted_peer, 0.94),
        ],
        limit=1,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == ["Handcrafted Peer"]


def test_select_similarity_v3_neighbors_prefers_compact_metroidvania_peers_without_skill_tree_noise():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Compact Explorer",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based", "semi_open"],
            "world_density": ["handcrafted_discovery"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
            "input_complexity": ["casual"],
        },
    )
    noisy_peer = Game(
        id=66,
        title="Noisy Peer",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based", "semi_open"],
            "world_density": ["handcrafted_discovery"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression", "skill_tree"],
            "input_complexity": ["casual"],
        },
    )
    compact_peer = Game(
        id=67,
        title="Compact Peer",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "perspective": ["side_scrolling"],
            "mode_profile": ["single_player"],
            "world_topology": ["level_based", "semi_open"],
            "world_density": ["handcrafted_discovery"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
            "input_complexity": ["casual"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(noisy_peer, 0.95),
            _scored_neighbor(compact_peer, 0.94),
        ],
        limit=1,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == ["Compact Peer"]


def test_select_similarity_v3_neighbors_prefers_parry_action_platformer_for_parry_metroidvania():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Parryvania",
        steam_detailed_description="A parry-focused action Metroidvania with stylish parries.",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "world_topology": ["level_based", "semi_open"],
            "perspective": ["side_scrolling"],
            "combat_presence": ["dominant"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
            "mode_profile": ["single_player"],
        },
    )
    generic_peer = Game(
        id=168,
        title="Generic Metroidvania",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "world_topology": ["level_based", "semi_open"],
            "perspective": ["side_scrolling"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
            "mode_profile": ["single_player"],
        },
    )
    parry_peer = Game(
        id=169,
        title="Deflection Peer",
        steam_detailed_description="A hand-drawn action-platformer with deflection-focused combat.",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="action_platformer",
        taxonomy_v2_secondary_archetypes=["metroidvania"],
        taxonomy_v2_fingerprint={
            "world_topology": ["level_based", "semi_open"],
            "perspective": ["side_scrolling"],
            "combat_presence": ["dominant"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
            "mode_profile": ["single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(generic_peer, 0.98),
            _scored_neighbor(parry_peer, 0.90),
        ],
        limit=1,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == ["Deflection Peer"]


def test_select_similarity_v3_neighbors_prefers_roguelite_metroidvania_peers():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Proceduralvania",
        steam_detailed_description="A Metroidvania x roguelite with auto-generated dungeons and loot to bring back.",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "world_topology": ["level_based", "semi_open", "run_based"],
            "session_shape": ["roguelite_run"],
            "keyword_layer": ["procedural_generation"],
            "perspective": ["side_scrolling"],
            "combat_presence": ["dominant"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
            "mode_profile": ["single_player"],
        },
    )
    generic_peer = Game(
        id=170,
        title="Generic Handcrafted Metroidvania",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="metroidvania",
        taxonomy_v2_fingerprint={
            "world_topology": ["level_based", "semi_open"],
            "perspective": ["side_scrolling"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression", "skill_tree"],
            "mode_profile": ["single_player"],
        },
    )
    roguelite_peer = Game(
        id=171,
        title="Roguelite Metroidvania Peer",
        steam_detailed_description="A metroidvania roguelike with procedurally-generated labyrinths and randomized power-ups.",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="action_platformer",
        taxonomy_v2_secondary_archetypes=["metroidvania"],
        taxonomy_v2_fingerprint={
            "world_topology": ["level_based", "semi_open", "run_based"],
            "session_shape": ["roguelite_run"],
            "keyword_layer": ["procedural_generation"],
            "perspective": ["side_scrolling"],
            "combat_presence": ["dominant"],
            "traversal_verbs": ["platforming"],
            "progression_model": ["metaprogression"],
            "mode_profile": ["single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(generic_peer, 0.99),
            _scored_neighbor(roguelite_peer, 0.86),
        ],
        limit=1,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == ["Roguelite Metroidvania Peer"]


def test_select_similarity_v3_neighbors_reserves_action_roguelite_lane_for_solo_roguelikes():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Solo Rogue Action",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="loot_action_rpg",
        taxonomy_v2_fingerprint={
            "session_shape": ["roguelite_run"],
            "world_topology": ["run_based"],
            "combat_presence": ["dominant"],
            "combat_style": ["melee"],
            "progression_model": ["metaprogression", "buildcraft"],
            "mode_profile": ["single_player"],
        },
    )
    roguelite_peer = Game(
        id=68,
        title="Roguelite Peer",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="co_op_action_roguelite",
        taxonomy_v2_fingerprint={
            "session_shape": ["roguelite_run"],
            "world_topology": ["run_based"],
            "combat_presence": ["dominant"],
            "combat_style": ["melee"],
            "progression_model": ["metaprogression"],
            "mode_profile": ["single_player"],
        },
    )
    quest_loot_peer = Game(
        id=69,
        title="Quest Loot Peer",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="loot_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "combat_presence": ["dominant"],
            "combat_style": ["melee"],
            "progression_model": ["quest_driven", "gear_chase"],
            "mode_profile": ["single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(quest_loot_peer, 0.98),
            _scored_neighbor(roguelite_peer, 0.93),
        ],
        limit=1,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == ["Roguelite Peer"]


def test_select_similarity_v3_neighbors_reserves_transport_work_sim_lane():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Port Work Sim",
        steam_detailed_description="Operate heavy machinery and restore port infrastructure.",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="transport_sim",
        taxonomy_v2_fingerprint={
            "traversal_verbs": ["driving"],
            "challenge_model": ["sim_realism"],
            "interface_control": ["vehicle_control"],
            "combat_presence": ["none"],
            "progression_model": ["base_growth"],
            "mechanics_structure": ["systemic_problem_solving"],
            "mode_profile": ["single_player"],
        },
    )
    machinery_peer = Game(
        id=70,
        title="Machinery Peer",
        steam_detailed_description="Use forklifts, cranes, wheel loaders, and heavy trucks for logistics missions.",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="realistic_racer",
        taxonomy_v2_fingerprint={
            "traversal_verbs": ["driving"],
            "challenge_model": ["sim_realism"],
            "interface_control": ["vehicle_control"],
            "combat_presence": ["none"],
            "progression_model": ["base_growth"],
            "mechanics_structure": ["systemic_problem_solving"],
            "mode_profile": ["single_player"],
        },
    )
    race_peer = Game(
        id=71,
        title="Race Peer",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="realistic_racer",
        taxonomy_v2_fingerprint={
            "traversal_verbs": ["driving"],
            "challenge_model": ["sim_realism"],
            "interface_control": ["vehicle_control"],
            "mechanics_structure": ["vehicular_racing"],
            "rules_goals": ["win_races"],
            "mode_profile": ["single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(race_peer, 0.98),
            _scored_neighbor(machinery_peer, 0.92),
        ],
        limit=1,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == ["Machinery Peer"]


def test_select_similarity_v3_neighbors_reserves_rhythm_action_hybrid_lane():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Music Fighter",
        steam_detailed_description="A music-based action game where combat follows the rhythm.",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="rhythm_game",
        taxonomy_v2_fingerprint={
            "keyword_layer": ["rhythm"],
            "mechanics_structure": ["rhythm_timing"],
            "rules_goals": ["hit_beats"],
            "combat_presence": ["dominant"],
            "combat_style": ["melee"],
            "mode_profile": ["single_player"],
        },
    )
    action_peer = Game(
        id=72,
        title="Rhythm Action Peer",
        steam_detailed_description="A rhythm-action adventure with music-based battles and bosses.",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="rhythm_game",
        taxonomy_v2_fingerprint={
            "keyword_layer": ["rhythm"],
            "mechanics_structure": ["rhythm_timing"],
            "rules_goals": ["hit_beats"],
            "combat_presence": ["dominant"],
            "combat_structure": ["boss_centric"],
            "mode_profile": ["single_player"],
        },
    )
    pure_peer = Game(
        id=73,
        title="Pure Rhythm Peer",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="rhythm_game",
        taxonomy_v2_fingerprint={
            "keyword_layer": ["rhythm"],
            "mechanics_structure": ["rhythm_timing"],
            "rules_goals": ["hit_beats"],
            "combat_presence": ["none"],
            "mode_profile": ["single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(pure_peer, 0.98),
            _scored_neighbor(action_peer, 0.91),
        ],
        limit=1,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == ["Rhythm Action Peer"]


def test_select_similarity_v3_neighbors_reserves_compact_topdown_adventure_lane():
    profile = _similarity_v3_scoring_profile(LocalSimilarityV3MCP())
    anchor = Game(
        title="Retro Open Adventure",
        steam_detailed_description="A retro open world adventure with hidden secrets and find hidden paths.",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="open_world_action_adventure",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "world_density": ["handcrafted_discovery"],
            "perspective": ["isometric"],
            "mechanics_structure": ["quest_exploration_loop"],
            "progression_model": ["quest_driven"],
            "mode_profile": ["single_player"],
            "art_style": ["retro"],
        },
    )
    compact_peer = Game(
        id=74,
        title="Fox Adventure Peer",
        steam_detailed_description="An isometric action game about ancient ruins, lost legends, and hidden secrets.",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="open_world_action_adventure",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "world_density": ["handcrafted_discovery"],
            "perspective": ["isometric"],
            "mechanics_structure": ["quest_exploration_loop"],
            "progression_model": ["quest_driven"],
            "mode_profile": ["single_player"],
            "art_style": ["retro"],
        },
    )
    aaa_peer = Game(
        id=75,
        title="AAA Open World Peer",
        taxonomy_v2_status=TAXONOMY_V2_STATUS_COMPUTED,
        taxonomy_v2_primary_archetype="open_world_action_adventure",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "world_density": ["handcrafted_discovery"],
            "perspective": ["third_person"],
            "mechanics_structure": ["quest_exploration_loop"],
            "progression_model": ["quest_driven"],
            "mode_profile": ["single_player"],
        },
    )

    selected = _select_similarity_v3_neighbors(
        anchor,
        [
            _scored_neighbor(aaa_peer, 0.98),
            _scored_neighbor(compact_peer, 0.91),
        ],
        limit=1,
        profile=profile,
    )

    assert [item.candidate.title for item in selected] == ["Fox Adventure Peer"]


class _PayloadScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _PayloadResult:
    def __init__(self, payloads):
        self._payloads = payloads

    def scalars(self):
        return _PayloadScalars(self._payloads)


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _CaptureSession:
    def __init__(self, result):
        self.result = result
        self.statements = []

    async def execute(self, statement, *_args, **_kwargs):
        self.statements.append(statement)
        return self.result


@pytest.mark.asyncio
async def test_audit_similarity_v3_hidden_states_scopes_to_current_version_by_default():
    db = _CaptureSession(_PayloadResult([None, {"audit_state": "insufficient_signal"}]))

    rows = await audit_similarity_v3_hidden_states(db)

    assert rows == {"insufficient_signal": 1, "unknown": 1}
    compiled = db.statements[0].compile()
    assert compiled.params["similarity_v3_status_1"] == "hidden"
    assert compiled.params["similarity_v3_version_1"] == SIMILARITY_V3_VERSION


@pytest.mark.asyncio
async def test_audit_similarity_v3_hidden_states_can_include_all_versions():
    db = _CaptureSession(_PayloadResult([]))

    await audit_similarity_v3_hidden_states(db, similarity_version=None)

    compiled = db.statements[0].compile()
    assert compiled.params["similarity_v3_status_1"] == "hidden"
    assert "similarity_v3_version_1" not in compiled.params


@pytest.mark.asyncio
async def test_audit_similarity_v3_confusion_excludes_same_by_default():
    db = _CaptureSession(_RowsResult([("arcade_racer", "strong_neighbor", 12)]))

    rows = await audit_similarity_v3_confusion(db, limit=10)

    assert rows == [
        {
            "primary_archetype": "arcade_racer",
            "relationship_type": "strong_neighbor",
            "count": 12,
        }
    ]
    compiled = db.statements[0].compile()
    assert compiled.params["similarity_version_1"] == SIMILARITY_V3_VERSION
    assert compiled.params["relationship_type_1"] == "same"
    assert compiled.params["param_1"] == 10


@pytest.mark.asyncio
async def test_audit_similarity_v3_confusion_can_include_same_rows():
    db = _CaptureSession(_RowsResult([]))

    await audit_similarity_v3_confusion(db, limit=5, include_same=True)

    compiled = db.statements[0].compile()
    assert compiled.params["similarity_version_1"] == SIMILARITY_V3_VERSION
    assert "relationship_type_1" not in compiled.params
