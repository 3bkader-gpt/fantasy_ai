from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Player:
    """Represents a Premier League player with current stats and projections."""
    id: int
    name: str
    full_name: str
    position_id: int
    position: str  # GK, DEF, MID, FWD
    team_id: int
    team_name: str
    team_short: str
    cost: float  # In millions (e.g. 12.5)
    now_cost: int  # Internal FPL price (* 10)
    total_points: int = 0
    points_per_game: float = 0.0
    form: float = 0.0
    selected_by_percent: float = 0.0
    minutes: int = 0
    goals_scored: int = 0
    assists: int = 0
    clean_sheets: int = 0
    status: str = "a"  # 'a' (available), 'd' (doubtful), 'i' (injured), 's' (suspended)
    news: str = ""
    chance_of_playing_next_round: Optional[int] = None
    expected_goals: float = 0.0
    expected_assists: float = 0.0
    expected_goal_involvements: float = 0.0
    ict_index: float = 0.0
    selling_price: Optional[int] = None
    purchase_price: Optional[int] = None

    # Projected metrics (Enriched by xP Engine)
    expected_minutes: float = 0.0
    xp: float = 0.0
    horizon_xp: float = 0.0
    horizon_fixtures: str = ""
    next_fixture: str = ""
    net_transfers: int = 0
    price_trend: str = "STABLE ⚖️"
    is_differential: bool = False
    is_flop_risk: bool = False

    @property
    def is_available(self) -> bool:
        """Returns True if the player is eligible to play."""
        if self.status in ("i", "u", "s", "n"):
            return False
        if self.chance_of_playing_next_round is not None and self.chance_of_playing_next_round == 0:
            return False
        return True

    @property
    def availability_factor(self) -> float:
        """Percentage chance player participates in the next match."""
        if not self.is_available:
            return 0.0
        if self.chance_of_playing_next_round is not None:
            return float(self.chance_of_playing_next_round) / 100.0
        return 1.0
