import logging
from pathlib import Path
from typing import Optional, Tuple, List

from ...infrastructure.fpl.historical_collector import HistoricalDataCollector
from ...infrastructure.fpl.repository import FPLDataRepository
from ...infrastructure.optimization.hindsight_solver import HindsightSolver
from ...infrastructure.analysis.gold_rule_extractor import GoldRuleExtractor
from ...presentation.hindsight_presenter import HindsightPresenter
from ...domain.models.hindsight_models import HindsightResult, GoldRule

logger = logging.getLogger("RunHindsightUseCase")


class RunHindsightUseCase:
    """Orchestrates the hindsight optimization pipeline:
    1. Collect actual player performance data across played gameweeks.
    2. Solve multi-period ILP to find the absolute maximum point path.
    3. Extract statistical Gold Rules from the optimal path.
    4. Present results to console and export structured JSON.
    """

    def __init__(
        self,
        collector: Optional[HistoricalDataCollector] = None,
        solver: Optional[HindsightSolver] = None,
        extractor: Optional[GoldRuleExtractor] = None,
        presenter: Optional[HindsightPresenter] = None,
        repository: Optional[FPLDataRepository] = None,
    ):
        self.repo = repository or FPLDataRepository()
        self.collector = collector or HistoricalDataCollector(repository=self.repo)
        self.solver = solver or HindsightSolver()
        self.extractor = extractor or GoldRuleExtractor()
        self.presenter = presenter or HindsightPresenter()

    def execute(
        self,
        gw_start: Optional[int] = 1,
        gw_end: Optional[int] = None,
        initial_budget: float = 100.0,
        export_json: bool = True,
        output_filename: str = "hindsight_gold_rules.json",
    ) -> Tuple[HindsightResult, List[GoldRule], Optional[Path]]:
        """Run the full hindsight analysis pipeline."""
        # 1. Determine GW range
        start_gw = gw_start or 1
        end_gw = gw_end

        if end_gw is None:
            curr_gw, next_gw, _ = self.repo.get_current_and_next_gw()
            # If current_gw is available, use it. Otherwise fallback to next_gw - 1 or 5
            if curr_gw:
                end_gw = curr_gw
            elif next_gw and next_gw > 1:
                end_gw = next_gw - 1
            else:
                end_gw = 5

        logger.info(f"Starting Hindsight Pipeline for GW{start_gw}..GW{end_gw}")
        print(f"\n🚀 Launching Hindsight Optimization Engine (GW{start_gw} -> GW{end_gw})...")
        print(f"💰 Starting budget: £{initial_budget:.1f}m (Global unconstrained optimum)")

        # 2. Collect actual gameweek points
        print(f"📥 Collecting actual player points for GW{start_gw}..GW{end_gw}...")
        player_points = self.collector.collect_range(start_gw, end_gw)

        # 3. Solve ILP for global optimum
        print(f"⚙️ Running Multi-Period ILP Solver (Google OR-Tools CP-SAT)...")
        result = self.solver.solve(
            player_points=player_points,
            gw_start=start_gw,
            gw_end=end_gw,
            initial_budget=initial_budget,
        )

        # 4. Extract Gold Rules
        print(f"🔍 Reverse-engineering optimal decisions to extract Gold Rules...")
        rules = self.extractor.extract(result=result, player_points=player_points)

        # 5. Export JSON (Priority) & Print summary
        exported_path: Optional[Path] = None
        if export_json:
            exported_path = self.presenter.export_json(
                result=result,
                rules=rules,
                player_points=player_points,
                filename=output_filename,
            )
            print(f"💾 Results & Gold Rules exported to JSON: {exported_path.resolve()}")

        self.presenter.print_summary(
            result=result,
            rules=rules,
            player_points=player_points,
        )

        return result, rules, exported_path
