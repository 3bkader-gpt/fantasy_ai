import logging
from typing import Dict, List, Any, Optional
import requests

from ...domain.interfaces.fpl_gateway import IFPLGateway
from ...domain.models.transfer import Transfer
from ...config import config
from .authenticator import PlaywrightFPLAuthenticator

logger = logging.getLogger("FPLClient")


class FPLClient(IFPLGateway):
    """Handles FPL account authentication, team fetching, transfers and lineup submission."""

    def __init__(
        self,
        email: str = config.fpl_email,
        password: str = config.fpl_password,
        cookie: str = config.fpl_cookie,
        dry_run: bool = config.dry_run
    ):
        self.email = email
        self.password = password
        self.cookie = cookie
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://fantasy.premierleague.com/",
        })
        self.is_authenticated = False

    def login(self) -> bool:
        if self.email and self.password:
            self.is_authenticated = True
            logger.info("Autonomous FPL credentials ready.")
            return True
        if self.cookie and len(self.cookie.strip()) > 10:
            cookie_val = self.cookie.strip()
            self.session.cookies.set("pl_profile", cookie_val, domain=".premierleague.com")
            self.is_authenticated = True
            return True
        return False

    def get_history_and_chips(self, team_id: int) -> Dict[str, Any]:
        url = f"{config.fpl_base_url}/entry/{team_id}/history/"
        try:
            res = self.session.get(url, timeout=15)
            if res.status_code == 200:
                data = res.json()
                chips_used = data.get("chips", [])
                used_names = [c.get("name") for c in chips_used]
                chips_available = {
                    "wildcard": 2 - used_names.count("wildcard"),
                    "freehit": 1 - used_names.count("freehit"),
                    "3xc": 1 - used_names.count("3xc"),
                    "bboost": 1 - used_names.count("bboost")
                }
                current_events = data.get("current", [])
                latest = current_events[-1] if current_events else {}
                return {
                    "chips_used": chips_used,
                    "chips_available": chips_available,
                    "overall_rank": latest.get("overall_rank"),
                    "total_points": latest.get("total_points", 0),
                    "team_value": latest.get("value", 1000) / 10.0,
                }
        except Exception as e:
            logger.warning(f"Could not retrieve history for team {team_id}: {e}")
        return {"chips_used": [], "chips_available": {}}

    def get_my_team(self, team_id: int) -> Dict[str, Any]:
        if not team_id:
            raise ValueError("FPL_TEAM_ID must be provided.")

        history = self.get_history_and_chips(team_id)

        if self.is_authenticated:
            try:
                url = f"{config.fpl_my_team_url}/{team_id}/"
                res = self.session.get(url, timeout=15)
                if res.status_code == 200:
                    data = res.json()
                    transfers_info = data.get("transfers", {})
                    limit = transfers_info.get("limit", 1)
                    made = transfers_info.get("made", 0)
                    return {
                        "is_authenticated": True,
                        "picks": data.get("picks", []),
                        "chips_available": history.get("chips_available", {}),
                        "bank": transfers_info.get("bank", 0) / 10.0,
                        "free_transfers": max(1, min(5, limit - made)),
                        "rank": history.get("overall_rank"),
                        "total_points": history.get("total_points", 0),
                        "team_value": history.get("team_value", 100.0),
                    }
            except Exception as e:
                logger.warning(f"Failed to fetch /my-team/: {e}. Falling back to public endpoints.")

        entry_url = f"{config.fpl_base_url}/entry/{team_id}/"
        entry_res = self.session.get(entry_url, timeout=15)
        if entry_res.status_code != 200:
            raise RuntimeError(f"Could not fetch team data for ID {team_id} (Status: {entry_res.status_code})")

        entry_data = entry_res.json()
        current_gw = entry_data.get("current_event", 1)
        picks_url = f"{config.fpl_base_url}/entry/{team_id}/event/{current_gw}/picks/"
        picks_res = self.session.get(picks_url, timeout=15)
        picks = picks_res.json().get("picks", []) if picks_res.status_code == 200 else []
        if not picks:
            baseline_file = config.data_cache_dir / f"team_{team_id}_baseline.json"
            if baseline_file.exists():
                import json
                try:
                    with open(baseline_file, "r", encoding="utf-8") as f:
                        picks = json.load(f)
                        logger.info(f"Loaded {len(picks)} initial picks from baseline squad file.")
                except Exception:
                    pass

        bank_val = entry_data.get("last_deadline_bank")
        bank = (float(bank_val) if bank_val is not None else 12.0) / 10.0
        val_val = entry_data.get("last_deadline_value")
        team_val = (float(val_val) if val_val is not None else 1000.0) / 10.0

        return {
            "is_authenticated": False,
            "picks": picks,
            "chips_available": history.get("chips_available", {}),
            "bank": bank,
            "free_transfers": 1,
            "rank": entry_data.get("summary_overall_rank") or history.get("overall_rank"),
            "total_points": entry_data.get("summary_overall_points", 0),
            "team_value": team_val,
            "leagues": entry_data.get("leagues", {}).get("classic", []),
            "manager_name": f"{entry_data.get('player_first_name', '')} {entry_data.get('player_last_name', '')}".strip(),
            "team_name": entry_data.get("name", "FPL Squad")
        }

    def set_lineup(self, team_id: int, picks_payload: List[Dict[str, Any]], chip: Optional[str] = None) -> Dict[str, Any]:
        payload = {"chip": chip, "picks": picks_payload}
        if self.dry_run:
            logger.info("[DRY RUN] Lineup submission simulated.")
            return {"status": "simulated", "dry_run": True, "payload": payload}
        if self.email and self.password:
            return PlaywrightFPLAuthenticator(self.email, self.password).submit_lineup_live(team_id, picks_payload, chip)
        headers = {"Content-Type": "application/json; charset=UTF-8", "X-Requested-With": "XMLHttpRequest"}
        res = self.session.post(f"{config.fpl_my_team_url}/{team_id}/", json=payload, headers=headers, timeout=15)
        return {"status": "success" if res.status_code == 200 else "error", "code": res.status_code}

    def make_transfers(self, team_id: int, transfers: List[Transfer], next_gw: int, chip: Optional[str] = None) -> Dict[str, Any]:
        if not transfers:
            return {"status": "noop", "message": "No transfers to execute."}
        payload = {
            "confirmed": True, "entry": team_id, "event": next_gw,
            "transfers": [{"element_in": t.player_in.id, "element_out": t.player_out.id,
                           "purchase_price": t.player_in.now_cost,
                           "selling_price": t.player_out.selling_price or t.player_out.now_cost} for t in transfers],
            "wildcard": (chip == "wildcard"), "freehit": (chip == "freehit")
        }
        if self.dry_run:
            logger.info(f"[DRY RUN] Transfers simulated for {len(transfers)} player(s).")
            return {"status": "simulated", "dry_run": True, "payload": payload}
        if self.email and self.password:
            return PlaywrightFPLAuthenticator(self.email, self.password).submit_transfers_live(team_id, payload)
        headers = {"Content-Type": "application/json; charset=UTF-8", "X-Requested-With": "XMLHttpRequest"}
        res = self.session.post(config.fpl_transfers_url, json=payload, headers=headers, timeout=15)
        return {"status": "success" if res.status_code in (200, 201) else "error", "code": res.status_code}
