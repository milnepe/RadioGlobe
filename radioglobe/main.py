import asyncio
import subprocess
import logging
import os
import json

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
from radio_config import FUZZINESS, STICKINESS, PIN_BTN_JOG, PIN_BTN_TOP, PIN_BTN_MID, PIN_BTN_BOTTOM


class App:
    def __init__(self):
        self.dial = AsyncDial()
        self.audio_player = AudioPlayer()
        self.audio_player.change_volume_level(50)
        self.encoders = PositionalEncoders()
        self.display = Display()
        self.led = RGBLed()
        self.led_running = asyncio.Event()
        self.stations = None
        self.station = None
        self.station_idx = None
        self.cities = None
        self.city = None
        self.city_idx = None
        self.jog_idx = 0
        self.mode = "station"
        self.stations_info = load_stations("stations.json")
        self.cities_info = build_cities_index(self.stations_info)

    def save_state(self, cache="~/cache/radioglobe.json"):
        def safe(obj):
            if isinstance(obj, tuple):
                return list(obj)
            return obj

        logging.debug(f"STATIONS: {self.stations}")
        state = {
            "stations": self.stations,
            "station": self.station,
            "station_idx": self.station_idx,
            "cities": self.cities,
            "city": self.city,
            "city_idx": self.city_idx,
            "jog_idx": self.jog_idx,
            "mode": self.mode,
            "lat": self.encoders.latitude,
            "lon": self.encoders.longitude,
            "lat_offset": self.encoders.latitude_offset,
            "lon_offset": self.encoders.longitude_offset,
            "latch": True,
        }

        path = os.path.expanduser(cache)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f)

    def load_state(self):
        path = os.path.expanduser("~/cache/radioglobe.json")
        if not os.path.exists(path):
            return
        with open(path, "r") as f:
            state = json.load(f)

        self.stations = state.get("stations")
        self.station = tuple(state["station"]) if state.get("station") else None
        self.station_idx = state.get("station_idx")
        self.cities = tuple(state["cities"]) if state.get("cities") else None
        self.city = state.get("city")
        self.city_idx = state.get("city_idx")
        self.jog_idx = state.get("jog_idx")
        self.mode = state.get("mode")
        self.encoders.latitude = state.get("lat")
        self.encoders.longitude = state.get("lon")
        self.encoders.latitude_offset = state.get("lat_offset")
        self.encoders.longitude_offset = state.get("lon_offset")
        self.encoders.latch_stickiness = True

    def next_station(self, direction):
        """Navigate to the next or previous station."""
        if not self.stations:
            logging.debug("⚠️ No stations available.")
            return
        self.jog_idx = (self.jog_idx + direction) % len(self.stations)
        logging.debug(f"jog:{self.jog_idx} {self.stations}")
        self.station = self.stations[self.jog_idx]
        logging.debug(f"📻 Tuning to: jog:{self.jog_idx} {self.station}")

    def next_city(self, direction):
        """Navigate to the next or previous city."""
        if not self.cities:
            logging.debug("⚠️ No cities available.")
            return
        self.jog_idx = (self.jog_idx + direction) % len(self.cities)
        self.city = self.cities[self.jog_idx]
        self.stations = get_stations_by_city(self.stations_info, self.city)
        logging.debug(f"📻 Changed city: jog:{self.jog_idx} {self.city} {self.stations}")

    def switch_mode(self):
        """Toggle between application modes."""
        self.mode = "city" if self.mode == "station" else "station"
        logging.debug(
            f"🌀 Mode switched to: {self.mode} jog:{self.jog_idx} {self.city} {self.station}"
        )

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    def _get_coords_by_city(self, city):
        """Return a Coordinate for the given city string."""
        lat = self.stations_info[city]["coords"]["n"]
        lon = self.stations_info[city]["coords"]["e"]
        return Coordinate(lat, lon)

    async def _find_all_cities(self, coords, cities):
        """Return all cities whose grid coordinates appear in coords."""
        return [cities[coord] for coord in coords if coord in cities]

    async def _update_volume(self, delta):
        """Adjust volume by delta and briefly show the level on the display."""
        volume = self.audio_player.change_volume(delta)
        coords = self._get_coords_by_city(self.city)
        self.display.update(coords, self.city, volume, self.station[0], False)
        await asyncio.sleep(0.5)
        self.display.update(coords, self.city, 0, self.station[0], False)

    async def _update_volume_level(self, level):
        """Set volume to an absolute level and briefly show it on the display."""
        volume = self.audio_player.change_volume_level(level)
        coords = self._get_coords_by_city(self.city)
        self.display.update(coords, self.city, volume, self.station[0], False)
        await asyncio.sleep(0.5)
        self.display.update(coords, self.city, 0, self.station[0], False)

    # ---------------------------------------------------------------------------
    # Button handlers
    # ---------------------------------------------------------------------------

    async def _on_jog_press(self):
        asyncio.create_task(led_task(self.led, self.led_running, "green", 0.2))

    async def _handle_short_jog(self):
        self.switch_mode()
        result = self.stations if self.mode == "station" else self.cities
        logging.debug(f"🖲️ Jog button short press! Change mode jog: {self.jog_idx} {result}")

    async def _handle_long_jog(self):
        logging.debug("🖲️ Jog button long press: None")
        await asyncio.sleep(0.2)

    async def _on_sound_press(self):
        asyncio.create_task(led_task(self.led, self.led_running, "blue", 0.2))

    async def _handle_short_top(self):
        logging.debug("🖲️ Top button short press! Increasing volume.")
        await self._update_volume(10)

    async def _handle_long_top(self):
        logging.debug("🖲️ Top button long press! Set volume on")
        await self._update_volume_level(80)

    async def _handle_short_bottom(self):
        logging.debug("🖲️ Bottom button short press! Lowering volume.")
        await self._update_volume(-10)

    async def _handle_long_bottom(self):
        logging.debug("🖲️ Bottom button long press! Set volume off")
        await self._update_volume_level(0)

    async def _on_mid_press(self):
        asyncio.create_task(led_task(self.led, self.led_running, "green", 0.2))

    async def _handle_short_mid(self):
        logging.debug("🖲️ Mid button mid short press! Calibrating.")
        self.encoders.zero()
        logging.debug(
            f"Encoder offsets set to: {self.encoders.latitude}, {self.encoders.longitude} "
            f"{self.encoders.latitude_offset}, {self.encoders.longitude_offset}"
        )
        self.display.update(Coordinate(0, 0), "Calibrated", 0, "", False)
        await asyncio.sleep(0.5)

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
                f"{self.mode} {self.city} {self.station} {self.encoders.is_latched()}"
            )

            # The latch is set if there was saved state — this triggers playing the saved station
            if self.encoders.is_latched():
                coords = self._get_coords_by_city(self.city)
                self.display.update(coords, self.city, 0, self.station[0], False)
                self.audio_player.play(self.city, self.station)
                logging.debug(
                    f"Playing saved station: {self.station} {self.city} {self.cities} {self.stations}"
                )
            else:
                self.display.update(Coordinate(0, 0), "CALIBRATE", 0, "", False)

            while True:
                await asyncio.sleep(0.1)

                coords = self.encoders.get_readings()
                # The size of the look-around zone is determined by FUZZINESS
                zone = look_around(coords, FUZZINESS)
                self.cities = await self._find_all_cities(zone, self.cities_info)

                if not self.encoders.is_latched() and self.cities:
                    logging.debug(f"latch: {self.encoders.is_latched()} Cities: {self.cities}")
                    # Flash LED to signal match
                    if not self.led_running.is_set():
                        asyncio.create_task(led_task(self.led, self.led_running, "green", 0.5))

                    # Freeze position until reticule moves again
                    self.encoders.latch(*coords, stickiness=STICKINESS)
                    self.jog_idx = self.city_idx = 0
                    logging.debug(
                        f"Matching cities: current:{self.jog_idx} city:{self.city_idx} "
                        f"stick:{STICKINESS} fuzz:{FUZZINESS} {self.cities} {self.encoders.is_latched()}"
                    )
                    self.city = self.cities[self.city_idx]
                    self.stations = get_stations_by_city(self.stations_info, self.city)
                    self.jog_idx = self.station_idx = 0
                    self.station = self.stations[self.station_idx]
                    logging.debug(
                        f"📻 Tuning to: current:{self.jog_idx} city:{self.city_idx} "
                        f"stat:{self.station_idx} {self.city} {self.station}\n{self.stations}"
                    )
                    coords = self._get_coords_by_city(self.city)
                    self.display.update(coords, self.city, 0, self.station[0], False)
                    self.audio_player.play(self.city, self.station)

                # Modal dial: cycles stations (station mode) or cities (city mode)
                direction = self.dial.get_direction()
                if direction != 0:
                    asyncio.create_task(led_task(self.led, self.led_running, "blue", 0.1))
                    logging.debug(
                        f"↪️ Dial turned: {'right' if direction > 0 else 'left'} dir:{direction}"
                    )
                    if self.mode == "station":
                        self.next_station(direction)
                    elif self.mode == "city":
                        self.next_city(direction)
                        self.station = get_stations_by_city(self.stations_info, self.city)[0]

                    coords = self._get_coords_by_city(self.city)
                    self.display.update(coords, self.city, 0, self.station[0], False)
                    self.audio_player.play(self.city, self.station)

        except KeyboardInterrupt:
            logging.debug("👋 Exiting on keyboard interrupt...")
        finally:
            for hw in [self.audio_player, self.dial, self.encoders, self.display, self.led]:
                await hw.stop()
            GPIO.cleanup()


if __name__ == "__main__":
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)

    logging.info("Starting RadioGlobe...")

    asyncio.run(App().run())
