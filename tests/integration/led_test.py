"""
LED hardware test — cycles through RED, GREEN, BLUE then blinks concurrently with async tasks.
NOTE: Requires Raspberry Pi hardware.

Usage:
    python tests/integration/led_test.py
"""

import asyncio
import time
import pytest

GPIO = pytest.importorskip("RPi.GPIO", reason="Requires Raspberry Pi hardware")

from radioglobe.rgb_led import RGBLed
from radioglobe.constants import COLOUR_RED, COLOUR_GREEN, COLOUR_BLUE


async def scheduler():
    while True:
        start_t = time.monotonic()
        await asyncio.sleep(0.5)
        print(f"Scheduler task ran for {time.monotonic() - start_t:.1f}")


async def led_cycle(led: RGBLed):
    """Cycle through RED, GREEN, BLUE then off."""
    print("Testing LEDs...")
    for colour in (COLOUR_RED, COLOUR_GREEN, COLOUR_BLUE):
        led.set_color(colour)
        await asyncio.sleep(1)
    led.off()


async def first_thing():
    print("Starting the first thing...")
    await asyncio.sleep(2)
    print("Finished first thing...")


async def second_thing():
    print("Starting second thing...")
    await asyncio.sleep(2)
    print("Finished second thing...")


async def main():
    # RGBLed.__init__'s GPIO.setup() calls require this to have been called
    # first. The real app does it once in App.__init__ (main.py) - this
    # script never constructs an App, so it has to do it itself.
    GPIO.setmode(GPIO.BCM)

    led = RGBLed()

    await led_cycle(led)

    asyncio.create_task(scheduler())

    while True:
        first_task = asyncio.create_task(first_thing())
        await led.flash(COLOUR_RED, 0.2)
        await first_task

        second_task = asyncio.create_task(second_thing())
        await led.flash(COLOUR_BLUE, 0.2)
        await second_task


if __name__ == "__main__":
    asyncio.run(main())
