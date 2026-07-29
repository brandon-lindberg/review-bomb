from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.models import Game, Journalist, Outlet
from app.services.index_eligibility import (
    MIN_GAME_CRITIC_REVIEWS,
    MIN_JOURNALIST_REVIEWS,
    MIN_OUTLET_REVIEWS,
    game_index_eligibility_expression,
    game_is_index_eligible,
    journalist_index_eligibility_expression,
    journalist_is_index_eligible,
    outlet_index_eligibility_expression,
    outlet_is_index_eligible,
)


def make_eligible_game(**overrides) -> Game:
    values = {
        "title": "Evidence-rich game",
        "description": "A useful description.",
        "critic_review_count": MIN_GAME_CRITIC_REVIEWS,
        "steam_user_score": Decimal("82"),
        "steam_sample_size": 500,
        "metacritic_user_score": None,
        "metacritic_sample_size": None,
        "disparity_steam": Decimal("4.5"),
        "disparity_metacritic": None,
    }
    values.update(overrides)
    return Game(**values)


def test_game_index_eligibility_accepts_strong_steam_or_metacritic_evidence():
    assert game_is_index_eligible(make_eligible_game())
    assert game_is_index_eligible(
        make_eligible_game(
            steam_user_score=None,
            steam_sample_size=None,
            disparity_steam=None,
            metacritic_user_score=Decimal("78"),
            metacritic_sample_size=100,
            disparity_metacritic=Decimal("7"),
        )
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"critic_review_count": MIN_GAME_CRITIC_REVIEWS - 1},
        {"description": "  "},
        {"steam_sample_size": 49},
        {"disparity_steam": None},
    ],
)
def test_game_index_eligibility_rejects_thin_or_incomplete_pages(overrides):
    assert not game_is_index_eligible(make_eligible_game(**overrides))


def test_journalist_and_outlet_eligibility_require_review_depth_and_disparity():
    journalist = Journalist(
        name="Critic",
        review_count_scored=MIN_JOURNALIST_REVIEWS,
        avg_disparity=Decimal("3.2"),
    )
    outlet = Outlet(
        name="Publication",
        review_count_scored=MIN_OUTLET_REVIEWS,
        avg_disparity=Decimal("2.1"),
    )

    assert journalist_is_index_eligible(journalist)
    assert outlet_is_index_eligible(outlet)

    journalist.review_count_scored = MIN_JOURNALIST_REVIEWS - 1
    outlet.avg_disparity = None
    assert not journalist_is_index_eligible(journalist)
    assert not outlet_is_index_eligible(outlet)


def test_sql_eligibility_expressions_use_the_same_evidence_columns():
    game_sql = str(game_index_eligibility_expression())
    journalist_sql = str(journalist_index_eligibility_expression())
    outlet_sql = str(outlet_index_eligibility_expression())

    assert "games.critic_review_count" in game_sql
    assert "games.steam_sample_size" in game_sql
    assert "games.metacritic_sample_size" in game_sql
    assert "games.description" in game_sql
    assert "games.disparity_steam" in game_sql
    assert "journalists.review_count_scored" in journalist_sql
    assert "journalists.avg_disparity" in journalist_sql
    assert "outlets.review_count_scored" in outlet_sql
    assert "outlets.avg_disparity" in outlet_sql
