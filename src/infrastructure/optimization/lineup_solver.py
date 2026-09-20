import re
import itertools
from collections import Counter
from typing import List, Dict, Any, Tuple, Optional
from ...domain.models.player import Player
from ...domain.models.squad import LineupSelection

VALID_FORMATIONS: List[Tuple[int, int, int]] = [
    (3, 5, 2), (3, 4, 3), (4, 4, 2), (4, 3, 3),
    (4, 5, 1), (5, 3, 2), (5, 4, 1), (5, 2, 3)
]


def get_opponent_code(fixture_or_player: Any) -> str:
    """Extracts 3-letter opponent team code from Player or fixture string."""
    if hasattr(fixture_or_player, "next_opponent_short") and fixture_or_player.next_opponent_short:
        return fixture_or_player.next_opponent_short
    fixture_str = getattr(fixture_or_player, "next_fixture", fixture_or_player) if not isinstance(fixture_or_player, str) else fixture_or_player
    if not fixture_str or fixture_str == "BLANK":
        return ""
    m = re.match(r"^([A-Za-z]{3})", fixture_str.strip())
    return m.group(1).upper() if m else ""


def calculate_gk_conflict_penalty(gk: Player, outfield_starters: List[Player], captain_id: Optional[int] = None) -> float:
    """Computes negative covariance / anti-correlation penalty when a goalkeeper
    faces our own starting attackers (MID / FWD).
    Cannibalizes clean sheet points and incurs negative points for goals conceded.
    """
    gk_opp = get_opponent_code(gk)
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


def calculate_defense_concentration_penalty(gk: Player, outfield_defs: List[Player]) -> float:
    """Computes negative covariance penalty when multiple defensive assets from the same team start.
    A single conceded goal destroys clean sheets simultaneously for all defenders/GKs from that club.
    Stacking >= 2 defenders from a mid/lower tier club, especially away from home, is penalized.
    Stacking 3 defenders (GK + 2 DEFs, or 3 DEFs) from the same club carries catastrophic wipeout risk.
    """
    all_defs = ([gk] if gk else []) + list(outfield_defs)
    club_counts = Counter([p.team_short.upper() for p in all_defs if p and p.team_short])
    penalty = 0.0
    for club, count in club_counts.items():
        sample_p = next(p for p in all_defs if p.team_short.upper() == club)
        is_away = not sample_p.next_is_home if hasattr(sample_p, "next_is_home") else ("(A)" in getattr(sample_p, "next_fixture", ""))
        fdr_high = (sample_p.next_fdr >= 3) if hasattr(sample_p, "next_fdr") else any(fdr in getattr(sample_p, "next_fixture", "") for fdr in ["[FDR 3]", "[FDR 4]", "[FDR 5]"])

        if count >= 3:
            # Triple defensive stack: catastrophic clean sheet correlation
            mult = 1.4 if (is_away or fdr_high) else 1.0
            penalty += 3.0 * mult
        elif count == 2:
            # Double defensive stack: penalize if not elite club at home
            if club not in ("ARS", "MCI", "LIV") or is_away or fdr_high:
                penalty += 1.2 if (is_away or fdr_high) else 0.6

    return round(penalty, 2)


from ..analysis.gold_rule_loader import GoldRuleConfig


class LineupSolver:
    """Finds optimal starting XI, captaincy, and bench hierarchy to maximize total xP,
    jointly optimizing goalkeepers with outfielders to eliminate anti-correlation conflicts
    and defensive concentration covariance, incorporating Hindsight Gold Rules.
    """

    def __init__(self, gold_rule_config: Optional[GoldRuleConfig] = None):
        self.gold_rule_config = gold_rule_config

    def solve(
        self,
        squad_15: List[Player],
        gold_rule_config: Optional[GoldRuleConfig] = None
    ) -> LineupSelection:
        config = gold_rule_config or self.gold_rule_config
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
                for cand_defs in itertools.combinations(defs, n_def):
                    cand_mids = mids[:n_mid]
                    cand_fwds = fwds[:n_fwd]
                    cand_outfield = list(cand_defs) + cand_mids + cand_fwds
                    bench_outfield = sorted(
                        [p for p in squad_15 if p.position != "GK" and p.id not in {x.id for x in cand_outfield}],
                        key=lambda x: x.xp,
                        reverse=True
                    )

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

                        # Calculate same-team defense concentration / covariance penalty
                        defense_pen = calculate_defense_concentration_penalty(
                            gk=gk_candidate,
                            outfield_defs=list(cand_defs)
                        )

                        # Gold Rule Formation Bias: reward heavy midfield setups (4-5-1, 3-5-2)
                        formation_bonus = 0.0
                        if config and config.is_active and n_mid == 5:
                            formation_bonus = config.midfield_formation_bonus

                        # Net effective score with anti-correlation, concentration penalties & formation bias
                        score = sum(p.xp for p in current_xi) + tentative_cap.xp - conflict_pen - defense_pen + formation_bonus

                        if score > best_score:
                            best_score = score
                            best_formation = f"{n_def}-{n_mid}-{n_fwd}"
                            best_xi = current_xi
                            best_starting_gk = gk_candidate
                            best_bench_gk = candidate_bench_gk
                            best_bench = ([candidate_bench_gk] if candidate_bench_gk else []) + bench_outfield

        # Captain and Vice-Captain with Talisman, Venue, Clean-Sheet Variance & Dynamic Attacking Threat EV weighting
        def cap_eval(p: Player) -> float:
            ev = p.xp
            is_home = p.next_is_home if hasattr(p, "next_is_home") else ("(H)" in getattr(p, "next_fixture", ""))
            fdr = p.next_fdr if hasattr(p, "next_fdr") else (2 if "[FDR 2]" in getattr(p, "next_fixture", "") else (4 if "[FDR 4]" in getattr(p, "next_fixture", "") or "[FDR 5]" in getattr(p, "next_fixture", "") else 3))

            # Clean Sheet Variance Asymmetry & Dynamic Attacking Threat:
            # GKs and pure CBs carry binary clean-sheet wipeout risk with zero/low attacking ceiling.
            # Elite attacking fullbacks/wing-backs with high xGI (e.g. Trent, Porro, Gvardiol) retain higher ceiling.
            if p.position == "GK":
                ev *= 0.50
            elif p.position == "DEF":
                xgi_90 = (p.expected_goal_involvements / p.minutes * 90.0) if getattr(p, "minutes", 0) >= 90 else 0.0
                if xgi_90 >= 0.25 or getattr(p, "cost", 0.0) >= 7.0:
                    ev *= 0.75  # Elite attacking fullback / set-piece specialist
                elif xgi_90 >= 0.15:
                    ev *= 0.65  # Moderate attacking threat
                elif xgi_90 >= 0.08:
                    ev *= 0.58  # Occasional set-piece target
                else:
                    ev *= 0.50  # Traditional center-back (pure clean-sheet dependency)
            elif p.position in ("MID", "FWD"):
                # Attackers have compounding ceiling (braces, hat-tricks, penalties, bonus)
                ev *= 1.15
                cost = getattr(p, "cost", 0.0)
                form = getattr(p, "form", 0.0)
                mins = getattr(p, "minutes", 0)
                xgi_90 = (getattr(p, "expected_goal_involvements", 0.0) / mins * 90.0) if mins >= 90 else 0.0

                if config and config.is_active:
                    # Gold Rule Captaincy Profile:
                    # Mid-priced explosive assets (£6.0m - £9.0m) with high ceiling, in-form
                    has_explosive_ceiling = (form >= 4.5 or xgi_90 >= 0.35)
                    if 6.0 <= cost <= 9.0 and has_explosive_ceiling:
                        ev *= config.captain_mid_multiplier
                    elif cost >= 10.0:
                        # Only boost premiums if justified by form or easy matchup; otherwise dampen static price bias
                        if form >= 4.5 or fdr <= 2:
                            ev *= 1.05
                        else:
                            ev *= config.captain_premium_bias_dampener
                    elif cost >= 7.5:
                        ev *= 1.03
                else:
                    if cost >= 10.0:
                        ev *= 1.08
                    elif cost >= 7.5:
                        ev *= 1.04

            if is_home:
                ev *= (config.captain_home_multiplier if (config and config.is_active) else 1.06)
            elif not is_home and p.position == "MID":
                ev *= 0.94

            if fdr <= 2:
                ev *= (config.captain_easy_fdr_multiplier if (config and config.is_active) else 1.10)
            elif fdr >= 4:
                ev *= 0.88
            return ev

        sorted_xi = sorted(best_xi, key=cap_eval, reverse=True)
        captain = sorted_xi[0] if sorted_xi else (gks[0] if gks else None)
        vc_cands = [p for p in best_xi if p.id != captain.id]
        vice_captain = sorted(vc_cands, key=cap_eval, reverse=True)[0] if vc_cands else captain

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
