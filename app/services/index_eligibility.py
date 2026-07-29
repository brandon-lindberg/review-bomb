"""Canonical search-index eligibility rules for public entity pages."""

from sqlalchemy import and_, func, or_
from sqlalchemy.sql.elements import ColumnElement

from app.models.models import Game, Journalist, Outlet


MIN_GAME_CRITIC_REVIEWS = 20
MIN_JOURNALIST_REVIEWS = 10
MIN_OUTLET_REVIEWS = 10
MIN_STEAM_USER_REVIEWS = 50
MIN_METACRITIC_USER_REVIEWS = 20


def game_index_eligibility_expression() -> ColumnElement[bool]:
    """SQL expression matching :func:`game_is_index_eligible`."""
    player_score_is_qualified = or_(
        and_(
            Game.steam_user_score.isnot(None),
            Game.steam_sample_size >= MIN_STEAM_USER_REVIEWS,
        ),
        and_(
            Game.metacritic_user_score.isnot(None),
            or_(
                Game.metacritic_sample_size.is_(None),
                Game.metacritic_sample_size >= MIN_METACRITIC_USER_REVIEWS,
            ),
        ),
    )
    has_description = (
        func.length(func.trim(func.coalesce(Game.description, ""))) > 0
    )
    has_disparity = or_(
        Game.disparity_steam.isnot(None),
        Game.disparity_metacritic.isnot(None),
    )
    return and_(
        Game.critic_review_count >= MIN_GAME_CRITIC_REVIEWS,
        player_score_is_qualified,
        has_description,
        has_disparity,
    )


def journalist_index_eligibility_expression() -> ColumnElement[bool]:
    """SQL expression matching :func:`journalist_is_index_eligible`."""
    return and_(
        Journalist.review_count_scored >= MIN_JOURNALIST_REVIEWS,
        Journalist.avg_disparity.isnot(None),
    )


def outlet_index_eligibility_expression() -> ColumnElement[bool]:
    """SQL expression matching :func:`outlet_is_index_eligible`."""
    return and_(
        Outlet.review_count_scored >= MIN_OUTLET_REVIEWS,
        Outlet.avg_disparity.isnot(None),
    )


def game_is_index_eligible(game: Game) -> bool:
    has_steam_evidence = (
        game.steam_user_score is not None
        and (game.steam_sample_size or 0) >= MIN_STEAM_USER_REVIEWS
    )
    has_metacritic_evidence = (
        game.metacritic_user_score is not None
        and (
            game.metacritic_sample_size is None
            or game.metacritic_sample_size >= MIN_METACRITIC_USER_REVIEWS
        )
    )
    return (
        (game.critic_review_count or 0) >= MIN_GAME_CRITIC_REVIEWS
        and bool((game.description or "").strip())
        and (has_steam_evidence or has_metacritic_evidence)
        and (
            game.disparity_steam is not None
            or game.disparity_metacritic is not None
        )
    )


def journalist_is_index_eligible(journalist: Journalist) -> bool:
    return (
        (journalist.review_count_scored or 0) >= MIN_JOURNALIST_REVIEWS
        and journalist.avg_disparity is not None
    )


def outlet_is_index_eligible(outlet: Outlet) -> bool:
    return (
        (outlet.review_count_scored or 0) >= MIN_OUTLET_REVIEWS
        and outlet.avg_disparity is not None
    )
