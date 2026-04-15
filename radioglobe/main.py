import asyncio
import dataclasses
import subprocess
import logging
import os
import json
from typing import Optional

from dataclasses import dataclass, field

import RPi.GPIO as GPIO  # type: ignore

from radioglobe.audio_async import AudioPlayer
from radioglobe.dial import AsyncDial
from radioglobe.positional_encoders import PositionalEncoders

from radioglobe.rgb_led import RGBLed
from radioglobe.rgb_led import led_task

from radioglobe.database import load_stations
from radioglobe.database import build_cities_index
from radioglobe.database import build_look_around_offsets
from radioglobe.database import look_around
from radioglobe.database import get_stations_by_city

from radioglobe.buttons import AsyncButtonManager

from radioglobe.coordinates import Coordinate
from radioglobe.display import Display
from radioglobe.radio_config import FUZZINESS, STICKINESS, VOLUME_STEP, PIN_BTN_JOG, PIN_BTN_TOP, PIN_BTN_MID, PIN_BTN_BOTTOM, STATE_CACHE_PATH, STATIONS_JSON, LOG_LEVEL


@dataclass
class AppState:
    stations: list = field(default_factory=list)
    station: Optional[tuple] = None
    cities: list = field(default_factory=list)
    city: Optional[str] = None
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
        self.stations_info = load_stations(STATIONS_JSON)
        self.cities_info = build_cities_index(self.stations_info)
        self.look_around_offsets = build_look_around_offsets(FUZZINESS)
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
            cities=state.get("cities") or [],
            city=state.get("city"),
            jog_idx=state.get("jog_idx") or 0,
            mode=state.get("mode") or "station",
        )
        self.encoders.latitude = state.get("lat")
        self.encoders.longitude = state.get("lon")
        self.encoders.latitude_offset = state.get("lat_offset")
        self.encoders.longitude_offset = state.get("lon_offset")
        self.encoders.latch_stickiness = True

        # Re-query stations from the live database so stale snapshots in the
        # cache never cause wrong URLs or indices after a stations.json update.
        if self.state.city:
            self.state.stations = get_stations_by_city(self.stations_info, self.state.city)
            saved_name = state["station"][0] if state.get("station") else None
            match = next(
                (s for s in self.state.stations if s[0] == saved_name),
                None,
            )
            if match:
                self.state.station = match
                self.state.jog_idx = self.state.stations.index(match)
            else:
                self.state.station = self.state.stations[0] if self.state.stations else None
                self.state.jog_idx = 0

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
        self.state.jog_idx = 0
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

    def _remove_failed_station(self):
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

    async def _monitor_stream(self, expected_url: str):
        """After a 3 s grace period, remove failed stations and try the next.

        Loops until a station plays without error, all stations have been
        removed, or the user selects a different station.
        """
        while self.state.stations:
            await asyncio.sleep(3)

            # User moved to a different station — stop watching
            if self.audio_player.current_url != expected_url:
                return

            if not self.audio_player.is_error():
                return  # playing fine

            if not self.state.city:
                return

            logging.debug(f"⚠️ Stream error: {expected_url}")
            asyncio.create_task(led_task(self.led, self.led_running, "red", 0.5))
            self._remove_failed_station()
            if not self.state.station:
                break
            coords = self._get_coords_by_city(self.state.city)
            self.display.update(coords, self.state.city, 0, self.state.station[0], False)
            self.audio_player.play(self.state.city, self.state.station)
            expected_url = self.state.station[1]

        logging.debug("⚠️ All stations failed for this city")

    def _start_monitor_stream(self, url: str):
        """Cancel any running stream monitor and start a fresh one for url."""
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
        self._stream_task = asyncio.create_task(self._monitor_stream(url))

    # ---------------------------------------------------------------------------
    # Event-driven loops
    # ---------------------------------------------------------------------------

    async def _encoder_loop(self):
        """Wake on each encoder update and handle city latching."""
        while True:
            await self.encoders.updated.wait()
            self.encoders.updated.clear()

            coords = self.encoders.get_readings()
            zone = look_around(coords, self.look_around_offsets)
            self.state.cities = self._find_all_cities(zone, self.cities_info)

            if not self.encoders.is_latched() and self.state.cities:
                logging.debug(f"latch: {self.encoders.is_latched()} Cities: {self.state.cities}")
                if not self.led_running.is_set():
                    asyncio.create_task(led_task(self.led, self.led_running, "green", 0.5))

                self.encoders.latch(*coords, stickiness=STICKINESS)
                self.state.jog_idx = 0
                logging.debug(
                    f"Matching cities: jog:{self.state.jog_idx} "
                    f"stick:{STICKINESS} fuzz:{FUZZINESS} {self.state.cities} {self.encoders.is_latched()}"
                )
                self.state.city = self.state.cities[0]
                self.state.stations = get_stations_by_city(self.stations_info, self.state.city)
                self.state.jog_idx = 0
                self.state.station = self.state.stations[0]
                logging.info(f"Cities: {self.state.cities}")
                logging.debug(
                    f"📻 Tuning to: jog:{self.state.jog_idx} "
                    f"{self.state.city} {self.state.station}\n{self.state.stations}"
                )
                coords = self._get_coords_by_city(self.state.city)
                self.display.update(coords, self.state.city, 0, self.state.station[0], False)
                self.audio_player.play(self.state.city, self.state.station)
                self._start_monitor_stream(self.state.station[1])

    async def _dial_loop(self):
        """Wake on each dial movement and handle station/city navigation."""
        while True:
            direction = await self.dial.queue.get()
            if not self.state.city or not self.state.station:
                continue
            asyncio.create_task(led_task(self.led, self.led_running, "blue", 0.1))
            logging.debug(
                f"↪️ Dial turned: {'right' if direction > 0 else 'left'} dir:{direction}"
            )
            if self.state.mode == "station":
                self.next_station(direction)
            elif self.state.mode == "city":
                self.next_city(direction)
                self.state.station = self.state.stations[0]

            coords = self._get_coords_by_city(self.state.city)
            self.display.update(coords, self.state.city, 0, self.state.station[0], False)
            self.audio_player.play(self.state.city, self.state.station)
            self._start_monitor_stream(self.state.station[1])

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

        encoder_task = None
        dial_task = None
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
            except FileNotFoundError:
                pass  # no cache yet — normal on first boot
            except Exception as e:
                logging.warning(f"load_state failed: {e}")
            logging.debug(
                f"State: {self.encoders.latitude_offset} {self.encoders.longitude_offset} "
                f"{self.state.mode} {self.state.city} {self.state.station} {self.encoders.is_latched()}"
            )

            # The latch is set if there was saved state — this triggers playing the saved station
            if self.encoders.is_latched():
                if not self.state.city or not self.state.station:
                    logging.warning("Saved state incomplete — starting in calibrate mode")
                    self.encoders.reset_latch()
                    self.display.update(Coordinate(0, 0), "CALIBRATE", 0, "", False)
                else:
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

            encoder_task = asyncio.create_task(self._encoder_loop())
            dial_task = asyncio.create_task(self._dial_loop())
            await asyncio.gather(encoder_task, dial_task)

        except KeyboardInterrupt:
            logging.debug("👋 Exiting on keyboard interrupt...")
            if encoder_task is not None:
                encoder_task.cancel()
            if dial_task is not None:
                dial_task.cancel()
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
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    )

    logging.info("Starting RadioGlobe...")

    asyncio.run(App().run())
