import logging
from typing import Dict, List, Any, Optional, Tuple
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
        bearer_token: str = config.fpl_bearer_token,
        refresh_token: str = config.fpl_refresh_token,
        dry_run: bool = config.dry_run
    ):
        self.email = email
        self.password = password
        self.cookie = cookie
        self.bearer_token = bearer_token
        self.refresh_token = refresh_token
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://fantasy.premierleague.com/en/my-team",
        })
        self.is_authenticated = False
        if self.bearer_token and len(self.bearer_token.strip()) > 10:
            token = self.bearer_token.strip()
            if not token.lower().startswith("bearer "):
                token = f"Bearer {token}"
            self.session.headers["x-api-authorization"] = token
            self.is_authenticated = True

    def refresh_access_token(self) -> bool:
        """Exchanges long-lived OAuth refresh token for a fresh short-lived access token."""
        if not self.refresh_token or len(self.refresh_token.strip()) < 10:
            return False
        url = "https://account.premierleague.com/as/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token.strip(),
            "client_id": "bfcbaf69-aade-4c1b-8f00-c1cb8a193030"
        }
        try:
            res = requests.post(url, data=payload, timeout=15)
            if res.status_code == 200:
                data = res.json()
                new_token = data.get("access_token")
                if new_token:
                    self.bearer_token = new_token
                    self.session.headers["x-api-authorization"] = f"Bearer {new_token}"
                    self.is_authenticated = True
                    if "refresh_token" in data:
                        self.refresh_token = data["refresh_token"]
                    logger.info("FPL access token refreshed successfully via OAuth refresh token.")
                    return True
        except Exception as e:
            logger.warning(f"Failed to refresh FPL access token: {e}")
        return False

    def login(self) -> bool:
        if self.bearer_token and len(self.bearer_token.strip()) > 10:
            self.is_authenticated = True
            logger.info("FPL Bearer token configured and active.")
            return True
        if self.refresh_token and len(self.refresh_token.strip()) > 10:
            if self.refresh_access_token():
                return True
        if self.email and self.password:
            self.is_authenticated = True
            logger.info("Autonomous FPL Playwright credentials ready.")
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

    def get_my_team(self, team_id: int, require_authenticated: bool = False) -> Dict[str, Any]:
        if not team_id:
            raise ValueError("FPL_TEAM_ID must be provided.")

        history = self.get_history_and_chips(team_id)

        if self.is_authenticated:
            try:
                url = f"{config.fpl_my_team_url}/{team_id}/"
                res = self.session.get(url, headers={"Cache-Control": "no-cache"}, timeout=15)
                if res.status_code == 200:
                    data = res.json()
                    transfers_info = data.get("transfers", {})
                    limit = transfers_info.get("limit", 1)
                    made = transfers_info.get("made", 0)
                    return {
                        "is_authenticated": True,
                        "is_live": True,
                        "picks": data.get("picks", []),
                        "chips_available": history.get("chips_available", {}),
                        "bank": transfers_info.get("bank", 0) / 10.0,
                        "free_transfers": max(1, min(5, limit - made)),
                        "rank": history.get("overall_rank"),
                        "total_points": history.get("total_points", 0),
                        "team_value": history.get("team_value", 100.0),
                    }
                else:
                    msg = f"Failed to fetch live /my-team/ (HTTP {res.status_code}). Session or Bearer token may be invalid/expired."
                    if require_authenticated:
                        raise PermissionError(msg)
                    logger.warning(f"{msg} Falling back to public endpoints.")
            except Exception as e:
                if require_authenticated:
                    raise PermissionError(f"Authentication failure accessing live FPL team {team_id}: {e}") from e
                logger.warning(f"Failed to fetch /my-team/: {e}. Falling back to public endpoints.")
        elif require_authenticated:
            raise PermissionError(
                f"Authentication required for live operation on team {team_id}. "
                "FPL_BEARER_TOKEN or active session is missing."
            )

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
            import json
            if baseline_file.exists():
                try:
                    with open(baseline_file, "r", encoding="utf-8") as f:
                        picks = json.load(f)
                except Exception:
                    pass

        bank_val = entry_data.get("last_deadline_bank")
        bank = (float(bank_val) if bank_val is not None else 12.0) / 10.0
        val_val = entry_data.get("last_deadline_value")
        team_val = (float(val_val) if val_val is not None else 1000.0) / 10.0

        return {
            "is_authenticated": False,
            "is_live": False,
            "picks": picks,
            "chips_available": history.get("chips_available", {}),
            "bank": bank,
            "free_transfers": 1,
            "rank": entry_data.get("summary_overall_rank") or history.get("overall_rank"),
            "total_points": entry_data.get("summary_overall_points", 0),
            "team_value": team_val,
            "leagues": (entry_data.get("leagues", {}).get("classic", []) or []) + (entry_data.get("leagues", {}).get("h2h", []) or []),
            "manager_name": f"{entry_data.get('player_first_name', '')} {entry_data.get('player_last_name', '')}".strip(),
            "team_name": entry_data.get("name", "FPL Squad")
        }

    def set_lineup(self, team_id: int, picks_payload: List[Dict[str, Any]], chip: Optional[str] = None) -> Dict[str, Any]:
        payload = {"chip": chip, "picks": picks_payload}
        if self.dry_run:
            logger.info("[DRY RUN] Lineup submission simulated.")
            return {"status": "simulated", "success": True, "dry_run": True, "payload": payload}

        # 1. Try direct API via Bearer Token if present
        if "x-api-authorization" in self.session.headers:
            headers = {"Content-Type": "application/json; charset=UTF-8", "X-Requested-With": "XMLHttpRequest"}
            try:
                res = self.session.post(f"{config.fpl_my_team_url}/{team_id}/", json=payload, headers=headers, timeout=15)
                if res.status_code in (200, 201):
                    logger.info("Lineup updated successfully via Bearer token API.")
                    return {"status": "success", "success": True, "code": res.status_code}
                else:
                    err = f"Bearer token lineup update rejected by FPL (HTTP {res.status_code}): {res.text[:200]}"
                    logger.warning(err)
                    return {"status": "error", "success": False, "code": res.status_code, "error": err}
            except Exception as e:
                logger.warning(f"Bearer token lineup update failed: {e}. Falling back to browser...")

        # 2. Browser Playwright autonomous execution
        if self.email and self.password:
            try:
                pw_res = PlaywrightFPLAuthenticator(self.email, self.password).submit_lineup_live(team_id, picks_payload, chip)
                pw_res["success"] = (pw_res.get("status") == "success")
                return pw_res
            except Exception as e:
                err = f"Playwright lineup execution failed: {e}"
                logger.error(err)
                return {"status": "error", "success": False, "error": err}

        return {
            "status": "error",
            "success": False,
            "error": "No valid authentication method (FPL_BEARER_TOKEN or Playwright credentials) configured for live lineup submission."
        }

    def make_transfers(self, team_id: int, transfers: List[Transfer], next_gw: int, chip: Optional[str] = None) -> Dict[str, Any]:
        if not transfers:
            return {"status": "noop", "success": True, "message": "No transfers to execute."}
        payload = {
            "confirmed": True, "entry": team_id, "event": next_gw,
            "transfers": [{"element_in": t.player_in.id, "element_out": t.player_out.id,
                           "purchase_price": t.player_in.now_cost,
                           "selling_price": t.player_out.selling_price or t.player_out.now_cost} for t in transfers],
            "wildcard": (chip == "wildcard"), "freehit": (chip == "freehit")
        }
        if self.dry_run:
            logger.info(f"[DRY RUN] Transfers simulated for {len(transfers)} player(s).")
            return {"status": "simulated", "success": True, "dry_run": True, "payload": payload}

        # 1. Try direct API via Bearer Token if present
        if "x-api-authorization" in self.session.headers:
            headers = {"Content-Type": "application/json; charset=UTF-8", "X-Requested-With": "XMLHttpRequest"}
            try:
                res = self.session.post(config.fpl_transfers_url, json=payload, headers=headers, timeout=15)
                if res.status_code in (200, 201):
                    logger.info("Transfers executed successfully via Bearer token API.")
                    return {"status": "success", "success": True, "code": res.status_code}
                else:
                    err = f"Bearer token transfer execution rejected by FPL (HTTP {res.status_code}): {res.text[:200]}"
                    logger.warning(err)
                    return {"status": "error", "success": False, "code": res.status_code, "error": err}
            except Exception as e:
                logger.warning(f"Bearer token transfer execution failed: {e}. Falling back to browser...")

        # 2. Browser Playwright autonomous execution
        if self.email and self.password:
            try:
                pw_res = PlaywrightFPLAuthenticator(self.email, self.password).submit_transfers_live(team_id, payload)
                pw_res["success"] = (pw_res.get("status") == "success")
                return pw_res
            except Exception as e:
                err = f"Playwright transfer execution failed: {e}"
                logger.error(err)
                return {"status": "error", "success": False, "error": err}

        return {
            "status": "error",
            "success": False,
            "error": "No valid authentication method (FPL_BEARER_TOKEN or Playwright credentials) configured for live transfer execution."
        }

    def verify_live_squad(
        self,
        team_id: int,
        expected_captain_id: Optional[int] = None,
        expected_starter_ids: Optional[List[int]] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Queries the live /my-team/ endpoint to verify that submitted changes
        actually took effect on FPL servers.
        """
        if self.dry_run:
            return True, {"verified": True, "dry_run": True}

        if not self.is_authenticated:
            return False, {"verified": False, "error": "Cannot verify live squad: Client not authenticated."}

        try:
            url = f"{config.fpl_my_team_url}/{team_id}/"
            res = self.session.get(url, headers={"Cache-Control": "no-cache"}, timeout=15)
            if res.status_code != 200:
                return False, {"verified": False, "error": f"HTTP {res.status_code} fetching live /my-team/"}

            data = res.json()
            picks = data.get("picks", [])
            live_cap = next((p["element"] for p in picks if p.get("is_captain")), None)
            live_starters = [p["element"] for p in picks[:11]]

            details: Dict[str, Any] = {
                "live_captain_id": live_cap,
                "expected_captain_id": expected_captain_id,
                "live_starters_count": len(live_starters)
            }

            if expected_captain_id and live_cap != expected_captain_id:
                details["error"] = f"Captain mismatch on FPL server: Server has {live_cap}, expected {expected_captain_id}"
                return False, details

            if expected_starter_ids:
                missing = set(expected_starter_ids) - set(live_starters)
                if missing:
                    details["error"] = f"Starters mismatch on FPL server: Missing expected starters: {missing}"
                    return False, details

            details["verified"] = True
            return True, details
        except Exception as e:
            return False, {"verified": False, "error": str(e)}

