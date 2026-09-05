from abc import ABC, abstractmethod
from typing import List
from ..models.transfer import Transfer
from ..models.squad import LineupSelection


class INotifier(ABC):
    """Abstract contract for sending user notifications and alerts."""

    @abstractmethod
    def send_message(self, text: str) -> bool:
        """Sends raw text message to notification channels."""
        pass

    @abstractmethod
    def send_gameweek_summary(
        self,
        gw: int,
        transfers: List[Transfer],
        lineup: LineupSelection,
        briefing_text: str,
        dry_run: bool
    ) -> bool:
        """Sends a formatted gameweek card with briefing to notification channels."""
        pass
