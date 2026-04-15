"""
Encoder index diagnostic test: displays the current index, search area, and
matched cities when the reticule latches onto a location. LED blinks red on latch.
No audio playback — use this to verify encoder calibration and city lookup.
NOTE: Start with the reticule set to the origin before running.

Usage:
    python tests/integration/main_test.py
    python tests/integration/main_test.py --stickiness 3 --fuzziness 7 --polling-sec 0.5
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


async def get_search_results(lat, lon, city_map, fuzziness) -> tuple[list, list]:
    search_area = database.look_around((lat, lon), fuzziness=fuzziness)
    cities = database.get_found_cities(search_area, city_map)
    return search_area, cities


async def main(stickiness: int, fuzziness: int, polling_sec: float):
    led = RGBLed()
    led_running = asyncio.Event()

    print("Starting up encoders...")
    encoders = PositionalEncoders()
    encoders.zero()
    print(f"Initial index: {encoders.get_readings()}")

    print("Loading stations data...")
    stations = database.load_stations(STATIONS_JSON)
    print(f"Loaded {len(stations)} stations")
    print("Building city map...")
    cities = database.build_cities_index(stations)
    print(f"Built city map with {len(cities)} entries")

    encoders.start()
    print("Scanning — move the reticule to a city...\n")

    while True:
        readings = encoders.get_readings()
        search_area, city_list = await get_search_results(*readings, cities, fuzziness)
        if not encoders.is_latched() and city_list:
            encoders.latch(*readings, stickiness)
            await led_task(led, led_running, "red", 0.5)
            print(f"Index:       {readings}")
            print(f"Search area: {search_area}")
            print(f"Cities:      {city_list}\n")
        await asyncio.sleep(polling_sec)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RadioGlobe encoder index diagnostic")
    parser.add_argument("--stickiness", type=int, default=2, help="Latch stickiness (default: 2)")
    parser.add_argument("--fuzziness", type=int, default=5, help="Search area fuzziness (default: 5)")
    parser.add_argument("--polling-sec", type=float, default=1.0, help="Poll interval in seconds (default: 1.0)")
    args = parser.parse_args()
    asyncio.run(main(args.stickiness, args.fuzziness, args.polling_sec))
