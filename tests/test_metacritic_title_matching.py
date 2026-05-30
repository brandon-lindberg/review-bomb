from datetime import datetime, timezone

import pytest

from app.services.metacritic import MetacriticService


def test_rejects_false_positive_when_distinctive_series_token_missing():
    assert not MetacriticService._titles_look_related(
        "Xenoblade Chronicles X: Definitive Edition - Nintendo Switch 2 Edition",
        "Xenoblade Chronicles: Definitive Edition",
    )


def test_accepts_expected_subtitle_format_variants():
    assert MetacriticService._titles_look_related(
        "God of War: Sons of Sparta",
        "God of War Sons of Sparta",
    )


def test_rejects_sequel_number_mismatch():
    assert not MetacriticService._titles_look_related(
        "Resident Evil 4",
        "Resident Evil 5",
    )


def test_rejects_yearly_sports_number_mismatch_with_shared_suffix():
    assert not MetacriticService._titles_look_related(
        "Fifa 21 Next Gen",
        "FIFA 26 Next Gen",
    )


def test_accepts_compact_yearly_sports_format_variant():
    assert MetacriticService._titles_look_related(
        "NBA2K 21 Next-Gen",
        "NBA 2K21 Next-Gen",
    )


def test_slug_candidates_convert_roman_numeral_to_arabic():
    candidates = MetacriticService.build_slug_candidates("Slay the Spire II")
    assert "slay-the-spire-ii" in candidates
    assert "slay-the-spire-2" in candidates


def test_slug_candidates_convert_arabic_numeral_to_roman():
    candidates = MetacriticService.build_slug_candidates("Final Fantasy VII")
    assert "final-fantasy-7" in candidates


def test_slug_candidates_do_not_mangle_single_letter_numerals():
    # "Mega Man X" must not become "mega-man-10".
    candidates = MetacriticService.build_slug_candidates("Mega Man X")
    assert candidates == ["mega-man-x"]


def test_slug_candidates_split_compound_dual_release_titles():
    candidates = MetacriticService.build_slug_candidates(
        "Pokémon HeartGold Version and Pokémon SoulSilver Version"
    )
    # Whole-title variant comes first, split parts are fallbacks.
    assert candidates[0] == "pokemon-heartgold-version-and-pokemon-soulsilver-version"
    assert "pokemon-heartgold-version" in candidates
    assert "pokemon-soulsilver-version" in candidates


def test_slug_candidates_keep_ampersand_title_intact_first():
    # "&" expands to "and" before any compound split is attempted.
    candidates = MetacriticService.build_slug_candidates("Ratchet & Clank")
    assert candidates[0] == "ratchet-and-clank"


def test_compound_split_accepts_single_half_page_title():
    assert MetacriticService._titles_look_related(
        "Pokémon HeartGold Version and Pokémon SoulSilver Version",
        "Pokémon HeartGold Version",
    )


@pytest.mark.asyncio
async def test_get_scores_passes_title_through_slug_candidate_recursion():
    class SpyMetacriticService(MetacriticService):
        def __init__(self):
            super().__init__(headless=True)
            self.calls = []

        async def get_scores(self, slug: str, max_retries: int = 3, title: str | None = None):
            self.calls.append((slug, title))
            if slug.startswith("http"):
                return {
                    "user_score": 80.0,
                    "user_score_raw": "8.0",
                    "user_sample_size": 100,
                    "metascore": 82,
                    "critic_count": 50,
                    "release_date": None,
                    "scraped_at": datetime.now(timezone.utc),
                }
            return await super().get_scores(slug, max_retries=max_retries, title=title)

    service = SpyMetacriticService()

    score_data = await service.get_scores(
        "xenoblade-chronicles-x-definitive-edition-nintendo-switch-2-edition",
        title="Xenoblade Chronicles X: Definitive Edition - Nintendo Switch 2 Edition",
    )

    assert score_data is not None
    assert len(service.calls) >= 2
    assert service.calls[0][1] == "Xenoblade Chronicles X: Definitive Edition - Nintendo Switch 2 Edition"
    # The recursive URL attempt must keep the expected title for mismatch checks.
    assert service.calls[1][1] == "Xenoblade Chronicles X: Definitive Edition - Nintendo Switch 2 Edition"
