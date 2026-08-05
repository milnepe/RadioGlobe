"""Fake hardware implementations satisfying radioglobe.hal.protocols.

Used by unit tests and off-Pi development to construct and drive App
end-to-end with no real I/O. These fakes intentionally do NOT re-implement
the real hardware modules' internal logic (SPI parity checks, evdev
capability matching, GPIO debounce/hold timing, etc.) - that's out of scope
here. A fake's only job is to be a well-behaved stand-in that App can hold a
reference to and that a test can drive/inspect.
"""

import asyncio
import inspect
import logging
from typing import Optional


class FakeDial:
    """Simulate dial turns via push_turn(); real Dial pushes +-1 ints too."""

    def __init__(self) -> None:
        self.queue: "asyncio.Queue[int]" = asyncio.Queue()
        self.started = False
        self.stopped = False

    def push_turn(self, direction: int) -> None:
        """Test hook: simulate a dial movement."""
        self.queue.put_nowait(direction)

    def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class FakePositionalEncoders:
    """Test hook: set_position()/latch() drive App._encoder_loop()."""

    def __init__(self, latitude_offset: int = 0, longitude_offset: int = 0) -> None:
        self.latitude = 0
        self.longitude = 0
        self.latitude_offset = latitude_offset
        self.longitude_offset = longitude_offset
        self.latch_stickiness = None
        self.updated = asyncio.Event()
        self.started = False
        self.stopped = False

    def set_position(self, lat: int, lon: int) -> None:
        """Test hook: simulate a new reading and wake _encoder_loop()."""
        self.latitude, self.longitude = lat, lon
        self.updated.set()

    def zero(self) -> list:
        self.latitude_offset = -self.latitude
        self.longitude_offset = -self.longitude
        return [self.latitude_offset, self.longitude_offset]

    def reset_latch(self) -> None:
        self.latch_stickiness = None

    def get_readings(self) -> tuple:
        return self.latitude + self.latitude_offset, self.longitude + self.longitude_offset

    def latch(self, latitude: int, longitude: int, stickiness: int) -> None:
        self.latch_stickiness = stickiness
        self.latitude, self.longitude = latitude, longitude

    def is_latched(self) -> bool:
        return self.latch_stickiness is not None

    def get_calibration(self) -> dict:
        return {
            "lat": self.latitude,
            "lon": self.longitude,
            "lat_offset": self.latitude_offset,
            "lon_offset": self.longitude_offset,
        }

    def restore_calibration(self, state: dict) -> None:
        self.latitude = state.get("lat")
        self.longitude = state.get("lon")
        self.latitude_offset = state.get("lat_offset")
        self.longitude_offset = state.get("lon_offset")
        self.latch_stickiness = True

    def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class FakeButtonManager:
    """Test hook: inject_event() drives handle_events() dispatch, no GPIO involved."""

    def __init__(self, button_definitions, long_press_threshold: float = 1.0) -> None:
        self.button_definitions = list(button_definitions)
        self.event_queue: "asyncio.Queue" = asyncio.Queue()
        self.started = False
        self.stopped = False

    async def inject_event(self, name: str, event_type: str) -> None:
        """Test hook: simulate a completed short/long press for button `name`."""
        await self.event_queue.put((name, event_type))

    def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def handle_events(self) -> None:
        while True:
            name, event_type = await self.event_queue.get()
            for definition in self.button_definitions:
                if definition.name == name:
                    handler = getattr(definition, f"{event_type}_cb", None)
                    if handler:
                        try:
                            if inspect.iscoroutinefunction(handler):
                                await handler()
                            else:
                                handler()
                        except Exception:
                            logging.exception(f"Button handler failed: {name} {event_type}")

    def get_event_nowait(self) -> Optional[tuple]:
        try:
            return self.event_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None


class FakeRGBLed:
    """Records every set_color()/flash() call for assertions."""

    def __init__(self) -> None:
        self.calls: list = []
        self.current_color: Optional[str] = None
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def set_color(self, color_name: str) -> None:
        self.current_color = color_name
        self.calls.append(("set_color", color_name))

    def off(self) -> None:
        self.set_color("off")

    async def stop(self) -> None:
        self.off()
        self.stopped = True

    async def flash(self, color: str, duration: float) -> None:
        self.calls.append(("flash", color, duration))
        self.set_color(color)
        self.off()


class FakeDisplay:
    """Records buffer state and every update()/show_*()/message() call."""

    ROWS = 4

    def __init__(self) -> None:
        self.buffer = ["" for _ in range(self.ROWS)]
        self.changed = asyncio.Event()
        self.calls: list = []
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    def message(self, line_1="", line_2="", line_3="", line_4="") -> None:
        self.buffer = [line_1, line_2, line_3, line_4]
        self.calls.append(("message", line_1, line_2, line_3, line_4))
        self.changed.set()

    def show_station(self, coords, city: str, station_name: str) -> None:
        self.calls.append(("show_station", coords, city, station_name))
        self.changed.set()

    def show_status(self, status: str, coords=None) -> None:
        self.calls.append(("show_status", status, coords))
        self.changed.set()

    def update(self, coords, location, volume, station, arrows) -> None:
        self.calls.append(("update", coords, location, volume, station, arrows))
        self.changed.set()


class FakeAudioPlayer:
    """Records play() calls; error state settable via set_error() for stream-monitor tests."""

    def __init__(self) -> None:
        self.current_url: Optional[str] = None
        self.played: list = []
        self.volume = 100
        self._error = False
        self.stopped_calls = 0
        self.started = False

    def start(self) -> None:
        self.started = True

    def play(self, url: str) -> None:
        self.current_url = url
        self.played.append(url)
        self._error = False

    def change_volume(self, delta, min_volume=10, max_volume=100) -> int:
        self.volume = max(min_volume, min(max_volume, self.volume + delta))
        return self.volume

    def change_volume_level(self, level: int) -> int:
        self.volume = level
        return self.volume

    def set_error(self, is_error: bool) -> None:
        """Test hook: simulate VLC entering/leaving an error state."""
        self._error = is_error

    def is_error(self) -> bool:
        return self._error

    async def stop(self) -> None:
        self.stopped_calls += 1
