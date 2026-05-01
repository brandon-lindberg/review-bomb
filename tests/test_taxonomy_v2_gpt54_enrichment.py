from __future__ import annotations

from types import SimpleNamespace

from app.services.game_taxonomy_v2 import (
    FINGERPRINT_AXES,
    _prefer_primary_archetype_candidate,
    assign_taxonomy_v2_archetypes,
    load_archetype_graph_v2,
)
from app.services.taxonomy_v2_gpt54_enrichment import (
    _build_similar_games_preview,
    _build_similar_repair_system_prompt,
    _build_similar_repair_user_prompt,
    _build_similar_games_system_prompt,
    _build_similar_stage_evaluation_system_prompt,
    _build_similar_stage_evaluation_user_prompt,
    _build_similar_games_user_prompt,
    _candidate_parent_titles,
    _build_external_evidence,
    _build_system_prompt,
    _build_llm_taxonomy_result,
    _build_user_prompt,
    _confidence_by_field_value,
    build_taxonomy_v2_gpt54_similar_preview_row,
    build_taxonomy_v2_gpt54_stage_evaluation_row,
    build_taxonomy_v2_gpt54_alignment_row,
    build_taxonomy_v2_gpt54_native_fix_backlog_row,
    build_taxonomy_v2_gpt54_gold_audit_row,
    build_taxonomy_v2_gpt54_gold_corpus_row,
    build_taxonomy_v2_gpt54_gold_drift_report_row,
    build_taxonomy_v2_gpt54_gold_fix_backlog_row,
    build_taxonomy_v2_gpt54_gold_split_rows,
    build_taxonomy_v2_gpt54_filtered_stage_row,
    build_taxonomy_v2_gpt54_stage_row,
    build_taxonomy_v2_result_from_stage_row,
    build_taxonomy_v2_gpt54_output_row,
    load_taxonomy_v2_allowed_vocab,
    should_retry_with_web,
    TaxonomyV2SimilarCandidateReview,
    TaxonomyV2SimilarGameExample,
    TaxonomyV2SimilarGamesPreview,
    TaxonomyV2SimilarGamesStageEvaluation,
    TaxonomyV2ExternalEvidence,
    TaxonomyV2EnrichmentBundle,
    TaxonomyV2EnrichmentDecision,
    TaxonomyV2EnrichmentParentGame,
)


def _make_bundle(
    *,
    audit_state: str = "mapping_gap",
    text_corpus: str = "A rich stored corpus describing combat, progression, traversal, and world structure.",
):
    return TaxonomyV2EnrichmentBundle(
        game_id=42,
        public_id="game-42",
        title="Hidden Game 42",
        release_date="2026-04-10",
        opencritic_id=42,
        steam_app_id=4242,
        metacritic_slug="hidden-game-42",
        description="Primary description",
        opencritic_description="OpenCritic description",
        steam_short_description="Steam short description",
        steam_detailed_description="Steam detailed description",
        metacritic_description="Metacritic description",
        taxonomy_genres=["action"],
        taxonomy_themes=["fantasy"],
        taxonomy_modes=["singleplayer"],
        taxonomy_v2_status="hidden",
        taxonomy_v2_text_corpus=text_corpus,
        taxonomy_v2_text_sources=["description", "steam_detailed_description"],
        taxonomy_v2_debug_payload={"audit_state": audit_state},
        source_labels=[],
    )


def _find_supported_primary_case():
    graph = load_archetype_graph_v2()
    for archetype, node in (graph.get("nodes") or {}).items():
        required_axes = node.get("required_axes") or {}
        if len(required_axes) < 2:
            continue
        fingerprint = {field: [] for field in FINGERPRINT_AXES}
        for axis, values in required_axes.items():
            if axis not in fingerprint or not values:
                continue
            fingerprint[axis] = [str(values[0])]
        for axis, values in (node.get("preferred_axes") or {}).items():
            if axis not in fingerprint or not values or fingerprint[axis]:
                continue
            fingerprint[axis] = [str(values[0])]
        candidates = assign_taxonomy_v2_archetypes(
            fingerprint,
            _confidence_by_field_value(fingerprint, 0.96),
        )
        if candidates and candidates[0].archetype == archetype:
            return archetype, fingerprint, candidates
    raise AssertionError("Expected at least one valid taxonomy archetype test case")


def _build_accept_payload(*, confidence: float = 0.96, evidence_summary: str | None = None):
    archetype, fingerprint, candidates = _find_supported_primary_case()
    return {
        "decision": "accept",
        "primary_archetype": archetype,
        "secondary_archetypes": [candidates[1].archetype] if len(candidates) > 1 else [],
        "fingerprint": fingerprint,
        "confidence": confidence,
        "evidence_summary": evidence_summary
        or (
            "Stored descriptions and source labels align on the game loop, traversal, progression, "
            "and combat structure strongly enough to support this taxonomy assignment."
        ),
        "used_web": False,
        "source_urls": ["https://example.com/game"],
        "rejection_reason": "",
    }, archetype


def test_load_taxonomy_v2_allowed_vocab_returns_expected_shape():
    vocab = load_taxonomy_v2_allowed_vocab()

    assert vocab["archetypes"]
    assert vocab["families_by_archetype"]
    assert set(vocab["values_by_field"]) == set(FINGERPRINT_AXES)
    assert "visual_novel" in vocab["archetypes"]
    assert "transport_sim" in vocab["archetypes"]
    assert "engineering_sandbox_sim" in vocab["archetypes"]
    assert "co_op_action_roguelite" in vocab["archetypes"]
    assert "side_scrolling_action_strategy" in vocab["archetypes"]
    assert "exploration_survival_adventure" in vocab["archetypes"]


def test_new_extension_archetypes_are_assignable_from_supported_fingerprints():
    cases = {
        "visual_novel": {
            "combat_presence": ["none"],
            "session_shape": ["campaign"],
            "narrative_structure": ["authored_linear"],
            "interface_control": ["cursor_driven"],
            "progression_model": ["relationship_social"],
        },
        "transport_sim": {
            "traversal_verbs": ["driving"],
            "challenge_model": ["sim_realism"],
            "interface_control": ["vehicle_control"],
            "combat_presence": ["none"],
            "session_shape": ["campaign"],
            "progression_model": ["base_growth"],
            "mechanics_structure": ["systemic_problem_solving"],
        },
        "engineering_sandbox_sim": {
            "world_density": ["systemic_sandbox"],
            "challenge_model": ["sim_realism"],
            "rules_goals": ["build_and_optimize"],
            "interface_control": ["vehicle_control"],
            "session_shape": ["sandbox_loop"],
            "vehicular_theme": ["spaceships"],
        },
        "co_op_action_roguelite": {
            "world_topology": ["run_based"],
            "session_shape": ["roguelite_run"],
            "mode_profile": ["drop_in_coop"],
            "combat_presence": ["dominant"],
            "combat_style": ["melee"],
            "progression_model": ["metaprogression"],
        },
        "side_scrolling_action_strategy": {
            "perspective": ["side_scrolling"],
            "mechanics_structure": ["real_time_command", "settlement_building"],
            "progression_model": ["base_growth"],
            "combat_presence": ["dominant"],
            "session_shape": ["campaign"],
        },
        "exploration_survival_adventure": {
            "world_topology": ["open_world"],
            "keyword_layer": ["open_world_exploration"],
            "mechanics_structure": ["systemic_problem_solving"],
            "progression_model": ["quest_driven"],
            "challenge_model": ["puzzle_gating"],
        },
    }

    for archetype, values in cases.items():
        fingerprint = {field: [] for field in FINGERPRINT_AXES}
        for field, field_values in values.items():
            fingerprint[field] = list(field_values)
        candidates = assign_taxonomy_v2_archetypes(
            fingerprint,
            _confidence_by_field_value(fingerprint, 0.96),
        )
        assert candidates
        assert candidates[0].archetype == archetype


def test_prefer_primary_archetype_candidate_prefers_turn_based_tactics_over_tactical_rpg_for_mission_based_roster_games():
    fingerprint = {field: [] for field in FINGERPRINT_AXES}
    fingerprint.update(
        {
            "world_topology": ["mission_based"],
            "session_shape": ["campaign", "mission_session"],
            "perspective": ["tactical_overhead"],
            "combat_style": ["party_tactics", "melee", "ranged"],
            "combat_tempo": ["tactical"],
            "combat_structure": ["party_management"],
            "progression_model": ["gear_chase", "skill_tree"],
            "challenge_model": ["tactical_optimization"],
            "entity_interaction": ["party_control", "inventory_loot"],
            "narrative_structure": ["authored_linear"],
            "setting": ["dark_fantasy"],
            "tone": ["bleak"],
        }
    )

    candidates = assign_taxonomy_v2_archetypes(
        fingerprint,
        _confidence_by_field_value(fingerprint, 0.96),
    )
    preferred = _prefer_primary_archetype_candidate(candidates, fingerprint)

    assert preferred
    assert preferred[0].archetype == "turn_based_tactics"


def test_build_llm_taxonomy_result_accepts_valid_payload():
    bundle = _make_bundle()
    payload, archetype = _build_accept_payload()

    decision = _build_llm_taxonomy_result(
        bundle,
        payload,
        min_confidence=0.85,
        used_web=False,
        reasoning_effort="low",
    )

    assert decision.accepted is True
    assert decision.reason == "accepted"
    assert decision.result is not None
    assert decision.result.primary_archetype == archetype
    assert decision.result.status == "curated"
    assert decision.result.debug_payload["llm_model"] == "gpt-5.4"
    assert decision.result.debug_payload["llm_used_web"] is False
    assert decision.result.debug_payload["llm_source_urls"] == ["https://example.com/game"]
    assert decision.result.evidence
    assert all(record.source == "llm_gpt54" for record in decision.result.evidence)


def test_build_llm_taxonomy_result_rejects_invalid_primary_archetype():
    bundle = _make_bundle()
    payload, _ = _build_accept_payload()
    payload["primary_archetype"] = "not_a_real_archetype"

    decision = _build_llm_taxonomy_result(
        bundle,
        payload,
        min_confidence=0.85,
        used_web=False,
        reasoning_effort="low",
    )

    assert decision.accepted is False
    assert decision.reason == "invalid_primary_archetype"


def test_build_llm_taxonomy_result_rejects_low_confidence():
    bundle = _make_bundle()
    payload, _ = _build_accept_payload(confidence=0.5)

    decision = _build_llm_taxonomy_result(
        bundle,
        payload,
        min_confidence=0.85,
        used_web=False,
        reasoning_effort="low",
    )

    assert decision.accepted is False
    assert decision.reason == "below_confidence_threshold"


def test_build_llm_taxonomy_result_rejects_thin_evidence_summary():
    bundle = _make_bundle()
    payload, _ = _build_accept_payload(evidence_summary="Too little evidence to trust.")

    decision = _build_llm_taxonomy_result(
        bundle,
        payload,
        min_confidence=0.85,
        used_web=False,
        reasoning_effort="low",
    )

    assert decision.accepted is False
    assert decision.reason == "thin_evidence_summary"


def test_should_retry_with_web_for_low_signal_or_sparse_evidence():
    rejected = TaxonomyV2EnrichmentDecision(
        game_id=42,
        public_id="game-42",
        title="Hidden Game 42",
        accepted=False,
        status="rejected",
        reason="invalid_primary_archetype",
        used_web=False,
        llm_confidence=0.8,
        result=None,
        payload={},
    )

    assert should_retry_with_web(_make_bundle(audit_state="insufficient_signal"), rejected) is True
    assert should_retry_with_web(_make_bundle(text_corpus="Thin text"), rejected) is True
    assert should_retry_with_web(_make_bundle(text_corpus=("rich evidence " * 100)), rejected) is False


def test_should_retry_with_web_for_dlc_bundle_even_with_rich_evidence():
    rejected = TaxonomyV2EnrichmentDecision(
        game_id=42,
        public_id="game-42",
        title="Hidden Game 42",
        accepted=False,
        status="rejected",
        reason="below_confidence_threshold",
        used_web=False,
        llm_confidence=0.8,
        result=None,
        payload={},
    )
    bundle = _make_bundle(text_corpus=("rich evidence " * 100))
    bundle = TaxonomyV2EnrichmentBundle(
        **{
            **bundle.__dict__,
            "title": "Starfield - Terran Armada",
            "description": "Story DLC for Starfield with new locations and weapons.",
        }
    )

    assert should_retry_with_web(bundle, rejected) is True


def test_candidate_parent_titles_infers_hyphenated_parent_without_explicit_dlc_markers():
    game = SimpleNamespace(
        title="Mordheim: City of the Damned - Witch Hunters",
        description="",
        steam_detailed_description="",
        steam_short_description="",
    )

    candidates = _candidate_parent_titles(game, [])

    assert candidates == ["Mordheim: City of the Damned"]


def test_build_taxonomy_v2_gpt54_output_row_includes_accepted_fields():
    bundle = _make_bundle()
    payload, archetype = _build_accept_payload()
    decision = _build_llm_taxonomy_result(
        bundle,
        payload,
        min_confidence=0.85,
        used_web=True,
        reasoning_effort="medium",
    )

    row = build_taxonomy_v2_gpt54_output_row(bundle, decision)

    assert row["accepted"] is True
    assert row["primary_archetype"] == archetype
    assert row["used_web"] is True
    assert row["source_urls"] == ["https://example.com/game"]


def test_build_llm_taxonomy_result_applies_primary_preference_alignment():
    bundle = _make_bundle()
    payload = {
        "decision": "accept",
        "primary_archetype": "western_narrative_rpg",
        "secondary_archetypes": ["stealth_action_adventure"],
        "fingerprint": {field: [] for field in FINGERPRINT_AXES},
        "confidence": 0.94,
        "evidence_summary": (
            "Stored descriptions support a quest-driven first-person sci-fi RPG with branching quests, "
            "dialogue choices, systemic encounters, and open-ended exploration."
        ),
        "used_web": False,
        "source_urls": ["https://example.com/starfield"],
        "rejection_reason": "",
    }
    payload["fingerprint"]["session_shape"] = ["campaign"]
    payload["fingerprint"]["perspective"] = ["first_person"]
    payload["fingerprint"]["progression_model"] = ["quest_driven"]
    payload["fingerprint"]["narrative_structure"] = ["authored_branching", "quest_web"]
    payload["fingerprint"]["entity_interaction"] = ["dialogue_choice", "inventory_loot"]
    payload["fingerprint"]["combat_style"] = ["stealth", "shooter"]
    payload["fingerprint"]["combat_structure"] = ["systemic_emergent", "encounter_driven"]
    payload["fingerprint"]["world_topology"] = ["semi_open", "open_world"]
    payload["fingerprint"]["setting"] = ["sci_fi"]
    payload["fingerprint"]["rules_goals"] = ["complete_quests"]

    decision = _build_llm_taxonomy_result(
        bundle,
        payload,
        min_confidence=0.85,
        used_web=False,
        reasoning_effort="low",
    )

    assert decision.accepted is True
    assert decision.result is not None
    assert decision.result.primary_archetype == "western_narrative_rpg"


def test_build_llm_taxonomy_result_drops_self_conflicting_hard_exclusions_for_primary():
    bundle = _make_bundle()
    payload = {
        "decision": "accept",
        "primary_archetype": "western_narrative_rpg",
        "secondary_archetypes": ["open_world_action_adventure"],
        "fingerprint": {field: [] for field in FINGERPRINT_AXES},
        "confidence": 0.9,
        "evidence_summary": (
            "Stored descriptions support a first-person branching sci-fi RPG with questing, dialogue choices, "
            "systemic exploration, and broad single-player campaign progression."
        ),
        "used_web": False,
        "source_urls": ["https://example.com/starfield"],
        "rejection_reason": "",
    }
    payload["fingerprint"]["session_shape"] = ["campaign"]
    payload["fingerprint"]["perspective"] = ["first_person", "third_person"]
    payload["fingerprint"]["progression_model"] = ["quest_driven", "buildcraft"]
    payload["fingerprint"]["narrative_structure"] = ["quest_web"]
    payload["fingerprint"]["entity_interaction"] = ["dialogue_choice", "inventory_loot"]
    payload["fingerprint"]["world_topology"] = ["open_world"]
    payload["fingerprint"]["setting"] = ["sci_fi"]
    payload["fingerprint"]["rules_goals"] = ["complete_quests"]
    payload["fingerprint"]["tone"] = ["serious", "heroic"]
    payload["fingerprint"]["hard_exclusions"] = ["match_based_only", "sports_sim"]

    decision = _build_llm_taxonomy_result(
        bundle,
        payload,
        min_confidence=0.85,
        used_web=False,
        reasoning_effort="low",
    )

    assert decision.accepted is True
    assert decision.result is not None
    assert decision.result.primary_archetype == "western_narrative_rpg"
    assert "match_based_only" not in decision.result.hard_exclusions
    assert "sports_sim" not in decision.result.hard_exclusions


def test_build_user_prompt_includes_explicit_dlc_parent_guidance():
    bundle = _make_bundle()
    bundle = TaxonomyV2EnrichmentBundle(
        **{
            **bundle.__dict__,
            "title": "Starfield - Terran Armada",
            "description": "Story DLC for Starfield with new locations and weapons.",
            "parent_game": TaxonomyV2EnrichmentParentGame(
                game_id=7,
                public_id="starfield",
                title="Starfield",
                release_date="2023-09-06",
                taxonomy_v2_status="computed",
                taxonomy_v2_primary_archetype="western_narrative_rpg",
                taxonomy_v2_secondary_archetypes=["open_world_action_adventure"],
                taxonomy_v2_fingerprint={"world_topology": ["open_world"]},
                description="A large-scale sci-fi RPG.",
                steam_detailed_description="Explore planets and complete quests.",
                taxonomy_genres=["rpg"],
                taxonomy_themes=["sci-fi"],
                taxonomy_modes=["single_player"],
            ),
        }
    )

    prompt = _build_user_prompt(bundle)

    assert "This title appears to be DLC for Starfield." in prompt
    assert "Prefer the parent game's stored descriptions and labels over any non-curated parent taxonomy fields." in prompt
    assert "classify it using the parent game's gameplay identity" in prompt


def test_build_system_prompt_strengthens_dlc_inheritance_guidance():
    prompt = _build_system_prompt(allow_web=False)

    assert "Additive story, mission, location, weapon, or expansion content" in prompt
    assert "Confidence may still be high" in prompt


def test_build_system_prompt_mentions_external_evidence_when_present():
    prompt = _build_system_prompt(allow_web=False, has_external_evidence=True)

    assert "external_evidence contains grounded, source-backed gameplay facts" in prompt
    assert "let it raise confidence" in prompt
    assert "official store or publisher sources consistently describe concrete gameplay loops" in prompt


def test_build_similar_stage_evaluation_prompt_requires_every_candidate_once():
    bundle = _make_bundle()
    stage_row = {
        "current_taxonomy": {"status": "hidden"},
        "proposed_taxonomy": {"primary_archetype": "western_narrative_rpg"},
        "review_flags": ["zero_live_overlap"],
        "staged_neighbors": [
            {
                "rank": 1,
                "candidate_public_id": "starfield",
                "candidate_title": "Starfield",
                "requested_title": "Starfield",
                "expected_relationship": "base_game",
                "why_similar": "Base game for the DLC.",
            }
        ],
    }
    candidate_game = SimpleNamespace(
        public_id="starfield",
        title="Starfield",
        release_date=None,
        taxonomy_v2_status="curated",
        taxonomy_v2_primary_archetype="western_narrative_rpg",
        taxonomy_v2_secondary_archetypes=["open_world_action_adventure"],
        taxonomy_v2_confidence=0.92,
        description="A large-scale sci-fi RPG.",
        opencritic_description="Explore planets and complete quests.",
        steam_short_description="Bethesda sci-fi RPG.",
        taxonomy_v2_text_corpus="Quest-driven open-world sci-fi role-playing game.",
        taxonomy_genres=["rpg"],
        taxonomy_themes=["sci-fi"],
        taxonomy_modes=["single_player"],
    )

    system_prompt = _build_similar_stage_evaluation_system_prompt()
    user_prompt = _build_similar_stage_evaluation_user_prompt(
        bundle,
        stage_row,
        {"starfield": candidate_game},
    )

    assert "Evaluate only the provided candidate games" in system_prompt
    assert "Rank every provided candidate exactly once" in system_prompt
    assert "candidate_public_id" in user_prompt
    assert "Starfield" in user_prompt


def test_build_similar_repair_prompt_blocks_existing_titles_and_uses_gap_notes():
    bundle = _make_bundle()
    stage_row = {
        "proposed_taxonomy": {"primary_archetype": "life_sim"},
    }
    evaluation_row = {
        "gap_notes": ["The rail needs a stronger shopkeeping life-sim comp."],
        "candidate_reviews": [
            {
                "rank": 1,
                "candidate_title": "Stardew Valley",
                "candidate_public_id": "stardew",
                "strength_label": "must_keep",
                "relationship_fit": "same",
                "strength_score": 95.0,
            },
            {
                "rank": 4,
                "candidate_title": "Moonlighter",
                "candidate_public_id": "moonlighter",
                "strength_label": "weak",
                "relationship_fit": "weak_neighbor",
                "strength_score": 47.0,
            },
        ],
    }

    system_prompt = _build_similar_repair_system_prompt()
    user_prompt = _build_similar_repair_user_prompt(
        bundle,
        stage_row,
        evaluation_row,
        replacement_limit=2,
    )

    assert "Do not repeat any title from keep_candidates or blocked_titles" in system_prompt
    assert "Stardew Valley" in user_prompt
    assert "Moonlighter" in user_prompt
    assert "stronger shopkeeping life-sim comp" in user_prompt


def test_build_taxonomy_v2_gpt54_stage_evaluation_row_includes_ranked_candidates():
    stage_row = {
        "game_id": 42,
        "public_id": "game-42",
        "title": "Hidden Game 42",
        "stage_status": "ready_for_review",
        "review_flags": ["zero_live_overlap"],
        "recommended_actions": ["review_neighbor_ranking"],
        "current_taxonomy": {"status": "hidden"},
        "proposed_taxonomy": {"primary_archetype": "western_narrative_rpg"},
    }
    evaluation = TaxonomyV2SimilarGamesStageEvaluation(
        game_id=42,
        public_id="game-42",
        title="Hidden Game 42",
        overall_verdict="good",
        overall_note="Most candidates are directionally right.",
        anchor_summary="Quest-driven open-world sci-fi RPG.",
        used_web=False,
        source_urls=[],
        gap_notes=["Missing a stronger first-person RPG benchmark."],
        candidate_reviews=[
            TaxonomyV2SimilarCandidateReview(
                candidate_public_id="starfield",
                candidate_title="Starfield",
                requested_title="Starfield",
                input_rank=2,
                rank=1,
                strength_label="must_keep",
                strength_score=97.0,
                relationship_fit="base_game",
                rationale="It is the base game and the clearest must-have comp.",
            ),
            TaxonomyV2SimilarCandidateReview(
                candidate_public_id="outer-worlds",
                candidate_title="The Outer Worlds",
                requested_title="The Outer Worlds",
                input_rank=1,
                rank=2,
                strength_label="strong",
                strength_score=88.0,
                relationship_fit="strong_neighbor",
                rationale="Shared first-person quest-driven sci-fi RPG structure.",
            ),
        ],
        payload={"overall_verdict": "good"},
    )

    row = build_taxonomy_v2_gpt54_stage_evaluation_row(stage_row, evaluation)

    assert row["overall_verdict"] == "good"
    assert row["strength_counts"] == {"must_keep": 1, "strong": 1}
    assert row["candidate_reviews"][0]["candidate_title"] == "Starfield"
    assert row["candidate_reviews"][0]["rank"] == 1
    assert row["gap_notes"] == ["Missing a stronger first-person RPG benchmark."]


def test_build_taxonomy_v2_gpt54_filtered_stage_row_prunes_weak_candidates():
    stage_row = {
        "public_id": "game-42",
        "title": "Hidden Game 42",
        "stage_status": "ready_for_review",
        "review_flags": [],
        "proposed_taxonomy": {"primary_archetype": "western_narrative_rpg"},
        "staged_neighbors": [
            {
                "rank": 1,
                "candidate_public_id": "a",
                "candidate_title": "Keep A",
                "requested_title": "Keep A",
                "expected_relationship": "same",
                "why_similar": "old rationale",
            },
            {
                "rank": 2,
                "candidate_public_id": "b",
                "candidate_title": "Drop B",
                "requested_title": "Drop B",
                "expected_relationship": "adjacent_neighbor",
                "why_similar": "old rationale",
            },
        ],
    }
    evaluation_row = {
        "overall_verdict": "good",
        "candidate_reviews": [
            {
                "candidate_public_id": "a",
                "candidate_title": "Keep A",
                "rank": 2,
                "strength_label": "strong",
                "strength_score": 88.0,
                "relationship_fit": "strong_neighbor",
                "rationale": "new rationale a",
            },
            {
                "candidate_public_id": "b",
                "candidate_title": "Drop B",
                "rank": 1,
                "strength_label": "weak",
                "strength_score": 48.0,
                "relationship_fit": "weak_neighbor",
                "rationale": "new rationale b",
            },
        ],
    }

    row = build_taxonomy_v2_gpt54_filtered_stage_row(stage_row, evaluation_row)

    assert row["stage_status"] == "ready_for_review"
    assert len(row["staged_neighbors"]) == 1
    assert row["staged_neighbors"][0]["candidate_public_id"] == "a"
    assert row["staged_neighbors"][0]["expected_relationship"] == "strong_neighbor"
    assert row["staged_neighbors"][0]["why_similar"] == "new rationale a"
    assert "weak_candidates_pruned" in row["review_flags"]
    assert row["filter_metadata"]["removed_neighbor_count"] == 1


def test_parent_prompt_payload_omits_non_curated_taxonomy_fields():
    parent = TaxonomyV2EnrichmentParentGame(
        game_id=7,
        public_id="starfield",
        title="Starfield",
        release_date="2023-09-06",
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="jrpg_story_rpg",
        taxonomy_v2_secondary_archetypes=["open_world_action_adventure"],
        taxonomy_v2_fingerprint={"world_topology": ["open_world"]},
        description="A large-scale sci-fi RPG.",
        steam_detailed_description="Explore planets and complete quests.",
        taxonomy_genres=["rpg"],
        taxonomy_themes=["sci-fi"],
        taxonomy_modes=["single_player"],
    )

    payload = parent.to_prompt_payload()

    assert payload["taxonomy_v2_status"] == "computed"
    assert payload["taxonomy_v2_primary_archetype"] is None
    assert payload["taxonomy_v2_secondary_archetypes"] == []
    assert payload["taxonomy_v2_fingerprint"] == {}


def test_build_user_prompt_includes_external_evidence_block():
    bundle = _make_bundle()
    external_evidence = TaxonomyV2ExternalEvidence(
        evidence_quality="strong",
        evidence_summary="Official sources confirm a structured single-player stealth horror campaign.",
        gameplay_facts={"core_loop": ["Stealth exploration and puzzle solving."], "perspective": [], "combat": [], "progression": [], "structure": [], "modes": [], "dlc_relationship": []},
        source_urls=["https://example.com/official"],
        source_notes=["Official site describes the stealth-and-puzzle loop."],
    )

    prompt = _build_user_prompt(bundle, external_evidence=external_evidence)

    assert "External evidence:" in prompt
    assert "Official sources confirm a structured single-player stealth horror campaign." in prompt
    assert "https://example.com/official" in prompt


def test_build_external_evidence_sanitizes_payload():
    evidence = _build_external_evidence(
        {
            "evidence_quality": "strong",
            "evidence_summary": "  Rich  grounded   gameplay evidence. ",
            "gameplay_facts": {
                "core_loop": ["Explore and solve mysteries", "Explore and solve mysteries"],
                "perspective": ["First-person"],
                "combat": [],
                "progression": [],
                "structure": [],
                "modes": ["Single-player"],
                "dlc_relationship": [],
            },
            "source_urls": ["https://example.com/a", "https://example.com/a", "not-a-url"],
            "source_notes": ["  Official page confirms exploration.  "],
        }
    )

    assert evidence is not None
    assert evidence.evidence_quality == "strong"
    assert evidence.source_urls == ["https://example.com/a"]
    assert evidence.gameplay_facts["core_loop"] == ["Explore and solve mysteries"]


def test_build_similar_games_system_prompt_mentions_dlc_parent_expectation():
    prompt = _build_similar_games_system_prompt(has_external_evidence=True)

    assert "base game should usually appear in similar_games" in prompt
    assert "external_evidence contains grounded, source-backed gameplay facts" in prompt


def test_build_similar_games_user_prompt_includes_external_evidence_and_limit():
    bundle = _make_bundle()
    external_evidence = TaxonomyV2ExternalEvidence(
        evidence_quality="strong",
        evidence_summary="Official sources confirm a first-person survival horror loop.",
        gameplay_facts={"core_loop": ["Investigate and survive."], "perspective": [], "combat": [], "progression": [], "structure": [], "modes": [], "dlc_relationship": []},
        source_urls=["https://example.com/official"],
        source_notes=["Official site confirms puzzle-driven stealth horror."],
    )

    prompt = _build_similar_games_user_prompt(bundle, limit=5, external_evidence=external_evidence)

    assert "Select 5 similar game examples" in prompt
    assert "Official sources confirm a first-person survival horror loop." in prompt
    assert "https://example.com/official" in prompt


def test_build_similar_games_preview_sanitizes_duplicates_and_urls():
    bundle = _make_bundle()
    preview = _build_similar_games_preview(
        bundle,
        {
            "anchor_summary": " A grounded first-person survival horror investigation game. ",
            "confidence": 0.92,
            "used_web": True,
            "expected_must_include_titles": ["Starfield", "Starfield"],
            "similar_games": [
                {
                    "title": "Starfield",
                    "expected_relationship": "base_game",
                    "why_similar": "The DLC inherits the base game's questing and exploration loop.",
                },
                {
                    "title": "Starfield",
                    "expected_relationship": "base_game",
                    "why_similar": "Duplicate should be dropped.",
                },
                {
                    "title": "The Outer Worlds",
                    "expected_relationship": "strong_neighbor",
                    "why_similar": "Single-player sci-fi questing with authored RPG structure.",
                },
            ],
            "source_urls": ["https://example.com/a", "https://example.com/a", "not-a-url"],
        },
        used_web=True,
        external_evidence=TaxonomyV2ExternalEvidence(
            evidence_quality="strong",
            evidence_summary="Grounded gameplay facts.",
            gameplay_facts={"core_loop": [], "perspective": [], "combat": [], "progression": [], "structure": [], "modes": [], "dlc_relationship": []},
            source_urls=["https://example.com/b"],
            source_notes=[],
        ),
        research_payload={"evidence_quality": "strong"},
        limit=5,
    )

    assert preview.anchor_summary == "A grounded first-person survival horror investigation game."
    assert preview.expected_must_include_titles == ["Starfield"]
    assert [item.title for item in preview.similar_games] == ["Starfield", "The Outer Worlds"]
    assert preview.source_urls == ["https://example.com/a", "https://example.com/b"]


def test_build_taxonomy_v2_gpt54_similar_preview_row_serializes_examples():
    bundle = _make_bundle()
    preview = TaxonomyV2SimilarGamesPreview(
        game_id=bundle.game_id,
        public_id=bundle.public_id,
        title=bundle.title,
        confidence=0.91,
        used_web=True,
        anchor_summary="A focused survival horror experience.",
        expected_must_include_titles=["Example Base Game"],
        similar_games=[
            TaxonomyV2SimilarGameExample(
                title="Example Base Game",
                expected_relationship="base_game",
                why_similar="Direct DLC inheritance.",
            )
        ],
        source_urls=["https://example.com/game"],
        payload={"anchor_summary": "A focused survival horror experience."},
        research_payload={"evidence_quality": "strong"},
    )

    row = build_taxonomy_v2_gpt54_similar_preview_row(bundle, preview)

    assert row["title"] == bundle.title
    assert row["expected_must_include_titles"] == ["Example Base Game"]
    assert row["similar_games"][0]["title"] == "Example Base Game"
    assert row["source_urls"] == ["https://example.com/game"]


def test_build_taxonomy_v2_gpt54_stage_row_builds_review_ready_payload():
    review_row = {
        "game_id": 42,
        "public_id": "game-42",
        "title": "Hidden Game 42",
        "current_taxonomy": {
            "status": "computed",
            "primary_archetype": "arcade_racer",
            "secondary_archetypes": [],
            "confidence": 0.9,
            "similarity_v3_status": "computed",
        },
        "llm_taxonomy": {
            "accepted": False,
            "status": "rejected",
            "reason": "fingerprint_primary_mismatch",
            "confidence": 0.8,
            "primary_archetype": None,
            "proposed_primary_archetype": "open_world_action_adventure",
            "proposed_secondary_archetypes": ["beat_em_up"],
            "evidence_summary": "Strong evidence for open-world brawler structure.",
        },
        "taxonomy_alignment": {
            "primary_match": False,
            "secondary_overlap": [],
            "needs_taxonomy_review": True,
        },
        "resolved_similar_games": [
            {
                "requested_title": "Sleeping Dogs",
                "resolved_title": "Sleeping Dogs: Definitive Edition",
                "resolved_public_id": "sleeping-dogs",
                "expected_relationship": "strong_neighbor",
                "why_similar": "Open-world urban brawler.",
            },
            {
                "requested_title": "Missing Game",
                "resolved_title": None,
                "resolved_public_id": None,
                "expected_relationship": "adjacent_neighbor",
                "why_similar": "Missing in DB.",
            },
        ],
        "missing_must_include_titles": ["Sleeping Dogs"],
        "matched_live_titles": [],
        "current_live_neighbors": [],
    }

    stage_row = build_taxonomy_v2_gpt54_stage_row(review_row, neighbor_limit=5)

    assert stage_row["stage_status"] == "ready_for_review"
    assert "taxonomy_review" in stage_row["review_flags"]
    assert "catalog_gap" in stage_row["review_flags"]
    assert "missing_must_include" in stage_row["review_flags"]
    assert stage_row["proposed_taxonomy"]["primary_archetype"] == "open_world_action_adventure"
    assert stage_row["staged_neighbors"][0]["candidate_public_id"] == "sleeping-dogs"
    assert stage_row["unresolved_similar_games"] == ["Missing Game"]


def test_build_taxonomy_v2_gpt54_stage_row_blocks_when_no_proposals_or_neighbors():
    stage_row = build_taxonomy_v2_gpt54_stage_row(
        {
            "game_id": 7,
            "public_id": "game-7",
            "title": "Game 7",
            "current_taxonomy": {"status": "hidden"},
            "llm_taxonomy": {"accepted": False, "status": "rejected", "reason": "llm_rejected"},
            "taxonomy_alignment": {"needs_taxonomy_review": False},
            "resolved_similar_games": [],
            "missing_must_include_titles": [],
            "matched_live_titles": [],
            "current_live_neighbors": [],
        }
    )

    assert stage_row["stage_status"] == "blocked"
    assert "no_resolved_neighbors" in stage_row["review_flags"]


def test_build_taxonomy_v2_result_from_stage_row_reconstructs_curated_result():
    payload, archetype = _build_accept_payload()
    stage_row = {
        "public_id": "game-42",
        "review_flags": ["taxonomy_review"],
        "recommended_actions": ["review_taxonomy"],
        "proposed_taxonomy": {
            "accepted": True,
            "status": "accepted",
            "reason": "accepted",
            "confidence": 0.96,
            "primary_archetype": archetype,
            "secondary_archetypes": payload["secondary_archetypes"],
            "fingerprint": payload["fingerprint"],
            "source_urls": ["https://example.com/game"],
            "used_web": False,
            "evidence_summary": payload["evidence_summary"],
        },
    }

    result = build_taxonomy_v2_result_from_stage_row(stage_row)

    assert result is not None
    assert result.status == "curated"
    assert result.primary_archetype == archetype
    assert result.curated is True
    assert result.debug_payload["audit_state"] == "llm_curated_stage_apply"
    assert result.debug_payload["llm_source_urls"] == ["https://example.com/game"]


def test_build_taxonomy_v2_gpt54_alignment_row_captures_training_targets_and_issue_types():
    review_row = {
        "game_id": 42,
        "public_id": "game-42",
        "title": "Hidden Game 42",
        "current_taxonomy": {
            "status": "computed",
            "primary_archetype": "arcade_racer",
            "secondary_archetypes": [],
            "confidence": 0.81,
            "similarity_v3_status": "computed",
        },
        "taxonomy_alignment": {
            "primary_match": False,
            "secondary_overlap": [],
            "needs_taxonomy_review": True,
        },
        "current_live_neighbors": [
            {"title": "Forza Horizon 5", "public_id": "forza"},
            {"title": "Roundabout", "public_id": "roundabout"},
        ],
        "missing_must_include_titles": ["Sleeping Dogs"],
        "matched_live_titles": [],
    }
    stage_row = {
        "game_id": 42,
        "public_id": "game-42",
        "title": "Hidden Game 42",
        "stage_status": "ready_for_review",
        "review_flags": ["taxonomy_review", "missing_must_include", "zero_live_overlap"],
        "recommended_actions": ["review_taxonomy", "review_neighbor_ranking"],
        "current_taxonomy": review_row["current_taxonomy"],
        "proposed_taxonomy": {
            "primary_archetype": "open_world_action_adventure",
            "secondary_archetypes": ["beat_em_up"],
            "confidence": 0.93,
        },
        "taxonomy_alignment": review_row["taxonomy_alignment"],
        "staged_neighbors": [
            {"candidate_public_id": "sleeping-dogs", "candidate_title": "Sleeping Dogs", "rank": 1},
            {"candidate_public_id": "mad-max", "candidate_title": "Mad Max", "rank": 2},
        ],
        "unresolved_similar_games": ["Mafia"],
        "missing_must_include_titles": ["Sleeping Dogs"],
        "matched_live_titles": [],
        "current_live_neighbors": review_row["current_live_neighbors"],
        "filter_metadata": {
            "removed_candidates": [
                {"candidate_title": "Tricky Madness", "strength_label": "drop"},
            ]
        },
    }
    evaluation_row = {
        "overall_verdict": "good",
        "candidate_reviews": [
            {"candidate_public_id": "sleeping-dogs", "strength_label": "must_keep", "rank": 1},
            {"candidate_public_id": "mad-max", "strength_label": "strong", "rank": 2},
        ],
    }

    row = build_taxonomy_v2_gpt54_alignment_row(review_row, stage_row, evaluation_row)

    assert row["title"] == "Hidden Game 42"
    assert {
        "taxonomy_not_curated",
        "taxonomy_mismatch",
        "zero_live_overlap",
        "must_include_missing",
        "catalog_gap",
        "weak_candidates_pruned",
        "live_ranking_misaligned",
        "live_false_positive_candidates",
    }.issubset(set(row["issue_types"]))
    assert row["live_only_titles"] == ["Forza Horizon 5", "Roundabout"]
    assert row["llm_only_titles"] == ["Mad Max", "Sleeping Dogs"]
    assert row["training_targets"]["target_primary_archetype"] == "open_world_action_adventure"
    assert row["training_targets"]["positive_neighbor_titles"] == ["Sleeping Dogs", "Mad Max"]
    assert row["training_targets"]["negative_live_titles"] == ["Forza Horizon 5", "Roundabout"]
    assert row["training_targets"]["removed_candidate_titles"] == ["Tricky Madness"]


def test_build_taxonomy_v2_gpt54_alignment_row_marks_live_empty_rows():
    row = build_taxonomy_v2_gpt54_alignment_row(
        {
            "game_id": 1,
            "public_id": "game-1",
            "title": "Game 1",
            "current_taxonomy": {"status": "pending"},
            "taxonomy_alignment": {"primary_match": False, "secondary_overlap": [], "needs_taxonomy_review": False},
            "current_live_neighbors": [],
            "missing_must_include_titles": [],
            "matched_live_titles": [],
        },
        {
            "game_id": 1,
            "public_id": "game-1",
            "title": "Game 1",
            "stage_status": "neighbors_only",
            "proposed_taxonomy": {},
            "staged_neighbors": [{"candidate_public_id": "x", "candidate_title": "Example", "rank": 1}],
            "current_live_neighbors": [],
            "review_flags": ["live_empty", "zero_live_overlap"],
            "recommended_actions": ["review_neighbor_ranking"],
        },
        {},
    )

    assert "live_empty" in row["issue_types"]
    assert "zero_live_overlap" in row["issue_types"]
    assert row["training_targets"]["positive_neighbor_titles"] == ["Example"]


def test_build_taxonomy_v2_gpt54_native_fix_backlog_row_prioritizes_taxonomy_drift():
    backlog_row = build_taxonomy_v2_gpt54_native_fix_backlog_row(
        {
            "game_id": 42,
            "public_id": "game-42",
            "title": "Hidden Game 42",
            "issue_types": [
                "taxonomy_not_curated",
                "taxonomy_mismatch",
                "must_include_missing",
                "zero_live_overlap",
                "live_false_positive_candidates",
                "catalog_gap",
                "weak_candidates_pruned",
            ],
            "current_taxonomy": {
                "status": "hidden",
                "primary_archetype": "arcade_racer",
            },
            "proposed_taxonomy": {
                "primary_archetype": "open_world_action_adventure",
            },
            "missing_must_include_titles": ["Sleeping Dogs"],
            "live_only_titles": ["Forza Horizon 5"],
            "llm_only_titles": ["Sleeping Dogs", "Mad Max"],
            "unresolved_similar_games": ["Mafia"],
            "removed_candidate_titles": ["Tricky Madness"],
            "training_targets": {
                "positive_neighbor_titles": ["Sleeping Dogs", "Mad Max"],
            },
        }
    )

    assert backlog_row["primary_bucket"] == "taxonomy_drift"
    assert backlog_row["priority_score"] == 150
    assert "taxonomy_backlog" in backlog_row["action_buckets"]
    assert "must_include_gap" in backlog_row["action_buckets"]
    assert backlog_row["target_primary_archetype"] == "open_world_action_adventure"
    assert backlog_row["live_only_titles"] == ["Forza Horizon 5"]
    assert backlog_row["unresolved_similar_games"] == ["Mafia"]


def test_build_taxonomy_v2_gpt54_gold_corpus_row_freezes_targets_and_baseline():
    gold_row = build_taxonomy_v2_gpt54_gold_corpus_row(
        {
            "game_id": 42,
            "public_id": "game-42",
            "title": "Hidden Game 42",
            "overall_verdict": "good",
            "current_taxonomy": {
                "status": "pending",
                "primary_archetype": None,
                "secondary_archetypes": [],
                "similarity_v3_status": "hidden",
            },
            "proposed_taxonomy": {
                "primary_archetype": "open_world_action_adventure",
                "secondary_archetypes": ["beat_em_up"],
                "confidence": 0.93,
            },
            "llm_neighbor_titles": ["Sleeping Dogs", "Mad Max"],
            "training_targets": {
                "positive_neighbor_public_ids": ["sleeping-dogs", "mad-max"],
            },
            "matched_live_titles": ["Sleeping Dogs"],
            "missing_must_include_titles": ["Mad Max"],
            "live_only_titles": ["Forza Horizon 5"],
            "removed_candidate_titles": ["Tricky Madness"],
            "live_titles": ["Sleeping Dogs", "Roundabout"],
            "overlap_titles": ["Sleeping Dogs"],
            "overlap_count": 1,
            "live_empty": False,
            "issue_types": ["taxonomy_not_curated", "must_include_missing"],
            "review_flags": ["taxonomy_review"],
            "recommended_actions": ["review_taxonomy"],
        }
    )

    assert gold_row["expected_taxonomy_ready"] is True
    assert gold_row["expected_similarity_v3_status"] == "computed"
    assert gold_row["gold_bucket"] == "taxonomy_backlog"
    assert gold_row["must_include_titles"] == ["Sleeping Dogs", "Mad Max"]
    assert gold_row["must_avoid_titles"] == ["Forza Horizon 5"]
    assert gold_row["tail_watchlist_titles"] == ["Tricky Madness"]
    assert gold_row["gold_neighbor_public_ids"] == ["sleeping-dogs", "mad-max"]
    assert gold_row["baseline_overlap_count"] == 1


def test_build_taxonomy_v2_gpt54_gold_split_rows_assigns_validation_deterministically():
    rows = [
        {"public_id": "a1", "title": "A1", "gold_bucket": "taxonomy_backlog", "holdout_priority": 90},
        {"public_id": "a2", "title": "A2", "gold_bucket": "taxonomy_backlog", "holdout_priority": 30},
        {"public_id": "b1", "title": "B1", "gold_bucket": "zero_overlap", "holdout_priority": 80},
        {"public_id": "b2", "title": "B2", "gold_bucket": "zero_overlap", "holdout_priority": 20},
        {"public_id": "c1", "title": "C1", "gold_bucket": "aligned", "holdout_priority": 70},
        {"public_id": "c2", "title": "C2", "gold_bucket": "aligned", "holdout_priority": 10},
    ]

    first = build_taxonomy_v2_gpt54_gold_split_rows(rows, validation_count=3)
    second = build_taxonomy_v2_gpt54_gold_split_rows(rows, validation_count=3)

    first_validation = {row["public_id"] for row in first if row["gold_split"] == "validation"}
    second_validation = {row["public_id"] for row in second if row["gold_split"] == "validation"}

    assert first_validation == {"a1", "b1", "c1"}
    assert second_validation == first_validation


def test_build_taxonomy_v2_gpt54_gold_audit_row_computes_recall_and_regression():
    audit_row = build_taxonomy_v2_gpt54_gold_audit_row(
        {
            "game_id": 42,
            "public_id": "game-42",
            "title": "Hidden Game 42",
            "gold_split": "validation",
            "gold_bucket": "zero_overlap",
            "overall_verdict": "good",
            "expected_taxonomy_ready": True,
            "expected_similarity_v3_status": "computed",
            "gold_taxonomy": {"primary_archetype": "metroidvania"},
            "gold_neighbor_titles": ["Supraland", "Metroid Prime Remastered"],
            "must_include_titles": ["Supraland"],
            "must_avoid_titles": ["Roundabout"],
            "baseline_overlap_count": 0,
            "baseline_live_empty": True,
            "issue_types": ["zero_live_overlap"],
            "review_flags": ["missing_must_include"],
        },
        {
            "anchor_found": True,
            "taxonomy_v2_status": "computed",
            "taxonomy_v2_primary_archetype": "metroidvania",
            "similarity_v3_status": "computed",
            "similarity_v3_version": "similarity_v3_pgvector_1",
            "live_titles": ["Supraland", "Roundabout"],
        },
    )

    assert audit_row["taxonomy_primary_match"] is True
    assert audit_row["overlap_count"] == 1
    assert audit_row["matched_must_include_titles"] == ["Supraland"]
    assert audit_row["missing_must_include_titles"] == []
    assert audit_row["must_avoid_hits"] == ["Roundabout"]
    assert audit_row["improved"] is True
    assert audit_row["worsened"] is False


def test_build_taxonomy_v2_gpt54_gold_fix_backlog_row_prioritizes_taxonomy_backlog():
    backlog_row = build_taxonomy_v2_gpt54_gold_fix_backlog_row(
        {
            "game_id": 42,
            "public_id": "game-42",
            "title": "Hidden Game 42",
            "gold_split": "repair",
            "gold_bucket": "taxonomy_backlog",
            "overall_verdict": "good",
            "expected_taxonomy_ready": True,
            "expected_similarity_v3_status": "computed",
            "gold_primary_archetype": "open_world_action_adventure",
            "current_taxonomy_status": "hidden",
            "current_primary_archetype": None,
            "current_similarity_v3_status": "hidden",
            "overlap_count": 0,
            "current_live_titles": [],
            "gold_neighbor_titles": ["Sleeping Dogs", "Mad Max"],
            "missing_must_include_titles": ["Sleeping Dogs", "Mad Max"],
            "must_avoid_hits": ["Forza Horizon 5"],
            "taxonomy_ready_match": False,
            "similarity_status_match": False,
            "live_empty": True,
            "issue_types": ["taxonomy_not_curated", "live_empty"],
            "review_flags": ["taxonomy_review"],
        }
    )

    assert backlog_row["primary_bucket"] == "taxonomy_backlog"
    assert "similarity_hidden" in backlog_row["action_buckets"]
    assert "live_empty" in backlog_row["action_buckets"]
    assert "must_include_gap" in backlog_row["action_buckets"]
    assert "false_positive_suppression" in backlog_row["action_buckets"]
    assert backlog_row["priority_score"] >= 100


def test_build_taxonomy_v2_gpt54_gold_drift_report_prioritizes_false_positives():
    drift_row = build_taxonomy_v2_gpt54_gold_drift_report_row(
        {
            "game_id": 42,
            "public_id": "game-42",
            "title": "Hidden Game 42",
            "gold_split": "validation",
            "gold_bucket": "zero_overlap",
            "overall_verdict": "good",
            "expected_taxonomy_ready": True,
            "expected_similarity_v3_status": "computed",
            "gold_primary_archetype": "open_world_action_adventure",
            "current_taxonomy_status": "computed",
            "current_primary_archetype": "open_world_action_adventure",
            "current_similarity_v3_status": "computed",
            "overlap_count": 0,
            "current_live_titles": ["Forza Horizon 5"],
            "gold_neighbor_titles": ["Sleeping Dogs", "Mad Max"],
            "missing_must_include_titles": ["Sleeping Dogs"],
            "must_avoid_hits": ["Forza Horizon 5"],
            "taxonomy_ready_match": True,
            "similarity_status_match": True,
            "live_empty": False,
            "worsened": False,
        }
    )

    assert drift_row["primary_bucket"] == "false_positive_suppression"
    assert "zero_overlap_live" in drift_row["action_buckets"]
    assert drift_row["recommended_action"] == "tighten_or_suppress_live_candidates"
    assert drift_row["priority_score"] >= 100
