from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from html import unescape
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Game, GameSourceTaxonomyLabel, GameTaxonomyV2Evidence
from app.services.game_taxonomy import normalize_taxonomy_label


TAXONOMY_V2_VERSION = "taxonomy_v3_matrix_5"
TAXONOMY_V2_STATUS_PENDING = "pending"
TAXONOMY_V2_STATUS_COMPUTED = "computed"
TAXONOMY_V2_STATUS_CURATED = "curated"
TAXONOMY_V2_STATUS_HIDDEN = "hidden"
TAXONOMY_V2_STATUS_FAILED = "failed"
TAXONOMY_V2_STATUS_NEEDS_REVIEW = "needs_review"
TAXONOMY_V2_READY_STATUSES = frozenset({TAXONOMY_V2_STATUS_COMPUTED, TAXONOMY_V2_STATUS_CURATED})
TAXONOMY_V2_LEGACY_HIDDEN_STATUSES = frozenset({TAXONOMY_V2_STATUS_FAILED, TAXONOMY_V2_STATUS_NEEDS_REVIEW})
_TITLE_EDITION_PARENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\s*[:\-–—]\s*(?:game of the year|goty|gator of the year)(?: edition)?\s*$"),
    re.compile(r"\s+(?:game of the year|goty|gator of the year)(?: edition)?\s*$"),
    re.compile(r"\s+(?:game of the year|goty|complete|definitive|ultimate|deluxe) edition\s*$"),
)

FINGERPRINT_AXES = (
    "world_topology",
    "world_density",
    "session_shape",
    "perspective",
    "visual_presentation",
    "art_style",
    "pacing",
    "interface_control",
    "combat_presence",
    "combat_style",
    "combat_tempo",
    "combat_structure",
    "traversal_verbs",
    "progression_model",
    "challenge_model",
    "narrative_structure",
    "narrative_topic",
    "sports_theme",
    "vehicular_theme",
    "keyword_layer",
    "mechanics_structure",
    "rules_goals",
    "entity_interaction",
    "setting",
    "tone",
    "mode_profile",
    "content_model",
    "input_complexity",
    "hard_exclusions",
    "soft_penalties",
)
FINGERPRINT_FIELDS = frozenset(FINGERPRINT_AXES)

_WORD_RE = re.compile(r"[^a-z0-9]+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TEXT_SEGMENT_SPLIT_RE = re.compile(r"\n{2,}|(?<=[.!?])\s+|[•·]")
_TEXT_AUDIT_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "to",
        "with",
        "your",
    }
)
_BOILERPLATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "edition_marketing",
        re.compile(r"\b(?:digital|deluxe|ultimate|gold|premium|collector(?:s)?|complete)\s+edition\b"),
    ),
    (
        "preorder_bonus",
        re.compile(r"\bpre[- ]?order\b|\bpreorder bonus\b"),
    ),
    (
        "bundle_contents",
        re.compile(
            r"\b(?:includes?|contains?)\b.*\b(?:full game|base game|bonus|dlc|season pass|expansion|artbook|soundtrack|skin|outfit|weapon|mount|pet|avatar|wallpaper)\b"
        ),
    ),
    (
        "dlc_marketing",
        re.compile(r"\b(?:season pass|expansion pass|downloadable content|dlc)\b"),
    ),
    (
        "account_legal",
        re.compile(
            r"\b(?:requires?|subject to change|terms and conditions|internet connection|account required|trademark|online services)\b"
        ),
    ),
)
_LOW_SIGNAL_SEGMENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("about_the_game", re.compile(r"\babout the game\b")),
    ("along_the_way", re.compile(r"\balong the way\b")),
    ("up_to_you", re.compile(r"\bup to you\b")),
    ("up_to_players", re.compile(r"\bup to players\b")),
    ("where_you_can", re.compile(r"\bwhere you can\b")),
    ("game_where_you", re.compile(r"\bgame where you\b")),
    ("create_your_own", re.compile(r"\bcreate your own\b")),
    ("you_can_also", re.compile(r"\byou can also\b")),
    ("will_be_able", re.compile(r"\bwill be able\b")),
    ("like_never_before", re.compile(r"\blike never before\b")),
)
_HIGH_SIGNAL_SEGMENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bopen[- ]world\b"),
    re.compile(r"\bturn[- ]based\b"),
    re.compile(r"\bco[- ]?op\b"),
    re.compile(r"\bmultiplayer\b"),
    re.compile(r"\bsingle[- ]player\b"),
    re.compile(r"\bstealth\b"),
    re.compile(r"\bmetroidvania\b"),
    re.compile(r"\bdeckbuilder\b"),
    re.compile(r"\bdeck[- ]building\b"),
    re.compile(r"\bcard battler\b"),
    re.compile(r"\brogue[- ]?lite\b"),
    re.compile(r"\brogue[- ]?like\b"),
    re.compile(r"\bpinball\b"),
    re.compile(r"\bplatformer\b"),
    re.compile(r"\breal[- ]time\b"),
    re.compile(r"\bracing\b"),
    re.compile(r"\bsoccer\b"),
    re.compile(r"\bfantasy\b"),
    re.compile(r"\bmagic\b"),
    re.compile(r"\bquest\b"),
    re.compile(r"\bhorseback\b"),
    re.compile(r"\bclimb(?:ing)?\b"),
    re.compile(r"\bglid(?:e|ing)\b"),
    re.compile(r"\bmelee\b"),
    re.compile(r"\branged\b"),
    re.compile(r"\belemental\b"),
    re.compile(r"\bbase\b"),
    re.compile(r"\bcamp\b"),
    re.compile(r"\bsettlement\b"),
    re.compile(r"\bpoint[- ]and[- ]click\b"),
    re.compile(r"\bfighter\b"),
    re.compile(r"\brhythm\b"),
    re.compile(r"\bshooter\b"),
    re.compile(r"\btwin[- ]stick\b"),
    re.compile(r"\bhorror\b"),
    re.compile(r"\bsupernatural\b"),
    re.compile(r"\bisometric\b"),
    re.compile(r"\bcrpg\b"),
    re.compile(r"\bword[- ]game\b"),
    re.compile(r"\bletter(?:s| synergies?)?\b"),
    re.compile(r"\bsynerg(?:y|ies)\b"),
    re.compile(r"\bfarming\b"),
    re.compile(r"\bcrops?\b"),
    re.compile(r"\bfish(?:ing)?\b"),
    re.compile(r"\bcultivat(?:e|ing)\b"),
    re.compile(r"\bbrawler\b"),
    re.compile(r"\brespawn system\b"),
    re.compile(r"\bzombies?\b"),
    re.compile(r"\bmodern warfare\b"),
    re.compile(r"\bmilitary\b"),
)
_IGNORED_SOURCE_LABELS: dict[tuple[str, str], set[str]] = {
    ("*", "platform"): {
        "pc",
        "mac",
        "linux",
        "windows",
        "ios",
        "android",
        "switch",
        "nintendo switch",
        "nintendo switch 2",
        "playstation 4",
        "playstation 5",
        "xbox one",
        "xbox series x",
        "xbox series s",
        "xbox series x s",
        "xbox series xs",
        "steam deck",
    },
    ("steam", "category"): {
        "family sharing",
        "steam achievements",
        "steam cloud",
        "steam trading cards",
        "steam turn notifications",
        "commentary available",
        "full controller support",
        "partial controller support",
        "tracked controller support",
        "vr supported",
        "vr only",
        "captions available",
        "custom volume controls",
        "adjustable difficulty",
        "mouse only option",
        "playable without timed input",
        "remote play on phone",
        "remote play on tablet",
        "remote play on tv",
        "save anytime",
        "stereo sound",
        "surround sound",
        "steam leaderboards",
    },
    ("steam", "genre"): {
        "indie",
    },
    ("steam", "tag"): {
        "indie",
        "colorful",
        "controller",
        "great soundtrack",
    },
}
_DESCRIPTION_RULES: tuple[tuple[tuple[re.Pattern[str], ...], tuple[tuple[str, str, float], ...]], ...] = (
    (
        (
            re.compile(r"\bopen[- ]world\b"),
            re.compile(r"\bseamless world\b"),
            re.compile(r"\bsprawling land\b"),
            re.compile(r"\bventure across\b"),
            re.compile(r"\bacross the kingdom\b"),
            re.compile(r"\bexplore a vast\b"),
            re.compile(r"\bworld is yours to explore\b"),
            re.compile(r"\bpaths for you to uncover\b"),
        ),
        (
            ("world_topology", "open_world", 0.95),
            ("world_density", "handcrafted_discovery", 0.82),
            ("keyword_layer", "open_world_exploration", 0.82),
            ("mechanics_structure", "quest_exploration_loop", 0.76),
        ),
    ),
    (
        (
            re.compile(r"\bopen[- ]air adventure\b"),
            re.compile(r"\bworld of discovery\b"),
            re.compile(r"\bdiscovery exploration and adventure\b"),
            re.compile(r"\bset your own path\b"),
            re.compile(r"\bworld waiting to be explored\b"),
        ),
        (
            ("world_topology", "open_world", 0.9),
            ("world_density", "handcrafted_discovery", 0.86),
            ("perspective", "third_person", 0.78),
            ("session_shape", "campaign", 0.74),
            ("combat_presence", "dominant", 0.72),
            ("keyword_layer", "open_world_exploration", 0.82),
            ("mechanics_structure", "quest_exploration_loop", 0.76),
        ),
    ),
    (
        (
            re.compile(r"\bhyrule\b"),
        ),
        (
            ("setting", "high_fantasy", 0.92),
            ("setting", "mythic", 0.88),
        ),
    ),
    (
        (
            re.compile(r"\bopen[- ]air adventure\b.*\bhyrule\b"),
            re.compile(r"\bhyrule\b.*\bopen[- ]air adventure\b"),
        ),
        (("traversal_verbs", "gliding", 0.9),),
    ),
    (
        (
            re.compile(r"\bland and skies\b"),
            re.compile(r"\bfloating islands?\b"),
            re.compile(r"\bsky islands?\b"),
        ),
        (
            ("world_density", "handcrafted_discovery", 0.82),
            ("traversal_verbs", "gliding", 0.84),
        ),
    ),
    (
        (
            re.compile(r"\bmission[- ]based\b"),
            re.compile(r"\bselect missions\b"),
            re.compile(r"\bmission structure\b"),
        ),
        (
            ("world_topology", "mission_based", 0.92),
            ("session_shape", "mission_session", 0.86),
            ("rules_goals", "clear_stages", 0.72),
        ),
    ),
    (
        (
            re.compile(r"\btactical overhead\b"),
            re.compile(r"\boverhead viewpoint\b"),
            re.compile(r"\bfrom a tactical overhead\b"),
        ),
        (
            ("perspective", "tactical_overhead", 0.92),
            ("combat_tempo", "tactical", 0.78),
            ("mechanics_structure", "real_time_command", 0.76),
        ),
    ),
    (
        (
            re.compile(r"\bride horseback\b"),
            re.compile(r"\bon horseback\b"),
            re.compile(r"\bmounted travel\b"),
            re.compile(r"\bhorseback\b"),
            re.compile(r"\bvarious mounts\b"),
            re.compile(r"\bmounts from horses\b"),
            re.compile(r"\broam the lands on\b"),
        ),
        (("traversal_verbs", "horseback", 0.95),),
    ),
    (
        (
            re.compile(r"\bclimb(?:ing)?\b"),
            re.compile(r"\bscale walls\b"),
            re.compile(r"\bscale cliffs\b"),
            re.compile(r"\bvertical traversal\b"),
        ),
        (("traversal_verbs", "climbing", 0.92),),
    ),
    (
        (
            re.compile(r"\bglide(?:ing)?\b"),
            re.compile(r"\btake to the skies\b"),
            re.compile(r"\bairborne traversal\b"),
            re.compile(r"\bparaglider\b"),
            re.compile(r"\bparaglide(?:r|ing)?\b"),
        ),
        (("traversal_verbs", "gliding", 0.92),),
    ),
    (
        (
            re.compile(r"\bpowerful new abilities\b"),
            re.compile(r"\bnew abilities\b"),
            re.compile(r"\buse your abilities\b"),
            re.compile(r"\bweapons and abilities\b"),
            re.compile(r"\bweapons and shields\b"),
        ),
        (
            ("combat_style", "hybrid", 0.84),
            ("progression_model", "skill_tree", 0.82),
            ("progression_model", "buildcraft", 0.78),
        ),
    ),
    (
        (
            re.compile(r"\bspecial items and rewards\b"),
            re.compile(r"\boutfits and gear\b"),
            re.compile(r"\bupgrade armor\b"),
        ),
        (
            ("progression_model", "gear_chase", 0.84),
            ("entity_interaction", "inventory_loot", 0.72),
        ),
    ),
    (
        (
            re.compile(r"\bparkour\b"),
            re.compile(r"\bwall[- ]run\b"),
            re.compile(r"\bfree[- ]run\b"),
            re.compile(r"\bfree[- ]running\b"),
            re.compile(r"\bfreerunning\b"),
            re.compile(r"\bfree[- ]runner\b"),
            re.compile(r"\bfree runner\b"),
        ),
        (("traversal_verbs", "parkour", 0.92),),
    ),
    (
        (
            re.compile(r"\bmmorpg\b"),
            re.compile(r"\bsandbox mmorpg\b"),
            re.compile(r"\bsandbox oriented mmorpg\b"),
        ),
        (
            ("world_topology", "persistent_shared_world", 0.94),
            ("world_density", "systemic_sandbox", 0.86),
            ("mode_profile", "mmo", 0.96),
            ("content_model", "mmo_persistent", 0.9),
        ),
    ),
    (
        (
            re.compile(r"\bcreative online sandbox adventure\b"),
            re.compile(r"\bvoxel[- ]based action mmo\b"),
            re.compile(r"\bcooperative,? 3d sandbox action rpg\b"),
            re.compile(r"\b3d sandbox action rpg\b"),
            re.compile(r"\bcreative sandbox adventure\b"),
            re.compile(r"\bsandbox adventure/building games?\b"),
            re.compile(r"\bsandbox adventure game\b"),
            re.compile(r"\bblock[- ]building rpg\b"),
            re.compile(r"\bblock[- ]building role[- ]playing game\b"),
            re.compile(r"\bbuild your own world of adventure\b"),
            re.compile(r"\bbuild big projects\b"),
            re.compile(r"\bbuild a cozy new life\b"),
            re.compile(r"\bbuild a new life\b"),
            re.compile(r"\brebuild a desolate world\b"),
            re.compile(r"\brebuild[^.]{0,80}\bworld\b"),
            re.compile(r"\brestore your [^.\n]{0,40}workshop\b"),
            re.compile(r"\bconstruct machines\b"),
            re.compile(r"\bturn your run[- ]down workshop\b"),
            re.compile(r"\bbuild the perfect neighborhood\b"),
            re.compile(r"\blife[- ]sim adventure game\b"),
            re.compile(r"\bhybrid between a life[- ]sim and an adventure game\b"),
            re.compile(r"\bcreating and destroying various types of blocks\b"),
            re.compile(r"\bdestroy or create blocks\b"),
            re.compile(r"\bforming fantastic structures\b"),
            re.compile(r"\bbuild impressive architectural structures\b"),
            re.compile(r"\bbuild brand new worlds\b"),
            re.compile(r"\bbuild almost anything\b"),
            re.compile(r"\bbuild your home\b"),
            re.compile(r"\bbuild your homebase\b"),
            re.compile(r"\bsculpt your world\b"),
            re.compile(r"\breshape or destroy anything\b"),
            re.compile(r"\bworlds? of skybound islands\b"),
            re.compile(r"\bsandbox islands\b"),
        ),
        (
            ("world_density", "systemic_sandbox", 0.9),
            ("progression_model", "buildcraft", 0.88),
            ("mechanics_structure", "settlement_building", 0.88),
            ("mechanics_structure", "systemic_problem_solving", 0.82),
            ("entity_interaction", "construction_placement", 0.9),
            ("rules_goals", "build_and_optimize", 0.9),
            ("session_shape", "sandbox_loop", 0.82),
        ),
    ),
    (
        (
            re.compile(r"\bexpansive world\b"),
            re.compile(r"\bworld just waiting to be explored\b"),
            re.compile(r"\bwaiting to be explored\b"),
            re.compile(r"\bexplore every corner\b"),
        ),
        (
            ("world_topology", "open_world", 0.86),
            ("world_density", "handcrafted_discovery", 0.8),
            ("keyword_layer", "open_world_exploration", 0.82),
            ("mechanics_structure", "quest_exploration_loop", 0.72),
        ),
    ),
    (
        (
            re.compile(r"\bblack spirit\b"),
            re.compile(r"\bblack stones?\b"),
        ),
        (
            ("setting", "high_fantasy", 0.88),
            ("setting", "mythic", 0.84),
        ),
    ),
    (
        (
            re.compile(r"\bsword and sorcery\b"),
            re.compile(r"\bmelee and magic\b"),
            re.compile(r"\bmix of melee and ranged combat\b"),
            re.compile(r"\bmelee and ranged combat\b"),
            re.compile(r"\bcombat style\b"),
            re.compile(r"\bskills and weapons\b"),
            re.compile(r"\bunique skills and weapons\b"),
        ),
        (
            ("combat_style", "hybrid", 0.9),
            ("progression_model", "buildcraft", 0.78),
        ),
    ),
    (
        (
            re.compile(r"\bskill[- ]based combat\b"),
            re.compile(r"\bintuitive skill[- ]based combat\b"),
            re.compile(r"\bfight back against\b"),
            re.compile(r"\bwield weapons\b"),
        ),
        (
            ("combat_style", "hybrid", 0.84),
            ("input_complexity", "mastery_heavy", 0.78),
        ),
    ),
    (
        (
            re.compile(r"\bprecise timing\b"),
            re.compile(r"\bpunishing combat\b"),
            re.compile(r"\bstamina[- ]based combat\b"),
        ),
        (
            ("challenge_model", "soulslike", 0.86),
            ("combat_tempo", "deliberate", 0.82),
        ),
    ),
    (
        (
            re.compile(r"\bcover[- ]based combat\b"),
            re.compile(r"\btake cover\b"),
        ),
        (("combat_structure", "cover_shooter", 0.88),),
    ),
    (
        (
            re.compile(r"\bfirst[- ]person shooter\b"),
            re.compile(r"\bfps\b"),
        ),
        (
            ("perspective", "first_person", 0.95),
            ("combat_style", "shooter", 0.95),
            ("combat_presence", "dominant", 0.84),
            ("hard_exclusions", "fps_only", 0.88),
        ),
    ),
    (
        (
            re.compile(r"\bteam[- ]based shooter\b"),
            re.compile(r"\bclass[- ]based shooter\b"),
            re.compile(r"\bhero[- ]based shooter\b"),
            re.compile(r"\bhero shooter\b"),
            re.compile(r"\bmultiplayer shooter\b"),
        ),
        (
            ("combat_style", "shooter", 0.94),
            ("combat_tempo", "tactical", 0.82),
            ("combat_structure", "crowd_control", 0.82),
            ("session_shape", "match_session", 0.8),
            ("mode_profile", "pvp", 0.84),
            ("keyword_layer", "hero_shooter", 0.86),
            ("mechanics_structure", "match_competition", 0.78),
            ("rules_goals", "win_matches", 0.76),
        ),
    ),
    (
        (
            re.compile(r"\bunique heroes\b"),
            re.compile(r"\bplayable heroes\b"),
            re.compile(r"\beach hero\b"),
            re.compile(r"\bhero roster\b"),
        ),
        (
            ("combat_structure", "crowd_control", 0.8),
        ),
    ),
    (
        (
            re.compile(r"\bsquad[- ]based battles\b"),
            re.compile(r"\bcommand your party\b"),
            re.compile(r"\bparty members\b"),
            re.compile(r"\bparty of heroes\b"),
            re.compile(r"\bcompanions\b"),
        ),
        (
            ("combat_style", "party_tactics", 0.88),
            ("combat_structure", "party_management", 0.88),
            ("mechanics_structure", "party_management_loop", 0.84),
            ("entity_interaction", "party_control", 0.8),
        ),
    ),
    (
        (
            re.compile(r"\bembark on quests\b"),
            re.compile(r"\bstory quests and side quests\b"),
            re.compile(r"\bstory quests\b"),
            re.compile(r"\bside quests\b"),
            re.compile(r"\bquest[- ]driven\b"),
            re.compile(r"\bthrough quests\b"),
            re.compile(r"\bundertake many quests\b"),
            re.compile(r"\boutside the main story\b"),
            re.compile(r"\btasked with\b"),
            re.compile(r"\bmonster contracts\b"),
        ),
        (
            ("progression_model", "quest_driven", 0.9),
            ("mechanics_structure", "quest_exploration_loop", 0.82),
            ("rules_goals", "complete_quests", 0.82),
        ),
    ),
    (
        (
            re.compile(r"\bchoice[- ]driven quests\b"),
            re.compile(r"\bbranching story\b"),
            re.compile(r"\bchoices matter\b"),
            re.compile(r"\bmultiple endings\b"),
        ),
        (
            ("progression_model", "quest_driven", 0.9),
            ("narrative_structure", "authored_branching", 0.86),
            ("entity_interaction", "dialogue_choice", 0.82),
            ("narrative_topic", "branching_choices", 0.82),
        ),
    ),
    (
        (
            re.compile(r"\bsingle[- ]player crpg\b"),
            re.compile(r"\bttrpg[- ]turned[- ]crpg\b"),
            re.compile(r"\bdisco[- ]like\b"),
            re.compile(r"\bpolitical conspiracy\b"),
            re.compile(r"\broll dice in tense encounters\b"),
        ),
        (
            ("perspective", "isometric", 0.9),
            ("progression_model", "quest_driven", 0.86),
            ("narrative_structure", "authored_branching", 0.86),
            ("entity_interaction", "dialogue_choice", 0.84),
            ("session_shape", "campaign", 0.82),
            ("tone", "serious", 0.76),
        ),
    ),
    (
        (
            re.compile(r"\bdetective with a unique skill system\b"),
            re.compile(r"\binterrogate unforgettable characters\b"),
            re.compile(r"\bcrack murders\b"),
            re.compile(r"\btake bribes\b"),
            re.compile(r"\bwhole city block\b"),
        ),
        (
            ("perspective", "isometric", 0.9),
            ("progression_model", "quest_driven", 0.86),
            ("narrative_structure", "authored_branching", 0.86),
            ("entity_interaction", "dialogue_choice", 0.84),
            ("session_shape", "campaign", 0.82),
            ("narrative_topic", "detective_mystery", 0.84),
            ("rules_goals", "solve_mysteries", 0.84),
            ("tone", "serious", 0.78),
        ),
    ),
    (
        (
            re.compile(r"\bcoming of age story\b"),
            re.compile(r"\bchain of serial murders\b"),
            re.compile(r"\bprotagonist and his friends\b"),
            re.compile(r"\bstrange world full of colorful friends and foes\b"),
            re.compile(r"\buncover a forgotten past\b"),
            re.compile(r"\bdetermine your fate\b"),
        ),
        (
            ("session_shape", "campaign", 0.84),
            ("combat_structure", "party_management", 0.82),
            ("combat_tempo", "tactical", 0.78),
            ("progression_model", "skill_tree", 0.78),
            ("narrative_structure", "authored_linear", 0.82),
            ("tone", "serious", 0.76),
        ),
    ),
    (
        (
            re.compile(r"\bshoot '?em up\b"),
            re.compile(r"\bshoot[- ]'?em[- ]up\b"),
            re.compile(r"\bshooting game series\b"),
            re.compile(r"\blegendary shooting game series\b"),
            re.compile(r"\bclassic arcade shoot\b"),
            re.compile(r"\barcade shoot.?em ups?\b"),
            re.compile(r"\barcade shoot '?em up\b"),
            re.compile(r"\bbullet[- ]hell shoot\b"),
            re.compile(r"\bbullet[- ]hell shooter\b"),
            re.compile(r"\bfrantic shooter series\b"),
            re.compile(r"\brevamped scoring system\b"),
            re.compile(r"\bvertically in (?:the )?popular '?tate'? mode\b"),
            re.compile(r"\bhigh[- ]octane aerial action\b"),
            re.compile(r"\bblast through these shooters\b"),
            re.compile(r"\bclassic shooting games\b"),
            re.compile(r"\braiden fighters trilogy\b"),
            re.compile(r"\braiden fighters series\b"),
            re.compile(r"\bhigh[- ]tempo\b.{0,80}\bscoring system\b"),
        ),
        (
            ("combat_style", "shooter", 0.92),
            ("combat_tempo", "twitch", 0.88),
            ("combat_presence", "dominant", 0.84),
            ("session_shape", "match_session", 0.82),
            ("perspective", "side_scrolling", 0.78),
            ("mechanics_structure", "score_attack", 0.8),
            ("rules_goals", "clear_stages", 0.8),
            ("rules_goals", "score_attack", 0.76),
        ),
    ),
    (
        (
            re.compile(r"\bcustomize your build\b"),
            re.compile(r"\badapt your build\b"),
            re.compile(r"\bpower builds?\b"),
            re.compile(r"\bunique power builds?\b"),
            re.compile(r"\btailor your playstyle\b"),
            re.compile(r"\bskill tree\b"),
            re.compile(r"\bno single path to victory\b"),
        ),
        (
            ("progression_model", "buildcraft", 0.88),
            ("progression_model", "skill_tree", 0.84),
            ("rules_goals", "defeat_bosses", 0.66),
        ),
    ),
    (
        (
            re.compile(r"\bpets destroy homes\b"),
            re.compile(r"\bdestroy homes\b"),
            re.compile(r"\bdemolition game\b"),
            re.compile(r"\bdestructive cat simulator\b"),
            re.compile(r"\bcat on a rampage\b"),
            re.compile(r"\bswat your human'?s possessions\b"),
            re.compile(r"\bscratch up curtains\b"),
            re.compile(r"\bsmash precious keepsakes\b"),
            re.compile(r"\bhorrible goose\b"),
            re.compile(r"\bslapstick[- ]stealth[- ]sandbox\b"),
            re.compile(r"\bgoose let loose\b"),
            re.compile(r"\bcreate carnage\b"),
            re.compile(r"\bsandbox farmyard experience\b"),
        ),
        (
            ("world_density", "systemic_sandbox", 0.88),
            ("mechanics_structure", "systemic_problem_solving", 0.86),
            ("rules_goals", "cause_mischief", 0.9),
            ("session_shape", "sandbox_loop", 0.82),
            ("tone", "whimsical", 0.84),
            ("input_complexity", "casual", 0.78),
            ("combat_presence", "none", 0.72),
        ),
    ),
    (
        (
            re.compile(r"\btwin[- ]stick shooter\b"),
            re.compile(r"\bbase defense twist\b"),
            re.compile(r"\bdefend your (?:ship|spaceship)\b"),
            re.compile(r"\balien hordes\b"),
        ),
        (
            ("combat_style", "shooter", 0.88),
            ("combat_structure", "crowd_control", 0.84),
            ("combat_presence", "dominant", 0.84),
            ("rules_goals", "survive_waves", 0.82),
        ),
    ),
    (
        (
            re.compile(r"\baction rogue[- ]lite\b"),
            re.compile(r"\baction rogue[- ]like\b"),
            re.compile(r"\baction roguelite\b"),
            re.compile(r"\baction roguelike\b"),
            re.compile(r"\brun after run\b"),
        ),
        (
            ("world_topology", "run_based", 0.88),
            ("session_shape", "roguelite_run", 0.86),
            ("progression_model", "metaprogression", 0.8),
        ),
    ),
    (
        (
            re.compile(r"\bfps rogue[- ]lite\b"),
            re.compile(r"\bfps rogue[- ]like\b"),
            re.compile(r"\bfps roguelite\b"),
            re.compile(r"\bfps roguelike\b"),
            re.compile(r"\brogue[- ]lite fps\b"),
            re.compile(r"\brogue[- ]like fps\b"),
            re.compile(r"\broguelite fps\b"),
            re.compile(r"\broguelike fps\b"),
            re.compile(r"\bfps with roguelite elements\b"),
            re.compile(r"\bfps with roguelike elements\b"),
            re.compile(r"\bfps with rogue[- ]lite elements\b"),
            re.compile(r"\bfps with rogue[- ]like elements\b"),
            re.compile(r"\bfps\b.{0,120}\broguelite elements\b"),
            re.compile(r"\bfps\b.{0,120}\broguelike elements\b"),
            re.compile(r"\bfps\b.{0,120}\brogue[- ]lite elements\b"),
            re.compile(r"\bfps\b.{0,120}\brogue[- ]like elements\b"),
            re.compile(r"\bfirst[- ]person shooter\b.{0,120}\broguelite mechanics\b"),
            re.compile(r"\bfirst[- ]person shooter\b.{0,120}\broguelike mechanics\b"),
            re.compile(r"\bfirst[- ]person shooter\b.{0,120}\brogue[- ]lite mechanics\b"),
            re.compile(r"\bfirst[- ]person shooter\b.{0,120}\brogue[- ]like mechanics\b"),
            re.compile(r"\bfirst[- ]person shooter with roguelite elements\b"),
            re.compile(r"\bfirst[- ]person shooter with roguelike elements\b"),
            re.compile(r"\bfirst[- ]person shooter with rogue[- ]lite elements\b"),
            re.compile(r"\bfirst[- ]person shooter with rogue[- ]like elements\b"),
        ),
        (
            ("perspective", "first_person", 0.95),
            ("combat_style", "shooter", 0.95),
            ("combat_presence", "dominant", 0.86),
            ("world_topology", "run_based", 0.9),
            ("session_shape", "roguelite_run", 0.88),
            ("progression_model", "metaprogression", 0.78),
            ("hard_exclusions", "fps_only", 0.86),
        ),
    ),
    (
        (
            re.compile(r"\bprotect your crystal\b"),
            re.compile(r"\bnever[- ]ending waves of monsters\b"),
            re.compile(r"\brogue[- ]lite tactical action\b"),
            re.compile(r"\bblend of roguelite, tactical action, and tower defense\b"),
        ),
        (
            ("world_topology", "run_based", 0.88),
            ("session_shape", "roguelite_run", 0.86),
            ("combat_presence", "dominant", 0.84),
            ("combat_style", "hybrid", 0.76),
            ("combat_structure", "crowd_control", 0.82),
            ("progression_model", "metaprogression", 0.8),
            ("rules_goals", "survive_waves", 0.82),
        ),
    ),
    (
        (
            re.compile(r"\bcollect gear\b"),
            re.compile(r"\bloot rare items\b"),
            re.compile(r"\bupgrade equipment\b"),
            re.compile(r"\brare loot\b"),
        ),
        (
            ("progression_model", "gear_chase", 0.86),
            ("progression_model", "loot_rarity", 0.8),
            ("entity_interaction", "inventory_loot", 0.74),
        ),
    ),
    (
        (
            re.compile(r"\bimprove your city\b"),
            re.compile(r"\bexpand your city\b"),
            re.compile(r"\brebuild your city\b"),
        ),
        (
            ("progression_model", "base_growth", 0.84),
            ("rules_goals", "build_and_optimize", 0.82),
            ("entity_interaction", "construction_placement", 0.76),
        ),
    ),
    (
        (
            re.compile(r"\bhordes? of enemies\b"),
            re.compile(r"\bhordes? of terrifying monsters\b"),
            re.compile(r"\bobliterate hordes?\b"),
            re.compile(r"\blegions? from the depths\b"),
        ),
        (
            ("combat_structure", "crowd_control", 0.84),
            ("combat_structure", "encounter_driven", 0.78),
            ("combat_presence", "dominant", 0.8),
        ),
    ),
    (
        (
            re.compile(r"\baction platformer\b"),
            re.compile(r"\bretro[- ]inspired action platformer\b"),
            re.compile(r"\bclassic 2d action\b"),
            re.compile(r"\bretro sword[- ]and[- ]whip action\b"),
            re.compile(r"\b8[- ]bit aesthetic\b"),
        ),
        (
            ("world_topology", "level_based", 0.88),
            ("perspective", "side_scrolling", 0.9),
            ("traversal_verbs", "platforming", 0.9),
            ("combat_presence", "dominant", 0.84),
            ("combat_structure", "encounter_driven", 0.8),
            ("art_style", "retro", 0.84),
        ),
    ),
    (
        (
            re.compile(r"\bgothic world\b"),
            re.compile(r"\bcursed realms?\b"),
            re.compile(r"\bpixel art foes\b"),
            re.compile(r"\bold school gameplay\b"),
            re.compile(r"\bgore galore\b"),
            re.compile(r"\barcade combat\b"),
            re.compile(r"\bback from hell\b"),
            re.compile(r"\bdark,? 8[- ]bit aesthetic\b"),
        ),
        (
            ("world_topology", "level_based", 0.84),
            ("perspective", "side_scrolling", 0.88),
            ("traversal_verbs", "platforming", 0.84),
            ("combat_presence", "dominant", 0.84),
            ("combat_structure", "encounter_driven", 0.78),
            ("setting", "horror", 0.84),
            ("tone", "bleak", 0.82),
            ("art_style", "retro", 0.84),
            ("art_style", "pixel_art", 0.82),
        ),
    ),
    (
        (
            re.compile(r"\bbuild your base\b"),
            re.compile(r"\bgrow your settlement\b"),
            re.compile(r"\bmanage colonists\b"),
            re.compile(r"\brebuild the faction\b"),
            re.compile(r"\blead your own group\b"),
            re.compile(r"\blead a band of\b"),
            re.compile(r"\bplayer housing\b"),
            re.compile(r"\breal estate management\b"),
        ),
        (
            ("progression_model", "base_growth", 0.9),
            ("progression_model", "colony_growth", 0.9),
            ("mechanics_structure", "settlement_building", 0.88),
            ("rules_goals", "build_and_optimize", 0.86),
            ("entity_interaction", "construction_placement", 0.82),
        ),
    ),
    (
        (
            re.compile(r"\btrading\b"),
            re.compile(r"\bcrafting\b"),
            re.compile(r"\bcastle sieging\b"),
            re.compile(r"\bnpc[- ]hiring\b"),
        ),
        (
            ("world_density", "systemic_sandbox", 0.82),
            ("progression_model", "buildcraft", 0.8),
            ("mechanics_structure", "systemic_problem_solving", 0.72),
        ),
    ),
    (
        (
            re.compile(r"\bfantasy realm\b"),
            re.compile(r"\bmythic kingdom\b"),
            re.compile(r"\bancient magic\b"),
            re.compile(r"\bfantasy kingdom\b"),
            re.compile(r"\bmedieval fantasy\b"),
            re.compile(r"\bwar[- ]torn realm\b"),
            re.compile(r"\bhostile world of monsters\b"),
            re.compile(r"\belixirs?\b"),
        ),
        (
            ("setting", "high_fantasy", 0.9),
            ("setting", "mythic", 0.82),
        ),
    ),
    (
        (
            re.compile(r"\bfeudal japan\b"),
            re.compile(r"\bsamurai\b"),
            re.compile(r"\bshinobi\b"),
            re.compile(r"\bmongol\b"),
            re.compile(r"\bhistorical\b"),
            re.compile(r"\b13th century\b"),
        ),
        (("setting", "historical", 0.92),),
    ),
    (
        (
            re.compile(r"\bsci[- ]fi\b"),
            re.compile(r"\bscience fiction\b"),
            re.compile(r"\bdeep space\b"),
            re.compile(r"\bspace station\b"),
            re.compile(r"\bouter space\b"),
        ),
        (("setting", "sci_fi", 0.88),),
    ),
    (
        (
            re.compile(r"\bgrim\b"),
            re.compile(r"\bruined world\b"),
            re.compile(r"\bbleak\b"),
            re.compile(r"\bdespair\b"),
            re.compile(r"\bdark tale\b"),
        ),
        (("tone", "bleak", 0.82),),
    ),
    (
        (
            re.compile(r"\blighthearted\b"),
            re.compile(r"\bwacky\b"),
            re.compile(r"\birreverent\b"),
            re.compile(r"\bhumorous\b"),
        ),
        (("tone", "comedic", 0.84),),
    ),
    (
        (
            re.compile(r"\bterror\b"),
            re.compile(r"\bnightmarish\b"),
            re.compile(r"\bgrotesque creatures\b"),
            re.compile(r"\bterrifying monsters\b"),
            re.compile(r"\beldritch abomination\b"),
            re.compile(r"\bblood[- ]soaked\b"),
            re.compile(r"\bgrim cultists\b"),
            re.compile(r"\binfernal minions\b"),
            re.compile(r"\bpsychological horror\b"),
            re.compile(r"\bdescend into madness\b"),
            re.compile(r"\bsurreal nightmare\b"),
        ),
        (
            ("setting", "horror", 0.9),
            ("tone", "grotesque", 0.84),
        ),
    ),
    (
        (
            re.compile(r"\bstory[- ]driven campaign\b"),
            re.compile(r"\bepic campaign\b"),
            re.compile(r"\bsingle[- ]player campaign\b"),
            re.compile(r"\bauthored linear story\b"),
            re.compile(r"\bfocused journey\b"),
        ),
        (
            ("session_shape", "campaign", 0.86),
            ("narrative_structure", "authored_linear", 0.82),
        ),
    ),
    (
        (
            re.compile(r"\bturn[- ]based combat\b"),
            re.compile(r"\bturn[- ]based battles\b"),
            re.compile(r"\bturn[- ]based rpg\b"),
        ),
        (
            ("combat_tempo", "tactical", 0.9),
            ("combat_structure", "party_management", 0.82),
            ("session_shape", "campaign", 0.76),
        ),
    ),
    (
        (
            re.compile(r"\bclassic jrpg\b"),
            re.compile(r"\bjrpg adventure\b"),
            re.compile(r"\bjapanese voice acting\b"),
            re.compile(r"\bstrategic turn[- ]based combat system\b"),
            re.compile(r"\brole[- ]playing game\b.{0,120}\bturn[- ]based combat\b"),
            re.compile(r"\bboard the astral express\b"),
            re.compile(r"\btravel across unique worlds\b"),
        ),
        (
            ("session_shape", "campaign", 0.84),
            ("combat_structure", "party_management", 0.8),
            ("combat_tempo", "tactical", 0.82),
            ("progression_model", "skill_tree", 0.78),
            ("narrative_structure", "authored_linear", 0.82),
            ("tone", "heroic", 0.72),
            ("mechanics_structure", "party_management_loop", 0.8),
            ("entity_interaction", "party_control", 0.76),
            ("narrative_topic", "heroic_journey", 0.72),
        ),
    ),
    (
        (
            re.compile(r"\bsave the world\b"),
            re.compile(r"\bepic quest\b"),
            re.compile(r"\bgrand adventure\b"),
        ),
        (
            ("session_shape", "campaign", 0.78),
            ("narrative_structure", "authored_linear", 0.76),
            ("tone", "heroic", 0.8),
            ("narrative_topic", "heroic_journey", 0.8),
        ),
    ),
    (
        (
            re.compile(r"\bcapture monsters\b"),
            re.compile(r"\bcollect monsters\b"),
            re.compile(r"\btame monsters\b"),
            re.compile(r"\braise monsters\b"),
            re.compile(r"\bmonster taming\b"),
            re.compile(r"\bbefriend creatures\b"),
            re.compile(r"\bcreature collecting\b"),
        ),
        (
            ("combat_structure", "party_management", 0.88),
            ("progression_model", "buildcraft", 0.82),
            ("progression_model", "skill_tree", 0.74),
            ("tone", "whimsical", 0.76),
            ("session_shape", "campaign", 0.76),
            ("keyword_layer", "monster_taming", 0.86),
            ("mechanics_structure", "creature_collection", 0.9),
            ("rules_goals", "capture_and_raise_companions", 0.88),
            ("entity_interaction", "creature_collection", 0.88),
            ("narrative_topic", "monster_bonding", 0.82),
        ),
    ),
    (
        (
            re.compile(r"\b1v1\b"),
            re.compile(r"\bhead[- ]to[- ]head\b"),
            re.compile(r"\broster of fighters\b"),
            re.compile(r"\bmaster combos\b"),
            re.compile(r"\bspecial moves\b"),
            re.compile(r"\bfighting game\b"),
            re.compile(r"\bversus fighter\b"),
        ),
        (
            ("combat_structure", "duel_focused", 0.92),
            ("combat_presence", "dominant", 0.88),
            ("mode_profile", "pvp", 0.86),
            ("input_complexity", "mastery_heavy", 0.84),
            ("mechanics_structure", "match_competition", 0.78),
            ("rules_goals", "win_matches", 0.82),
        ),
    ),
    (
        (
            re.compile(r"\bboss battles?\b"),
            re.compile(r"\bchallenging enemies and bosses\b"),
            re.compile(r"\bone[- ]on[- ]one duels?\b"),
            re.compile(r"\bduel powerful foes\b"),
        ),
        (
            ("combat_structure", "boss_centric", 0.92),
            ("combat_presence", "dominant", 0.82),
            ("combat_style", "melee", 0.74),
            ("rules_goals", "defeat_bosses", 0.84),
        ),
    ),
    (
        (
            re.compile(r"\bside[- ]scrolling action\b"),
            re.compile(r"\brun and gun\b"),
            re.compile(r"\bjump and slash\b"),
            re.compile(r"\bfight your way through levels\b"),
            re.compile(r"\bbattle enemies and bosses\b"),
        ),
        (
            ("perspective", "side_scrolling", 0.88),
            ("traversal_verbs", "platforming", 0.92),
            ("world_topology", "level_based", 0.84),
            ("combat_structure", "encounter_driven", 0.8),
            ("combat_presence", "moderate", 0.76),
            ("mechanics_structure", "platform_navigation", 0.86),
            ("rules_goals", "clear_stages", 0.76),
        ),
    ),
    (
        (
            re.compile(r"\bprecision jumps\b"),
            re.compile(r"\bprecision platforming\b"),
            re.compile(r"\bchallenging platforming\b"),
            re.compile(r"\bcustom respawn system\b"),
            re.compile(r"\breductive platforming game\b"),
            re.compile(r"\btough[- ]as[- ]nails platformer\b"),
            re.compile(r"\bcompetitive scoring\b"),
            re.compile(r"\breverse(?:d)? gravity instead of jumping\b"),
            re.compile(r"\bphysics[- ]based platformer\b"),
            re.compile(r"\bsuper[- ]tight platformer\b"),
            re.compile(r"\bhundreds of hand[- ]crafted challenges\b"),
            re.compile(r"\bclimb any surface for a few seconds\b"),
            re.compile(r"\bsprawling adventure platformer where you die a lot\b"),
        ),
        (
            ("perspective", "side_scrolling", 0.88),
            ("world_topology", "level_based", 0.84),
            ("traversal_verbs", "platforming", 0.92),
            ("challenge_model", "precision_platforming", 0.92),
            ("input_complexity", "mastery_heavy", 0.82),
            ("combat_presence", "none", 0.78),
            ("rules_goals", "score_attack", 0.8),
        ),
    ),
    (
        (
            re.compile(r"\bmysteries of the supernatural\b"),
            re.compile(r"\bsupernatural phenomena\b"),
            re.compile(r"\bsupernatural horror game\b"),
            re.compile(r"\bvillage that has vanished from the map\b"),
            re.compile(r"\blost in a village\b"),
            re.compile(r"\bhistory of suicides\b"),
            re.compile(r"\btragic deaths\b"),
            re.compile(r"\bshadows of those who passed away\b"),
            re.compile(r"\btrapped in an old abandoned town\b"),
            re.compile(r"\btrusty smart[- ]phone\b"),
            re.compile(r"\bslr camera\b"),
            re.compile(r"\bterrifying encounters\b"),
            re.compile(r"\bsolve mysterious puzzles\b"),
        ),
        (
            ("setting", "horror", 0.9),
            ("tone", "bleak", 0.82),
            ("combat_style", "survival", 0.84),
            ("combat_structure", "encounter_driven", 0.8),
            ("challenge_model", "puzzle_gating", 0.84),
            ("session_shape", "campaign", 0.8),
        ),
    ),
    (
        (
            re.compile(r"\bbase[- ]building,? survival game with action[- ]rpg elements\b"),
            re.compile(r"\bhack (?:and|&) slash(?:ing)? hordes of enemies\b"),
            re.compile(r"\bbuild up your base\b"),
            re.compile(r"\bresearch new inventions\b"),
        ),
        (
            ("combat_presence", "dominant", 0.82),
            ("combat_style", "hybrid", 0.84),
            ("combat_structure", "crowd_control", 0.82),
            ("progression_model", "buildcraft", 0.86),
            ("progression_model", "gear_chase", 0.82),
            ("entity_interaction", "construction_placement", 0.86),
            ("rules_goals", "build_and_optimize", 0.88),
            ("rules_goals", "survive_waves", 0.82),
            ("content_model", "premium_replayable", 0.8),
        ),
    ),
    (
        (
            re.compile(r"\binterconnected world\b"),
            re.compile(r"\bnew abilities unlock\b"),
            re.compile(r"\bability[- ]gated\b"),
            re.compile(r"\bbacktrack with new powers\b"),
        ),
        (
            ("world_topology", "semi_open", 0.86),
            ("world_density", "handcrafted_discovery", 0.82),
            ("progression_model", "skill_tree", 0.78),
            ("progression_model", "metaprogression", 0.76),
            ("traversal_verbs", "platforming", 0.78),
            ("mechanics_structure", "platform_navigation", 0.8),
        ),
    ),
    (
        (
            re.compile(r"\bopen[- ]world action\b"),
            re.compile(r"\bhuge open world\b"),
            re.compile(r"\bopen[- ]world game\b"),
            re.compile(r"\bexplore the world\b"),
        ),
        (
            ("world_topology", "open_world", 0.88),
            ("world_density", "handcrafted_discovery", 0.78),
            ("progression_model", "quest_driven", 0.74),
            ("combat_presence", "dominant", 0.7),
            ("keyword_layer", "open_world_exploration", 0.78),
            ("mechanics_structure", "quest_exploration_loop", 0.72),
        ),
    ),
    (
        (
            re.compile(r"\bpoint[- ]and[- ]click\b"),
            re.compile(r"\bsolve environmental puzzles\b"),
            re.compile(r"\bsearch for clues\b"),
        ),
        (
            ("challenge_model", "puzzle_gating", 0.9),
            ("combat_presence", "none", 0.86),
            ("narrative_structure", "authored_linear", 0.82),
            ("session_shape", "campaign", 0.74),
            ("keyword_layer", "point_and_click", 0.86),
            ("interface_control", "cursor_driven", 0.9),
            ("mechanics_structure", "environmental_puzzle_solving", 0.88),
            ("entity_interaction", "cursor_driven_interaction", 0.88),
            ("rules_goals", "solve_mysteries", 0.74),
        ),
    ),
    (
        (
            re.compile(r"\binvestigate\b"),
            re.compile(r"\buncover the mystery\b"),
            re.compile(r"\bsolve the mystery\b"),
            re.compile(r"\bdetective\b"),
        ),
        (
            ("challenge_model", "puzzle_gating", 0.82),
            ("narrative_structure", "authored_linear", 0.8),
            ("session_shape", "campaign", 0.72),
            ("narrative_topic", "detective_mystery", 0.84),
            ("rules_goals", "solve_mysteries", 0.84),
        ),
    ),
    (
        (
            re.compile(r"\breal[- ]time strategy\b"),
            re.compile(r"\bcommand armies\b"),
            re.compile(r"\bmanage resources\b"),
            re.compile(r"\bbuild your kingdom\b"),
        ),
        (
            ("perspective", "tactical_overhead", 0.88),
            ("combat_tempo", "tactical", 0.9),
            ("world_density", "systemic_sandbox", 0.78),
            ("progression_model", "base_growth", 0.84),
            ("session_shape", "campaign", 0.72),
            ("mechanics_structure", "real_time_command", 0.88),
            ("rules_goals", "build_and_optimize", 0.84),
            ("interface_control", "party_command", 0.76),
        ),
    ),
    (
        (
            re.compile(r"\brhythm game\b"),
            re.compile(r"\bkeep the beat\b"),
            re.compile(r"\bmusical adventure\b"),
        ),
        (
            ("session_shape", "match_session", 0.84),
            ("input_complexity", "moderate", 0.78),
            ("keyword_layer", "rhythm", 0.9),
            ("interface_control", "timing_input", 0.88),
            ("mechanics_structure", "rhythm_timing", 0.92),
            ("rules_goals", "hit_beats", 0.9),
        ),
    ),
    (
        (
            re.compile(r"\bstreet racing\b"),
            re.compile(r"\brealistic handling\b"),
            re.compile(r"\bopen[- ]world racer\b"),
        ),
        (
            ("traversal_verbs", "driving", 0.92),
            ("session_shape", "match_session", 0.8),
            ("challenge_model", "sim_realism", 0.76),
            ("vehicular_theme", "cars", 0.84),
            ("interface_control", "vehicle_control", 0.84),
            ("mechanics_structure", "vehicular_racing", 0.88),
            ("rules_goals", "win_races", 0.88),
        ),
    ),
    (
        (
            re.compile(r"\bbehind the wheel\b"),
            re.compile(r"\bturn[- ]of[- ]the[- ]century motorcars\b"),
            re.compile(r"\bspeed down dirt roads\b"),
            re.compile(r"\bspeed down roads\b"),
        ),
        (
            ("traversal_verbs", "driving", 0.82),
            ("vehicular_theme", "cars", 0.76),
        ),
    ),
)

_GLOBAL_LABEL_RULES: dict[str, tuple[tuple[str, str, float], ...]] = {
    "open world": (
        ("world_topology", "open_world", 0.88),
        ("world_density", "handcrafted_discovery", 0.75),
        ("keyword_layer", "open_world_exploration", 0.78),
        ("mechanics_structure", "quest_exploration_loop", 0.7),
    ),
    "open-world": (
        ("world_topology", "open_world", 0.88),
        ("world_density", "handcrafted_discovery", 0.75),
        ("keyword_layer", "open_world_exploration", 0.78),
        ("mechanics_structure", "quest_exploration_loop", 0.7),
    ),
    "sandbox": (("world_density", "systemic_sandbox", 0.76),),
    "exploration": (
        ("world_density", "handcrafted_discovery", 0.82),
        ("keyword_layer", "open_world_exploration", 0.72),
    ),
    "mission based": (("world_topology", "mission_based", 0.84), ("session_shape", "mission_session", 0.78)),
    "mission-based": (("world_topology", "mission_based", 0.84), ("session_shape", "mission_session", 0.78)),
    "hub": (("world_topology", "hub_and_spoke", 0.72),),
    "hub based": (("world_topology", "hub_and_spoke", 0.78),),
    "hub-based": (("world_topology", "hub_and_spoke", 0.78),),
    "roguelike": (("world_topology", "run_based", 0.86), ("session_shape", "roguelite_run", 0.82)),
    "rogue like": (("world_topology", "run_based", 0.86), ("session_shape", "roguelite_run", 0.82)),
    "rogue-like": (("world_topology", "run_based", 0.86), ("session_shape", "roguelite_run", 0.82)),
    "roguelite": (("world_topology", "run_based", 0.86), ("session_shape", "roguelite_run", 0.82)),
    "rogue lite": (("world_topology", "run_based", 0.86), ("session_shape", "roguelite_run", 0.82)),
    "rogue-lite": (("world_topology", "run_based", 0.86), ("session_shape", "roguelite_run", 0.82)),
    "mmo": (
        ("world_topology", "persistent_shared_world", 0.9),
        ("mode_profile", "mmo", 0.94),
        ("content_model", "mmo_persistent", 0.86),
    ),
    "massively multiplayer": (
        ("world_topology", "persistent_shared_world", 0.88),
        ("mode_profile", "mmo", 0.92),
    ),
    "first person shooter": (
        ("perspective", "first_person", 0.95),
        ("combat_style", "shooter", 0.95),
        ("hard_exclusions", "fps_only", 0.92),
    ),
    "fps": (
        ("perspective", "first_person", 0.92),
        ("combat_style", "shooter", 0.92),
        ("hard_exclusions", "fps_only", 0.88),
    ),
    "third person shooter": (
        ("perspective", "third_person", 0.9),
        ("combat_style", "shooter", 0.9),
    ),
    "first person": (("perspective", "first_person", 0.9),),
    "first-person": (("perspective", "first_person", 0.9),),
    "third person": (("perspective", "third_person", 0.9),),
    "third-person": (("perspective", "third_person", 0.9),),
    "isometric": (("perspective", "isometric", 0.9),),
    "pixel graphics": (
        ("art_style", "pixel_art", 0.9),
        ("visual_presentation", "side_scrolling_2d", 0.62),
    ),
    "retro": (("art_style", "retro", 0.86),),
    "hand drawn": (("art_style", "hand_drawn", 0.9),),
    "hand-drawn": (("art_style", "hand_drawn", 0.9),),
    "stylized": (("art_style", "stylized", 0.82),),
    "cartoony": (("art_style", "stylized", 0.82),),
    "anime": (("art_style", "anime", 0.86),),
    "action": (("combat_presence", "dominant", 0.62),),
    "adventure": (("session_shape", "campaign", 0.62),),
    "rpg": (("progression_model", "buildcraft", 0.64),),
    "jrpg": (
        ("session_shape", "campaign", 0.84),
        ("combat_structure", "party_management", 0.8),
        ("progression_model", "skill_tree", 0.82),
        ("narrative_structure", "authored_linear", 0.8),
    ),
    "fantasy": (("setting", "high_fantasy", 0.78),),
    "dark fantasy": (("setting", "dark_fantasy", 0.88),),
    "historical": (("setting", "historical", 0.88),),
    "magic": (("combat_style", "magic", 0.84),),
    "crafting": (("progression_model", "buildcraft", 0.84),),
    "word game": (
        ("challenge_model", "puzzle_gating", 0.88),
        ("combat_presence", "none", 0.84),
        ("interface_control", "cursor_driven", 0.78),
    ),
    "word-based": (
        ("challenge_model", "puzzle_gating", 0.86),
        ("combat_presence", "none", 0.82),
    ),
    "character customization": (
        ("progression_model", "buildcraft", 0.82),
        ("progression_model", "skill_tree", 0.74),
    ),
    "combat": (("combat_presence", "dominant", 0.74),),
    "tactical": (
        ("combat_tempo", "tactical", 0.82),
        ("challenge_model", "tactical_optimization", 0.8),
    ),
    "linear": (("world_topology", "linear", 0.84),),
    "sci fi": (("setting", "sci_fi", 0.84),),
    "sci-fi": (("setting", "sci_fi", 0.84),),
    "science fiction": (("setting", "sci_fi", 0.86),),
    "horror": (("setting", "horror", 0.84), ("tone", "bleak", 0.72)),
    "psychological horror": (
        ("setting", "horror", 0.92),
        ("tone", "melancholic", 0.82),
        ("world_topology", "linear", 0.72),
        ("combat_presence", "light", 0.68),
    ),
    "shooter": (("combat_style", "shooter", 0.88), ("combat_presence", "dominant", 0.8)),
    "military": (
        ("setting", "military", 0.9),
        ("combat_tempo", "tactical", 0.8),
    ),
    "modern warfare": (
        ("setting", "modern", 0.9),
        ("setting", "military", 0.88),
        ("world_topology", "mission_based", 0.82),
        ("session_shape", "mission_session", 0.8),
    ),
    "strategy": (
        ("combat_tempo", "tactical", 0.82),
        ("challenge_model", "tactical_optimization", 0.76),
    ),
    "simulation": (
        ("challenge_model", "sim_realism", 0.72),
        ("soft_penalties", "sim_heavy", 0.76),
    ),
    "story rich": (
        ("session_shape", "campaign", 0.74),
        ("narrative_structure", "authored_linear", 0.72),
        ("pacing", "long_form_campaign", 0.7),
    ),
    "atmospheric": (("tone", "melancholic", 0.68),),
    "mystery": (
        ("challenge_model", "puzzle_gating", 0.72),
        ("narrative_structure", "authored_linear", 0.68),
    ),
    "detective": (
        ("challenge_model", "puzzle_gating", 0.84),
        ("narrative_structure", "authored_linear", 0.78),
    ),
    "point and click": (
        ("challenge_model", "puzzle_gating", 0.92),
        ("combat_presence", "none", 0.86),
        ("narrative_structure", "authored_linear", 0.84),
        ("session_shape", "campaign", 0.74),
        ("interface_control", "cursor_driven", 0.9),
        ("keyword_layer", "point_and_click", 0.86),
        ("mechanics_structure", "environmental_puzzle_solving", 0.88),
        ("entity_interaction", "cursor_driven_interaction", 0.88),
    ),
    "point-and-click": (
        ("challenge_model", "puzzle_gating", 0.92),
        ("combat_presence", "none", 0.86),
        ("narrative_structure", "authored_linear", 0.84),
        ("session_shape", "campaign", 0.74),
        ("interface_control", "cursor_driven", 0.9),
        ("keyword_layer", "point_and_click", 0.86),
        ("mechanics_structure", "environmental_puzzle_solving", 0.88),
        ("entity_interaction", "cursor_driven_interaction", 0.88),
    ),
    "choices matter": (
        ("narrative_structure", "authored_branching", 0.88),
        ("entity_interaction", "dialogue_choice", 0.82),
        ("narrative_topic", "branching_choices", 0.82),
    ),
    "multiple endings": (("narrative_structure", "authored_branching", 0.84),),
    "comedy": (("tone", "comedic", 0.84),),
    "comedic": (("tone", "comedic", 0.84),),
    "funny": (("tone", "comedic", 0.84),),
    "cute": (("tone", "cozy", 0.76),),
    "family friendly": (("tone", "cozy", 0.78),),
    "dark": (("tone", "bleak", 0.78),),
    "emotional": (("tone", "melancholic", 0.82),),
    "violent": (("combat_presence", "dominant", 0.74),),
    "gore": (("tone", "grotesque", 0.82),),
    "arcade": (("session_shape", "match_session", 0.72),),
    "casual": (
        ("input_complexity", "casual", 0.82),
        ("tone", "cozy", 0.68),
    ),
    "relaxing": (("tone", "cozy", 0.82), ("combat_presence", "none", 0.74)),
    "2d": (("perspective", "side_scrolling", 0.62),),
    "2.5d": (("visual_presentation", "side_scrolling_2d", 0.7),),
    "3d": (("visual_presentation", "third_person_3d", 0.7),),
    "top down": (("perspective", "top_down", 0.88),),
    "top-down": (("perspective", "top_down", 0.88),),
    "side scroller": (("perspective", "side_scrolling", 0.88),),
    "side-scroller": (("perspective", "side_scrolling", 0.88),),
    "side scrolling": (("perspective", "side_scrolling", 0.88),),
    "side-scrolling": (("perspective", "side_scrolling", 0.88),),
    "fixed camera": (("perspective", "fixed_camera", 0.88),),
    "action rpg": (("combat_style", "hybrid", 0.9),),
    "deckbuilder": (
        ("progression_model", "deck_growth", 0.92),
        ("interface_control", "deck_management", 0.9),
        ("keyword_layer", "deckbuilding", 0.88),
        ("mechanics_structure", "deck_construction", 0.9),
        ("entity_interaction", "card_play", 0.88),
    ),
    "deck builder": (
        ("progression_model", "deck_growth", 0.92),
        ("interface_control", "deck_management", 0.9),
        ("keyword_layer", "deckbuilding", 0.88),
        ("mechanics_structure", "deck_construction", 0.9),
        ("entity_interaction", "card_play", 0.88),
    ),
    "hack and slash": (
        ("combat_style", "melee", 0.9),
        ("combat_tempo", "combo_driven", 0.86),
        ("combat_presence", "dominant", 0.84),
    ),
    "soulslike": (
        ("challenge_model", "soulslike", 0.94),
        ("combat_tempo", "deliberate", 0.82),
        ("rules_goals", "defeat_bosses", 0.74),
    ),
    "souls like": (
        ("challenge_model", "soulslike", 0.94),
        ("combat_tempo", "deliberate", 0.82),
        ("rules_goals", "defeat_bosses", 0.74),
    ),
    "souls-like": (
        ("challenge_model", "soulslike", 0.94),
        ("combat_tempo", "deliberate", 0.82),
        ("rules_goals", "defeat_bosses", 0.74),
    ),
    "stealth": (
        ("combat_style", "stealth", 0.9),
        ("mechanics_structure", "stealth_infiltration", 0.88),
        ("rules_goals", "infiltrate_avoid_detection", 0.82),
    ),
    "survival": (("combat_style", "survival", 0.82),),
    "realistic": (
        ("challenge_model", "sim_realism", 0.84),
        ("art_style", "photorealistic", 0.74),
    ),
    "space": (
        ("setting", "sci_fi", 0.8),
        ("vehicular_theme", "spaceships", 0.68),
    ),
    "turn based tactics": (("combat_style", "party_tactics", 0.9), ("combat_tempo", "tactical", 0.86)),
    "turn-based tactics": (("combat_style", "party_tactics", 0.9), ("combat_tempo", "tactical", 0.86)),
    "turn based combat": (
        ("combat_tempo", "tactical", 0.88),
        ("combat_structure", "party_management", 0.78),
    ),
    "turn-based combat": (
        ("combat_tempo", "tactical", 0.88),
        ("combat_structure", "party_management", 0.78),
    ),
    "turn based rpg": (
        ("combat_tempo", "tactical", 0.88),
        ("combat_structure", "party_management", 0.82),
        ("session_shape", "campaign", 0.78),
    ),
    "turn-based rpg": (
        ("combat_tempo", "tactical", 0.88),
        ("combat_structure", "party_management", 0.82),
        ("session_shape", "campaign", 0.78),
    ),
    "singleplayer": (("mode_profile", "single_player", 0.95),),
    "single-player": (("mode_profile", "single_player", 0.95),),
    "single player": (("mode_profile", "single_player", 0.95),),
    "local multiplayer": (("mode_profile", "party_coop", 0.74), ("mode_profile", "pvp", 0.72)),
    "shared split screen": (("mode_profile", "party_coop", 0.82),),
    "shared split screen co op": (("mode_profile", "party_coop", 0.9),),
    "shared split screen co-op": (("mode_profile", "party_coop", 0.9),),
    "shared split screen pvp": (("mode_profile", "pvp", 0.9),),
    "multi player": (("mode_profile", "pvp", 0.72),),
    "multi-player": (("mode_profile", "pvp", 0.72),),
    "multiplayer": (("mode_profile", "pvp", 0.72),),
    "remote play together": (("mode_profile", "party_coop", 0.92),),
    "co op": (("mode_profile", "drop_in_coop", 0.88),),
    "co-op": (("mode_profile", "drop_in_coop", 0.88),),
    "coop": (("mode_profile", "drop_in_coop", 0.88),),
    "online co op": (("mode_profile", "drop_in_coop", 0.92),),
    "online co-op": (("mode_profile", "drop_in_coop", 0.92),),
    "local co op": (("mode_profile", "party_coop", 0.92),),
    "local co-op": (("mode_profile", "party_coop", 0.92),),
    "pvp": (("mode_profile", "pvp", 0.94),),
    "pvpve": (("mode_profile", "pvpve", 0.96),),
    "live service": (("content_model", "live_service", 0.9),),
    "seasonal": (("content_model", "seasonal", 0.9),),
    "persistent world": (("content_model", "mmo_persistent", 0.9),),
    "city builder": (
        ("world_density", "city_dense", 0.88),
        ("progression_model", "colony_growth", 0.88),
    ),
    "colony sim": (
        ("world_density", "systemic_sandbox", 0.84),
        ("progression_model", "colony_growth", 0.9),
    ),
    "factory builder": (
        ("world_density", "systemic_sandbox", 0.86),
        ("progression_model", "base_growth", 0.82),
    ),
    "life sim": (
        ("progression_model", "relationship_social", 0.88),
        ("tone", "cozy", 0.84),
    ),
    "farming sim": (
        ("progression_model", "base_growth", 0.84),
        ("progression_model", "relationship_social", 0.8),
        ("tone", "cozy", 0.88),
    ),
    "farming": (
        ("progression_model", "base_growth", 0.84),
        ("world_density", "sandbox_light", 0.8),
        ("tone", "cozy", 0.78),
    ),
    "management": (
        ("progression_model", "base_growth", 0.8),
        ("session_shape", "sandbox_loop", 0.74),
        ("combat_presence", "light", 0.64),
    ),
    "real time strategy": (
        ("perspective", "tactical_overhead", 0.88),
        ("combat_tempo", "tactical", 0.92),
        ("world_density", "systemic_sandbox", 0.8),
        ("progression_model", "base_growth", 0.82),
    ),
    "real-time strategy": (
        ("perspective", "tactical_overhead", 0.88),
        ("combat_tempo", "tactical", 0.92),
        ("world_density", "systemic_sandbox", 0.8),
        ("progression_model", "base_growth", 0.82),
    ),
    "real time tactics": (
        ("perspective", "tactical_overhead", 0.88),
        ("combat_tempo", "tactical", 0.92),
        ("challenge_model", "tactical_optimization", 0.84),
        ("world_topology", "mission_based", 0.74),
    ),
    "real-time tactics": (
        ("perspective", "tactical_overhead", 0.88),
        ("combat_tempo", "tactical", 0.92),
        ("challenge_model", "tactical_optimization", 0.84),
        ("world_topology", "mission_based", 0.74),
    ),
    "metroidvania": (
        ("world_topology", "semi_open", 0.82),
        ("progression_model", "skill_tree", 0.68),
    ),
    "puzzle platformer": (
        ("traversal_verbs", "platforming", 0.9),
        ("world_topology", "level_based", 0.82),
        ("challenge_model", "puzzle_gating", 0.86),
        ("combat_presence", "light", 0.66),
    ),
    "deckbuilder": (("progression_model", "deck_growth", 0.92),),
    "deck builder": (("progression_model", "deck_growth", 0.92),),
    "survival horror": (
        ("setting", "horror", 0.94),
        ("combat_style", "survival", 0.9),
        ("tone", "bleak", 0.8),
        ("hard_exclusions", "pure_survival_horror", 0.94),
    ),
    "cover-based": (("combat_structure", "cover_shooter", 0.86),),
    "cover based": (("combat_structure", "cover_shooter", 0.86),),
    "sports sim": (("hard_exclusions", "sports_sim", 0.94),),
    "sports simulation": (("hard_exclusions", "sports_sim", 0.94),),
    "sports": (("session_shape", "match_session", 0.72),),
    "racing": (
        ("traversal_verbs", "driving", 0.9),
        ("session_shape", "match_session", 0.76),
        ("vehicular_theme", "cars", 0.84),
        ("interface_control", "vehicle_control", 0.84),
        ("mechanics_structure", "vehicular_racing", 0.88),
        ("rules_goals", "win_races", 0.88),
    ),
    "rhythm": (
        ("session_shape", "match_session", 0.84),
        ("input_complexity", "moderate", 0.76),
        ("keyword_layer", "rhythm", 0.9),
        ("interface_control", "timing_input", 0.88),
        ("mechanics_structure", "rhythm_timing", 0.92),
        ("rules_goals", "hit_beats", 0.9),
    ),
    "brawler": (
        ("combat_presence", "dominant", 0.88),
        ("combat_style", "melee", 0.9),
        ("combat_tempo", "combo_driven", 0.84),
        ("world_topology", "level_based", 0.78),
    ),
    "beat em up": (
        ("combat_presence", "dominant", 0.9),
        ("combat_style", "melee", 0.92),
        ("combat_tempo", "combo_driven", 0.86),
        ("world_topology", "level_based", 0.82),
    ),
    "beat-'em-up": (
        ("combat_presence", "dominant", 0.9),
        ("combat_style", "melee", 0.92),
        ("combat_tempo", "combo_driven", 0.86),
        ("world_topology", "level_based", 0.82),
    ),
    "visual novel": (
        ("hard_exclusions", "non_combat", 0.84),
        ("combat_presence", "none", 0.88),
        ("session_shape", "campaign", 0.78),
        ("narrative_structure", "authored_linear", 0.86),
        ("interface_control", "cursor_driven", 0.76),
    ),
    "walking simulator": (("hard_exclusions", "non_combat", 0.84),),
    "walking sim": (("hard_exclusions", "non_combat", 0.84),),
}

_FACET_LABEL_RULES: dict[str, dict[str, tuple[tuple[str, str, float], ...]]] = {
    "genre": {
        "horror": (("setting", "horror", 0.8),),
        "fantasy": (("setting", "high_fantasy", 0.76),),
        "dark fantasy": (("setting", "dark_fantasy", 0.86),),
        "rpg": (("progression_model", "buildcraft", 0.64),),
        "action": (("combat_presence", "dominant", 0.62),),
        "simulation": (("soft_penalties", "sim_heavy", 0.65), ("challenge_model", "sim_realism", 0.7)),
        "shooter": (("combat_style", "shooter", 0.84), ("combat_presence", "dominant", 0.76)),
        "strategy": (
            ("combat_tempo", "tactical", 0.72),
            ("challenge_model", "tactical_optimization", 0.72),
        ),
        "sports": (("session_shape", "match_session", 0.72),),
        "racing": (
            ("traversal_verbs", "driving", 0.86),
            ("session_shape", "match_session", 0.74),
        ),
    },
    "category": {
        "multiplayer": (("mode_profile", "pvp", 0.72),),
        "online multiplayer": (("mode_profile", "pvp", 0.72),),
        "online multi-player": (("mode_profile", "pvp", 0.72),),
        "local pvp": (("mode_profile", "pvp", 0.88),),
        "online pvp": (("mode_profile", "pvp", 0.9),),
        "local multiplayer": (("mode_profile", "party_coop", 0.76), ("mode_profile", "pvp", 0.74)),
        "shared split screen": (("mode_profile", "party_coop", 0.82),),
        "shared split screen co-op": (("mode_profile", "party_coop", 0.9),),
        "shared split screen pvp": (("mode_profile", "pvp", 0.9),),
    },
    "theme": {
        "open world": (("world_topology", "open_world", 0.88),),
        "survival horror": (
            ("setting", "horror", 0.94),
            ("combat_style", "survival", 0.9),
            ("hard_exclusions", "pure_survival_horror", 0.92),
        ),
        "psychological horror": (
            ("setting", "horror", 0.92),
            ("tone", "melancholic", 0.84),
            ("world_topology", "linear", 0.72),
            ("combat_presence", "light", 0.68),
        ),
    },
}

_STRICT_MIN_REQUIRED_HITS: dict[str, int] = {
    "open_world_fantasy_action_rpg": 5,
    "beat_em_up": 3,
    "loot_action_rpg": 3,
    "mmo_action_rpg": 4,
}
_MANDATORY_REQUIRED_AXES: dict[str, set[str]] = {
    "open_world_fantasy_action_rpg": {"setting", "perspective", "progression_model"},
    "arena_fps": {"perspective", "session_shape"},
    "hero_shooter": {"mode_profile", "session_shape"},
    "traditional_fighter": {"combat_structure", "mode_profile"},
    "jrpg_story_rpg": {"combat_structure", "session_shape"},
    "monster_collect_rpg": {"combat_structure"},
    "survival_horror": {"setting", "combat_style"},
    "action_horror": {"setting"},
    "card_battler": {"progression_model"},
    "hidden_object_puzzle": {"challenge_model", "combat_presence"},
    "sports_sim": {"session_shape"},
}
_ADDITIONAL_NODE_HARD_EXCLUSIONS: dict[str, set[str]] = {
    "open_world_fantasy_action_rpg": {
        "platformer_first",
        "jrpg_first",
        "historical_first",
        "isometric_first",
        "overhead_strategy_first",
    },
    "arena_fps": {"campaign_only"},
    "hero_shooter": {"campaign_only"},
}
_ASSIGNMENT_ONLY_NODE_HARD_EXCLUSIONS: dict[str, set[str]] = {
    "open_world_fantasy_action_rpg": {"mmo_first", "cinematic_linear_first"},
}
_PROGRESSION_MATCH_WEIGHTS: dict[str, int] = {
    "buildcraft": 6,
    "skill_tree": 14,
    "quest_driven": 16,
    "base_growth": 8,
    "colony_growth": 6,
    "gear_chase": 16,
    "loot_rarity": 12,
    "craft_survive": 16,
    "deck_growth": 18,
    "extraction_economy": 18,
    "relationship_social": 10,
    "metaprogression": 10,
}
_TRAVERSAL_MATCH_WEIGHTS: dict[str, int] = {
    "horseback": 18,
    "gliding": 18,
    "climbing": 16,
    "parkour": 14,
    "driving": 12,
    "sailing": 14,
    "flying": 14,
    "platforming": 8,
    "teleportation": 12,
}
_KEYWORD_MATCH_WEIGHTS: dict[str, int] = {
    "open_world_exploration": 6,
    "immersive_sim": 16,
    "hidden_object": 14,
    "point_and_click": 12,
    "monster_taming": 18,
    "deckbuilding": 16,
    "psychological_horror": 16,
    "hero_shooter": 18,
    "real_time_tactics": 16,
    "pinball": 18,
    "rhythm": 18,
    "retail_management": 18,
}
_MECHANICS_MATCH_WEIGHTS: dict[str, int] = {
    "quest_exploration_loop": 10,
    "party_management_loop": 18,
    "creature_collection": 20,
    "deck_construction": 20,
    "environmental_puzzle_solving": 16,
    "stealth_infiltration": 16,
    "vehicular_racing": 18,
    "match_competition": 14,
    "settlement_building": 18,
    "systemic_problem_solving": 18,
    "platform_navigation": 14,
    "real_time_command": 16,
    "rhythm_timing": 18,
    "score_attack": 14,
}
_RULES_GOALS_MATCH_WEIGHTS: dict[str, int] = {
    "complete_quests": 18,
    "win_matches": 12,
    "win_races": 14,
    "capture_and_raise_companions": 18,
    "solve_mysteries": 16,
    "build_and_optimize": 16,
    "infiltrate_avoid_detection": 16,
    "defeat_bosses": 20,
    "clear_stages": 10,
    "hit_beats": 16,
}
_ENTITY_INTERACTION_MATCH_WEIGHTS: dict[str, int] = {
    "party_control": 14,
    "dialogue_choice": 16,
    "creature_collection": 18,
    "card_play": 18,
    "construction_placement": 16,
    "vehicle_control": 16,
    "cursor_driven_interaction": 14,
    "timing_input": 14,
}
_NARRATIVE_TOPIC_MATCH_WEIGHTS: dict[str, int] = {
    "crime_heist": 14,
    "detective_mystery": 14,
    "survival_escape": 14,
    "branching_choices": 16,
    "heroic_journey": 10,
    "monster_bonding": 16,
}
_ART_STYLE_MATCH_WEIGHTS: dict[str, int] = {
    "pixel_art": 10,
    "hand_drawn": 10,
    "anime": 10,
    "stylized": 8,
    "retro": 8,
    "photorealistic": 8,
}
_VISUAL_PRESENTATION_MATCH_WEIGHTS: dict[str, int] = {
    "side_scrolling_2d": 8,
    "third_person_3d": 8,
    "isometric_view": 8,
    "top_down_view": 8,
}
_PACING_MATCH_WEIGHTS: dict[str, int] = {
    "long_form_campaign": 8,
    "fast_arcade": 8,
    "methodical_tension": 10,
    "relaxed_sandbox": 8,
}
_INTERFACE_CONTROL_MATCH_WEIGHTS: dict[str, int] = {
    "cursor_driven": 12,
    "deck_management": 14,
    "party_command": 14,
    "vehicle_control": 12,
    "timing_input": 14,
}
_SPORTS_THEME_MATCH_WEIGHTS: dict[str, int] = {
    "soccer": 16,
    "baseball": 16,
    "basketball": 16,
}
_VEHICULAR_THEME_MATCH_WEIGHTS: dict[str, int] = {
    "cars": 16,
    "motorcycles": 16,
    "spaceships": 14,
}
_SETTING_MATCH_WEIGHTS: dict[str, int] = {
    "high_fantasy": 18,
    "dark_fantasy": 18,
    "mythic": 12,
    "horror": 18,
    "sci_fi": 14,
    "cyberpunk": 14,
    "historical": 10,
    "military": 12,
}
_SUPPORTING_VALUES: frozenset[str] = frozenset(
    {
        "action",
        "adventure",
        "rpg",
        "single_player",
        "pvp",
        "buildcraft",
        "campaign",
        "dominant",
        "handcrafted_discovery",
        "open_world",
    }
)
_TONE_MATCH_WEIGHTS: dict[str, int] = {
    "heroic": 8,
    "bleak": 8,
    "melancholic": 8,
    "comedic": 6,
    "cozy": 6,
    "grotesque": 8,
}


@dataclass(frozen=True)
class TaxonomyV2EvidenceRecord:
    field: str
    value: str
    source: str
    source_field: str
    confidence: float
    evidence_text: str | None = None
    curated: bool = False
    weight: float | None = None
    conflict_group: str | None = None
    suppressed_by_rule: str | None = None


@dataclass(frozen=True)
class ArchetypeCandidate:
    archetype: str
    family: str
    score: int
    required_hits: int
    required_total: int
    preferred_hits: int
    preferred_total: int
    confidence: float


@dataclass(frozen=True)
class TaxonomyV2Result:
    version: str
    status: str
    primary_family: str | None
    primary_archetype: str | None
    secondary_archetypes: list[str]
    hard_exclusions: list[str]
    soft_penalties: list[str]
    confidence: float | None
    fingerprint: dict[str, list[str]]
    curated: bool
    evidence: list[TaxonomyV2EvidenceRecord]
    debug_payload: dict[str, Any]


@dataclass(frozen=True)
class SimilarityBreakdownV2:
    score: int
    confidence: str
    match_reasons: list[str]
    relationship: str
    derived_similarity_score: int
    shared_world_topology: list[str]
    shared_session_shape: list[str]
    shared_combat_style: list[str]
    shared_combat_structure: list[str]
    shared_mode_profile: list[str]
    shared_progression_model: list[str]
    shared_traversal_verbs: list[str]
    shared_setting: list[str]
    shared_tone: list[str]
    shared_keyword_layer: list[str]
    shared_mechanics_structure: list[str]
    shared_rules_goals: list[str]
    shared_entity_interaction: list[str]
    shared_narrative_topic: list[str]
    shared_visual_presentation: list[str]
    shared_art_style: list[str]
    shared_pacing: list[str]
    shared_interface_control: list[str]
    shared_sports_theme: list[str]
    shared_vehicular_theme: list[str]
    shared_challenge_model: list[str]
    shared_studios: list[str]


@dataclass(frozen=True)
class TaxonomyV2LabelAnalysis:
    source: str
    facet: str
    raw_label: str
    normalized_label: str
    resolved_tokens: tuple[str, ...]
    emitted_signals: tuple[str, ...]
    classification: str
    mapped: bool
    suppressed: bool
    role_tier: str | None = None
    rarity_bucket: str | None = None
    suppression_reason: str | None = None


@dataclass(frozen=True)
class TaxonomyV2BoilerplateHit:
    category: str
    segment: str
    normalized_segment: str


@dataclass(frozen=True)
class TaxonomyV2SuppressedTextSegment:
    category: str
    segment: str
    normalized_segment: str


@dataclass(frozen=True)
class TaxonomyV2NearMiss:
    archetype: str
    family: str
    closeness_score: int
    required_hits: int
    required_total: int
    preferred_hits: int
    preferred_total: int
    matched_required_axes: tuple[str, ...]
    missing_required_axes: tuple[str, ...]
    matched_preferred_axes: tuple[str, ...]


def _data_path(filename: str) -> Path:
    return Path(__file__).resolve().parent.parent / "data" / filename


def _docs_path(filename: str) -> Path:
    return Path(__file__).resolve().parent.parent.parent / "docs" / filename


def _canonical_token(value: str | None) -> str:
    normalized = normalize_taxonomy_label(value)
    if not normalized:
        return ""
    return normalized.replace(" ", "_")


def _title_parent_edition_keys(value: str | None) -> list[str]:
    normalized = normalize_taxonomy_label(value or "")
    if not normalized:
        return []

    keys: list[str] = []
    for pattern in _TITLE_EDITION_PARENT_PATTERNS:
        parent_key = " ".join(pattern.sub(" ", normalized).split())
        if parent_key and parent_key != normalized and len(parent_key.split()) >= 2:
            keys.append(parent_key)

    ordered: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def _canonical_provenance_token(value: str | None) -> str:
    if not value:
        return ""
    if "/" not in value:
        return _canonical_token(value)
    source, source_field = value.split("/", 1)
    canonical_source = _canonical_token(source)
    canonical_source_field = _canonical_token(source_field)
    if not canonical_source or not canonical_source_field:
        return ""
    return f"{canonical_source}/{canonical_source_field}"


def display_taxonomy_v2_token(value: str) -> str:
    specials = {"rpg": "RPG", "mmo": "MMO", "pvp": "PvP", "pvpve": "PvPvE"}
    if value in specials:
        return specials[value]
    return " ".join(specials.get(part, part.capitalize()) for part in value.split("_") if part)


def _render_signal(field: str, value: str) -> str:
    return f"{field}={value}"


def classify_taxonomy_v2_signal_tier(field: str, value: str) -> str:
    facet_matrix = load_facet_matrix()
    canonical_field = _canonical_token(field)
    canonical_value = _canonical_token(value)
    if canonical_field == "hard_exclusions":
        return "identity_driving"
    if canonical_field == "soft_penalties":
        return "supporting"
    supporting_values = {
        _canonical_token(item)
        for item in facet_matrix.get("supporting_values", [])
        if _canonical_token(item)
    }
    if canonical_value in supporting_values:
        return "supporting"
    field_role_defaults = {
        _canonical_token(key): value
        for key, value in (facet_matrix.get("field_role_defaults") or {}).items()
        if _canonical_token(key)
    }
    if canonical_field in field_role_defaults:
        return str(field_role_defaults[canonical_field])
    if canonical_field in {"setting", "combat_style", "combat_structure", "progression_model", "world_topology", "perspective"}:
        return "identity_driving"
    return "supporting"


def get_taxonomy_v2_source_weight(source: str, source_field: str | None = None) -> float:
    matrix = load_facet_matrix()
    source_weights = matrix.get("source_weights") or {}
    if source_field:
        source_field_key = _canonical_token(source_field)
        if source_field_key and source_field_key in source_weights:
            return float(source_weights[source_field_key])
    source_key = _canonical_token(source)
    if source_key and source_key in source_weights:
        return float(source_weights[source_key])
    return 1.0


def get_taxonomy_v2_role_weight(role_tier: str) -> float:
    matrix = load_facet_matrix()
    role_weights = matrix.get("role_weights") or {}
    return float(role_weights.get(role_tier, 1.0))


def get_taxonomy_v2_rarity_bucket(value: str) -> str | None:
    normalized = _canonical_token(value)
    if not normalized:
        return None
    source_matrix = load_source_label_matrix()
    global_buckets = (
        source_matrix.get("rarity_buckets", {}).get("global", {})
        if isinstance(source_matrix.get("rarity_buckets"), dict)
        else {}
    )
    if normalized in global_buckets:
        return str(global_buckets[normalized])
    facet_matrix = load_facet_matrix()
    value_overrides = {
        _canonical_token(key): value
        for key, value in (facet_matrix.get("value_rarity_overrides") or {}).items()
        if _canonical_token(key)
    }
    if normalized in value_overrides:
        return str(value_overrides[normalized])
    return None


def get_taxonomy_v2_rarity_weight(value: str) -> float:
    bucket = get_taxonomy_v2_rarity_bucket(value)
    if not bucket:
        return 0.0
    matrix = load_facet_matrix()
    return float((matrix.get("rarity_weights") or {}).get(bucket, 0.0))


def game_has_sufficient_taxonomy_v2_support(game: Game) -> bool:
    return (
        getattr(game, "taxonomy_v2_status", None) in TAXONOMY_V2_READY_STATUSES
        and bool(getattr(game, "taxonomy_v2_primary_archetype", None))
        and bool(getattr(game, "taxonomy_v2_fingerprint", None))
    )


def build_taxonomy_v2_fingerprint_sets(game: Game) -> dict[str, set[str]]:
    fingerprint = getattr(game, "taxonomy_v2_fingerprint", None) or {}
    return build_taxonomy_v2_fingerprint_sets_from_mapping(fingerprint)


def build_taxonomy_v2_fingerprint_sets_from_mapping(
    fingerprint: dict[str, list[str]] | None,
) -> dict[str, set[str]]:
    actual_fingerprint = fingerprint or {}
    return {
        axis: {
            _canonical_token(value)
            for value in (actual_fingerprint.get(axis) or [])
            if _canonical_token(value)
        }
        for axis in FINGERPRINT_AXES
    }


def _prefer_primary_archetype_candidate(
    candidates: list[ArchetypeCandidate],
    fingerprint: dict[str, list[str]],
) -> list[ArchetypeCandidate]:
    if len(candidates) < 2:
        return candidates

    candidates_by_archetype = {candidate.archetype: candidate for candidate in candidates}
    open_world_candidate = candidates_by_archetype.get("open_world_fantasy_action_rpg")

    fingerprint_sets = build_taxonomy_v2_fingerprint_sets_from_mapping(fingerprint)
    traversal_verbs = fingerprint_sets["traversal_verbs"]
    progression_model = fingerprint_sets["progression_model"]
    narrative_structure = fingerprint_sets["narrative_structure"]
    entity_interaction = fingerprint_sets["entity_interaction"]
    rules_goals = fingerprint_sets["rules_goals"]
    challenge_model = fingerprint_sets["challenge_model"]
    combat_structure = fingerprint_sets["combat_structure"]
    combat_style = fingerprint_sets["combat_style"]
    combat_tempo = fingerprint_sets["combat_tempo"]
    combat_presence = fingerprint_sets["combat_presence"]
    perspective = fingerprint_sets["perspective"]
    world_topology = fingerprint_sets["world_topology"]
    world_density = fingerprint_sets["world_density"]
    session_shape = fingerprint_sets["session_shape"]
    setting = fingerprint_sets["setting"]
    tone = fingerprint_sets["tone"]
    narrative_topic = fingerprint_sets["narrative_topic"]
    mechanics_structure = fingerprint_sets["mechanics_structure"]
    mode_profile = fingerprint_sets["mode_profile"]
    content_model = fingerprint_sets["content_model"]
    interface_control = fingerprint_sets["interface_control"]
    input_complexity = fingerprint_sets["input_complexity"]
    keyword_layer = fingerprint_sets["keyword_layer"]
    sports_theme = fingerprint_sets["sports_theme"]
    vehicular_theme = fingerprint_sets["vehicular_theme"]
    kingdom_decision_candidate = candidates_by_archetype.get("kingdom_decision_sim")
    beat_em_up_signals = (
        "level_based" in world_topology
        and bool(perspective & {"side_scrolling", "third_person"})
        and bool(combat_style & {"melee", "hybrid"})
        and "match_session" not in session_shape
        and (
            "combo_driven" in combat_tempo
            or bool(mode_profile & {"drop_in_coop", "party_coop"})
            or bool(combat_structure & {"crowd_control", "party_management"})
        )
    )

    if (
        keyword_layer & {"deckbuilding"}
        or progression_model & {"deck_growth"}
        or interface_control & {"deck_management"}
    ) and not sports_theme and not (
        mechanics_structure & {"match_competition"}
        or rules_goals & {"win_matches"}
        or vehicular_theme
    ):
        filtered_candidates = [
            candidate
            for candidate in candidates
            if candidate.archetype not in {"sports_sim", "realistic_racer", "arcade_racer", "pinball", "party_game"}
        ]
        if filtered_candidates != candidates:
            candidates = filtered_candidates
            if len(candidates) < 2:
                return candidates
            candidates_by_archetype = {candidate.archetype: candidate for candidate in candidates}

    preferred_archetype: str | None = None

    kingdom_decision_profile = (
        kingdom_decision_candidate is not None
        and "none" in combat_presence
        and "campaign" in session_shape
        and "authored_branching" in narrative_structure
        and bool(interface_control & {"cursor_driven"})
        and bool(entity_interaction & {"dialogue_choice"} or narrative_topic & {"branching_choices"})
        and bool(
            progression_model & {"base_growth"}
            or rules_goals & {"build_and_optimize"}
            or mechanics_structure & {"systemic_problem_solving"}
        )
        and "match_session" not in session_shape
        and not sports_theme
        and not vehicular_theme
        and not (keyword_layer & {"retail_management"})
    )
    if kingdom_decision_profile:
        preferred_archetype = "kingdom_decision_sim"

    soulslike_candidate = candidates_by_archetype.get("soulslike_action_rpg")
    soulslike_profile = (
        soulslike_candidate is not None
        and "boss_centric" in combat_structure
        and "third_person" in perspective
        and "soulslike" in challenge_model
        and "defeat_bosses" in rules_goals
        and bool(setting & {"dark_fantasy"})
        and not (
            narrative_structure & {"authored_branching", "quest_web"}
            or entity_interaction & {"dialogue_choice"}
            or narrative_topic & {"branching_choices"}
        )
    )
    if soulslike_profile:
        preferred_archetype = "soulslike_action_rpg"

    character_action_candidate = candidates_by_archetype.get("character_action")
    character_action_profile = (
        character_action_candidate is not None
        and "third_person" in perspective
        and "dominant" in combat_presence
        and bool(combat_style & {"hybrid", "melee", "ranged"})
        and bool(combat_tempo & {"twitch", "combo_driven"} or input_complexity & {"mastery_heavy"})
        and bool(input_complexity & {"mastery_heavy"} or combat_structure & {"boss_centric"})
        and "party_management" not in combat_structure
        and "match_session" not in session_shape
        and not (world_topology & {"open_world", "persistent_shared_world"})
        and not (traversal_verbs & {"climbing", "gliding", "horseback"})
        and not (challenge_model & {"soulslike"})
        and not sports_theme
        and not vehicular_theme
    )
    if character_action_profile:
        preferred_archetype = "character_action"

    cinematic_action_candidate = candidates_by_archetype.get("cinematic_action_adventure")
    authored_linear_cinematic_profile = (
        cinematic_action_candidate is not None
        and "third_person" in perspective
        and "dominant" in combat_presence
        and "authored_linear" in narrative_structure
        and bool(world_topology & {"semi_open", "level_based"} or world_density & {"setpiece_driven"})
        and bool(combat_style & {"hybrid", "melee", "ranged"})
        and "open_world" not in world_topology
        and "match_session" not in session_shape
        and not sports_theme
        and not vehicular_theme
    )
    if authored_linear_cinematic_profile and preferred_archetype is None:
        preferred_archetype = "cinematic_action_adventure"

    western_candidate = candidates_by_archetype.get("western_narrative_rpg")
    compact_topdown_adventure_signal = (
        "open_world" in world_topology
        and "isometric" in perspective
        and bool(world_density & {"handcrafted_discovery"})
        and bool(combat_presence & {"dominant", "moderate"} or combat_style & {"melee", "hybrid"})
        and bool(mechanics_structure & {"quest_exploration_loop"} or progression_model & {"quest_driven"})
        and "single_player" in mode_profile
        and "match_session" not in session_shape
        and not sports_theme
        and not vehicular_theme
    )
    western_narrative_profile = (
        western_candidate is not None
        and bool(perspective & {"third_person", "first_person", "isometric"})
        and "quest_driven" in progression_model
        and bool(
            narrative_structure & {"authored_branching", "quest_web"}
            or entity_interaction & {"dialogue_choice"}
            or narrative_topic & {"branching_choices"}
        )
        and "party_management" not in combat_structure
        and not (challenge_model & {"soulslike"})
        and not compact_topdown_adventure_signal
    )
    if western_narrative_profile:
        preferred_archetype = "western_narrative_rpg"

    western_party_action_rpg_profile = (
        western_candidate is not None
        and "open_world" in world_topology
        and "campaign" in session_shape
        and "single_player" in mode_profile
        and "party_management" in combat_structure
        and bool(combat_style & {"hybrid", "melee", "party_tactics"})
        and bool(
            mechanics_structure & {"quest_exploration_loop"}
            or rules_goals & {"solve_mysteries", "complete_quests"}
            or narrative_topic & {"detective_mystery"}
        )
        and not sports_theme
        and not vehicular_theme
        and not (entity_interaction & {"creature_collection"})
        and not (mechanics_structure & {"creature_collection"})
    )
    if western_party_action_rpg_profile:
        preferred_archetype = "western_narrative_rpg"

    party_based_crpg_candidate = candidates_by_archetype.get("party_based_crpg")
    party_based_crpg_profile = (
        party_based_crpg_candidate is not None
        and bool(perspective & {"isometric", "tactical_overhead"})
        and "campaign" in session_shape
        and "party_management" in combat_structure
        and "party_tactics" in combat_style
        and "tactical" in combat_tempo
        and bool(progression_model & {"quest_driven", "skill_tree"})
        and bool(
            entity_interaction & {"dialogue_choice", "party_control"}
            or narrative_structure & {"authored_branching"}
        )
        and not sports_theme
        and not vehicular_theme
    )
    if party_based_crpg_profile:
        preferred_archetype = "party_based_crpg"

    monster_collect_candidate = candidates_by_archetype.get("monster_collect_rpg")
    monster_collect_profile = (
        monster_collect_candidate is not None
        and "campaign" in session_shape
        and "party_management" in combat_structure
        and bool(combat_tempo & {"tactical"} or progression_model & {"skill_tree"})
        and bool(
            entity_interaction & {"creature_collection"}
            or mechanics_structure & {"creature_collection"}
            or rules_goals & {"capture_and_raise_companions"}
            or narrative_topic & {"monster_bonding"}
        )
        and not sports_theme
        and not vehicular_theme
    )
    if monster_collect_profile:
        preferred_archetype = "monster_collect_rpg"

    jrpg_story_candidate = candidates_by_archetype.get("jrpg_story_rpg")
    jrpg_story_profile = (
        jrpg_story_candidate is not None
        and "campaign" in session_shape
        and bool(combat_structure & {"party_management"})
        and bool(
            combat_tempo & {"tactical"}
            or (
                progression_model & {"skill_tree", "quest_driven"}
                and narrative_structure & {"authored_linear", "authored_branching"}
            )
        )
        and bool(progression_model & {"skill_tree", "quest_driven"})
        and bool(narrative_structure & {"authored_linear", "authored_branching"} or narrative_topic & {"heroic_journey"})
        and "match_session" not in session_shape
        and "none" not in combat_presence
        and not sports_theme
        and not vehicular_theme
        and not (world_topology & {"mission_based"})
        and not (entity_interaction & {"creature_collection"})
        and not (mechanics_structure & {"creature_collection"})
    )
    if jrpg_story_profile and preferred_archetype is None:
        preferred_archetype = "jrpg_story_rpg"

    turn_based_tactics_candidate = candidates_by_archetype.get("turn_based_tactics")
    tactical_rpg_candidate = candidates_by_archetype.get("tactical_rpg")
    bleak_horror_tactical_rpg_profile = (
        tactical_rpg_candidate is not None
        and "campaign" in session_shape
        and "party_management" in combat_structure
        and "tactical" in fingerprint_sets["combat_tempo"]
        and bool(combat_style & {"party_tactics"})
        and bool(setting & {"horror"} or tone & {"bleak", "grotesque"})
        and not (progression_model & {"skill_tree"})
        and not (mode_profile & {"drop_in_coop", "party_coop"})
        and not (world_density & {"systemic_sandbox"})
    )
    if bleak_horror_tactical_rpg_profile and preferred_archetype is None:
        preferred_archetype = "tactical_rpg"

    turn_based_dungeon_rpg_profile = (
        tactical_rpg_candidate is not None
        and "party_management" in combat_structure
        and "party_tactics" in combat_style
        and "tactical" in fingerprint_sets["combat_tempo"]
        and bool(session_shape & {"campaign", "roguelite_run"})
        and bool(world_topology & {"run_based", "mission_based"} or entity_interaction & {"inventory_loot"})
        and bool(progression_model & {"skill_tree", "buildcraft", "metaprogression"})
        and not (mode_profile & {"drop_in_coop", "party_coop"})
        and not sports_theme
        and not vehicular_theme
    )
    if turn_based_dungeon_rpg_profile and preferred_archetype in {None, "jrpg_story_rpg"}:
        preferred_archetype = "tactical_rpg"

    grim_survival_expedition_horror_profile = (
        candidates_by_archetype.get("survival_horror") is not None
        and "horror" in setting
        and "survival" in combat_style
        and bool(tone & {"bleak", "grotesque"})
        and bool(
            progression_model & {"buildcraft", "base_growth"}
            or world_density & {"systemic_sandbox"}
            or combat_structure & {"party_management"}
        )
        and bool(
            combat_style & {"party_tactics"}
            or combat_tempo & {"tactical"}
            or challenge_model & {"tactical_optimization", "sim_realism"}
        )
        and not sports_theme
        and not vehicular_theme
    )
    if grim_survival_expedition_horror_profile:
        preferred_archetype = "survival_horror"

    turn_based_tactics_profile = (
        turn_based_tactics_candidate is not None
        and tactical_rpg_candidate is not None
        and bool(perspective & {"tactical_overhead", "isometric"})
        and "party_management" in combat_structure
        and "tactical" in fingerprint_sets["combat_tempo"]
        and "party_tactics" in fingerprint_sets["combat_style"]
        and bool(
            world_topology & {"mission_based"}
            or session_shape & {"mission_session"}
            or progression_model & {"gear_chase"}
            or entity_interaction & {"inventory_loot"}
        )
        and not (
            entity_interaction & {"dialogue_choice"}
            or narrative_structure & {"authored_branching"}
            or narrative_topic & {"branching_choices"}
        )
    )
    if turn_based_tactics_profile and preferred_archetype is None:
        preferred_archetype = "turn_based_tactics"

    rhythm_candidate = candidates_by_archetype.get("rhythm_game")
    rhythm_profile = (
        rhythm_candidate is not None
        and "match_session" in session_shape
        and bool(
            keyword_layer & {"rhythm"}
            or mechanics_structure & {"rhythm_timing"}
            or rules_goals & {"hit_beats"}
            or interface_control & {"timing_input"}
        )
    )
    if rhythm_profile and preferred_archetype is None:
        preferred_archetype = "rhythm_game"

    card_battler_candidate = candidates_by_archetype.get("card_battler")
    card_battler_profile = (
        card_battler_candidate is not None
        and bool(
            keyword_layer & {"deckbuilding"}
            or progression_model & {"deck_growth"}
            or interface_control & {"deck_management"}
            or mechanics_structure & {"deck_construction"}
        )
        and "tactical" in combat_tempo
        and bool(session_shape & {"roguelite_run", "match_session"} or world_topology & {"run_based"})
        and not sports_theme
        and not vehicular_theme
        and "dominant" not in combat_presence
    )
    if card_battler_profile and preferred_archetype is None:
        preferred_archetype = "card_battler"

    tower_defense_strategy_candidate = candidates_by_archetype.get("tower_defense_strategy")
    tower_defense_strategy_profile = (
        tower_defense_strategy_candidate is not None
        and "tactical_optimization" in challenge_model
        and bool(rules_goals & {"build_and_optimize", "survive_waves"})
        and bool(combat_structure & {"crowd_control"} or mechanics_structure & {"settlement_building"})
        and "first_person" not in perspective
        and not (mode_profile & {"drop_in_coop", "party_coop"} and combat_presence & {"dominant"})
        and not (combat_style & {"shooter", "melee", "hybrid"} and combat_tempo & {"fast", "twitch"})
        and not sports_theme
        and not vehicular_theme
    )
    if tower_defense_strategy_profile and preferred_archetype is None:
        preferred_archetype = "tower_defense_strategy"

    precision_platformer_candidate = candidates_by_archetype.get("precision_platformer")
    precision_platformer_profile = (
        precision_platformer_candidate is not None
        and "level_based" in world_topology
        and "platforming" in traversal_verbs
        and "precision_platforming" in challenge_model
        and bool(perspective & {"side_scrolling"})
        and "match_session" not in session_shape
        and (
            "dominant" not in combat_presence
            or (
                not (combat_structure & {"crowd_control", "boss_centric"})
                and not (combat_style & {"melee", "hybrid", "magic", "ranged"})
            )
        )
        and not sports_theme
    )
    if precision_platformer_profile and preferred_archetype is None:
        preferred_archetype = "precision_platformer"

    action_platformer_candidate = candidates_by_archetype.get("action_platformer")
    action_platformer_profile = (
        action_platformer_candidate is not None
        and "level_based" in world_topology
        and "platforming" in traversal_verbs
        and bool(perspective & {"side_scrolling", "third_person"})
        and bool(combat_presence & {"dominant", "light", "moderate"})
        and bool(combat_structure & {"encounter_driven", "crowd_control", "boss_centric"})
        and "match_session" not in session_shape
        and not sports_theme
        and not beat_em_up_signals
    )
    if action_platformer_profile and preferred_archetype is None:
        preferred_archetype = "action_platformer"

    metroidvania_candidate = candidates_by_archetype.get("metroidvania")
    metroidvania_profile = (
        metroidvania_candidate is not None
        and "single_player" in mode_profile
        and "match_session" not in session_shape
        and bool(traversal_verbs & {"platforming", "gliding"})
        and bool(
            world_topology & {"semi_open", "level_based"}
            or world_density & {"handcrafted_discovery"}
            or progression_model & {"metaprogression", "skill_tree"}
        )
        and not beat_em_up_signals
        and not sports_theme
    )
    if metroidvania_profile and preferred_archetype is None:
        preferred_archetype = "metroidvania"

    exploration_survival_candidate = candidates_by_archetype.get("exploration_survival_adventure")
    puzzle_exploration_adventure_profile = (
        exploration_survival_candidate is not None
        and bool(world_topology & {"open_world", "semi_open"})
        and bool(challenge_model & {"puzzle_gating"})
        and bool(mechanics_structure & {"environmental_puzzle_solving", "systemic_problem_solving"})
        and bool(progression_model & {"quest_driven", "buildcraft", "metaprogression"})
        and "campaign" in session_shape
        and not sports_theme
        and not vehicular_theme
        and not (setting & {"horror"})
    )
    if puzzle_exploration_adventure_profile:
        preferred_archetype = "exploration_survival_adventure"

    sports_candidate = candidates_by_archetype.get("sports_sim")
    sports_profile = (
        sports_candidate is not None
        and "match_session" in session_shape
        and bool(mode_profile & {"pvp", "single_player"} or sports_theme)
        and "party_coop" not in mode_profile
        and bool(
            sports_theme
            or (
                (
                    "match_competition" in mechanics_structure
                    or "win_matches" in rules_goals
                )
                and "dominant" not in combat_presence
                and not (fingerprint_sets["combat_style"] & {"shooter", "stealth", "melee", "magic", "hybrid"})
            )
        )
    )
    if sports_profile and preferred_archetype is None:
        preferred_archetype = "sports_sim"

    creative_sandbox_candidate = candidates_by_archetype.get("creative_sandbox_adventure")
    creative_sandbox_profile = (
        creative_sandbox_candidate is not None
        and bool(world_density & {"systemic_sandbox"})
        and bool(progression_model & {"buildcraft"})
        and bool(
            entity_interaction & {"construction_placement"}
            or mechanics_structure & {"settlement_building"}
        )
        and bool(mode_profile & {"single_player", "drop_in_coop", "party_coop", "mmo"} or session_shape & {"sandbox_loop"})
        and "match_session" not in session_shape
        and not (
            perspective & {"third_person"}
            and (
                combat_style & {"melee", "hybrid", "ranged", "magic"}
                or (
                    mode_profile & {"mmo"}
                    and input_complexity & {"mastery_heavy"}
                )
            )
        )
        and not sports_theme
        and not vehicular_theme
    )
    if creative_sandbox_profile:
        preferred_archetype = "creative_sandbox_adventure"

    mischief_sandbox_candidate = candidates_by_archetype.get("mischief_sandbox_sim")
    mischief_sandbox_profile = (
        mischief_sandbox_candidate is not None
        and bool(world_density & {"systemic_sandbox"})
        and bool(mechanics_structure & {"systemic_problem_solving"})
        and bool(rules_goals & {"cause_mischief"})
        and "match_session" not in session_shape
        and not sports_theme
        and not vehicular_theme
    )
    if mischief_sandbox_profile:
        preferred_archetype = "mischief_sandbox_sim"

    colony_sim_candidate = candidates_by_archetype.get("colony_sim")
    colony_management_hybrid_profile = (
        colony_sim_candidate is not None
        and "colony_growth" in progression_model
        and bool(world_density & {"systemic_sandbox", "city_dense"})
        and bool(rules_goals & {"build_and_optimize"} or mechanics_structure & {"settlement_building", "real_time_command"})
        and bool(challenge_model & {"sim_realism", "tactical_optimization"} or mechanics_structure & {"systemic_problem_solving"})
        and "mmo" not in mode_profile
        and not (candidates_by_archetype.get("management_tycoon") is not None and "first_person" not in perspective)
        and not sports_theme
        and not vehicular_theme
    )
    if colony_management_hybrid_profile:
        preferred_archetype = "colony_sim"

    roguelite_fps_candidate = candidates_by_archetype.get("roguelite_fps")
    roguelite_fps_profile = (
        roguelite_fps_candidate is not None
        and "first_person" in perspective
        and "shooter" in combat_style
        and "run_based" in world_topology
        and "roguelite_run" in session_shape
        and "dominant" in combat_presence
        and "match_session" not in session_shape
        and not sports_theme
        and not vehicular_theme
        and not colony_management_hybrid_profile
    )
    if roguelite_fps_profile:
        preferred_archetype = "roguelite_fps"

    shoot_em_up_candidate = candidates_by_archetype.get("shoot_em_up")
    shoot_em_up_profile = (
        shoot_em_up_candidate is not None
        and "shooter" in combat_style
        and "twitch" in combat_tempo
        and "dominant" in combat_presence
        and bool(session_shape & {"match_session", "campaign"})
        and "first_person" not in perspective
        and not (setting & {"military", "modern"})
        and not sports_theme
        and not vehicular_theme
    )
    if shoot_em_up_profile:
        preferred_archetype = "shoot_em_up"

    co_op_action_roguelite_candidate = candidates_by_archetype.get("co_op_action_roguelite")
    co_op_action_roguelite_profile = (
        co_op_action_roguelite_candidate is not None
        and "run_based" in world_topology
        and "roguelite_run" in session_shape
        and "dominant" in combat_presence
        and bool(
            mode_profile & {"drop_in_coop", "party_coop"}
            or (
                "single_player" in mode_profile
                and "first_person" not in perspective
                and bool(combat_tempo & {"fast", "combo_driven"} or combat_structure & {"boss_centric", "encounter_driven"})
            )
        )
        and bool(
            combat_style & {"melee", "hybrid", "shooter"}
            or (
                mode_profile & {"drop_in_coop", "party_coop"}
                and (combat_structure & {"crowd_control", "encounter_driven"} or rules_goals & {"survive_waves"})
            )
        )
        and bool(progression_model & {"metaprogression", "buildcraft", "gear_chase"})
        and "match_session" not in session_shape
        and not sports_theme
        and not vehicular_theme
    )
    if co_op_action_roguelite_profile and preferred_archetype in {None, "loot_action_rpg"}:
        preferred_archetype = "co_op_action_roguelite"

    loot_action_rpg_candidate = candidates_by_archetype.get("loot_action_rpg")
    loot_action_rpg_profile = (
        loot_action_rpg_candidate is not None
        and "dominant" in combat_presence
        and bool(
            combat_style & {"hybrid", "melee", "ranged", "magic"}
            or combat_structure & {"encounter_driven", "crowd_control", "boss_centric"}
        )
        and bool(content_model & {"premium_replayable", "live_service", "mmo_persistent"})
        and bool(progression_model & {"buildcraft", "gear_chase", "loot_rarity", "skill_tree", "base_growth"})
        and bool(
            entity_interaction & {"inventory_loot", "construction_placement"}
            or rules_goals & {"build_and_optimize", "complete_quests", "defeat_bosses"}
        )
        and bool(mode_profile & {"single_player", "drop_in_coop", "party_coop"})
        and "match_session" not in session_shape
        and not sports_theme
        and not vehicular_theme
        and not (
            "open_world" in world_topology
            and (
                bool(traversal_verbs & {"horseback", "climbing", "gliding"})
                or (
                    "quest_driven" in progression_model
                    and (
                        "complete_quests" in rules_goals
                        or bool(keyword_layer & {"open_world_exploration"})
                    )
                )
            )
        )
    )
    loot_action_rpg_supersede_story_profile = (
        loot_action_rpg_profile
        and (
            "drop_in_coop" in mode_profile
            or "construction_placement" in entity_interaction
            or bool(rules_goals & {"build_and_optimize", "survive_waves"})
            or bool(combat_structure & {"crowd_control"})
        )
    )
    if loot_action_rpg_profile and (
        preferred_archetype is None
        or (
            preferred_archetype in {"jrpg_story_rpg", "turn_based_tactics", "monster_collect_rpg"}
            and loot_action_rpg_supersede_story_profile
        )
    ):
        preferred_archetype = "loot_action_rpg"

    military_fps_candidate = candidates_by_archetype.get("military_fps")
    military_fps_profile = (
        military_fps_candidate is not None
        and "first_person" in perspective
        and "shooter" in combat_style
        and bool(combat_tempo & {"twitch", "tactical"})
        and "mission_based" in world_topology
        and bool(setting & {"military", "modern"})
        and bool(mode_profile & {"pvp", "drop_in_coop"} or session_shape & {"mission_session", "match_session"})
    )
    if military_fps_profile and preferred_archetype is None:
        preferred_archetype = "military_fps"

    survival_horror_candidate = candidates_by_archetype.get("survival_horror")
    psychological_horror_candidate = candidates_by_archetype.get("psychological_horror")
    action_horror_candidate = candidates_by_archetype.get("action_horror")
    co_op_horror_candidate = candidates_by_archetype.get("co_op_horror")
    survival_horror_profile = (
        survival_horror_candidate is not None
        and psychological_horror_candidate is not None
        and "horror" in setting
        and "survival" in fingerprint_sets["combat_style"]
        and "dominant" not in combat_presence
        and "encounter_driven" in combat_structure
        and bool(
            mechanics_structure & {"stealth_infiltration", "environmental_puzzle_solving"}
            or rules_goals & {"infiltrate_avoid_detection", "solve_mysteries"}
            or narrative_topic & {"survival_escape", "detective_mystery"}
        )
    )
    if survival_horror_profile and preferred_archetype is None:
        preferred_archetype = "survival_horror"

    co_op_horror_profile = (
        co_op_horror_candidate is not None
        and "horror" in setting
        and "shooter" in combat_style
        and "dominant" in combat_presence
        and bool(mode_profile & {"drop_in_coop", "party_coop"})
        and bool(combat_structure & {"crowd_control", "encounter_driven"})
        and bool(session_shape & {"campaign", "mission_session"} or "match_session" not in session_shape)
    )
    if co_op_horror_profile and preferred_archetype is None:
        preferred_archetype = "co_op_horror"

    psychological_horror_profile = (
        psychological_horror_candidate is not None
        and "horror" in setting
        and bool(tone & {"bleak", "grotesque", "melancholic"})
        and "dominant" not in combat_presence
        and bool(perspective & {"first_person", "third_person"})
        and "match_session" not in session_shape
        and bool(
            keyword_layer & {"psychological_horror"}
            or
            narrative_topic & {"survival_escape", "detective_mystery"}
            or narrative_structure & {"authored_linear", "authored_branching"}
        )
    )
    if psychological_horror_profile and preferred_archetype is None:
        preferred_archetype = "psychological_horror"

    action_horror_profile = (
        action_horror_candidate is not None
        and "horror" in setting
        and "dominant" in combat_presence
        and bool(combat_style & {"shooter", "melee", "hybrid", "survival"})
        and bool(combat_structure & {"crowd_control", "encounter_driven", "boss_centric"})
        and "match_session" not in session_shape
    )
    if action_horror_profile and preferred_archetype is None:
        preferred_archetype = "action_horror"

    physics_roguelite_strategy_candidate = candidates_by_archetype.get("physics_roguelite_strategy")
    merge_puzzle_candidate = candidates_by_archetype.get("merge_puzzle")
    narrative_exploration_candidate = candidates_by_archetype.get("narrative_exploration_adventure")
    cinematic_puzzle_candidate = candidates_by_archetype.get("cinematic_puzzle_adventure")
    hidden_object_candidate = candidates_by_archetype.get("hidden_object_puzzle")
    visual_novel_candidate = candidates_by_archetype.get("visual_novel")
    narrative_exploration_profile = (
        narrative_exploration_candidate is not None
        and "campaign" in session_shape
        and "none" in combat_presence
        and "narrative_exploration" in keyword_layer
        and bool(narrative_structure & {"authored_linear", "authored_branching"})
        and "match_session" not in session_shape
        and not sports_theme
        and not vehicular_theme
    )
    if narrative_exploration_profile and preferred_archetype is None:
        preferred_archetype = "narrative_exploration_adventure"

    cinematic_puzzle_profile = (
        cinematic_puzzle_candidate is not None
        and "campaign" in session_shape
        and "none" in combat_presence
        and "puzzle_gating" in challenge_model
        and bool(narrative_structure & {"authored_linear", "authored_branching"})
        and bool(
            mechanics_structure & {"environmental_puzzle_solving", "quest_exploration_loop"}
            or world_density & {"setpiece_driven", "handcrafted_discovery"}
        )
        and not (rules_goals & {"solve_mysteries"})
        and "match_session" not in session_shape
        and not sports_theme
        and not vehicular_theme
    )
    if cinematic_puzzle_profile and preferred_archetype is None:
        preferred_archetype = "cinematic_puzzle_adventure"

    visual_novel_profile = (
        visual_novel_candidate is not None
        and "none" in combat_presence
        and bool(narrative_structure & {"authored_linear", "authored_branching"})
        and bool(
            entity_interaction & {"dialogue_choice"}
            or narrative_structure & {"authored_branching"}
            or narrative_topic & {"interpersonal_drama", "branching_choices"}
            or (
                bool(narrative_topic & {"detective_mystery"} or rules_goals & {"solve_mysteries"})
                and not (mechanics_structure & {"environmental_puzzle_solving", "quest_exploration_loop"})
                and not (world_density & {"setpiece_driven", "handcrafted_discovery"})
            )
        )
        and "sandbox_loop" not in session_shape
        and "relationship_social" not in progression_model
        and "dominant" not in combat_presence
    )
    if visual_novel_profile and preferred_archetype in {None, "cinematic_puzzle_adventure"}:
        preferred_archetype = "visual_novel"

    physics_roguelite_strategy_profile = (
        physics_roguelite_strategy_candidate is not None
        and "run_based" in world_topology
        and "roguelite_run" in session_shape
        and "buildcraft" in progression_model
        and "tactical_optimization" in challenge_model
        and "physics_board_strategy" in keyword_layer
        and bool(mechanics_structure & {"systemic_problem_solving", "score_attack"})
    )
    if physics_roguelite_strategy_profile and preferred_archetype is None:
        preferred_archetype = "physics_roguelite_strategy"

    merge_puzzle_profile = (
        merge_puzzle_candidate is not None
        and "match_session" in session_shape
        and "puzzle_gating" in challenge_model
        and "none" in combat_presence
        and "build_and_optimize" in rules_goals
        and bool(mechanics_structure & {"systemic_problem_solving", "score_attack"})
    )
    if merge_puzzle_profile and preferred_archetype is None:
        preferred_archetype = "merge_puzzle"

    hidden_object_profile = (
        hidden_object_candidate is not None
        and "puzzle_gating" in challenge_model
        and "none" in combat_presence
        and bool(
            keyword_layer & {"point_and_click"}
            or mechanics_structure & {"environmental_puzzle_solving", "systemic_problem_solving"}
        )
        and bool(
            rules_goals & {"solve_mysteries"}
            or narrative_topic & {"detective_mystery"}
            or rules_goals & {"build_and_optimize"}
            or visual_novel_candidate is not None
        )
    )
    if hidden_object_profile and preferred_archetype is None:
        preferred_archetype = "hidden_object_puzzle"

    life_sim_candidate = candidates_by_archetype.get("life_sim")
    farming_sim_candidate = candidates_by_archetype.get("farming_sim")
    management_tycoon_candidate = candidates_by_archetype.get("management_tycoon")
    farming_sim_profile = (
        farming_sim_candidate is not None
        and "base_growth" in progression_model
        and bool(tone & {"cozy", "whimsical"})
        and "dominant" not in combat_presence
        and bool(world_density & {"sandbox_light", "handcrafted_discovery", "systemic_sandbox"})
        and bool(session_shape & {"sandbox_loop", "campaign"})
        and not sports_theme
        and not vehicular_theme
    )
    if farming_sim_profile and preferred_archetype is None:
        preferred_archetype = "farming_sim"

    life_sim_profile = (
        life_sim_candidate is not None
        and farming_sim_candidate is not None
        and "relationship_social" in progression_model
        and bool(tone & {"cozy", "whimsical"})
        and "dominant" not in combat_presence
        and "base_growth" not in progression_model
        and bool(
            fingerprint_sets["interface_control"] & {"cursor_driven"}
            or entity_interaction & {"dialogue_choice", "cursor_driven_interaction"}
            or narrative_structure & {"authored_branching"}
        )
    )
    if life_sim_profile and preferred_archetype is None:
        preferred_archetype = "life_sim"

    management_tycoon_profile = (
        management_tycoon_candidate is not None
        and ("base_growth" in progression_model or keyword_layer & {"retail_management"})
        and (
            "none" in combat_presence
            or (
                keyword_layer & {"retail_management"}
                and "dominant" not in combat_presence
            )
        )
        and bool(session_shape & {"sandbox_loop", "campaign"})
        and bool(rules_goals & {"build_and_optimize"} or mechanics_structure & {"systemic_problem_solving"})
        and bool(world_density & {"systemic_sandbox", "sandbox_light"})
        and not vehicular_theme
        and not (interface_control & {"vehicle_control"})
        and "open_world_exploration" not in keyword_layer
    )
    if management_tycoon_profile and preferred_archetype is None:
        preferred_archetype = "management_tycoon"

    cozy_exploration_candidate = candidates_by_archetype.get("cozy_exploration_adventure")
    cozy_exploration_profile = (
        cozy_exploration_candidate is not None
        and bool(world_topology & {"open_world", "semi_open"})
        and bool(world_density & {"handcrafted_discovery", "sandbox_light"})
        and bool(tone & {"cozy", "whimsical"})
        and "dominant" not in combat_presence
        and bool(
            traversal_verbs & {"climbing", "gliding", "platforming"}
            or mechanics_structure & {"quest_exploration_loop", "environmental_puzzle_solving"}
            or entity_interaction & {"relationship_social"}
        )
        and not sports_theme
        and not vehicular_theme
        and "match_session" not in session_shape
        and "mmo" not in mode_profile
    )
    if cozy_exploration_profile and preferred_archetype in {None, "metroidvania", "action_platformer", "3d_collectathon"}:
        preferred_archetype = "cozy_exploration_adventure"

    open_world_fantasy_profile = (
        open_world_candidate is not None
        and
        "open_world" in world_topology
        and bool(setting & {"high_fantasy", "dark_fantasy", "mythic"})
        and ("third_person" in perspective or bool(traversal_verbs & {"horseback", "climbing", "gliding"}))
        and (
            "dominant" in combat_presence
            or bool(combat_structure & {"boss_centric", "encounter_driven"})
            or bool(rules_goals & {"complete_quests", "defeat_bosses"})
        )
        and (
            bool(traversal_verbs & {"horseback", "climbing", "gliding"})
            or "quest_driven" in progression_model
            or "complete_quests" in rules_goals
        )
        and "historical" not in setting
    )
    if open_world_fantasy_profile and preferred_archetype is None:
        preferred_archetype = "open_world_fantasy_action_rpg"

    three_d_collectathon_candidate = candidates_by_archetype.get("3d_collectathon")
    three_d_collectathon_profile = (
        three_d_collectathon_candidate is not None
        and bool(world_topology & {"open_world", "level_based"})
        and bool(traversal_verbs & {"platforming", "parkour", "climbing"})
        and bool(perspective & {"third_person", "first_person", "vr"})
        and "persistent_shared_world" not in world_topology
        and "mmo" not in mode_profile
        and "quest_driven" not in progression_model
        and "dark_fantasy" not in setting
        and "dialogue_choice" not in entity_interaction
        and "cause_mischief" not in rules_goals
        and "dominant" not in combat_presence
        and "match_session" not in session_shape
    )
    if three_d_collectathon_profile and preferred_archetype != "cozy_exploration_adventure":
        preferred_archetype = "3d_collectathon"

    open_world_action_candidate = candidates_by_archetype.get("open_world_action_adventure")
    compact_topdown_action_profile = open_world_action_candidate is not None and compact_topdown_adventure_signal
    open_world_action_profile = (
        open_world_action_candidate is not None
        and not open_world_fantasy_profile
        and (
            (
                "open_world" in world_topology
                and "third_person" in perspective
            )
            or compact_topdown_action_profile
        )
        and "party_management" not in combat_structure
        and ("dialogue_choice" not in entity_interaction or compact_topdown_action_profile)
        and not (setting & {"dark_fantasy"} and "soulslike" in challenge_model)
        and not (traversal_verbs & {"horseback", "climbing", "gliding"})
        and (
            compact_topdown_action_profile
            or
            "authored_linear" in narrative_structure
            or (
                "quest_driven" not in progression_model
                and "complete_quests" not in rules_goals
            )
        )
    )
    if open_world_action_profile:
        preferred_archetype = "open_world_action_adventure"

    beat_em_up_candidate = candidates_by_archetype.get("beat_em_up")
    beat_em_up_profile = (
        beat_em_up_candidate is not None
        and action_platformer_candidate is not None
        and "dominant" in combat_presence
        and beat_em_up_signals
        and bool(mode_profile & {"drop_in_coop", "party_coop"} or combat_structure & {"encounter_driven", "party_management"})
    )
    if beat_em_up_profile and (
        preferred_archetype is None
        or preferred_archetype in {"action_horror", "jrpg_story_rpg", "traditional_fighter"}
    ):
        preferred_archetype = "beat_em_up"

    if (
        beat_em_up_candidate is not None
        and "open_world" in world_topology
        and traversal_verbs & {"gliding", "platforming"}
        and "match_session" not in session_shape
        and preferred_archetype != "cozy_exploration_adventure"
    ):
        if open_world_action_candidate is not None:
            preferred_archetype = "open_world_action_adventure"
        elif three_d_collectathon_candidate is not None:
            preferred_archetype = "3d_collectathon"

    if not preferred_archetype:
        return candidates

    preferred_candidate = candidates_by_archetype.get(preferred_archetype)
    if preferred_candidate is None:
        return candidates

    return [preferred_candidate] + [
        candidate for candidate in candidates if candidate.archetype != preferred_archetype
    ]


def get_taxonomy_v2_allowed_archetypes(game: Game) -> set[str]:
    primary = _canonical_token(getattr(game, "taxonomy_v2_primary_archetype", None))
    if not primary:
        return set()
    graph = load_connection_matrix()
    node = graph.get("nodes", {}).get(primary, {})
    allowed = {primary}
    allowed.update(_canonical_token(value) for value in node.get("strong_neighbors", []) if _canonical_token(value))
    allowed.update(_canonical_token(value) for value in node.get("adjacent_neighbors", []) if _canonical_token(value))
    for bridge in node.get("bridge_neighbors", []) or []:
        target = _canonical_token(bridge.get("target"))
        if target:
            allowed.add(target)
    allowed.update(_canonical_token(value) for value in getattr(game, "taxonomy_v2_secondary_archetypes", None) or [] if _canonical_token(value))
    return allowed


def _build_bridge_context(
    *,
    anchor_fingerprint: dict[str, set[str]],
    candidate_fingerprint: dict[str, set[str]],
    shared_world_topology: list[str],
    shared_combat_style: list[str],
    shared_combat_structure: list[str],
    shared_progression_model: list[str],
    shared_traversal_verbs: list[str],
    shared_setting: list[str],
    shared_tone: list[str],
    shared_perspective: list[str],
    shared_keyword_layer: list[str],
    shared_mechanics_structure: list[str],
    shared_rules_goals: list[str],
    shared_entity_interaction: list[str],
    shared_narrative_topic: list[str],
) -> dict[str, bool]:
    return {
        "shared_world_topology": bool(shared_world_topology),
        "shared_combat_style": bool(shared_combat_style),
        "shared_combat_structure": bool(shared_combat_structure),
        "shared_combat_style_or_structure": bool(shared_combat_style or shared_combat_structure),
        "shared_progression_model": bool(shared_progression_model),
        "shared_traversal_verbs": bool(shared_traversal_verbs),
        "shared_setting": bool(shared_setting),
        "shared_tone": bool(shared_tone),
        "shared_perspective": bool(shared_perspective),
        "shared_keyword_layer": bool(shared_keyword_layer),
        "shared_mechanics_structure": bool(shared_mechanics_structure),
        "shared_rules_goals": bool(shared_rules_goals),
        "shared_entity_interaction": bool(shared_entity_interaction),
        "shared_narrative_topic": bool(shared_narrative_topic),
        "candidate_persistent_shared_world": "persistent_shared_world" in candidate_fingerprint["world_topology"],
        "candidate_mmo": "mmo" in candidate_fingerprint["mode_profile"],
        "anchor_persistent_shared_world": "persistent_shared_world" in anchor_fingerprint["world_topology"],
    }


def _bridge_condition_matches(
    condition: str,
    context: dict[str, bool],
    *,
    shared_progression_model: list[str],
    shared_rules_goals: list[str],
    shared_entity_interaction: list[str],
    shared_narrative_topic: list[str],
    shared_combat_structure: list[str],
    shared_challenge_model: list[str],
) -> bool:
    normalized = _canonical_token(condition)
    if not normalized:
        return False
    if ":" not in normalized:
        return bool(context.get(normalized))
    scope, value = normalized.split(":", 1)
    token = _canonical_token(value)
    mapping = {
        "shared_progression_model": set(shared_progression_model),
        "shared_rules_goals": set(shared_rules_goals),
        "shared_entity_interaction": set(shared_entity_interaction),
        "shared_narrative_topic": set(shared_narrative_topic),
        "shared_combat_structure": set(shared_combat_structure),
        "shared_challenge_model": set(shared_challenge_model),
    }
    return token in mapping.get(scope, set())


def _resolve_connection_relationship(
    *,
    anchor_archetype: str,
    candidate_archetype: str,
    candidate_secondaries: set[str],
    anchor_fingerprint: dict[str, set[str]],
    candidate_fingerprint: dict[str, set[str]],
    shared_world_topology: list[str],
    shared_combat_style: list[str],
    shared_combat_structure: list[str],
    shared_progression_model: list[str],
    shared_traversal_verbs: list[str],
    shared_setting: list[str],
    shared_tone: list[str],
    shared_perspective: list[str],
    shared_keyword_layer: list[str],
    shared_mechanics_structure: list[str],
    shared_rules_goals: list[str],
    shared_entity_interaction: list[str],
    shared_narrative_topic: list[str],
    shared_challenge_model: list[str],
) -> str | None:
    connection_matrix = load_connection_matrix()
    anchor_node = connection_matrix.get("nodes", {}).get(anchor_archetype, {})
    strong_neighbors = {_canonical_token(value) for value in anchor_node.get("strong_neighbors", []) if _canonical_token(value)}
    adjacent_neighbors = {_canonical_token(value) for value in anchor_node.get("adjacent_neighbors", []) if _canonical_token(value)}
    if candidate_archetype == anchor_archetype:
        return "same"
    if candidate_archetype in strong_neighbors:
        return "strong_neighbor"
    if candidate_archetype in adjacent_neighbors:
        return "adjacent_neighbor"
    if candidate_secondaries & strong_neighbors:
        return "strong_secondary"
    if candidate_secondaries & adjacent_neighbors:
        return "adjacent_secondary"

    context = _build_bridge_context(
        anchor_fingerprint=anchor_fingerprint,
        candidate_fingerprint=candidate_fingerprint,
        shared_world_topology=shared_world_topology,
        shared_combat_style=shared_combat_style,
        shared_combat_structure=shared_combat_structure,
        shared_progression_model=shared_progression_model,
        shared_traversal_verbs=shared_traversal_verbs,
        shared_setting=shared_setting,
        shared_tone=shared_tone,
        shared_perspective=shared_perspective,
        shared_keyword_layer=shared_keyword_layer,
        shared_mechanics_structure=shared_mechanics_structure,
        shared_rules_goals=shared_rules_goals,
        shared_entity_interaction=shared_entity_interaction,
        shared_narrative_topic=shared_narrative_topic,
    )

    for bridge in anchor_node.get("bridge_neighbors", []) or []:
        target = _canonical_token(bridge.get("target"))
        if target not in {candidate_archetype, *candidate_secondaries}:
            continue
        required_all = [
            item
            for item in bridge.get("required_all", [])
            if isinstance(item, str) and item.strip()
        ]
        required_any = [
            item
            for item in bridge.get("required_any", [])
            if isinstance(item, str) and item.strip()
        ]
        if required_all and not all(
            _bridge_condition_matches(
                item,
                context,
                shared_progression_model=shared_progression_model,
                shared_rules_goals=shared_rules_goals,
                shared_entity_interaction=shared_entity_interaction,
                shared_narrative_topic=shared_narrative_topic,
                shared_combat_structure=shared_combat_structure,
                shared_challenge_model=shared_challenge_model,
            )
            for item in required_all
        ):
            continue
        if required_any and not any(
            _bridge_condition_matches(
                item,
                context,
                shared_progression_model=shared_progression_model,
                shared_rules_goals=shared_rules_goals,
                shared_entity_interaction=shared_entity_interaction,
                shared_narrative_topic=shared_narrative_topic,
                shared_combat_structure=shared_combat_structure,
                shared_challenge_model=shared_challenge_model,
            )
            for item in required_any
        ):
            continue
        return "bridge_secondary" if target in candidate_secondaries and target != candidate_archetype else "bridge_neighbor"
    return None


def _quantize_decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def clean_taxonomy_v2_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = unescape(value)
    cleaned = re.sub(r"</p\s*>", "\n\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</li\s*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    cleaned = _HTML_TAG_RE.sub(" ", cleaned)
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r" ?\n ?", "\n", cleaned)
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    cleaned = cleaned.strip()
    if len(cleaned) < 40:
        return None
    return cleaned[:8000]


def split_taxonomy_v2_text_segments(text: str | None) -> list[str]:
    cleaned = clean_taxonomy_v2_text(text)
    if not cleaned:
        return []
    segments = [segment.strip() for segment in _TEXT_SEGMENT_SPLIT_RE.split(cleaned) if segment.strip()]
    return [segment for segment in segments if len(segment) >= 24]


def _detect_taxonomy_v2_low_signal_segments(text: str | None) -> list[TaxonomyV2SuppressedTextSegment]:
    _, low_signal_patterns, high_signal_patterns = _compiled_noise_patterns()
    hits: list[TaxonomyV2SuppressedTextSegment] = []
    seen: set[tuple[str, str]] = set()
    for segment in split_taxonomy_v2_text_segments(text):
        normalized_segment = normalize_taxonomy_label(segment)
        if not normalized_segment:
            continue
        has_high_signal = any(pattern.search(normalized_segment) for pattern in high_signal_patterns)
        if has_high_signal:
            continue
        for category, pattern in low_signal_patterns:
            if not pattern.search(normalized_segment):
                continue
            marker = (category, normalized_segment)
            if marker in seen:
                break
            seen.add(marker)
            hits.append(
                TaxonomyV2SuppressedTextSegment(
                    category=category,
                    segment=segment,
                    normalized_segment=normalized_segment,
                )
            )
            break
    return hits


def detect_taxonomy_v2_boilerplate_segments(text: str | None) -> list[TaxonomyV2BoilerplateHit]:
    boilerplate_patterns, _, _ = _compiled_noise_patterns()
    hits: list[TaxonomyV2BoilerplateHit] = []
    seen: set[tuple[str, str]] = set()
    for segment in split_taxonomy_v2_text_segments(text):
        normalized_segment = normalize_taxonomy_label(segment)
        if not normalized_segment:
            continue
        for category, pattern in boilerplate_patterns:
            if not pattern.search(normalized_segment):
                continue
            marker = (category, normalized_segment)
            if marker in seen:
                break
            seen.add(marker)
            hits.append(
                TaxonomyV2BoilerplateHit(
                    category=category,
                    segment=segment,
                    normalized_segment=normalized_segment,
                )
            )
            break
    return hits


def strip_taxonomy_v2_noise_segments(text: str | None) -> str | None:
    if not text:
        return None
    blocked_segments = {
        hit.normalized_segment
        for hit in detect_taxonomy_v2_boilerplate_segments(text)
    }
    blocked_segments.update(
        hit.normalized_segment
        for hit in _detect_taxonomy_v2_low_signal_segments(text)
    )

    kept_segments: list[str] = []
    seen: set[str] = set()
    for segment in split_taxonomy_v2_text_segments(text):
        raw_segment = segment.strip()
        normalized_segment = normalize_taxonomy_label(raw_segment)
        if re.search(r"\babout the game\b", normalized_segment):
            # Steam store pages often lead with Deluxe/bonus-item boilerplate and
            # only begin the actual description after "About the Game".
            kept_segments.clear()
            seen.clear()
            raw_segment = re.sub(r"(?i)\babout the game\b[:\s-]*", "", raw_segment).strip()
            normalized_segment = normalize_taxonomy_label(raw_segment)
        if not normalized_segment or normalized_segment in blocked_segments:
            continue
        if normalized_segment in seen:
            continue
        seen.add(normalized_segment)
        kept_segments.append(raw_segment)

    if not kept_segments:
        return clean_taxonomy_v2_text(text)
    return "\n\n".join(kept_segments)


def get_taxonomy_v2_source_label_suppression(
    *,
    source: str,
    facet: str,
    normalized_label: str,
) -> str | None:
    _label, classification = classify_taxonomy_v2_source_label(
        source=source,
        facet=facet,
        raw_label=normalized_label,
        normalized_label=normalized_label,
    )
    if classification == "suppressed":
        return f"suppressed:{_canonical_token(source)}/{_canonical_token(facet)}"
    return None


def extract_taxonomy_v2_text_phrases(
    text: str | None,
    *,
    ngram: int = 3,
    exclude_boilerplate: bool = True,
) -> list[str]:
    if ngram < 2:
        raise ValueError("ngram must be at least 2")

    blocked_segments = {
        hit.normalized_segment
        for hit in detect_taxonomy_v2_boilerplate_segments(text)
    } if exclude_boilerplate else set()
    if exclude_boilerplate:
        blocked_segments.update(
            hit.normalized_segment
            for hit in _detect_taxonomy_v2_low_signal_segments(text)
        )
    phrases: set[str] = set()

    for segment in split_taxonomy_v2_text_segments(text):
        normalized_segment = normalize_taxonomy_label(segment)
        if not normalized_segment or normalized_segment in blocked_segments:
            continue
        words = [
            word
            for word in _WORD_RE.split(normalized_segment)
            if word and not word.isdigit() and len(word) >= 2
        ]
        if len(words) < ngram:
            continue
        for index in range(len(words) - ngram + 1):
            window = words[index : index + ngram]
            if window[0] in _TEXT_AUDIT_STOPWORDS or window[-1] in _TEXT_AUDIT_STOPWORDS:
                continue
            content_words = [word for word in window if word not in _TEXT_AUDIT_STOPWORDS]
            if len(content_words) < max(2, ngram - 1):
                continue
            phrases.add(" ".join(window))
    return sorted(phrases)


def build_taxonomy_v2_text_corpus(game: Game) -> tuple[str | None, list[str]]:
    candidates = (
        ("steam_detailed", getattr(game, "steam_detailed_description", None)),
        ("opencritic", getattr(game, "opencritic_description", None)),
        ("steam_short", getattr(game, "steam_short_description", None)),
        ("metacritic", getattr(game, "metacritic_description", None)),
        ("generic", getattr(game, "description", None)),
    )
    segments: list[dict[str, str]] = []

    for source, raw_text in candidates:
        cleaned = strip_taxonomy_v2_noise_segments(raw_text)
        cleaned = clean_taxonomy_v2_text(cleaned)
        if not cleaned:
            continue
        normalized = normalize_taxonomy_label(cleaned)
        if not normalized:
            continue
        matched_index: int | None = None
        for index, segment in enumerate(segments):
            existing = segment["normalized"]
            if normalized == existing or normalized in existing:
                matched_index = index
                break
            if existing in normalized:
                segments[index] = {
                    "source": segment["source"],
                    "text": cleaned,
                    "normalized": normalized,
                }
                matched_index = index
                break
        if matched_index is None:
            segments.append(
                {
                    "source": source,
                    "text": cleaned,
                    "normalized": normalized,
                }
            )

    if not segments:
        return None, []

    corpus = "\n\n".join(segment["text"] for segment in segments).strip()
    sources = [segment["source"] for segment in segments]
    return corpus[:12000] or None, sources


def refresh_game_taxonomy_v2_text(game: Game) -> tuple[str | None, list[str]]:
    corpus, sources = build_taxonomy_v2_text_corpus(game)
    game.taxonomy_v2_text_corpus = corpus
    game.taxonomy_v2_text_sources = list(sources)
    game.taxonomy_v2_text_synced_at = datetime.now(timezone.utc)
    return corpus, sources


def apply_opencritic_description(game: Game, description: str | None) -> bool:
    cleaned = clean_taxonomy_v2_text(description)
    changed = False
    previous = getattr(game, "opencritic_description", None)
    if cleaned != previous:
        game.opencritic_description = cleaned
        changed = True
    if cleaned and (not getattr(game, "description", None) or getattr(game, "description", None) == previous):
        if game.description != cleaned:
            game.description = cleaned
            changed = True
    return changed


def apply_steam_descriptions(
    game: Game,
    *,
    short_description: str | None,
    detailed_description: str | None,
) -> bool:
    cleaned_short = clean_taxonomy_v2_text(short_description)
    cleaned_detailed = clean_taxonomy_v2_text(detailed_description)
    changed = False
    if cleaned_short != getattr(game, "steam_short_description", None):
        game.steam_short_description = cleaned_short
        changed = True
    if cleaned_detailed != getattr(game, "steam_detailed_description", None):
        game.steam_detailed_description = cleaned_detailed
        changed = True
    preferred = cleaned_detailed or cleaned_short
    if preferred and not getattr(game, "description", None):
        game.description = preferred
        changed = True
    return changed


def apply_metacritic_description(game: Game, description: str | None) -> bool:
    cleaned = clean_taxonomy_v2_text(description)
    changed = False
    if cleaned != getattr(game, "metacritic_description", None):
        game.metacritic_description = cleaned
        changed = True
    if cleaned and not getattr(game, "description", None):
        game.description = cleaned
        changed = True
    return changed


def _override_keys_for_game(game: Game) -> list[str]:
    keys: list[str] = []
    if getattr(game, "public_id", None):
        keys.append(f"public_id:{game.public_id}")
    if getattr(game, "opencritic_id", None) is not None:
        keys.append(f"opencritic_id:{game.opencritic_id}")
    if getattr(game, "steam_app_id", None) is not None:
        keys.append(f"steam_app_id:{game.steam_app_id}")
    if getattr(game, "metacritic_slug", None):
        keys.append(f"metacritic_slug:{game.metacritic_slug}")
    if getattr(game, "title", None):
        keys.append(f"title:{_canonical_token(game.title)}")
    return keys


@lru_cache(maxsize=1)
def _load_legacy_archetype_graph_v2() -> dict[str, Any]:
    preferred = _data_path("archetype_graph_v2.json")
    fallback = _docs_path("archetype-graph-v2.json")
    base_graph: dict[str, Any] | None = None
    for path in (preferred, fallback):
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                base_graph = json.load(handle)
            break
    if base_graph is None:
        raise FileNotFoundError("Could not find archetype graph V2 JSON in app/data or docs")

    extensions_path = _data_path("archetype_graph_v2_extensions.json")
    if not extensions_path.exists():
        return base_graph

    with extensions_path.open("r", encoding="utf-8") as handle:
        extension_graph = json.load(handle)

    merged = dict(base_graph)
    merged_nodes = dict(base_graph.get("nodes", {}))
    merged_nodes.update(extension_graph.get("nodes", {}))
    merged["nodes"] = merged_nodes
    merged["version"] = (
        f"{base_graph.get('version', 'taxonomy_v2_graph')}"
        f"+{extension_graph.get('version', 'extensions')}"
    )
    return merged


@lru_cache(maxsize=1)
def load_taxonomy_v2_label_crosswalk() -> dict[str, Any]:
    path = _data_path("taxonomy_v2_label_crosswalk.json")
    if not path.exists():
        return {"aliases": {"global": {}}, "tag_rules": {}}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def load_opencritic_theme_catalog() -> dict[str, Any]:
    path = _data_path("opencritic_theme_catalog.json")
    if not path.exists():
        return {"themes": {}}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _json_deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            if key in merged:
                merged[key] = _json_deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged
    if isinstance(base, list) and isinstance(override, list):
        merged = list(base)
        seen = {json.dumps(item, sort_keys=True, default=str) for item in merged}
        for item in override:
            marker = json.dumps(item, sort_keys=True, default=str)
            if marker in seen:
                continue
            seen.add(marker)
            merged.append(item)
        return merged
    return override


def _serialize_rule_tuples(mapping: dict[str, tuple[tuple[str, str, float], ...]]) -> dict[str, list[list[Any]]]:
    return {
        key: [[field, value, confidence] for field, value, confidence in values]
        for key, values in mapping.items()
    }


def _serialize_nested_rule_tuples(
    mapping: dict[str, dict[str, tuple[tuple[str, str, float], ...]]]
) -> dict[str, dict[str, list[list[Any]]]]:
    return {
        facet: _serialize_rule_tuples(values)
        for facet, values in mapping.items()
    }


def _build_default_source_label_matrix() -> dict[str, Any]:
    crosswalk = load_taxonomy_v2_label_crosswalk()
    suppressions: dict[str, dict[str, list[str]]] = {}
    for (source, facet), values in _IGNORED_SOURCE_LABELS.items():
        suppressions.setdefault(source, {})[facet] = sorted(values)
    return {
        "version": "source_label_matrix_default",
        "aliases": crosswalk.get("aliases", {"global": {}}),
        "tag_rules": crosswalk.get("tag_rules", {}),
        "global_rules": _serialize_rule_tuples(_GLOBAL_LABEL_RULES),
        "facet_rules": _serialize_nested_rule_tuples(_FACET_LABEL_RULES),
        "suppressions": suppressions,
        "ignored": {"global": []},
        "provider_gaps": {},
        "rarity_buckets": {"global": {}},
    }


@lru_cache(maxsize=1)
def load_source_label_matrix() -> dict[str, Any]:
    base = _build_default_source_label_matrix()
    path = _data_path("source_label_matrix.json")
    if not path.exists():
        return base
    with path.open("r", encoding="utf-8") as handle:
        override = json.load(handle)
    return _json_deep_merge(base, override)


def _build_default_phrase_matrix() -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    for index, (patterns, outputs) in enumerate(_DESCRIPTION_RULES, start=1):
        rules.append(
            {
                "id": f"default_phrase_rule_{index}",
                "scope": ["global"],
                "patterns": [pattern.pattern for pattern in patterns],
                "emits": [[field, value, confidence] for field, value, confidence in outputs],
            }
        )
    return {"version": "phrase_matrix_default", "rules": rules}


@lru_cache(maxsize=1)
def load_phrase_matrix() -> dict[str, Any]:
    base = _build_default_phrase_matrix()
    path = _data_path("phrase_matrix.json")
    if not path.exists():
        return base
    with path.open("r", encoding="utf-8") as handle:
        override = json.load(handle)
    return _json_deep_merge(base, override)


def _build_default_noise_matrix() -> dict[str, Any]:
    return {
        "version": "noise_matrix_default",
        "boilerplate_patterns": [
            {"category": category, "pattern": pattern.pattern}
            for category, pattern in _BOILERPLATE_PATTERNS
        ],
        "low_signal_patterns": [
            {"category": category, "pattern": pattern.pattern}
            for category, pattern in _LOW_SIGNAL_SEGMENT_PATTERNS
        ],
        "high_signal_patterns": [pattern.pattern for pattern in _HIGH_SIGNAL_SEGMENT_PATTERNS],
    }


@lru_cache(maxsize=1)
def load_noise_matrix() -> dict[str, Any]:
    base = _build_default_noise_matrix()
    path = _data_path("noise_matrix.json")
    if not path.exists():
        return base
    with path.open("r", encoding="utf-8") as handle:
        override = json.load(handle)
    return _json_deep_merge(base, override)


def _build_default_facet_matrix() -> dict[str, Any]:
    return {
        "version": "facet_matrix_default",
        "source_weights": {
            "description": 1.0,
            "steam": 0.95,
            "opencritic": 0.9,
            "metacritic": 0.88,
            "inference": 0.92,
        },
        "role_weights": {
            "identity_driving": 1.0,
            "supporting": 0.8,
            "filter_only": 0.0,
        },
        "rarity_weights": {
            "ubiquitous": 0.0,
            "common": 0.02,
            "uncommon": 0.05,
            "rare": 0.08,
        },
        "supporting_values": sorted(_SUPPORTING_VALUES),
        "field_role_defaults": {
            "keyword_layer": "identity_driving",
            "mechanics_structure": "identity_driving",
            "rules_goals": "identity_driving",
            "entity_interaction": "identity_driving",
            "narrative_topic": "identity_driving",
            "sports_theme": "identity_driving",
            "vehicular_theme": "identity_driving",
            "setting": "identity_driving",
            "combat_style": "identity_driving",
            "combat_structure": "identity_driving",
            "progression_model": "identity_driving",
            "world_topology": "identity_driving",
            "perspective": "identity_driving",
            "session_shape": "identity_driving",
            "narrative_structure": "identity_driving",
            "mode_profile": "identity_driving",
            "challenge_model": "identity_driving",
        },
        "assignment": {
            "strict_min_required_hits": _STRICT_MIN_REQUIRED_HITS,
            "mandatory_required_axes": {
                key: sorted(values)
                for key, values in _MANDATORY_REQUIRED_AXES.items()
            },
        },
        "match_weights": {
            "progression_model": _PROGRESSION_MATCH_WEIGHTS,
            "traversal_verbs": _TRAVERSAL_MATCH_WEIGHTS,
            "keyword_layer": _KEYWORD_MATCH_WEIGHTS,
            "mechanics_structure": _MECHANICS_MATCH_WEIGHTS,
            "rules_goals": _RULES_GOALS_MATCH_WEIGHTS,
            "entity_interaction": _ENTITY_INTERACTION_MATCH_WEIGHTS,
            "narrative_topic": _NARRATIVE_TOPIC_MATCH_WEIGHTS,
            "art_style": _ART_STYLE_MATCH_WEIGHTS,
            "visual_presentation": _VISUAL_PRESENTATION_MATCH_WEIGHTS,
            "pacing": _PACING_MATCH_WEIGHTS,
            "interface_control": _INTERFACE_CONTROL_MATCH_WEIGHTS,
            "sports_theme": _SPORTS_THEME_MATCH_WEIGHTS,
            "vehicular_theme": _VEHICULAR_THEME_MATCH_WEIGHTS,
            "setting": _SETTING_MATCH_WEIGHTS,
            "tone": _TONE_MATCH_WEIGHTS,
        },
        "co_signal_gates": [],
        "value_rarity_overrides": {},
    }


@lru_cache(maxsize=1)
def load_facet_matrix() -> dict[str, Any]:
    base = _build_default_facet_matrix()
    path = _data_path("facet_matrix.json")
    if not path.exists():
        return base
    with path.open("r", encoding="utf-8") as handle:
        override = json.load(handle)
    return _json_deep_merge(base, override)


def _build_default_connection_matrix() -> dict[str, Any]:
    legacy_graph = _load_legacy_archetype_graph_v2()
    return {
        "version": legacy_graph.get("version", "connection_matrix_default"),
        "relation_weights": {
            "same": 220,
            "strong_neighbor": 175,
            "adjacent_neighbor": 140,
            "bridge_neighbor": 150,
            "strong_secondary": 155,
            "adjacent_secondary": 125,
            "bridge_secondary": 135,
        },
        "nodes": legacy_graph.get("nodes", {}),
    }


@lru_cache(maxsize=1)
def load_connection_matrix() -> dict[str, Any]:
    base = _build_default_connection_matrix()
    path = _data_path("connection_matrix.json")
    if not path.exists():
        return base
    with path.open("r", encoding="utf-8") as handle:
        override = json.load(handle)
    return _json_deep_merge(base, override)


@lru_cache(maxsize=1)
def load_archetype_graph_v2() -> dict[str, Any]:
    matrix = load_connection_matrix()
    return {
        "version": matrix.get("version", "connection_matrix"),
        "description": matrix.get("description", "Matrix-backed archetype graph"),
        "nodes": matrix.get("nodes", {}),
    }


@lru_cache(maxsize=1)
def load_taxonomy_v2_overrides() -> dict[str, Any]:
    path = _data_path("taxonomy_v2_overrides.json")
    if not path.exists():
        return {"games": {}}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def get_taxonomy_v2_override(game: Game) -> dict[str, Any]:
    overrides = load_taxonomy_v2_overrides().get("games", {})
    merged: dict[str, Any] = {
        "replace": {},
        "add": {},
        "remove": {},
        "primary_family": None,
        "primary_archetype": None,
        "secondary_archetypes": [],
        "hard_exclusions": {"add": [], "remove": []},
        "soft_penalties": {"add": [], "remove": []},
        "rationale": None,
    }
    for key in _override_keys_for_game(game):
        override = overrides.get(key)
        if not override:
            continue
        for bucket in ("replace", "add", "remove"):
            for axis, values in (override.get(bucket) or {}).items():
                normalized_values = sorted(
                    {
                        _canonical_token(value)
                        for value in values
                        if _canonical_token(value)
                    }
                )
                if normalized_values:
                    merged[bucket][axis] = normalized_values
        for bucket in ("hard_exclusions", "soft_penalties"):
            bucket_value = override.get(bucket) or {}
            merged[bucket]["add"].extend(
                _canonical_token(value)
                for value in bucket_value.get("add", [])
                if _canonical_token(value)
            )
            merged[bucket]["remove"].extend(
                _canonical_token(value)
                for value in bucket_value.get("remove", [])
                if _canonical_token(value)
            )
            merged[bucket]["add"] = sorted(set(merged[bucket]["add"]))
            merged[bucket]["remove"] = sorted(set(merged[bucket]["remove"]))
        if override.get("primary_family"):
            merged["primary_family"] = _canonical_token(str(override["primary_family"]))
        if override.get("primary_archetype"):
            merged["primary_archetype"] = _canonical_token(str(override["primary_archetype"]))
        if override.get("secondary_archetypes"):
            merged["secondary_archetypes"] = sorted(
                {
                    _canonical_token(value)
                    for value in override["secondary_archetypes"]
                    if _canonical_token(value)
                }
            )
        if override.get("rationale"):
            merged["rationale"] = str(override["rationale"]).strip()
    return merged


def game_has_taxonomy_v2_override(game: Game) -> bool:
    override = get_taxonomy_v2_override(game)
    return any(
        [
            override["replace"],
            override["add"],
            override["remove"],
            override["primary_family"],
            override["primary_archetype"],
            override["secondary_archetypes"],
            override["hard_exclusions"]["add"],
            override["hard_exclusions"]["remove"],
            override["soft_penalties"]["add"],
            override["soft_penalties"]["remove"],
        ]
    )


@lru_cache(maxsize=1)
def _compiled_phrase_rules() -> tuple[
    tuple[str, int, tuple[str, ...], tuple[tuple[str, str, float], ...]],
    ...,
]:
    compiled: list[tuple[str, int, tuple[str, ...], tuple[tuple[str, str, float], ...]]] = []
    for rule in load_phrase_matrix().get("rules", []):
        patterns: list[str] = []
        for pattern in rule.get("patterns", []):
            if not isinstance(pattern, str):
                continue
            patterns.append(pattern)
        emits = _crosswalk_rule_tuples(rule.get("emits"))
        if not patterns or not emits:
            continue
        min_matches = int(rule.get("min_matches") or 1)
        if min_matches < 1:
            min_matches = 1
        compiled.append((str(rule.get("id") or "matrix_rule"), min_matches, tuple(patterns), emits))
    return tuple(compiled)


@lru_cache(maxsize=1)
def _compiled_noise_patterns() -> tuple[
    tuple[tuple[str, re.Pattern[str]], ...],
    tuple[tuple[str, re.Pattern[str]], ...],
    tuple[re.Pattern[str], ...],
]:
    matrix = load_noise_matrix()
    boilerplate: list[tuple[str, re.Pattern[str]]] = []
    for item in matrix.get("boilerplate_patterns", []):
        category = str(item.get("category") or "").strip()
        pattern = str(item.get("pattern") or "").strip()
        if not category or not pattern:
            continue
        boilerplate.append((category, re.compile(pattern)))

    low_signal: list[tuple[str, re.Pattern[str]]] = []
    for item in matrix.get("low_signal_patterns", []):
        category = str(item.get("category") or "").strip()
        pattern = str(item.get("pattern") or "").strip()
        if not category or not pattern:
            continue
        low_signal.append((category, re.compile(pattern)))

    high_signal: list[re.Pattern[str]] = []
    for pattern in matrix.get("high_signal_patterns", []):
        if not isinstance(pattern, str) or not pattern.strip():
            continue
        high_signal.append(re.compile(pattern))

    return tuple(boilerplate), tuple(low_signal), tuple(high_signal)


def _normalize_source_label_rules(
    rules: Iterable[Any],
) -> tuple[tuple[str, str, float], ...]:
    return _crosswalk_rule_tuples(list(rules))


def _resolve_source_label(
    *,
    source: str,
    facet: str,
    raw_label: str,
    normalized_label: str | None = None,
) -> tuple[str, str | None]:
    normalized = normalize_taxonomy_label(normalized_label or raw_label)
    if not normalized:
        return "", None
    if _canonical_token(source) == "opencritic" and _canonical_token(facet) == "theme":
        theme_entry = (load_opencritic_theme_catalog().get("themes") or {}).get(normalized)
        if isinstance(theme_entry, dict):
            label = normalize_taxonomy_label(theme_entry.get("label"))
            status = _canonical_token(theme_entry.get("status"))
            if label:
                return label, status or None
            if status:
                return normalized, status
    provider_theme = (
        load_source_label_matrix()
        .get("provider_gaps", {})
        .get(_canonical_token(source), {})
        .get(_canonical_token(facet), {})
    )
    if isinstance(provider_theme, dict) and normalized in provider_theme:
        status = _canonical_token(provider_theme[normalized].get("status"))
        if status:
            return normalized, status
    return normalized, None


def _source_label_list_values(container: Any) -> set[str]:
    if isinstance(container, list):
        return {normalize_taxonomy_label(value) for value in container if normalize_taxonomy_label(value)}
    return set()


def _source_label_nested_values(container: Any, source: str, facet: str) -> set[str]:
    if not isinstance(container, dict):
        return set()
    source_key = _canonical_token(source)
    source_bucket = container.get(source_key, {})
    if source == "*" and not source_bucket:
        source_bucket = container.get("*", {})
    if not isinstance(source_bucket, dict):
        return set()
    return _source_label_list_values(source_bucket.get(_canonical_token(facet), []))


def classify_taxonomy_v2_source_label(
    *,
    source: str,
    facet: str,
    raw_label: str,
    normalized_label: str | None = None,
) -> tuple[str, str]:
    resolved_label, resolved_status = _resolve_source_label(
        source=source,
        facet=facet,
        raw_label=raw_label,
        normalized_label=normalized_label,
    )
    if not resolved_label:
        return "", "unmapped"
    if resolved_status == "provider_gap":
        return resolved_label, "provider_gap"
    matrix = load_source_label_matrix()
    normalized_source = _canonical_token(source)
    normalized_facet = _canonical_token(facet)

    suppressions = matrix.get("suppressions", {})
    suppressed = _source_label_nested_values(suppressions, source, facet)
    suppressed.update(_source_label_nested_values(suppressions, "*", facet))
    if resolved_label in suppressed:
        return resolved_label, "suppressed"

    ignored = _source_label_list_values((matrix.get("ignored") or {}).get("global", []))
    ignored.update(_source_label_nested_values(matrix.get("ignored", {}), source, facet))
    if resolved_label in ignored:
        return resolved_label, "ignored"

    global_rules = matrix.get("global_rules", {}) or {}
    facet_rules = (matrix.get("facet_rules", {}) or {}).get(normalized_facet, {}) if normalized_facet else {}
    tag_rules = matrix.get("tag_rules", {}) or {}
    aliases = (matrix.get("aliases", {}) or {}).get("global", {}) if isinstance(matrix.get("aliases"), dict) else {}
    resolved_tokens = [resolved_label]
    resolved_tokens.extend(
        _canonical_token(value).replace("_", " ")
        for value in aliases.get(resolved_label, [])
        if _canonical_token(value)
    )
    for token in resolved_tokens:
        if token in global_rules or token in facet_rules or token in tag_rules:
            return resolved_label, "mapped"
    return resolved_label, "unmapped"


def analyze_taxonomy_v2_label(
    *,
    source: str,
    facet: str,
    raw_label: str,
    normalized_label: str | None = None,
) -> TaxonomyV2LabelAnalysis:
    normalized = normalize_taxonomy_label(normalized_label or raw_label)
    resolved_label, classification = classify_taxonomy_v2_source_label(
        source=source,
        facet=facet,
        raw_label=raw_label,
        normalized_label=normalized,
    )
    suppression_reason = None
    if classification == "suppressed":
        suppression_reason = f"suppressed:{_canonical_token(source)}/{_canonical_token(facet)}"
        return TaxonomyV2LabelAnalysis(
            source=source,
            facet=facet,
            raw_label=raw_label,
            normalized_label=normalized,
            resolved_tokens=(),
            emitted_signals=(),
            classification=classification,
            mapped=False,
            suppressed=True,
            role_tier="filter_only",
            rarity_bucket=get_taxonomy_v2_rarity_bucket(resolved_label),
            suppression_reason=suppression_reason,
        )
    if classification in {"ignored", "provider_gap"}:
        return TaxonomyV2LabelAnalysis(
            source=source,
            facet=facet,
            raw_label=raw_label,
            normalized_label=normalized,
            resolved_tokens=tuple(_resolve_crosswalk_tokens(resolved_label or normalized)),
            emitted_signals=(),
            classification=classification,
            mapped=False,
            suppressed=False,
            role_tier="filter_only" if classification == "ignored" else None,
            rarity_bucket=get_taxonomy_v2_rarity_bucket(resolved_label),
            suppression_reason=None,
        )
    synthetic_row = GameSourceTaxonomyLabel(
        game_id=0,
        source=source,
        facet=facet,
        raw_label=resolved_label or raw_label,
        normalized_label=resolved_label or normalized,
    )
    emitted = extract_v2_evidence_from_source_labels([synthetic_row])
    emitted_signals = tuple(
        sorted(
            {
                _render_signal(record.field, record.value)
                for record in emitted
            }
        )
    )
    return TaxonomyV2LabelAnalysis(
        source=source,
        facet=facet,
        raw_label=raw_label,
        normalized_label=normalized,
        resolved_tokens=_resolve_crosswalk_tokens(resolved_label or raw_label or normalized),
        emitted_signals=emitted_signals,
        classification="mapped" if emitted_signals else classification,
        mapped=bool(emitted_signals),
        suppressed=False,
        role_tier=(
            "identity_driving"
            if any(classify_taxonomy_v2_signal_tier(record.field, record.value) == "identity_driving" for record in emitted)
            else "supporting"
            if emitted
            else None
        ),
        rarity_bucket=get_taxonomy_v2_rarity_bucket(resolved_label),
        suppression_reason=None,
    )


def _make_evidence(
    field: str,
    value: str,
    *,
    source: str,
    source_field: str,
    confidence: float,
    evidence_text: str | None = None,
    curated: bool = False,
    weight: float | None = None,
    conflict_group: str | None = None,
    suppressed_by_rule: str | None = None,
) -> TaxonomyV2EvidenceRecord | None:
    canonical_field = _canonical_token(field)
    canonical_value = _canonical_token(value)
    if canonical_field not in FINGERPRINT_FIELDS or not canonical_value:
        return None
    return TaxonomyV2EvidenceRecord(
        field=canonical_field,
        value=canonical_value,
        source=source,
        source_field=source_field,
        confidence=max(0.0, min(confidence, 0.99)),
        evidence_text=evidence_text.strip() if evidence_text else None,
        curated=curated,
        weight=weight,
        conflict_group=conflict_group,
        suppressed_by_rule=suppressed_by_rule,
    )


def _crosswalk_rule_tuples(value: Any) -> tuple[tuple[str, str, float], ...]:
    rules: list[tuple[str, str, float]] = []
    for item in value or []:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            continue
        field, token, confidence = item
        if not isinstance(field, str) or not isinstance(token, str):
            continue
        try:
            numeric_confidence = float(confidence)
        except (TypeError, ValueError):
            continue
        rules.append((field, token, numeric_confidence))
    return tuple(rules)


@lru_cache(maxsize=4096)
def _resolve_crosswalk_tokens(raw_label: str) -> tuple[str, ...]:
    normalized = normalize_taxonomy_label(raw_label)
    if not normalized:
        return ()

    aliases = load_source_label_matrix().get("aliases", {}).get("global", {})
    resolved: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        token = _canonical_token(value)
        if not token or token in seen:
            return
        seen.add(token)
        resolved.append(token)

    add(normalized)
    for alias in aliases.get(normalized, []):
        add(alias)
    return tuple(resolved)


def extract_v2_evidence_from_source_labels(
    rows: Iterable[GameSourceTaxonomyLabel],
) -> list[TaxonomyV2EvidenceRecord]:
    evidence: list[TaxonomyV2EvidenceRecord] = []
    seen: set[tuple[str, str, str, str]] = set()
    matrix = load_source_label_matrix()
    global_rules = {
        normalize_taxonomy_label(key): _normalize_source_label_rules(value)
        for key, value in (matrix.get("global_rules") or {}).items()
        if normalize_taxonomy_label(key)
    }
    facet_rules = {
        _canonical_token(facet): {
            normalize_taxonomy_label(key): _normalize_source_label_rules(value)
            for key, value in (rules or {}).items()
            if normalize_taxonomy_label(key)
        }
        for facet, rules in (matrix.get("facet_rules") or {}).items()
        if _canonical_token(facet)
    }
    tag_rules = {
        _canonical_token(key): _crosswalk_rule_tuples(value)
        for key, value in (matrix.get("tag_rules") or {}).items()
        if _canonical_token(key)
    }
    for row in rows:
        normalized_label, classification = classify_taxonomy_v2_source_label(
            source=row.source,
            facet=row.facet,
            raw_label=row.raw_label or row.normalized_label or "",
            normalized_label=row.normalized_label,
        )
        if not normalized_label:
            continue
        if classification in {"suppressed", "ignored", "provider_gap"}:
            continue
        rules = list(global_rules.get(normalized_label, ()))
        rules.extend(facet_rules.get(_canonical_token(row.facet), {}).get(normalized_label, ()))
        for token in _resolve_crosswalk_tokens(row.raw_label or row.normalized_label):
            rules.extend(global_rules.get(token.replace("_", " "), ()))
            rules.extend(tag_rules.get(token, ()))
        for field, value, confidence in rules:
            record = _make_evidence(
                field,
                value,
                source=row.source,
                source_field=row.facet,
                confidence=confidence,
                evidence_text=row.raw_label,
            )
            if record is None:
                continue
            marker = (record.field, record.value, record.source, record.evidence_text or "")
            if marker in seen:
                continue
            seen.add(marker)
            evidence.append(record)
    return evidence


def extract_v2_evidence_from_description(description: str | None) -> list[TaxonomyV2EvidenceRecord]:
    if not description:
        return []
    normalized_description = normalize_taxonomy_label(description)
    if not normalized_description:
        return []
    evidence: list[TaxonomyV2EvidenceRecord] = []
    for _rule_id, min_matches, patterns, outputs in _compiled_phrase_rules():
        matches: list[str] = []
        for pattern_text in patterns:
            pattern = re.compile(pattern_text)
            match = pattern.search(normalized_description)
            if not match:
                continue
            matched_text = match.group(0)
            if matched_text not in matches:
                matches.append(matched_text)
        if len(matches) < min_matches:
            continue
        evidence_text = ", ".join(matches[:min_matches])
        for field, value, confidence in outputs:
            record = _make_evidence(
                field,
                value,
                source="description",
                source_field="description",
                confidence=confidence,
                evidence_text=evidence_text,
            )
            if record is not None:
                evidence.append(record)
    return evidence


def _apply_taxonomy_v2_co_signal_gates(
    fingerprint: dict[str, list[str]],
    confidence_by_field_value: dict[str, dict[str, float]],
    source_count_by_field_value: dict[str, dict[str, int]],
    provenance_by_field_value: dict[str, dict[str, set[str]]],
) -> None:
    gates = load_facet_matrix().get("co_signal_gates") or []
    for gate in gates:
        field = _canonical_token(gate.get("field"))
        value = _canonical_token(gate.get("value"))
        required_fields = {
            _canonical_token(item)
            for item in gate.get("requires_any_fields", [])
            if _canonical_token(item)
        }
        if not field or not value or value not in fingerprint.get(field, []):
            continue
        required_provenance = {
            _canonical_provenance_token(item)
            for item in gate.get("requires_any_provenance", [])
            if _canonical_provenance_token(item)
        }
        disallowed_only_provenance = {
            _canonical_provenance_token(item)
            for item in gate.get("disallow_only_provenance", [])
            if _canonical_provenance_token(item)
        }
        provenances = provenance_by_field_value.get(field, {}).get(value, set())
        if any(fingerprint.get(required_field, []) for required_field in required_fields):
            if not required_provenance or provenances & required_provenance:
                if not disallowed_only_provenance or not provenances.issubset(disallowed_only_provenance):
                    continue
        elif required_provenance and not (provenances & required_provenance):
            fingerprint[field] = [item for item in fingerprint.get(field, []) if item != value]
            confidence_by_field_value.get(field, {}).pop(value, None)
            source_count_by_field_value.get(field, {}).pop(value, None)
            provenance_by_field_value.get(field, {}).pop(value, None)
            continue
        elif not required_fields and not required_provenance and (
            not disallowed_only_provenance or not provenances.issubset(disallowed_only_provenance)
        ):
            continue
        if disallowed_only_provenance and provenances and not provenances.issubset(disallowed_only_provenance):
            continue
        fingerprint[field] = [item for item in fingerprint.get(field, []) if item != value]
        confidence_by_field_value.get(field, {}).pop(value, None)
        source_count_by_field_value.get(field, {}).pop(value, None)
        provenance_by_field_value.get(field, {}).pop(value, None)


def _apply_taxonomy_v2_false_positive_suppressions(
    fingerprint: dict[str, list[str]],
    confidence_by_field_value: dict[str, dict[str, float]],
    source_count_by_field_value: dict[str, dict[str, int]],
    provenance_by_field_value: dict[str, dict[str, set[str]]],
) -> None:
    def _remove(field: str, value: str) -> None:
        fingerprint[field] = [item for item in fingerprint.get(field, []) if item != value]
        confidence_by_field_value.get(field, {}).pop(value, None)
        source_count_by_field_value.get(field, {}).pop(value, None)
        provenance_by_field_value.get(field, {}).pop(value, None)

    traversal = set(fingerprint.get("traversal_verbs", []))
    perspective = set(fingerprint.get("perspective", []))
    challenge_model = set(fingerprint.get("challenge_model", []))
    sports_theme = set(fingerprint.get("sports_theme", []))
    vehicular_theme = set(fingerprint.get("vehicular_theme", []))
    combat_presence = set(fingerprint.get("combat_presence", []))
    combat_style = set(fingerprint.get("combat_style", []))
    combat_structure = set(fingerprint.get("combat_structure", []))
    combat_tempo = set(fingerprint.get("combat_tempo", []))
    world_topology = set(fingerprint.get("world_topology", []))
    world_density = set(fingerprint.get("world_density", []))
    session_shapes = set(fingerprint.get("session_shape", []))
    progression_model = set(fingerprint.get("progression_model", []))
    mode_profile = set(fingerprint.get("mode_profile", []))
    setting = set(fingerprint.get("setting", []))
    tone = set(fingerprint.get("tone", []))
    art_style = set(fingerprint.get("art_style", []))
    keyword_layer = set(fingerprint.get("keyword_layer", []))
    narrative_topic = set(fingerprint.get("narrative_topic", []))
    narrative_structure = set(fingerprint.get("narrative_structure", []))
    interface_control = set(fingerprint.get("interface_control", []))
    mechanics_structure = set(fingerprint.get("mechanics_structure", []))
    rules_goals = set(fingerprint.get("rules_goals", []))
    entity_interaction = set(fingerprint.get("entity_interaction", []))
    content_model = set(fingerprint.get("content_model", []))

    parkour_platformer_profile = (
        bool(traversal & {"parkour", "platforming", "climbing"})
        and bool(perspective & {"first_person", "vr"})
        and "sim_realism" not in challenge_model
        and not sports_theme
        and bool(world_topology & {"level_based"} or traversal & {"parkour"})
        and bool(combat_presence & {"none", "light"} or combat_style & {"shooter"})
    )
    if parkour_platformer_profile and vehicular_theme <= {"cars"}:
        for field, value in (
            ("traversal_verbs", "driving"),
            ("vehicular_theme", "cars"),
            ("interface_control", "vehicle_control"),
            ("mechanics_structure", "vehicular_racing"),
            ("rules_goals", "win_races"),
        ):
            _remove(field, value)

    compact_metroidvania_profile = (
        bool(perspective & {"side_scrolling"})
        and bool(world_topology & {"semi_open", "level_based"})
        and bool(traversal & {"platforming"})
        and bool(progression_model & {"metaprogression"})
        and "single_player" in mode_profile
    )
    if compact_metroidvania_profile and not (mode_profile & {"party_coop", "drop_in_coop"}):
        for field, value in (
            ("combat_style", "party_tactics"),
            ("combat_structure", "party_management"),
            ("mechanics_structure", "party_management_loop"),
            ("entity_interaction", "party_control"),
        ):
            _remove(field, value)
        if (
            "horror" in setting
            and not (keyword_layer & {"psychological_horror"})
            and not (tone & {"bleak", "melancholic"})
            and not (narrative_topic & {"survival_escape"})
        ):
            _remove("setting", "horror")
            _remove("tone", "grotesque")

    retro_horror_platformer_profile = (
        bool(perspective & {"side_scrolling"})
        and bool(traversal & {"platforming"})
        and bool(combat_presence & {"dominant", "moderate"})
        and "single_player" in mode_profile
        and bool(setting & {"horror"} or tone & {"bleak", "grotesque"} or art_style & {"retro", "pixel_art"})
    )
    if retro_horror_platformer_profile and not (world_topology & {"open_world", "persistent_shared_world"}):
        for field, value in (
            ("progression_model", "buildcraft"),
            ("world_density", "systemic_sandbox"),
            ("mechanics_structure", "systemic_problem_solving"),
            ("keyword_layer", "open_world_exploration"),
        ):
            _remove(field, value)

    replayable_loot_arpg_profile = (
        bool(combat_presence & {"dominant"})
        and bool(combat_style & {"hybrid", "melee", "magic", "ranged"})
        and bool(mode_profile & {"single_player", "drop_in_coop", "party_coop"})
        and "match_session" not in set(fingerprint.get("session_shape", []))
        and bool(progression_model & {"buildcraft", "gear_chase", "loot_rarity", "skill_tree", "base_growth"})
        and not sports_theme
        and not vehicular_theme
    )
    if replayable_loot_arpg_profile and confidence_by_field_value.get("mode_profile", {}).get("pvp", 0.0) <= 0.72:
        _remove("mode_profile", "pvp")

    kingdom_decision_profile = (
        "campaign" in set(fingerprint.get("session_shape", []))
        and "none" in combat_presence
        and "authored_branching" in narrative_structure
        and "cursor_driven" in interface_control
        and bool(entity_interaction & {"dialogue_choice"} or narrative_topic & {"branching_choices"})
        and bool(
            progression_model & {"base_growth"}
            or mechanics_structure & {"systemic_problem_solving"}
            or rules_goals & {"build_and_optimize"}
        )
    )
    if kingdom_decision_profile:
        for field, value in (
            ("combat_presence", "dominant"),
            ("combat_presence", "light"),
            ("combat_style", "melee"),
            ("combat_style", "shooter"),
            ("combat_style", "magic"),
            ("combat_style", "hybrid"),
            ("combat_structure", "boss_centric"),
            ("combat_structure", "encounter_driven"),
            ("perspective", "third_person"),
            ("progression_model", "buildcraft"),
        ):
            _remove(field, value)

    precision_no_combat_platformer_profile = (
        bool(perspective & {"side_scrolling"})
        and bool(traversal & {"platforming"})
        and "level_based" in world_topology
        and bool(challenge_model & {"precision_platforming"})
        and "match_session" not in session_shapes
        and not sports_theme
    )
    precision_action_noise_profile = (
        precision_no_combat_platformer_profile
        and not (combat_structure & {"crowd_control", "boss_centric"})
        and not (combat_style & {"melee", "hybrid", "magic", "ranged"})
    )
    if precision_action_noise_profile:
        for field, value in (
            ("perspective", "first_person"),
            ("combat_style", "shooter"),
            ("combat_presence", "dominant"),
            ("combat_structure", "encounter_driven"),
            ("hard_exclusions", "fps_only"),
            ("world_topology", "open_world"),
            ("world_topology", "semi_open"),
            ("world_density", "handcrafted_discovery"),
            ("progression_model", "metaprogression"),
            ("keyword_layer", "open_world_exploration"),
        ):
            _remove(field, value)

    detective_isometric_crpg_profile = (
        bool(perspective & {"isometric"})
        and "campaign" in session_shapes
        and bool(
            entity_interaction & {"dialogue_choice"}
            or narrative_structure & {"authored_branching"}
            or narrative_topic & {"detective_mystery", "branching_choices"}
        )
        and bool(rules_goals & {"solve_mysteries"} or progression_model & {"quest_driven"})
        and not (
            world_density & {"handcrafted_discovery"}
            and mechanics_structure & {"quest_exploration_loop"}
            and world_topology & {"open_world"}
            and combat_presence & {"dominant", "moderate"}
        )
        and not sports_theme
    )
    if detective_isometric_crpg_profile:
        for field, value in (
            ("world_topology", "open_world"),
            ("setting", "high_fantasy"),
            ("combat_presence", "dominant"),
            ("combat_style", "hybrid"),
            ("keyword_layer", "open_world_exploration"),
        ):
            _remove(field, value)

    card_battler_story_profile = (
        bool(progression_model & {"deck_growth"})
        and bool(entity_interaction & {"card_play"} or mechanics_structure & {"deck_construction"})
        and bool(mode_profile & {"pvp"} or session_shapes & {"match_session"})
    )
    if card_battler_story_profile:
        for field, value in (
            ("combat_structure", "party_management"),
            ("entity_interaction", "party_control"),
            ("mechanics_structure", "party_management_loop"),
            ("hard_exclusions", "jrpg_first"),
        ):
            _remove(field, value)

    colony_tactical_profile = (
        bool(world_density & {"systemic_sandbox"})
        and bool(progression_model & {"base_growth", "colony_growth"})
        and bool(entity_interaction & {"construction_placement"} or mechanics_structure & {"settlement_building"})
    )
    if colony_tactical_profile:
        for field, value in (
            ("combat_structure", "party_management"),
            ("entity_interaction", "party_control"),
            ("mechanics_structure", "party_management_loop"),
            ("hard_exclusions", "jrpg_first"),
        ):
            _remove(field, value)

    creative_sandbox_profile = (
        bool(world_density & {"systemic_sandbox"})
        and bool(progression_model & {"buildcraft"})
        and bool(
            entity_interaction & {"construction_placement"}
            or mechanics_structure & {"settlement_building"}
        )
        and bool(mode_profile & {"single_player", "drop_in_coop", "party_coop", "mmo"} or session_shapes & {"sandbox_loop"})
        and "match_session" not in session_shapes
        and not (
            perspective & {"third_person"}
            and (
                combat_style & {"melee", "hybrid", "ranged", "magic"}
                or (
                    mode_profile & {"mmo"}
                    and input_complexity & {"mastery_heavy"}
                )
            )
        )
        and not sports_theme
        and not vehicular_theme
    )
    if creative_sandbox_profile:
        for field, value in (
            ("combat_structure", "party_management"),
            ("combat_structure", "boss_centric"),
            ("hard_exclusions", "jrpg_first"),
            ("soft_penalties", "sim_heavy"),
            ("world_density", "handcrafted_discovery"),
            ("perspective", "side_scrolling"),
        ):
            _remove(field, value)

    mischief_sandbox_profile = (
        bool(world_density & {"systemic_sandbox"})
        and bool(mechanics_structure & {"systemic_problem_solving"})
        and bool(rules_goals & {"cause_mischief"})
        and "match_session" not in session_shapes
        and not sports_theme
        and not vehicular_theme
    )
    if mischief_sandbox_profile:
        for field, value in (
            ("combat_style", "party_tactics"),
            ("combat_structure", "party_management"),
            ("entity_interaction", "party_control"),
            ("mechanics_structure", "party_management_loop"),
            ("combat_presence", "dominant"),
            ("hard_exclusions", "platformer_first"),
            ("soft_penalties", "sim_heavy"),
        ):
            _remove(field, value)

    tactical_action_roguelite_profile = (
        bool(mode_profile & {"drop_in_coop", "single_player"})
        and bool(world_topology & {"run_based"})
        and bool(session_shapes & {"roguelite_run"})
        and bool(combat_presence & {"dominant"})
        and bool(combat_structure & {"crowd_control"} or rules_goals & {"survive_waves"})
    )
    if tactical_action_roguelite_profile:
        for field, value in (
            ("hard_exclusions", "overhead_strategy_first"),
            ("progression_model", "base_growth"),
            ("world_density", "systemic_sandbox"),
            ("challenge_model", "sim_realism"),
        ):
            _remove(field, value)

    shoot_em_up_profile = (
        bool(combat_style & {"shooter"})
        and bool(combat_tempo & {"twitch"})
        and bool(session_shapes & {"match_session", "campaign"})
        and bool(rules_goals & {"clear_stages", "score_attack"} or mechanics_structure & {"score_attack"})
    )
    if shoot_em_up_profile:
        for field, value in (
            ("hard_exclusions", "historical_first"),
            ("hard_exclusions", "match_based_only"),
            ("soft_penalties", "sim_heavy"),
        ):
            _remove(field, value)

    action_base_defense_arpg_profile = (
        bool(combat_presence & {"dominant"})
        and bool(mode_profile & {"single_player", "drop_in_coop", "party_coop"})
        and "match_session" not in session_shapes
        and bool(progression_model & {"buildcraft", "gear_chase", "loot_rarity", "skill_tree"})
        and bool(
            entity_interaction & {"construction_placement", "inventory_loot"}
            or rules_goals & {"build_and_optimize", "survive_waves"}
        )
        and bool(combat_structure & {"crowd_control", "encounter_driven"} or rules_goals & {"survive_waves"})
        and not sports_theme
        and not vehicular_theme
    )
    if action_base_defense_arpg_profile:
        for field, value in (
            ("combat_structure", "party_management"),
            ("entity_interaction", "party_control"),
            ("mechanics_structure", "party_management_loop"),
            ("hard_exclusions", "jrpg_first"),
            ("challenge_model", "sim_realism"),
        ):
            _remove(field, value)

    action_horror_rpg_profile = (
        bool(perspective & {"third_person", "first_person"})
        and bool(combat_presence & {"dominant"})
        and bool(combat_style & {"melee", "hybrid", "magic", "ranged"})
        and bool(combat_structure & {"boss_centric", "encounter_driven"})
        and bool(progression_model & {"gear_chase", "loot_rarity", "buildcraft"})
        and bool(setting & {"horror", "dark_fantasy"} or tone & {"bleak", "grotesque"})
        and bool(content_model & {"premium_replayable"} or world_topology & {"semi_open", "hub_and_spoke"})
        and not (entity_interaction & {"party_control"} or mechanics_structure & {"party_management_loop"})
    )
    if action_horror_rpg_profile:
        for field, value in (
            ("combat_structure", "party_management"),
            ("hard_exclusions", "jrpg_first"),
        ):
            _remove(field, value)

    co_op_horror_tactical_profile = (
        bool(setting & {"horror"})
        and bool(combat_style & {"shooter"})
        and bool(combat_tempo & {"tactical"})
        and bool(combat_structure & {"party_management"})
        and bool(combat_structure & {"crowd_control", "encounter_driven"})
        and bool(mode_profile & {"drop_in_coop", "party_coop"})
    )
    if co_op_horror_tactical_profile:
        for field, value in (
            ("combat_structure", "party_management"),
            ("entity_interaction", "party_control"),
            ("mechanics_structure", "party_management_loop"),
            ("progression_model", "skill_tree"),
            ("hard_exclusions", "jrpg_first"),
        ):
            _remove(field, value)

    console_party_jrpg_profile = (
        "campaign" in session_shapes
        and "single_player" in mode_profile
        and "party_management" in combat_structure
        and "tactical" in combat_tempo
        and "skill_tree" in progression_model
        and "authored_linear" in narrative_structure
        and not (world_density & {"systemic_sandbox"})
        and not (entity_interaction & {"construction_placement", "card_play", "creature_collection"})
        and not (mechanics_structure & {"settlement_building", "deck_construction"})
    )
    if console_party_jrpg_profile and not (
        perspective & {"third_person", "first_person"}
        and combat_presence & {"dominant"}
        and setting & {"horror", "dark_fantasy"}
        and progression_model & {"gear_chase", "loot_rarity"}
    ):
        _remove("combat_presence", "none")
        _remove("challenge_model", "sim_realism")
        _remove("soft_penalties", "sim_heavy")
        if (
            "horror" in setting
            and "dark_fantasy" not in setting
            and "grotesque" not in tone
            and not (combat_presence & {"dominant"})
            and not (perspective & {"third_person", "first_person"})
        ):
            _remove("setting", "horror")


def _aggregate_evidence(
    evidence: Iterable[TaxonomyV2EvidenceRecord],
) -> tuple[
    dict[str, list[str]],
    dict[str, dict[str, float]],
    dict[str, dict[str, int]],
    dict[str, dict[str, set[str]]],
]:
    grouped: dict[tuple[str, str], list[TaxonomyV2EvidenceRecord]] = defaultdict(list)
    for record in evidence:
        grouped[(record.field, record.value)].append(record)

    fingerprint: dict[str, list[str]] = {field: [] for field in FINGERPRINT_AXES}
    confidence_by_field_value: dict[str, dict[str, float]] = {field: {} for field in FINGERPRINT_AXES}
    source_count_by_field_value: dict[str, dict[str, int]] = {field: {} for field in FINGERPRINT_AXES}
    provenance_by_field_value: dict[str, dict[str, set[str]]] = {field: {} for field in FINGERPRINT_AXES}

    for (field, value), records in grouped.items():
        distinct_sources = {record.source for record in records}
        distinct_provenance = {
            f"{_canonical_token(record.source)}/{_canonical_token(record.source_field)}"
            for record in records
            if _canonical_token(record.source) and _canonical_token(record.source_field)
        }
        effective_confidences = []
        for record in records:
            role = classify_taxonomy_v2_signal_tier(record.field, record.value)
            effective_confidence = record.confidence
            effective_confidence *= get_taxonomy_v2_source_weight(record.source, record.source_field)
            effective_confidence *= get_taxonomy_v2_role_weight(role)
            effective_confidence += get_taxonomy_v2_rarity_weight(record.value)
            effective_confidences.append(min(0.99, effective_confidence))
        combined_confidence = max(effective_confidences or [0.0])
        combined_confidence = min(0.99, combined_confidence + 0.04 * (len(distinct_sources) - 1))
        threshold = 0.8 if field == "hard_exclusions" else 0.6
        if combined_confidence < threshold:
            continue
        confidence_by_field_value[field][value] = combined_confidence
        source_count_by_field_value[field][value] = len(distinct_sources)
        provenance_by_field_value[field][value] = distinct_provenance
        fingerprint[field].append(value)

    for field in FINGERPRINT_AXES:
        fingerprint[field] = sorted(set(fingerprint[field]))

    _apply_taxonomy_v2_co_signal_gates(
        fingerprint,
        confidence_by_field_value,
        source_count_by_field_value,
        provenance_by_field_value,
    )
    _apply_taxonomy_v2_false_positive_suppressions(
        fingerprint,
        confidence_by_field_value,
        source_count_by_field_value,
        provenance_by_field_value,
    )

    return fingerprint, confidence_by_field_value, source_count_by_field_value, provenance_by_field_value


def infer_derived_v2_evidence(
    fingerprint: dict[str, list[str]],
) -> list[TaxonomyV2EvidenceRecord]:
    evidence: list[TaxonomyV2EvidenceRecord] = []
    combat_styles = set(fingerprint.get("combat_style", []))
    session_shapes = set(fingerprint.get("session_shape", []))
    mode_profile = set(fingerprint.get("mode_profile", []))
    world_topology = set(fingerprint.get("world_topology", []))
    traversal_verbs = set(fingerprint.get("traversal_verbs", []))
    settings = set(fingerprint.get("setting", []))
    world_density = set(fingerprint.get("world_density", []))
    art_style = set(fingerprint.get("art_style", []))
    combat_structure = set(fingerprint.get("combat_structure", []))
    challenge_model = set(fingerprint.get("challenge_model", []))
    narrative_structure = set(fingerprint.get("narrative_structure", []))
    narrative_topic = set(fingerprint.get("narrative_topic", []))
    mechanics_structure = set(fingerprint.get("mechanics_structure", []))
    combat_presence = set(fingerprint.get("combat_presence", []))
    progression_model = set(fingerprint.get("progression_model", []))
    rules_goals = set(fingerprint.get("rules_goals", []))
    entity_interaction = set(fingerprint.get("entity_interaction", []))
    content_model = set(fingerprint.get("content_model", []))
    has_dominant_profile = "dominant" in combat_presence or bool(
        combat_styles & {"melee", "ranged", "magic", "hybrid", "stealth", "party_tactics", "shooter", "survival"}
    )
    if combat_styles & {"melee", "ranged", "magic", "hybrid", "stealth", "party_tactics", "shooter", "survival"}:
        record = _make_evidence(
            "combat_presence",
            "dominant",
            source="inference",
            source_field="combat_style",
            confidence=0.7,
            evidence_text="derived from combat_style evidence",
        )
        if record is not None:
            evidence.append(record)

    if "mmo" in fingerprint.get("mode_profile", []) and "mmo_persistent" not in fingerprint.get("content_model", []):
        record = _make_evidence(
            "content_model",
            "mmo_persistent",
            source="inference",
            source_field="mode_profile",
            confidence=0.72,
            evidence_text="derived from MMO mode evidence",
        )
        if record is not None:
            evidence.append(record)

    if (
        "premium_replayable" not in content_model
        and not (content_model & {"live_service", "mmo_persistent"})
        and "match_session" not in session_shapes
        and "pvp" not in mode_profile
        and has_dominant_profile
        and bool(progression_model & {"buildcraft", "gear_chase", "loot_rarity", "skill_tree", "base_growth"})
        and bool(
            rules_goals & {"build_and_optimize", "complete_quests", "defeat_bosses"}
            or entity_interaction & {"inventory_loot", "construction_placement"}
            or world_topology & {"semi_open", "open_world", "hub_and_spoke"}
        )
    ):
        record = _make_evidence(
            "content_model",
            "premium_replayable",
            source="inference",
            source_field="progression_model",
            confidence=0.84,
            evidence_text="derived from replayable buildcraft and loot progression profile",
        )
        if record is not None:
            evidence.append(record)

    if "mmo" in mode_profile and "persistent_shared_world" in world_topology:
        record = _make_evidence(
            "hard_exclusions",
            "mmo_first",
            source="inference",
            source_field="mode_profile",
            confidence=0.9,
            evidence_text="derived from persistent-world MMO identity",
        )
        if record is not None:
            evidence.append(record)

    if (
        not fingerprint.get("perspective")
        and "open_world" in world_topology
        and settings & {"high_fantasy", "dark_fantasy", "mythic"}
        and traversal_verbs & {"horseback", "climbing", "gliding"}
        and has_dominant_profile
    ):
        record = _make_evidence(
            "perspective",
            "third_person",
            source="inference",
            source_field="world_topology",
            confidence=0.76,
            evidence_text="derived from open-world fantasy traversal profile",
        )
        if record is not None:
            evidence.append(record)

    if (
        not fingerprint.get("perspective")
        and "persistent_shared_world" in world_topology
        and "mmo" in mode_profile
        and settings & {"high_fantasy", "dark_fantasy", "mythic", "sci_fi"}
        and has_dominant_profile
    ):
        record = _make_evidence(
            "perspective",
            "third_person",
            source="inference",
            source_field="mode_profile",
            confidence=0.74,
            evidence_text="derived from persistent-world MMO action profile",
        )
        if record is not None:
            evidence.append(record)

    if (
        not combat_styles
        and "open_world" in world_topology
        and settings & {"high_fantasy", "dark_fantasy", "mythic"}
        and (
            has_dominant_profile
            or (
                "third_person" in fingerprint.get("perspective", [])
                and (
                    "quest_driven" in fingerprint.get("progression_model", [])
                    or traversal_verbs & {"horseback", "climbing", "gliding"}
                )
            )
        )
        and "party_management" not in combat_structure
        and ("third_person" in fingerprint.get("perspective", []) or traversal_verbs & {"horseback", "climbing", "gliding"})
    ):
        record = _make_evidence(
            "combat_style",
            "hybrid",
            source="inference",
            source_field="combat_presence",
            confidence=0.74,
            evidence_text="derived from open-world fantasy action profile",
        )
        if record is not None:
            evidence.append(record)

    if (
        "shooter" in combat_styles
        and mode_profile & {"pvp", "pvpve"}
        and "match_session" not in session_shapes
        and "campaign" not in session_shapes
        and not (
            mode_profile & {"drop_in_coop", "party_coop"}
            and "horror" in fingerprint.get("setting", [])
            and "crowd_control" in fingerprint.get("combat_structure", [])
        )
    ):
        record = _make_evidence(
            "session_shape",
            "match_session",
            source="inference",
            source_field="mode_profile",
            confidence=0.76,
            evidence_text="derived from competitive shooter profile",
        )
        if record is not None:
            evidence.append(record)

    transport_sim_profile = (
        "driving" in fingerprint.get("traversal_verbs", [])
        and "sim_realism" in fingerprint.get("challenge_model", [])
        and "vehicle_control" in fingerprint.get("interface_control", [])
        and "win_races" not in fingerprint.get("rules_goals", [])
        and "vehicular_racing" not in fingerprint.get("mechanics_structure", [])
    )

    if (
        "driving" in fingerprint.get("traversal_verbs", [])
        and "match_session" not in session_shapes
        and not transport_sim_profile
        and not (
            "campaign" in session_shapes
            and ("shooter" in combat_styles or mode_profile & {"drop_in_coop", "party_coop"})
        )
    ):
        record = _make_evidence(
            "session_shape",
            "match_session",
            source="inference",
            source_field="traversal_verbs",
            confidence=0.72,
            evidence_text="derived from driving-focused profile",
        )
        if record is not None:
            evidence.append(record)

    if "shooter" in combat_styles and "first_person" in fingerprint.get("perspective", []):
        record = _make_evidence(
            "hard_exclusions",
            "fps_only",
            source="inference",
            source_field="combat_style",
            confidence=0.86,
            evidence_text="derived from first-person shooter profile",
        )
        if record is not None:
            evidence.append(record)

    if (
        "shooter" in combat_styles
        and "campaign" in session_shapes
        and not (mode_profile & {"pvp", "pvpve"})
        and "match_session" not in session_shapes
    ):
        record = _make_evidence(
            "hard_exclusions",
            "campaign_only",
            source="inference",
            source_field="session_shape",
            confidence=0.9,
            evidence_text="derived from shooter campaign profile without competitive modes",
        )
        if record is not None:
            evidence.append(record)

    if (
        "campaign" not in session_shapes
        and "quest_driven" in fingerprint.get("progression_model", [])
        and (
            narrative_structure & {"authored_branching", "quest_web", "authored_linear"}
            or rules_goals & {"complete_quests"}
        )
    ):
        record = _make_evidence(
            "session_shape",
            "campaign",
            source="inference",
            source_field="progression_model",
            confidence=0.84,
            evidence_text="derived from quest-driven narrative progression",
        )
        if record is not None:
            evidence.append(record)

    if (
        "third_person" in fingerprint.get("perspective", [])
        and "authored_linear" in narrative_structure
        and settings & {"high_fantasy", "dark_fantasy", "mythic"}
        and (
            "dominant" in fingerprint.get("combat_presence", [])
            or "boss_centric" in combat_structure
            or "defeat_bosses" in rules_goals
        )
        and "open_world" not in world_topology
        and "setpiece_driven" not in world_density
    ):
        record = _make_evidence(
            "world_density",
            "setpiece_driven",
            source="inference",
            source_field="narrative_structure",
            confidence=0.88,
            evidence_text="derived from authored-linear third-person mythic action profile",
        )
        if record is not None:
            evidence.append(record)

    if (
        "third_person" in fingerprint.get("perspective", [])
        and "authored_linear" in narrative_structure
        and settings & {"high_fantasy", "dark_fantasy", "mythic"}
        and (
            "dominant" in fingerprint.get("combat_presence", [])
            or "boss_centric" in combat_structure
            or "defeat_bosses" in rules_goals
        )
        and "open_world" not in world_topology
        and not (world_topology & {"linear", "semi_open"})
    ):
        record = _make_evidence(
            "world_topology",
            "semi_open",
            source="inference",
            source_field="narrative_structure",
            confidence=0.82,
            evidence_text="derived from authored-linear third-person mythic action structure",
        )
        if record is not None:
            evidence.append(record)

    if (
        "party_management" in combat_structure
        and "authored_linear" in narrative_structure
        and (
            "anime" in art_style
            or "heroic_journey" in narrative_topic
            or "party_management_loop" in mechanics_structure
        )
    ):
        record = _make_evidence(
            "hard_exclusions",
            "jrpg_first",
            source="inference",
            source_field="combat_structure",
            confidence=0.88,
            evidence_text="derived from party-based authored-linear JRPG profile",
        )
        if record is not None:
            evidence.append(record)

    if (
        "authored_linear" in narrative_structure
        and ("boss_centric" in combat_structure or "defeat_bosses" in rules_goals)
        and "third_person" in fingerprint.get("perspective", [])
        and "open_world" not in world_topology
        and not traversal_verbs
    ):
        record = _make_evidence(
            "hard_exclusions",
            "cinematic_linear_first",
            source="inference",
            source_field="narrative_structure",
            confidence=0.9,
            evidence_text="derived from authored-linear third-person boss-driven action profile",
        )
        if record is not None:
            evidence.append(record)

    if "isometric" in fingerprint.get("perspective", []):
        record = _make_evidence(
            "hard_exclusions",
            "isometric_first",
            source="inference",
            source_field="perspective",
            confidence=0.86,
            evidence_text="derived from isometric presentation profile",
        )
        if record is not None:
            evidence.append(record)

    if "tactical_overhead" in fingerprint.get("perspective", []):
        record = _make_evidence(
            "hard_exclusions",
            "overhead_strategy_first",
            source="inference",
            source_field="perspective",
            confidence=0.9,
            evidence_text="derived from tactical overhead strategy profile",
        )
        if record is not None:
            evidence.append(record)

    if "boss_centric" in combat_structure and "defeat_bosses" not in rules_goals:
        record = _make_evidence(
            "rules_goals",
            "defeat_bosses",
            source="inference",
            source_field="combat_structure",
            confidence=0.82,
            evidence_text="derived from boss-centric combat structure",
        )
        if record is not None:
            evidence.append(record)

    if "soulslike" in challenge_model and "defeat_bosses" not in rules_goals:
        record = _make_evidence(
            "rules_goals",
            "defeat_bosses",
            source="inference",
            source_field="challenge_model",
            confidence=0.8,
            evidence_text="derived from soulslike challenge profile",
        )
        if record is not None:
            evidence.append(record)

    if (
        "defeat_bosses" in rules_goals
        and "boss_centric" not in combat_structure
        and "dominant" in combat_presence
        and "third_person" in fingerprint.get("perspective", [])
    ):
        record = _make_evidence(
            "combat_structure",
            "boss_centric",
            source="inference",
            source_field="rules_goals",
            confidence=0.74,
            evidence_text="derived from third-person action profile focused on defeating bosses",
        )
        if record is not None:
            evidence.append(record)

    if (
        (
            "rhythm_timing" in mechanics_structure
            or "hit_beats" in rules_goals
            or "timing_input" in fingerprint.get("interface_control", [])
        )
        and not (fingerprint.get("input_complexity", []) and set(fingerprint.get("input_complexity", [])) & {"moderate", "mastery_heavy"})
    ):
        record = _make_evidence(
            "input_complexity",
            "moderate",
            source="inference",
            source_field="mechanics_structure",
            confidence=0.84,
            evidence_text="derived from rhythm-timing input demands",
        )
        if record is not None:
            evidence.append(record)

    if "historical" in settings and "magic" not in combat_styles and "mmo" not in mode_profile:
        record = _make_evidence(
            "hard_exclusions",
            "historical_first",
            source="inference",
            source_field="setting",
            confidence=0.88,
            evidence_text="derived from historical action-adventure profile",
        )
        if record is not None:
            evidence.append(record)

    if "survival" in combat_styles and "horror" in fingerprint.get("setting", []):
        record = _make_evidence(
            "hard_exclusions",
            "pure_survival_horror",
            source="inference",
            source_field="combat_style",
            confidence=0.88,
            evidence_text="derived from horror survival profile",
        )
        if record is not None:
            evidence.append(record)

    if "shooter" in combat_styles and "comedic" in fingerprint.get("tone", []):
        record = _make_evidence(
            "hard_exclusions",
            "comedy_shooter",
            source="inference",
            source_field="tone",
            confidence=0.86,
            evidence_text="derived from comedic shooter profile",
        )
        if record is not None:
            evidence.append(record)

    if (
        "mission_based" in fingerprint.get("world_topology", [])
        and "open_world" not in fingerprint.get("world_topology", [])
        and "mission_session" in fingerprint.get("session_shape", [])
    ):
        record = _make_evidence(
            "hard_exclusions",
            "mission_based_only",
            source="inference",
            source_field="world_topology",
            confidence=0.84,
            evidence_text="derived from mission-based-only structure",
        )
        if record is not None:
            evidence.append(record)

    if "match_session" in fingerprint.get("session_shape", []):
        record = _make_evidence(
            "hard_exclusions",
            "match_based_only",
            source="inference",
            source_field="session_shape",
            confidence=0.84,
            evidence_text="derived from match-session structure",
        )
        if record is not None:
            evidence.append(record)

    if "platforming" in fingerprint.get("traversal_verbs", []) and "level_based" in fingerprint.get("world_topology", []):
        record = _make_evidence(
            "hard_exclusions",
            "platformer_first",
            source="inference",
            source_field="traversal_verbs",
            confidence=0.84,
            evidence_text="derived from level-based platforming profile",
        )
        if record is not None:
            evidence.append(record)

    return evidence


def _apply_override_to_fingerprint(
    game: Game,
    fingerprint: dict[str, list[str]],
) -> tuple[dict[str, list[str]], list[TaxonomyV2EvidenceRecord], bool]:
    override = get_taxonomy_v2_override(game)
    if not game_has_taxonomy_v2_override(game):
        return fingerprint, [], False

    updated = {field: list(values) for field, values in fingerprint.items()}
    evidence: list[TaxonomyV2EvidenceRecord] = []
    rationale = override.get("rationale")
    for axis, values in override["replace"].items():
        if axis in updated:
            updated[axis] = list(values)
            for value in values:
                record = _make_evidence(
                    axis,
                    value,
                    source="override",
                    source_field=axis,
                    confidence=0.99,
                    evidence_text=rationale or f"override replace for {axis}",
                    curated=True,
                )
                if record is not None:
                    evidence.append(record)
    for axis, values in override["add"].items():
        if axis not in updated:
            continue
        updated[axis] = sorted(set(updated[axis]) | set(values))
        for value in values:
            record = _make_evidence(
                axis,
                value,
                source="override",
                source_field=axis,
                confidence=0.99,
                evidence_text=rationale or f"override add for {axis}",
                curated=True,
            )
            if record is not None:
                evidence.append(record)
    for axis, values in override["remove"].items():
        if axis not in updated:
            continue
        updated[axis] = sorted(set(updated[axis]) - set(values))

    updated["hard_exclusions"] = sorted(
        (set(updated["hard_exclusions"]) | set(override["hard_exclusions"]["add"]))
        - set(override["hard_exclusions"]["remove"])
    )
    updated["soft_penalties"] = sorted(
        (set(updated["soft_penalties"]) | set(override["soft_penalties"]["add"]))
        - set(override["soft_penalties"]["remove"])
    )
    return updated, evidence, True


def assign_taxonomy_v2_archetypes(
    fingerprint: dict[str, list[str]],
    confidence_by_field_value: dict[str, dict[str, float]],
) -> list[ArchetypeCandidate]:
    graph = load_archetype_graph_v2()
    facet_matrix = load_facet_matrix()
    assignment_rules = facet_matrix.get("assignment") or {}
    strict_min_required_hits = {
        _canonical_token(key): int(value)
        for key, value in (assignment_rules.get("strict_min_required_hits") or {}).items()
        if _canonical_token(key)
    }
    mandatory_required_axes = {
        _canonical_token(key): {
            _canonical_token(axis)
            for axis in value
            if _canonical_token(axis)
        }
        for key, value in (assignment_rules.get("mandatory_required_axes") or {}).items()
        if _canonical_token(key)
    }
    excluded = set(fingerprint.get("hard_exclusions", []))
    candidates: list[ArchetypeCandidate] = []

    for archetype, node in graph.get("nodes", {}).items():
        node_hard_exclusions = {_canonical_token(value) for value in node.get("hard_exclusions", [])}
        node_hard_exclusions.update(_ADDITIONAL_NODE_HARD_EXCLUSIONS.get(archetype, set()))
        node_hard_exclusions.update(_ASSIGNMENT_ONLY_NODE_HARD_EXCLUSIONS.get(archetype, set()))
        if excluded & node_hard_exclusions:
            continue

        required_axes: dict[str, list[str]] = node.get("required_axes", {})
        preferred_axes: dict[str, list[str]] = node.get("preferred_axes", {})
        required_total = len(required_axes)
        preferred_total = len(preferred_axes)
        required_hits = 0
        preferred_hits = 0
        matched_confidences: list[float] = []
        matched_required_axes: list[str] = []

        for axis, values in required_axes.items():
            actual = set(fingerprint.get(axis, []))
            expected = {_canonical_token(value) for value in values}
            overlap = actual & expected
            if not overlap:
                continue
            required_hits += 1
            matched_required_axes.append(axis)
            matched_confidences.append(
                max(confidence_by_field_value.get(axis, {}).get(value, 0.6) for value in overlap)
            )

        minimum_required_hits = 0
        if required_total:
            minimum_required_hits = max(2, math.ceil(required_total * 0.6))
        minimum_required_hits = max(
            minimum_required_hits,
            strict_min_required_hits.get(archetype, _STRICT_MIN_REQUIRED_HITS.get(archetype, 0)),
        )
        if required_hits < minimum_required_hits:
            continue
        mandatory_axes = set(node.get("mandatory_axes", []) or [])
        mandatory_axes.update(mandatory_required_axes.get(archetype, _MANDATORY_REQUIRED_AXES.get(archetype, set())))
        if mandatory_axes and any(axis not in matched_required_axes for axis in mandatory_axes):
            continue

        for axis, values in preferred_axes.items():
            actual = set(fingerprint.get(axis, []))
            expected = {_canonical_token(value) for value in values}
            overlap = actual & expected
            if not overlap:
                continue
            preferred_hits += 1
            matched_confidences.append(
                max(confidence_by_field_value.get(axis, {}).get(value, 0.6) for value in overlap)
            )

        required_ratio = required_hits / required_total if required_total else 0.0
        preferred_ratio = preferred_hits / preferred_total if preferred_total else 0.0
        evidence_confidence = sum(matched_confidences) / len(matched_confidences) if matched_confidences else 0.0
        candidate_confidence = min(
            0.99,
            0.35 + (required_ratio * 0.35) + (preferred_ratio * 0.1) + (evidence_confidence * 0.2),
        )
        score = (required_hits * 100) + (preferred_hits * 25) + int(round(evidence_confidence * 10))
        candidates.append(
            ArchetypeCandidate(
                archetype=archetype,
                family=_canonical_token(node.get("family", "")),
                score=score,
                required_hits=required_hits,
                required_total=required_total,
                preferred_hits=preferred_hits,
                preferred_total=preferred_total,
                confidence=candidate_confidence,
            )
        )

    candidates.sort(key=lambda item: (-item.score, -item.confidence, item.archetype))
    return candidates


def rank_taxonomy_v2_near_misses(
    fingerprint: dict[str, list[str]] | None,
    *,
    hard_exclusions: Iterable[str] | None = None,
    limit: int = 5,
) -> list[TaxonomyV2NearMiss]:
    graph = load_archetype_graph_v2()
    actual_fingerprint = fingerprint or {}
    excluded = {
        _canonical_token(value)
        for value in (hard_exclusions if hard_exclusions is not None else actual_fingerprint.get("hard_exclusions", []))
        if _canonical_token(value)
    }

    near_misses: list[TaxonomyV2NearMiss] = []
    for archetype, node in graph.get("nodes", {}).items():
        node_hard_exclusions = {
            _canonical_token(value)
            for value in node.get("hard_exclusions", [])
            if _canonical_token(value)
        }
        if excluded & node_hard_exclusions:
            continue

        required_axes: dict[str, list[str]] = node.get("required_axes", {})
        preferred_axes: dict[str, list[str]] = node.get("preferred_axes", {})
        matched_required_axes: list[str] = []
        missing_required_axes: list[str] = []
        matched_preferred_axes: list[str] = []

        for axis, values in required_axes.items():
            actual = {_canonical_token(value) for value in actual_fingerprint.get(axis, []) if _canonical_token(value)}
            expected = {_canonical_token(value) for value in values if _canonical_token(value)}
            if actual & expected:
                matched_required_axes.append(axis)
            else:
                missing_required_axes.append(axis)

        for axis, values in preferred_axes.items():
            actual = {_canonical_token(value) for value in actual_fingerprint.get(axis, []) if _canonical_token(value)}
            expected = {_canonical_token(value) for value in values if _canonical_token(value)}
            if actual & expected:
                matched_preferred_axes.append(axis)

        if not matched_required_axes and not matched_preferred_axes:
            continue

        closeness_score = (
            len(matched_required_axes) * 100
            + len(matched_preferred_axes) * 20
            - len(missing_required_axes) * 15
        )
        near_misses.append(
            TaxonomyV2NearMiss(
                archetype=archetype,
                family=_canonical_token(node.get("family", "")),
                closeness_score=closeness_score,
                required_hits=len(matched_required_axes),
                required_total=len(required_axes),
                preferred_hits=len(matched_preferred_axes),
                preferred_total=len(preferred_axes),
                matched_required_axes=tuple(sorted(matched_required_axes)),
                missing_required_axes=tuple(sorted(missing_required_axes)),
                matched_preferred_axes=tuple(sorted(matched_preferred_axes)),
            )
        )

    near_misses.sort(
        key=lambda item: (
            -item.required_hits,
            len(item.missing_required_axes),
            -item.preferred_hits,
            -item.closeness_score,
            item.archetype,
        )
    )
    return near_misses[:limit]


def _format_v2_match_reason(prefix: str, values: list[str], *, limit: int = 2) -> str:
    rendered = ", ".join(display_taxonomy_v2_token(value) for value in values[:limit])
    return f"{prefix}: {rendered}"


def get_taxonomy_v2_match_weights(axis: str) -> dict[str, int]:
    matrix = load_facet_matrix()
    match_weights = matrix.get("match_weights") or {}
    weights = match_weights.get(_canonical_token(axis), {})
    if isinstance(weights, dict):
        return {_canonical_token(key): int(value) for key, value in weights.items() if _canonical_token(key)}
    return {}


def _weighted_token_score(
    values: list[str],
    weights: dict[str, int],
    *,
    default: int,
) -> int:
    score = 0
    for value in values:
        score += weights.get(value, default)
        rarity = get_taxonomy_v2_rarity_bucket(value)
        if rarity == "uncommon":
            score += 2
        elif rarity == "rare":
            score += 4
    return score


def build_similarity_breakdown_v2(
    anchor: Game,
    candidate: Game,
) -> SimilarityBreakdownV2 | None:
    if not game_has_sufficient_taxonomy_v2_support(anchor) or not game_has_sufficient_taxonomy_v2_support(candidate):
        return None

    graph = load_connection_matrix()
    anchor_archetype = _canonical_token(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _canonical_token(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if not anchor_archetype or not candidate_archetype:
        return None

    anchor_node = graph.get("nodes", {}).get(anchor_archetype)
    candidate_node = graph.get("nodes", {}).get(candidate_archetype)
    if not anchor_node or not candidate_node:
        return None

    anchor_blocked = {_canonical_token(value) for value in anchor_node.get("blocked_neighbors", []) if _canonical_token(value)}
    candidate_blocked = {_canonical_token(value) for value in candidate_node.get("blocked_neighbors", []) if _canonical_token(value)}
    if candidate_archetype in anchor_blocked or anchor_archetype in candidate_blocked:
        return None

    anchor_hard_exclusions = set(getattr(anchor, "taxonomy_v2_hard_exclusions", None) or [])
    candidate_hard_exclusions = set(getattr(candidate, "taxonomy_v2_hard_exclusions", None) or [])
    anchor_node_exclusions = {_canonical_token(value) for value in anchor_node.get("hard_exclusions", []) if _canonical_token(value)}
    candidate_node_exclusions = {_canonical_token(value) for value in candidate_node.get("hard_exclusions", []) if _canonical_token(value)}
    anchor_node_exclusions.update(_ADDITIONAL_NODE_HARD_EXCLUSIONS.get(anchor_archetype, set()))
    candidate_node_exclusions.update(_ADDITIONAL_NODE_HARD_EXCLUSIONS.get(candidate_archetype, set()))
    if candidate_hard_exclusions & anchor_node_exclusions:
        return None
    if anchor_hard_exclusions & candidate_node_exclusions:
        return None

    candidate_secondaries = {
        _canonical_token(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _canonical_token(value)
    }

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)

    shared_world_topology = sorted(anchor_fingerprint["world_topology"] & candidate_fingerprint["world_topology"])
    shared_session_shape = sorted(anchor_fingerprint["session_shape"] & candidate_fingerprint["session_shape"])
    shared_combat_style = sorted(anchor_fingerprint["combat_style"] & candidate_fingerprint["combat_style"])
    shared_combat_tempo = sorted(anchor_fingerprint["combat_tempo"] & candidate_fingerprint["combat_tempo"])
    shared_combat_structure = sorted(anchor_fingerprint["combat_structure"] & candidate_fingerprint["combat_structure"])
    shared_mode_profile = sorted(anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"])
    shared_content_model = sorted(anchor_fingerprint["content_model"] & candidate_fingerprint["content_model"])
    shared_progression_model = sorted(anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"])
    shared_traversal_verbs = sorted(anchor_fingerprint["traversal_verbs"] & candidate_fingerprint["traversal_verbs"])
    shared_setting = sorted(anchor_fingerprint["setting"] & candidate_fingerprint["setting"])
    shared_tone = sorted(anchor_fingerprint["tone"] & candidate_fingerprint["tone"])
    shared_perspective = sorted(anchor_fingerprint["perspective"] & candidate_fingerprint["perspective"])
    shared_keyword_layer = sorted(anchor_fingerprint["keyword_layer"] & candidate_fingerprint["keyword_layer"])
    shared_mechanics_structure = sorted(anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"])
    shared_rules_goals = sorted(anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"])
    shared_entity_interaction = sorted(anchor_fingerprint["entity_interaction"] & candidate_fingerprint["entity_interaction"])
    shared_narrative_topic = sorted(anchor_fingerprint["narrative_topic"] & candidate_fingerprint["narrative_topic"])
    shared_visual_presentation = sorted(anchor_fingerprint["visual_presentation"] & candidate_fingerprint["visual_presentation"])
    shared_art_style = sorted(anchor_fingerprint["art_style"] & candidate_fingerprint["art_style"])
    shared_pacing = sorted(anchor_fingerprint["pacing"] & candidate_fingerprint["pacing"])
    shared_interface_control = sorted(anchor_fingerprint["interface_control"] & candidate_fingerprint["interface_control"])
    shared_sports_theme = sorted(anchor_fingerprint["sports_theme"] & candidate_fingerprint["sports_theme"])
    shared_vehicular_theme = sorted(anchor_fingerprint["vehicular_theme"] & candidate_fingerprint["vehicular_theme"])
    shared_challenge_model = sorted(anchor_fingerprint["challenge_model"] & candidate_fingerprint["challenge_model"])
    shared_studios = sorted(set(getattr(anchor, "taxonomy_studios", None) or []) & set(getattr(candidate, "taxonomy_studios", None) or []))
    anchor_challenge = anchor_fingerprint["challenge_model"]
    candidate_challenge = candidate_fingerprint["challenge_model"]
    candidate_soulslike_core_hits = sum(
        1
        for values in (
            candidate_fingerprint["challenge_model"] & {"soulslike"},
            candidate_fingerprint["combat_structure"] & {"boss_centric"},
        )
        if values
    )
    candidate_soulslike_identity_hits = candidate_soulslike_core_hits + sum(
        1
        for values in (
            candidate_fingerprint["rules_goals"] & {"defeat_bosses"},
            candidate_fingerprint["combat_style"] & {"melee", "magic", "hybrid"},
            candidate_fingerprint["world_topology"] & {"open_world"},
        )
        if values
    )
    candidate_open_world_fantasy_identity_hits = sum(
        1
        for values in (
            candidate_fingerprint["combat_style"] & {"melee", "magic", "hybrid"},
            candidate_fingerprint["rules_goals"] & {"complete_quests", "defeat_bosses", "build_and_optimize"},
            candidate_fingerprint["progression_model"] & {"quest_driven", "buildcraft", "skill_tree", "base_growth"},
            candidate_fingerprint["traversal_verbs"] & {"horseback", "climbing", "gliding"},
            candidate_fingerprint["entity_interaction"] & {"dialogue_choice", "construction_placement"},
        )
        if values
    )
    candidate_open_world_fantasy_frontier_hits = sum(
        1
        for values in (
            candidate_fingerprint["traversal_verbs"] & {"horseback", "climbing", "gliding"},
            candidate_fingerprint["rules_goals"] & {"complete_quests"},
            candidate_fingerprint["progression_model"] & {"quest_driven", "gear_chase"},
        )
        if values
    )
    candidate_open_world_fantasy_sandbox_signals = bool(
        candidate_fingerprint["world_density"] & {"systemic_sandbox"}
        or candidate_fingerprint["session_shape"] & {"sandbox_loop"}
        or candidate_fingerprint["mode_profile"] & {"drop_in_coop", "party_coop", "mmo", "pvpve"}
    )
    anchor_open_world_fantasy_sandbox_signals = bool(
        anchor_fingerprint["world_density"] & {"systemic_sandbox"}
        or anchor_fingerprint["session_shape"] & {"sandbox_loop"}
        or anchor_fingerprint["mode_profile"] & {"drop_in_coop", "party_coop", "mmo", "pvpve"}
    )
    candidate_western_identity_hits = sum(
        1
        for values in (
            candidate_fingerprint["world_topology"] & {"open_world"},
            candidate_fingerprint["rules_goals"] & {"complete_quests"},
            candidate_fingerprint["entity_interaction"] & {"dialogue_choice"},
            candidate_fingerprint["progression_model"] & {"quest_driven"},
        )
        if values
    )
    candidate_mmo_identity_hits = sum(
        1
        for values in (
            candidate_fingerprint["world_topology"] & {"persistent_shared_world"},
            candidate_fingerprint["traversal_verbs"] & {"horseback"},
            candidate_fingerprint["rules_goals"] & {"build_and_optimize"},
            candidate_fingerprint["entity_interaction"] & {"construction_placement"},
            candidate_fingerprint["progression_model"] & {"base_growth"},
            candidate_fingerprint["combat_style"] & {"melee", "magic", "hybrid"},
        )
        if values
    )
    candidate_cinematic_identity_hits = sum(
        1
        for values in (
            candidate_fingerprint["rules_goals"] & {"defeat_bosses", "complete_quests"},
            candidate_fingerprint["progression_model"] & {"buildcraft", "skill_tree"},
            candidate_fingerprint["combat_style"] & {"melee", "magic", "hybrid"},
            candidate_fingerprint["world_topology"] & {"semi_open", "linear"},
            candidate_fingerprint["narrative_structure"] & {"authored_linear"},
        )
        if values
    )

    relationship = _resolve_connection_relationship(
        anchor_archetype=anchor_archetype,
        candidate_archetype=candidate_archetype,
        candidate_secondaries=candidate_secondaries,
        anchor_fingerprint=anchor_fingerprint,
        candidate_fingerprint=candidate_fingerprint,
        shared_world_topology=shared_world_topology,
        shared_combat_style=shared_combat_style,
        shared_combat_structure=shared_combat_structure,
        shared_progression_model=shared_progression_model,
        shared_traversal_verbs=shared_traversal_verbs,
        shared_setting=shared_setting,
        shared_tone=shared_tone,
        shared_perspective=shared_perspective,
        shared_keyword_layer=shared_keyword_layer,
        shared_mechanics_structure=shared_mechanics_structure,
        shared_rules_goals=shared_rules_goals,
        shared_entity_interaction=shared_entity_interaction,
        shared_narrative_topic=shared_narrative_topic,
        shared_challenge_model=shared_challenge_model,
    )
    if relationship is None:
        cross_horror_bridge = (
            anchor_archetype in {"action_horror", "survival_horror"}
            and (
                candidate_archetype in {"action_horror", "survival_horror", "psychological_horror"}
                or bool(candidate_secondaries & {"action_horror", "survival_horror", "psychological_horror"})
            )
            and bool(set(shared_setting) & {"horror"})
            and bool(
                set(shared_tone) & {"bleak", "grotesque", "melancholic"}
                or shared_narrative_topic
                or shared_mode_profile
            )
            and bool(
                set(shared_perspective) & {"third_person", "first_person"}
                or (
                    set(candidate_fingerprint["perspective"]) & {"third_person", "first_person"}
                    and set(anchor_fingerprint["perspective"]) & {"third_person", "first_person"}
                )
            )
        )
        if cross_horror_bridge:
            relationship = "bridge_neighbor"
    if relationship is None:
        return None

    studio_bridge = (
        relationship in {"adjacent_neighbor", "adjacent_secondary", "bridge_neighbor", "bridge_secondary"}
        and bool(shared_studios)
        and bool(shared_setting)
        and bool(shared_perspective)
        and bool(shared_progression_model)
        and bool(shared_combat_style or shared_combat_structure)
    )
    adjacent_persistent_world_bridge = (
        relationship in {"adjacent_neighbor", "adjacent_secondary", "bridge_neighbor", "bridge_secondary"}
        and "persistent_shared_world" in candidate_fingerprint["world_topology"]
        and bool(shared_world_topology)
        and bool(shared_setting)
        and bool(shared_perspective)
        and bool(shared_combat_style or shared_combat_structure)
    )
    traversal_identity_bridge = (
        bool(anchor_fingerprint["traversal_verbs"] & {"horseback", "climbing", "gliding"})
        and bool(candidate_fingerprint["traversal_verbs"] & {"horseback", "climbing", "gliding"})
        and bool(shared_world_topology)
        and bool(shared_setting)
    )
    derived_identity_bridge = bool(
        shared_mechanics_structure
        or (shared_keyword_layer and shared_rules_goals)
        or (shared_keyword_layer and shared_entity_interaction)
    )
    low_combat_anchor = bool(anchor_fingerprint["combat_presence"] & {"none"}) or not (
        anchor_fingerprint["combat_style"] or anchor_fingerprint["combat_structure"]
    )
    low_combat_candidate = bool(candidate_fingerprint["combat_presence"] & {"none"}) or not (
        candidate_fingerprint["combat_style"] or candidate_fingerprint["combat_structure"]
    )
    low_combat_identity_bridge = (
        relationship in {"same", "strong_neighbor", "strong_secondary"}
        and (low_combat_anchor or low_combat_candidate)
        and (
            (shared_session_shape and shared_mode_profile)
            or (shared_interface_control and (shared_rules_goals or shared_mechanics_structure or shared_narrative_topic))
            or (shared_sports_theme and (shared_session_shape or shared_mode_profile))
            or (shared_vehicular_theme and (shared_session_shape or shared_mode_profile))
            or (
                shared_narrative_topic
                and shared_interface_control
                and (shared_session_shape or shared_visual_presentation or shared_art_style)
            )
            or (
                shared_session_shape
                and (
                    shared_visual_presentation
                    or shared_art_style
                    or shared_pacing
                    or shared_interface_control
                    or shared_rules_goals
                )
            )
        )
    )
    loot_action_rpg_identity_bridge = (
        relationship in {"same", "strong_neighbor", "strong_secondary"}
        and anchor_archetype == "loot_action_rpg"
        and (candidate_archetype == "loot_action_rpg" or "loot_action_rpg" in candidate_secondaries)
        and bool(anchor_fingerprint["combat_presence"] & {"dominant"})
        and bool(candidate_fingerprint["combat_presence"] & {"dominant"})
        and bool(shared_mode_profile)
        and bool(shared_combat_style or shared_progression_model)
        and bool(
            shared_content_model
            or shared_rules_goals
            or shared_entity_interaction
            or (
                anchor_fingerprint["progression_model"] & {"buildcraft", "gear_chase", "loot_rarity", "skill_tree", "base_growth"}
                and candidate_fingerprint["progression_model"] & {"buildcraft", "gear_chase", "loot_rarity", "skill_tree", "base_growth"}
            )
        )
    )
    farming_sim_identity_bridge = (
        relationship in {"same", "strong_neighbor", "strong_secondary"}
        and anchor_archetype == "farming_sim"
        and (candidate_archetype == "farming_sim" or "farming_sim" in candidate_secondaries)
        and bool(anchor_fingerprint["combat_presence"] & {"none"})
        and bool(candidate_fingerprint["combat_presence"] & {"none"})
        and bool(shared_mode_profile)
        and bool(
            shared_tone
            or shared_challenge_model
            or (
                anchor_fingerprint["progression_model"] & {"base_growth", "relationship_social"}
                and candidate_fingerprint["progression_model"] & {"base_growth", "relationship_social"}
            )
            or (
                anchor_fingerprint["world_density"] & {"sandbox_light"}
                and candidate_fingerprint["world_density"] & {"sandbox_light"}
            )
        )
    )
    creative_sandbox_identity_bridge = (
        relationship in {"same", "strong_neighbor", "strong_secondary"}
        and anchor_archetype == "creative_sandbox_adventure"
        and (
            candidate_archetype == "creative_sandbox_adventure"
            or "creative_sandbox_adventure" in candidate_secondaries
        )
        and bool(anchor_fingerprint["world_density"] & {"systemic_sandbox"})
        and bool(candidate_fingerprint["world_density"] & {"systemic_sandbox"})
        and bool(
            shared_progression_model
            or (
                anchor_fingerprint["progression_model"] & {"buildcraft"}
                and candidate_fingerprint["progression_model"] & {"buildcraft"}
            )
        )
        and bool(
            shared_entity_interaction
            or shared_mechanics_structure
            or shared_rules_goals
            or (
                anchor_fingerprint["entity_interaction"] & {"construction_placement"}
                and candidate_fingerprint["entity_interaction"] & {"construction_placement"}
            )
        )
    )
    jrpg_story_identity_bridge = (
        relationship in {"same", "strong_neighbor", "strong_secondary"}
        and anchor_archetype == "jrpg_story_rpg"
        and (candidate_archetype == "jrpg_story_rpg" or "jrpg_story_rpg" in candidate_secondaries)
        and "none" not in candidate_fingerprint["combat_presence"]
        and bool(set(shared_session_shape) & {"campaign"})
        and bool(
            set(shared_combat_structure) & {"party_management"}
            or set(shared_combat_tempo) & {"tactical"}
            or set(shared_progression_model) & {"skill_tree", "quest_driven"}
            or (
                anchor_fingerprint["combat_structure"] & {"party_management"}
                and candidate_fingerprint["combat_structure"] & {"party_management"}
            )
        )
    )
    metroidvania_identity_bridge = (
        relationship in {"same", "strong_neighbor", "strong_secondary"}
        and anchor_archetype == "metroidvania"
        and (candidate_archetype == "metroidvania" or "metroidvania" in candidate_secondaries)
        and bool(set(shared_traversal_verbs) & {"platforming"})
        and bool(
            set(shared_world_topology) & {"semi_open", "level_based", "open_world"}
            or set(shared_progression_model) & {"metaprogression", "skill_tree"}
        )
        and bool(
            set(shared_perspective) & {"side_scrolling"}
            or set(shared_mode_profile) & {"single_player"}
        )
    )
    precision_platformer_identity_bridge = (
        relationship in {"same", "strong_neighbor", "strong_secondary"}
        and anchor_archetype == "precision_platformer"
        and (candidate_archetype == "precision_platformer" or "precision_platformer" in candidate_secondaries)
        and bool(set(shared_world_topology) & {"level_based"})
        and bool(set(shared_perspective) & {"side_scrolling"})
        and bool(set(shared_traversal_verbs) & {"platforming"})
        and bool(
            set(shared_challenge_model) & {"precision_platforming"}
            or shared_mode_profile
            or (
                set(anchor_fingerprint["input_complexity"]) & {"mastery_heavy"}
                and set(candidate_fingerprint["input_complexity"]) & {"mastery_heavy"}
            )
        )
    )
    hidden_object_identity_bridge = (
        relationship in {"same", "strong_neighbor", "strong_secondary"}
        and anchor_archetype == "hidden_object_puzzle"
        and (candidate_archetype == "hidden_object_puzzle" or "hidden_object_puzzle" in candidate_secondaries)
        and bool(anchor_fingerprint["combat_presence"] & {"none"})
        and bool(candidate_fingerprint["combat_presence"] & {"none"})
        and bool(set(shared_challenge_model) & {"puzzle_gating"})
        and bool(
            shared_mode_profile
            or shared_interface_control
            or shared_keyword_layer
            or shared_mechanics_structure
            or shared_rules_goals
            or shared_narrative_topic
        )
    )
    collectathon_identity_bridge = (
        relationship in {"same", "strong_neighbor", "strong_secondary"}
        and anchor_archetype == "3d_collectathon"
        and (candidate_archetype == "3d_collectathon" or "3d_collectathon" in candidate_secondaries)
        and bool(set(shared_perspective) & {"third_person"})
        and bool(set(shared_traversal_verbs) & {"platforming", "climbing", "parkour"})
        and bool(
            set(shared_world_topology) & {"level_based", "open_world"}
            or shared_mode_profile
            or shared_keyword_layer
            or shared_mechanics_structure
        )
    )
    visual_novel_identity_bridge = (
        relationship in {"same", "strong_neighbor", "strong_secondary"}
        and anchor_archetype == "visual_novel"
        and (candidate_archetype == "visual_novel" or "visual_novel" in candidate_secondaries)
        and bool(anchor_fingerprint["combat_presence"] & {"none"})
        and bool(candidate_fingerprint["combat_presence"] & {"none"})
        and bool(set(shared_session_shape) & {"campaign"})
        and bool(
            shared_interface_control
            or shared_narrative_topic
            or shared_mode_profile
            or shared_entity_interaction
            or (
                set(anchor_fingerprint["narrative_structure"]) & {"authored_linear", "authored_branching"}
                and set(candidate_fingerprint["narrative_structure"]) & {"authored_linear", "authored_branching"}
            )
        )
    )
    kingdom_decision_identity_bridge = (
        relationship in {"same", "strong_neighbor", "strong_secondary"}
        and anchor_archetype == "kingdom_decision_sim"
        and (
            candidate_archetype == "kingdom_decision_sim"
            or "kingdom_decision_sim" in candidate_secondaries
        )
        and bool(anchor_fingerprint["combat_presence"] & {"none"})
        and bool(candidate_fingerprint["combat_presence"] & {"none"})
        and bool(set(shared_session_shape) & {"campaign"})
        and bool(
            shared_interface_control
            or shared_entity_interaction
            or shared_narrative_topic
            or shared_progression_model
            or shared_rules_goals
            or shared_mechanics_structure
            or (
                set(anchor_fingerprint["narrative_structure"]) & {"authored_branching"}
                and set(candidate_fingerprint["narrative_structure"]) & {"authored_branching"}
            )
        )
    )
    co_op_horror_identity_bridge = (
        relationship in {"same", "strong_neighbor", "strong_secondary"}
        and anchor_archetype == "co_op_horror"
        and (candidate_archetype == "co_op_horror" or "co_op_horror" in candidate_secondaries)
        and bool(set(shared_mode_profile) & {"drop_in_coop", "party_coop"})
        and bool(set(shared_setting) & {"horror"})
        and bool(
            set(shared_combat_style) & {"shooter"}
            or set(shared_combat_structure) & {"crowd_control", "encounter_driven"}
            or (
                anchor_fingerprint["combat_style"] & {"shooter"}
                and candidate_fingerprint["combat_style"] & {"shooter"}
            )
        )
        and bool(
            set(shared_session_shape) & {"campaign", "mission_session", "roguelite_run"}
            or set(shared_combat_structure) & {"crowd_control", "encounter_driven"}
        )
    )
    action_horror_identity_bridge = (
        anchor_archetype == "action_horror"
        and (
            candidate_archetype in {"action_horror", "survival_horror", "psychological_horror"}
            or bool(candidate_secondaries & {"action_horror", "survival_horror", "psychological_horror"})
        )
        and bool(set(shared_setting) & {"horror"})
        and bool(
            set(shared_tone) & {"bleak", "grotesque"}
            or shared_narrative_topic
            or shared_mode_profile
        )
        and bool(
            set(shared_perspective) & {"third_person", "first_person"}
            or shared_combat_style
            or (
                set(candidate_fingerprint["perspective"]) & {"third_person", "first_person"}
                and set(anchor_fingerprint["perspective"]) & {"third_person", "first_person"}
            )
        )
    )
    survival_horror_identity_bridge = (
        anchor_archetype == "survival_horror"
        and (
            candidate_archetype in {"survival_horror", "psychological_horror", "action_horror"}
            or bool(candidate_secondaries & {"survival_horror", "psychological_horror", "action_horror"})
        )
        and bool(set(shared_setting) & {"horror"})
        and bool(shared_mode_profile or shared_session_shape)
        and bool(
            shared_combat_style
            or shared_rules_goals
            or shared_narrative_topic
            or shared_challenge_model
            or bool(set(shared_tone) & {"bleak", "grotesque"})
        )
    )
    thematic_action_bridge = bool(
        shared_setting
        and shared_perspective
        and (shared_rules_goals or shared_narrative_topic)
    )
    cinematic_fantasy_bridge = (
        {anchor_archetype, candidate_archetype} == {"open_world_fantasy_action_rpg", "cinematic_action_adventure"}
        and bool(shared_setting)
        and bool(shared_perspective)
        and bool(shared_combat_style or shared_combat_structure or shared_progression_model)
    )
    same_soulslike_lane = (
        anchor_archetype == "soulslike_action_rpg"
        and (candidate_archetype == "soulslike_action_rpg" or "soulslike_action_rpg" in candidate_secondaries)
    )
    soulslike_conflicting_perspectives = {"isometric", "tactical_overhead", "top_down", "side_scrolling", "first_person"}
    anchor_prefers_third_person_soulslike = bool(
        anchor_fingerprint["perspective"] & {"third_person"}
        or anchor_fingerprint["visual_presentation"] & {"third_person_3d"}
    )
    candidate_supports_third_person_soulslike = bool(
        candidate_fingerprint["perspective"] & {"third_person"}
        or candidate_fingerprint["visual_presentation"] & {"third_person_3d"}
    )
    candidate_conflicting_soulslike_view = bool(
        candidate_fingerprint["perspective"] & soulslike_conflicting_perspectives
        or candidate_fingerprint["visual_presentation"] & {"side_scrolling_2d"}
    )
    open_world_fantasy_identity_bridge = False
    if anchor_archetype == "open_world_fantasy_action_rpg":
        if candidate_archetype == "open_world_fantasy_action_rpg":
            open_world_fantasy_identity_bridge = (
                bool(shared_setting)
                and bool(shared_perspective)
                and bool(
                    shared_traversal_verbs
                    or shared_rules_goals
                    or shared_entity_interaction
                    or shared_progression_model
                    or traversal_identity_bridge
                )
                and candidate_open_world_fantasy_identity_hits >= (1 if shared_traversal_verbs else 2)
                and not (
                    candidate_open_world_fantasy_sandbox_signals
                    and not anchor_open_world_fantasy_sandbox_signals
                    and candidate_open_world_fantasy_frontier_hits < 1
                )
            )
        elif candidate_archetype == "western_narrative_rpg":
            open_world_fantasy_identity_bridge = (
                bool(shared_setting)
                and bool(shared_perspective)
                and candidate_western_identity_hits >= 2
                and bool(
                    set(shared_rules_goals) & {"complete_quests"}
                    or set(shared_entity_interaction) & {"dialogue_choice"}
                    or set(shared_progression_model) & {"quest_driven"}
                )
            )
        elif candidate_archetype == "soulslike_action_rpg":
            open_world_fantasy_identity_bridge = (
                bool(shared_perspective)
                and bool(
                    set(shared_setting) & {"high_fantasy", "dark_fantasy"}
                    or set(shared_challenge_model) & {"soulslike"}
                    or set(shared_rules_goals) & {"defeat_bosses"}
                )
                and candidate_soulslike_core_hits >= 1
                and candidate_soulslike_identity_hits >= 3
                and bool(
                    set(shared_rules_goals) & {"defeat_bosses"}
                    or set(shared_combat_structure) & {"boss_centric"}
                    or set(shared_challenge_model) & {"soulslike"}
                )
            )
        elif candidate_archetype == "mmo_action_rpg":
            open_world_fantasy_identity_bridge = (
                bool(shared_world_topology)
                and bool(shared_setting)
                and bool(shared_perspective)
                and candidate_mmo_identity_hits >= 2
                and bool(shared_traversal_verbs or shared_progression_model or shared_entity_interaction or shared_combat_style)
            )
        elif candidate_archetype == "cinematic_action_adventure":
            open_world_fantasy_identity_bridge = (
                bool(shared_setting)
                and bool(shared_perspective)
                and candidate_cinematic_identity_hits >= 2
                and bool(
                    set(shared_rules_goals) & {"defeat_bosses", "complete_quests"}
                    or shared_progression_model
                    or shared_combat_style
                    or shared_combat_structure
                )
            )

    if (
        not shared_world_topology
        and not studio_bridge
        and not derived_identity_bridge
        and not low_combat_identity_bridge
        and not loot_action_rpg_identity_bridge
        and not farming_sim_identity_bridge
        and not creative_sandbox_identity_bridge
        and not jrpg_story_identity_bridge
        and not metroidvania_identity_bridge
        and not precision_platformer_identity_bridge
        and not hidden_object_identity_bridge
        and not collectathon_identity_bridge
        and not visual_novel_identity_bridge
        and not kingdom_decision_identity_bridge
        and not co_op_horror_identity_bridge
        and not action_horror_identity_bridge
        and not survival_horror_identity_bridge
        and not thematic_action_bridge
        and not cinematic_fantasy_bridge
        and not same_soulslike_lane
        and not open_world_fantasy_identity_bridge
    ):
        return None
    if not (shared_combat_style or shared_combat_structure or shared_mechanics_structure):
        if not (
            open_world_fantasy_identity_bridge
            or low_combat_identity_bridge
            or loot_action_rpg_identity_bridge
            or farming_sim_identity_bridge
            or creative_sandbox_identity_bridge
            or jrpg_story_identity_bridge
            or metroidvania_identity_bridge
            or precision_platformer_identity_bridge
            or hidden_object_identity_bridge
            or collectathon_identity_bridge
            or visual_novel_identity_bridge
            or kingdom_decision_identity_bridge
            or co_op_horror_identity_bridge
            or action_horror_identity_bridge
            or survival_horror_identity_bridge
        ):
            return None
    if not (
        shared_session_shape
        or shared_mode_profile
        or shared_progression_model
        or shared_traversal_verbs
        or shared_setting
        or shared_mechanics_structure
        or shared_keyword_layer
    ):
        if not (
            open_world_fantasy_identity_bridge
            or low_combat_identity_bridge
            or loot_action_rpg_identity_bridge
            or farming_sim_identity_bridge
            or creative_sandbox_identity_bridge
            or metroidvania_identity_bridge
            or precision_platformer_identity_bridge
            or hidden_object_identity_bridge
            or collectathon_identity_bridge
            or visual_novel_identity_bridge
            or kingdom_decision_identity_bridge
            or co_op_horror_identity_bridge
            or action_horror_identity_bridge
            or survival_horror_identity_bridge
        ):
            return None
    if (
        anchor_archetype == "open_world_fantasy_action_rpg"
        and relationship == "same"
        and not (
            shared_traversal_verbs
            or traversal_identity_bridge
            or shared_rules_goals
            or shared_entity_interaction
            or shared_narrative_topic
        )
    ):
        return None
    if (
        anchor_archetype == "open_world_fantasy_action_rpg"
        and candidate_archetype == "open_world_action_adventure"
        and not (
            shared_setting
            or shared_traversal_verbs
            or traversal_identity_bridge
            or (set(shared_rules_goals) & {"defeat_bosses"})
            or shared_entity_interaction
            or shared_narrative_topic
        )
    ):
        return None
    if (
        anchor_archetype == "open_world_fantasy_action_rpg"
        and candidate_archetype in {"beat_em_up", "3d_collectathon"}
    ):
        return None

    relation_weights = {
        _canonical_token(key): int(value)
        for key, value in (graph.get("relation_weights") or {}).items()
        if _canonical_token(key)
    }
    anchor_secondaries = {
        _canonical_token(value)
        for value in getattr(anchor, "taxonomy_v2_secondary_archetypes", None) or []
        if _canonical_token(value)
    }
    score = relation_weights.get(relationship, 120)
    score += len(shared_world_topology) * 45
    score += _weighted_token_score(shared_session_shape, {}, default=12)
    if shared_combat_style:
        score += 35
        score += max(0, len(shared_combat_style) - 1) * 12
    score += len(shared_combat_structure) * 24
    score += _weighted_token_score(shared_mode_profile, {}, default=12)
    score += _weighted_token_score(shared_progression_model, get_taxonomy_v2_match_weights("progression_model"), default=10)
    score += _weighted_token_score(shared_traversal_verbs, get_taxonomy_v2_match_weights("traversal_verbs"), default=12)
    score += _weighted_token_score(shared_setting, get_taxonomy_v2_match_weights("setting"), default=12)
    score += _weighted_token_score(shared_tone, get_taxonomy_v2_match_weights("tone"), default=6)
    if studio_bridge:
        score += 100
    if adjacent_persistent_world_bridge:
        score += 60
    if traversal_identity_bridge:
        score += 60
    if loot_action_rpg_identity_bridge:
        score += 72
    if farming_sim_identity_bridge:
        score += 64
    if creative_sandbox_identity_bridge:
        score += 70
    if jrpg_story_identity_bridge:
        score += 62
    if metroidvania_identity_bridge:
        score += 66
    if precision_platformer_identity_bridge:
        score += 62
    if hidden_object_identity_bridge:
        score += 60
    if collectathon_identity_bridge:
        score += 64
    if visual_novel_identity_bridge:
        score += 58
    if kingdom_decision_identity_bridge:
        score += 62
    if co_op_horror_identity_bridge:
        score += 70
    if action_horror_identity_bridge:
        score += 66
    if survival_horror_identity_bridge:
        score += 68
    if shared_traversal_verbs and shared_setting:
        score += 18
    derived_similarity_score = 0
    derived_similarity_score += _weighted_token_score(shared_keyword_layer, get_taxonomy_v2_match_weights("keyword_layer"), default=8)
    derived_similarity_score += _weighted_token_score(shared_mechanics_structure, get_taxonomy_v2_match_weights("mechanics_structure"), default=10)
    derived_similarity_score += _weighted_token_score(shared_rules_goals, get_taxonomy_v2_match_weights("rules_goals"), default=8)
    derived_similarity_score += _weighted_token_score(shared_entity_interaction, get_taxonomy_v2_match_weights("entity_interaction"), default=8)
    derived_similarity_score += _weighted_token_score(shared_narrative_topic, get_taxonomy_v2_match_weights("narrative_topic"), default=8)
    derived_similarity_score += _weighted_token_score(shared_visual_presentation, get_taxonomy_v2_match_weights("visual_presentation"), default=6)
    derived_similarity_score += _weighted_token_score(shared_art_style, get_taxonomy_v2_match_weights("art_style"), default=6)
    derived_similarity_score += _weighted_token_score(shared_pacing, get_taxonomy_v2_match_weights("pacing"), default=6)
    derived_similarity_score += _weighted_token_score(shared_interface_control, get_taxonomy_v2_match_weights("interface_control"), default=8)
    derived_similarity_score += _weighted_token_score(shared_sports_theme, get_taxonomy_v2_match_weights("sports_theme"), default=10)
    derived_similarity_score += _weighted_token_score(shared_vehicular_theme, get_taxonomy_v2_match_weights("vehicular_theme"), default=10)
    score += derived_similarity_score
    score += len(shared_perspective) * 12
    score += len(shared_studios) * 8
    score += _weighted_token_score(shared_challenge_model, get_taxonomy_v2_match_weights("challenge_model"), default=12)
    if candidate_archetype in anchor_secondaries and relationship.startswith(("bridge", "adjacent", "strong")):
        score += 36

    anchor_art_style = anchor_fingerprint["art_style"]
    candidate_art_style = candidate_fingerprint["art_style"]
    if anchor_archetype == "open_world_fantasy_action_rpg":
        conflicting_perspectives = {"isometric", "tactical_overhead", "top_down", "side_scrolling"}
        if candidate_fingerprint["perspective"] & conflicting_perspectives:
            return None
        if candidate_archetype == "open_world_fantasy_action_rpg" and candidate_open_world_fantasy_identity_hits < (1 if shared_traversal_verbs else 2):
            return None
        if (
            candidate_archetype == "open_world_fantasy_action_rpg"
            and candidate_open_world_fantasy_sandbox_signals
            and not anchor_open_world_fantasy_sandbox_signals
            and candidate_open_world_fantasy_frontier_hits < 1
        ):
            return None
        if candidate_archetype == "western_narrative_rpg" and candidate_western_identity_hits < 2:
            return None
        if candidate_archetype == "soulslike_action_rpg" and (
            candidate_soulslike_core_hits < 1 or candidate_soulslike_identity_hits < 3
        ):
            return None
        if candidate_archetype == "mmo_action_rpg" and candidate_mmo_identity_hits < 2:
            return None
        if candidate_archetype == "cinematic_action_adventure" and candidate_cinematic_identity_hits < 2:
            return None
        if "historical_first" in candidate_hard_exclusions and not shared_setting:
            return None
        if candidate_archetype == "open_world_action_adventure" and (not shared_setting or not shared_perspective):
            return None
        if "party_management" not in anchor_fingerprint["combat_structure"] and "party_management" in candidate_fingerprint["combat_structure"]:
            score -= 28
        if "anime" not in anchor_art_style and "anime" in candidate_art_style and "anime" not in shared_art_style:
            score -= 18
        if (
            "soulslike" in candidate_fingerprint["challenge_model"]
            and not traversal_identity_bridge
            and "quest_driven" not in shared_progression_model
        ):
            score -= 55
        if not (
            shared_traversal_verbs
            or traversal_identity_bridge
            or shared_rules_goals
            or shared_entity_interaction
            or shared_narrative_topic
        ):
            score -= 80
        if not shared_setting:
            score -= 72
        if not shared_perspective and candidate_archetype != "mmo_action_rpg":
            score -= 42
        shared_traversal_verbs_set = set(shared_traversal_verbs)
        shared_rules_goals_set = set(shared_rules_goals)
        shared_entity_interaction_set = set(shared_entity_interaction)
        if (
            "puzzle_gating" in candidate_challenge
            and "puzzle_gating" not in anchor_challenge
            and "dominant" not in candidate_fingerprint["combat_presence"]
            and not (shared_rules_goals_set & {"complete_quests", "defeat_bosses"})
        ):
            return None
        if shared_rules_goals_set & {"complete_quests", "defeat_bosses"}:
            score += 14
        if shared_entity_interaction_set & {"dialogue_choice", "construction_placement"}:
            score += 12
        if shared_traversal_verbs_set & {"horseback", "climbing"}:
            score += 12
        if candidate_archetype == "western_narrative_rpg":
            if shared_rules_goals_set & {"complete_quests"}:
                score += 34
            if shared_entity_interaction_set & {"dialogue_choice"}:
                score += 22
        if candidate_archetype == "soulslike_action_rpg":
            if "soulslike" in shared_challenge_model:
                score += 28
            if "boss_centric" in shared_combat_structure:
                score += 24
        if candidate_archetype == "mmo_action_rpg":
            if adjacent_persistent_world_bridge:
                score += 24
            if shared_traversal_verbs:
                score += 14
        if candidate_archetype == "cinematic_action_adventure":
            if cinematic_fantasy_bridge:
                score += 54
            if shared_setting:
                score += 18
            if shared_perspective:
                score += 12
        if (
            "platforming" in candidate_fingerprint["traversal_verbs"]
            and "platforming" not in shared_traversal_verbs
            and "quest_driven" not in shared_progression_model
            and "complete_quests" not in shared_rules_goals_set
        ):
            return None
        if "comedic" in candidate_fingerprint["tone"] and "comedic" not in anchor_fingerprint["tone"]:
            score -= 32

    if anchor_archetype == "soulslike_action_rpg":
        shared_rules_goals_set = set(shared_rules_goals)
        if candidate_conflicting_soulslike_view:
            return None
        if same_soulslike_lane and anchor_prefers_third_person_soulslike and not candidate_supports_third_person_soulslike:
            return None
        if same_soulslike_lane:
            score += 46
        if shared_perspective:
            score += 28
        elif same_soulslike_lane and anchor_prefers_third_person_soulslike:
            score -= 120
        if "soulslike" in shared_challenge_model:
            score += 96
        if "boss_centric" in shared_combat_structure:
            score += 52
        if shared_rules_goals_set & {"defeat_bosses"}:
            score += 24
        if shared_studios:
            score += 90
        if not same_soulslike_lane:
            score -= 60
        if "soulslike" not in shared_challenge_model and "boss_centric" not in shared_combat_structure:
            score -= 96
        if "dark_fantasy" not in candidate_fingerprint["setting"] and "dark_fantasy" in anchor_fingerprint["setting"]:
            score -= 40
        if "comedic" in candidate_fingerprint["tone"]:
            return None

    if anchor_archetype == "jrpg_story_rpg":
        anchor_requires_party_rpg_identity = bool(
            anchor_fingerprint["combat_structure"] & {"party_management"}
            or anchor_fingerprint["combat_tempo"] & {"tactical"}
        )
        candidate_party_rpg_identity_hits = sum(
            1
            for present in (
                bool(candidate_fingerprint["combat_structure"] & {"party_management"}),
                bool(candidate_fingerprint["combat_tempo"] & {"tactical"}),
                "none" not in candidate_fingerprint["combat_presence"],
            )
            if present
        )
        if anchor_requires_party_rpg_identity and "none" in candidate_fingerprint["combat_presence"]:
            return None
        if (
            candidate_archetype == anchor_archetype
            and anchor_requires_party_rpg_identity
            and candidate_party_rpg_identity_hits < 2
        ):
            score -= 90

    if anchor_archetype == "cinematic_action_adventure":
        if candidate_archetype == "open_world_fantasy_action_rpg" and cinematic_fantasy_bridge:
            score += 54
            if shared_setting:
                score += 18
            if shared_perspective:
                score += 12

    anchor_modes = anchor_fingerprint["mode_profile"]
    candidate_modes = candidate_fingerprint["mode_profile"]
    if ("mmo" in anchor_modes) ^ ("mmo" in candidate_modes):
        score -= 18
    if not shared_tone:
        if "cozy" in candidate_fingerprint["tone"] and "cozy" not in anchor_fingerprint["tone"]:
            score -= 10
        if "comedic" in candidate_fingerprint["tone"] and "comedic" not in anchor_fingerprint["tone"]:
            score -= 12
    if "puzzle_gating" in candidate_challenge and "puzzle_gating" not in anchor_challenge:
        score -= 18
    if "none" in candidate_fingerprint["combat_presence"] and "none" not in anchor_fingerprint["combat_presence"]:
        score -= 14

    reasons: list[str] = []
    if relationship == "same":
        reasons.append(f"Same archetype: {display_taxonomy_v2_token(anchor_archetype)}")
    elif relationship.startswith("strong"):
        reasons.append(f"Neighbor archetype: {display_taxonomy_v2_token(candidate_archetype)}")
    elif relationship.startswith("bridge"):
        reasons.append(f"Bridge archetype: {display_taxonomy_v2_token(candidate_archetype)}")
    else:
        reasons.append(f"Adjacent archetype: {display_taxonomy_v2_token(candidate_archetype)}")

    reasons.append(_format_v2_match_reason("Shared world", shared_world_topology))
    if shared_traversal_verbs:
        reasons.append(_format_v2_match_reason("Shared traversal", shared_traversal_verbs))
    elif shared_progression_model:
        reasons.append(_format_v2_match_reason("Shared progression", shared_progression_model))
    elif shared_session_shape:
        reasons.append(_format_v2_match_reason("Shared session flow", shared_session_shape))
    elif shared_setting:
        reasons.append(_format_v2_match_reason("Shared setting", shared_setting))
    elif shared_mechanics_structure:
        reasons.append(_format_v2_match_reason("Shared mechanics", shared_mechanics_structure))
    elif shared_keyword_layer:
        reasons.append(_format_v2_match_reason("Shared keywords", shared_keyword_layer))
    if len(reasons) < 3 and shared_combat_style:
        reasons.append(_format_v2_match_reason("Shared combat", shared_combat_style))
    elif len(reasons) < 3 and shared_combat_structure:
        reasons.append(_format_v2_match_reason("Shared combat structure", shared_combat_structure))
    if len(reasons) < 3 and shared_rules_goals:
        reasons.append(_format_v2_match_reason("Shared goals", shared_rules_goals))
    elif len(reasons) < 3 and shared_mode_profile:
        reasons.append(_format_v2_match_reason("Shared modes", shared_mode_profile))
    elif len(reasons) < 3 and shared_narrative_topic:
        reasons.append(_format_v2_match_reason("Shared narrative", shared_narrative_topic))
    elif len(reasons) < 3 and shared_interface_control:
        reasons.append(_format_v2_match_reason("Shared interface", shared_interface_control))
    elif len(reasons) < 3 and shared_art_style:
        reasons.append(_format_v2_match_reason("Shared style", shared_art_style))
    if len(reasons) < 3 and shared_studios:
        reasons.append("Shared studio lineage")

    confidence = "high" if score >= 280 else "medium" if score >= 200 else "low"
    return SimilarityBreakdownV2(
        score=score,
        confidence=confidence,
        match_reasons=reasons[:3],
        relationship=relationship,
        derived_similarity_score=derived_similarity_score,
        shared_world_topology=shared_world_topology,
        shared_session_shape=shared_session_shape,
        shared_combat_style=shared_combat_style,
        shared_combat_structure=shared_combat_structure,
        shared_mode_profile=shared_mode_profile,
        shared_progression_model=shared_progression_model,
        shared_traversal_verbs=shared_traversal_verbs,
        shared_setting=shared_setting,
        shared_tone=shared_tone,
        shared_keyword_layer=shared_keyword_layer,
        shared_mechanics_structure=shared_mechanics_structure,
        shared_rules_goals=shared_rules_goals,
        shared_entity_interaction=shared_entity_interaction,
        shared_narrative_topic=shared_narrative_topic,
        shared_visual_presentation=shared_visual_presentation,
        shared_art_style=shared_art_style,
        shared_pacing=shared_pacing,
        shared_interface_control=shared_interface_control,
        shared_sports_theme=shared_sports_theme,
        shared_vehicular_theme=shared_vehicular_theme,
        shared_challenge_model=shared_challenge_model,
        shared_studios=shared_studios,
    )


def _summarize_source_label_classifications(
    rows: Iterable[GameSourceTaxonomyLabel],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        _resolved, classification = classify_taxonomy_v2_source_label(
            source=row.source,
            facet=row.facet,
            raw_label=row.raw_label or row.normalized_label or "",
            normalized_label=row.normalized_label,
        )
        counts[classification] += 1
    return dict(counts)


def _derive_hidden_audit_state(
    *,
    evidence: list[TaxonomyV2EvidenceRecord],
    candidates: list[ArchetypeCandidate],
    near_misses: list[TaxonomyV2NearMiss],
    source_label_summary: dict[str, int],
) -> str:
    provider_gap = int(source_label_summary.get("provider_gap", 0))
    mapping_gap = int(source_label_summary.get("unmapped", 0))
    if not evidence:
        if provider_gap:
            return "provider_gap"
        if mapping_gap:
            return "mapping_gap"
        return "insufficient_signal"
    if candidates:
        return "computed"
    if provider_gap:
        return "provider_gap"
    if mapping_gap:
        return "mapping_gap"
    if near_misses:
        top = near_misses[0]
        if top.required_total and top.required_hits >= max(2, top.required_total - 1):
            return "curation_required"
        return "conflict_ambiguous"
    return "insufficient_signal"


def build_game_taxonomy_v2(
    game: Game,
    source_labels: Iterable[GameSourceTaxonomyLabel],
) -> TaxonomyV2Result:
    text_corpus = getattr(game, "taxonomy_v2_text_corpus", None)
    text_sources = list(getattr(game, "taxonomy_v2_text_sources", None) or [])
    if not text_corpus:
        text_corpus, text_sources = build_taxonomy_v2_text_corpus(game)

    source_label_rows = list(source_labels)
    source_label_summary = _summarize_source_label_classifications(source_label_rows)

    evidence = extract_v2_evidence_from_source_labels(source_label_rows)
    evidence.extend(extract_v2_evidence_from_description(text_corpus))

    preliminary_fingerprint, _, _, _ = _aggregate_evidence(evidence)
    evidence.extend(infer_derived_v2_evidence(preliminary_fingerprint))

    fingerprint, confidence_by_field_value, source_count_by_field_value, provenance_by_field_value = _aggregate_evidence(evidence)
    fingerprint, override_evidence, curated = _apply_override_to_fingerprint(game, fingerprint)
    if override_evidence:
        evidence.extend(override_evidence)
        fingerprint, confidence_by_field_value, source_count_by_field_value, provenance_by_field_value = _aggregate_evidence(evidence)

    candidates = assign_taxonomy_v2_archetypes(fingerprint, confidence_by_field_value)
    candidates = _prefer_primary_archetype_candidate(candidates, fingerprint)
    if candidates and candidates[0].archetype == "open_world_action_adventure":
        fantasy_index = next(
            (index for index, candidate in enumerate(candidates) if candidate.archetype == "open_world_fantasy_action_rpg"),
            None,
        )
        if fantasy_index is not None:
            fingerprint_sets = build_taxonomy_v2_fingerprint_sets_from_mapping(fingerprint)
            if (
                "open_world" in fingerprint_sets["world_topology"]
                and bool(fingerprint_sets["setting"] & {"high_fantasy", "dark_fantasy", "mythic"})
                and (
                    "third_person" in fingerprint_sets["perspective"]
                    or bool(fingerprint_sets["traversal_verbs"] & {"horseback", "climbing", "gliding"})
                )
                and "dominant" in fingerprint_sets["combat_presence"]
                and (
                    "quest_driven" in fingerprint_sets["progression_model"]
                    or "complete_quests" in fingerprint_sets["rules_goals"]
                    or bool(fingerprint_sets["traversal_verbs"] & {"horseback", "climbing", "gliding"})
                )
                and "historical" not in fingerprint_sets["setting"]
            ):
                fantasy_candidate = candidates[fantasy_index]
                candidates = [fantasy_candidate] + [
                    candidate for index, candidate in enumerate(candidates) if index != fantasy_index
                ]
    override = get_taxonomy_v2_override(game)

    primary_family = None
    primary_archetype = None
    secondary_archetypes: list[str] = []
    confidence: float | None = None

    if candidates:
        primary_family = candidates[0].family or None
        primary_archetype = candidates[0].archetype
        confidence = candidates[0].confidence
        cutoff = max(60, int(candidates[0].score * 0.7))
        secondary_archetypes = [
            candidate.archetype
            for candidate in candidates[1:]
            if candidate.score >= cutoff
        ][:3]

    if override["primary_family"]:
        primary_family = override["primary_family"]
        curated = True
    if override["primary_archetype"]:
        primary_archetype = override["primary_archetype"]
        curated = True
    if override["secondary_archetypes"]:
        secondary_archetypes = override["secondary_archetypes"]
        curated = True

    near_misses = rank_taxonomy_v2_near_misses(
        fingerprint,
        hard_exclusions=fingerprint.get("hard_exclusions", []),
        limit=3,
    )
    audit_state = _derive_hidden_audit_state(
        evidence=evidence,
        candidates=candidates,
        near_misses=near_misses,
        source_label_summary=source_label_summary,
    )

    if primary_archetype:
        status = TAXONOMY_V2_STATUS_CURATED if curated else TAXONOMY_V2_STATUS_COMPUTED
    else:
        status = TAXONOMY_V2_STATUS_HIDDEN

    debug_payload = {
        "candidate_archetypes": [
            {
                "archetype": candidate.archetype,
                "family": candidate.family,
                "score": candidate.score,
                "required_hits": candidate.required_hits,
                "required_total": candidate.required_total,
                "preferred_hits": candidate.preferred_hits,
                "preferred_total": candidate.preferred_total,
                "confidence": round(candidate.confidence, 2),
            }
            for candidate in candidates[:5]
        ],
        "confidence_by_field_value": {
            field: {value: round(score, 2) for value, score in values.items()}
            for field, values in confidence_by_field_value.items()
            if values
        },
        "source_count_by_field_value": {
            field: values
            for field, values in source_count_by_field_value.items()
            if values
        },
        "provenance_by_field_value": {
            field: {value: sorted(values) for value, values in field_values.items()}
            for field, field_values in provenance_by_field_value.items()
            if field_values
        },
        "evidence_count": len(evidence),
        "text_sources": text_sources,
        "text_length": len(text_corpus or ""),
        "signal_tiers": {
            field: {
                value: classify_taxonomy_v2_signal_tier(field, value)
                for value in values.keys()
            }
            for field, values in confidence_by_field_value.items()
            if values
        },
        "audit_state": audit_state,
        "source_label_summary": source_label_summary,
        "near_misses": [
            {
                "archetype": near_miss.archetype,
                "family": near_miss.family,
                "required_hits": near_miss.required_hits,
                "required_total": near_miss.required_total,
                "missing_required_axes": list(near_miss.missing_required_axes),
            }
            for near_miss in near_misses
        ],
        "matrix_versions": {
            "source_label_matrix": load_source_label_matrix().get("version"),
            "phrase_matrix": load_phrase_matrix().get("version"),
            "noise_matrix": load_noise_matrix().get("version"),
            "facet_matrix": load_facet_matrix().get("version"),
            "connection_matrix": load_connection_matrix().get("version"),
            "opencritic_theme_catalog": load_opencritic_theme_catalog().get("version"),
        },
    }
    return TaxonomyV2Result(
        version=TAXONOMY_V2_VERSION,
        status=status,
        primary_family=primary_family,
        primary_archetype=primary_archetype,
        secondary_archetypes=secondary_archetypes,
        hard_exclusions=sorted(set(fingerprint.get("hard_exclusions", []))),
        soft_penalties=sorted(set(fingerprint.get("soft_penalties", []))),
        confidence=confidence,
        fingerprint={field: sorted(set(fingerprint.get(field, []))) for field in FINGERPRINT_AXES},
        curated=curated,
        evidence=evidence,
        debug_payload=debug_payload,
    )


async def compute_game_taxonomy_v2(db: AsyncSession, game: Game) -> TaxonomyV2Result:
    flush = getattr(db, "flush", None)
    if flush is not None:
        await flush()
    refresh_game_taxonomy_v2_text(game)
    result = await db.execute(
        select(GameSourceTaxonomyLabel).where(GameSourceTaxonomyLabel.game_id == game.id)
    )
    rows = result.scalars().all()
    result = build_game_taxonomy_v2(game, rows)
    inherited_result = await _maybe_inherit_taxonomy_v2_from_edition_parent(db, game, result)
    return inherited_result or result


async def _maybe_inherit_taxonomy_v2_from_edition_parent(
    db: AsyncSession,
    game: Game,
    result: TaxonomyV2Result,
) -> TaxonomyV2Result | None:
    if result.status in TAXONOMY_V2_READY_STATUSES:
        return None

    parent_keys = _title_parent_edition_keys(getattr(game, "title", None))
    if not parent_keys:
        return None

    parent_rows = (
        await db.execute(
            select(Game)
            .where(
                Game.id != game.id,
                func.lower(Game.title).in_(parent_keys),
            )
            .order_by(Game.release_date.desc().nulls_last(), Game.id.desc())
        )
    ).scalars().all()
    if not parent_rows:
        return None

    for parent in parent_rows:
        parent_result: TaxonomyV2Result | None = None
        if getattr(parent, "taxonomy_v2_status", None) in TAXONOMY_V2_READY_STATUSES:
            parent_result = TaxonomyV2Result(
                version=str(getattr(parent, "taxonomy_v2_version", None) or TAXONOMY_V2_VERSION),
                status=str(getattr(parent, "taxonomy_v2_status", None)),
                primary_family=getattr(parent, "taxonomy_v2_primary_family", None),
                primary_archetype=getattr(parent, "taxonomy_v2_primary_archetype", None),
                secondary_archetypes=list(getattr(parent, "taxonomy_v2_secondary_archetypes", None) or []),
                hard_exclusions=list(getattr(parent, "taxonomy_v2_hard_exclusions", None) or []),
                soft_penalties=list(getattr(parent, "taxonomy_v2_soft_penalties", None) or []),
                confidence=float(getattr(parent, "taxonomy_v2_confidence", None) or 0),
                fingerprint=dict(getattr(parent, "taxonomy_v2_fingerprint", None) or {}),
                curated=bool(getattr(parent, "taxonomy_v2_curated", False)),
                evidence=[],
                debug_payload=dict(getattr(parent, "taxonomy_v2_debug_payload", None) or {}),
            )
        else:
            parent_result = await compute_game_taxonomy_v2(db, parent)
            if parent_result.status in TAXONOMY_V2_READY_STATUSES:
                await store_game_taxonomy_v2(db, parent, parent_result)

        if (
            parent_result is None
            or parent_result.status not in TAXONOMY_V2_READY_STATUSES
            or not parent_result.primary_family
            or not parent_result.primary_archetype
            or not parent_result.fingerprint
        ):
            continue

        parent_confidence = parent_result.confidence or 0.0
        inherited_confidence = max(0.85, min(0.93, parent_confidence - 0.01 if parent_confidence else 0.88))
        return TaxonomyV2Result(
            version=TAXONOMY_V2_VERSION,
            status=TAXONOMY_V2_STATUS_COMPUTED,
            primary_family=parent_result.primary_family,
            primary_archetype=parent_result.primary_archetype,
            secondary_archetypes=list(parent_result.secondary_archetypes),
            hard_exclusions=list(parent_result.hard_exclusions),
            soft_penalties=list(parent_result.soft_penalties),
            confidence=inherited_confidence,
            fingerprint={key: list(values) for key, values in parent_result.fingerprint.items()},
            curated=False,
            evidence=[
                TaxonomyV2EvidenceRecord(
                    field="primary_archetype",
                    value=parent_result.primary_archetype,
                    source="title_variant_inheritance",
                    source_field="parent_title",
                    confidence=inherited_confidence,
                    evidence_text=getattr(parent, "title", None),
                )
            ],
            debug_payload={
                **(result.debug_payload or {}),
                "audit_state": "edition_parent_inherited",
                "inherited_from_parent_game": {
                    "id": getattr(parent, "id", None),
                    "public_id": getattr(parent, "public_id", None),
                    "title": getattr(parent, "title", None),
                    "taxonomy_v2_status": parent_result.status,
                    "primary_archetype": parent_result.primary_archetype,
                    "confidence": parent_result.confidence,
                },
            },
        )

    return None


def apply_taxonomy_v2_result_to_game(game: Game, result: TaxonomyV2Result) -> None:
    game.taxonomy_v2_version = result.version
    game.taxonomy_v2_status = result.status
    game.taxonomy_v2_primary_family = result.primary_family
    game.taxonomy_v2_primary_archetype = result.primary_archetype
    game.taxonomy_v2_secondary_archetypes = list(result.secondary_archetypes)
    game.taxonomy_v2_hard_exclusions = list(result.hard_exclusions)
    game.taxonomy_v2_soft_penalties = list(result.soft_penalties)
    game.taxonomy_v2_confidence = _quantize_decimal(result.confidence)
    game.taxonomy_v2_fingerprint = result.fingerprint
    game.taxonomy_v2_computed_at = datetime.now(timezone.utc)
    game.taxonomy_v2_curated = result.curated
    game.taxonomy_v2_debug_payload = result.debug_payload


async def store_game_taxonomy_v2(
    db: AsyncSession,
    game: Game,
    result: TaxonomyV2Result,
) -> None:
    await db.execute(
        delete(GameTaxonomyV2Evidence).where(GameTaxonomyV2Evidence.game_id == game.id)
    )
    apply_taxonomy_v2_result_to_game(game, result)
    for record in result.evidence:
        db.add(
            GameTaxonomyV2Evidence(
                game_id=game.id,
                taxonomy_version=result.version,
                field=record.field,
                value=record.value,
                source=record.source,
                source_field=record.source_field,
                confidence=_quantize_decimal(record.confidence),
                evidence_text=record.evidence_text,
                curated=record.curated,
                weight=_quantize_decimal(record.weight) if record.weight is not None else None,
                conflict_group=record.conflict_group,
                suppressed_by_rule=record.suppressed_by_rule,
            )
        )


async def compute_and_store_game_taxonomy_v2(db: AsyncSession, game: Game) -> TaxonomyV2Result:
    result = await compute_game_taxonomy_v2(db, game)
    await store_game_taxonomy_v2(db, game, result)
    from app.services.game_similarity_v3 import mark_game_similarity_v3_dirty

    mark_game_similarity_v3_dirty(game, "taxonomy_v2")
    return result
