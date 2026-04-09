from __future__ import annotations

import pytest
from sqlalchemy import Text, select

from app.models.models import Game, GameSimilarityV3Document, GameSimilarityV3Neighbor
from app.services.game_similarity_v3 import (
    SIMILARITY_V3_VERSION,
    LocalSimilarityV3MCP,
    _family_rerank_adjustment,
    _is_nonstandalone_similarity_candidate,
    _normalize_taxonomy_score,
    _open_world_fantasy_lane_fit,
    _select_similarity_v3_neighbors,
    _similarity_v3_scoring_profile,
    _title_variant_key,
    SimilarityV3ScoredNeighbor,
    build_similarity_v3_documents,
    build_similarity_v3_provider_text_doc,
    load_similarity_v3_target_games,
    mark_game_similarity_v3_dirty,
)


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
