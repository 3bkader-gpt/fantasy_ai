import logging
from typing import Callable, List, Optional, Dict, Any

from ...domain.interfaces.data_repository import IDataRepository
from ...domain.interfaces.fpl_gateway import IFPLGateway
from ...domain.interfaces.xp_engine import IXPEngine
from ...domain.interfaces.optimizer import IOptimizer
from ...domain.interfaces.ai_advisor import IAIAdvisor
from ...domain.interfaces.notifier import INotifier
from ...domain.models.player import Player
from ..dtos.gameweek_dto import GameweekPlanDTO

logger = logging.getLogger("OptimizeGameweekUseCase")


class OptimizeGameweekUseCase:
    """Orchestrates end-to-end squad analysis, optimization, AI consulting, and execution."""

    def __init__(
        self,
        repository: IDataRepository,
        fpl_gateway: IFPLGateway,
        xp_engine: IXPEngine,
        optimizer_factory: Callable[[List[Player]], IOptimizer],
        ai_advisor: IAIAdvisor,
        notifier: INotifier,
        news_service: Optional[Any] = None,
        press_analyst: Optional[Any] = None
    ):
        self.repository = repository
        self.gateway = fpl_gateway
        self.xp_engine = xp_engine
        self.optimizer_factory = optimizer_factory
        self.advisor = ai_advisor
        self.notifier = notifier

        if news_service is None:
            from ...infrastructure.news.premier_league_news import PremierLeagueNewsService
            self.news_service = PremierLeagueNewsService()
        else:
            self.news_service = news_service

        if press_analyst is None:
            from ...infrastructure.ai.press_conference_analyst import PressConferenceAnalyst
            self.press_analyst = PressConferenceAnalyst()
        else:
            self.press_analyst = press_analyst

    def execute(
        self,
        team_id: int,
        dry_run: bool = True,
        max_hits: int = 1,
        horizon_weeks: int = 3,
        horizon_decay: float = 0.85
    ) -> GameweekPlanDTO:
        # 1. Login if possible
        self.gateway.login()

        # 2. Get Gameweek schedule
        current_gw, next_gw, deadline = self.repository.get_current_and_next_gw()
        if next_gw is None:
            next_gw = (current_gw or 1) + 1

        # 3. Get team status and picks
        team_status = self.gateway.get_my_team(team_id)
        raw_picks = team_status.get("picks", [])
        if not raw_picks:
            raise ValueError(f"No squad picks retrieved for team ID {team_id}.")

        bank = team_status.get("bank", 0.0)
        free_transfers = team_status.get("free_transfers", 1)
        rank = team_status.get("rank")
        total_points = team_status.get("total_points", 0)
        team_value = team_status.get("team_value", 100.0)
        chips_available = team_status.get("chips_available", {})
        manager_name = team_status.get("manager_name", "FPL Manager")
        team_name = team_status.get("team_name", "FPL Squad")

        # 4. Compute xP across all players & perform NLP Press Conference Analysis
        all_players = self.repository.get_all_players()
        squad_ids = {pick.get("element") for pick in raw_picks}

        # Track squad members + elite form targets
        tracked_candidates = [
            p for p in all_players 
            if p.id in squad_ids or p.form >= 4.0 or p.selected_by_percent >= 15.0
        ]
        tracked_dicts = [
            {
                "id": p.id,
                "web_name": p.name,
                "team_name": p.team_name,
                "status": p.status,
                "chance_of_playing_next_round": p.chance_of_playing_next_round
            }
            for p in tracked_candidates
        ]

        nlp_insights: Dict[int, Dict[str, Any]] = {}
        try:
            raw_news = self.news_service.fetch_recent_news()
            relevant_news = self.news_service.filter_tactical_and_injury_news(
                raw_news, [p.name for p in tracked_candidates]
            )
            fpl_flags = [
                {
                    "player_id": p.id,
                    "web_name": p.name,
                    "status": p.status,
                    "chance_of_playing": p.chance_of_playing_next_round,
                    "news": p.news
                }
                for p in tracked_candidates if p.news or p.status != "a"
            ]
            if relevant_news or fpl_flags:
                nlp_insights = self.press_analyst.analyze_news(relevant_news, fpl_flags, tracked_dicts)
        except Exception as e:
            logger.warning(f"Error during NLP press conference analysis: {e}")

        team_fixtures = self.repository.get_team_fixtures(next_gw, weeks_ahead=horizon_weeks)
        enriched_players = self.xp_engine.enrich_players_with_horizon_xp(
            players=all_players,
            team_fixtures=team_fixtures,
            next_gw=next_gw,
            weeks_ahead=horizon_weeks,
            decay=horizon_decay,
            nlp_insights=nlp_insights
        )
        players_by_id = {p.id: p for p in enriched_players}


        # Map current squad picks
        current_squad: List[Player] = []
        for pick in raw_picks:
            p_id = pick.get("element")
            if p_id in players_by_id:
                p = players_by_id[p_id]
                p.selling_price = pick.get("selling_price", p.now_cost)
                p.purchase_price = pick.get("purchase_price", p.now_cost)
                current_squad.append(p)

        # 5. Solve optimization (formation, captain, transfers, chips)
        optimizer = self.optimizer_factory(enriched_players)
        plan = optimizer.optimize_transfers(
            current_squad=current_squad,
            bank=bank,
            free_transfers=free_transfers,
            max_hits=max_hits,
            chips_available=chips_available,
            next_gw=next_gw
        )

        # 6. Consult Gemini AI Advisor for tactical briefing
        briefing = self.advisor.generate_briefing(
            gw=next_gw,
            deadline=deadline,
            current_squad=current_squad,
            recommended_transfers=plan.transfers,
            lineup=plan.final_lineup,
            points_gain=plan.net_gain,
            hits_cost=plan.hits_cost,
            bank=plan.new_bank,
            rank=rank,
            chips_available=chips_available,
            chip_recommendation=plan.chip_recommendation,
            market_trends=enriched_players,
            leagues=team_status.get("leagues", [])
        )

        # 7. Execute changes on FPL account if live
        execution_status: Dict[str, Any] = {"dry_run": dry_run}
        if not dry_run:
            if plan.transfers:
                trans_res = self.gateway.make_transfers(team_id=team_id, transfers=plan.transfers, next_gw=next_gw)
                execution_status["transfers"] = trans_res
            lineup_res = self.gateway.set_lineup(team_id=team_id, picks_payload=plan.final_lineup.api_picks)
            execution_status["lineup"] = lineup_res
        else:
            execution_status["transfers"] = {"status": "simulated"}
            execution_status["lineup"] = {"status": "simulated"}

        # 8. Notify via Telegram if configured
        self.notifier.send_gameweek_summary(
            gw=next_gw,
            transfers=plan.transfers,
            lineup=plan.final_lineup,
            briefing_text=briefing,
            dry_run=dry_run
        )

        return GameweekPlanDTO(
            gameweek=next_gw,
            deadline=deadline,
            manager_name=manager_name,
            team_name=team_name,
            rank=rank,
            total_points=total_points,
            team_value=team_value,
            bank=plan.new_bank,
            free_transfers=free_transfers,
            chips_available=chips_available,
            current_squad=current_squad,
            all_players=enriched_players,
            plan=plan,
            briefing=briefing,
            dry_run=dry_run,
            execution_status=execution_status,
            press_conference_insights=list(nlp_insights.values()),
            press_wire=relevant_news[:10] if 'relevant_news' in locals() else []
        )


