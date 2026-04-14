import asyncio
import dataclasses
import subprocess
import logging
import os
import json
from typing import Optional

from dataclasses import dataclass, field

import RPi.GPIO as GPIO  # type: ignore

from audio_async import AudioPlayer
from dial import AsyncDial
from positional_encoders import PositionalEncoders

from rgb_led import RGBLed
from rgb_led import led_task

from database import load_stations
from database import build_cities_index
from database import look_around
from database import get_stations_by_city

from buttons import AsyncButtonManager

from coordinates import Coordinate
from display import Display
from radio_config import FUZZINESS, STICKINESS, VOLUME_STEP, PIN_BTN_JOG, PIN_BTN_TOP, PIN_BTN_MID, PIN_BTN_BOTTOM, STATE_CACHE_PATH


@dataclass
class AppState:
    stations: list = field(default_factory=list)
    station: Optional[tuple] = None
    station_idx: int = 0
    cities: list = field(default_factory=list)
    city: Optional[str] = None
    city_idx: int = 0
    jog_idx: int = 0
    mode: str = "station"


class App:
    def __init__(self):
        self.dial = AsyncDial()
        self.audio_player = AudioPlayer()
        self.audio_player.change_volume_level(50)
        self.encoders = PositionalEncoders()
        self.display = Display()
        self.led = RGBLed()
        self.led_running = asyncio.Event()
        self.state = AppState()
        self.stations_info = load_stations("stations.json")
        self.cities_info = build_cities_index(self.stations_info)
        self._stream_task: Optional[asyncio.Task] = None

    def save_state(self, cache=STATE_CACHE_PATH):
        logging.debug(f"STATIONS: {self.state.stations}")
        state = dataclasses.asdict(self.state)
        state.update({
            "lat": self.encoders.latitude,
            "lon": self.encoders.longitude,
            "lat_offset": self.encoders.latitude_offset,
            "lon_offset": self.encoders.longitude_offset,
            "latch": True,
        })

        path = os.path.expanduser(cache)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f)

    def load_state(self):
        path = os.path.expanduser(STATE_CACHE_PATH)
        if not os.path.exists(path):
            return
        with open(path, "r") as f:
            state = json.load(f)

        self.state = AppState(
            stations=state.get("stations") or [],
            station=tuple(state["station"]) if state.get("station") else None,
            station_idx=state.get("station_idx") or 0,
            cities=state.get("cities") or [],
            city=state.get("city"),
            city_idx=state.get("city_idx") or 0,
            jog_idx=state.get("jog_idx") or 0,
            mode=state.get("mode") or "station",
        )
        self.encoders.latitude = state.get("lat")
        self.encoders.longitude = state.get("lon")
        self.encoders.latitude_offset = state.get("lat_offset")
        self.encoders.longitude_offset = state.get("lon_offset")
        self.encoders.latch_stickiness = True

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
        self.state.stations = get_stations_by_city(self.stations_info, self.state.city)
        logging.debug(f"📻 Changed city: jog:{self.state.jog_idx} {self.state.city} {self.state.stations}")

    def switch_mode(self):
        """Toggle between application modes."""
        self.state.mode = "city" if self.state.mode == "station" else "station"
        logging.debug(
            f"🌀 Mode switched to: {self.state.mode} jog:{self.state.jog_idx} "
            f"{self.state.city} {self.state.station}"
        )

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    def _get_coords_by_city(self, city: str) -> Coordinate:
        """Return a Coordinate for the given city string."""
        entry = self.stations_info.get(city)
        if entry is None:
            logging.warning(f"City not found in stations data: {city!r}")
            return Coordinate(0, 0)
        return Coordinate(entry["coords"]["n"], entry["coords"]["e"])

    def _find_all_cities(self, coords, cities):
        """Return all cities whose grid coordinates appear in coords."""
        return [city for coord in coords if coord in cities for city in cities[coord]]

    async def _update_volume(self, delta):
        """Adjust volume by delta and briefly show the level on the display."""
        if not self.state.city or not self.state.station:
            return
        volume = self.audio_player.change_volume(delta)
        coords = self._get_coords_by_city(self.state.city)
        self.display.update(coords, self.state.city, volume, self.state.station[0], False)
        await asyncio.sleep(0.5)
        self.display.update(coords, self.state.city, 0, self.state.station[0], False)

    async def _update_volume_level(self, level):
        """Set volume to an absolute level and briefly show it on the display."""
        if not self.state.city or not self.state.station:
            return
        volume = self.audio_player.change_volume_level(level)
        coords = self._get_coords_by_city(self.state.city)
        self.display.update(coords, self.state.city, volume, self.state.station[0], False)
        await asyncio.sleep(0.5)
        self.display.update(coords, self.state.city, 0, self.state.station[0], False)

    async def _monitor_stream(self, expected_url: str):
        """Monitor a stream for failures until the station changes.

        Polls every 5 s after an initial 3 s grace period. Shows a red LED
        flash and 'Stream error' on the display on the first failed poll, then
        continues watching in case VLC recovers (--input-repeat=-1 retries).
        Exits silently when the URL changes (user selected a different station).
        """
        await asyncio.sleep(3)
        error_shown = False
        while self.audio_player.current_url == expected_url:
            if self.audio_player.is_error():
                if not error_shown:
                    logging.debug(f"⚠️ Stream error detected for {expected_url}")
                    asyncio.create_task(led_task(self.led, self.led_running, "red", 0.5))
                    coords = self._get_coords_by_city(self.state.city) if self.state.city else Coordinate(0, 0)
                    self.display.update(coords, self.state.city or "", 0, "Stream error", False)
                    error_shown = True
            else:
                if error_shown:
                    logging.debug(f"✅ Stream recovered for {expected_url}")
                    coords = self._get_coords_by_city(self.state.city) if self.state.city else Coordinate(0, 0)
                    station_name = self.state.station[0] if self.state.station else ""
                    self.display.update(coords, self.state.city or "", 0, station_name, False)
                    error_shown = False
            await asyncio.sleep(5)

    def _start_monitor_stream(self, url: str):
        """Cancel any running stream monitor and start a fresh one for url."""
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
        self._stream_task = asyncio.create_task(self._monitor_stream(url))

    # ---------------------------------------------------------------------------
    # Button handlers
    # ---------------------------------------------------------------------------

    async def _on_jog_press(self):
        asyncio.create_task(led_task(self.led, self.led_running, "green", 0.2))

    async def _handle_short_jog(self):
        self.switch_mode()
        result = self.state.stations if self.state.mode == "station" else self.state.cities
        logging.debug(f"🖲️ Jog button short press! Change mode jog: {self.state.jog_idx} {result}")

    async def _handle_long_jog(self):
        logging.debug("🖲️ Jog button long press: None")
        await asyncio.sleep(0.2)

    async def _on_sound_press(self):
        asyncio.create_task(led_task(self.led, self.led_running, "blue", 0.2))

    async def _handle_short_top(self):
        logging.debug("🖲️ Top button short press! Increasing volume.")
        await self._update_volume(VOLUME_STEP)

    async def _handle_long_top(self):
        logging.debug("🖲️ Top button long press! Set volume on")
        await self._update_volume_level(80)

    async def _handle_short_bottom(self):
        logging.debug("🖲️ Bottom button short press! Lowering volume.")
        await self._update_volume(-VOLUME_STEP)

    async def _handle_long_bottom(self):
        logging.debug("🖲️ Bottom button long press! Set volume off")
        await self._update_volume_level(0)

    async def _on_mid_press(self):
        asyncio.create_task(led_task(self.led, self.led_running, "green", 0.2))

    async def _handle_short_mid(self):
        logging.debug("🖲️ Mid button mid short press! Calibrating.")
        self.encoders.zero()
        self.encoders.reset_latch()
        logging.debug(
            f"Encoder offsets set to: {self.encoders.latitude}, {self.encoders.longitude} "
            f"{self.encoders.latitude_offset}, {self.encoders.longitude_offset}"
        )
        self.display.update(Coordinate(0, 0), "Calibrated", 0, "", False)
        await asyncio.sleep(0.5)
        self.display.update(Coordinate(0, 0), "CALIBRATE", 0, "", False)

    async def _handle_long_mid(self):
        logging.debug("🔴 Shutdown initiated! Powering off...")
        self.save_state()
        logging.debug("Saved state...")
        self.display.update(Coordinate(0, 0), "Shutdown", 0, "", False)
        await asyncio.sleep(2)
        subprocess.run(["sudo", "poweroff"])

    # ---------------------------------------------------------------------------
    # Main loop
    # ---------------------------------------------------------------------------

    async def run(self):
        """Main app loop."""
        self.dial.start()
        self.encoders.start()
        self.display.start()

        loop = asyncio.get_running_loop()

        button_definitions = [
            ("Jog",    PIN_BTN_JOG,    self._handle_short_jog,    None,                    self._on_jog_press),
            ("Top",    PIN_BTN_TOP,    self._handle_short_top,    self._handle_long_top,   self._on_sound_press),
            ("Mid",    PIN_BTN_MID,    self._handle_short_mid,    self._handle_long_mid,   self._on_mid_press),
            ("Bottom", PIN_BTN_BOTTOM, self._handle_short_bottom, self._handle_long_bottom, self._on_sound_press),
        ]

        button_manager = AsyncButtonManager(button_definitions, loop)
        await button_manager.start()
        asyncio.create_task(button_manager.handle_events())

        try:
            self.display.message(
                line_1="Radio Globe",
                line_2="Made for DesignSpark",
                line_3="Jude Pullen, Donald",
                line_4="Robson, Pete Milne",
            )
            await asyncio.sleep(2)

            try:
                self.load_state()
            except Exception:
                logging.debug("Config not found...")
            logging.debug(
                f"State: {self.encoders.latitude_offset} {self.encoders.longitude_offset} "
                f"{self.state.mode} {self.state.city} {self.state.station} {self.encoders.is_latched()}"
            )

            # The latch is set if there was saved state — this triggers playing the saved station
            if self.encoders.is_latched():
                assert self.state.city is not None, "latched state missing city"
                assert self.state.station is not None, "latched state missing station"
                coords = self._get_coords_by_city(self.state.city)
                self.display.update(coords, self.state.city, 0, self.state.station[0], False)
                self.audio_player.play(self.state.city, self.state.station)
                self._start_monitor_stream(self.state.station[1])
                logging.debug(
                    f"Playing saved station: {self.state.station} {self.state.city} "
                    f"{self.state.cities} {self.state.stations}"
                )
            else:
                self.display.update(Coordinate(0, 0), "CALIBRATE", 0, "", False)

            while True:
                await asyncio.sleep(0.1)

                coords = self.encoders.get_readings()
                # The size of the look-around zone is determined by FUZZINESS
                zone = look_around(coords, FUZZINESS)
                self.state.cities = self._find_all_cities(zone, self.cities_info)

                if not self.encoders.is_latched() and self.state.cities:
                    logging.debug(f"latch: {self.encoders.is_latched()} Cities: {self.state.cities}")
                    # Flash LED to signal match
                    if not self.led_running.is_set():
                        asyncio.create_task(led_task(self.led, self.led_running, "green", 0.5))

                    # Freeze position until reticule moves again
                    self.encoders.latch(*coords, stickiness=STICKINESS)
                    self.state.jog_idx = self.state.city_idx = 0
                    logging.debug(
                        f"Matching cities: current:{self.state.jog_idx} city:{self.state.city_idx} "
                        f"stick:{STICKINESS} fuzz:{FUZZINESS} {self.state.cities} {self.encoders.is_latched()}"
                    )
                    self.state.city = self.state.cities[self.state.city_idx]
                    self.state.stations = get_stations_by_city(self.stations_info, self.state.city)
                    self.state.jog_idx = self.state.station_idx = 0
                    self.state.station = self.state.stations[self.state.station_idx]
                    logging.debug(
                        f"📻 Tuning to: current:{self.state.jog_idx} city:{self.state.city_idx} "
                        f"stat:{self.state.station_idx} {self.state.city} {self.state.station}\n{self.state.stations}"
                    )
                    coords = self._get_coords_by_city(self.state.city)
                    self.display.update(coords, self.state.city, 0, self.state.station[0], False)
                    self.audio_player.play(self.state.city, self.state.station)
                    self._start_monitor_stream(self.state.station[1])

                # Modal dial: cycles stations (station mode) or cities (city mode)
                direction = self.dial.get_direction()
                if direction != 0 and self.state.city and self.state.station:
                    asyncio.create_task(led_task(self.led, self.led_running, "blue", 0.1))
                    logging.debug(
                        f"↪️ Dial turned: {'right' if direction > 0 else 'left'} dir:{direction}"
                    )
                    if self.state.mode == "station":
                        self.next_station(direction)
                    elif self.state.mode == "city":
                        self.next_city(direction)
                        self.state.station = get_stations_by_city(self.stations_info, self.state.city)[0]

                    coords = self._get_coords_by_city(self.state.city)
                    self.display.update(coords, self.state.city, 0, self.state.station[0], False)
                    self.audio_player.play(self.state.city, self.state.station)
                    self._start_monitor_stream(self.state.station[1])

        except KeyboardInterrupt:
            logging.debug("👋 Exiting on keyboard interrupt...")
        finally:
            if self._stream_task and not self._stream_task.done():
                self._stream_task.cancel()
            for hw in [self.audio_player, self.dial, self.encoders, self.display, self.led]:
                await hw.stop()
            GPIO.cleanup()


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s: %(message)s",
        datefmt="%H:%M:%S",
        level=logging.DEBUG,
    )

    logging.info("Starting RadioGlobe...")

    asyncio.run(App().run())
