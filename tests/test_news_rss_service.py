from __future__ import annotations

import pytest

from app.services.news_rss import NewsRSSService


NEW_NEWS_FEEDS = {
    "Jason Schreier (Schrei Guy)": "https://jasonschreier.substack.com/feed",
    "Paul Tassi (God Rolls)": "https://paultassi.substack.com/feed",
    "GameDiscoverCo": "https://newsletter.gamediscover.co/feed",
    "The Game Business": "https://www.thegamebusiness.com/feed",
    "Game File": "https://www.gamefile.news/feed",
    "Hit Points": "https://newsletter.hitpoints.co/rss/",
    "Crossplay": "https://www.crossplay.news/feed",
    "Post Games": "https://postgame.substack.com/feed",
    "Game & Word": "https://gameandword.substack.com/feed",
    "SuperJoost Playlist": "https://superjoost.substack.com/feed",
    "Game (Pad and Pixel)": "https://game.substack.com/feed",
    "Video Games Industry Memo": "https://www.videogamesindustrymemo.com/feed",
}


def test_author_substack_feeds_are_labeled_as_independent_sources():
    assert (
        NewsRSSService.FEEDS["Jason Schreier (Bloomberg)"]
        == "https://www.bloomberg.com/authors/AUvqMRVAZCw/jason-schreier.rss"
    )
    assert NewsRSSService.FEEDS["Jason Schreier (Schrei Guy)"] == "https://jasonschreier.substack.com/feed"
    assert NewsRSSService.FEEDS["Paul Tassi (Forbes)"] == "https://www.forbes.com/sites/paultassi/feed/"
    assert NewsRSSService.FEEDS["Paul Tassi (God Rolls)"] == "https://paultassi.substack.com/feed"
    assert "Jason Schreier (Substack)" not in NewsRSSService.FEEDS
    assert "Paul Tassi (Substack)" not in NewsRSSService.FEEDS


def test_configured_feed_count_counts_grouped_feed_urls():
    assert NewsRSSService.configured_source_count() == 22
    assert NewsRSSService.configured_feed_count() == 22


def test_new_newsletter_sources_are_configured():
    for source_name, feed_url in NEW_NEWS_FEEDS.items():
        assert NewsRSSService.FEEDS[source_name] == feed_url


@pytest.mark.parametrize("source_name", NEW_NEWS_FEEDS)
def test_parse_entry_keeps_new_newsletter_source_names(source_name):
    service = NewsRSSService()
    entry = {
        "title": "Steam launch analysis shows a breakout indie game",
        "link": f"https://example.com/{source_name.lower().replace(' ', '-')}",
        "summary": "A market note about Steam performance and video game discovery.",
        "author": "Example Author",
    }

    article = service._parse_entry(entry, source_name)

    assert article is not None
    assert article["source_name"] == source_name


def test_parse_entry_keeps_paul_tassi_substack_under_god_rolls_source():
    service = NewsRSSService()
    entry = {
        "title": "God Rolls - Destiny Burns, Starfield's Sky, Diablo 4 Doubts",
        "link": "https://paultassi.substack.com/p/god-rolls-destiny-burns-starfields",
        "summary": "A weekly roundup about Destiny, Starfield, and Diablo 4.",
        "author": "Paul Tassi",
    }

    article = service._parse_entry(
        entry,
        "Paul Tassi (God Rolls)",
        "https://paultassi.substack.com/feed",
    )

    assert article is not None
    assert article["source_name"] == "Paul Tassi (God Rolls)"


def test_parse_entry_keeps_jason_schreier_substack_under_schrei_guy_source():
    service = NewsRSSService()
    entry = {
        "title": "Frequently asked questions about Play Nice",
        "link": "https://jasonschreier.substack.com/p/frequently-asked-questions-about-play",
        "summary": "A note about Play Nice: The Rise, Fall, and Future of Blizzard Entertainment.",
        "author": "Jason Schreier",
    }

    article = service._parse_entry(
        entry,
        "Jason Schreier (Schrei Guy)",
        "https://jasonschreier.substack.com/feed",
    )

    assert article is not None
    assert article["source_name"] == "Jason Schreier (Schrei Guy)"


def test_parse_entry_keeps_paul_tassi_game_article():
    service = NewsRSSService()
    entry = {
        "title": "Slay The Spire 2 Breaks Two Steam Player Count Records In One Day",
        "link": "https://www.forbes.com/sites/paultassi/2026/03/06/slay-the-spire-2-breaks-two-steam-player-count-records-in-one-day/",
        "summary": "Slay the Spire 2 is a smash hit on Steam, shattering player count records.",
        "author": "Paul Tassi, Senior Contributor",
    }

    article = service._parse_entry(entry, "Paul Tassi (Forbes)")

    assert article is not None
    assert article["source_name"] == "Paul Tassi (Forbes)"
    assert article["author"] == "Paul Tassi, Senior Contributor"


def test_parse_entry_keeps_paul_tassi_forbes_author_feed_game_article():
    service = NewsRSSService()
    entry = {
        "title": "Bungie May Transform 'Marathon' Entirely This Year, According To Its New Roadmap",
        "link": "https://www.forbes.com/sites/paultassi/2026/05/16/bungie-may-transform-marathon-entirely-this-year-according-to-its-new-roadmap/",
        "summary": "Marathon may transform what the entire game is over the next year.",
        "author": "Paul Tassi, Senior Contributor",
    }

    article = service._parse_entry(
        entry,
        "Paul Tassi (Forbes)",
        "https://www.forbes.com/sites/paultassi/feed/",
    )

    assert article is not None
    assert article["source_name"] == "Paul Tassi (Forbes)"


@pytest.mark.parametrize(
    ("title", "summary"),
    [
        (
            "Sony's PlayStation PC Departure Is The Right Move For Them, Not Players",
            "Sony is changing its PlayStation PC port strategy for single-player games.",
        ),
        (
            "Xbox Reveals Its Top 10 Player Demands In New Transparency Era",
            "Microsoft shares the most requested Xbox hardware and Game Pass changes.",
        ),
        (
            "Steam Deck Rival Gets New Hardware Revision",
            "A new handheld PC gaming device targets Steam users.",
        ),
    ],
)
def test_parse_entry_keeps_platform_business_and_hardware_news(title, summary):
    service = NewsRSSService()
    entry = {
        "title": title,
        "link": "https://www.forbes.com/sites/paultassi/2026/05/19/platform-business-news/",
        "summary": summary,
        "author": "Paul Tassi, Senior Contributor",
    }

    article = service._parse_entry(
        entry,
        "Paul Tassi (Forbes)",
        "https://www.forbes.com/sites/paultassi/feed/",
    )

    assert article is not None


def test_parse_entry_drops_paul_tassi_non_game_media_article():
    service = NewsRSSService()
    entry = {
        "title": "Reviews Are In For Netflix's War Machine With Reacher's Alan Ritchson",
        "link": "https://www.forbes.com/sites/paultassi/2026/03/06/reviews-are-in-for-netflixs-war-machine-with-reachers-alan-ritchson/",
        "summary": "A sci-fi action movie review with Rotten Tomatoes scores and viewership discussion.",
        "author": "Paul Tassi, Senior Contributor",
    }

    article = service._parse_entry(entry, "Paul Tassi (Forbes)")

    assert article is None


def test_parse_entry_drops_paul_tassi_when_author_does_not_match():
    service = NewsRSSService()
    entry = {
        "title": "The Marathon Day One Steam Player Count Is A Bit Concerning",
        "link": "https://www.forbes.com/sites/paultassi/2026/03/06/the-marathon-day-one-steam-player-count-is-a-bit-concerning/",
        "summary": "A look at Marathon Steam concurrency and launch momentum.",
        "author": "Erik Kain, Senior Contributor",
    }

    article = service._parse_entry(entry, "Paul Tassi (Forbes)")

    assert article is None


def test_parse_entry_drops_bellular_non_game_post():
    service = NewsRSSService()
    entry = {
        "title": "Discord Backtrack, Claiming (Again) That They'll Do Better This Time",
        "link": "https://bellular.games/discord-backtrack-claiming-again-that-theyll-do-better-this-time/",
        "summary": "A platform policy discussion about moderation and account controls.",
        "author": "Bellular",
    }

    article = service._parse_entry(entry, "Bellular")

    assert article is None


def test_parse_entry_keeps_bellular_game_post():
    service = NewsRSSService()
    entry = {
        "title": "The Console War Resurrected... PS5 Finally Gets True Exclusives",
        "link": "https://bellular.games/the-console-war-resurrected-ps5-finally-gets-true-exclusives/",
        "summary": "A look at PS5 game exclusives and shifting console strategy.",
        "author": "Bellular",
    }

    article = service._parse_entry(entry, "Bellular")

    assert article is not None
    assert article["source_name"] == "Bellular"
