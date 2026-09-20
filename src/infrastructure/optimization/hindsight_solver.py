import logging
from typing import Dict, List, Tuple, Optional, Any
from ortools.sat.python import cp_model

from ...domain.models.hindsight_models import (
    PlayerGameweekRecord,
    HindsightGameweekDecision,
    HindsightResult,
)

logger = logging.getLogger("HindsightSolver")


class HindsightSolver:
    """Multi-period Integer Linear Programming (ILP) solver using Google OR-Tools CP-SAT.
    
    Discovers the mathematically optimal sequence of squads, lineups, captains, and transfers
    across finished gameweeks to achieve the absolute maximum possible points.
    """

    def __init__(self, time_limit_seconds: float = 60.0, num_workers: int = 8):
        self.time_limit_seconds = time_limit_seconds
        self.num_workers = num_workers

    def solve(
        self,
        player_points: Dict[int, List[PlayerGameweekRecord]],
        gw_start: int,
        gw_end: int,
        initial_budget: float = 100.0,
    ) -> HindsightResult:
        """Solve the multi-period hindsight optimization problem."""
        gameweeks = sorted([gw for gw in player_points.keys() if gw_start <= gw <= gw_end])
        if not gameweeks:
            raise ValueError(f"No player points provided for gameweek range {gw_start}..{gw_end}")

        # Index player records
        # Map: player_id -> {gw -> record}
        all_player_ids = set()
        records_by_gw_player: Dict[Tuple[int, int], PlayerGameweekRecord] = {}
        player_meta: Dict[int, Dict[str, Any]] = {}

        for gw in gameweeks:
            for rec in player_points[gw]:
                all_player_ids.add(rec.player_id)
                records_by_gw_player[(gw, rec.player_id)] = rec
                if rec.player_id not in player_meta:
                    player_meta[rec.player_id] = {
                        "element_type": rec.element_type,
                        "team_id": rec.team_id,
                        "web_name": rec.web_name,
                    }

        player_list = sorted(list(all_player_ids))
        logger.info(
            f"Solving hindsight optimization: GW{gw_start}..GW{gw_end}, "
            f"{len(player_list)} unique players, initial budget: £{initial_budget}m"
        )

        model = cp_model.CpModel()

        # Decision Variables
        # s[gw, p]: 1 if player p is in starting XI in gw
        # b[gw, p]: 1 if player p is on bench in gw
        # c[gw, p]: 1 if player p is captain in gw
        # squad[gw, p]: 1 if player p is in 15-man squad in gw
        s: Dict[Tuple[int, int], cp_model.IntVar] = {}
        b: Dict[Tuple[int, int], cp_model.IntVar] = {}
        c: Dict[Tuple[int, int], cp_model.IntVar] = {}
        squad: Dict[Tuple[int, int], cp_model.IntVar] = {}

        # Transfer variables (gw > gw_start)
        buy: Dict[Tuple[int, int], cp_model.IntVar] = {}
        sell: Dict[Tuple[int, int], cp_model.IntVar] = {}

        for gw in gameweeks:
            for p in player_list:
                s[gw, p] = model.NewBoolVar(f"start_{gw}_{p}")
                b[gw, p] = model.NewBoolVar(f"bench_{gw}_{p}")
                c[gw, p] = model.NewBoolVar(f"cap_{gw}_{p}")
                squad[gw, p] = model.NewBoolVar(f"squad_{gw}_{p}")

                # Squad link: player in squad if and only if starter or bench
                model.Add(squad[gw, p] == s[gw, p] + b[gw, p])
                model.Add(s[gw, p] + b[gw, p] <= 1)

                # Captain must start
                model.Add(c[gw, p] <= s[gw, p])

                if gw > gameweeks[0]:
                    buy[gw, p] = model.NewBoolVar(f"buy_{gw}_{p}")
                    sell[gw, p] = model.NewBoolVar(f"sell_{gw}_{p}")
                    model.Add(buy[gw, p] + sell[gw, p] <= 1)

        # Categorize players by position and team
        gks = [p for p in player_list if player_meta[p]["element_type"] == 1]
        defs = [p for p in player_list if player_meta[p]["element_type"] == 2]
        mids = [p for p in player_list if player_meta[p]["element_type"] == 3]
        fwds = [p for p in player_list if player_meta[p]["element_type"] == 4]

        teams: Dict[int, List[int]] = {}
        for p in player_list:
            t_id = player_meta[p]["team_id"]
            teams.setdefault(t_id, []).append(p)

        # Gameweek-specific constraints
        for gw in gameweeks:
            # 1. Exactly 15 in squad, 11 starters, 4 bench, 1 captain
            model.Add(sum(squad[gw, p] for p in player_list) == 15)
            model.Add(sum(s[gw, p] for p in player_list) == 11)
            model.Add(sum(b[gw, p] for p in player_list) == 4)
            model.Add(sum(c[gw, p] for p in player_list) == 1)

            # 2. Positional quotas in 15-man squad
            model.Add(sum(squad[gw, p] for p in gks) == 2)
            model.Add(sum(squad[gw, p] for p in defs) == 5)
            model.Add(sum(squad[gw, p] for p in mids) == 5)
            model.Add(sum(squad[gw, p] for p in fwds) == 3)

            # 3. Starting XI formation quotas
            model.Add(sum(s[gw, p] for p in gks) == 1)
            model.Add(sum(s[gw, p] for p in defs) >= 3)
            model.Add(sum(s[gw, p] for p in defs) <= 5)
            model.Add(sum(s[gw, p] for p in mids) >= 2)
            model.Add(sum(s[gw, p] for p in mids) <= 5)
            model.Add(sum(s[gw, p] for p in fwds) >= 1)
            model.Add(sum(s[gw, p] for p in fwds) <= 3)

            # 4. Club limit: max 3 players per club in 15-man squad
            for t_id, club_players in teams.items():
                if t_id > 0:
                    model.Add(sum(squad[gw, p] for p in club_players) <= 3)

        # Budget variables (all values in tenths of £m, e.g., 100.0m -> 1000)
        # bank[gw] represents remaining cash in bank
        initial_budget_int = int(round(initial_budget * 10))
        bank: Dict[int, cp_model.IntVar] = {}

        for gw in gameweeks:
            bank[gw] = model.NewIntVar(0, initial_budget_int, f"bank_{gw}")

        # Helper to get price_int for player at gw
        def get_price_int(gw_idx: int, p_id: int) -> int:
            rec = records_by_gw_player.get((gw_idx, p_id))
            if rec:
                return int(round(rec.price * 10))
            return 50  # Default 5.0m

        # GW1 Budget: cost of initial 15 + bank[gw1] == initial_budget
        gw1 = gameweeks[0]
        model.Add(
            sum(get_price_int(gw1, p) * squad[gw1, p] for p in player_list) + bank[gw1]
            == initial_budget_int
        )

        # Transfer linking & rollover variables
        # free_transfers[gw]: available FTs at start of gw (in [1, 5])
        # hits[gw]: hits taken at gw (>= 0)
        free_transfers: Dict[int, cp_model.IntVar] = {}
        hits: Dict[int, cp_model.IntVar] = {}
        transfers_made: Dict[int, cp_model.IntVar] = {}

        for i, gw in enumerate(gameweeks):
            hits[gw] = model.NewIntVar(0, 15, f"hits_{gw}")
            transfers_made[gw] = model.NewIntVar(0, 15, f"transfers_made_{gw}")
            free_transfers[gw] = model.NewIntVar(1, 5, f"ft_{gw}")

            if i == 0:
                # GW1: Squad selection is free, FT for next GW starts at 1
                model.Add(transfers_made[gw] == 0)
                model.Add(hits[gw] == 0)
                model.Add(free_transfers[gw] == 1)
            else:
                prev_gw = gameweeks[i - 1]

                # 1. Squad transition: squad[gw, p] = squad[prev_gw, p] + buy[gw, p] - sell[gw, p]
                for p in player_list:
                    model.Add(
                        squad[gw, p] == squad[prev_gw, p] + buy[gw, p] - sell[gw, p]
                    )

                # 2. Transfers count
                model.Add(transfers_made[gw] == sum(buy[gw, p] for p in player_list))
                # Number of buys must equal number of sells
                model.Add(sum(buy[gw, p] for p in player_list) == sum(sell[gw, p] for p in player_list))

                # 3. Budget transition:
                # bank[gw] == bank[prev_gw] + money_from_sells - money_for_buys
                sell_revenue = sum(get_price_int(gw, p) * sell[gw, p] for p in player_list)
                buy_cost = sum(get_price_int(gw, p) * buy[gw, p] for p in player_list)
                model.Add(bank[gw] == bank[prev_gw] + sell_revenue - buy_cost)

                # 4. Hits calculation: hits[gw] >= transfers_made[gw] - free_transfers[gw]
                excess_transfers = model.NewIntVar(-5, 15, f"excess_transfers_{gw}")
                model.Add(excess_transfers == transfers_made[gw] - free_transfers[gw])
                model.AddMaxEquality(hits[gw], [excess_transfers, model.NewConstant(0)])

                # 5. Free transfer rollover for subsequent GWs
                # In FPL: unused_ft = max(0, free_transfers[prev] - transfers_made[prev])
                # available_ft[gw] = min(5, 1 + unused_ft)
                unused_ft = model.NewIntVar(0, 5, f"unused_ft_{prev_gw}")
                diff_ft = model.NewIntVar(-15, 5, f"diff_ft_{prev_gw}")
                model.Add(diff_ft == free_transfers[prev_gw] - transfers_made[prev_gw])
                model.AddMaxEquality(unused_ft, [diff_ft, model.NewConstant(0)])

                next_ft_expr = model.NewIntVar(1, 6, f"next_ft_expr_{gw}")
                model.Add(next_ft_expr == unused_ft + 1)
                model.AddMinEquality(free_transfers[gw], [next_ft_expr, model.NewConstant(5)])

        # Objective Function: Maximize total net points across all gameweeks
        # Net points = sum(points * starters) + sum(points * captain) - 4 * hits
        objective_terms = []
        for gw in gameweeks:
            for p in player_list:
                rec = records_by_gw_player.get((gw, p))
                pts = rec.total_points if rec else 0
                if pts != 0:
                    objective_terms.append(pts * s[gw, p])
                    objective_terms.append(pts * c[gw, p])  # Captain extra points
            objective_terms.append(-4 * hits[gw])

        model.Maximize(sum(objective_terms))

        # Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.time_limit_seconds
        solver.parameters.num_search_workers = self.num_workers

        logger.info(f"Solving with CP-SAT (time limit: {self.time_limit_seconds}s)...")
        status = solver.Solve(model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError(f"Hindsight solver failed to find a feasible solution. Status: {status}")

        logger.info(
            f"CP-SAT finished with status: {'OPTIMAL' if status == cp_model.OPTIMAL else 'FEASIBLE'}, "
            f"Objective Value: {solver.ObjectiveValue()}"
        )

        # Reconstruct decisions
        decisions: List[HindsightGameweekDecision] = []
        total_points_accum = 0
        total_hits_accum = 0
        total_hit_cost_accum = 0

        for gw in gameweeks:
            squad_ids = [p for p in player_list if solver.Value(squad[gw, p]) == 1]
            starter_ids = [p for p in player_list if solver.Value(s[gw, p]) == 1]
            bench_ids = [p for p in player_list if solver.Value(b[gw, p]) == 1]
            captain_id = [p for p in player_list if solver.Value(c[gw, p]) == 1][0]

            transfers_in_ids = [p for p in player_list if gw > gameweeks[0] and solver.Value(buy[gw, p]) == 1]
            transfers_out_ids = [p for p in player_list if gw > gameweeks[0] and solver.Value(sell[gw, p]) == 1]

            hits_val = int(solver.Value(hits[gw]))
            hit_cost_val = hits_val * 4
            bank_val = float(solver.Value(bank[gw])) / 10.0

            # Calculate gross points for starters and captain
            starter_pts = sum(
                records_by_gw_player.get((gw, p), PlayerGameweekRecord(p, gw, 0, 0, 0, 0, 0, 0, False, 0, "", 3, 0.0)).total_points
                for p in starter_ids
            )
            cap_rec = records_by_gw_player.get((gw, captain_id))
            cap_pts = cap_rec.total_points if cap_rec else 0
            gross_points = starter_pts + cap_pts
            net_points = gross_points - hit_cost_val

            total_points_accum += net_points
            total_hits_accum += hits_val
            total_hit_cost_accum += hit_cost_val

            # Determine formation
            def_starters = sum(1 for p in starter_ids if player_meta[p]["element_type"] == 2)
            mid_starters = sum(1 for p in starter_ids if player_meta[p]["element_type"] == 3)
            fwd_starters = sum(1 for p in starter_ids if player_meta[p]["element_type"] == 4)
            formation = f"{def_starters}-{mid_starters}-{fwd_starters}"

            # Bench ordering: GK first, then outfield by points descending
            bench_gk = [p for p in bench_ids if player_meta[p]["element_type"] == 1]
            bench_outfield = [p for p in bench_ids if player_meta[p]["element_type"] != 1]
            bench_outfield.sort(
                key=lambda p: records_by_gw_player.get((gw, p), PlayerGameweekRecord(p, gw, 0, 0, 0, 0, 0, 0, False, 0, "", 3, 0.0)).total_points,
                reverse=True,
            )
            ordered_bench = bench_gk + bench_outfield

            # Vice-captain: highest scoring non-captain starter
            other_starters = [p for p in starter_ids if p != captain_id]
            other_starters.sort(
                key=lambda p: records_by_gw_player.get((gw, p), PlayerGameweekRecord(p, gw, 0, 0, 0, 0, 0, 0, False, 0, "", 3, 0.0)).total_points,
                reverse=True,
            )
            vice_captain_id = other_starters[0] if other_starters else captain_id

            # Calculate total team value
            squad_value = sum(
                records_by_gw_player.get((gw, p), PlayerGameweekRecord(p, gw, 0, 0, 0, 0, 0, 0, False, 0, "", 3, 0.0)).price
                for p in squad_ids
            )

            decision = HindsightGameweekDecision(
                gameweek=gw,
                squad_15=squad_ids,
                starting_xi=starter_ids,
                bench=ordered_bench,
                captain_id=captain_id,
                vice_captain_id=vice_captain_id,
                formation=formation,
                transfers_in=transfers_in_ids,
                transfers_out=transfers_out_ids,
                hits_taken=hits_val,
                hit_cost=hit_cost_val,
                gross_points=gross_points,
                total_points=net_points,
                bank=round(bank_val, 1),
                team_value=round(squad_value + bank_val, 1),
            )
            decisions.append(decision)

        return HindsightResult(
            gameweek_range=(gameweeks[0], gameweeks[-1]),
            decisions=decisions,
            total_points=total_points_accum,
            total_hits=total_hits_accum,
            total_hit_cost=total_hit_cost_accum,
        )
