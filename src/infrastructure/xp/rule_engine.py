from typing import List, Dict
from ...domain.interfaces.xp_engine import IXPEngine
from ...domain.models.player import Player
from ...domain.models.fixture import Fixture


class RuleBasedXPEngine(IXPEngine):
    """Calculates expected points using a continuous Expected Minutes (E[Min]) model,

    blending form, ppg, fixture FDR, venue advantage, and horizon decay.
    """

    @staticmethod
    def calculate_expected_minutes(player: Player) -> float:
        """Computes expected playing minutes probabilistically instead of binary exclusion."""
        if player.status in ("i", "u", "s", "n"):
            return 0.0

        chance = player.chance_of_playing_next_round
        if chance is not None and chance == 0:
            return 0.0

        # Availability probability P(plays)
        if chance is None or chance == 100:
            prob_avail = 1.0
        elif chance == 75:
            prob_avail = 0.80  # 75% flag often starts or plays 65+ mins
        elif chance == 50:
            prob_avail = 0.45
        elif chance == 25:
            prob_avail = 0.15
        else:
            prob_avail = float(chance) / 100.0

        # Baseline expected minutes when fit
        if player.position == "GK":
            # Goalkeepers rarely subbed off; if starter (high points/minutes), expects 90
            base_mins = 90.0 if (player.minutes > 90 or player.total_points > 5) else 0.0
        else:
            # Outfield players: assess starting role from historical minutes
            # In early season (3 matches played = 270 max minutes), 120+ indicates regular starter
            if player.minutes >= 120:
                base_mins = 80.0
                if player.minutes >= 240 or player.form >= 4.5:
                    base_mins = 88.0
            elif player.minutes >= 60:
                base_mins = 55.0
            else:
                # Bench warmer / young prospect
                base_mins = 15.0 if player.points_per_game > 1.0 else 0.0

        exp_mins = prob_avail * base_mins
        return round(exp_mins, 1)

    def calculate_player_xp(self, player: Player, fixtures: List[Fixture]) -> float:
        exp_mins = self.calculate_expected_minutes(player)
        player.expected_minutes = exp_mins

        if exp_mins <= 0.0 or not fixtures:
            return 0.0

        # Base performance blend (65% form + 35% ppg)
        if player.minutes < 90 and player.total_points < 5:
            base_pts_90 = 1.5
        else:
            base_pts_90 = (0.65 * player.form) + (0.35 * player.points_per_game)
            if base_pts_90 <= 0.0:
                base_pts_90 = 1.2

        gw_xp_sum = 0.0
        for fix in fixtures:
            fdr = fix.difficulty
            is_home = fix.is_home
            pos = player.position

            # FDR multiplier
            if pos in ("GK", "DEF"):
                fdr_mult = 1.0 + (3.0 - fdr) * 0.14
            else:
                fdr_mult = 1.0 + (3.0 - fdr) * 0.09

            venue_mult = 1.08 if is_home else 0.92

            underlying_boost = 1.0
            if pos in ("MID", "FWD") and (player.expected_goal_involvements > 3.0 or player.ict_index > 40.0):
                underlying_boost = 1.05

            full_match_xp = base_pts_90 * fdr_mult * venue_mult * underlying_boost

            # Scale by expected minutes fraction (E[Minutes] / 90)
            scaled_match_xp = full_match_xp * (exp_mins / 90.0)
            gw_xp_sum += scaled_match_xp

        return round(max(0.0, gw_xp_sum), 2)

    def enrich_players_with_horizon_xp(
        self,
        players: List[Player],
        team_fixtures: Dict[int, List[Fixture]],
        next_gw: int,
        weeks_ahead: int = 3,
        decay: float = 0.85
    ) -> List[Player]:
        for p in players:
            all_fixes = team_fixtures.get(p.team_id, [])
            gw1_fixes = [f for f in all_fixes if f.event == next_gw]
            p.xp = self.calculate_player_xp(p, gw1_fixes)

            # Rolling horizon calculation with exponential decay
            horizon_total = 0.0
            upcoming_strs = []
            for offset in range(weeks_ahead):
                target_gw = next_gw + offset
                target_fixes = [f for f in all_fixes if f.event == target_gw]
                gw_xp = self.calculate_player_xp(p, target_fixes)
                horizon_total += gw_xp * (decay ** offset)

                if target_fixes:
                    f = target_fixes[0]
                    venue = "H" if f.is_home else "A"
                    upcoming_strs.append(f"{f.opponent_name} ({venue}) [{f.difficulty}]")
                else:
                    upcoming_strs.append("BLANK")

            p.horizon_xp = round(horizon_total, 2)
            p.horizon_fixtures = " | ".join(upcoming_strs)
            if gw1_fixes:
                f0 = gw1_fixes[0]
                p.next_fixture = f"{f0.opponent_name} ({'H' if f0.is_home else 'A'}) [FDR {f0.difficulty}]"
            else:
                p.next_fixture = "BLANK"

            # Tactical flags
            if p.selected_by_percent < 10.0 and p.xp >= 5.0:
                p.is_differential = True
            if p.selected_by_percent > 15.0 and p.xp < 3.5:
                p.is_flop_risk = True

        return players
