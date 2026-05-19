from __future__ import annotations

import pytest

from app.services.news_rss import NewsRSSService


NEW_NEWS_FEEDS = {
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
