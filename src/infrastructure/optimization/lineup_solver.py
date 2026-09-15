import re
from typing import List, Dict, Any, Tuple, Optional
from ...domain.models.player import Player
from ...domain.models.squad import LineupSelection

VALID_FORMATIONS: List[Tuple[int, int, int]] = [
    (3, 5, 2), (3, 4, 3), (4, 4, 2), (4, 3, 3),
    (4, 5, 1), (5, 3, 2), (5, 4, 1), (5, 2, 3)
]


def get_opponent_code(fixture_str: str) -> str:
    """Extracts 3-letter opponent team code from fixture string, e.g. 'CHE (A) [FDR 4]' -> 'CHE'."""
    if not fixture_str or fixture_str == "BLANK":
        return ""
    m = re.match(r"^([A-Za-z]{3})", fixture_str.strip())
    return m.group(1).upper() if m else ""


def calculate_gk_conflict_penalty(gk: Player, outfield_starters: List[Player], captain_id: Optional[int] = None) -> float:
    """Computes negative covariance / anti-correlation penalty when a goalkeeper

    faces our own starting attackers (MID / FWD).
    Cannibalizes clean sheet points and incurs negative points for goals conceded.
    """
    gk_opp = get_opponent_code(gk.next_fixture)
    if not gk_opp:
        return 0.0

    penalty = 0.0
    for p in outfield_starters:
        if p.position in ("MID", "FWD") and p.team_short.upper() == gk_opp:
            # Starting attacker directly threatens the GK's clean sheet
            att_weight = max(1.0, p.xp / 4.0)
            pen = 1.5 * att_weight
            # Amplified penalty if opposing attacker is captained (we are actively betting on goals)
            if captain_id is not None and p.id == captain_id:
                pen *= 1.8
            penalty += pen

    return round(penalty, 2)


class LineupSolver:
    """Finds optimal starting XI, captaincy, and bench hierarchy to maximize total xP,

    jointly optimizing goalkeepers with outfielders to eliminate anti-correlation conflicts.
    """

    def solve(self, squad_15: List[Player]) -> LineupSelection:
        gks = sorted([p for p in squad_15 if p.position == "GK"], key=lambda x: x.xp, reverse=True)
        defs = sorted([p for p in squad_15 if p.position == "DEF"], key=lambda x: x.xp, reverse=True)
        mids = sorted([p for p in squad_15 if p.position == "MID"], key=lambda x: x.xp, reverse=True)
        fwds = sorted([p for p in squad_15 if p.position == "FWD"], key=lambda x: x.xp, reverse=True)

        best_score = -999.0
        best_formation = "3-5-2"
        best_xi: List[Player] = []
        best_bench: List[Player] = []
        best_starting_gk: Optional[Player] = gks[0] if gks else None
        best_bench_gk: Optional[Player] = gks[1] if len(gks) > 1 else None

        # Joint optimization: evaluate every valid outfield formation against all available GKs
        for n_def, n_mid, n_fwd in VALID_FORMATIONS:
            if n_def <= len(defs) and n_mid <= len(mids) and n_fwd <= len(fwds):
                cand_outfield = defs[:n_def] + mids[:n_mid] + fwds[:n_fwd]
                bench_outfield = sorted(defs[n_def:] + mids[n_mid:] + fwds[n_fwd:], key=lambda x: x.xp, reverse=True)

                for gk_candidate in gks:
                    other_gk = [g for g in gks if g.id != gk_candidate.id]
                    candidate_bench_gk = other_gk[0] if other_gk else None

                    current_xi = [gk_candidate] + cand_outfield
                    tentative_cap = max(current_xi, key=lambda x: x.xp)

                    # Calculate conflict penalty against opposing starting attackers
                    conflict_pen = calculate_gk_conflict_penalty(
                        gk=gk_candidate,
                        outfield_starters=cand_outfield,
                        captain_id=tentative_cap.id
                    )

                    # Net effective score with anti-correlation penalty
                    score = sum(p.xp for p in current_xi) + tentative_cap.xp - conflict_pen

                    if score > best_score:
                        best_score = score
                        best_formation = f"{n_def}-{n_mid}-{n_fwd}"
                        best_xi = current_xi
                        best_starting_gk = gk_candidate
                        best_bench_gk = candidate_bench_gk
                        best_bench = ([candidate_bench_gk] if candidate_bench_gk else []) + bench_outfield

        # Captain and Vice-Captain with Talisman, Venue & Fixture FDR EV weighting
        def cap_eval(p: Player) -> float:
            ev = p.xp * (1.18 if (p.position == "FWD" and p.cost >= 11.5) else (1.08 if p.cost >= 10.0 else 1.0))
            if "(H)" in p.next_fixture:
                ev *= 1.06
            elif "(A)" in p.next_fixture and p.position == "MID":
                ev *= 0.94
            if "[FDR 2]" in p.next_fixture:
                ev *= 1.10
            elif "[FDR 4]" in p.next_fixture or "[FDR 5]" in p.next_fixture:
                ev *= 0.88
            return ev

        sorted_xi = sorted(best_xi, key=cap_eval, reverse=True)
        captain = sorted_xi[0] if sorted_xi else (gks[0] if gks else None)
        vc_cands = [p for p in best_xi if p.id != captain.id]
        vice_captain = sorted(vc_cands, key=lambda x: x.xp, reverse=True)[0] if vc_cands else captain

        starting_gk = best_starting_gk or (gks[0] if gks else None)
        bench_gk = best_bench_gk

        # Construct official FPL API picks payload (1-15)
        api_picks: List[Dict[str, Any]] = [
            {
                "element": starting_gk.id,
                "position": 1,
                "is_captain": (starting_gk.id == captain.id),
                "is_vice_captain": (starting_gk.id == vice_captain.id)
            }
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
