from app.services.news_matcher import NewsMatcher


def test_matches_punctuation_and_possessive_variants():
    matcher = NewsMatcher([(18955, "Rayman: 30th Anniversary Edition")])

    article_title = (
        "Rayman's 30th Anniversary Edition Is Just The \"First Step\" "
        "In Franchise's Comeback, Ubisoft Says"
    )

    assert matcher.match(article_title) == 18955


def test_matches_colon_subtitle_when_words_are_separated():
    matcher = NewsMatcher([(18955, "Rayman: 30th Anniversary Edition")])

    article_title = (
        "Rayman fans rejoice! His first ever adventure is getting a fancy "
        "30th anniversary edition and it's out very soon"
    )

    assert matcher.match(article_title) == 18955


def test_second_tier_matches_rephrased_title_with_intervening_words():
    matcher = NewsMatcher([(18955, "Rayman: 30th Anniversary Edition")])

    article_title = "Rayman 30th huge anniversary edition revealed by Ubisoft"

    assert matcher.match(article_title) == 18955


def test_prefers_specific_subtitle_over_base_game():
    matcher = NewsMatcher(
        [
            (4693, "God of War"),
            (18951, "God of War: Sons of Sparta"),
        ]
    )

    article_title = (
        "God of War Sons of Sparta review: 2D Metroidvania gives "
        "Kratos new depth amid growing pains"
    )

    assert matcher.match(article_title) == 18951


def test_second_tier_does_not_force_generic_franchise_headline():
    matcher = NewsMatcher(
        [
            (15705, "Assassin's Creed Shadows"),
            (8811, "Far Cry 6"),
        ]
    )

    article_title = (
        "Ubisoft CEO confirms new Assassin's Creed and Far Cry games are coming"
    )

    assert matcher.match(article_title) is None


def test_second_tier_does_not_match_missing_terminal_number_token():
    matcher = NewsMatcher([(15124, "Grand Theft Auto IV")])

    article_title = "GTA Online Celebrates Valentine's Day With Free Champagne"
    description = (
        "Grand Theft Auto Online adds new bonuses for players this week."
    )

    assert matcher.match(article_title, description) is None


def test_second_tier_does_not_match_collectibles_news_to_game_title():
    matcher = NewsMatcher([(18724, "Pokémon Trading Card Game")])

    article_title = (
        "Logan Paul's Pikachu Illustrator Pokémon Trading Card Sells "
        "for $16.4 Million"
    )

    assert matcher.match(article_title) is None


def test_matches_description_when_title_is_generic():
    matcher = NewsMatcher([(18043, "skate.")])

    assert (
        matcher.match(
            article_title="EA addresses map-paywall criticism",
            description=(
                "Skate players unload on EA over broken promise "
                "about not paywalling maps."
            ),
        )
        == 18043
    )
