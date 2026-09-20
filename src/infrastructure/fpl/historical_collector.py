import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

import requests

from ...config import config
from ...domain.models.hindsight_models import PlayerGameweekRecord
from .repository import FPLDataRepository

logger = logging.getLogger("HistoricalDataCollector")


class HistoricalDataCollector:
    """Fetches, caches, and parses historical gameweek performance data from FPL API."""

    def __init__(
        self,
        repository: Optional[FPLDataRepository] = None,
        cache_dir: Optional[Path] = None,
        request_delay_sec: float = 1.0,
    ):
        self.repo = repository or FPLDataRepository()
        self.cache_dir = cache_dir or (config.data_cache_dir / "hindsight")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.request_delay_sec = request_delay_sec
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        })

    def collect_gameweek(self, gw: int, force_refresh: bool = False) -> List[PlayerGameweekRecord]:
        """Fetch and return all player records for a finished gameweek."""
        cache_file = self.cache_dir / f"gw_{gw}_live.json"
        raw_live_data = None

        if not force_refresh and cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    raw_live_data = json.load(f)
                logger.debug(f"Loaded GW{gw} live data from cache: {cache_file}")
            except Exception as e:
                logger.warning(f"Failed to read cache {cache_file}: {e}")

        if raw_live_data is None:
            url = f"{config.fpl_base_url}/event/{gw}/live/"
            logger.info(f"Fetching live data for GW{gw} from {url}")
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            raw_live_data = resp.json()

            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(raw_live_data, f, ensure_ascii=False, indent=2)
                logger.info(f"Cached GW{gw} live data to {cache_file}")
            except Exception as e:
                logger.warning(f"Failed to write cache {cache_file}: {e}")

            # Rate limit polite pause
            time.sleep(self.request_delay_sec)

        return self._parse_gameweek_records(gw, raw_live_data)

    def collect_range(self, gw_start: int, gw_end: int, force_refresh: bool = False) -> Dict[int, List[PlayerGameweekRecord]]:
        """Collect actual player performance records across a range of gameweeks."""
        results: Dict[int, List[PlayerGameweekRecord]] = {}
        for gw in range(gw_start, gw_end + 1):
            results[gw] = self.collect_gameweek(gw, force_refresh=force_refresh)
        return results

    def _parse_gameweek_records(self, gw: int, raw_live_data: Dict[str, Any]) -> List[PlayerGameweekRecord]:
        """Parse raw event/live response into structured domain records."""
        bootstrap = self.repo.get_bootstrap()
        fixtures = self.repo.get_fixtures()

        teams_by_id = {t["id"]: t for t in bootstrap.get("teams", [])}
        elements_by_id = {el["id"]: el for el in bootstrap.get("elements", [])}
        fixtures_by_id = {f["id"]: f for f in fixtures}

        # Build team fixture lookup for this gameweek
        gw_team_fixtures: Dict[int, Dict[str, Any]] = {}
        for f in fixtures:
            if f.get("event") == gw:
                gw_team_fixtures[f["team_h"]] = f
                gw_team_fixtures[f["team_a"]] = f

        records: List[PlayerGameweekRecord] = []
        for item in raw_live_data.get("elements", []):
            p_id = item["id"]
            stats = item.get("stats", {})
            p_meta = elements_by_id.get(p_id, {})

            team_id = p_meta.get("team", 0)
            element_type = p_meta.get("element_type", 0)
            web_name = p_meta.get("web_name", "")

            # Price at start of season: (now_cost - cost_change_start) / 10.0
            # For GW1 we use start price, for later GWs now_cost / 10.0 is a solid proxy
            now_cost = p_meta.get("now_cost", 50)
            cost_change_start = p_meta.get("cost_change_start", 0)
            if gw == 1:
                price = (now_cost - cost_change_start) / 10.0
            else:
                price = now_cost / 10.0

            # Match context
            was_home = False
            opponent_id = 0
            opponent_short = "UNK"
            fixture_difficulty = 3

            explain = item.get("explain", [])
            fixture_info = None
            if explain:
                f_id = explain[0].get("fixture")
                fixture_info = fixtures_by_id.get(f_id)

            if fixture_info is None and team_id in gw_team_fixtures:
                fixture_info = gw_team_fixtures[team_id]

            if fixture_info:
                if fixture_info.get("team_h") == team_id:
                    was_home = True
                    opponent_id = fixture_info.get("team_a", 0)
                    fixture_difficulty = fixture_info.get("team_h_difficulty", 3)
                else:
                    was_home = False
                    opponent_id = fixture_info.get("team_h", 0)
                    fixture_difficulty = fixture_info.get("team_a_difficulty", 3)

                opp_team = teams_by_id.get(opponent_id, {})
                opponent_short = opp_team.get("short_name", "UNK")

            record = PlayerGameweekRecord(
                player_id=p_id,
                gameweek=gw,
                total_points=stats.get("total_points", 0),
                minutes=stats.get("minutes", 0),
                goals_scored=stats.get("goals_scored", 0),
                assists=stats.get("assists", 0),
                clean_sheets=stats.get("clean_sheets", 0),
                bonus=stats.get("bonus", 0),
                was_home=was_home,
                opponent_id=opponent_id,
                opponent_short=opponent_short,
                fixture_difficulty=fixture_difficulty,
                price=price,
                element_type=element_type,
                web_name=web_name,
                team_id=team_id,
            )
            records.append(record)

        return records
