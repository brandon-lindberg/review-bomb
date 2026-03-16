from app.services.news_matcher import NewsMatcher


def test_edge_does_not_match_when_only_referenced_inside_mirrors_edge_phrase():
    matcher = NewsMatcher([(8101, "Edge")])

    article_title = "New parkour game channels Mirror's Edge in stylish reveal trailer"
    description = "The newly announced game looks fast and fluid but it is not called Edge."

    assert matcher.match(article_title, description) is None


def test_mirrors_edge_reference_does_not_link_when_article_is_about_another_game():
    matcher = NewsMatcher([(8102, "Mirror's Edge")])

    article_title = "New parkour game channels Mirror's Edge in stylish reveal trailer"
    description = "This spiritual successor to Mirror's Edge stars a different protagonist."

    assert matcher.match(article_title, description) is None
