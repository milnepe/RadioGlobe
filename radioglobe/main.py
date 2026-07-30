import asyncio
import json
import logging
import os
import subprocess
from dataclasses import asdict
from typing import Optional

import RPi.GPIO as GPIO  # type: ignore

from radioglobe.app_state import AppState
from radioglobe.audio_async import AudioPlayer
from radioglobe.buttons import AsyncButtonManager, ButtonDefinition
from radioglobe.constants import (
    COLOUR_BLUE, COLOUR_GREEN, COLOUR_RED,
    MODE_CITY, MODE_STATION,
    STATUS_CALIBRATE, STATUS_CALIBRATED, STATUS_CALIBRATING, STATUS_SHUTDOWN,
)
from radioglobe.coordinates import Coordinate
from radioglobe.database import get_stations_by_city, match_saved_station
from radioglobe.dial import AsyncDial
from radioglobe.display import Display
from radioglobe.navigation import Navigator
from radioglobe.positional_encoders import PositionalEncoders
from radioglobe.radio_config import (
    BRIEF_DISPLAY_DURATION, DEFAULT_VOLUME, FUZZINESS, LED_FLASH_DIAL, LED_FLASH_LONG,
    LED_FLASH_SHORT, LOG_LEVEL, MESSAGE_DISPLAY_DURATION, PIN_BTN_BOTTOM, PIN_BTN_JOG,
    PIN_BTN_MID, PIN_BTN_TOP, STATE_CACHE_PATH, STICKINESS,
    STREAM_CHECK_INTERVAL, VOLUME_OFF_LEVEL, VOLUME_ON_LEVEL, VOLUME_STEP,
)
from radioglobe.rgb_led import RGBLed


class App:
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        self.dial = AsyncDial()
        self.audio_player = AudioPlayer()
        self.audio_player.change_volume_level(DEFAULT_VOLUME)
        self.encoders = PositionalEncoders()
        self.display = Display()
        self.led = RGBLed()
        self.nav = Navigator()
        self._stream_task: Optional[asyncio.Task] = None

    def save_state(self, cache=STATE_CACHE_PATH):
        logging.debug(f"STATIONS: {self.nav.state.stations}")
        state = asdict(self.nav.state)
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

        self.nav.state = AppState(
            stations=state.get("stations") or [],
            station=tuple(state["station"]) if state.get("station") else None,
            cities=state.get("cities") or [],
            city=state.get("city"),
            jog_idx=state.get("jog_idx") or 0,
            mode=state.get("mode") or MODE_STATION,
        )
        self.encoders.latitude = state.get("lat")
        self.encoders.longitude = state.get("lon")
        self.encoders.latitude_offset = state.get("lat_offset")
        self.encoders.longitude_offset = state.get("lon_offset")
        self.encoders.latch_stickiness = True

        # Re-query stations from the live database so stale snapshots in the
        # cache never cause wrong URLs or indices after a stations.json update.
        if self.nav.state.city:
            try:
                self.nav.current_coords  # validate city still exists
            except KeyError as e:
                logging.warning(f"{e} — discarding stale saved city")
                self.nav.state.city = None
                self.nav.state.station = None
                return
            self.nav.state.stations = get_stations_by_city(self.nav.stations_info, self.nav.state.city)
            saved_name = state["station"][0] if state.get("station") else None
            self.nav.state.station, self.nav.state.jog_idx = match_saved_station(
                saved_name, self.nav.state.stations
            )

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    async def _show_volume_briefly(self, volume: int):
        """Display volume level temporarily, then revert to station info."""
        if not self.nav.state.is_complete():
            return
        coords = self.nav.current_coords
        self.display.update(coords, self.nav.state.city, volume, self.nav.state.station[0], arrows=False)
        await asyncio.sleep(BRIEF_DISPLAY_DURATION)
        self.display.show_station(coords, self.nav.state.city, self.nav.state.station[0])

    async def _update_volume(self, delta):
        """Adjust volume by delta and briefly show the level on the display."""
        if not self.nav.state.is_complete():
            return
        volume = self.audio_player.change_volume(delta)
        await self._show_volume_briefly(volume)

    async def _update_volume_level(self, level):
        """Set volume to an absolute level and briefly show it on the display."""
        if not self.nav.state.is_complete():
            return
        volume = self.audio_player.change_volume_level(level)
        await self._show_volume_briefly(volume)

    async def _monitor_stream(self, expected_url: str):
        """After a 3 s grace period, remove failed stations and try the next.

        Loops until a station plays without error, all stations have been
        removed, or the user selects a different station.
        """
        while self.nav.state.stations:
            await asyncio.sleep(STREAM_CHECK_INTERVAL)

            # User moved to a different station — stop watching
            if self.audio_player.current_url != expected_url:
                return

            if not self.audio_player.is_error():
                return  # playing fine

            if not self.nav.state.city:
                return

            logging.debug(f"⚠️ Stream error: {expected_url}")
            asyncio.create_task(self.led.flash(COLOUR_RED, LED_FLASH_LONG))
            self.nav.remove_failed_station()
            if not self.nav.state.station:
                break
            coords = self.nav.current_coords
            self.display.show_station(coords, self.nav.state.city, self.nav.state.station[0])
            self.audio_player.play(self.nav.state.city, self.nav.state.station)
            expected_url = self.nav.state.station[1]

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
            self.nav.state.cities = self.nav.find_cities_near(coords)

            if not self.encoders.is_latched() and self.nav.state.cities:
                logging.debug(f"latch: {self.encoders.is_latched()} Cities: {self.nav.state.cities}")
                asyncio.create_task(self.led.flash(COLOUR_GREEN, LED_FLASH_LONG))

                self.encoders.latch(*coords, stickiness=STICKINESS)
                self.nav.state.jog_idx = 0
                logging.debug(
                    f"Matching cities: jog:{self.nav.state.jog_idx} "
                    f"stick:{STICKINESS} fuzz:{FUZZINESS} {self.nav.state.cities} {self.encoders.is_latched()}"
                )
                self.nav.state.city = self.nav.state.cities[0]
                stations = get_stations_by_city(self.nav.stations_info, self.nav.state.city)
                if not self.nav.state.select_station(stations):
                    logging.warning(f"No stations for {self.nav.state.city!r} — skipping latch")
                    self.encoders.reset_latch()
                    continue
                logging.info(f"Cities: {self.nav.state.cities}")
                logging.debug(
                    f"📻 Tuning to: jog:{self.nav.state.jog_idx} "
                    f"{self.nav.state.city} {self.nav.state.station}\n{self.nav.state.stations}"
                )
                self.display.show_station(self.nav.current_coords, self.nav.state.city, self.nav.state.station[0])
                self.audio_player.play(self.nav.state.city, self.nav.state.station)
                self._start_monitor_stream(self.nav.state.station[1])

    async def _dial_loop(self):
        """Wake on each dial movement and handle station/city navigation."""
        while True:
            direction = await self.dial.queue.get()
            if not self.nav.state.is_complete():
                continue
            asyncio.create_task(self.led.flash(COLOUR_BLUE, LED_FLASH_DIAL))
            logging.debug(
                f"↪️ Dial turned: {'right' if direction > 0 else 'left'} dir:{direction}"
            )
            if self.nav.state.mode == MODE_STATION:
                self.nav.next_station(direction)
            elif self.nav.state.mode == MODE_CITY:
                self.nav.next_city(direction)
                stations = get_stations_by_city(self.nav.stations_info, self.nav.state.city)
                if not self.nav.state.select_station(stations):
                    logging.warning(f"No stations for {self.nav.state.city!r} — keeping previous station")
                    continue

            coords = self.nav.current_coords
            self.display.show_station(coords, self.nav.state.city, self.nav.state.station[0])
            self.audio_player.play(self.nav.state.city, self.nav.state.station)
            self._start_monitor_stream(self.nav.state.station[1])

    # ---------------------------------------------------------------------------
    # Button handlers
    # ---------------------------------------------------------------------------

    async def _on_jog_press(self):
        asyncio.create_task(self.led.flash(COLOUR_GREEN, LED_FLASH_SHORT))

    async def _handle_short_jog(self):
        self.nav.switch_mode()
        result = self.nav.state.stations if self.nav.state.mode == MODE_STATION else self.nav.state.cities
        logging.debug(f"🖲️ Jog button short press! Change mode jog: {self.nav.state.jog_idx} {result}")

    async def _handle_long_jog(self):
        logging.debug("🖲️ Jog button long press: None")
        await asyncio.sleep(LED_FLASH_SHORT)

    async def _on_sound_press(self):
        asyncio.create_task(self.led.flash(COLOUR_BLUE, LED_FLASH_SHORT))

    async def _handle_short_top(self):
        logging.debug("🖲️ Top button short press! Increasing volume.")
        await self._update_volume(VOLUME_STEP)

    async def _handle_long_top(self):
        logging.debug("🖲️ Top button long press! Set volume on")
        await self._update_volume_level(VOLUME_ON_LEVEL)

    async def _handle_short_bottom(self):
        logging.debug("🖲️ Bottom button short press! Lowering volume.")
        await self._update_volume(-VOLUME_STEP)

    async def _handle_long_bottom(self):
        logging.debug("🖲️ Bottom button long press! Set volume off")
        await self._update_volume_level(VOLUME_OFF_LEVEL)

    async def _on_mid_press(self):
        asyncio.create_task(self.led.flash(COLOUR_GREEN, LED_FLASH_SHORT))

    async def _handle_short_mid(self):
        logging.debug("🖲️ Mid button mid short press! Calibrating.")
        self.encoders.zero()
        self.encoders.reset_latch()
        logging.debug(
            f"Encoder offsets set to: {self.encoders.latitude}, {self.encoders.longitude} "
            f"{self.encoders.latitude_offset}, {self.encoders.longitude_offset}"
        )
        self.display.show_status(STATUS_CALIBRATING)
        await asyncio.sleep(MESSAGE_DISPLAY_DURATION)
        self.display.show_status(STATUS_CALIBRATED)

    async def _handle_long_mid(self):
        logging.debug("🔴 Shutdown initiated! Powering off...")
        self.save_state()
        logging.debug("Saved state...")
        coords = self.nav.current_coords or Coordinate(0, 0)
        self.display.show_status(STATUS_SHUTDOWN, coords)
        await asyncio.sleep(MESSAGE_DISPLAY_DURATION)
        if self.nav.state.city and self.nav.state.station:
            self.display.show_station(coords, self.nav.state.city, self.nav.state.station[0])
        await asyncio.sleep(BRIEF_DISPLAY_DURATION)
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
            ButtonDefinition("Jog",    PIN_BTN_JOG,    self._handle_short_jog,    None,                     self._on_jog_press),
            ButtonDefinition("Top",    PIN_BTN_TOP,    self._handle_short_top,    self._handle_long_top,   self._on_sound_press),
            ButtonDefinition("Mid",    PIN_BTN_MID,    self._handle_short_mid,    self._handle_long_mid,   self._on_mid_press),
            ButtonDefinition("Bottom", PIN_BTN_BOTTOM, self._handle_short_bottom, self._handle_long_bottom, self._on_sound_press),
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
            await asyncio.sleep(MESSAGE_DISPLAY_DURATION)

            try:
                self.load_state()
            except FileNotFoundError:
                pass  # no cache yet — normal on first boot
            except Exception as e:
                logging.warning(f"load_state failed: {e}")
            logging.debug(
                f"State: {self.encoders.latitude_offset} {self.encoders.longitude_offset} "
                f"{self.nav.state.mode} {self.nav.state.city} {self.nav.state.station} {self.encoders.is_latched()}"
            )

            # The latch is set if there was saved state — this triggers playing the saved station
            if self.encoders.is_latched():
                if not self.nav.state.is_complete():
                    logging.warning("Saved state incomplete — starting in calibrate mode")
                    self.encoders.reset_latch()
                    self.display.show_status(STATUS_CALIBRATE)
                else:
                    self.display.show_station(self.nav.current_coords, self.nav.state.city, self.nav.state.station[0])
                    self.audio_player.play(self.nav.state.city, self.nav.state.station)
                    self._start_monitor_stream(self.nav.state.station[1])
                    logging.debug(
                        f"Playing saved station: {self.nav.state.station} {self.nav.state.city} "
                        f"{self.nav.state.cities} {self.nav.state.stations}"
                    )
            else:
                self.display.show_status(STATUS_CALIBRATE)

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
