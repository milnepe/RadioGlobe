import asyncio
import logging
from typing import Optional
import liquidcrystal_i2c  # type: ignore
from .coordinates import Coordinate

_I2C_LCD_ADDR = 0x27
_DISPLAY_I2C_PORT = 1
_DISPLAY_COLUMNS = 20
_DISPLAY_ROWS = 4


class Display:
    def __init__(self) -> None:
        self.lcd = None
        self.buffer = ["" for _ in range(_DISPLAY_ROWS)]
        self.changed = asyncio.Event()
        self._task = None

    def start(self) -> None:
        """Connect to the LCD and start the background display update loop."""
        self.lcd = liquidcrystal_i2c.LiquidCrystal_I2C(
            _I2C_LCD_ADDR, _DISPLAY_I2C_PORT, numlines=_DISPLAY_ROWS
        )
        logging.info("Display initialized")
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._display_loop())
            logging.info("Display loop started")

    async def stop(self) -> None:
        """Stop the background display loop and wait for the task to finish."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logging.info("Display loop stopped")

    async def _display_loop(self) -> None:
        while True:
            await self.changed.wait()
            try:
                for line_num in range(_DISPLAY_ROWS):
                    self.lcd.printline(line_num, self.buffer[line_num])
            except Exception:
                logging.exception("Display write failed")
            self.changed.clear()
            await asyncio.sleep(0.1)

    def message(self, line_1: str = "", line_2: str = "", line_3: str = "", line_4: str = "") -> None:
        self.buffer[0] = line_1[:_DISPLAY_COLUMNS].center(_DISPLAY_COLUMNS)
        self.buffer[1] = line_2[:_DISPLAY_COLUMNS].center(_DISPLAY_COLUMNS)
        self.buffer[2] = line_3[:_DISPLAY_COLUMNS].center(_DISPLAY_COLUMNS)
        self.buffer[3] = line_4[:_DISPLAY_COLUMNS].center(_DISPLAY_COLUMNS)
        self.changed.set()
        logging.info(f"Message set: {[line_1, line_2, line_3, line_4]}")

    def show_station(self, coords: Coordinate, city: str, station_name: str) -> None:
        """Show the current city and station."""
        self.update(coords, city, volume=0, station=station_name, arrows=False)

    def show_status(self, status: str, coords: Optional[Coordinate] = None) -> None:
        """Show a status message (e.g. calibrating, shutdown)."""
        self.update(coords or Coordinate(0, 0), status, volume=0, station="", arrows=False)

    def update(self, coords: Coordinate, location: str, volume: int, station: str, arrows: bool) -> None:
        self.buffer[0] = str(coords)[:_DISPLAY_COLUMNS].center(_DISPLAY_COLUMNS)
        self.buffer[1] = location[:_DISPLAY_COLUMNS].center(_DISPLAY_COLUMNS)

        # Volume bar
        bar_length = (volume * _DISPLAY_COLUMNS) // 100
        self.buffer[2] = "-" * bar_length + " " * (_DISPLAY_COLUMNS - bar_length)

        if arrows and station:
            station = str(station)[: _DISPLAY_COLUMNS - 4]
            padding = _DISPLAY_COLUMNS - 4 - len(station)
            station = " " * (padding // 2) + station + " " * (padding - padding // 2)
            station = "< " + station + " >"
        else:
            station = str(station)[:_DISPLAY_COLUMNS]
        self.buffer[3] = station.center(_DISPLAY_COLUMNS)

        self.changed.set()
