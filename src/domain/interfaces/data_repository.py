from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple
from ..models.player import Player
from ..models.fixture import Fixture, Gameweek


class IDataRepository(ABC):
    """Abstract contract for fetching and caching FPL bootstrap and fixture data."""

    @abstractmethod
    def get_current_and_next_gw(self) -> Tuple[Optional[int], Optional[int], Optional[str]]:
        """Returns (current_gw, next_gw, deadline_timestamp)."""
        pass

    @abstractmethod
    def get_all_players(self, force_refresh: bool = False) -> List[Player]:
        """Returns parsed list of all Premier League players."""
        pass

    @abstractmethod
    def get_team_fixtures(self, next_gw: int, weeks_ahead: int) -> Dict[int, List[Fixture]]:
        """Returns map of team_id to upcoming Fixtures."""
        pass
