from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from .player import Player


@dataclass
class Pick:
    """Represents a player selection in a manager squad."""
    element_id: int
    position: int  # 1-15
    multiplier: int = 1
    is_captain: bool = False
    is_vice_captain: bool = False
    selling_price: Optional[int] = None
    purchase_price: Optional[int] = None


@dataclass
class LineupSelection:
    """Represents the solved starting XI and bench setup for a Gameweek."""
    formation: str  # e.g. '3-5-2'
    total_expected_points: float
    starting_xi: List[Player]
    bench: List[Player]
    captain: Player
    vice_captain: Player
    api_picks: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Squad:
    """Represents the complete 15-player squad of a manager."""
    players: List[Player]
    bank: float = 0.0
    free_transfers: int = 1
    total_value: float = 100.0

    @property
    def total_xp(self) -> float:
        return sum(p.xp for p in self.players)

    @property
    def total_horizon_xp(self) -> float:
        return sum(p.horizon_xp for p in self.players)

    @property
    def team_counts(self) -> Dict[int, int]:
        counts: Dict[int, int] = {}
        for p in self.players:
            counts[p.team_id] = counts.get(p.team_id, 0) + 1
        return counts
