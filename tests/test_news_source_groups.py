from app.routers.news import _display_sources, _source_filter_values


def test_source_filter_values_expands_author_groups():
    assert _source_filter_values("Jason Schreier") == (
        "Jason Schreier (Bloomberg)",
        "Jason Schreier (Schrei Guy)",
    )
    assert _source_filter_values("Paul Tassi") == (
        "Paul Tassi (Forbes)",
        "Paul Tassi (God Rolls)",
    )


def test_source_filter_values_keeps_regular_source_exact():
    assert _source_filter_values("Game File") == ("Game File",)
    assert _source_filter_values(None) is None


def test_display_sources_collapses_author_variants_to_author_groups():
    sources = _display_sources(
        [
            "Game File",
            "Jason Schreier (Bloomberg)",
            "Jason Schreier (Schrei Guy)",
            "Paul Tassi (Forbes)",
            "Paul Tassi (God Rolls)",
        ]
    )

    assert sources == ["Game File", "Jason Schreier", "Paul Tassi"]


def test_display_sources_includes_author_group_when_only_one_variant_exists():
    assert _display_sources(["Jason Schreier (Bloomberg)"]) == ["Jason Schreier"]
