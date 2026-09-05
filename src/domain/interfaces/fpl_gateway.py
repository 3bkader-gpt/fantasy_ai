from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple
from ..models.transfer import Transfer


class IFPLGateway(ABC):
    """Abstract contract for interacting with official FPL user account."""

    @abstractmethod
    def login(self) -> bool:
        """Authenticate user against premierleague.com identity service."""
        pass

    @abstractmethod
    def get_my_team(self, team_id: int) -> Dict[str, Any]:
        """Fetch current team squad picks, bank balance, and chip status."""
        pass

    @abstractmethod
    def set_lineup(self, team_id: int, picks_payload: List[Dict[str, Any]], chip: Optional[str] = None) -> Dict[str, Any]:
        """Submit starting XI, captain, and bench order."""
        pass

    @abstractmethod
    def make_transfers(
        self,
        team_id: int,
        transfers: List[Transfer],
        next_gw: int,
        chip: Optional[str] = None
    ) -> Dict[str, Any]:
        """Submit transfers to official FPL API."""
        pass
