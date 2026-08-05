"""Structural interfaces (typing.Protocol) for RadioGlobe's hardware roles.

These describe the existing public surface of dial.py, positional_encoders.py,
buttons.py, rgb_led.py, display.py and audio_async.py exactly as it stands
today. Nothing in those modules needs to change or subclass anything here -
Protocol uses structural typing, so the existing concrete classes already
satisfy these interfaces by shape alone.
"""

import asyncio
from typing import Optional, Protocol, runtime_checkable

from radioglobe.coordinates import Coordinate


class HardwareComponent(Protocol):
    """Shared teardown shape common to all hardware roles.

    Deliberately does NOT declare start() - RGBLed and AudioPlayer have no
    start() at all (construction alone makes them ready; see rgb_led.py /
    audio_async.py), while the other four roles do. Each role protocol
    below declares start() only where the concrete class has one.
    """

    async def stop(self) -> None: ...


@runtime_checkable
class DialProtocol(HardwareComponent, Protocol):
    queue: "asyncio.Queue[int]"

    def start(self) -> None: ...


@runtime_checkable
class PositionalEncodersProtocol(HardwareComponent, Protocol):
    updated: asyncio.Event

    def zero(self) -> list: ...
    def reset_latch(self) -> None: ...
    def get_readings(self) -> tuple: ...
    def latch(self, latitude: int, longitude: int, stickiness: int) -> None: ...
    def is_latched(self) -> bool: ...
    def get_calibration(self) -> dict: ...
    def restore_calibration(self, state: dict) -> None: ...
    def start(self) -> None: ...


@runtime_checkable
class ButtonManagerProtocol(HardwareComponent, Protocol):
    event_queue: "asyncio.Queue"

    def start(self) -> None: ...
    async def handle_events(self) -> None: ...
    def get_event_nowait(self) -> Optional[tuple]: ...


@runtime_checkable
class RGBLedProtocol(HardwareComponent, Protocol):
    def set_color(self, color_name: str) -> None: ...
    def off(self) -> None: ...
    async def flash(self, color: str, duration: float) -> None: ...


@runtime_checkable
class DisplayProtocol(HardwareComponent, Protocol):
    changed: asyncio.Event

    def start(self) -> None: ...
    def message(
        self, line_1: str = "", line_2: str = "", line_3: str = "", line_4: str = ""
    ) -> None: ...
    def show_station(self, coords: Coordinate, city: str, station_name: str) -> None: ...
    def show_status(self, status: str, coords: Optional[Coordinate] = None) -> None: ...
    def update(
        self, coords: Coordinate, location: str, volume: int, station: str, arrows: bool
    ) -> None: ...


@runtime_checkable
class AudioPlayerProtocol(HardwareComponent, Protocol):
    current_url: Optional[str]

    def play(self, url: str) -> None: ...
    def change_volume(self, delta, min_volume: int = 10, max_volume: int = 100) -> int: ...
    def change_volume_level(self, level: int) -> int: ...
    def is_error(self) -> bool: ...
