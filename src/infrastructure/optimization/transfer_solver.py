from typing import List, Dict, Tuple, Optional
from ...domain.models.player import Player
from ...domain.models.transfer import Transfer, TransferPlan
from .lineup_solver import LineupSolver


class TransferSolver:
    """Evaluates transfer candidate permutations under budget and team constraints."""

    def __init__(self, all_players: List[Player], lineup_solver: LineupSolver):
        self.all_players = all_players
        self.lineup_solver = lineup_solver
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
        max_hits: int
    ) -> TransferPlan:
        current_ids = {p.id for p in current_squad}
        base_lineup = self.lineup_solver.solve(current_squad)
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
                test_lineup = self.lineup_solver.solve(test_squad)
                gain = test_lineup.total_expected_points - base_lineup_xp
                test_horizon = sum(p.horizon_xp for p in test_squad)
                horizon_gain = test_horizon - base_horizon_xp
                remaining_bank = round(bank + p_out.cost - p_in.cost, 2)

                single_options.append({
                    "p_out": p_out,
                    "p_in": p_in,
                    "gain": gain,
                    "horizon_gain": round(horizon_gain, 2),
                    "new_bank": remaining_bank,
                    "test_lineup": test_lineup,
                    "test_squad": test_squad
                })

        # Sort single options by blended score (70% immediate EV + 30% horizon EV)
        single_options.sort(key=lambda x: (x["gain"] * 0.7 + x["horizon_gain"] * 0.3), reverse=True)

        if single_options and single_options[0]["gain"] > 0.5:
            top = single_options[0]
            hits_needed = max(0, 1 - free_transfers)
            hit_cost = hits_needed * 4

            if hits_needed <= max_hits and (top["gain"] - hit_cost) > 0.5:
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
        if (free_transfers >= 2 or max_hits >= 1) and len(single_options) >= 2:
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

                    test_lineup = self.lineup_solver.solve(test_squad)
                    raw_gain = test_lineup.total_expected_points - base_lineup_xp
                    test_horizon = sum(p.horizon_xp for p in test_squad)
                    horizon_gain = test_horizon - base_horizon_xp
                    hits_needed = max(0, 2 - free_transfers)
                    hit_cost = hits_needed * 4
                    net_gain = raw_gain - hit_cost

                    if hits_needed <= max_hits and net_gain > best_plan.net_gain:
                        best_plan = TransferPlan(
                            transfers=[
                                Transfer(player_out=opt1["p_out"], player_in=opt1["p_in"]),
                                Transfer(player_out=opt2["p_out"], player_in=opt2["p_in"])
                            ],
                            hits=hits_needed,
                            hits_cost=hit_cost,
                            net_gain=round(net_gain, 2),
                            horizon_gain=round(horizon_gain, 2),
                            new_bank=round(total_out - total_in, 2),
                            final_lineup=test_lineup,
                            new_players=test_squad
                        )

        return best_plan
