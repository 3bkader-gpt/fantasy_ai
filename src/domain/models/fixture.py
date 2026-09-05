from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Fixture:
    """Represents a scheduled match for a team."""
    event: int  # Gameweek number
    is_home: bool
    opponent_id: int
    opponent_name: str
    difficulty: int  # FDR 1 to 5


@dataclass(frozen=True)
class Gameweek:
    """Represents a Gameweek in the Premier League schedule."""
    id: int
    name: str
    deadline_time: str
    is_current: bool
    is_next: bool
