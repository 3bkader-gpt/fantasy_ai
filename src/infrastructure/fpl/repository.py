import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import requests

from ...domain.interfaces.data_repository import IDataRepository
from ...domain.models.player import Player
from ...domain.models.fixture import Fixture
from ...config import config

logger = logging.getLogger("FPLDataRepository")

POSITION_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


class FPLDataRepository(IDataRepository):
    """Fetches, caches, and parses data from the official FPL Public API."""

    def __init__(self, cache_ttl_minutes: int = 15):
        self.cache_ttl = cache_ttl_minutes * 60
        self.cache_dir = config.data_cache_dir
        self.cache_dir.mkdir(exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        })

    def _get_cached(self, url: str, filename: str, force_refresh: bool = False) -> Any:
        cache_path = self.cache_dir / filename
        if not force_refresh and cache_path.exists():
            if (time.time() - cache_path.stat().st_mtime) < self.cache_ttl:
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        headers = {"Cache-Control": "no-cache"} if force_refresh else {}
        resp = self.session.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write cache {filename}: {e}")
        return data

    def get_bootstrap(self, force_refresh: bool = False) -> Dict[str, Any]:
        return self._get_cached(config.fpl_bootstrap_url, "bootstrap_static.json", force_refresh=force_refresh)

    def get_fixtures(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        return self._get_cached(config.fpl_fixtures_url, "fixtures.json", force_refresh=force_refresh)

    def get_current_and_next_gw(self) -> Tuple[Optional[int], Optional[int], Optional[str]]:
        data = self.get_bootstrap()
        events = data.get("events", [])
        current_gw, next_gw, next_deadline = None, None, None

        for ev in events:
            if ev.get("is_current"):
                current_gw = ev.get("id")
            if ev.get("is_next"):
                next_gw = ev.get("id")
                next_deadline = ev.get("deadline_time")

        if current_gw is None and next_gw is not None and next_gw > 1:
            current_gw = next_gw - 1

        return current_gw, next_gw, next_deadline

    def get_all_players(self, force_refresh: bool = False) -> List[Player]:
        data = self.get_bootstrap(force_refresh=force_refresh)
        teams = {t["id"]: t for t in data.get("teams", [])}
        raw_players = data.get("elements", [])

        players: List[Player] = []
        for p in raw_players:
            team_info = teams.get(p["team"], {})
            pos_id = p.get("element_type", 0)
            player = Player(
                id=p["id"],
                name=p["web_name"],
                full_name=f"{p.get('first_name', '')} {p.get('second_name', '')}".strip(),
                position_id=pos_id,
                position=POSITION_MAP.get(pos_id, "UNK"),
                team_id=p["team"],
                team_name=team_info.get("name", "Unknown"),
                team_short=team_info.get("short_name", "UNK"),
                cost=p["now_cost"] / 10.0,
                now_cost=p["now_cost"],
                total_points=p.get("total_points", 0),
                points_per_game=float(p.get("points_per_game", 0.0) or 0.0),
                form=float(p.get("form", 0.0) or 0.0),
                selected_by_percent=float(p.get("selected_by_percent", 0.0) or 0.0),
                minutes=p.get("minutes", 0),
                goals_scored=p.get("goals_scored", 0),
                assists=p.get("assists", 0),
                clean_sheets=p.get("clean_sheets", 0),
                status=p.get("status", "a"),
                news=p.get("news", ""),
                chance_of_playing_next_round=p.get("chance_of_playing_next_round"),
                expected_goals=float(p.get("expected_goals", 0.0) or 0.0),
                expected_assists=float(p.get("expected_assists", 0.0) or 0.0),
                expected_goal_involvements=float(p.get("expected_goal_involvements", 0.0) or 0.0),
                ict_index=float(p.get("ict_index", 0.0) or 0.0),
            )
            players.append(player)
        return players

    def get_team_fixtures(self, next_gw: int, weeks_ahead: int = 5) -> Dict[int, List[Fixture]]:
        raw_fixtures = self.get_fixtures()
        teams = {t["id"]: t for t in self.get_bootstrap().get("teams", [])}
        target_gws = set(range(next_gw, next_gw + weeks_ahead))

        team_fixtures: Dict[int, List[Fixture]] = {t_id: [] for t_id in teams.keys()}
        for fix in raw_fixtures:
            event = fix.get("event")
            if event in target_gws:
                t_home = fix["team_h"]
                t_away = fix["team_a"]
                diff_home = fix.get("team_h_difficulty", 3)
                diff_away = fix.get("team_a_difficulty", 3)

                if t_home in team_fixtures:
                    team_fixtures[t_home].append(Fixture(
                        event=event,
                        is_home=True,
                        opponent_id=t_away,
                        opponent_name=teams.get(t_away, {}).get("short_name", "OPP"),
                        difficulty=diff_home
                    ))
                if t_away in team_fixtures:
                    team_fixtures[t_away].append(Fixture(
                        event=event,
                        is_home=False,
                        opponent_id=t_home,
                        opponent_name=teams.get(t_home, {}).get("short_name", "OPP"),
                        difficulty=diff_away
                    ))

        return team_fixtures
