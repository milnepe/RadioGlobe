import json
import logging
import os
from dataclasses import asdict
from typing import Optional

from .app_state import AppState
from .constants import MODE_CITY, MODE_STATION
from .coordinates import Coordinate
from .database import (
    build_cities_index,
    build_look_around_offsets,
    find_cities_near,
    get_coords_by_city,
    get_stations_by_city,
    load_stations,
    match_saved_station,
)
from .radio_config import FUZZINESS, STATE_CACHE_PATH, STATIONS_JSON


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

    def save_state(self, encoder_offsets: dict, cache: str = STATE_CACHE_PATH):
        """Serialise state + encoder_offsets (lat/lon/lat_offset/lon_offset) to cache as JSON.

        encoder_offsets is plain data supplied by the caller rather than a
        PositionalEncoders object, since Navigator has no hardware
        dependency and can't read one directly.
        """
        logging.debug(f"STATIONS: {self.state.stations}")
        state = asdict(self.state)
        state.update(encoder_offsets)
        state["latch"] = True

        path = os.path.expanduser(cache)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f)

    def load_state(self, cache: str = STATE_CACHE_PATH) -> dict:
        """Restore self.state from cache; returns the saved encoder offsets.

        Returns {} (leaving self.state untouched) if no cache file exists.
        Encoder offsets are always returned when a cache file is found,
        even if the saved city turns out to be stale and gets discarded.
        """
        path = os.path.expanduser(cache)
        if not os.path.exists(path):
            return {}
        with open(path, "r") as f:
            state = json.load(f)

        self.state = AppState(
            stations=state.get("stations") or [],
            station=tuple(state["station"]) if state.get("station") else None,
            cities=state.get("cities") or [],
            city=state.get("city"),
            jog_idx=state.get("jog_idx") or 0,
            mode=state.get("mode") or MODE_STATION,
        )

        # Re-query stations from the live database so stale snapshots in the
        # cache never cause wrong URLs or indices after a stations.json update.
        if self.state.city:
            try:
                self.current_coords  # validate city still exists
            except KeyError as e:
                logging.warning(f"{e} — discarding stale saved city")
                self.state.city = None
                self.state.station = None
            else:
                self.state.stations = get_stations_by_city(self.stations_info, self.state.city)
                saved_name = state["station"][0] if state.get("station") else None
                self.state.station, self.state.jog_idx = match_saved_station(
                    saved_name, self.state.stations
                )

        return {
            "lat": state.get("lat"),
            "lon": state.get("lon"),
            "lat_offset": state.get("lat_offset"),
            "lon_offset": state.get("lon_offset"),
        }

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
