from src.domain.models.player import Player
from src.domain.models.fixture import Fixture
from src.infrastructure.xp.rule_engine import RuleBasedXPEngine


def make_player(
    pid: int,
    name: str,
    pos: str,
    status: str = "a",
    chance: int = 100,
    cost: float = 6.0,
    minutes: int = 270,
    form: float = 5.0,
    ppg: float = 5.0,
    xgi: float = 0.0
) -> Player:
    return Player(
        id=pid,
        name=name,
        full_name=name,
        position_id={"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}[pos],
        position=pos,
        team_id=1,
        team_name="Test Club",
        team_short="TST",
        cost=cost,
        now_cost=int(cost * 10),
        status=status,
        chance_of_playing_next_round=chance,
        minutes=minutes,
        form=form,
        points_per_game=ppg,
        expected_goal_involvements=xgi
    )


def test_expected_minutes_availability():
    engine = RuleBasedXPEngine()

    # 1. Ruled out / Injured
    p_injured = make_player(1, "Pedro", "FWD", status="i", chance=0)
    mins = engine.calculate_expected_minutes(p_injured)
    assert mins == 0.0, "Injured player must receive 0 expected minutes."

    # 2. Fully available starter
    p_fit = make_player(2, "Salah", "MID", status="a", chance=100, minutes=360)
    mins_fit = engine.calculate_expected_minutes(p_fit)
    assert mins_fit >= 80.0, f"Fit regular starter should expect >= 80 mins, got {mins_fit}"

    # 3. Doubtful 75%
    p_doubt = make_player(3, "Isak", "FWD", status="d", chance=75, minutes=360)
    mins_doubt = engine.calculate_expected_minutes(p_doubt)
    assert 60.0 <= mins_doubt < mins_fit, f"75% doubtful should receive scaled minutes, got {mins_doubt}"

    # 4. NLP ruled out
    nlp_ruled_out = {"fitness_sentiment": "ruled_out", "minute_multiplier": 0.0}
    mins_nlp = engine.calculate_expected_minutes(p_fit, nlp_insight=nlp_ruled_out)
    assert mins_nlp == 0.0, "NLP ruled_out must force expected minutes to 0."


def test_defender_dynamic_ceiling():
    engine = RuleBasedXPEngine()
    easy_fixture = [Fixture(event=6, is_home=True, opponent_id=2, opponent_name="SOU", difficulty=2)]

    # Pure CB (low xGI, budget price)
    cb = make_player(4, "Burn", "DEF", cost=4.5, minutes=360, form=8.0, ppg=8.0, xgi=0.02)
    cb_xp = engine.calculate_player_xp(cb, easy_fixture)
    assert cb_xp <= 6.5, f"Pure CB should be capped at 6.5 xP, got {cb_xp}"

    # Elite attacking fullback (high xGI >= 0.20 or expensive)
    fb = make_player(5, "Alexander-Arnold", "DEF", cost=7.2, minutes=360, form=8.0, ppg=8.0, xgi=0.35)
    fb_xp = engine.calculate_player_xp(fb, easy_fixture)
    assert fb_xp <= 7.5, f"Attacking fullback should be capped at 7.5 xP, got {fb_xp}"
    assert fb_xp > 6.5, f"Elite attacking fullback should be allowed to exceed 6.5 xP, got {fb_xp}"


def test_horizon_enrichment_decay():
    engine = RuleBasedXPEngine()
    p = make_player(6, "Palmer", "MID", cost=10.5, minutes=360, form=6.0, ppg=6.0, xgi=0.5)

    fixtures_by_team = {
        1: [
            Fixture(event=6, is_home=True, opponent_id=2, opponent_name="BOU", difficulty=2),
            Fixture(event=7, is_home=False, opponent_id=3, opponent_name="LIV", difficulty=4),
            Fixture(event=8, is_home=True, opponent_id=4, opponent_name="NFO", difficulty=2),
        ]
    }

    enriched = engine.enrich_players_with_horizon_xp(
        players=[p],
        team_fixtures=fixtures_by_team,
        next_gw=6,
        weeks_ahead=3,
        decay=0.85
    )

    player = enriched[0]
    assert player.xp > 0.0
    assert player.horizon_xp > player.xp, "Horizon xP across 3 gameweeks should exceed single gameweek xP."
    assert player.next_opponent_short == "BOU"
    assert player.next_is_home is True
    assert player.next_fdr == 2
