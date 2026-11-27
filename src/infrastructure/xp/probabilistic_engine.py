import math
import logging
from typing import List, Dict, Optional

from ...domain.interfaces.xp_engine import IXPEngine
from ...domain.models.player import Player
from ...domain.models.fixture import Fixture
from .rule_engine import RuleBasedXPEngine
from .team_strength import TeamStrengthModel
from ..odds.market_odds import MarketOddsService

logger = logging.getLogger("ProbabilisticXPEngine")

GOAL_POINTS = {"GK": 6.0, "DEF": 6.0, "MID": 5.0, "FWD": 4.0}
CS_POINTS = {"GK": 4.0, "DEF": 4.0, "MID": 1.0, "FWD": 0.0}


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0.0:
        return 1.0 if k == 0 else 0.0
    return (math.exp(-lam) * (lam ** k)) / math.factorial(k)


def _poisson_tail(threshold: int, lam: float) -> float:
    """P(X >= threshold) for X ~ Poisson(lam)."""
    if lam <= 0.0:
        return 0.0
    cdf = sum(_poisson_pmf(k, lam) for k in range(threshold))
    return max(0.0, min(1.0, 1.0 - cdf))


def _expected_conceded_penalty(lam_against: float) -> float:
    """Expected FPL goals-conceded penalty (-1 pt per 2 goals conceded) for GK/DEF."""
    pen = 0.0
    for k in range(2, 11):
        pen += (k // 2) * _poisson_pmf(k, lam_against)
    return pen


def _expected_saves_points(lam_saves: float) -> float:
    """Expected FPL save points (+1 pt per 3 saves) for GK."""
    pts = 0.0
    for s in range(3, 16):
        pts += (s // 3) * _poisson_pmf(s, lam_saves)
    return pts


class ProbabilisticXPEngine(IXPEngine):
    """Pro-grade Probabilistic Poisson / Dixon-Coles xP Engine.

    Combines:
    1. Official Opta per-90 telemetry from FPL API (xG/90, xA/90, xGC/90, saves/90, DefCon/90, BPS, penalties_order)
    2. Self-calibrating Dixon-Coles TeamStrengthModel (replaces static FPL FDR)
    3. Sharp Market Odds via The Odds API (h2h/totals implied team goals + Anytime Goalscorer Player Props)
    4. Exact FPL Poisson scoring (Appearance, Goals, Assists, CS, Conceded, Saves, DefCon +2, Bonus, Cards)
    5. Press Conference NLP availability adjustments
    """

    def __init__(
        self,
        team_strength: Optional[TeamStrengthModel] = None,
        market_odds: Optional[MarketOddsService] = None,
        raw_fixtures: Optional[List[Dict]] = None,
        use_market_odds: bool = True,
    ):
        self.team_strength = team_strength or TeamStrengthModel()
        self.raw_fixtures = raw_fixtures
        self._fitted = bool(self.team_strength.ratings)
        self.market_odds = market_odds
        self.use_market_odds = use_market_odds
        self._odds_loaded = False

    def _ensure_models_ready(self, players: List[Player]) -> None:
        if not self._fitted:
            fixtures_data = self.raw_fixtures
            if fixtures_data is None:
                try:
                    from ..fpl.repository import FPLDataRepository
                    fixtures_data = FPLDataRepository().get_fixtures()
                except Exception as e:
                    logger.debug(f"Could not auto-load fixtures for TeamStrengthModel: {e}")
                    fixtures_data = []
            if fixtures_data:
                self.team_strength.fit(fixtures_data, players)
            self._fitted = True

        if self.use_market_odds and not self._odds_loaded:
            if self.market_odds is None:
                self.market_odds = MarketOddsService()
            self.market_odds.load_odds()
            self._odds_loaded = True

    @staticmethod
    def calculate_expected_minutes(player: Player, nlp_insight: Optional[Dict] = None) -> float:
        """Uses RuleBasedXPEngine's proven availability & NLP logic enhanced with starts_per_90."""
        base = RuleBasedXPEngine.calculate_expected_minutes(player, nlp_insight)
        if base <= 0.0:
            return 0.0
        # Refine with starts_per_90 if available
        starts_90 = getattr(player, "starts_per_90", 0.0)
        if player.position != "GK" and player.minutes >= 180 and starts_90 > 0:
            # High start rate (>=0.85) confirms nailed starter; low (<0.5) caps expected minutes
            if starts_90 >= 0.90 and base >= 80.0:
                base = min(90.0, base + 2.0)
            elif starts_90 < 0.45 and base > 45.0:
                base *= 0.72
        return round(max(0.0, min(90.0, base)), 1)

    def _get_blended_match_lambdas(self, player: Player, fix: Fixture) -> tuple:
        """Blends 60% Market Implied Odds + 40% Dixon-Coles TeamStrength (or 100% Dixon-Coles)."""
        dc_for, dc_against = self.team_strength.predict_match_lambdas(
            team_id=player.team_id,
            opponent_id=fix.opponent_id,
            is_home=fix.is_home,
            fdr_fallback=fix.difficulty,
        )
        if self.market_odds and self.market_odds.match_odds:
            mkt = self.market_odds.get_match_lambdas(player.team_short, fix.opponent_name, fix.is_home)
            if mkt:
                lam_for = 0.60 * mkt[0] + 0.40 * dc_for
                lam_ag = 0.60 * mkt[1] + 0.40 * dc_against
                return round(lam_for, 3), round(lam_ag, 3)
        return dc_for, dc_against

    def calculate_player_xp(
        self,
        player: Player,
        fixtures: List[Fixture],
        nlp_insight: Optional[Dict] = None,
        is_next_gw: bool = True,
    ) -> float:
        insight = nlp_insight or getattr(player, "press_insight", None)
        exp_mins = self.calculate_expected_minutes(player, insight)
        player.expected_minutes = exp_mins

        if exp_mins <= 0.0 or not fixtures:
            return 0.0

        pos = player.position
        min_frac = exp_mins / 90.0

        # Probability of playing >=60 minutes vs cameo (1-59 mins)
        if exp_mins >= 72.0:
            p_60 = min(0.96, exp_mins / 88.0)
            p_play = min(0.99, p_60 + 0.04)
        elif exp_mins >= 45.0:
            p_60 = (exp_mins - 20.0) / 70.0
            p_play = min(0.92, exp_mins / 60.0)
        else:
            p_60 = max(0.0, (exp_mins - 25.0) / 90.0)
            p_play = min(0.85, exp_mins / 35.0)

        # Appearance points: +1 for playing, +1 extra for >=60 mins
        app_pts = p_play * 1.0 + p_60 * 1.0

        # Bayesian-shrunk Opta xG/90 and xA/90
        mins = max(0, player.minutes)
        w_sample = min(1.0, mins / 540.0)  # Full weight after ~6 full matches
        prior_xg90 = {"GK": 0.0, "DEF": 0.05, "MID": max(0.08, (player.cost - 4.0) * 0.065), "FWD": max(0.22, (player.cost - 4.0) * 0.095)}.get(pos, 0.10)
        prior_xa90 = {"GK": 0.005, "DEF": 0.06, "MID": max(0.08, (player.cost - 4.0) * 0.055), "FWD": 0.12}.get(pos, 0.08)

        raw_xg90 = getattr(player, "expected_goals_per_90", 0.0) or ((player.expected_goals / mins * 90.0) if mins >= 60 else 0.0)
        raw_xa90 = getattr(player, "expected_assists_per_90", 0.0) or ((player.expected_assists / mins * 90.0) if mins >= 60 else 0.0)

        xg90 = w_sample * raw_xg90 + (1.0 - w_sample) * prior_xg90
        xa90 = w_sample * raw_xa90 + (1.0 - w_sample) * prior_xa90

        team_avg_xg = max(0.85, self.team_strength.get_team_avg_xg(player.team_id))

        # Check Market Anytime Goalscorer Odds (next GW only)
        mkt_scorer = None
        if is_next_gw and self.market_odds and self.market_odds.player_scorer_odds and pos != "GK":
            mkt_scorer = self.market_odds.get_player_scorer_lambda(player.full_name, player.name, player.team_short)
            if mkt_scorer:
                player.market_scorer_prob = mkt_scorer[0]

        gw_xp_sum = 0.0
        last_cs_prob = 0.0
        last_team_xg = 0.0
        last_defcon_pts = 0.0

        for fix in fixtures:
            lam_for, lam_against = self._get_blended_match_lambdas(player, fix)
            last_team_xg = lam_for

            # Match attack scaling factor relative to team's season baseline
            att_scale = max(0.55, min(1.75, lam_for / team_avg_xg))

            # 1. Expected Goals
            opta_match_xg = xg90 * att_scale * min_frac
            # Explicit penalty taker boost if not already priced by market scorer odds
            if getattr(player, "penalties_order", None) == 1 and not mkt_scorer:
                opta_match_xg += 0.09 * min_frac

            if mkt_scorer and len(fixtures) == 1:
                # Blend 55% Sharp Market Anytime Scorer + 45% Opta model (scaled by availability)
                mkt_lam = mkt_scorer[1] * (min_frac if exp_mins < 65.0 else 1.0)
                match_xg = 0.55 * mkt_lam + 0.45 * opta_match_xg
            else:
                match_xg = opta_match_xg

            goal_pts = match_xg * GOAL_POINTS.get(pos, 4.0)

            # 2. Expected Assists (with set-piece taker bonus)
            match_xa = xa90 * att_scale * min_frac
            if getattr(player, "corners_order", None) == 1 or getattr(player, "freekicks_order", None) == 1:
                match_xa += 0.05 * min_frac
            assist_pts = match_xa * 3.0

            # 3. Clean Sheet & Goals Conceded Penalty (Poisson + mild Dixon-Coles low-score uplift)
            cs_prob = min(0.75, math.exp(-lam_against) * 1.03)
            last_cs_prob = cs_prob
            cs_pts = p_60 * cs_prob * CS_POINTS.get(pos, 0.0)
            conceded_pen = p_60 * _expected_conceded_penalty(lam_against) if pos in ("GK", "DEF") else 0.0

            # 4. GK Save Points (Exact Poisson E[floor(Saves/3)])
            save_pts = 0.0
            if pos == "GK":
                base_saves90 = getattr(player, "saves_per_90", 0.0) or ((getattr(player, "saves", 0) / mins * 90.0) if mins >= 90 else 2.8)
                opp_threat_scale = max(0.65, min(1.55, lam_against / 1.30))
                lam_saves = base_saves90 * opp_threat_scale * min_frac
                save_pts = _expected_saves_points(lam_saves)

            # 5. Defensive Contribution Points (+2 pts for DEF >=10 CBIT, MID/FWD >=12 CBIRT)
            defcon_pts = 0.0
            defcon_90 = getattr(player, "defensive_contribution_per_90", 0.0)
            if pos != "GK" and defcon_90 > 0 and mins >= 90:
                # Defending teams facing stronger attacks accrue slightly more clearances/interceptions
                def_activity_scale = max(0.85, min(1.25, lam_against / 1.30))
                lam_defcon = defcon_90 * def_activity_scale * min_frac
                thresh = 10 if pos == "DEF" else 12
                defcon_pts = 2.0 * _poisson_tail(thresh, lam_defcon)
            last_defcon_pts = defcon_pts

            # 6. Expected Bonus Points (calibrated from BPS/90 + match attacking/defensive returns)
            bps_90 = (getattr(player, "bps", 0) / mins * 90.0) if mins >= 90 else 14.0
            bonus_pts = min(1.6, max(0.0, (bps_90 - 12.0) * 0.025 + match_xg * 0.65 + match_xa * 0.35 + (cs_prob * 0.30 if pos in ("GK", "DEF") else 0.0))) * min_frac

            # 7. Expected Cards Penalty
            starts_cnt = max(1, getattr(player, "starts", 0) or (mins // 90) or 1)
            yc_rate = min(0.45, getattr(player, "yellow_cards", 0) / starts_cnt)
            card_pen = yc_rate * 1.0 * p_play

            # 8. Subtle Form calibration (10% nudge to capture hot/cold streaks without chasing noise)
            raw_match_xp = app_pts + goal_pts + assist_pts + cs_pts - conceded_pen + save_pts + defcon_pts + bonus_pts - card_pen
            if player.form > 0 and mins >= 180:
                form_nudge = max(-0.45, min(0.55, (player.form - raw_match_xp) * 0.12))
                raw_match_xp += form_nudge

            gw_xp_sum += max(0.0, raw_match_xp)

        if is_next_gw:
            player.expected_cs_prob = round(last_cs_prob, 3)
            player.expected_team_goals = round(last_team_xg, 2)
            player.expected_defcon_pts = round(last_defcon_pts, 2)

        return round(max(0.0, gw_xp_sum), 2)

    def enrich_players_with_horizon_xp(
        self,
        players: List[Player],
        team_fixtures: Dict[int, List[Fixture]],
        next_gw: int,
        weeks_ahead: int = 3,
        decay: float = 0.85,
        nlp_insights: Optional[Dict[int, Dict]] = None,
    ) -> List[Player]:
        self._ensure_models_ready(players)

        for p in players:
            if nlp_insights and p.id in nlp_insights:
                p.press_insight = nlp_insights[p.id]

            t_fix = team_fixtures.get(p.team_id, [])
            gw_map: Dict[int, List[Fixture]] = {}
            for fix in t_fix:
                gw_map.setdefault(fix.event, []).append(fix)

            # Next GW exact xP (with Market Anytime Scorer Odds)
            next_gw_fix = gw_map.get(next_gw, [])
            p.xp = self.calculate_player_xp(p, next_gw_fix, nlp_insight=p.press_insight, is_next_gw=True)
            if next_gw_fix:
                f0 = next_gw_fix[0]
                p.next_fixture = f"{f0.opponent_name} ({'H' if f0.is_home else 'A'}) [FDR {f0.difficulty}]"
                p.next_opponent_short = f0.opponent_name.upper()
                p.next_is_home = f0.is_home
                p.next_fdr = f0.difficulty
            else:
                p.next_fixture = "BLANK"
                p.next_opponent_short = ""
                p.next_is_home = False
                p.next_fdr = 5

            # Multi-GW decayed horizon xP
            horizon_sum = 0.0
            fix_labels = []
            for offset in range(weeks_ahead):
                gw = next_gw + offset
                gw_fix = gw_map.get(gw, [])
                gw_xp = p.xp if offset == 0 else self.calculate_player_xp(p, gw_fix, nlp_insight=p.press_insight, is_next_gw=False)
                horizon_sum += gw_xp * (decay ** offset)
                if gw_fix:
                    fg = gw_fix[0]
                    fix_labels.append(f"{fg.opponent_name} ({'H' if fg.is_home else 'A'}) [{fg.difficulty}]")
                else:
                    fix_labels.append("BLANK")

            p.horizon_xp = round(horizon_sum, 2)
            p.horizon_fixtures = " | ".join(fix_labels)

            # 5-GW fixture run for Dashboard
            fixtures_5gw = []
            for offset in range(5):
                gw = next_gw + offset
                gw_fix = gw_map.get(gw, [])
                if gw_fix:
                    for f in gw_fix:
                        fixtures_5gw.append({
                            "gw": gw,
                            "opponent": f.opponent_name,
                            "is_home": f.is_home,
                            "fdr": f.difficulty,
                        })
                else:
                    fixtures_5gw.append({"gw": gw, "opponent": "-", "is_home": True, "fdr": 3})
            p.fixtures_5gw = fixtures_5gw

            p.is_differential = (p.selected_by_percent < 12.0 and p.horizon_xp >= 14.0)
            p.is_flop_risk = (p.selected_by_percent > 20.0 and p.form < 3.0 and p.xp < 4.0)

        return players
