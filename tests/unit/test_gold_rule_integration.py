import pytest
from src.domain.models.player import Player
from src.infrastructure.analysis.gold_rule_loader import (
    GoldRuleConfig,
    load_gold_rule_config,
)
from src.infrastructure.optimization.lineup_solver import LineupSolver
from src.infrastructure.optimization.transfer_solver import TransferSolver


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
    minutes: int = 270,
    form: float = 4.0,
    horizon_xp: float = 15.0,
    team_id: int = 1
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
        now_cost=int(cost * 10),
        minutes=minutes,
        expected_goal_involvements=xgi,
        form=form
    )
    p.xp = xp
    p.horizon_xp = horizon_xp
    p.next_fixture = f"{opp} ({'H' if is_home else 'A'}) [FDR {fdr}]"
    p.next_opponent_short = opp
    p.next_is_home = is_home
    p.next_fdr = fdr
    return p


def test_gold_rule_loader_real_and_fallback():
    # 1. Fallback test when file does not exist
    fallback_config = load_gold_rule_config("non_existent_file.json")
    assert not fallback_config.is_active
    assert fallback_config.source_file is None

    # 2. Real file test
    real_config = load_gold_rule_config("output/hindsight_gold_rules.json")
    assert real_config.is_active
    assert real_config.source_file == "output/hindsight_gold_rules.json"
    assert len(real_config.extracted_rules) > 0
    assert real_config.captain_mid_multiplier >= 1.15
    assert real_config.midfield_formation_bonus >= 0.75
    assert real_config.aggressive_hits_enabled is True


def test_lineup_solver_gold_rule_captain_profiling():
    config = GoldRuleConfig(
        is_active=True,
        captain_mid_multiplier=1.20,
        captain_premium_bias_dampener=0.90,
        captain_easy_fdr_multiplier=1.10,
        captain_home_multiplier=1.08
    )

    # Mid-priced explosive midfielder: cost £7.5m, Home, FDR 2, Form 6.0, xGI 0.45, base xP 6.5
    explosive_mid = make_player(
        pid=10, name="Groß", pos="MID", team_short="BHA",
        xp=6.5, opp="SOU", is_home=True, fdr=2, cost=7.5, xgi=0.50, form=6.0
    )

    # Premium forward: cost £14.0m, Away, FDR 4, Form 3.5, base xP 6.8
    premium_fwd = make_player(
        pid=20, name="Haaland", pos="FWD", team_short="MCI",
        xp=6.8, opp="ARS", is_home=False, fdr=4, cost=14.0, xgi=0.30, form=3.5
    )

    squad = [
        make_player(1, "GK1", "GK", "MCI", 4.5),
        make_player(2, "GK2", "GK", "LIV", 4.0),
        make_player(3, "Def1", "DEF", "ARS", 5.0),
        make_player(4, "Def2", "DEF", "LIV", 5.0),
        make_player(5, "Def3", "DEF", "AVL", 4.0),
        make_player(6, "Def4", "DEF", "CRY", 4.0),
        make_player(7, "Def5", "DEF", "BOU", 4.0),
        explosive_mid,
        make_player(11, "Mid2", "MID", "ARS", 5.5),
        make_player(12, "Mid3", "MID", "LIV", 5.0),
        make_player(13, "Mid4", "MID", "AVL", 4.5),
        make_player(14, "Mid5", "MID", "BOU", 4.5),
        premium_fwd,
        make_player(16, "Fwd2", "FWD", "NEW", 5.0),
        make_player(17, "Fwd3", "FWD", "BHA", 4.0),
    ]

    solver = LineupSolver(gold_rule_config=config)
    selection = solver.solve(squad)

    # With Gold Rules active, the explosive mid-priced asset at Home vs FDR 2
    # should be captained over the away premium facing tough FDR
    assert selection.captain.id == explosive_mid.id, (
        f"Expected explosive mid-priced asset ({explosive_mid.name}) to be captain, "
        f"got {selection.captain.name} ({selection.captain.cost}m)"
    )


def test_lineup_solver_formation_bias_heavy_midfield():
    config = GoldRuleConfig(is_active=True, midfield_formation_bonus=1.5)

    # Setup a squad where 5 midfielders are strong and 4-5-1 or 3-5-2 is competitive
    squad = [
        make_player(1, "GK1", "GK", "MCI", 4.5),
        make_player(2, "GK2", "GK", "LIV", 4.0),
        make_player(3, "Def1", "DEF", "ARS", 5.0),
        make_player(4, "Def2", "DEF", "LIV", 5.0),
        make_player(5, "Def3", "DEF", "AVL", 4.5),
        make_player(6, "Def4", "DEF", "CRY", 4.5),
        make_player(7, "Def5", "DEF", "BOU", 4.0),
        make_player(8, "Mid1", "MID", "CHE", 6.0),
        make_player(9, "Mid2", "MID", "ARS", 6.0),
        make_player(10, "Mid3", "MID", "LIV", 5.8),
        make_player(11, "Mid4", "MID", "AVL", 5.5),
        make_player(12, "Mid5", "MID", "BOU", 5.4),
        make_player(13, "Fwd1", "FWD", "MCI", 6.2),
        make_player(14, "Fwd2", "FWD", "NEW", 5.3),
        make_player(15, "Fwd3", "FWD", "BHA", 4.0),
    ]

    solver = LineupSolver(gold_rule_config=config)
    selection = solver.solve(squad)

    # Formation should have 5 midfielders (e.g., 4-5-1 or 3-5-2)
    n_mid = sum(1 for p in selection.starting_xi if p.position == "MID")
    assert n_mid == 5, f"Expected 5 starting midfielders under Gold Rule bias, got {n_mid} (Formation: {selection.formation})"


def test_transfer_solver_aggressive_hit_ev():
    config = GoldRuleConfig(
        is_active=True,
        aggressive_hits_enabled=True,
        hit_hurdle_discount=2.0,
        horizon_hit_weight=0.50,
        max_hits_evaluated=2
    )

    lineup_solver = LineupSolver(gold_rule_config=config)

    # Current squad with an underperforming/injured player
    injured_mid = make_player(
        pid=12, name="InjuredMid", pos="MID", team_short="WHU",
        cost=5.5, xp=1.0, horizon_xp=2.0, minutes=30, form=1.5, team_id=10
    )
    injured_mid.chance_of_playing_next_round = 25

    current_squad = [
        make_player(1, "GK1", "GK", "ARS", 4.0, horizon_xp=12.0, team_id=1),
        make_player(2, "GK2", "GK", "CHE", 3.5, horizon_xp=10.0, team_id=2),
        make_player(3, "Def1", "DEF", "ARS", 4.5, horizon_xp=13.0, team_id=1),
        make_player(4, "Def2", "DEF", "LIV", 4.5, horizon_xp=13.0, team_id=3),
        make_player(5, "Def3", "DEF", "MCI", 4.0, horizon_xp=12.0, team_id=4),
        make_player(6, "Def4", "DEF", "AVL", 4.0, horizon_xp=12.0, team_id=5),
        make_player(7, "Def5", "DEF", "CRY", 3.0, horizon_xp=9.0, team_id=6),
        make_player(8, "Mid1", "MID", "TOT", 5.0, horizon_xp=15.0, team_id=7),
        make_player(9, "Mid2", "MID", "NEW", 4.5, horizon_xp=14.0, team_id=8),
        make_player(10, "Mid3", "MID", "BHA", 4.0, horizon_xp=12.0, team_id=9),
        make_player(11, "Mid4", "MID", "BOU", 3.5, horizon_xp=11.0, team_id=11),
        injured_mid,
        make_player(13, "Fwd1", "FWD", "MCI", 8.0, horizon_xp=24.0, cost=14.0, team_id=4),
        make_player(14, "Fwd2", "FWD", "AVL", 5.0, horizon_xp=15.0, cost=7.5, team_id=5),
        make_player(15, "Fwd3", "FWD", "FUL", 3.0, horizon_xp=9.0, cost=5.5, team_id=12),
    ]

    # Market: Explosive replacement with 7.0 xP and 22.0 horizon xP
    explosive_replacement = make_player(
        pid=18, name="Rogers", pos="MID", team_short="AVL",
        cost=5.5, xp=7.0, horizon_xp=22.0, form=6.5, xgi=0.5, fdr=2, is_home=True, team_id=5
    )

    market = current_squad + [explosive_replacement]
    solver = TransferSolver(
        all_players=market,
        lineup_solver=lineup_solver,
        gold_rule_config=config
    )

    # 0 free transfers, max_hits=1. Under traditional logic, a hit was severely penalized.
    # Under Gold Rules with multi-week horizon & underperformer discount, taking a hit is EV-positive.
    plan = solver.solve(
        current_squad=current_squad,
        bank=0.5,
        free_transfers=0,
        max_hits=1,
        gold_rule_config=config
    )

    assert len(plan.transfers) == 1, "Expected 1 transfer to be triggered"
    assert plan.transfers[0].player_in.id == explosive_replacement.id
    assert plan.transfers[0].player_out.id == injured_mid.id
    assert plan.hits == 1, "Expected 1 hit to be taken"
    assert plan.hits_cost == 4
