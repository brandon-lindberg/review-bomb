from app.services.opencritic import OpenCriticService


def test_transform_game_maps_negative_placeholders_to_none():
    transformed = OpenCriticService.transform_game(
        {
            "id": 1,
            "name": "Example Game",
            "topCriticScore": -1,
            "percentRecommended": -1,
        }
    )

    assert transformed["top_critic_score"] is None
    assert transformed["percent_recommended"] is None


def test_transform_game_keeps_zero_and_positive_values():
    transformed = OpenCriticService.transform_game(
        {
            "id": 2,
            "name": "Example Game 2",
            "topCriticScore": 0,
            "percentRecommended": 72.5,
        }
    )

    assert transformed["top_critic_score"] is not None
    assert transformed["percent_recommended"] is not None
