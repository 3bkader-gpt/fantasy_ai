"""Backwards compatibility shim for SquadOptimizer."""
from src.infrastructure.optimization import SquadOptimizer, LineupSolver, TransferSolver, ChipEvaluator

__all__ = ["SquadOptimizer", "LineupSolver", "TransferSolver", "ChipEvaluator"]
