"""Shared title matching for the catalog and global search."""

import re

from sqlalchemy import func, or_

from app.models.models import Game


# Edition aliases resolve to the source ID so identical official titles stay distinct.
GAME_SEARCH_ALIASES = {
    "gta6": 15398,
    "gtavi": 15398,
    "grandtheftauto6": 15398,
    "ocarinaoftimeremake": 21344,
    "ocarinatimeremake": 21344,
    "zeldaocarinaoftimeremake": 21344,
    "zeldaocarinatimeremake": 21344,
    "legendofzeldaocarinaoftimeremake": 21344,
    "legendofzeldaocarinatimeremake": 21344,
    "thelegendofzeldaocarinaoftimeremake": 21344,
    "thelegendofzeldaocarinatimeremake": 21344,
    "ocarinaoftimeswitch2": 21344,
    "ocarinaoftime2026": 21344,
    "thelegendofzeldaocarinaoftimeswitch2": 21344,
}


def compact_search_value(value: str) -> str:
    """Ignore punctuation and spacing when comparing search text."""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def text_search_clause(column, query: str, *, match_punctuation_variants: bool = True):
    normalized_query = query.strip().lower()
    escaped_query = normalized_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    literal_match = func.lower(column).like(f"%{escaped_query}%", escape="\\")
    if not match_punctuation_variants:
        return literal_match
    compact_query = compact_search_value(normalized_query)
    if not compact_query:
        return literal_match
    compact_column = func.regexp_replace(func.lower(column), "[^a-z0-9]+", "", "g")
    return or_(literal_match, compact_column.like(f"%{compact_query}%", escape="\\"))


def game_title_search_clause(query: str, *, match_punctuation_variants: bool = True):
    opencritic_id = GAME_SEARCH_ALIASES.get(compact_search_value(query))
    if opencritic_id is not None:
        return Game.opencritic_id == opencritic_id
    return text_search_clause(
        Game.title, query, match_punctuation_variants=match_punctuation_variants
    )
