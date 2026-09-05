from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ChipType(str, Enum):
    WILDCARD = "wildcard"
    FREE_HIT = "freehit"
    TRIPLE_CAPTAIN = "3xc"
    BENCH_BOOST = "bboost"


@dataclass(frozen=True)
class ChipRecommendation:
    """Tactical suggestion for activating a special chip."""
    chip: ChipType
    reason: str
    confidence: str  # HIGH, MEDIUM, VERY HIGH
