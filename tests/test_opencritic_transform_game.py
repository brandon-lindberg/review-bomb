from app.models.models import OpenCriticMalformedGame
from app.services.opencritic import OpenCriticService
from app.services.sync_orchestrator import SyncOrchestrator


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


def test_sync_rejects_malformed_opencritic_game_named_as_url():
    payload = {
        "id": 19801,
        "name": "https://nichegamer.com/reviews/fuga-melodies-of-steel-3-review/",
    }

    assert SyncOrchestrator._opencritic_game_rejection_reason(payload) == "name_is_url"
    assert (
        SyncOrchestrator._is_valid_opencritic_game_data(payload)
        is False
    )


def test_sync_accepts_normal_opencritic_game_payload():
    assert (
        SyncOrchestrator._is_valid_opencritic_game_data(
            {
                "id": 19224,
                "name": "007 First Light",
            }
        )
        is True
    )


def test_opencritic_malformed_game_quarantine_model_has_raw_payload():
    assert "opencritic_id" in OpenCriticMalformedGame.__table__.c
    assert "reason" in OpenCriticMalformedGame.__table__.c
    assert "raw_payload" in OpenCriticMalformedGame.__table__.c
    assert "resolved_at" in OpenCriticMalformedGame.__table__.c
