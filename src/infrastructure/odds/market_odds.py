import json
import math
import time
import unicodedata
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests

from ...config import config

logger = logging.getLogger("MarketOddsService")

# Mapping common Odds API club names -> canonical normalized FPL short names or team names
TEAM_NAME_ALIASES: Dict[str, str] = {
    "arsenal": "ARS",
    "aston villa": "AVL",
    "bournemouth": "BOU",
    "afc bournemouth": "BOU",
    "brentford": "BRE",
    "brighton and hove albion": "BHA",
    "brighton": "BHA",
    "burnley": "BUR",
    "chelsea": "CHE",
    "coventry city": "COV",
    "coventry": "COV",
    "crystal palace": "CRY",
    "everton": "EVE",
    "fulham": "FUL",
    "hull city": "HUL",
    "hull": "HUL",
    "ipswich town": "IPS",
    "ipswich": "IPS",
    "leeds united": "LEE",
    "leeds": "LEE",
    "leicester city": "LEI",
    "leicester": "LEI",
    "liverpool": "LIV",
    "manchester city": "MCI",
    "man city": "MCI",
    "manchester united": "MUN",
    "man utd": "MUN",
    "newcastle united": "NEW",
    "newcastle": "NEW",
    "nottingham forest": "NFO",
    "nott'm forest": "NFO",
    "southampton": "SOU",
    "sunderland": "SUN",
    "tottenham hotspur": "TOT",
    "tottenham": "TOT",
    "west ham united": "WHU",
    "west ham": "WHU",
    "wolverhampton wanderers": "WOL",
    "wolves": "WOL",
}


def _norm_text(s: str) -> str:
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    ascii_s = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(ascii_s.lower().replace("-", " ").replace("'", "").split())


def _canonical_team(name: str) -> str:
    norm = _norm_text(name)
    if norm in TEAM_NAME_ALIASES:
        return TEAM_NAME_ALIASES[norm]
    for alias, short in TEAM_NAME_ALIASES.items():
        if alias in norm or norm in alias:
            return short
    return norm[:3].upper()


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.exp(-lam) * (lam ** k)) / math.factorial(k)


def _solve_match_lambdas_from_odds(
    p_home: float,
    p_draw: float,
    p_away: float,
    total_goals: float = 2.65,
) -> Tuple[float, float]:
    """Inverts (p_home, p_draw, p_away, total_goals) into Poisson expected goals (lam_h, lam_a)."""
    best_err = 1e9
    best_pair = (total_goals * 0.54, total_goals * 0.46)

    # Search share of total_goals going to home team (0.15 .. 0.85) in 1% steps
    for step in range(15, 86):
        share = step / 100.0
        lh = max(0.25, total_goals * share)
        la = max(0.25, total_goals * (1.0 - share))

        h_pmf = [_poisson_pmf(i, lh) for i in range(8)]
        a_pmf = [_poisson_pmf(j, la) for j in range(8)]

        ph = pd = pa = 0.0
        for i in range(8):
            for j in range(8):
                prob = h_pmf[i] * a_pmf[j]
                if i > j:
                    ph += prob
                elif i == j:
                    pd += prob
                else:
                    pa += prob

        err = (ph - p_home) ** 2 + (pd - p_draw) ** 2 + (pa - p_away) ** 2
        if err < best_err:
            best_err = err
            best_pair = (lh, la)

    return round(best_pair[0], 3), round(best_pair[1], 3)


class MarketOddsService:
    """Fetches & caches sharp bookmaker odds from The Odds API:
    1. Match Odds (h2h + totals) -> Market Implied Team Goals (lam_h, lam_a) & Clean Sheet %
    2. Player Props (player_goal_scorer_anytime) -> Exact Market Implied Goal Probabilities per player
    """

    BASE_URL = "https://api.the-odds-api.com/v4/sports/soccer_epl"
    CACHE_TTL_SECONDS = 6 * 3600  # 6 hours cache -> protects free 500 credits/month quota

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_path: Optional[Path] = None,
        enable_player_props: bool = True,
    ):
        self.api_key = api_key if api_key is not None else config.odds_api_key
        self.cache_path = cache_path or (config.data_cache_dir / "odds_cache.json")
        self.enable_player_props = enable_player_props
        # (home_short, away_short) -> {"lam_h": float, "lam_a": float, "p_home": float, ...}
        self.match_odds: Dict[Tuple[str, str], Dict[str, float]] = {}
        # normalized_player_name -> {"team_hint": set, "p_score": float, "lam_goals": float, "raw_name": str}
        self.player_scorer_odds: Dict[str, Dict] = {}

    def _load_cache(self) -> Optional[Dict]:
        if not self.cache_path.exists():
            return None
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            ts = data.get("fetched_at", 0)
            if (time.time() - ts) < self.CACHE_TTL_SECONDS:
                return data
        except Exception:
            pass
        return None

    def _save_cache(self, payload: Dict) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug(f"Could not save odds cache: {e}")

    def load_odds(self, force_refresh: bool = False) -> bool:
        """Loads match odds and next-GW anytime goalscorer odds (from cache or live API)."""
        if not self.api_key or len(self.api_key.strip()) < 10:
            logger.info("ODDS_API_KEY not configured; using pure Dixon-Coles TeamStrengthModel.")
            return False

        cached = None if force_refresh else self._load_cache()
        if cached:
            self._hydrate_from_payload(cached)
            logger.info(
                f"Loaded cached Market Odds: {len(self.match_odds)} matches, "
                f"{len(self.player_scorer_odds)} player scorer props."
            )
            return True

        try:
            url = f"{self.BASE_URL}/odds/"
            params = {
                "apiKey": self.api_key.strip(),
                "regions": "uk",
                "markets": "h2h,totals",
                "oddsFormat": "decimal",
            }
            res = requests.get(url, params=params, timeout=15)
            if res.status_code != 200:
                logger.warning(f"The Odds API match fetch failed (HTTP {res.status_code}): {res.text[:150]}")
                return False

            events = res.json()
            rem = res.headers.get("x-requests-remaining", "?")
            logger.info(f"Fetched {len(events)} EPL match odds from The Odds API (Credits remaining: {rem}).")

            parsed_matches: List[Dict] = []
            parsed_scorers: Dict[str, Dict] = {}

            now_utc = datetime.now(timezone.utc)
            next_gw_cutoff = now_utc + timedelta(days=5)

            for ev in events:
                home_short = _canonical_team(ev.get("home_team", ""))
                away_short = _canonical_team(ev.get("away_team", ""))
                m_stats = self._extract_match_implied(ev)
                if m_stats:
                    m_stats["home_short"] = home_short
                    m_stats["away_short"] = away_short
                    m_stats["event_id"] = ev.get("id")
                    m_stats["commence_time"] = ev.get("commence_time")
                    parsed_matches.append(m_stats)

                # Fetch player_goal_scorer_anytime ONLY for upcoming GW matches (within 5 days, max 10 calls)
                if self.enable_player_props and ev.get("id") and ev.get("commence_time"):
                    try:
                        ct = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
                        if now_utc - timedelta(hours=1) <= ct <= next_gw_cutoff:
                            self._fetch_event_player_scorers(ev["id"], home_short, away_short, parsed_scorers)
                    except Exception:
                        pass

            payload = {
                "fetched_at": time.time(),
                "matches": parsed_matches,
                "scorers": parsed_scorers,
            }
            self._save_cache(payload)
            self._hydrate_from_payload(payload)
            logger.info(
                f"Hydrated live Market Odds: {len(self.match_odds)} matches, "
                f"{len(self.player_scorer_odds)} anytime goalscorers."
            )
            return True
        except Exception as e:
            logger.warning(f"MarketOddsService error: {e}")
            return False

    def _extract_match_implied(self, ev: Dict) -> Optional[Dict[str, float]]:
        home_name = ev.get("home_team", "")
        away_name = ev.get("away_team", "")
        h_probs, d_probs, a_probs = [], [], []
        over25_probs = []

        for bm in ev.get("bookmakers", []):
            for mk in bm.get("markets", []):
                if mk.get("key") == "h2h":
                    prices = {o["name"]: float(o["price"]) for o in mk.get("outcomes", []) if float(o.get("price", 0)) > 1.0}
                    if home_name in prices and away_name in prices and "Draw" in prices:
                        ih, idr, ia = 1.0 / prices[home_name], 1.0 / prices["Draw"], 1.0 / prices[away_name]
                        s = ih + idr + ia
                        h_probs.append(ih / s)
                        d_probs.append(idr / s)
                        a_probs.append(ia / s)
                elif mk.get("key") == "totals":
                    # Look for 2.5 goal line
                    over_p = under_p = None
                    for o in mk.get("outcomes", []):
                        if abs(float(o.get("point", 0)) - 2.5) < 0.05 and float(o.get("price", 0)) > 1.0:
                            if o.get("name") == "Over":
                                over_p = 1.0 / float(o["price"])
                            elif o.get("name") == "Under":
                                under_p = 1.0 / float(o["price"])
                    if over_p and under_p:
                        over25_probs.append(over_p / (over_p + under_p))

        if not h_probs:
            return None

        p_h = sum(h_probs) / len(h_probs)
        p_d = sum(d_probs) / len(d_probs)
        p_a = sum(a_probs) / len(a_probs)

        # Infer total expected goals from Over 2.5 probability (Poisson: P(X<=2) = e^-L (1 + L + L^2/2))
        total_goals = 2.65
        if over25_probs:
            p_over = sum(over25_probs) / len(over25_probs)
            p_under = max(0.05, min(0.95, 1.0 - p_over))
            # Binary search total_goals in [1.2, 4.8]
            lo, hi = 1.2, 4.8
            for _ in range(25):
                mid = (lo + hi) / 2.0
                pu = math.exp(-mid) * (1.0 + mid + (mid ** 2) / 2.0)
                if pu > p_under:
                    lo = mid
                else:
                    hi = mid
            total_goals = (lo + hi) / 2.0

        lam_h, lam_a = _solve_match_lambdas_from_odds(p_h, p_d, p_a, total_goals)
        return {
            "p_home": round(p_h, 4),
            "p_draw": round(p_d, 4),
            "p_away": round(p_a, 4),
            "total_goals": round(total_goals, 3),
            "lam_h": lam_h,
            "lam_a": lam_a,
        }

    def _fetch_event_player_scorers(
        self,
        event_id: str,
        home_short: str,
        away_short: str,
        out_scorers: Dict[str, Dict],
    ) -> None:
        url = f"{self.BASE_URL}/events/{event_id}/odds"
        params = {
            "apiKey": self.api_key.strip(),
            "regions": "uk",
            "markets": "player_goal_scorer_anytime",
            "oddsFormat": "decimal",
        }
        res = requests.get(url, params=params, timeout=12)
        if res.status_code != 200:
            return

        data = res.json()
        raw_probs: Dict[str, List[float]] = {}
        raw_names: Dict[str, str] = {}
        for bm in data.get("bookmakers", []):
            for mk in bm.get("markets", []):
                if mk.get("key") != "player_goal_scorer_anytime":
                    continue
                for o in mk.get("outcomes", []):
                    if o.get("name") == "Yes" and o.get("description") and float(o.get("price", 0)) > 1.01:
                        norm = _norm_text(o["description"])
                        # Vig discount (~10% standard margin on anytime goalscorer markets)
                        implied = (1.0 / float(o["price"])) * 0.90
                        raw_probs.setdefault(norm, []).append(min(0.85, max(0.01, implied)))
                        raw_names[norm] = o["description"]

        for norm, probs in raw_probs.items():
            p_score = sum(probs) / len(probs)
            lam_g = -math.log(max(0.05, 1.0 - p_score))
            out_scorers[norm] = {
                "raw_name": raw_names[norm],
                "match_teams": [home_short, away_short],
                "p_score": round(p_score, 4),
                "lam_goals": round(lam_g, 4),
            }

    def _hydrate_from_payload(self, payload: Dict) -> None:
        self.match_odds = {}
        for m in payload.get("matches", []):
            key = (m["home_short"], m["away_short"])
            self.match_odds[key] = m
        self.player_scorer_odds = payload.get("scorers", {})

    def get_match_lambdas(self, team_short: str, opponent_short: str, is_home: bool) -> Optional[Tuple[float, float]]:
        t = team_short.upper()
        o = opponent_short.upper()
        if is_home:
            m = self.match_odds.get((t, o))
            return (m["lam_h"], m["lam_a"]) if m else None
        else:
            m = self.match_odds.get((o, t))
            return (m["lam_a"], m["lam_h"]) if m else None

    def get_player_scorer_lambda(self, full_name: str, web_name: str, team_short: str) -> Optional[Tuple[float, float]]:
        """Matches an FPL player to market Anytime Goalscorer odds.
        Returns (p_score, lam_goals) if matched cleanly within the player's match.
        """
        if not self.player_scorer_odds:
            return None

        t = team_short.upper()
        n_full = _norm_text(full_name)
        n_web = _norm_text(web_name)

        # 1. Exact normalized match
        for cand in (n_full, n_web):
            if cand in self.player_scorer_odds:
                rec = self.player_scorer_odds[cand]
                if t in rec.get("match_teams", []):
                    return rec["p_score"], rec["lam_goals"]

        # 2. Token subset match restricted to players in the exact same match
        web_tokens = [tok for tok in n_web.split() if len(tok) >= 3]
        full_tokens = [tok for tok in n_full.split() if len(tok) >= 3]
        if not web_tokens and not full_tokens:
            return None

        for norm_k, rec in self.player_scorer_odds.items():
            if t not in rec.get("match_teams", []):
                continue
            k_tokens = set(norm_k.split())
            if web_tokens and all(tok in k_tokens for tok in web_tokens):
                return rec["p_score"], rec["lam_goals"]
            if len(full_tokens) >= 2 and full_tokens[0] in k_tokens and full_tokens[-1] in k_tokens:
                return rec["p_score"], rec["lam_goals"]

        return None
