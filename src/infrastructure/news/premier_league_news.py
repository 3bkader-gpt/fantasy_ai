import logging
import urllib.request
import urllib.error
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger("PremierLeagueNewsService")


class PremierLeagueNewsService:
    """Fetches and filters official Premier League articles, press conferences, and team news."""

    BASE_URL = "https://footballapi.pulselive.com/content/premierleague/text/en"
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://www.premierleague.com",
        "Referer": "https://www.premierleague.com/",
        "Accept": "application/json",
    }

    RELEVANT_KEYWORDS = [
        "injury", "injuries", "fitness", "press", "presser", "conference", 
        "team news", "doubt", "ruled out", "available", "training", "bench", 
        "start", "starts", "rotation", "rotated", "fpl", "update", "knock", 
        "hamstring", "knee", "groin", "illness", "suspension", "banned"
    ]

    def __init__(self, timeout: int = 8):
        self.timeout = timeout

    def fetch_recent_news(self, page: int = 0, page_size: int = 35) -> List[Dict[str, Any]]:
        """Queries PulseLive API for the latest Premier League articles."""
        url = f"{self.BASE_URL}?page={page}&pageSize={page_size}"
        try:
            req = urllib.request.Request(url, headers=self.DEFAULT_HEADERS)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    articles = data.get("content", [])
                    logger.info(f"Fetched {len(articles)} articles from Premier League API.")
                    return articles
                logger.warning(f"PulseLive API returned HTTP status {resp.status}")
                return []
        except urllib.error.URLError as e:
            logger.warning(f"Network error fetching Premier League news: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Premier League news: {e}")
            return []

    def filter_tactical_and_injury_news(
        self, 
        articles: List[Dict[str, Any]], 
        player_names: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Filters articles relevant to injuries, fitness, press conferences, or tracked players.
        """
        filtered = []
        lower_players = [p.lower() for p in (player_names or []) if p]

        for item in articles:
            title = (item.get("title") or "").strip()
            summary = (item.get("summary") or "").strip()
            description = (item.get("description") or "").strip()
            combined_text = f"{title} {summary} {description}".lower()

            # Exclude non-relevant topics (e.g. U21 match summaries, Women's team, third kit releases)
            if any(exc in combined_text for exc in ["u21 report", "u18", "women", "third kit", "gallery:"]):
                continue

            # 1. Match against specific tracked player names
            has_player_match = any(p in combined_text for p in lower_players)

            # 2. Match against general press conference / tactical / injury keywords
            has_keyword_match = any(kw in combined_text for kw in self.RELEVANT_KEYWORDS)

            if has_player_match or has_keyword_match:
                filtered.append({
                    "id": item.get("id"),
                    "title": title,
                    "summary": summary or description,
                    "date": item.get("date"),
                    "url": item.get("hotlinkUrl") or item.get("canonicalUrl") or f"https://www.premierleague.com/en/news/{item.get('id')}",
                    "matched_players": [p for p in lower_players if p in combined_text]
                })

        logger.info(f"Filtered {len(filtered)} relevant news articles from {len(articles)} total.")
        return filtered

    @staticmethod
    def extract_fpl_flags_news(bootstrap_elements: List[Dict[str, Any]], player_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        """
        Extracts official FPL injury & availability flags from bootstrap-static elements.
        """
        tracked_ids = set(player_ids) if player_ids else None
        flagged = []

        for p in bootstrap_elements:
            pid = p.get("id")
            if tracked_ids and pid not in tracked_ids:
                continue

            news = p.get("news", "").strip()
            chance = p.get("chance_of_playing_next_round")
            status = p.get("status", "a")

            if news or status != "a" or (chance is not None and chance < 100):
                flagged.append({
                    "player_id": pid,
                    "web_name": p.get("web_name"),
                    "team_id": p.get("team"),
                    "status": status,
                    "chance_of_playing": chance,
                    "news": news,
                    "news_added": p.get("news_added")
                })

        return flagged
