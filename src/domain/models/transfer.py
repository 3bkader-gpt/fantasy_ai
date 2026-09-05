from dataclasses import dataclass, field
from typing import List, Optional
from .player import Player
from .squad import LineupSelection


@dataclass(frozen=True)
class Transfer:
    """Represents a single player swap."""
    player_out: Player
    player_in: Player

    @property
    def cost_diff(self) -> float:
        return self.player_in.cost - self.player_out.cost


@dataclass
class TransferPlan:
    """Represents the recommended set of transfers and resulting squad."""
    transfers: List[Transfer] = field(default_factory=list)
    hits: int = 0
    hits_cost: int = 0
    net_gain: float = 0.0
    horizon_gain: float = 0.0
    new_bank: float = 0.0
    final_lineup: Optional[LineupSelection] = None
    new_players: List[Player] = field(default_factory=list)
    chip_recommendation: Optional[dict] = None
