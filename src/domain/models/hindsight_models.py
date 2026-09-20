from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Dict, Any


@dataclass
class PlayerGameweekRecord:
    """Actual performance metrics and context for a player in a specific finished Gameweek."""
    player_id: int
    gameweek: int
    total_points: int
    minutes: int
    goals_scored: int
    assists: int
    clean_sheets: int
    bonus: int
    was_home: bool
    opponent_id: int
    opponent_short: str
    fixture_difficulty: int
    price: float
    element_type: int = 0  # 1: GKP, 2: DEF, 3: MID, 4: FWD
    web_name: str = ""
    team_id: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HindsightGameweekDecision:
    """The mathematically optimal squad selection and transfer decisions for a single gameweek."""
    gameweek: int
    squad_15: List[int]
    starting_xi: List[int]
    bench: List[int]
    captain_id: int
    formation: str
    transfers_in: List[int] = field(default_factory=list)
    transfers_out: List[int] = field(default_factory=list)
    hits_taken: int = 0
    hit_cost: int = 0
    gross_points: int = 0
    total_points: int = 0  # Net points after deducting hit cost
    bank: float = 0.0
    team_value: float = 0.0
    vice_captain_id: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HindsightResult:
    """The complete multi-gameweek hindsight optimization result."""
    gameweek_range: Tuple[int, int]
    decisions: List[HindsightGameweekDecision]
    total_points: int
    total_hits: int
    total_hit_cost: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gameweek_range": list(self.gameweek_range),
            "decisions": [d.to_dict() for d in self.decisions],
            "total_points": self.total_points,
            "total_hits": self.total_hits,
            "total_hit_cost": self.total_hit_cost,
        }


@dataclass
class GoldRule:
    """A statistical pattern or winning heuristic extracted from the optimal hindsight path."""
    category: str  # 'captain', 'transfer', 'formation', 'position_allocation', 'fdr', 'home_away', 'price_efficiency'
    rule_text: str
    confidence: float
    evidence_gws: List[int]
    feature_values: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
