import pytest

from app.services.opencritic import OpenCriticService


@pytest.mark.asyncio
async def test_get_game_reviews_paginates_until_short_page():
    service = object.__new__(OpenCriticService)
    calls = []

    async def fake_request(method, endpoint, params=None, max_retries=3):
        calls.append((method, endpoint, params))
        skip = params["skip"]
        if skip == 0:
            return [{"_id": f"a{i}"} for i in range(20)]
        if skip == 20:
            return [{"_id": f"b{i}"} for i in range(14)]
        return []

    service._request = fake_request

    reviews = await OpenCriticService.get_game_reviews(service, game_id=19824, batch_size=20)

    assert len(reviews) == 34
    assert calls == [
        ("GET", "/reviews/game/19824", {"skip": 0, "limit": 20}),
        ("GET", "/reviews/game/19824", {"skip": 20, "limit": 20}),
    ]


def test_transform_review_accepts_capitalized_scoreformat():
    transformed = OpenCriticService.transform_review(
        {
            "_id": "r1",
            "score": 8,
            "ScoreFormat": {"base": 10},
            "Authors": [{"id": 123}],
            "Outlet": {"id": 456},
        }
    )

    assert transformed["opencritic_review_id"] == "r1"
    assert transformed["opencritic_critic_id"] == 123
    assert transformed["opencritic_outlet_id"] == 456
    assert transformed["score_scale"] == "10"
    assert transformed["score_normalized"] == 80.0
