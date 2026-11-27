from src.domain.models.player import Player
from src.domain.models.fixture import Fixture
from src.infrastructure.xp.team_strength import TeamStrengthModel
from src.infrastructure.xp.probabilistic_engine import ProbabilisticXPEngine
from src.infrastructure.odds.market_odds import MarketOddsService, _solve_match_lambdas_from_odds


def _make_player(
    pid, name, pos, team_id, team_short, cost,
    xg90=0.0, xa90=0.0, saves90=0.0, defcon90=0.0, bps=200,
    penalties_order=None, minutes=900, status="a", form=5.0
):
    pos_id = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}[pos]
    return Player(
        id=pid,
        name=name,
        full_name=name,
        position=pos,
        position_id=pos_id,
        team_id=team_id,
        team_name=team_short,
        team_short=team_short,
        cost=cost,
        now_cost=int(cost * 10),
        minutes=minutes,
        starts=minutes // 90,
        starts_per_90=1.0 if minutes >= 90 else 0.0,
        form=form,
        points_per_game=form,
        total_points=50,
        status=status,
        expected_goals=xg90 * (minutes / 90.0),
        expected_assists=xa90 * (minutes / 90.0),
        expected_goal_involvements=(xg90 + xa90) * (minutes / 90.0),
        expected_goals_per_90=xg90,
        expected_assists_per_90=xa90,
        saves_per_90=saves90,
        defensive_contribution_per_90=defcon90,
        bps=bps,
        penalties_order=penalties_order,
    )


def test_team_strength_model_ranks_strong_over_weak():
    fixtures = [
        {"event": 1, "finished": True, "team_h": 1, "team_a": 2, "team_h_score": 3, "team_a_score": 0},
        {"event": 2, "finished": True, "team_h": 1, "team_a": 2, "team_h_score": 2, "team_a_score": 0},
        {"event": 3, "finished": True, "team_h": 2, "team_a": 1, "team_h_score": 0, "team_a_score": 3},
    ]
    model = TeamStrengthModel(raw_fixtures=fixtures)
    lam_for, lam_ag = model.predict_match_lambdas(team_id=1, opponent_id=2, is_home=True)
    assert lam_for > lam_ag
    assert lam_for > 1.5


def test_odds_lambda_inversion():
    # Heavy home favorite (70% win, 18% draw, 12% away, 2.8 total goals)
    lh, la = _solve_match_lambdas_from_odds(0.70, 0.18, 0.12, total_goals=2.8)
    assert lh > la
    assert abs((lh + la) - 2.8) < 0.05


def test_probabilistic_engine_defcon_and_penalties():
    engine = ProbabilisticXPEngine(use_market_odds=False)
    engine._fitted = True  # Use clean FDR fallback

    fix = Fixture(event=12, opponent_id=2, opponent_name="OPP", is_home=True, difficulty=3)
    cb_high_defcon = _make_player(1, "DefConCB", "DEF", 1, "T1", 5.0, xg90=0.05, defcon90=13.0)
    cb_low_defcon = _make_player(2, "LowCB", "DEF", 1, "T1", 5.0, xg90=0.05, defcon90=4.0)

    xp_hi = engine.calculate_player_xp(cb_high_defcon, [fix])
    xp_lo = engine.calculate_player_xp(cb_low_defcon, [fix])
    assert xp_hi > xp_lo + 1.0
    assert cb_high_defcon.expected_defcon_pts > 1.2

    fwd_pen = _make_player(3, "PenFWD", "FWD", 1, "T1", 8.0, xg90=0.45, penalties_order=1)
    fwd_nopen = _make_player(4, "NoPenFWD", "FWD", 1, "T1", 8.0, xg90=0.45, penalties_order=None)
    assert engine.calculate_player_xp(fwd_pen, [fix]) > engine.calculate_player_xp(fwd_nopen, [fix])


def test_probabilistic_engine_market_scorer_and_gk_saves():
    odds = MarketOddsService(api_key="", enable_player_props=False)
    odds.match_odds = {("ARS", "WOL"): {"lam_h": 2.4, "lam_a": 0.6}}
    odds.player_scorer_odds = {
        "star striker": {"raw_name": "Star Striker", "match_teams": ["ARS", "WOL"], "p_score": 0.55, "lam_goals": 0.80}
    }
    engine = ProbabilisticXPEngine(market_odds=odds, use_market_odds=True)
    engine._fitted = True
    engine._odds_loaded = True

    fix = Fixture(event=12, opponent_id=2, opponent_name="WOL", is_home=True, difficulty=2)
    striker = _make_player(10, "Star Striker", "FWD", 1, "ARS", 11.0, xg90=0.60, xa90=0.15)
    xp = engine.calculate_player_xp(striker, [fix], is_next_gw=True)
    assert xp >= 6.0
    assert striker.market_scorer_prob == 0.55

    gk_high = _make_player(20, "ShotStopper", "GK", 2, "WOL", 4.5, saves90=5.0)
    gk_low = _make_player(21, "IdleGK", "GK", 2, "WOL", 4.5, saves90=1.2)
    fix_away = Fixture(event=12, opponent_id=1, opponent_name="ARS", is_home=False, difficulty=5)
    assert engine.calculate_player_xp(gk_high, [fix_away]) > engine.calculate_player_xp(gk_low, [fix_away]) + 0.5
