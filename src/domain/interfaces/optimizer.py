from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from ..models.player import Player
from ..models.squad import LineupSelection
from ..models.transfer import TransferPlan


class IOptimizer(ABC):
    """Abstract contract for lineup selection and transfer optimization."""

    @abstractmethod
    def select_best_lineup(self, squad_15: List[Player]) -> LineupSelection:
        """Determines optimal starting XI, captain, vice-captain, and bench order."""
        pass

    @abstractmethod
    def optimize_transfers(
        self,
        current_squad: List[Player],
        bank: float,
        free_transfers: int,
        max_hits: int,
        chips_available: Optional[Dict[str, int]],
        next_gw: int
    ) -> TransferPlan:
        """Solves optimal transfers evaluating 1-GW EV and multi-GW horizon EV."""
        pass
