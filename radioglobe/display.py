import asyncio
import logging
import liquidcrystal_i2c  # type: ignore
from coordinates import Coordinate
from radio_config import I2C_LCD_ADDR
DISPLAY_I2C_PORT = 1
DISPLAY_COLUMNS = 20
DISPLAY_ROWS = 4

# Configure logging
# logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class Display:
    def __init__(self):
        self.lcd = liquidcrystal_i2c.LiquidCrystal_I2C(
            I2C_LCD_ADDR, DISPLAY_I2C_PORT, numlines=DISPLAY_ROWS
        )
        self.buffer = ["" for _ in range(DISPLAY_ROWS)]
        self.changed = asyncio.Event()
        self.running = True
        self._task = None
        logging.info("Display initialized")

    def start(self):
        """Start the background display update loop."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._display_loop())
            logging.info("Display loop started")

    async def stop(self):
        """Stop the background display loop and wait for the task to finish."""
        self.running = False
        self.changed.set()
        if self._task:
            await self._task
            logging.info("Display loop stopped")

    async def _display_loop(self):
        while self.running:
            await self.changed.wait()
            try:
                for line_num in range(DISPLAY_ROWS):
                    self.lcd.printline(line_num, self.buffer[line_num])
            except Exception as e:
                logging.error(f"Display write failed: {e}")
            self.changed.clear()
            await asyncio.sleep(0.1)

    def clear(self):
        self.buffer = ["" for _ in range(DISPLAY_ROWS)]
        self.changed.set()
        logging.info("Display cleared")

    def message(self, line_1="", line_2="", line_3="", line_4=""):
        self.buffer[0] = line_1[:DISPLAY_COLUMNS].center(DISPLAY_COLUMNS)
        self.buffer[1] = line_2[:DISPLAY_COLUMNS].center(DISPLAY_COLUMNS)
        self.buffer[2] = line_3[:DISPLAY_COLUMNS].center(DISPLAY_COLUMNS)
        self.buffer[3] = line_4[:DISPLAY_COLUMNS].center(DISPLAY_COLUMNS)
        self.changed.set()
        logging.info(f"Message set: {[line_1, line_2, line_3, line_4]}")

    def update(self, coords: Coordinate, location: str, volume: int, station: str, arrows: bool):
        self.buffer[0] = str(coords).center(DISPLAY_COLUMNS)
        self.buffer[1] = location[:DISPLAY_COLUMNS].center(DISPLAY_COLUMNS)

        # Volume bar
        if not volume:
            volume = 0
        bar_length = (volume * DISPLAY_COLUMNS) // 100
        self.buffer[2] = "-" * bar_length + " " * (DISPLAY_COLUMNS - bar_length)

        if arrows and station:
            station = str(station)[: DISPLAY_COLUMNS - 4]
            padding = DISPLAY_COLUMNS - 4 - len(station)
            station = " " * (padding // 2) + station + " " * (padding - padding // 2)
            station = "< " + station + " >"
        else:
            station = station[:DISPLAY_COLUMNS]
        self.buffer[3] = station.center(DISPLAY_COLUMNS)

        self.changed.set()
        # logging.debug(
        #     f"Display updated: coords={coords}, location='{location}', volume={volume}, station='{station}', arrows={arrows}"
        # )


async def main():
    display = Display()
    display.start()

    bristol = Coordinate(51.45, -2.59)
    display.update(bristol, "Bristol, United Kingdom", 45, "BBC Radio Bristol", True)

    await asyncio.sleep(5)

    display.update(Coordinate(0, 0), "Clearing in 2s...", 0, "", False)
    await asyncio.sleep(2)

    display.clear()
    await asyncio.sleep(1)

    await display.stop()


if __name__ == "__main__":
    asyncio.run(main())
