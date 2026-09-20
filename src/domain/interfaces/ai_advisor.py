from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from ..models.player import Player
from ..models.transfer import Transfer
from ..models.squad import LineupSelection


class IAIAdvisor(ABC):
    """Abstract contract for tactical AI analysis and briefing generation."""

    @abstractmethod
    def generate_briefing(
        self,
        gw: int,
        deadline: Optional[str],
        current_squad: List[Player],
        recommended_transfers: List[Transfer],
        lineup: LineupSelection,
        points_gain: float,
        hits_cost: int,
        bank: float,
        rank: Optional[int] = None,
        chips_available: Optional[Dict[str, int]] = None,
        chip_recommendation: Optional[Dict[str, Any]] = None,
        market_trends: Optional[List[Player]] = None,
        leagues: Optional[List[Dict[str, Any]]] = None,
        gold_rules: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Generates an Arabic tactical briefing based on mathematical solver output and Gold Rules."""
        pass
