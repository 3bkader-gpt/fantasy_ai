from typing import Dict, List, Any, Optional
from src.domain.models.player import Player
from src.domain.models.fixture import Fixture
from src.domain.interfaces.data_repository import IDataRepository
from src.domain.interfaces.fpl_gateway import IFPLGateway
from src.domain.interfaces.ai_advisor import IAIAdvisor
from src.domain.interfaces.notifier import INotifier
from src.infrastructure.xp.rule_engine import RuleBasedXPEngine
from src.infrastructure.optimization import SquadOptimizer
from src.application.use_cases.optimize_gameweek import OptimizeGameweekUseCase


class MockRepository(IDataRepository):
    def get_current_and_next_gw(self):
        return 5, 6, "2026-10-10T10:00:00Z"

    def get_all_players(self, force_refresh=False) -> List[Player]:
        players = []
        pos_map = {
            1: "GK", 2: "GK",
            3: "DEF", 4: "DEF", 5: "DEF", 6: "DEF", 7: "DEF",
            8: "MID", 9: "MID", 10: "MID", 11: "MID", 12: "MID",
            13: "FWD", 14: "FWD", 15: "FWD"
        }
        for i in range(1, 30):
            pos = pos_map.get(i, "MID" if i % 2 == 0 else "DEF")
            p = Player(
                id=i,
                name=f"Player_{i}",
                full_name=f"Player Full {i}",
                position_id={"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}[pos],
                position=pos,
                team_id=(i % 5) + 1,
                team_name=f"Club_{i % 5 + 1}",
                team_short=f"C{i % 5 + 1}",
                cost=5.0 + (i * 0.3),
                now_cost=int((5.0 + (i * 0.3)) * 10),
                minutes=270,
                form=4.0 + (i * 0.1),
                points_per_game=4.5
            )
            players.append(p)
        return players

    def get_team_fixtures(self, next_gw: int, weeks_ahead: int = 3) -> Dict[int, List[Fixture]]:
        return {
            t: [
                Fixture(event=next_gw, is_home=True, opponent_id=99, opponent_name="OPP", difficulty=2),
                Fixture(event=next_gw + 1, is_home=False, opponent_id=98, opponent_name="OPP2", difficulty=3),
                Fixture(event=next_gw + 2, is_home=True, opponent_id=97, opponent_name="OPP3", difficulty=2)
            ]
            for t in range(1, 10)
        }


class MockGateway(IFPLGateway):
    def login(self) -> bool:
        return True

    def get_my_team(self, team_id: int) -> Dict[str, Any]:
        return {
            "is_authenticated": True,
            "picks": [{"element": i, "position": i} for i in range(1, 16)],
            "bank": 1.5,
            "free_transfers": 1,
            "rank": 50000,
            "total_points": 300,
            "team_value": 101.5,
            "chips_available": {"wildcard": 1, "freehit": 1, "3xc": 1, "bboost": 1},
            "manager_name": "Test Manager",
            "team_name": "Test Team",
            "leagues": []
        }

    def set_lineup(self, team_id: int, picks_payload: List[Dict[str, Any]], chip: Optional[str] = None):
        return {"status": "simulated", "code": 200}

    def make_transfers(self, team_id: int, transfers: List[Any], next_gw: int, chip: Optional[str] = None):
        return {"status": "simulated", "code": 200}


class MockAdvisor(IAIAdvisor):
    def generate_briefing(self, **kwargs) -> str:
        return "تقرير تكتيكي تجريبي ناجح."


class MockNotifier(INotifier):
    def send_gameweek_summary(self, **kwargs) -> bool:
        return True

    def send_message(self, message: str) -> bool:
        return True


class MockNewsService:
    def fetch_recent_news(self):
        return []

    def filter_tactical_and_injury_news(self, news, names):
        return []


class MockPressAnalyst:
    def analyze_news(self, news, flags, tracked):
        return {}


def test_optimize_gameweek_pipeline():
    use_case = OptimizeGameweekUseCase(
        repository=MockRepository(),
        fpl_gateway=MockGateway(),
        xp_engine=RuleBasedXPEngine(),
        optimizer_factory=lambda players: SquadOptimizer(players),
        ai_advisor=MockAdvisor(),
        notifier=MockNotifier(),
        news_service=MockNewsService(),
        press_analyst=MockPressAnalyst()
    )

    dto = use_case.execute(
        team_id=10469492,
        dry_run=True,
        max_hits=1,
        horizon_weeks=3,
        horizon_decay=0.85
    )

    assert dto is not None
    assert dto.gameweek == 6
    assert len(dto.current_squad) == 15
    assert dto.plan.final_lineup is not None
    assert len(dto.plan.final_lineup.starting_xi) == 11
    assert len(dto.plan.final_lineup.bench) == 4
    assert dto.plan.final_lineup.captain is not None
    assert dto.plan.final_lineup.vice_captain is not None
    assert dto.briefing == "تقرير تكتيكي تجريبي ناجح."
