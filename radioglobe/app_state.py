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

    def select_station(self, stations: list) -> bool:
        """Select the first station from `stations` as current.

        Returns False (and clears the current station) if the list is
        empty."""
        self.stations = stations
        if not stations:
            self.station = None
            return False
        self.station = stations[0]
        return True
