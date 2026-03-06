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


def test_ambiguous_single_word_title_does_not_hijack_marathon_headline():
    matcher = NewsMatcher(
        [
            (9991, "Everything"),
            (9992, "Marathon"),
        ]
    )

    article_title = "Everything you need to know about Marathon after Bungie's reveal"
    description = "Bungie shared Marathon gameplay details, release plans, and platform updates."

    assert matcher.match(article_title, description) == 9992


def test_ambiguous_single_word_title_still_matches_with_game_context():
    matcher = NewsMatcher([(9991, "Everything")])

    article_title = "Everything review roundup praises this surreal exploration game"

    assert matcher.match(article_title) == 9991


def test_ambiguous_single_word_title_returns_none_for_generic_prose_headline():
    matcher = NewsMatcher([(9991, "Everything")])

    article_title = "Everything you need to know about Bungie's new extraction shooter"
    description = "Here are all the key Marathon details from today's reveal."

    assert matcher.match(article_title, description) is None


def test_ambiguous_title_not_matched_from_non_game_usage_mid_headline():
    matcher = NewsMatcher(
        [
            (9993, "Control"),
            (9992, "Marathon"),
        ]
    )

    article_title = "Bungie says control schemes in Marathon can be fully customized"
    description = "Marathon supports remapping and accessibility options at launch."

    assert matcher.match(article_title, description) == 9992


def test_common_single_word_title_not_matched_from_prepositional_phrase():
    matcher = NewsMatcher([(7001, "Return")])

    article_title = "A Couple invited Sony To Their Wedding, And Got A Gift In Return"
    description = "The surprise package was sent after a viral post."

    assert matcher.match(article_title, description) is None


def test_common_single_word_title_not_matched_from_lore_phrase():
    matcher = NewsMatcher([(7002, "Hatred")])

    article_title = (
        "Is this a 2.0 moment for Diablo 4? Unpacking the new warlock class "
        "and the new Lord of Hatred expansion"
    )
    description = "Blizzard's reveal focused on a class overhaul and endgame updates."

    assert matcher.match(article_title, description) is None


def test_common_single_word_title_still_matches_with_game_context():
    matcher = NewsMatcher([(7003, "Return")])

    article_title = "Return gameplay preview outlines combat systems and bosses"

    assert matcher.match(article_title) == 7003


def test_common_single_word_title_not_matched_from_description_only_generic_phrase():
    matcher = NewsMatcher([(7004, "Return")])

    article_title = "Microsoft teases its next Xbox, says Project Helix will play PC games too"
    description = (
        "Team Xbox says Project Helix is part of a long-term commitment "
        "to the return of Xbox."
    )

    assert matcher.match(article_title, description) is None


def test_single_word_title_with_strong_non_generic_title_match_still_links():
    matcher = NewsMatcher([(7005, "Marathon"), (7006, "Everything")])

    article_title = "What is the Cryo Archive zone in Marathon?"
    description = "Guide for Marathon players entering the Cryo Archive."

    assert matcher.match(article_title, description) == 7005


def test_sequel_number_prefers_roman_numeral_game_record():
    matcher = NewsMatcher(
        [
            (16, "Helldivers"),
            (14823, "Helldivers II"),
        ]
    )

    article_title = "Helldivers 2 Charity Challenge Leads To Death Threats"

    assert matcher.match(article_title) == 14823


def test_sequel_number_does_not_link_base_game_when_sequel_missing():
    matcher = NewsMatcher([(6426, "Slay The Spire")])

    article_title = "Slay the Spire 2 Launches, Immediately Shatters a Concurrent Player Record on Steam"

    assert matcher.match(article_title) is None


def test_description_only_candidate_does_not_override_title_candidates():
    matcher = NewsMatcher(
        [
            (6426, "Slay The Spire"),
            (18847, "Mewgenics"),
        ]
    )

    article_title = "Slay the Spire 2 Launches, Immediately Shatters a Concurrent Player Record on Steam"
    description = "Mewgenics fans are still waiting on release details."

    assert matcher.match(article_title, description) is None


def test_sequel_number_does_not_link_base_control_game():
    matcher = NewsMatcher([(6998, "Control")])

    article_title = "Control 2 Doesn’t Feature A Parry Button And 6 Other Things We Just Learned About It"

    assert matcher.match(article_title) is None
