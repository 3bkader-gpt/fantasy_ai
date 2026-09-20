import logging
from typing import List, Dict, Set, Tuple, Optional, Any
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds

from ...domain.models.player import Player

logger = logging.getLogger("InitialSquadBuilder")


class InitialSquadBuilder:
    """Exact Two-Tier Mixed-Integer Linear Programming (MILP) solver that optimizes
    the 11 starters (weight 1.0x), Captain (2.0x), and bench enablers (0.10x)
    under the Power 11 budget allocation rules (Bench <= £17.5m, Total <= £100.0m).
    """

    def solve(
        self,
        all_players: List[Player],
        budget: float = 100.0,
        max_bench_budget: float = 17.5,
        max_per_club: int = 3,
        bench_weight: float = 0.10,
        min_starter_chance: int = 75,
        locked_player_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        candidates = [
            p for p in all_players
            if p.expected_minutes > 0.0 and p.cost > 0.0 and p.horizon_xp > 0.0
        ]
        N = len(candidates)
        if N < 15:
            raise ValueError(f"Not enough active candidates ({N}) to build a squad.")

        logger.info(f"Solving Two-Tier MILP (min_chance={min_starter_chance}%) across {N} candidates...")

        # 3N binary decision variables:
        # Indices 0 to N-1:       s_i (1 if player i is in Starting XI)
        # Indices N to 2N-1:     b_i (1 if player i is on the Bench)
        # Indices 2N to 3N-1:    c_i (1 if player i is Captain)

        c_obj = np.zeros(3 * N)
        for i, p in enumerate(candidates):
            c_obj[i] = -p.horizon_xp                    # s_i
            c_obj[N + i] = -bench_weight * p.horizon_xp # b_i (down-weighted bench insurance)
            # Captaincy EV: Talisman floor, venue & fixture FDR weighting
            cap_ev = p.horizon_xp * (1.18 if (p.position == "FWD" and p.cost >= 11.5) else (1.08 if p.cost >= 10.0 else 1.0))
            if "(H)" in p.next_fixture: cap_ev *= 1.06
            elif "(A)" in p.next_fixture and p.position == "MID": cap_ev *= 0.94
            if "[FDR 2]" in p.next_fixture: cap_ev *= 1.10
            elif "[FDR 4]" in p.next_fixture or "[FDR 5]" in p.next_fixture: cap_ev *= 0.88
            c_obj[2 * N + i] = -round(cap_ev, 2)        # c_i (captain double points)

        integrality = np.ones(3 * N)
        bounds_lb = np.zeros(3 * N)
        bounds_ub = np.ones(3 * N)

        # Support locked players (e.g. Haaland lock)
        if locked_player_ids:
            cand_id_map = {p.id: i for i, p in enumerate(candidates)}
            for l_id in locked_player_ids:
                if l_id in cand_id_map:
                    bounds_lb[cand_id_map[l_id]] = 1.0

        # 1. Captaincy Fitness Policy (Absolute Zero-Risk):
        # Captain earns 2.0x points; any doubt is catastrophic.
        # Only fully available players (status == 'a' and chance >= 100/None) can be Captain.
        for i, p in enumerate(candidates):
            has_cap_doubt = (
                p.status != "a"
                or (p.chance_of_playing_next_round is not None and p.chance_of_playing_next_round < 100)
            )
            if has_cap_doubt:
                bounds_ub[2 * N + i] = 0.0  # Barred from Captaincy (c_i = 0)

        # 2. Starting XI Fitness Policy (Parametric Ceiling vs Floor):
        # - Status in ('i', 's', 'u', 'n'): Unconditionally barred from Starting XI.
        # - Status == 'd' (Doubtful): Only permitted if chance >= min_starter_chance (e.g. 75%).
        #   If chance is unspecified (None) under doubt, treated as high-risk and barred.
        # - Status == 'a': Fully permitted (administrative/transfer notes in 'news' never cause false exclusions).
        for i, p in enumerate(candidates):
            if p.status in ("i", "s", "u", "n"):
                bounds_ub[i] = 0.0          # Barred from Starting XI
                if p.chance_of_playing_next_round == 0:
                    bounds_ub[N + i] = 0.0  # Also barred from Bench if 0% chance
                continue

            if p.status == "d":
                chance = p.chance_of_playing_next_round
                if chance is None or chance < min_starter_chance:
                    bounds_ub[i] = 0.0      # Barred from Starting XI

        bounds = Bounds(bounds_lb, bounds_ub)

        A_rows = []
        lb_list = []
        ub_list = []

        # 1-3. Exactly 11 Starters, 4 Bench, 1 Captain
        for (st, en), count in [((0, N), 11), ((N, 2 * N), 4), ((2 * N, 3 * N), 1)]:
            r = np.zeros(3 * N); r[st:en] = 1.0
            A_rows.append(r); lb_list.append(count); ub_list.append(count)

        # 4. Captain must be in Starting XI: c_i - s_i <= 0
        for i in range(N):
            row = np.zeros(3 * N); row[2*N + i] = 1.0; row[i] = -1.0
            A_rows.append(row); lb_list.append(-np.inf); ub_list.append(0.0)

        # 5. Player cannot be both starter and bench: s_i + b_i <= 1
        for i in range(N):
            row = np.zeros(3 * N); row[i] = 1.0; row[N + i] = 1.0
            A_rows.append(row); lb_list.append(0.0); ub_list.append(1.0)

        # 6. Total Budget: sum(cost_i * (s_i + b_i)) <= budget (100.0)
        row = np.zeros(3 * N)
        for i, p in enumerate(candidates):
            row[i] = p.cost; row[N + i] = p.cost
        A_rows.append(row); lb_list.append(0.0); ub_list.append(budget)

        # 7. Bench Budget Constraint (Power 11 Principle): sum(cost_i * b_i) <= max_bench_budget (17.5)
        row = np.zeros(3 * N)
        for i, p in enumerate(candidates):
            row[N + i] = p.cost
        A_rows.append(row); lb_list.append(0.0); ub_list.append(max_bench_budget)

        # 8. Positional Limits: (pos, squad_total, min_starter, max_starter)
        pos_rules = [("GK", 2, 1, 1), ("DEF", 5, 3, 5), ("MID", 5, 2, 5), ("FWD", 3, 1, 3)]
        for pos, quota, s_min, s_max in pos_rules:
            # Squad total (s_i + b_i == quota)
            r_tot = np.zeros(3 * N)
            for i, p in enumerate(candidates):
                if p.position == pos: r_tot[i] = 1.0; r_tot[N + i] = 1.0
            A_rows.append(r_tot); lb_list.append(quota); ub_list.append(quota)

            # Starters range (s_min <= sum(s_i) <= s_max)
            r_str = np.zeros(3 * N)
            for i, p in enumerate(candidates):
                if p.position == pos: r_str[i] = 1.0
            A_rows.append(r_str); lb_list.append(s_min); ub_list.append(s_max)

        # 10. Club Limits: max 3 per club, and anti-stacking (max 1 attacker from non-elite in XI)
        elite_clubs = {"ARS", "MCI", "LIV", "CHE", "MUN", "NEW", "TOT"}
        teams: Set[int] = set(p.team_id for p in candidates)
        for t_id in teams:
            row = np.zeros(3 * N)
            att_row = np.zeros(3 * N)
            for i, p in enumerate(candidates):
                if p.team_id == t_id:
                    row[i] = 1.0; row[N + i] = 1.0
                    if p.position in ("MID", "FWD") and p.team_short.upper() not in elite_clubs:
                        att_row[i] = 1.0
            A_rows.append(row); lb_list.append(0); ub_list.append(max_per_club)
            if np.sum(att_row) > 1.0:
                A_rows.append(att_row); lb_list.append(-np.inf); ub_list.append(1.0)

        # Solve MILP
        A = np.array(A_rows)
        constraints = LinearConstraint(A, lb_list, ub_list)
        res = milp(c=c_obj, integrality=integrality, constraints=constraints, bounds=bounds)

        if not res.success:
            raise RuntimeError(f"MILP optimization failed with status {res.status}")

        s_sol, b_sol, c_sol = res.x[:N], res.x[N:2*N], res.x[2*N:]
        starters = [candidates[i] for i in np.where(s_sol > 0.5)[0]]
        bench_raw = [candidates[i] for i in np.where(b_sol > 0.5)[0]]
        captain = [candidates[i] for i in np.where(c_sol > 0.5)[0]][0]

        vc_cand = sorted([p for p in starters if p.id != captain.id], key=lambda x: x.xp, reverse=True)
        vice_captain = vc_cand[0] if vc_cand else captain

        bench_gk = [p for p in bench_raw if p.position == "GK"]
        bench_outfield = sorted([p for p in bench_raw if p.position != "GK"], key=lambda x: x.xp, reverse=True)
        ordered_bench = bench_gk + bench_outfield

        n_def = sum(1 for p in starters if p.position == "DEF")
        n_mid = sum(1 for p in starters if p.position == "MID")
        n_fwd = sum(1 for p in starters if p.position == "FWD")

        return {
            "starters": starters,
            "bench": ordered_bench,
            "captain": captain,
            "vice_captain": vice_captain,
            "formation": f"{n_def}-{n_mid}-{n_fwd}",
            "squad_15": starters + ordered_bench
        }
