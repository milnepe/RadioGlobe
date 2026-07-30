import logging
from typing import Optional

from .app_state import AppState
from .constants import MODE_CITY, MODE_STATION
from .coordinates import Coordinate
from .database import (
    build_cities_index,
    build_look_around_offsets,
    find_cities_near,
    get_coords_by_city,
    load_stations,
)
from .radio_config import FUZZINESS, STATIONS_JSON


class Navigator:
    """Owns station/city data and the pure station/city navigation state.

    No hardware dependencies, so it's constructible and testable off a Pi,
    unlike App (which imports RPi.GPIO at module level).
    """

    def __init__(self, stations_json: str = STATIONS_JSON, fuzziness: int = FUZZINESS):
        self.state = AppState()
        self.stations_info = load_stations(stations_json)
        self.cities_info = build_cities_index(self.stations_info)
        self.look_around_offsets = build_look_around_offsets(fuzziness)

    @property
    def current_coords(self) -> Optional[Coordinate]:
        """Coordinate of the currently selected city, if any."""
        if not self.state.city:
            return None
        return get_coords_by_city(self.stations_info, self.state.city)

    def find_cities_near(self, origin: tuple) -> list:
        """Cities within the search zone around origin, closest-first."""
        return find_cities_near(origin, self.look_around_offsets, self.cities_info)

    def next_station(self, direction):
        """Navigate to the next or previous station."""
        if not self.state.stations:
            logging.debug("⚠️ No stations available.")
            return
        self.state.jog_idx = (self.state.jog_idx + direction) % len(self.state.stations)
        logging.debug(f"jog:{self.state.jog_idx} {self.state.stations}")
        self.state.station = self.state.stations[self.state.jog_idx]
        logging.debug(f"📻 Tuning to: jog:{self.state.jog_idx} {self.state.station}")

    def next_city(self, direction):
        """Navigate to the next or previous city."""
        if not self.state.cities:
            logging.debug("⚠️ No cities available.")
            return
        self.state.jog_idx = (self.state.jog_idx + direction) % len(self.state.cities)
        self.state.city = self.state.cities[self.state.jog_idx]
        logging.debug(f"📻 Changed city: jog:{self.state.jog_idx} {self.state.city}")

    def switch_mode(self):
        """Toggle between application modes."""
        if self.state.mode == MODE_STATION:
            self.state.mode = MODE_CITY
            items, current = self.state.cities, self.state.city
        else:
            self.state.mode = MODE_STATION
            items, current = self.state.stations, self.state.station

        self.state.jog_idx = items.index(current) if current in items else 0

        logging.debug(
            f"🌀 Mode switched to: {self.state.mode} jog:{self.state.jog_idx} "
            f"{self.state.city} {self.state.station}"
        )

    def remove_failed_station(self):
        """Remove the current station from the session list and advance to the next.

        The removal is temporary — every city-change code path rebuilds
        self.state.stations from self.stations_info, restoring all stations.
        """
        if not self.state.station or self.state.station not in self.state.stations:
            return
        self.state.stations = [s for s in self.state.stations if s != self.state.station]
        if not self.state.stations:
            self.state.station = None
            return
        self.state.jog_idx = self.state.jog_idx % len(self.state.stations)
        self.state.station = self.state.stations[self.state.jog_idx]
