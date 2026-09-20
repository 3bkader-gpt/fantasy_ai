from src.domain.models.player import Player
from src.infrastructure.optimization.lineup_solver import (
    LineupSolver,
    calculate_gk_conflict_penalty,
    calculate_defense_concentration_penalty
)


def make_player(
    pid: int,
    name: str,
    pos: str,
    team_short: str,
    xp: float,
    opp: str = "CHE",
    is_home: bool = True,
    fdr: int = 3,
    cost: float = 6.0,
    xgi: float = 0.0,
    minutes: int = 270
) -> Player:
    p = Player(
        id=pid,
        name=name,
        full_name=name,
        position_id={"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}[pos],
        position=pos,
        team_id=pid,
        team_name=team_short,
        team_short=team_short,
        cost=cost,
        now_cost=int(cost * 10),
        minutes=minutes,
        expected_goal_involvements=xgi
    )
    p.xp = xp
    p.next_fixture = f"{opp} ({'H' if is_home else 'A'}) [FDR {fdr}]"
    p.next_opponent_short = opp
    p.next_is_home = is_home
    p.next_fdr = fdr
    return p


def test_gk_conflict_penalty():
    # GK from NFO facing ARS away
    gk = make_player(1, "Sels", "GK", "NFO", 4.0, opp="ARS", is_home=False, fdr=4)
    # Starting attacker from ARS
    attacker = make_player(2, "Saka", "MID", "ARS", 6.5, opp="NFO", is_home=True, fdr=2)
    
    pen = calculate_gk_conflict_penalty(gk, [attacker], captain_id=None)
    assert pen > 0.0, "Expected positive conflict penalty when GK faces own starting attacker."

    # When attacker is captain, penalty should be amplified (1.8x)
    cap_pen = calculate_gk_conflict_penalty(gk, [attacker], captain_id=2)
    assert cap_pen > pen, "Expected amplified conflict penalty when opponent attacker is captain."


def test_defense_concentration_penalty():
    # Two defenders from same non-elite team away from home
    d1 = make_player(3, "Greaves", "DEF", "IPS", 4.0, opp="NEW", is_home=False, fdr=4)
    d2 = make_player(4, "Davis", "DEF", "IPS", 4.2, opp="NEW", is_home=False, fdr=4)

    pen = calculate_defense_concentration_penalty(None, [d1, d2])
    assert pen >= 1.2, f"Expected double stack penalty of at least 1.2, got {pen}"


def test_captain_choice_prefers_high_ceiling_attackers():
    # Traditional CB with 7.0 base xP (e.g. Tarkowski) vs Midfielder with 6.5 base xP (e.g. Palmer)
    cb = make_player(5, "Tarkowski", "DEF", "EVE", 7.0, opp="LEI", is_home=True, fdr=2, cost=5.5, xgi=0.05)
    mid = make_player(6, "Palmer", "MID", "CHE", 6.5, opp="WHU", is_home=True, fdr=2, cost=10.5, xgi=0.60)

    # 15-man squad dummy setup
    squad = [
        make_player(1, "GK1", "GK", "MCI", 4.5),
        make_player(2, "GK2", "GK", "LIV", 4.0),
        cb,
        make_player(7, "Def2", "DEF", "ARS", 5.0),
        make_player(8, "Def3", "DEF", "LIV", 5.0),
        make_player(9, "Def4", "DEF", "AVL", 4.0),
        make_player(10, "Def5", "DEF", "CRY", 4.0),
        mid,
        make_player(11, "Mid2", "MID", "ARS", 6.0),
        make_player(12, "Mid3", "MID", "LIV", 5.5),
        make_player(13, "Mid4", "MID", "AVL", 5.0),
        make_player(14, "Mid5", "MID", "BOU", 4.5),
        make_player(15, "Fwd1", "FWD", "MCI", 7.5, cost=14.0, xgi=0.8),
        make_player(16, "Fwd2", "FWD", "NEW", 6.0, cost=8.0, xgi=0.4),
        make_player(17, "Fwd3", "FWD", "BHA", 4.0),
    ]

    solver = LineupSolver()
    selection = solver.solve(squad)

    # Captain must NOT be the pure CB despite having 7.0 base xP
    assert selection.captain.id != cb.id, "Pure CB must not be captain when elite attackers are available."
    assert selection.captain.position in ("MID", "FWD"), "Captain should be an attacker with compounding ceiling."


def test_valid_formation_and_counts():
    squad = [
        make_player(1, "GK1", "GK", "MCI", 4.5),
        make_player(2, "GK2", "GK", "LIV", 4.0),
        make_player(3, "Def1", "DEF", "ARS", 5.0),
        make_player(4, "Def2", "DEF", "LIV", 5.0),
        make_player(5, "Def3", "DEF", "MCI", 4.5),
        make_player(6, "Def4", "DEF", "AVL", 4.0),
        make_player(7, "Def5", "DEF", "CRY", 4.0),
        make_player(8, "Mid1", "MID", "CHE", 6.5),
        make_player(9, "Mid2", "MID", "ARS", 6.0),
        make_player(10, "Mid3", "MID", "LIV", 5.5),
        make_player(11, "Mid4", "MID", "AVL", 5.0),
        make_player(12, "Mid5", "MID", "BOU", 4.5),
        make_player(13, "Fwd1", "FWD", "MCI", 7.5),
        make_player(14, "Fwd2", "FWD", "NEW", 6.0),
        make_player(15, "Fwd3", "FWD", "BHA", 4.0),
    ]
    solver = LineupSolver()
    selection = solver.solve(squad)

    assert len(selection.starting_xi) == 11
    assert len(selection.bench) == 4
    assert len(selection.api_picks) == 15
    assert selection.captain is not None
    assert selection.vice_captain is not None
    assert selection.captain.id != selection.vice_captain.id
