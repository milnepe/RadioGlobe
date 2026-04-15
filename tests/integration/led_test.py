"""
LED hardware test — cycles through RED, GREEN, BLUE then blinks concurrently with async tasks.
NOTE: Requires Raspberry Pi hardware.

Usage:
    python tests/integration/led_test.py
"""

import asyncio
import time
import pytest

pytest.importorskip("RPi.GPIO", reason="Requires Raspberry Pi hardware")

from radioglobe.rgb_led import RGBLed, led_task


async def scheduler():
    while True:
        start_t = time.monotonic()
        await asyncio.sleep(0.5)
        print(f"Scheduler task ran for {time.monotonic() - start_t:.1f}")


async def led_cycle(led: RGBLed):
    """Cycle through RED, GREEN, BLUE then off."""
    print("Testing LEDs...")
    for colour in ("red", "green", "blue"):
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
    led = RGBLed()
    led_running = asyncio.Event()

    await led_cycle(led)

    asyncio.create_task(scheduler())

    while True:
        first_task = asyncio.create_task(first_thing())
        await led_task(led, led_running, "red", 0.2)
        await first_task

        second_task = asyncio.create_task(second_thing())
        await led_task(led, led_running, "blue", 0.2)
        await second_task


if __name__ == "__main__":
    asyncio.run(main())
