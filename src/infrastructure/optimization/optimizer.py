from typing import List, Dict, Optional
from ...domain.interfaces.optimizer import IOptimizer
from ...domain.models.player import Player
from ...domain.models.squad import LineupSelection
from ...domain.models.transfer import TransferPlan
from .lineup_solver import LineupSolver
from .transfer_solver import TransferSolver
from .chip_evaluator import ChipEvaluator


class SquadOptimizer(IOptimizer):
    """Facade orchestrating lineup formation, transfer heuristics, and chip evaluations."""

    def __init__(self, all_players: List[Player]):
        self.lineup_solver = LineupSolver()
        self.transfer_solver = TransferSolver(all_players, self.lineup_solver)
        self.chip_evaluator = ChipEvaluator()

    def select_best_lineup(self, squad_15: List[Player]) -> LineupSelection:
        return self.lineup_solver.solve(squad_15)

    def optimize_transfers(
        self,
        current_squad: List[Player],
        bank: float,
        free_transfers: int = 1,
        max_hits: int = 1,
        chips_available: Optional[Dict[str, int]] = None,
        next_gw: int = 1
    ) -> TransferPlan:
        plan = self.transfer_solver.solve(
            current_squad=current_squad,
            bank=bank,
            free_transfers=free_transfers,
            max_hits=max_hits
        )
        # Evaluate chips on current and resulting squad
        chips_result = self.chip_evaluator.evaluate(
            squad_15=plan.new_players,
            lineup=plan.final_lineup,
            chips_available=chips_available or {}
        )
        plan.chip_recommendation = chips_result
        return plan
