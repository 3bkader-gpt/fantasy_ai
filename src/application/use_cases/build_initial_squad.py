import logging
from typing import List, Optional

from ...domain.interfaces.data_repository import IDataRepository
from ...domain.interfaces.xp_engine import IXPEngine
from ...domain.interfaces.ai_advisor import IAIAdvisor
from ...domain.models.squad import LineupSelection
from ...infrastructure.optimization.initial_squad_builder import InitialSquadBuilder
from ..dtos.initial_squad_dto import InitialSquadDTO

logger = logging.getLogger("BuildInitialSquadUseCase")


class BuildInitialSquadUseCase:
    """Orchestrates building the optimal initial 15-man squad from scratch

    using mathematical Two-Tier MILP optimization and tactical AI review.
    """

    def __init__(
        self,
        repository: IDataRepository,
        xp_engine: IXPEngine,
        advisor: IAIAdvisor
    ):
        self.repository = repository
        self.xp_engine = xp_engine
        self.advisor = advisor
        self.squad_builder = InitialSquadBuilder()

    def execute(
        self,
        budget: float = 100.0,
        max_bench_budget: float = 17.5,
        horizon_weeks: int = 3,
        horizon_decay: float = 0.85,
        min_starter_chance: int = 75,
        locked_player_ids: Optional[List[int]] = None
    ) -> InitialSquadDTO:
        # 1. Fetch schedule
        current_gw, next_gw, deadline = self.repository.get_current_and_next_gw()
        if next_gw is None:
            next_gw = (current_gw or 1) + 1

        # 2. Enrich players with live data (bypassing cache) and Expected Minutes
        all_players = self.repository.get_all_players(force_refresh=True)
        team_fixtures = self.repository.get_team_fixtures(next_gw, weeks_ahead=horizon_weeks)
        enriched = self.xp_engine.enrich_players_with_horizon_xp(
            players=all_players,
            team_fixtures=team_fixtures,
            next_gw=next_gw,
            weeks_ahead=horizon_weeks,
            decay=horizon_decay
        )

        # 3. Solve initial squad via Two-Tier MILP
        sol = self.squad_builder.solve(
            enriched,
            budget=budget,
            max_bench_budget=max_bench_budget,
            min_starter_chance=min_starter_chance,
            locked_player_ids=locked_player_ids
        )

        starters = sol["starters"]
        bench = sol["bench"]
        captain = sol["captain"]
        vice_captain = sol["vice_captain"]
        formation = sol["formation"]
        squad_15 = sol["squad_15"]

        starters_cost = round(sum(p.cost for p in starters), 1)
        bench_cost = round(sum(p.cost for p in bench), 1)
        total_cost = round(starters_cost + bench_cost, 1)
        remaining_bank = round(budget - total_cost, 1)
        total_horizon_xp = round(sum(p.horizon_xp for p in squad_15), 2)
        total_starters_xp = round(sum(p.xp for p in starters) + captain.xp, 2)

        lineup = LineupSelection(
            formation=formation,
            total_expected_points=total_starters_xp,
            starting_xi=starters,
            bench=bench,
            captain=captain,
            vice_captain=vice_captain,
            api_picks=[]
        )

        # 4. Generate Tactical Briefing via Gemini
        prompt = f"""
تحليل تشكيلة البداية الكاملة المقترحة (Initial Squad - Draft 1):
- الجولة المستهدفة: {next_gw} | موعد الديدلاين: {deadline or 'قريباً'}
- ميزانية الأساسيين (Starting XI): £{starters_cost}m | ميزانية البدلاء (Bench): £{bench_cost}m
- إجمالي الميزانية المستهلكة: £{total_cost}m من £{budget}m (المتبقي في البنك: £{remaining_bank}m)
- إجمالي النقاط المتوقعة لأفق 3 جولات (3-GW Horizon xP): {total_horizon_xp:.1f} نقطة

التشكيل الأساسي ({lineup.formation}):
{', '.join([f"{p.name} ({p.team_short} - £{p.cost}m)" for p in lineup.starting_xi])}

شارة القيادة:
- الكابتن (C): {lineup.captain.name} ({lineup.captain.team_short}) - xP: {lineup.captain.xp:.1f} | 3-GW: {lineup.captain.horizon_xp:.1f}
- النائب (VC): {lineup.vice_captain.name} ({lineup.vice_captain.team_short}) - xP: {lineup.vice_captain.xp:.1f}

دكة البدلاء (Bench Enablers - £{bench_cost}m):
{', '.join([f"{p.name} ({p.position} - £{p.cost}m)" for p in lineup.bench])}

المطلوب:
اكتب تحليلاً شاملاً باللغة العربية يشمل:
1. الفلسفة العامة لبناء هذا التشكيل (توزيع الميزانية الصارم: Power 11 £{starters_cost}m مقابل دكة اقتصادية £{bench_cost}m).
2. تقييم مفصل لخطوط الفريق (حراسة المرمى، الدفاع، الوسط، والهجوم).
3. أسباب اختيار الكابتن ونائب الكابتن للجولة {next_gw}.
4. نصائح للمستقبل وخارطة الطريق للـ 3 جولات القادمة.
"""
        system_instruction = (
            "أنت الخبير الفني الأعلى كفاءة لفانتازي الدوري الإنجليزي (FPL Autonomous AI Architect).\n"
            "مهمتك تقييم التشكيلة الافتتاحية للموسم بدقة وموضوعية رياضية وتكتيكية كروية فذة."
        )
        briefing = self.advisor._call_gemini(prompt, system_instruction) if hasattr(self.advisor, "_call_gemini") else "تم توليد التشكيلة بنجاح."

        return InitialSquadDTO(
            target_gameweek=next_gw,
            deadline=deadline,
            total_cost=total_cost,
            starters_cost=starters_cost,
            bench_cost=bench_cost,
            remaining_bank=remaining_bank,
            total_squad_horizon_xp=total_horizon_xp,
            all_squad_players=squad_15,
            lineup=lineup,
            briefing=briefing
        )
