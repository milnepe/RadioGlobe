import asyncio
import logging
import subprocess
from typing import Optional

from radioglobe.constants import (
    MODE_CITY, MODE_STATION,
    STATUS_CALIBRATE, STATUS_CALIBRATED, STATUS_CALIBRATING, STATUS_SHUTDOWN,
)
from radioglobe.coordinates import Coordinate
from radioglobe.hal.protocols import (
    AudioPlayerProtocol,
    DialProtocol,
    DisplayProtocol,
    PositionalEncodersProtocol,
    RGBLedProtocol,
)
from radioglobe.hal.rgb_led import COLOUR_BLUE, COLOUR_GREEN, COLOUR_RED
from radioglobe.navigation import Navigator
from radioglobe.radio_config import (
    BRIEF_DISPLAY_DURATION, DEFAULT_VOLUME, FUZZINESS, LED_FLASH_DIAL, LED_FLASH_LONG,
    LED_FLASH_SHORT, LOG_LEVEL, MESSAGE_DISPLAY_DURATION, STATE_CACHE_PATH, STICKINESS,
    STREAM_CHECK_INTERVAL, VOLUME_OFF_LEVEL, VOLUME_ON_LEVEL, VOLUME_STEP,
)


class App:
    def __init__(
        self,
        dial: DialProtocol,
        audio_player: AudioPlayerProtocol,
        encoders: PositionalEncodersProtocol,
        display: DisplayProtocol,
        led: RGBLedProtocol,
        nav: Optional[Navigator] = None,
    ):
        self.dial = dial
        self.audio_player = audio_player
        self.encoders = encoders
        self.display = display
        self.led = led
        self.nav = nav if nav is not None else Navigator()
        self._stream_task: Optional[asyncio.Task] = None

    def save_state(self, cache=STATE_CACHE_PATH):
        self.nav.save_state(self.encoders.get_calibration(), cache)

    def load_state(self):
        encoder_state = self.nav.load_state(STATE_CACHE_PATH)
        if not encoder_state:
            return
        self.encoders.restore_calibration(encoder_state)

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

    def _play_station(self) -> str:
        """Show and play self.nav.state.station; returns the URL played."""
        coords = self.nav.current_coords
        name, url = self.nav.state.station
        self.display.show_station(coords, self.nav.state.city, name)
        self.audio_player.play(url)
        return url

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
            expected_url = self._play_station()

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
            cities = self.nav.refresh_nearby_cities(coords)

            if not self.encoders.is_latched() and cities:
                logging.debug(f"latch: {self.encoders.is_latched()} Cities: {cities}")
                asyncio.create_task(self.led.flash(COLOUR_GREEN, LED_FLASH_LONG))

                self.encoders.latch(*coords, stickiness=STICKINESS)
                logging.debug(f"Matching cities: stick:{STICKINESS} fuzz:{FUZZINESS} {cities} {self.encoders.is_latched()}")
                if not self.nav.select_city():
                    logging.warning(f"No stations for {self.nav.state.city!r} — skipping latch")
                    self.encoders.reset_latch()
                    continue
                logging.info(f"Cities: {cities}")
                logging.debug(
                    f"📻 Tuning to: city_idx:{self.nav.state.city_idx} "
                    f"{self.nav.state.city} {self.nav.state.station}\n{self.nav.state.stations}"
                )
                self._start_monitor_stream(self._play_station())

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
                if not self.nav.next_city_and_select_station(direction):
                    logging.warning(f"No stations for {self.nav.state.city!r} — keeping previous station")
                    continue

            self._start_monitor_stream(self._play_station())

    # ---------------------------------------------------------------------------
    # Button handlers
    # ---------------------------------------------------------------------------

    async def _on_jog_press(self):
        asyncio.create_task(self.led.flash(COLOUR_GREEN, LED_FLASH_SHORT))

    async def _handle_short_jog(self):
        self.nav.switch_mode()
        if self.nav.state.mode == MODE_STATION:
            idx, result = self.nav.state.station_idx, self.nav.state.stations
        else:
            idx, result = self.nav.state.city_idx, self.nav.state.cities
        logging.debug(f"🖲️ Jog button short press! Change mode idx: {idx} {result}")

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
        logging.debug(f"Encoder offsets set to: {self.encoders.get_calibration()}")
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
        # Deferred like hal/factory.py's build_hardware(): buttons.py imports
        # evdev at module scope, so importing radioglobe.main shouldn't
        # require evdev unless run() is actually called.
        from radioglobe.hal.buttons import ButtonCallbacks, create_button_manager

        self.dial.start()
        self.encoders.start()
        self.display.start()
        self.led.start()
        self.audio_player.start()
        self.audio_player.change_volume_level(DEFAULT_VOLUME)

        button_manager = create_button_manager(
            jog=ButtonCallbacks(short_cb=self._handle_short_jog, press_cb=self._on_jog_press),
            top=ButtonCallbacks(short_cb=self._handle_short_top, long_cb=self._handle_long_top, press_cb=self._on_sound_press),
            mid=ButtonCallbacks(short_cb=self._handle_short_mid, long_cb=self._handle_long_mid, press_cb=self._on_mid_press),
            bottom=ButtonCallbacks(short_cb=self._handle_short_bottom, long_cb=self._handle_long_bottom, press_cb=self._on_sound_press),
        )
        button_manager.start()
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
                f"State: {self.encoders.get_calibration()} "
                f"{self.nav.state.mode} {self.nav.state.city} {self.nav.state.station} {self.encoders.is_latched()}"
            )

            # The latch is set if there was saved state — this triggers playing the saved station
            if self.encoders.is_latched():
                if not self.nav.state.is_complete():
                    logging.warning("Saved state incomplete — starting in calibrate mode")
                    self.encoders.reset_latch()
                    self.display.show_status(STATUS_CALIBRATE)
                else:
                    self._start_monitor_stream(self._play_station())
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
            # Reverse of the start order above.
            for hw in [button_manager, self.audio_player, self.led, self.display, self.encoders, self.dial]:
                await hw.stop()


if __name__ == "__main__":
    from radioglobe.hal.factory import build_hardware

    logging.basicConfig(
        format="%(asctime)s: %(message)s",
        datefmt="%H:%M:%S",
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    )

    logging.info("Starting RadioGlobe...")

    asyncio.run(App(*build_hardware()).run())
