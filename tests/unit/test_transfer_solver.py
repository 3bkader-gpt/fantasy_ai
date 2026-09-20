from src.domain.models.player import Player
from src.infrastructure.optimization.lineup_solver import LineupSolver
from src.infrastructure.optimization.transfer_solver import TransferSolver


def make_player(
    pid: int,
    name: str,
    pos: str,
    team_id: int,
    team_short: str,
    cost: float,
    xp: float,
    horizon_xp: float
) -> Player:
    p = Player(
        id=pid,
        name=name,
        full_name=name,
        position_id={"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}[pos],
        position=pos,
        team_id=team_id,
        team_name=team_short,
        team_short=team_short,
        cost=cost,
        now_cost=int(cost * 10)
    )
    p.xp = xp
    p.horizon_xp = horizon_xp
    p.next_fixture = "OPP (H) [FDR 3]"
    p.next_opponent_short = "OPP"
    p.next_is_home = True
    p.next_fdr = 3
    return p


def test_transfer_solver_respects_budget_and_club_limits():
    lineup_solver = LineupSolver()

    # Current squad with 15 players
    current_squad = [
        make_player(1, "GK1", "GK", 1, "ARS", 5.0, 4.0, 12.0),
        make_player(2, "GK2", "GK", 2, "CHE", 4.0, 3.5, 10.0),
        make_player(3, "Def1", "DEF", 1, "ARS", 5.0, 4.5, 13.0),
        make_player(4, "Def2", "DEF", 1, "ARS", 5.5, 4.5, 13.0),  # Already 3 ARS players (GK1, Def1, Def2)
        make_player(5, "Def3", "DEF", 3, "LIV", 5.0, 4.0, 12.0),
        make_player(6, "Def4", "DEF", 4, "MCI", 5.0, 4.0, 12.0),
        make_player(7, "Def5", "DEF", 5, "AVL", 4.0, 3.0, 9.0),
        make_player(8, "Mid1", "MID", 6, "TOT", 7.0, 5.0, 15.0),
        make_player(9, "Mid2", "MID", 7, "NEW", 6.5, 4.5, 14.0),
        make_player(10, "Mid3", "MID", 8, "BHA", 6.0, 4.0, 12.0),
        make_player(11, "Mid4", "MID", 9, "BOU", 5.5, 3.5, 11.0),
        make_player(12, "Mid5", "MID", 10, "WHU", 4.5, 2.5, 7.0),
        make_player(13, "Fwd1", "FWD", 4, "MCI", 14.0, 8.0, 24.0),
        make_player(14, "Fwd2", "FWD", 5, "AVL", 7.5, 5.0, 15.0),
        make_player(15, "Fwd3", "FWD", 11, "FUL", 5.5, 3.0, 9.0),
    ]

    # Market candidates:
    # 1. An expensive player we cannot afford (cost 10.0, bank is only 0.5, selling player is 4.5 -> max budget 5.0)
    expensive_mid = make_player(16, "Saka", "MID", 1, "ARS", 10.0, 8.0, 24.0)
    # 2. A 4th ARS player (would violate 3 per club if replacing non-ARS player)
    fourth_ars_mid = make_player(17, "Martinelli", "MID", 1, "ARS", 7.0, 6.0, 18.0)
    # 3. An affordable, legal improvement
    affordable_mid = make_player(18, "Rogers", "MID", 5, "AVL", 5.0, 5.5, 16.0)

    market = current_squad + [expensive_mid, fourth_ars_mid, affordable_mid]
    solver = TransferSolver(all_players=market, lineup_solver=lineup_solver)

    plan = solver.solve(
        current_squad=current_squad,
        bank=0.5,
        free_transfers=1,
        max_hits=0
    )

    if plan.transfers:
        t = plan.transfers[0]
        # Must not be the unaffordable player
        assert t.player_in.id != expensive_mid.id, "Solver recommended unaffordable player."
        # Verify remaining bank is >= 0
        assert plan.new_bank >= 0.0, f"Remaining bank must be non-negative, got {plan.new_bank}"
        # Verify club limit
        team_counts = {}
        for p in plan.new_players:
            team_counts[p.team_id] = team_counts.get(p.team_id, 0) + 1
        assert all(c <= 3 for c in team_counts.values()), "Exceeded max 3 players per club constraint."
