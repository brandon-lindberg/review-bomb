"""
RSS feed service for fetching gaming news articles.

Aggregates news from multiple gaming outlets via their RSS feeds.
"""

import asyncio
import html
import re
from datetime import datetime, timezone
from time import mktime
from typing import Any, Optional

import feedparser
import httpx


class NewsRSSService:
    """Fetches and parses gaming news RSS feeds."""

    FeedConfig = str | tuple[str, ...]

    FEEDS = {
        "IGN": "https://feeds.feedburner.com/ign/all",
        "GameSpot": "https://www.gamespot.com/feeds/news/",
        "Kotaku": "https://kotaku.com/rss",
        "PC Gamer": "https://www.pcgamer.com/rss/",
        "Polygon": "https://www.polygon.com/rss/index.xml",
        "Eurogamer": "https://www.eurogamer.net/feed",
        "The Verge": "https://www.theverge.com/rss/games/index.xml",
        "Jason Schreier (Bloomberg)": (
            "https://www.bloomberg.com/authors/AUvqMRVAZCw/jason-schreier.rss",
            "https://jasonschreier.substack.com/feed",
        ),
        # Forbes author feeds are blocked in this environment. Use Innovation feed
        # and filter to Paul Tassi entries by author and URL.
        "Paul Tassi (Forbes)": (
            "https://www.forbes.com/innovation/feed/",
            "https://paultassi.substack.com/feed",
        ),
        "Bellular": "https://bellular.games/tag/news-posts/feed/",
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

    FEED_RULES: dict[str, dict[str, Any]] = {
        "https://www.forbes.com/innovation/feed/": {
            "required_author_contains": "paul tassi",
            "required_url_contains": "/sites/paultassi/",
            "enforce_game_relevance": True,
        },
    }

    SOURCE_RULES: dict[str, dict[str, Any]] = {
        "Bellular": {
            "enforce_game_relevance": True,
        },
    }

    REQUEST_TIMEOUT = 30.0

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    GAME_SIGNAL_TERMS = (
        "video game",
        "gaming",
        "steam",
        "playstation",
        "ps5",
        "ps4",
        "xbox",
        "nintendo",
        "switch",
        "pc game",
        "dlc",
        "game update",
        "patch notes",
        "early access",
        "indie game",
        "game studio",
        "developer",
        "metacritic",
        "opencritic",
    )
    NON_GAME_MEDIA_TERMS = (
        "netflix",
        "tv series",
        "tv show",
        "season ",
        "episode ",
        "movie",
        "box office",
        "rotten tomatoes",
        "viewership",
    )
    NON_VIDEO_GAME_PUZZLE_TERMS = (
        "nyt connections",
        "connections hints",
        "wordle",
        "crossword",
        "strands puzzle",
    )

    @staticmethod
    def _strip_html(text: Optional[str]) -> Optional[str]:
        """Remove HTML tags and decode entities from text."""
        if not text:
            return None
        clean = re.sub(r"<[^>]+>", "", text)
        clean = html.unescape(clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    @staticmethod
    def _extract_image(entry: dict) -> Optional[str]:
        """Extract the best image URL from an RSS entry."""
        # media:content (common in RSS 2.0 with media namespace)
        media_content = entry.get("media_content", [])
        if media_content:
            for media in media_content:
                url = media.get("url", "")
                if media.get("medium") == "image" or any(
                    ext in url.lower() for ext in (".jpg", ".jpeg", ".png", ".webp")
                ):
                    return url

        # media:thumbnail
        media_thumbnail = entry.get("media_thumbnail", [])
        if media_thumbnail:
            return media_thumbnail[0].get("url")

        # enclosures (standard RSS)
        enclosures = entry.get("enclosures", [])
        for enc in enclosures:
            enc_type = enc.get("type", "")
            if enc_type.startswith("image/"):
                return enc.get("href") or enc.get("url")

        # og:image in links
        links = entry.get("links", [])
        for link in links:
            if link.get("type", "").startswith("image/"):
                return link.get("href")

        return None

    @staticmethod
    def _parse_date(entry: dict) -> Optional[datetime]:
        """Parse publication date from a feed entry."""
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed:
            try:
                return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
            except (ValueError, OverflowError):
                return None
        return None

    def _is_video_game_relevant(
        self,
        *,
        title: str,
        description: str | None,
        url: str,
    ) -> bool:
        combined = f"{title} {description or ''} {url}".lower()
        if any(term in combined for term in self.NON_VIDEO_GAME_PUZZLE_TERMS):
            return False

        has_game_signal = any(term in combined for term in self.GAME_SIGNAL_TERMS)
        has_non_game_media = any(term in combined for term in self.NON_GAME_MEDIA_TERMS)

        if has_non_game_media and not has_game_signal:
            return False
        return has_game_signal

    @classmethod
    def _iter_feed_urls(cls, feed_config: FeedConfig) -> tuple[str, ...]:
        if isinstance(feed_config, str):
            return (feed_config,)
        return feed_config

    @classmethod
    def _rules_for_entry(
        cls,
        source_name: str,
        feed_url: str | None = None,
    ) -> dict[str, Any]:
        rules = dict(cls.SOURCE_RULES.get(source_name, {}))
        if feed_url is not None:
            rules.update(cls.FEED_RULES.get(feed_url, {}))
            return rules

        feed_config = cls.FEEDS.get(source_name)
        if feed_config is None:
            return rules
        feed_rules = [
            cls.FEED_RULES[url]
            for url in cls._iter_feed_urls(feed_config)
            if url in cls.FEED_RULES
        ]
        if len(feed_rules) == 1:
            rules.update(feed_rules[0])
        return rules

    def _parse_entry(
        self,
        entry: dict,
        source_name: str,
        feed_url: str | None = None,
    ) -> Optional[dict[str, Any]]:
        """Parse a single RSS feed entry into our article format."""
        title = self._strip_html(entry.get("title"))
        link = entry.get("link")

        if not title or not link:
            return None

        description = self._strip_html(
            entry.get("summary") or entry.get("description")
        )
        if description and len(description) > 500:
            description = description[:497] + "..."

        author = entry.get("author")
        rules = self._rules_for_entry(source_name, feed_url)
        required_author = rules.get("required_author_contains")
        if required_author and required_author not in (author or "").lower():
            return None

        required_url = rules.get("required_url_contains")
        if required_url and required_url not in link.lower():
            return None

        if rules.get("enforce_game_relevance"):
            if not self._is_video_game_relevant(
                title=title,
                description=description,
                url=link,
            ):
                return None

        return {
            "title": title[:512],
            "description": description,
            "url": link[:1024],
            "image_url": self._extract_image(entry),
            "source_name": source_name,
            "author": author,
            "published_at": self._parse_date(entry),
        }

    async def fetch_feed(self, source_name: str, url: str) -> list[dict[str, Any]]:
        """Fetch and parse a single RSS feed."""
        try:
            async with httpx.AsyncClient(
                timeout=self.REQUEST_TIMEOUT,
                headers={"User-Agent": self.USER_AGENT},
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

            feed = feedparser.parse(response.text)
            articles = []
            for entry in feed.entries:
                article = self._parse_entry(entry, source_name, url)
                if article:
                    articles.append(article)

            return articles

        except Exception as e:
            print(f"Error fetching {source_name} RSS feed: {e}")
            return []

    async def fetch_all_feeds(self) -> list[dict[str, Any]]:
        """Fetch all configured RSS feeds concurrently."""
        tasks = [
            self.fetch_feed(name, url)
            for name, feed_config in self.FEEDS.items()
            for url in self._iter_feed_urls(feed_config)
        ]
        results = await asyncio.gather(*tasks)

        # Flatten all results
        all_articles = []
        for articles in results:
            all_articles.extend(articles)

        # Sort by published date (newest first)
        all_articles.sort(
            key=lambda a: a.get("published_at") or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        return all_articles
