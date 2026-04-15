"""
Full stack integration test: encoders -> city lookup -> stream playback.
NOTE: Start with the reticule set to the origin before running.

Usage:
    python tests/integration/main_test.py
    python tests/integration/main_test.py --stickiness 3 --fuzziness 7 --polling-sec 0.5 --audio-service pulse
"""

import asyncio
import argparse
import time
import pytest

pytest.importorskip("RPi.GPIO", reason="Requires Raspberry Pi hardware")
pytest.importorskip("spidev", reason="Requires SPI hardware")

from radioglobe import database
from radioglobe.rgb_led import RGBLed, led_task
from radioglobe.radio_config import STATIONS_JSON
from radioglobe.positional_encoders import PositionalEncoders
from streaming.streaming_cvlc import StreamerCVLC


async def reader(encoders: PositionalEncoders):
    print("Starting reader...")
    while True:
        await asyncio.sleep(0.2)  # 200 ms


async def get_cities(lat, lon, city_map, fuzziness=2) -> list:
    search_area = database.look_around((lat, lon), fuzziness=fuzziness)
    cities = database.get_found_cities(search_area, city_map)
    return cities


async def main(stickiness: int, fuzziness: int, polling_sec: float, audio_service: str):
    """
    Returns the cities found when the reticule is moved
    NOTE: Start with the reticule set to the origin
    """
    STICKINESS = stickiness
    FUZZINESS = fuzziness
    POLLING_SEC = polling_sec
    AUDIO_SERVICE = audio_service

    led = RGBLed()
    led_running = asyncio.Event()

    print("Starting up encoders...")
    encoders = PositionalEncoders()
    encoders.zero()
    initial_readings = encoders.get_readings()
    print(initial_readings)

    print("Loading stations data...")
    stations = database.load_stations(STATIONS_JSON)
    print("Building city map...")
    cities = database.build_cities_index(stations)

    encoders.start()
    asyncio.create_task(reader(encoders))

    city_list = []
    station_info = None
    url = None
    streamer_task = None
    streamer = None
    while True:
        start_t = time.monotonic()
        readings = encoders.get_readings()
        city_list = await get_cities(*readings, cities, FUZZINESS)
        if not encoders.is_latched():
            if city_list:
                encoders.latch(*readings, STICKINESS)
                await led_task(led, led_running, "red", 0.5)
                first_city = city_list[0]
                station_info = database.get_stations_info(first_city, stations)
                print(f"Found: {city_list[0]} Station: {station_info}")
                name, url = station_info[0]
                print(f"First station: {name}, URL: {url} Latched: {encoders.is_latched()}")
                if streamer_task and streamer:
                    streamer.stop()
                    await streamer_task
                streamer = StreamerCVLC(AUDIO_SERVICE, url)
                streamer_task = asyncio.create_task(asyncio.to_thread(streamer.play))

        await asyncio.sleep(POLLING_SEC)
        elapst_t = time.monotonic() - start_t
        print(f"Coords: {readings} Cities: {city_list} Latched: {encoders.is_latched()} t={elapst_t:.1f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RadioGlobe main integration test")
    parser.add_argument("--stickiness", type=int, default=2, help="Latch stickiness (default: 2)")
    parser.add_argument("--fuzziness", type=int, default=5, help="Search area fuzziness (default: 5)")
    parser.add_argument("--polling-sec", type=float, default=1.0, help="Poll interval in seconds (default: 1.0)")
    parser.add_argument("--audio-service", default="pulse", help="Audio service (default: pulse)")
    args = parser.parse_args()
    asyncio.run(main(args.stickiness, args.fuzziness, args.polling_sec, args.audio_service))
