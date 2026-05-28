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


def test_transform_game_normalizes_protocol_relative_banner_urls():
    transformed = OpenCriticService.transform_game(
        {
            "id": 5581,
            "name": "Example Game 3",
            "bannerScreenshot": {
                "fullRes": "//c.opencritic.com/images/games/5581/banner.jpg",
            },
        }
    )

    assert (
        transformed["image_url"]
        == "https://c.opencritic.com/images/games/5581/banner.jpg"
    )


def test_transform_game_reads_current_images_payload_shape():
    transformed = OpenCriticService.transform_game(
        {
            "id": 19224,
            "name": "007 First Light",
            "images": {
                "box": {"og": "game/19224/o/icLXuJWa.jpg"},
                "banner": {"og": "game/19224/o/aTseze8n.jpg"},
            },
        }
    )

    assert transformed["image_url"] == "https://img.opencritic.com/game/19224/o/icLXuJWa.jpg"
