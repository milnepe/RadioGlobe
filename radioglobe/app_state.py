from dataclasses import dataclass, field
from typing import Optional

from .constants import MODE_STATION


@dataclass
class AppState:
    stations: list = field(default_factory=list)
    station: Optional[tuple] = None
    cities: list = field(default_factory=list)
    city: Optional[str] = None
    jog_idx: int = 0
    mode: str = MODE_STATION

    def is_complete(self) -> bool:
        """Whether a city and station are both selected."""
        return bool(self.city and self.station)
