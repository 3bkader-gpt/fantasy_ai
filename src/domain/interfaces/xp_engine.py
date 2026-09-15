from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from ..models.player import Player
from ..models.fixture import Fixture


class IXPEngine(ABC):
    """Abstract contract for calculating Expected Points (xP)."""

    @abstractmethod
    def calculate_player_xp(self, player: Player, fixtures: List[Fixture]) -> float:
        """Calculates expected points for a single player in a single gameweek."""
        pass

    @abstractmethod
    def enrich_players_with_horizon_xp(
        self,
        players: List[Player],
        team_fixtures: Dict[int, List[Fixture]],
        next_gw: int,
        weeks_ahead: int,
        decay: float,
        nlp_insights: Optional[Dict[int, Dict]] = None
    ) -> List[Player]:
        """Calculates 1-GW and multi-GW decayed xP and market momentum flags."""
        pass

