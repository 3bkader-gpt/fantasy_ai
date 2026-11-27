from datetime import datetime, timedelta, timezone
from src.domain.models.player import Player
from src.domain.models.squad import LineupSelection
from src.infrastructure.optimization.lineup_solver import LineupSolver
from src.infrastructure.optimization.transfer_solver import TransferSolver
from src.infrastructure.optimization.chip_evaluator import ChipEvaluator
from src.infrastructure.analysis.gold_rule_loader import GoldRuleConfig


def _make_player(pid, name, pos, team_id, cost, xp, horizon_xp=None, status="a", expected_minutes=90.0):
    pos_id_map = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}
    return Player(
        id=pid,
        name=name,
        full_name=name,
        position=pos,
        position_id=pos_id_map[pos],
        team_id=team_id,
        team_name=f"Team {team_id}",
        team_short=f"T{team_id}",
        cost=cost,
        now_cost=int(cost * 10),
        form=5.0,
        points_per_game=5.0,
        total_points=50,
        minutes=900,
        status=status,
        xp=xp,
        horizon_xp=horizon_xp if horizon_xp is not None else xp * 2.5,
        expected_minutes=expected_minutes,
    )


def _make_squad():
    return [
        _make_player(1, "GK1", "GK", 1, 5.0, 4.5),
        _make_player(2, "GK2", "GK", 2, 4.5, 4.0),
        _make_player(3, "DEF1", "DEF", 1, 5.5, 5.0),
        _make_player(4, "DEF2", "DEF", 2, 5.0, 4.8),
        _make_player(5, "DEF3", "DEF", 3, 5.0, 4.6),
        _make_player(6, "DEF4", "DEF", 4, 4.5, 4.0),
        _make_player(7, "DEF5", "DEF", 5, 4.5, 3.8),
        _make_player(8, "MID1", "MID", 3, 9.0, 7.0),
        _make_player(9, "MID2", "MID", 4, 8.0, 6.5),
        _make_player(10, "MID3", "MID", 5, 7.5, 6.0),
        _make_player(11, "MID4", "MID", 6, 6.5, 5.5),
        _make_player(12, "MID5", "MID", 7, 5.5, 4.2),
        _make_player(13, "FWD1", "FWD", 6, 10.0, 8.0),
        _make_player(14, "FWD2", "FWD", 7, 8.0, 6.0),
        _make_player(15, "FWD3", "FWD", 8, 6.0, 4.5),
    ]


def test_transfer_solver_blocks_hits_when_max_hits_zero():
    squad = _make_squad()
    star_in = _make_player(99, "StarMid", "MID", 9, 5.5, 9.5, horizon_xp=25.0)
    solver = TransferSolver(all_players=squad + [star_in], lineup_solver=LineupSolver())
    plan = solver.solve(
        current_squad=squad,
        bank=2.0,
        free_transfers=0,
        max_hits=0,
        gold_rule_config=GoldRuleConfig(is_active=True),
    )
    assert len(plan.transfers) == 0
    assert plan.hits == 0
    assert plan.hits_cost == 0


def test_chip_evaluator_urgency_before_gw19():
    squad = _make_squad()
    lineup = LineupSolver().solve(squad)
    evaluator = ChipEvaluator()
    chips = {"bboost": 1, "3xc": 1, "freehit": 1, "wildcard": 1}

    # GW16: 4 GWs left (16, 17, 18, 19) with 4 chips -> urgency mode active
    res = evaluator.evaluate(squad_15=squad, lineup=lineup, chips_available=chips, next_gw=16)
    assert res["urgent_window"] is True
    assert res["gws_remaining_in_half"] == 4
    assert res["auto_activate_chip"] in ("bboost", "3xc")
