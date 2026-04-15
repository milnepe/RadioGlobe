"""
Test harness for async cvlc streamer
"""

import asyncio
import pytest

pytest.importorskip("RPi.GPIO", reason="Requires Raspberry Pi hardware")
pytest.importorskip("spidev", reason="Requires SPI hardware")

from radioglobe import database
from radioglobe.rgb_led import RGBLed, led_task
from radioglobe.radio_config import STATIONS_JSON
from radioglobe.positional_encoders import PositionalEncoders
from streaming.streaming_cvlc import StreamerCVLC


async def get_cities(lat, lon, city_map, fuzziness=2) -> list:
    search_area = database.look_around((lat, lon), fuzziness=fuzziness)
    cities = database.get_found_cities(search_area, city_map)
    return cities


async def main():
    """
    Returns the cities found when the reticule is moved
    NOTE: Start with the reticule set to the origin
    """
    STICKINESS = 2
    FUZZINESS = 5
    AUDIO_SERVICE = "pulse"

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

    city_list = []
    station_info = None
    url = None
    streamer_task = None
    streamer = None
    while True:
        await encoders.updated.wait()
        encoders.updated.clear()
        readings = encoders.get_readings()
        city_list = await get_cities(*readings, cities, FUZZINESS)
        if not encoders.is_latched():
            if city_list:
                encoders.latch(*readings, STICKINESS)
                asyncio.create_task(led_task(led, led_running, "red", 0.5))
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


if __name__ == "__main__":
    asyncio.run(main())
