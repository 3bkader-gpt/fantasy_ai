from typing import List, Dict, Tuple, Optional
from ...domain.models.player import Player
from ...domain.models.transfer import Transfer, TransferPlan
from ..analysis.gold_rule_loader import GoldRuleConfig
from .lineup_solver import LineupSolver


class TransferSolver:
    """Evaluates transfer candidate permutations under budget and team constraints,
    incorporating Hindsight Gold Rules for aggressive hit EV and budget enabler profiling.
    """

    def __init__(
        self,
        all_players: List[Player],
        lineup_solver: LineupSolver,
        gold_rule_config: Optional[GoldRuleConfig] = None
    ):
        self.all_players = all_players
        self.lineup_solver = lineup_solver
        self.gold_rule_config = gold_rule_config
        self.players_by_pos = {
            "GK": [p for p in all_players if p.position == "GK"],
            "DEF": [p for p in all_players if p.position == "DEF"],
            "MID": [p for p in all_players if p.position == "MID"],
            "FWD": [p for p in all_players if p.position == "FWD"],
        }

    def solve(
        self,
        current_squad: List[Player],
        bank: float,
        free_transfers: int,
        max_hits: int,
        gold_rule_config: Optional[GoldRuleConfig] = None
    ) -> TransferPlan:
        config = gold_rule_config or self.gold_rule_config
        allowed_max_hits = max(0, max_hits)

        current_ids = {p.id for p in current_squad}
        base_lineup = self.lineup_solver.solve(current_squad, gold_rule_config=config)
        base_lineup_xp = base_lineup.total_expected_points
        base_horizon_xp = sum(p.horizon_xp for p in current_squad)

        # Count players per club
        team_counts: Dict[int, int] = {}
        for p in current_squad:
            team_counts[p.team_id] = team_counts.get(p.team_id, 0) + 1

        best_plan = TransferPlan(
            transfers=[],
            hits=0,
            hits_cost=0,
            net_gain=0.0,
            horizon_gain=0.0,
            new_bank=bank,
            final_lineup=base_lineup,
            new_players=current_squad
        )

        single_options: List[Dict] = []
        for p_out in current_squad:
            pos = p_out.position
            max_budget = p_out.cost + bank

            candidates = [
                c for c in self.players_by_pos[pos]
                if c.id not in current_ids
                and c.cost <= max_budget
                and (c.team_id == p_out.team_id or team_counts.get(c.team_id, 0) < 3)
                and (c.xp > p_out.xp or c.horizon_xp > p_out.horizon_xp)
            ]

            for p_in in candidates:
                test_squad = [p for p in current_squad if p.id != p_out.id] + [p_in]
                test_lineup = self.lineup_solver.solve(test_squad, gold_rule_config=config)
                gain = test_lineup.total_expected_points - base_lineup_xp
                test_horizon = sum(p.horizon_xp for p in test_squad)
                horizon_gain = test_horizon - base_horizon_xp
                remaining_bank = round(bank + p_out.cost - p_in.cost, 2)

                # Gold Rule: Budget enabler prioritization (< £6.0m with high points-per-million)
                ppm_boost = 0.0
                if config and config.is_active and p_in.cost < 6.0:
                    ppm = p_in.xp / max(4.0, p_in.cost)
                    ppm_boost = ppm * config.budget_enabler_ppm_weight

                # Check underperformer out vs explosive in
                is_out_underperformer = (
                    getattr(p_out, "expected_minutes", 90.0) < 60.0
                    or getattr(p_out, "form", 5.0) < 3.0
                    or (p_out.chance_of_playing_next_round is not None and p_out.chance_of_playing_next_round < 75)
                )
                mins_in = getattr(p_in, "minutes", 0)
                xgi_90_in = (getattr(p_in, "expected_goal_involvements", 0.0) / mins_in * 90.0) if mins_in >= 90 else 0.0
                is_in_explosive = (
                    getattr(p_in, "form", 0.0) >= 4.5
                    or (xgi_90_in >= 0.35 and getattr(p_in, "next_fdr", 3) <= 2)
                    or p_in.xp >= 6.0
                )

                single_options.append({
                    "p_out": p_out,
                    "p_in": p_in,
                    "gain": gain,
                    "horizon_gain": round(horizon_gain, 2),
                    "new_bank": remaining_bank,
                    "test_lineup": test_lineup,
                    "test_squad": test_squad,
                    "ppm_boost": ppm_boost,
                    "is_out_underperformer": is_out_underperformer,
                    "is_in_explosive": is_in_explosive,
                })

        # Sort single options by blended score (70% immediate EV + 30% horizon EV + ppm boost)
        single_options.sort(
            key=lambda x: (x["gain"] * 0.7 + x["horizon_gain"] * 0.3 + x.get("ppm_boost", 0.0)),
            reverse=True
        )

        # Unified comparison score (0.0 = hold / no transfers)
        best_score = 0.0

        def _hit_is_justified(
            hits_needed: int,
            gain: float,
            horizon_gain: float,
            out_players: List[Player],
            in_players: Optional[List[Player]] = None,
        ) -> bool:
            if hits_needed <= 0:
                return True
            # Anti-Churn Same-Club Guard: never pay a hit for a sideways same-club swap unless outgoing is unavailable
            if in_players:
                for p_out, p_in in zip(out_players, in_players):
                    if p_out.team_id == p_in.team_id and p_out.is_available and getattr(p_out, "expected_minutes", 90.0) > 0.0:
                        return False
            hit_cost = hits_needed * 4
            has_injured_out = any(
                (not p.is_available) or getattr(p, "expected_minutes", 90.0) == 0.0
                for p in out_players
            )
            if has_injured_out and gain >= 2.0 and (horizon_gain - hit_cost) >= 1.5:
                return True
            return (gain - hit_cost) >= 1.5 and (horizon_gain - hit_cost) >= 4.0

        # Smart Roll-FT Hurdle: FPL allows banking up to 5 FTs.
        # Avoid burning a free transfer for marginal gains (< 1.5 xP) unless squad is at max 5 FTs or outgoing is injured.
        if single_options and single_options[0]["gain"] > 0.5:
            top = single_options[0]
            hits_needed = max(0, 1 - free_transfers)
            hit_cost = hits_needed * 4
            net_ev = (top["gain"] * 0.7 + top["horizon_gain"] * 0.3) - hit_cost

            out_injured = (not top["p_out"].is_available) or getattr(top["p_out"], "expected_minutes", 90.0) == 0.0
            roll_ft_hurdle = 0.5 if (free_transfers >= 5 or out_injured or hits_needed > 0) else 1.5

            if (
                hits_needed <= allowed_max_hits
                and _hit_is_justified(hits_needed, top["gain"], top["horizon_gain"], [top["p_out"]], [top["p_in"]])
                and net_ev > max(roll_ft_hurdle, best_score)
            ):
                best_score = net_ev
                best_plan = TransferPlan(
                    transfers=[Transfer(player_out=top["p_out"], player_in=top["p_in"])],
                    hits=hits_needed,
                    hits_cost=hit_cost,
                    net_gain=round(top["gain"] - hit_cost, 2),
                    horizon_gain=top["horizon_gain"],
                    new_bank=top["new_bank"],
                    final_lineup=top["test_lineup"],
                    new_players=top["test_squad"]
                )

        # Check Double Transfers if allowed
        if (free_transfers >= 2 or allowed_max_hits >= 1) and len(single_options) >= 2:
            top_subset = single_options[:15]
            for i in range(len(top_subset)):
                for j in range(i + 1, len(top_subset)):
                    opt1, opt2 = top_subset[i], top_subset[j]
                    if opt1["p_out"].id == opt2["p_out"].id or opt1["p_in"].id == opt2["p_in"].id:
                        continue

                    total_in = opt1["p_in"].cost + opt2["p_in"].cost
                    total_out = opt1["p_out"].cost + opt2["p_out"].cost + bank
                    if total_in > total_out:
                        continue

                    # Validate max 3 per club
                    test_counts = dict(team_counts)
                    test_counts[opt1["p_out"].team_id] -= 1
                    test_counts[opt2["p_out"].team_id] -= 1
                    test_counts[opt1["p_in"].team_id] = test_counts.get(opt1["p_in"].team_id, 0) + 1
                    test_counts[opt2["p_in"].team_id] = test_counts.get(opt2["p_in"].team_id, 0) + 1
                    if any(c > 3 for c in test_counts.values()):
                        continue

                    test_squad = [
                        p for p in current_squad
                        if p.id not in (opt1["p_out"].id, opt2["p_out"].id)
                    ] + [opt1["p_in"], opt2["p_in"]]

                    test_lineup = self.lineup_solver.solve(test_squad, gold_rule_config=config)
                    raw_gain = test_lineup.total_expected_points - base_lineup_xp
                    test_horizon = sum(p.horizon_xp for p in test_squad)
                    horizon_gain = test_horizon - base_horizon_xp
                    hits_needed = max(0, 2 - free_transfers)
                    hit_cost = hits_needed * 4

                    net_ev = (raw_gain * 0.7 + horizon_gain * 0.3) - hit_cost

                    if (
                        hits_needed <= allowed_max_hits
                        and _hit_is_justified(
                            hits_needed,
                            raw_gain,
                            horizon_gain,
                            [opt1["p_out"], opt2["p_out"]],
                            [opt1["p_in"], opt2["p_in"]],
                        )
                        and net_ev > best_score
                    ):
                        best_score = net_ev
                        best_plan = TransferPlan(
                            transfers=[
                                Transfer(player_out=opt1["p_out"], player_in=opt1["p_in"]),
                                Transfer(player_out=opt2["p_out"], player_in=opt2["p_in"])
                            ],
                            hits=hits_needed,
                            hits_cost=hit_cost,
                            net_gain=round(raw_gain - hit_cost, 2),
                            horizon_gain=round(horizon_gain, 2),
                            new_bank=round(total_out - total_in, 2),
                            final_lineup=test_lineup,
                            new_players=test_squad
                        )

        return best_plan
