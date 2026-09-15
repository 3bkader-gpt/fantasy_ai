from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from ...domain.models.player import Player
from ...domain.models.transfer import Transfer, TransferPlan
from ...domain.models.squad import LineupSelection


@dataclass
class GameweekPlanDTO:
    """Carries complete gameweek optimization results for presentation and auditing."""
    gameweek: int
    deadline: Optional[str]
    manager_name: str
    team_name: str
    rank: Optional[int]
    total_points: int
    team_value: float
    bank: float
    free_transfers: int
    chips_available: Dict[str, int]
    current_squad: List[Player]
    all_players: List[Player]
    plan: TransferPlan
    briefing: str
    dry_run: bool
    execution_status: Dict[str, Any]
    press_conference_insights: Optional[List[Dict[str, Any]]] = None
    press_wire: Optional[List[Dict[str, Any]]] = None
    leagues: Optional[List[Dict[str, Any]]] = None


