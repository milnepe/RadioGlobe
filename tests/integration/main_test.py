"""
Encoder index diagnostic test: displays the current index, search area, and
matched cities when the reticule latches onto a location. LED blinks red on latch.
No audio playback — use this to verify encoder calibration and city lookup.
NOTE: Start with the reticule set to the origin before running.

Usage:
    python tests/integration/main_test.py
    python tests/integration/main_test.py --stickiness 3 --fuzziness 7
"""

import asyncio
import argparse
import pytest

pytest.importorskip("RPi.GPIO", reason="Requires Raspberry Pi hardware")
pytest.importorskip("spidev", reason="Requires SPI hardware")

from radioglobe import database
from radioglobe.rgb_led import RGBLed, led_task
from radioglobe.radio_config import STATIONS_JSON
from radioglobe.positional_encoders import PositionalEncoders


async def main(stickiness: int, fuzziness: int):
    led = RGBLed()
    led_running = asyncio.Event()

    print("Starting up encoders...")
    encoders = PositionalEncoders()
    encoders.start()
    await asyncio.sleep(0.5)  # wait for first SPI read before zeroing
    encoders.zero()
    origin = encoders.get_readings()
    print(f"Origin index: {origin} (expect (512, 512) at equator/prime meridian)")

    print("Loading stations data...")
    stations = database.load_stations(STATIONS_JSON)
    print(f"Loaded {len(stations)} stations")
    print("Building city map...")
    city_map = database.build_cities_index(stations)
    print(f"Built city map with {len(city_map)} entries")
    offsets = database.build_look_around_offsets(fuzziness)

    print("Scanning — move the reticule to a city...\n")

    while True:
        await encoders.updated.wait()
        encoders.updated.clear()
        readings = encoders.get_readings()
        search_area = database.look_around(readings, offsets)
        city_list = database.get_found_cities(search_area, city_map)
        if not encoders.is_latched() and city_list:
            encoders.latch(*readings, stickiness)
            asyncio.create_task(led_task(led, led_running, "red", 0.5))
            print(f"Index:       {readings}")
            print(f"Search area: {search_area}")
            print(f"Cities:      {city_list}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RadioGlobe encoder index diagnostic")
    parser.add_argument("--stickiness", type=int, default=2, help="Latch stickiness (default: 2)")
    parser.add_argument("--fuzziness", type=int, default=5, help="Search area fuzziness (default: 5)")
    args = parser.parse_args()
    asyncio.run(main(args.stickiness, args.fuzziness))
