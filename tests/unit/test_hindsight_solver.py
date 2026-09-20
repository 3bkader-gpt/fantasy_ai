import pytest
from src.domain.models.hindsight_models import PlayerGameweekRecord
from src.infrastructure.optimization.hindsight_solver import HindsightSolver


def create_synthetic_player_pool():
    """Create a minimal valid pool of 20 players for 2 gameweeks to test ILP constraints.
    Positions:
    - GK: 3 players (id 1, 2, 3)
    - DEF: 7 players (id 4..10)
    - MID: 7 players (id 11..17)
    - FWD: 4 players (id 18..21)
    """
    player_points = {1: [], 2: []}

    # 1: GK (need 2 in squad, 1 starts)
    # 2: DEF (need 5 in squad, 3-5 start)
    # 3: MID (need 5 in squad, 2-5 start)
    # 4: FWD (need 3 in squad, 1-3 start)
    specs = [
        # (id, pos, team, price, gw1_pts, gw2_pts)
        (1, 1, 1, 5.0, 6, 2),
        (2, 1, 2, 4.5, 2, 7),
        (3, 1, 3, 4.0, 0, 0),
        (4, 2, 1, 5.5, 8, 2),
        (5, 2, 2, 5.0, 6, 6),
        (6, 2, 3, 4.5, 2, 9),
        (7, 2, 4, 4.5, 5, 2),
        (8, 2, 5, 4.0, 1, 1),
        (9, 2, 6, 4.0, 0, 8),
        (10, 2, 7, 4.0, 0, 0),
        (11, 3, 1, 10.0, 15, 3),  # Premium MID
        (12, 3, 2, 8.5, 7, 12),  # Mid MID
        (13, 3, 3, 7.0, 5, 5),
        (14, 3, 4, 6.0, 6, 2),
        (15, 3, 5, 5.5, 3, 10),
        (16, 3, 6, 4.5, 2, 2),
        (17, 3, 7, 4.5, 1, 1),
        (18, 4, 1, 12.0, 13, 16), # Premium FWD (Monster points)
        (19, 4, 2, 7.5, 8, 2),
        (20, 4, 3, 5.5, 2, 9),
        (21, 4, 4, 4.5, 1, 1),
    ]

    for p_id, pos, team, price, gw1_pts, gw2_pts in specs:
        player_points[1].append(
            PlayerGameweekRecord(
                player_id=p_id,
                gameweek=1,
                total_points=gw1_pts,
                minutes=90 if gw1_pts > 0 else 0,
                goals_scored=1 if gw1_pts > 5 else 0,
                assists=0,
                clean_sheets=1 if pos <= 2 and gw1_pts >= 6 else 0,
                bonus=3 if gw1_pts >= 10 else 0,
                was_home=True,
                opponent_id=team + 1,
                opponent_short="OPP",
                fixture_difficulty=2,
                price=price,
                element_type=pos,
                web_name=f"Player_{p_id}",
                team_id=team,
            )
        )
        player_points[2].append(
            PlayerGameweekRecord(
                player_id=p_id,
                gameweek=2,
                total_points=gw2_pts,
                minutes=90 if gw2_pts > 0 else 0,
                goals_scored=1 if gw2_pts > 5 else 0,
                assists=0,
                clean_sheets=1 if pos <= 2 and gw2_pts >= 6 else 0,
                bonus=3 if gw2_pts >= 10 else 0,
                was_home=False,
                opponent_id=team + 1,
                opponent_short="OPP",
                fixture_difficulty=3,
                price=price,
                element_type=pos,
                web_name=f"Player_{p_id}",
                team_id=team,
            )
        )

    return player_points


def test_hindsight_solver_constraints():
    """Verify that HindsightSolver strictly enforces all FPL constraints across multiple gameweeks."""
    player_points = create_synthetic_player_pool()
    solver = HindsightSolver(time_limit_seconds=10.0)

    result = solver.solve(
        player_points=player_points,
        gw_start=1,
        gw_end=2,
        initial_budget=100.0,
    )

    assert result.gameweek_range == (1, 2)
    assert len(result.decisions) == 2

    # Map player metadata
    p_map = {r.player_id: r for r in player_points[1]}

    for d in result.decisions:
        # 1. Squad size = 15, Starting XI = 11, Bench = 4
        assert len(d.squad_15) == 15
        assert len(d.starting_xi) == 11
        assert len(d.bench) == 4
        assert set(d.starting_xi).union(set(d.bench)) == set(d.squad_15)

        # 2. Positional quotas
        gks = [p for p in d.squad_15 if p_map[p].element_type == 1]
        defs = [p for p in d.squad_15 if p_map[p].element_type == 2]
        mids = [p for p in d.squad_15 if p_map[p].element_type == 3]
        fwds = [p for p in d.squad_15 if p_map[p].element_type == 4]

        assert len(gks) == 2
        assert len(defs) == 5
        assert len(mids) == 5
        assert len(fwds) == 3

        # 3. Starting XI formation quotas
        s_gks = [p for p in d.starting_xi if p_map[p].element_type == 1]
        s_defs = [p for p in d.starting_xi if p_map[p].element_type == 2]
        s_mids = [p for p in d.starting_xi if p_map[p].element_type == 3]
        s_fwds = [p for p in d.starting_xi if p_map[p].element_type == 4]

        assert len(s_gks) == 1
        assert 3 <= len(s_defs) <= 5
        assert 2 <= len(s_mids) <= 5
        assert 1 <= len(s_fwds) <= 3

        # 4. Captain in starting XI
        assert d.captain_id in d.starting_xi

        # 5. Bank non-negative
        assert d.bank >= 0.0

    # 6. Squad transition between GW1 and GW2
    d1, d2 = result.decisions[0], result.decisions[1]
    squad1 = set(d1.squad_15)
    squad2 = set(d2.squad_15)

    transferred_in = set(d2.transfers_in)
    transferred_out = set(d2.transfers_out)

    assert len(transferred_in) == len(transferred_out)
    assert squad2 == (squad1 - transferred_out).union(transferred_in)


def test_hindsight_solver_captain_maximization():
    """Verify that captain is the highest scoring player in starting XI."""
    player_points = create_synthetic_player_pool()
    solver = HindsightSolver(time_limit_seconds=10.0)

    result = solver.solve(
        player_points=player_points,
        gw_start=1,
        gw_end=2,
        initial_budget=100.0,
    )

    for d in result.decisions:
        gw = d.gameweek
        pts_map = {r.player_id: r.total_points for r in player_points[gw]}

        cap_pts = pts_map[d.captain_id]
        starter_pts = [pts_map[p] for p in d.starting_xi]

        # Captain must have maximum points among all starting XI players
        assert cap_pts == max(starter_pts)
