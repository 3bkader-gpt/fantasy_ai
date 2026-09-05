from dataclasses import dataclass
from typing import List, Optional
from ...domain.models.player import Player
from ...domain.models.squad import LineupSelection


@dataclass
class InitialSquadDTO:
    """Carries complete initial squad generation results and tactical evaluation."""
    target_gameweek: int
    deadline: Optional[str]
    total_cost: float
    starters_cost: float
    bench_cost: float
    remaining_bank: float
    total_squad_horizon_xp: float
    all_squad_players: List[Player]
    lineup: LineupSelection
    briefing: str
