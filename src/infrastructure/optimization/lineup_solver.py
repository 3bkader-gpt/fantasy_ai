from typing import List, Dict, Any, Tuple
from ...domain.models.player import Player
from ...domain.models.squad import LineupSelection

VALID_FORMATIONS: List[Tuple[int, int, int]] = [
    (3, 5, 2), (3, 4, 3), (4, 4, 2), (4, 3, 3),
    (4, 5, 1), (5, 3, 2), (5, 4, 1), (5, 2, 3)
]


class LineupSolver:
    """Finds optimal starting XI, captaincy, and bench hierarchy to maximize total xP."""

    def solve(self, squad_15: List[Player]) -> LineupSelection:
        gks = sorted([p for p in squad_15 if p.position == "GK"], key=lambda x: x.xp, reverse=True)
        defs = sorted([p for p in squad_15 if p.position == "DEF"], key=lambda x: x.xp, reverse=True)
        mids = sorted([p for p in squad_15 if p.position == "MID"], key=lambda x: x.xp, reverse=True)
        fwds = sorted([p for p in squad_15 if p.position == "FWD"], key=lambda x: x.xp, reverse=True)

        starting_gk = gks[0]
        bench_gk = gks[1] if len(gks) > 1 else None

        best_score = -1.0
        best_formation = "3-5-2"
        best_xi: List[Player] = []
        best_bench: List[Player] = []

        for n_def, n_mid, n_fwd in VALID_FORMATIONS:
            if n_def <= len(defs) and n_mid <= len(mids) and n_fwd <= len(fwds):
                current_xi = [starting_gk] + defs[:n_def] + mids[:n_mid] + fwds[:n_fwd]
                cap = max(current_xi, key=lambda x: x.xp)
                score = sum(p.xp for p in current_xi) + cap.xp  # Captain double points

                if score > best_score:
                    best_score = score
                    best_formation = f"{n_def}-{n_mid}-{n_fwd}"
                    best_xi = current_xi
                    bench_outfield = sorted(defs[n_def:] + mids[n_mid:] + fwds[n_fwd:], key=lambda x: x.xp, reverse=True)
                    best_bench = ([bench_gk] if bench_gk else []) + bench_outfield

        # Captain and Vice-Captain with Talisman, Venue & Fixture FDR EV weighting
        def cap_eval(p: Player) -> float:
            ev = p.xp * (1.18 if (p.position == "FWD" and p.cost >= 11.5) else (1.08 if p.cost >= 10.0 else 1.0))
            if "(H)" in p.next_fixture: ev *= 1.06
            elif "(A)" in p.next_fixture and p.position == "MID": ev *= 0.94
            if "[FDR 2]" in p.next_fixture: ev *= 1.10
            elif "[FDR 4]" in p.next_fixture or "[FDR 5]" in p.next_fixture: ev *= 0.88
            return ev

        sorted_xi = sorted(best_xi, key=cap_eval, reverse=True)
        captain = sorted_xi[0]
        vc_cands = sorted([p for p in best_xi if p.id != captain.id], key=lambda x: x.xp, reverse=True)
        vice_captain = vc_cands[0] if vc_cands else captain

        # Construct official FPL API picks payload (1-15)
        api_picks: List[Dict[str, Any]] = [
            {"element": starting_gk.id, "position": 1, "is_captain": (starting_gk.id == captain.id), "is_vice_captain": (starting_gk.id == vice_captain.id)}
        ]
        outfield_starters = [p for p in best_xi if p.position != "GK"]
        for idx, p in enumerate(outfield_starters, start=2):
            api_picks.append({
                "element": p.id,
                "position": idx,
                "is_captain": (p.id == captain.id),
                "is_vice_captain": (p.id == vice_captain.id)
            })

        if bench_gk:
            api_picks.append({"element": bench_gk.id, "position": 12, "is_captain": False, "is_vice_captain": False})
        for idx, p in enumerate(best_bench[1:] if bench_gk else best_bench, start=13):
            api_picks.append({"element": p.id, "position": idx, "is_captain": False, "is_vice_captain": False})

        return LineupSelection(
            formation=best_formation,
            total_expected_points=round(best_score, 2),
            starting_xi=best_xi,
            bench=best_bench,
            captain=captain,
            vice_captain=vice_captain,
            api_picks=api_picks
        )
