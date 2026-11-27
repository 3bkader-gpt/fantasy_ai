import math
import logging
from typing import Dict, List, Tuple, Optional
from ...domain.models.player import Player

logger = logging.getLogger("TeamStrengthModel")


class TeamStrengthModel:
    """Self-calibrating Dixon-Coles / Time-Decayed Attack & Defense Strength model
    built directly from finished Premier League fixtures and Opta team xG/xGC telemetry.
    Replaces static FPL FDR with continuous expected goal rates (lambda_for, lambda_against).
    """

    LEAGUE_AVG_HOME_GOALS = 1.48
    LEAGUE_AVG_AWAY_GOALS = 1.18
    SHRINKAGE_MATCHES = 5.0  # Prior weight (equivalent matches) for early-season stability

    def __init__(
        self,
        raw_fixtures: Optional[List[Dict]] = None,
        players: Optional[List[Player]] = None,
        decay_rate: float = 0.06,
    ):
        self.decay_rate = decay_rate
        # team_id -> {"att_h": float, "def_h": float, "att_a": float, "def_a": float, "avg_xg": float}
        self.ratings: Dict[int, Dict[str, float]] = {}
        self.league_home_avg = self.LEAGUE_AVG_HOME_GOALS
        self.league_away_avg = self.LEAGUE_AVG_AWAY_GOALS

        if raw_fixtures:
            self.fit(raw_fixtures, players or [])

    def fit(self, raw_fixtures: List[Dict], players: Optional[List[Player]] = None) -> None:
        finished = [
            f for f in raw_fixtures
            if f.get("finished") and f.get("team_h_score") is not None and f.get("team_a_score") is not None
        ]
        if not finished:
            return

        max_gw = max((f.get("event") or 1) for f in finished)

        # Compute league-wide weighted home/away goals
        tot_w = 0.0
        tot_h = 0.0
        tot_a = 0.0
        home_gf: Dict[int, float] = {}
        home_ga: Dict[int, float] = {}
        home_w: Dict[int, float] = {}
        away_gf: Dict[int, float] = {}
        away_ga: Dict[int, float] = {}
        away_w: Dict[int, float] = {}
        team_ids = set()

        for f in finished:
            ev = f.get("event") or max_gw
            age = max(0, max_gw - ev)
            w = math.exp(-self.decay_rate * age)
            th, ta = f["team_h"], f["team_a"]
            sh, sa = float(f["team_h_score"]), float(f["team_a_score"])
            team_ids.add(th)
            team_ids.add(ta)

            tot_w += w
            tot_h += w * sh
            tot_a += w * sa

            home_gf[th] = home_gf.get(th, 0.0) + w * sh
            home_ga[th] = home_ga.get(th, 0.0) + w * sa
            home_w[th] = home_w.get(th, 0.0) + w

            away_gf[ta] = away_gf.get(ta, 0.0) + w * sa
            away_ga[ta] = away_ga.get(ta, 0.0) + w * sh
            away_w[ta] = away_w.get(ta, 0.0) + w

        if tot_w > 0:
            self.league_home_avg = max(1.10, min(1.85, tot_h / tot_w))
            self.league_away_avg = max(0.85, min(1.55, tot_a / tot_w))

        # Aggregate Opta team xG and xGC per match from players (reduces goal-scoring noise!)
        team_xg_sum: Dict[int, float] = {}
        team_xgc_max: Dict[int, float] = {}
        team_matches_est: Dict[int, float] = {}
        if players:
            for p in players:
                tid = p.team_id
                team_xg_sum[tid] = team_xg_sum.get(tid, 0.0) + max(0.0, getattr(p, "expected_goals", 0.0))
                if getattr(p, "minutes", 0) >= 180 and getattr(p, "expected_goals_conceded_per_90", 0.0) > 0:
                    # Use max-minute regular (typically GK/CB) for clean team xGC/90
                    prev_m = team_matches_est.get(tid, 0.0)
                    if p.minutes > prev_m:
                        team_matches_est[tid] = float(p.minutes)
                        team_xgc_max[tid] = float(p.expected_goals_conceded_per_90)

        league_avg_total = (self.league_home_avg + self.league_away_avg) / 2.0
        matches_played = max(1.0, float(max_gw))

        for tid in team_ids:
            hw = home_w.get(tid, 0.0)
            aw = away_w.get(tid, 0.0)
            prior = self.SHRINKAGE_MATCHES

            # Shrink actual goals toward league average
            h_gf_rate = (home_gf.get(tid, 0.0) + prior * self.league_home_avg) / (hw + prior)
            h_ga_rate = (home_ga.get(tid, 0.0) + prior * self.league_away_avg) / (hw + prior)
            a_gf_rate = (away_gf.get(tid, 0.0) + prior * self.league_away_avg) / (aw + prior)
            a_ga_rate = (away_ga.get(tid, 0.0) + prior * self.league_home_avg) / (aw + prior)

            att_h = h_gf_rate / self.league_home_avg
            def_h = h_ga_rate / self.league_away_avg
            att_a = a_gf_rate / self.league_away_avg
            def_a = a_ga_rate / self.league_home_avg

            # Blend 50% with Opta xG/xGC underlying team strength when available
            if tid in team_xg_sum and team_xg_sum[tid] > 0:
                xg_per_match = team_xg_sum[tid] / matches_played
                opta_att = max(0.55, min(1.85, xg_per_match / max(0.8, league_avg_total)))
                att_h = 0.55 * att_h + 0.45 * opta_att
                att_a = 0.55 * att_a + 0.45 * opta_att

            if tid in team_xgc_max and team_xgc_max[tid] > 0:
                opta_def = max(0.55, min(1.85, team_xgc_max[tid] / max(0.8, league_avg_total)))
                def_h = 0.55 * def_h + 0.45 * opta_def
                def_a = 0.55 * def_a + 0.45 * opta_def

            self.ratings[tid] = {
                "att_h": round(max(0.50, min(2.00, att_h)), 3),
                "def_h": round(max(0.50, min(2.00, def_h)), 3),
                "att_a": round(max(0.50, min(2.00, att_a)), 3),
                "def_a": round(max(0.50, min(2.00, def_a)), 3),
                "avg_xg": round((att_h * self.league_home_avg + att_a * self.league_away_avg) / 2.0, 3),
            }

        logger.info(
            f"TeamStrengthModel fitted on {len(finished)} finished matches (GW1..GW{max_gw}). "
            f"League avg goals: Home={self.league_home_avg:.2f}, Away={self.league_away_avg:.2f}."
        )

    def predict_match_lambdas(
        self,
        team_id: int,
        opponent_id: int,
        is_home: bool,
        fdr_fallback: int = 3,
    ) -> Tuple[float, float]:
        """Returns (expected_goals_for, expected_goals_against) for team_id vs opponent_id."""
        t_rat = self.ratings.get(team_id)
        o_rat = self.ratings.get(opponent_id)

        if t_rat and o_rat:
            if is_home:
                lam_for = self.league_home_avg * t_rat["att_h"] * o_rat["def_a"]
                lam_against = self.league_away_avg * o_rat["att_a"] * t_rat["def_h"]
            else:
                lam_for = self.league_away_avg * t_rat["att_a"] * o_rat["def_h"]
                lam_against = self.league_home_avg * o_rat["att_h"] * t_rat["def_a"]
            return (
                round(max(0.35, min(3.60, lam_for)), 3),
                round(max(0.35, min(3.60, lam_against)), 3),
            )

        # Clean fallback from FDR if ratings not fitted
        base_for = self.league_home_avg if is_home else self.league_away_avg
        base_ag = self.league_away_avg if is_home else self.league_home_avg
        fdr_delta = (3.0 - float(fdr_fallback)) * 0.22
        lam_for = max(0.45, min(3.20, base_for * (1.0 + fdr_delta)))
        lam_ag = max(0.45, min(3.20, base_ag * (1.0 - fdr_delta)))
        return round(lam_for, 3), round(lam_ag, 3)

    def get_team_avg_xg(self, team_id: int) -> float:
        r = self.ratings.get(team_id)
        if r:
            return r["avg_xg"]
        return (self.league_home_avg + self.league_away_avg) / 2.0
